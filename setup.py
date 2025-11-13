"""
Setup script for pfs-quicklook

WARNING: This package should NOT be installed via pip install.
This is a web application that requires the LSST Science Pipelines stack.

Installation Instructions:
1. Load LSST stack: source /work/stack/loadLSST.bash
2. Setup PFS pipelines: setup -v pfs_pipe2d && setup -v display_matplotlib
3. Install additional dependencies:
   pip install --target $LSST_PYTHON_USERLIB -r requirements.txt
4. Run the application: bash launch_app.bash

See README.md for detailed installation instructions.
"""

import setuptools

# This setup.py is designed to prevent pip installation by raising an error
# when setuptools.setup() is called during the build process

ERROR_MESSAGE = """
================================================================================
ERROR: This package cannot be installed via 'pip install .'
================================================================================

This is a web application that requires the LSST Science Pipelines stack
to be pre-installed and configured.

Proper installation steps:
  1. Load LSST stack environment
  2. Install additional dependencies with:
     pip install --target $LSST_PYTHON_USERLIB -r requirements.txt
  3. Configure .env file
  4. Launch with: bash launch_app.bash

See README.md for detailed instructions.
================================================================================
"""

# Raise an error immediately to prevent installation
raise RuntimeError(ERROR_MESSAGE)
