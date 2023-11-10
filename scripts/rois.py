import logging
import os
from random import randrange
import omero
from omero.cli import cli_login
from omero.gateway import BlitzGateway, DatasetWrapper
from omero_rois import mask_from_binary_image
from omero.rtypes import rstring
import zarr
from skimage.transform import resize


PROJECT = "idr0138-lohoff-seqfish/experimentA"
RGBA = (255, 255, 255, 128)
DRYRUN = False


def create_image(conn, cells_data, nuclei_data, name, dataset):

    # find or create new Dataset
    target_name = f"{dataset.name}_seg"   # same as idr0079
    project = dataset.getParent()
    new_dataset = None
    for ds in project.listChildren():
        if ds.name == target_name:
            new_dataset = ds
    if new_dataset is None:
        ds = omero.model.DatasetI()
        ds.name = rstring(target_name)
        ds = conn.getUpdateService().saveAndReturnObject(ds, conn.SERVICE_OPTS)
        link = omero.model.ProjectDatasetLinkI()
        link.parent = omero.model.ProjectI(project.id, False)
        link.child = omero.model.DatasetI(ds.id.val, False)
        conn.getUpdateService().saveAndReturnObject(link)
        new_dataset = DatasetWrapper(conn, ds)

    # ensure all data is same dtype. nuclei was int8, cells is int32
    nuclei_data = nuclei_data.astype(cells_data.dtype)

    sizeZ = cells_data.shape[0]
    sizeC = 2
    
    def plane_gen():
        for z in range(sizeZ):
            for c in range(sizeC):
                yield(cells_data[z] if c == 0 else nuclei_data[z])

    image = conn.createImageFromNumpySeq(plane_gen(), name, sizeZ=sizeZ, sizeC=sizeC, dataset=new_dataset)
    logging.info(f"Created new image: {image.id}")
    conn.setChannelNames("Image", [image.id], {1: "Cells", 2: "Nuclei"})
    # turn on just the Cells, with glasbey LUT to highlight segmentation
    image.setActiveChannels([1], colors=['glasbey.lut'])
    image.saveDefaults()


def get_images(conn):
    project = conn.getObject('Project', attributes={'name': PROJECT})
    for dataset in project.listChildren():
        if "_seg" in dataset.name:
            continue
        for image in dataset.listChildren():
            if "labels" in image.name:
                continue
            yield dataset, image


def save_rois(conn, im, rois):
    logging.info(f"Saving {len(rois)} ROIs for image {im.id}:{im.name}")
    us = conn.getUpdateService()
    for roi in rois:
        im = conn.getObject('Image', im.id)
        roi.setImage(im._obj)
        roi = us.saveAndReturnObject(roi)
        if not roi:
            logging.warning("Saving ROI failed.")


def delete_rois(conn, im):
    result = conn.getRoiService().findByImage(im.id, None)
    to_delete = []
    for roi in result.rois:
        to_delete.append(roi.getId().getValue())
    if to_delete:
        logging.info(f"Deleting existing {len(to_delete)} rois")
        conn.deleteObjects("Roi", to_delete, deleteChildren=True, wait=True)


def scale_mask_from_binary_image(bin_img, size_x, size_y, rgba, z, c, t, text, raise_on_no_mask):
    # we want to resize the BINARY image since this avoids interpolation etc.
    scaled_img = resize(bin_img, (size_y, size_x))
    if rgba is None:
        rgba = [randrange(256), randrange(256), randrange(256), 128]
    return mask_from_binary_image(scaled_img, rgba, z, c, t, text, raise_on_no_mask)


def masks_from_label_image(
        labelim, size_x, size_y, rgba=None, z=None, c=None, t=None, text=""):
    masks = {}
    for i in range(1, labelim.max() + 1):
        mask = scale_mask_from_binary_image(labelim == i, size_x, size_y, rgba, z, c, t, f"{text}{i}",
                                      False)
        masks[i] = mask
    return masks


def create_rois(img_data, size_x, size_y, is_nuclei):
    
    # assume zyx dimensions
    size_z = img_data.shape[0]

    rois = []
    if is_nuclei:
        for i in range(size_z):
            plane = img_data[i]
            mask = scale_mask_from_binary_image(plane == 2, size_x, size_y, RGBA, i, None, None, "Nuclei", False)
            if mask:
                logging.info(f"Found nuclei masks for plane {i}")
                roi = omero.model.RoiI()
                roi.setName(rstring("Nuclei"))
                roi.addShape(mask)
                rois.append(roi)
            else:
                logging.warning(f"Found NO nuclei masks for plane {i}")
    else:
        for i in range(size_z):
            plane = img_data[i]
            plane_masks = masks_from_label_image(plane, size_x, size_y, rgba=None, z=i, c=None, t=None, text="Cell ")
            if plane_masks:
                logging.info(f"Found cell masks for plane {i}")
            else:
                logging.warning(f"Found NO cell masks for plane {i}")
            for cell_id, mask in plane_masks.items():
                # The cell_ids (label pixel values) aren't consistent across Z-sections (2D-segmentation instead of 3D)
                # We can't create 3D ROIs with multiple shapes. Just a single mask in each ROI...
                if mask is not None and mask.getBytes().any():
                    roi = omero.model.RoiI()
                    roi.setName(rstring(f"Cell {cell_id}"))
                    roi.addShape(mask)
                    rois.append(roi)

    logging.info("{} rois created.".format(len(rois)))
    return rois


def get_labels_data(image, name):
    # Find path/to/labels/cell/0 highest resolution of cells image
    cps = image.getImportedImageFilePaths()["client_paths"]
    path_to_zarr = cps[0].split(".zarr")[0]
    labels_path = f"/{path_to_zarr}.zarr/labels/{name}/0/"
    if os.path.exists(labels_path):
        return zarr.open(labels_path)
    else:
        logging.warning(f"Could not find {labels_path} for {image.name}")
        return None


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s [%(pathname)s, %(lineno)s]')
    with cli_login() as c:
        conn = BlitzGateway(client_obj=c.get_client())
        for ds, im in get_images(conn):
            size_y = im.getSizeY()
            size_x = im.getSizeX()
            try:
                logging.info(f"Processing Image: {im.id} {im.name}")
                if not DRYRUN:
                    delete_rois(conn, im)
                cells_data = get_labels_data(im, "cells")
                rois = []
                if cells_data is not None:
                    rois.extend(create_rois(cells_data, size_x, size_y, False))
                nuc_data = get_labels_data(im, "nuclei")
                if nuc_data is not None:
                    rois.extend(create_rois(nuc_data, size_x, size_y, True))
                if not DRYRUN and len(rois) > 0:
                    save_rois(conn, im, rois)

                # Create new Image
                # if nuc_data is not None or cells_data is not None:
                #     create_image(conn, cells_data, nuc_data, im.name, ds)
            except Exception as e:
                logging.warning(e)


if __name__ == "__main__":
    main()
