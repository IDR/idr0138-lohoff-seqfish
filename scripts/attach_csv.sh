#!/bin/bash

# Attach csv as bulkannotation to dataset, has to be named <Dataset Name>_<something else>.csv
#
# Run script like this: ./attach_csv.sh <CSV file>

set -euo pipefail

filename=$1
datasetname=${filename%_*.csv}
datasetid=`omero hql -q --style plain --ids-only "select d.id from Dataset d where d.name = '${datasetname}'" | cut -d, -f2`
omero metadata populate Dataset:$datasetid --file $filename
