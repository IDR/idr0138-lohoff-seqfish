# Create a filePaths.tsv which only contains one image per dataset, for testing

with open("../experimentA/idr0138-experimentA-filePaths.tsv", "r") as infile:
    with open("../experimentA/idr0138-experimentA-filePaths_sample.tsv", mode="w") as outfile:
        files = dict()
        for line in infile.readlines():
            line = line.strip()
            parts = line.split("\t")
            if parts[0] not in files:
                files[parts[0]] = set()
            files[parts[0]].add(line)

        for k,v in files.items():
            outfile.write(f"{v.pop()}\n")
