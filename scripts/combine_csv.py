import csv
import os
import re

"""
Combines the submitted csv files into one cellData and one segmentedData csv
for each of the two dataset types TimEmbryos-102219 and TimEmbryos-120919
"""

PROCESSED_FILE_DIR = "../processed_files"

DS_0 = "TimEmbryos-102219"
DS_1 = "TimEmbryos-120919"

# Area,Centroid_1,Centroid_2,BoundingBox_1,BoundingBox_2,BoundingBox_3,BoundingBox_4,cellID,z
# 732848,1162.89787786826,248.662740431849,0.5,0.5,2048,1168,1,2
#HEADER_CELL = "# header roi,image,s,l,d,d,d,d,l,l,l,l"
FIELDS_CELL = "Image,Roi,Shape,ImageName,Area,Centroid_1,Centroid_2,BoundingBox_1,BoundingBox_2,BoundingBox_3,BoundingBox_4,cellID,z".split(',')

# cellID,geneID,regionID,x,y,z,seeds,intensity
# 135,Abcc4,1,670.522,423.266,2,4,671
#HEADER_SEG = "# header roi,image,s,l,s,l,d,d,l,l,l"
FIELDS_SEG = "Image,Roi,Shape,ImageName,cellID,geneID,regionID,x,y,z,seeds,intensity".split(',')

def create_writer(ds, is_cell):
    if is_cell:
        filename = f"{PROCESSED_FILE_DIR}/{ds}-cellData-processed.csv"
    else:
        filename = f"{PROCESSED_FILE_DIR}/{ds}-segmentedData-processed.csv"
    outfile = open(filename, mode="w")
    if is_cell:
        writer = csv.DictWriter(outfile, fieldnames=FIELDS_CELL)
    else:
        writer = csv.DictWriter(outfile, fieldnames=FIELDS_SEG)
    writer.writeheader()
    return outfile, writer

outfiles = []
writers = dict()
for d in DS_0, DS_1:
    for c in True, False:
        o, w = create_writer(d, c)
        outfiles.append(o)
        writers[f"{d}{c}"] = w

for file in os.scandir(PROCESSED_FILE_DIR):
    # TimEmbryos-102219-Pos0-cellData.csv
    # TimEmbryos-102219-Pos0-segmentedData.csv
    filename = file.name

    if "Pos" not in filename:
        continue

    print(f"Processing {filename} ...")

    is_cell = "cellData" in filename
    is_seg = "segmentedData" in filename
    if not is_seg and not is_cell:
        print(f"Skipping {filename}")
        continue

    pat = re.compile(r"TimEmbryos-(?P<ds>.+)-(?P<pos>.+)-.+")
    m = pat.match(filename).groupdict()
    m['ds'] = f"TimEmbryos-{m['ds']}"
    img_name = f"MMStack_{m['pos']}.ome.zarr"

    key = f"{m['ds']}{is_cell}"
    if not key in writers:
        print(f"Can't find {key}")
        continue

    with open(file, mode="r") as csvfile:
        reader = csv.DictReader(csvfile)
        fnames = reader.fieldnames.copy()
        fnames.insert(0, "ImageName")
        fnames.insert(0, "Shape")
        fnames.insert(0, "Roi")
        fnames.insert(0, "Image")

        for row in reader:
            row["Image"] = "-1"
            row["Roi"] = "-1"
            row["Shape"] = "-1"
            row["ImageName"] = img_name
            writers[key].writerow(row)

for outfile in outfiles:
    outfile.close()
