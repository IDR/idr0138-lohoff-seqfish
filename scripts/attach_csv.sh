#!/bin/bash

# Attach csv as bulkannotation to dataset, has to be named <Dataset Name>_<something else>.csv
#
# Run script like this: ./attach_csv.sh <CSV file>

# This will need https://github.com/ome/omero-metadata/pull/86

set -euo pipefail

filename=$1
datasetname=${filename%_*.csv}
tablename=${filename##*_}
datasetid=`omero hql -q --style plain --ids-only "select d.id from Dataset d where d.name = '${datasetname}'" | cut -d, -f2`
omero metadata populate Dataset:$datasetid --allow_nan --table-name $tablename --file $filename
