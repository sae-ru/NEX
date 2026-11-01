#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
exec "${NEX_PYTHON:-python3}" -X utf8 "$project_dir/project.py" test "$@"
