#!/bin/bash

# set -euo pipefail
# set -u
set -eo pipefail

# (1) Activate LSST shared stack environment
source /work/stack/loadLSST.bash
setup -v pfs_pipe2d
setup -v display_matplotlib


# (2) Set local Python path for additional local installed packages
export LSST_PYTHON_USERLIB="/work/monodera/pyvenvs/lsst-stack-local-pythonlibs"
export PYTHONPATH="$LSST_PYTHON_USERLIB:$PYTHONPATH"

echo "LSST_PYTHON_USERLIB: $LSST_PYTHON_USERLIB"

# (3) Check if Panel is installed and print its version
python - <<'PY'
import sys
try:
    import panel as pn
    print("Panel:", pn.__version__)
except Exception as e:
    print("Panel not found:", e, file=sys.stderr)
    sys.exit(2)
PY

# # (4) Launch the app（--dev for auto-reload）
# python -m panel serve ./app.py --show --dev
python -m panel serve app.py --address 0.0.0.0 --allow-websocket-origin=pfsa-usr01.subaru.nao.ac.jp:5006 --dev



# Notes
# python3 -m pip install --target "$LSST_PYTHON_USERLIB" panel watchfiles loguru ipywidgets_bokeh ipympl python-dotenv
