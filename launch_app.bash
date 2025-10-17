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

# Default server settings
ADDRESS="0.0.0.0"
PORT="5106"
ORIGIN="pfsa-usr01.subaru.nao.ac.jp"

# Determine mode from first argument
MODE="$1"

if [[ "$MODE" == "dev" ]]; then
  echo "Running in development mode with auto-reload"
  PORT="5206"
  python -m panel serve app.py \
    --address $ADDRESS \
    --port $PORT \
    --allow-websocket-origin=$ORIGIN:$PORT \
    --dev
else
  echo "Running in production mode with multi-threading"
  PORT="5106"
  python -m panel serve app.py \
    --address $ADDRESS \
    --port $PORT \
    --allow-websocket-origin=$ORIGIN:$PORT \
    --num-threads 8
fi


# Notes
# python3 -m pip install --target "$LSST_PYTHON_USERLIB" panel watchfiles loguru ipywidgets_bokeh ipympl python-dotenv joblib datashader "holoviews[recommended]"

