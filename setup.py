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

import sys


def main():
    """Prevent standard pip installation"""
    print("\n" + "=" * 70)
    print("ERROR: This package cannot be installed via 'pip install .'")
    print("=" * 70)
    print("\nThis is a web application that requires the LSST Science Pipelines")
    print("stack to be pre-installed and configured.")
    print("\nProper installation steps:")
    print("  1. Load LSST stack environment")
    print("  2. Install additional dependencies with:")
    print("     pip install --target $LSST_PYTHON_USERLIB -r requirements.txt")
    print("  3. Configure .env file")
    print("  4. Launch with: bash launch_app.bash")
    print("\nSee README.md for detailed instructions.")
    print("=" * 70 + "\n")
    sys.exit(1)


if __name__ == "__main__":
    main()
