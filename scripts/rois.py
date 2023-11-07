import logging
import omero
from omero.cli import cli_login
from omero.gateway import BlitzGateway
from omero_rois import mask_from_binary_image
from omero.rtypes import rstring
import zarr


PROJECT = "idr0138-lohoff-seqfish/experimentA"
RGBA = (255, 255, 0, 128)
DRYRUN = False


def get_images(conn):
    project = conn.getObject('Project', attributes={'name': PROJECT})
    for dataset in project.listChildren():
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


def masks_from_label_image(
        labelim, rgba=None, z=None, c=None, t=None, text=""):
    masks = {}
    for i in range(1, labelim.max() + 1):
        mask = mask_from_binary_image(labelim == i, rgba, z, c, t, f"{text}{i}",
                                      False)
        masks[i] = mask
    return masks


def create_rois(img_data, is_nuclei):
    
    # assume zyx dimensions
    size_z = img_data.shape[0]

    rois = []
    if is_nuclei:
        for i in range(size_z):
            plane = img_data[i]
            print(f"Nuclei plane {i}")
            mask = mask_from_binary_image(plane == 2, RGBA, i, None, None, "Nucleis", False)
            if mask:
                logging.info(f"Found nuclei masks for plane {i}")
                roi = omero.model.RoiI()
                roi.setName(rstring("Nucleis"))
                roi.addShape(mask)
                rois.append(roi)
            else:
                logging.warning(f"Found NO nuclei masks for plane {i}")
    else:
        rois_map = {}
        for i in range(size_z):
            plane = img_data[i]
            print(f"Cell plane {i}")
            plane_masks = masks_from_label_image(plane, rgba=RGBA, z=i, c=None, t=None, text="Cell ")
            if plane_masks:
                logging.info(f"Found cell masks for plane {i}")
            else:
                logging.warning(f"Found NO cell masks for plane {i}")
            for cell_index, mask in plane_masks.items():
                if mask.getBytes().any():
                    if cell_index not in rois_map:
                        roi = omero.model.RoiI()
                        roi.setName(rstring(f"Cell {cell_index}"))
                        rois_map[cell_index] = roi
                    else:
                        roi = rois_map[cell_index]
                    roi.addShape(mask)
        rois = list(rois_map.values())

    logging.info("{} rois created.".format(len(rois)))
    return rois


def get_labels_data(image, name):
    # Find path/to/labels/cell/0 highest resolution of cells image
    path_to_zarr = None
    for orig_file in image.getFileset().listFiles():
        if orig_file.path.endswith(f".zarr/labels/{name}/0/"):
            path_to_zarr = orig_file.path
    if path_to_zarr is None:
        logging.warning(f"Could not find {name} for {image.name}")
        return None
    return zarr.open(path_to_zarr)


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s [%(pathname)s, %(lineno)s]')
    with cli_login() as c:
        conn = omero.gateway.BlitzGateway(client_obj=c.get_client())
        for ds, im in get_images(conn):
            try:
                logging.info(f"Processing {im.name}")
                if not DRYRUN:
                    delete_rois(conn, im)
                cells_data = get_labels_data(im, "cells")
                rois = []
                if cells_data is not None:
                    rois.extend(create_rois(cells_data, False))
                nuc_data = get_labels_data(im, "nuclei")
                if nuc_data is not None:
                    rois.extend(create_rois(nuc_data, True))
                if not DRYRUN and len(rois) > 0:
                    save_rois(conn, im, rois)
            except Exception as e:
                logging.warning(e)


if __name__ == "__main__":
    main()
