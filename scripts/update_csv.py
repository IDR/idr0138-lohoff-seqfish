import csv
import os

import omero.cli
from omero.gateway import BlitzGateway

"""
Creates a cellData and segmentedData csv for each dataset, which includes the image, roi and shape ids.
Attach these later with: omero metadata populate Dataset:123 --allow_nan --file xyz.csv
"""

DS_0 = "TimEmbryos-102219"
DS_1 = "TimEmbryos-120919"

PROCESSED_FILE_DIR = "../processed_files"
OUT_DIR = "../processed_files_with_ids"

PROJECT_NAME = "idr0138-lohoff-seqfish/experimentA"

HEADER_CELL = "# header image,roi,l,s,l,d,d,d,d,l,l,l,l"
HEADER_SEG = "# header image,roi,l,s,l,s,l,d,d,l,l,l"

def get_reader(ds, is_cell):
    if is_cell:
        filename = f"{PROCESSED_FILE_DIR}/{ds}-cellData-processed.csv"
    else:
        filename = f"{PROCESSED_FILE_DIR}/{ds}-segmentedData-processed.csv"
    infile = open(filename, mode="r")
    reader = csv.DictReader(infile)
    return infile, reader


def get_roi_id(conn, image, z, roi_name, roi_cache):
    if not roi_cache:
        roi_service = conn.getRoiService()
        roi_cache = roi_service.findByImage(image.getId(), None).rois
    for roi in roi_cache:
        if roi.getName().getValue() == roi_name:
            shape = roi.copyShapes()[0]
            if shape.theZ.getValue() == z:
                return roi.getId().getValue(), shape.getId().getValue(), roi_cache
    print(f"WARN: Could not find {roi_name} on z={z} for {image.getName()}")
    return None, None, roi_cache


with omero.cli.cli_login() as c:
    conn = BlitzGateway(client_obj=c.get_client())
    project = conn.getObject("Project", attributes={"name": PROJECT_NAME})
    for cell in True, False:
        for dataset in project.listChildren():
            if DS_0 in dataset.getName():
                ifile, reader = get_reader(DS_0, cell)
            elif DS_1 in dataset.getName():
                ifile, reader = get_reader(DS_1, cell)
            else:
                print(f"WARN: Can't handle {dataset.getName()}")
                continue

            images = dict()
            roi_cache = dict()
            for img in dataset.listChildren():
                images[img.getName()] = img
                roi_cache[img.getName()] = None

            if cell:
                ofilename = f"{OUT_DIR}/{dataset.getName()}_cellData.csv"
            else:
                ofilename = f"{OUT_DIR}/{dataset.getName()}_segmentedData.csv"

            if os.path.exists(ofilename):
                print(f"Skipping existing file {ofilename}")
                continue

            with open(ofilename, mode="w") as ofile:
                print(f"Processing {ofilename} ...")
                if cell:
                    ofile.write(f"{HEADER_CELL}\n")
                else:
                    ofile.write(f"{HEADER_SEG}\n")
                writer = csv.DictWriter(ofile, fieldnames=reader.fieldnames.copy())
                writer.writeheader()
                for row in reader:
                    img_name = row['ImageName']
                    if img_name not in images:
                        print(f"WARN: Can't find {img_name}")
                        writer.writerow(row)
                        continue
                    row['Image'] = images[img_name].getId()

                    roi_name = f"Cell {row['cellID']}"
                    z_plane = int(row['z'])-1
                    roi_id, shape_id, roi_cache[img_name] = get_roi_id(conn, images[img_name], z_plane, roi_name, roi_cache[img_name])
                    if not roi_id:
                        print(f"Can't find {roi_name} for {img_name}")
                        writer.writerow(row)
                        continue
                    row['Roi'] = roi_id
                    row['Shape'] = shape_id
                    writer.writerow(row)
            ifile.close()
