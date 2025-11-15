#!/bin/bash
set -eo pipefail

# Change to script directory to ensure .env is found
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables from .env file
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -v '^#' .env | grep -v '^[[:space:]]*$')
  set +a
else
  echo "Error: .env file not found in $SCRIPT_DIR" >&2
  exit 1
fi

# Check if PFS_APP_HOSTNAME is set and matches current hostname
CURRENT_HOSTNAME=$(hostname -f)
if [[ -z "$PFS_APP_HOSTNAME" ]]; then
  echo "Error: PFS_APP_HOSTNAME is not set in .env file" >&2
  exit 1
fi

if [[ "$PFS_APP_HOSTNAME" != "$CURRENT_HOSTNAME" ]]; then
  echo "Hostname mismatch: PFS_APP_HOSTNAME=$PFS_APP_HOSTNAME, current hostname=$CURRENT_HOSTNAME"
  echo "Skipping application launch."
  exit 0
fi

echo "Hostname matches: $CURRENT_HOSTNAME"

# Activate LSST shared stack environment
source /work/stack/loadLSST.bash
setup -v pfs_pipe2d
# setup -v display_matplotlib

# Check if LSST_PYTHON_USERLIB is set in .env file
if [[ -z "$LSST_PYTHON_USERLIB" ]]; then
  echo "Error: LSST_PYTHON_USERLIB is not set in .env file" >&2
  exit 1
fi

# Set local Python path for additional local installed packages
export PYTHONPATH="$LSST_PYTHON_USERLIB:$PYTHONPATH"

echo "LSST_PYTHON_USERLIB: $LSST_PYTHON_USERLIB"

# Server settings
ADDRESS="0.0.0.0"
ORIGIN="$PFS_APP_HOSTNAME"

# Determine mode from first argument
MODE="${1:-production}"

if [[ "$MODE" == "dev" ]]; then
  echo "Running in development mode with auto-reload"
  PORT="5206"
  python -m panel serve app.py \
    --address "$ADDRESS" \
    --port "$PORT" \
    --allow-websocket-origin="$ORIGIN:$PORT" \
    --allow-websocket-origin="localhost:$PORT" \
    --allow-websocket-origin="127.0.0.1:$PORT" \
    --prefix quicklook \
    --dev
else
  echo "Running in production mode with multi-threading"
  PORT="5106"
  python -m panel serve app.py \
    --address "$ADDRESS" \
    --port "$PORT" \
    --allow-websocket-origin="$ORIGIN:$PORT" \
    --allow-websocket-origin="localhost:$PORT" \
    --allow-websocket-origin="127.0.0.1:$PORT" \
    --prefix quicklook \
    --num-threads 8
fi

echo "Application started successfully on $ORIGIN:$PORT"


# Notes
# python3 -m pip install --target "$LSST_PYTHON_USERLIB" panel watchfiles loguru ipywidgets_bokeh ipympl python-dotenv joblib datashader "holoviews[recommended]"

