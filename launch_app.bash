#!/bin/bash

set -eo pipefail

# Activate LSST shared stack environment
source /work/stack/loadLSST.bash
setup -v pfs_pipe2d
setup -v display_matplotlib


# Set local Python path for additional local installed packages
export LSST_PYTHON_USERLIB="/work/monodera/pyvenvs/lsst-stack-local-pythonlibs"
export PYTHONPATH="$LSST_PYTHON_USERLIB:$PYTHONPATH"

echo "LSST_PYTHON_USERLIB: $LSST_PYTHON_USERLIB"

# Launch the app
# Check if 'dev' option is passed
DEV_FLAG=""
if [[ "$1" == "dev" ]]; then
    DEV_FLAG="--dev"
    echo "Running in development mode with auto-reload"
fi

python -m panel serve app.py --address 0.0.0.0 --allow-websocket-origin=pfsa-usr01.subaru.nao.ac.jp:5006 $DEV_FLAG



# Notes
# python3 -m pip install --target "$LSST_PYTHON_USERLIB" panel watchfiles loguru ipywidgets_bokeh ipympl python-dotenv joblib datashader "holoviews[recommended]"
