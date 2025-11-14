# PFS Quicklook Web App

This repository contains a web application for quick inspection of data from the Prime Focus Spectrograph (PFS). The app is designed for summit/remote observers to perform real-time quality assessment of spectral data during observations.

The app replaces the previous Jupyter notebook-based quicklook tool ([check_quick_reduction_data.ipynb](check_quick_reduction_data.ipynb)) with a production-ready web interface featuring:

- **Fiber configuration viewer** with interactive table showing pointing and fiber details
- **Interactive 2D/1D spectral visualization** with zoom, pan, and hover tools
- **Multi-user support** with per-session state isolation
- **Performance optimizations** (8× faster 2D rendering, 100× faster visit discovery)
- **Automatic visit discovery** with configurable auto-refresh
- **Dual deployment modes** (development/production)

## Prerequisites

You need to have access to one of PFSA servers to run this app. Also, you need a proper configuration file for database access. Please ask Moritani-san, Yabe-sa, or other relevant PFS obsproc team members for the configuration file.

## Installation and Setup

1. Activate LSST stack environment:

   ```bash
   source /work/stack/loadLSST.bash
   ```

2. Clone the repository and move into the directory:

   ```bash
   git clone https://github.com/Subaru-SciOp/pfs_quicklook.git
   cd pfs_quicklook
   ```

3. Create a directory to install additional Python pacakges which are not included in the LSST stack:

   ```bash
   mkdir -p /work/<your_username>/lsst-stack-local-pythonlibs
   ```

4. Install required Python packages using pip:

   ```bash
   # make sure to use the python3 from the LSST stack
   which python3
   # should return something like /work/stack-2025-06-06/conda/envs/lsst-scipipe-10.0.0/bin/python3
   python3 -m pip install --target=/work/<your_username>/lsst-stack-local-pythonlibs -r requirements.txt
   ```

5. Create and edit `.env` file:

   ```bash
   cp .env.example .env
   vi .env
   # nano .env  # if you prefer nano editor
   ```

   Make sure to set the correct values for the following variables in the `.env` file. An example is shown below:

   ```bash
   # datastore directory to fetch reduced data
    PFS_DATASTORE="/work/datastore"

    # name of the base collection for the reduction
    PFS_BASE_COLLECTION="<collection name for the night>"

    # observation date to be considered (YYYY-MM-DD format)
    # only single data is allowed
    PFS_OBSDATE_UTC="2025-05-26"

    # Auto-refresh interval for visit list (in seconds)
    # Set to 0 to disable auto-refresh
    # Default: 300 seconds (5 minutes)
    PFS_VISIT_REFRESH_INTERVAL=300

    # hostname to run the app
    # full hostname can be obtained by running `hostname -f` command
    PFS_APP_HOSTNAME=<your_server_hostname>

    # Location of additional Python packages
    # This will be used by pip when --target option is used
    LSST_PYTHON_USERLIB="/work/<your_username>/lsst-stack-local-pythonlibs"
   ```

6. Launch the app from the command line:

   ```bash
   # I recommend to run the script inside a screen or tmux session
   bash ./launch_app.bash
   ```

7. Access the app from your web browser:

   **Production mode** (default):

   ```text
   http://<your_server_hostname>:5106/quicklook
   ```

   **Development mode** (if launched with `dev` argument: `bash launch_app.bash dev`):

   ```text
   http://<your_server_hostname>:5206/quicklook
   ```

   The launch script automatically selects the appropriate port based on deployment mode.

## Features

### Core Functionality

- **2D Spectral Images**: Sky-subtracted 2D images with interactive zoom/pan
  - Fast Preview Mode (default): 8× faster rendering with Datashader rasterization
  - Pixel Inspection Mode: Full resolution with exact pixel values for quality assessment
- **1D Spectra Visualization**: Interactive plots with fiber selection and OB code filtering
- **1D Gallery View**: 2D representation showing all fiber spectra at once
- **Automatic Visit Discovery**: Background discovery with configurable auto-refresh (default: 5 minutes)
- **Real-time Configuration Display**: Shows current datastore, collection, and observation date

### Performance Features

- **Parallel Processing**: Utilizes all CPU cores for fast data loading
- **Session Caching**: Intelligent caching of Butler instances and visit metadata
- **Non-blocking UI**: All long operations run in background threads
- **Multi-user Support**: Independent sessions for concurrent users

### User Interface

- **Bidirectional Fiber Selection**: Link between OB codes and Fiber IDs
- **Visit List**: Newest visits first for easy access to recent observations
- **Toast Notifications**: User-friendly feedback for all operations
- **Responsive Design**: Works on various screen sizes

## Usage

### Basic Workflow

1. **Configuration Check**: Verify datastore path and collection in the sidebar configuration display
2. **Select Spectrograph**: Choose spectrographs 1-4 from checkbox group (all selected by default)
3. **Load Visit Data**: Select visit from dropdown and click "Load Data"
4. **Visualize Data**: Use Plot 2D, Plot 1D, or Plot 1D Image buttons
5. **Filter Fibers** (optional): Select by OB Code or Fiber ID for focused analysis

### Load Visits

1. Select the spectrograph (1 to 4) from the checkbox group on the sidebar. All spectrographs are selected by default.
2. Select the visit from the `Visit` selection box. When focused, you will see the dropdown list of available visits (newest first). You can also type the visit number to search.
3. Once a visit is selected, press the `Load Data` button to load the data for the selected visit.
4. Visit list is automatically refreshed based on the interval set in the `.env` file (default: 5 minutes).

**Note**: Currently, only a single visit can be loaded at a time.

[![Screenshot Load Visit](docs/img/screenshot_loadvisit.png)](docs/img/screenshot_loadvisit.png)

### Inspect Sky-Subtracted 2D Images

1. **Rendering Mode Selection** (optional):
   - **Fast Preview Mode** (default, recommended): Uses Datashader for 8× faster rendering
   - **Pixel Inspection Mode**: Uncheck "Fast Preview Mode" for full resolution with exact pixel values
2. Press **"Plot 2D"** button to display sky-subtracted 2D images for the selected visit
   - Loading time: ~10-30 seconds depending on mode and number of spectrographs
   - Fast Preview Mode: ~2-4 seconds per image (recommended for initial inspection)
   - Pixel Inspection Mode: ~16-32 seconds per image (use for quality assessment)
3. Images are displayed in tabs (SM1, SM2, SM3, SM4), with arms arranged horizontally
4. **Interactive controls**:
   - Pan: Click and drag
   - Zoom: Mouse wheel or box select
   - Hover: View pixel coordinates and intensity values
   - Reset: Click reset tool to restore original view

**Tip**: Use Fast Preview Mode for initial quick inspection, then switch to Pixel Inspection Mode when you need to examine specific pixel values.

[![Screenshot 2D Images](docs/img/screenshot_2dimage.png)](docs/img/screenshot_2dimage.png)

### Inspect 1D Gallery of Spectra

1. Press **"Plot 1D Image"** button to display a gallery of all fiber spectra for the selected visit
   - Shows all fibers from `pfsMerged` file as a 2D image (each row = one fiber)
   - Loading time: ~5-10 seconds
2. **Interactive controls**:
   - Pan and zoom using mouse controls
   - Hover over a row to see fiber information in the tooltip
   - Use color scale to identify spectral features

[![Screenshot 1D Gallery](docs/img/screenshot_pfsmerged.png)](docs/img/screenshot_pfsmerged.png)

### Inspect 1D Spectra of Specific Fibers

1. **Select Fibers** using one of two methods:
   - **By OB Code**: Select from OB Code dropdown → Fiber IDs auto-populate
   - **By Fiber ID**: Select from Fiber ID dropdown → OB Codes auto-populate
   - **Bidirectional sync**: Selections in one box automatically update the other
2. Press **"Plot 1D"** button to display the 1D spectrum of selected fibers
   - Loading time: ~2-5 seconds
   - Multiple fibers plotted with different colors
3. **Interactive controls**:
   - Pan: Click and drag on plot area
   - Zoom: Mouse wheel or box select tool
   - Hover: View wavelength, flux, and fiber information
   - **Legend interaction**: Click legend entry to mute/unmute individual fibers
   - Reset: Click reset tool to restore original view

**Note**: By default, only the first fiber is visible. Click legend entries to show/hide other fibers.

[![Screenshot 1D Spectrum](docs/img/screenshot_1dspec.png)](docs/img/screenshot_1dspec.png)

## Additional Information

### Technical Documentation

For detailed technical documentation, development notes, and architecture details, see:

- **[CLAUDE.md](CLAUDE.md)**: Comprehensive development documentation
  - Project metrics and code organization
  - Complete feature descriptions
  - Performance optimization details
  - Development roadmap
- **[SESSION_STATE_MIGRATION.md](SESSION_STATE_MIGRATION.md)**: Session state implementation details

### Configuration Tips

- **Visit Auto-Refresh**: Adjust `PFS_VISIT_REFRESH_INTERVAL` in `.env` to change refresh frequency (seconds)
  - Set to `0` to disable auto-refresh
  - Default: 300 seconds (5 minutes)
- **Hostname Validation**: Launch script checks `PFS_APP_HOSTNAME` to prevent deployment errors
- **Development vs Production**:
  - Development: Auto-reload on code changes (port 5206)
  - Production: Multi-threaded for concurrent users (port 5106)

### Performance Notes

- **2D Image Rendering**: Fast Preview Mode provides 8× speedup (recommended for routine use)
- **Visit Discovery**: First discovery may take 10-20 seconds; subsequent refreshes use caching
- **Parallel Processing**: Application utilizes all available CPU cores for data loading
- **Multi-User**: Each browser session maintains independent state (no interference)

## Known Limitations & Future Features

### Current Limitations

- Single visit loading only (multi-visit stacking planned)
- DetectorMap overlay not yet implemented
- Export functionality (PNG/HTML) not yet available

### Planned Features

- Multi-visit stacking for improved S/N
- DetectorMap fiber trace overlay
- Image and plot export functionality
- Additional visualization options (colormap selection, custom scaling)

## Troubleshooting

### Common Issues

1. **"Hostname mismatch" error**: Update `PFS_APP_HOSTNAME` in `.env` to match your server's hostname (run `hostname -f` to check)
2. **Import errors**: Ensure LSST stack is loaded (`source /work/stack/loadLSST.bash`)
3. **No visits found**: Check `PFS_BASE_COLLECTION` and `PFS_OBSDATE_UTC` in `.env`
4. **Slow performance**: Use Fast Preview Mode for 2D images; check network connection
5. **Widget not updating**: Reload browser page to reset session state

For additional help, see the [CLAUDE.md](CLAUDE.md) Testing & Debugging section.

## Contact & Support

This is a QuickLook tool for PFS observatory operations. For issues or feature requests:

- **PFS Observation Helpdesk**: <pfs-obs-help@naoj.org>
- Check existing documentation in [CLAUDE.md](CLAUDE.md)
- Create an issue in the repository: <https://github.com/Subaru-SciOp/pfs_quicklook/issues>
