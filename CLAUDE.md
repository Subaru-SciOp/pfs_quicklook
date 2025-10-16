# PFS QuickLook Web Application

## Project Overview

This is a web application for visualizing 2D and 1D spectral data from the PFS (Prime Focus Spectrograph) pipeline. The application is built using Panel and provides an interactive interface for observatory personnel to quickly inspect spectral data during observations.

## Current Status

### Completed Features

#### Core Infrastructure
- **Web Framework**: Panel-based web application ([app.py](app.py))
- **Core Functions**: Modular spectral processing functions ([quicklook_core.py](quicklook_core.py))
- **Butler Integration**: LSST Data Butler integration for data retrieval
- **Launch Script**: Bash script to set up environment and launch app ([launch_app.bash](launch_app.bash))

#### User Interface (app.py)
- **Sidebar Controls**:
  - Arm selection: `brn`, `bmn` (radio button group)
  - Spectrograph selection: 1, 2, 3, 4 (checkbox group)
  - Visit multi-select widget (currently populated with test visits)
  - Fiber ID multi-choice widget (1-2394)
  - Options: Sky subtraction (checkbox), DetectorMap overlay (checkbox), Scale selection (zscale/minmax)
  - Run/Reset buttons

- **Main Panel Tabs**:
  - **2D Tab**: Matplotlib pane showing 2D spectral images (700px height)
  - **1D Tab**: Bokeh interactive plot showing 1D spectra (550px height)
  - **Log Tab**: Markdown pane showing execution status and parameters

- **Notifications**: Toast notifications for warnings and errors

#### Data Visualization

**2D Image Display** ([quicklook_core.py:74-193](quicklook_core.py#L74-L193)):
- Sky-subtracted 2D spectral images
- Configurable scaling algorithms (zscale with Lupton Asinh stretch, or minmax with Asinh stretch)
- PFS cursor overlay for wavelength/fiber identification
- DetectorMap overlay support (partially implemented, line 95-96 shows warning)
- Matplotlib-based rendering with LSST afw.display integration

**1D Spectra Display** ([quicklook_core.py:244-401](quicklook_core.py#L244-L401)):
- Interactive Bokeh plots for 1D spectra
- Multiple fiber overlays with color coding
- Error bands (shaded regions showing variance)
- Interactive legend with mute/unmute functionality (click to toggle visibility)
- HoverTool showing: Fiber ID, Object ID, OB Code, Wavelength, Flux
- Pan, zoom, and box zoom tools
- Initial state: only first fiber visible, others muted
- Responsive design (1400px width, scales with window)

#### Data Processing
- Butler-based data retrieval from specified datastore and collections
- Sky subtraction using `subtractSky1d` from PFS DRP pipeline
- SpectrumSet creation from pfsArm data
- Fiber trace generation from fiberProfiles and detectorMap
- Image reconstruction from 1D spectra

### Known Limitations & TODOs

1. **Multi-arm/Multi-spectrograph Support** (app.py:69-76):
   - Only processes first arm if multiple selected
   - Only processes first spectrograph if multiple selected
   - Warnings displayed to user

2. **DetectorMap Overlay** (app.py:95-96):
   - Feature not yet fully implemented
   - Warning shown when user attempts to enable

3. **Visit Discovery**:
   - Currently using hardcoded test visits (126714-126717) for initial options
   - No automatic visit discovery from datastore
   - No date-based filtering

4. **Export Functionality**:
   - Export button referenced but not implemented (app.py:173 commented out)

5. **Options Panel** (app.py:163-168):
   - Options widgets exist but section is commented out in layout
   - Widgets still functional but not visible in UI

6. **Multi-visit Stacking**:
   - Original notebook supports stacking multiple visits ([check_quick_reduction_data.py:288-470](check_quick_reduction_data.py#L288-L470))
   - Not yet implemented in web app

## Architecture

### File Structure

```
pfs_quicklook/
├── app.py                          # Main Panel web application
├── quicklook_core.py               # Core spectral processing functions
├── check_quick_reduction_data.py   # Original Jupyter notebook converted to .py
├── check_quick_reduction_data.ipynb # Original Jupyter notebook
├── launch_app.bash                 # Environment setup and launch script
├── requirements.txt                # Python dependencies (Panel, etc.)
├── pyproject.toml                  # Project metadata
├── README.md                       # Project documentation
└── .gitignore                      # Git ignore rules
```

### Data Flow

1. User selects parameters in sidebar (visit, arm, spectrograph, fibers)
2. User clicks "Run" button → triggers `run_app()` callback
3. `run_app()` validates inputs and extracts parameters
4. **2D Processing**:
   - Calls `build_2d_figure()` with parameters
   - Butler retrieves: pfsConfig, calexp, detectorMap, pfsArm, sky1d, fiberProfiles
   - Optional sky subtraction performed
   - Image displayed in 2D tab
5. **1D Processing**:
   - Calls `build_1d_bokeh_figure_single_visit()` with parameters
   - Butler retrieves: pfsConfig, pfsMerged
   - Bokeh figure created with selected fibers
   - Interactive plot displayed in 1D tab
6. Log tab updated with execution summary

### Environment Configuration

**Environment Variables** ([quicklook_core.py:49-51](quicklook_core.py#L49-L51)):
- `PFS_DATASTORE`: Path to Butler datastore (default: `/work/datastore`)
- `PFS_BASE_COLLECTION`: Base collection name (default: `u/obsproc/s25a/20250520b`)

**Launch Requirements** ([launch_app.bash](launch_app.bash)):
1. LSST stack environment (`loadLSST.bash`)
2. PFS pipeline setup (`pfs_pipe2d`, `display_matplotlib`)
3. Additional Python packages in custom location (`$LSST_PYTHON_USERLIB`)
4. Server configuration: port 5006, accessible from `pfsa-usr01.subaru.nao.ac.jp`

### Dependencies

**Python Packages** ([requirements.txt](requirements.txt)):
- panel (web framework)
- watchfiles (auto-reload support)
- loguru (logging)
- ipywidgets_bokeh (widget support)
- ipympl (matplotlib interactivity)

**LSST/PFS Stack** ([quicklook_core.py:27-46](quicklook_core.py#L27-L46)):
- lsst.afw.display, lsst.afw.image
- lsst.daf.butler (Butler)
- pfs.datamodel (TargetType, etc.)
- pfs.drp.stella (SpectrumSet, subtractSky1d, utilities)

## Development Roadmap

### High Priority

1. **Automatic Visit Discovery**
   - Implement Butler query to discover available visits
   - Add date filtering (use current UTC date by default)
   - Auto-refresh visit list on app load or manual trigger
   - See original notebook line 76 for UTC date usage

2. **Complete DetectorMap Overlay**
   - Uncomment and debug overlay code in `build_2d_figure()` ([quicklook_core.py:171-187](quicklook_core.py#L171-L187))
   - Test with selected fiber IDs
   - Add default behavior (highlight SCIENCE + observatoryfiller fibers)

3. **Multi-arm/Multi-spectrograph Support**
   - Modify UI to show multiple 2D/1D tabs for each arm/spectrograph combination
   - Or create tabbed/tiled layout for multiple panels
   - Update core functions to handle multiple data IDs in parallel

4. **Export Functionality**
   - Implement PNG export for 2D images
   - Implement PNG/HTML export for 1D Bokeh plots
   - Consider PDF export for reports

### Medium Priority

5. **Multi-visit Stacking**
   - Port stacking functionality from notebook ([check_quick_reduction_data.py:288-470](check_quick_reduction_data.py#L288-L470))
   - Add UI for multi-visit selection and stacking options
   - Display stacked 2D image and median/mean 1D spectra
   - Show individual visit spectra overlaid with stack

6. **Restore Options Panel**
   - Uncomment options section in sidebar ([app.py:163-168](app.py#L163-L168))
   - Make sky subtraction and overlay options visible
   - Consider adding more display options (colormap, stretch parameters)

7. **Enhanced Error Handling**
   - Add more specific error messages for common failures
   - Implement retry logic for Butler timeouts
   - Add data validation before processing

8. **Performance Optimization**
   - Cache Butler instances and data products
   - Implement lazy loading for large datasets
   - Add progress indicators for long operations
   - Consider async processing for 2D and 1D independently

### Low Priority

9. **Advanced Features**
   - Line identification overlay (see notebook imports: ReadLineListTask)
   - Spectral line measurements (EW, flux, redshift)
   - Comparison with reference spectra
   - Batch processing mode

10. **UI/UX Improvements**
    - Add keyboard shortcuts
    - Implement session saving/loading
    - Add more responsive design breakpoints
    - Custom color schemes/themes
    - Fiber map visualization

11. **Documentation**
    - User manual
    - API documentation
    - Deployment guide
    - Troubleshooting guide

## Technical Notes

### Butler Collections Pattern
Collections are constructed per-visit: `base_collection/visit` (e.g., `u/obsproc/s25a/20250520b/126714`)

### Data ID Format
```python
dataId = {
    "visit": int,
    "spectrograph": int,  # 1, 2, 3, or 4
    "arm": str,           # "b", "r", "n", or "m"
}
```

### Fiber ID Range
Valid fiber IDs: 1-2394

### Target Types (from original notebook)
- `TargetType.SCIENCE`: Science targets
- Observatory fillers identified by `"observatoryfiller_"` in obCode

### Image Scaling Algorithms
- **zscale**: `LuptonAsinhStretch(Q=1) + ZScaleInterval()` (default)
- **minmax**: `AsinhStretch(a=1) + MinMaxInterval()`

### Bokeh Figure Configuration
- Width: 1400px (optimized for 1920px screen minus 320px sidebar)
- Height: 500px
- Default tool: box_zoom
- Responsive: `sizing_mode="scale_width"`

## Testing & Debugging

### Test Data
Current test visits in use: 126714, 126715, 126716, 126717
Test fiber IDs: 141, 412, 418, 437

### Logging
Application uses loguru for logging. Check console output for detailed information.

### Common Issues

1. **Import Errors**: Ensure LSST stack is properly loaded before running
2. **Butler Errors**: Check datastore path and collection names
3. **Missing Data Products**: Verify all required data products exist (calexp, pfsArm, pfsMerged, etc.)
4. **Memory Issues**: Large datasets may require more memory; consider processing fewer fibers at once

## Original Source Reference

The web app is based on [check_quick_reduction_data.ipynb](check_quick_reduction_data.ipynb) which contains:
- Single-visit 2D/1D visualization (cells around lines 84-235)
- Multi-visit stacking (cells around lines 288-470)
- Interactive matplotlib plots with cursor support
- Comprehensive metadata display

Key differences from notebook:
- Panel web UI instead of Jupyter widgets
- Bokeh for 1D plots (instead of matplotlib) for better interactivity
- Simplified initial UI (stacking not yet implemented)
- Responsive design for web deployment

## Development Commands

### Launch Development Server
```bash
bash launch_app.bash
# Runs with auto-reload (--dev flag)
# Accessible at: http://pfsa-usr01.subaru.nao.ac.jp:5006
```

### Manual Launch (if bash script fails)
```bash
source /work/stack/loadLSST.bash
setup -v pfs_pipe2d
setup -v display_matplotlib
export LSST_PYTHON_USERLIB="/work/monodera/pyvenvs/lsst-stack-local-pythonlibs"
export PYTHONPATH="$LSST_PYTHON_USERLIB:$PYTHONPATH"
python -m panel serve app.py --address 0.0.0.0 --allow-websocket-origin=pfsa-usr01.subaru.nao.ac.jp:5006 --dev
```

### Install Additional Dependencies
```bash
python3 -m pip install --target "$LSST_PYTHON_USERLIB" panel watchfiles loguru ipywidgets_bokeh ipympl
```

## Contact & Support

This is a QuickLook tool for PFS observatory operations. For issues or feature requests, contact the development team or create an issue in the repository.
