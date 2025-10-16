# PFS QuickLook Web Application

## Project Overview

This is a web application for visualizing 2D and 1D spectral data from the PFS (Prime Focus Spectrograph) pipeline. The application is built using Panel and provides an interactive interface for observatory personnel to quickly inspect spectral data during observations.

## Current Status

### Completed Features

#### Core Infrastructure
- **Web Framework**: Panel-based web application ([app.py](app.py))
- **Core Functions**: Modular spectral processing functions ([quicklook_core.py](quicklook_core.py))
- **Butler Integration**: LSST Data Butler integration for data retrieval
- **Visit Discovery**: Automatic visit discovery from Butler datastore based on base collection ([quicklook_core.py:103-152](quicklook_core.py#L103-L152))
- **Launch Script**: Bash script to set up environment and launch app ([launch_app.bash](launch_app.bash))
- **Session Management**: Per-session data caching using `pn.state.cache` for multi-user support

#### User Interface (app.py)

**Sidebar Structure**:
1. **Instrument Settings**
   - Arm selection: `brn`, `bmn` (radio button group)
   - Spectrograph selection: 1, 2, 3, 4 (checkbox group)

2. **Data Selection** ([app.py:335-340](app.py#L335-L340))
   - Visit selection: MultiChoice widget with search functionality (no limit on displayed options)
   - **Load Data** button: Loads visit data and populates OB Code options
   - Status display: Shows current state (Ready/Loading/Loaded with fiber & OB code counts)

3. **Fiber Selection** ([app.py:343-347](app.py#L343-L347))
   - **OB Code** MultiChoice: Populated after data load, max 20 options/10 search results
   - **Fiber ID** MultiChoice: All fiber IDs (1-2394), max 20 options/10 search results
   - **Bidirectional Linking**: OB Code ↔ Fiber ID automatic synchronization

4. **Plot Controls** ([app.py:353-355](app.py#L353-L355))
   - **Plot 2D** button: Creates 2D spectral image (enabled after data load)
   - **Plot 1D** button: Creates 1D spectra plot (enabled after data load, requires fiber selection)
   - **Reset** button: Clears all data and selections

5. **Options** (Currently commented out - [app.py:344-349](app.py#L344-L349))
   - Sky subtraction (checkbox, default: True)
   - DetectorMap overlay (checkbox, default: False)
   - Scale selection (zscale/minmax, default: zscale)
   - Widgets exist but are hidden from UI

**Main Panel Tabs**:
- **2D Tab**: Matplotlib pane showing 2D spectral images (700px height)
- **1D Tab**: Bokeh interactive plot showing 1D spectra (550px height)
- **Log Tab**: Markdown pane showing execution status and parameters

**UI Features**:
- Toast notifications for warnings, errors, and success messages
- Automatic tab switching: switches to 2D/1D tab after plot creation
- Fixed-height status display (60px) to prevent layout shifts
- Responsive design with min/max width constraints (280-400px sidebar)

#### Workflow & Data Flow

**Three-Step Process** ([app.py:114-221](app.py#L114-L221)):

1. **Load Data** (`load_data_callback`):
   - Validates visit selection
   - Calls `load_visit_data()` to retrieve pfsConfig
   - Creates bidirectional OB Code ↔ Fiber ID mappings
   - Populates OB Code options
   - Enables Plot 2D/1D buttons
   - Updates status: "Loaded visit XXXXX: N fibers, M OB codes"

2. **Select Fibers** (Optional):
   - Via OB Code: Select OB codes → corresponding Fiber IDs auto-selected
   - Via Fiber ID: Select Fiber IDs → corresponding OB codes auto-selected
   - Manual adjustment: Users can add/remove selections freely
   - Bidirectional sync maintains consistency

3. **Create Plots**:
   - **Plot 2D** (`plot_2d_callback`):
     - No fiber selection required (displays full detector image)
     - Retrieves: pfsConfig, calexp, detectorMap, pfsArm, sky1d, fiberProfiles
     - Applies sky subtraction (if enabled)
     - Displays in 2D tab (auto-switches)

   - **Plot 1D** (`plot_1d_callback`):
     - Requires fiber selection
     - Retrieves: pfsConfig, pfsMerged
     - Creates interactive Bokeh plot
     - Displays in 1D tab (auto-switches)

**Bidirectional Fiber Selection** ([quicklook_core.py:103-137](quicklook_core.py#L103-L137), [app.py:166-221](app.py#L166-L221)):
- `load_visit_data()` creates two mappings:
  - `obcode_to_fibers`: OB Code → List of Fiber IDs
  - `fiber_to_obcode`: Fiber ID → OB Code
- `on_obcode_change()`: Updates Fiber IDs when OB Code selection changes
- `on_fiber_change()`: Updates OB Codes when Fiber ID selection changes
- Circular reference prevention via `programmatic_update` flag

#### Data Visualization

**2D Image Display** ([quicklook_core.py:140-252](quicklook_core.py#L140-L252)):
- Sky-subtracted 2D spectral images (sky1d subtraction via `subtractSky1d`)
- Configurable scaling algorithms:
  - **zscale** (default): `LuptonAsinhStretch(Q=1) + ZScaleInterval()`
  - **minmax**: `AsinhStretch(a=1) + MinMaxInterval()`
- PFS cursor overlay for wavelength/fiber identification
- DetectorMap overlay support (partially implemented, warning shown)
- Matplotlib-based rendering with LSST afw.display integration
- Image reconstruction from 1D spectra using fiberProfiles and detectorMap

**1D Spectra Display** ([quicklook_core.py:274-431](quicklook_core.py#L274-L431)):
- Interactive Bokeh plots for 1D spectra
- Multiple fiber overlays with color coding (Category10 palette)
- Error bands (shaded regions showing variance)
- Interactive legend with mute/unmute functionality (click to toggle visibility)
- HoverTool showing: Fiber ID, Object ID, OB Code, Wavelength, Flux
- Tools: pan, wheel_zoom, box_zoom (default), undo, redo, reset, save
- Initial state: only first fiber visible, others muted
- Responsive design (1400px width, scales with window)

#### Data Processing
- Butler-based data retrieval from specified datastore and collections
- Collection pattern: `base_collection/visit` (e.g., `u/obsproc/s25a/20250520b/126714`)
- Sky subtraction using `subtractSky1d` from PFS DRP pipeline
- SpectrumSet creation from pfsArm data
- Fiber trace generation from fiberProfiles and detectorMap
- Image reconstruction from 1D spectra for sky subtraction

### Known Limitations & TODOs

1. **Multi-arm/Multi-spectrograph Support**:
   - Only processes first arm if multiple selected (shows warning)
   - Only processes first spectrograph if multiple selected (shows warning)
   - Future: support multiple arm/spectrograph combinations in parallel

2. **DetectorMap Overlay**:
   - Feature not yet fully implemented
   - Warning shown when user attempts to enable
   - Overlay code exists but commented out ([quicklook_core.py:201-217](quicklook_core.py#L201-L217))

3. **Export Functionality**:
   - Not yet implemented
   - Future: PNG export for 2D images, PNG/HTML export for 1D plots

4. **Options Panel**:
   - Options widgets exist but are commented out in layout
   - Widgets still functional via default values:
     - Sky subtraction: True
     - DetectorMap overlay: False
     - Scale: zscale
   - Can be uncommented to expose in UI

5. **Multi-visit Stacking**:
   - Original notebook supports stacking multiple visits
   - Not yet implemented in web app
   - Future feature for S/N improvement

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
├── CLAUDE.md                       # This file - development documentation
├── .env                            # Environment configuration (datastore, collection)
└── .gitignore                      # Git ignore rules
```

### Key Functions

#### quicklook_core.py

**`discover_visits(datastore, base_collection, obsdate_utc)`** ([quicklook_core.py:103-152](quicklook_core.py#L103-L152)):
- Discovers available visits from Butler datastore
- Uses Butler registry to query collections matching `base_collection/??????` pattern (6-digit visit numbers)
- Parameters: datastore, base_collection, obsdate_utc (optional, for future filtering)
- Returns: Sorted list of visit numbers (as integers)
- Called on app startup to populate visit selection widget

**`load_visit_data(datastore, base_collection, visit)`** ([quicklook_core.py:155-200](quicklook_core.py#L155-L200)):
- Loads pfsConfig for specified visit
- Creates bidirectional mappings:
  - `obcode_to_fibers`: dict mapping OB codes to lists of fiber IDs
  - `fiber_to_obcode`: dict mapping fiber IDs to OB codes
- Returns: `(pfsConfig, obcode_to_fibers, fiber_to_obcode)`

**`build_2d_figure(...)`** ([quicklook_core.py:203-350](quicklook_core.py#L203-L350)):
- Creates 2D spectral image with optional sky subtraction
- Parameters: datastore, base_collection, visit, spectrograph, arm, subtract_sky, overlay, fiber_ids, scale_algo
- Returns: Matplotlib Figure object

**`build_1d_bokeh_figure_single_visit(...)`** ([quicklook_core.py:274-431](quicklook_core.py#L274-L431)):
- Creates interactive Bokeh 1D spectra plot
- Parameters: datastore, base_collection, visit, fiber_ids, ylim
- Returns: Bokeh figure object

#### app.py Callbacks

**`load_data_callback()`** ([app.py:114-163](app.py#L114-L163)):
- Loads visit data and populates OB Code options
- Updates session cache with pfsConfig and mappings
- Enables plot buttons

**`on_obcode_change()`** ([app.py:166-191](app.py#L166-L191)):
- Updates Fiber ID selection when OB Code changes
- Uses `obcode_to_fibers` mapping

**`on_fiber_change()`** ([app.py:194-221](app.py#L194-L221)):
- Updates OB Code selection when Fiber ID changes
- Uses `fiber_to_obcode` mapping

**`plot_2d_callback()`** ([app.py:224-274](app.py#L224-L274)):
- Creates 2D plot (no fiber selection required)
- Switches to 2D tab automatically

**`plot_1d_callback()`** ([app.py:277-318](app.py#L277-L318)):
- Creates 1D plot (requires fiber selection)
- Switches to 1D tab automatically

**`reset_app()`** ([app.py:321-344](app.py#L321-L344)):
- Clears all plots, cache, and selections
- Disables plot buttons
- Resets status to "Ready"

### Session State Management

**Session Cache** (`pn.state.cache`):
```python
{
    'visit_data': {
        'loaded': bool,              # Data loaded flag
        'visit': int,                # Current visit number
        'pfsConfig': PfsConfig,      # PFS configuration object
        'obcode_to_fibers': dict,    # OB Code → [Fiber IDs]
        'fiber_to_obcode': dict,     # Fiber ID → OB Code
    },
    'programmatic_update': bool      # Circular reference prevention flag
}
```

**Circular Reference Prevention**:
- `programmatic_update` flag prevents infinite loops
- Set to `True` before programmatic widget updates
- Callbacks check flag and return early if `True`
- Ensures OB Code ↔ Fiber ID bidirectional sync doesn't cause loops

### Environment Configuration

**Environment Variables** ([quicklook_core.py:54-56](quicklook_core.py#L54-L56)):
- `PFS_DATASTORE`: Path to Butler datastore (default: `/work/datastore`)
- `PFS_BASE_COLLECTION`: Base collection name (default: `u/obsproc/s25a/20250520b`)
- `PFS_OBSDATE_UTC`: Optional observation date for visit filtering

**Configuration Reload** ([quicklook_core.py:60-69](quicklook_core.py#L60-L69)):
- `reload_config()` function reloads `.env` file
- Called on session start
- Allows runtime configuration changes

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

**LSST/PFS Stack** ([quicklook_core.py:29-48](quicklook_core.py#L29-L48)):
- lsst.afw.display, lsst.afw.image (image display and manipulation)
- lsst.daf.butler (Butler data access)
- pfs.datamodel (TargetType, PfsConfig, etc.)
- pfs.drp.stella (SpectrumSet, subtractSky1d, utilities)

## Development Roadmap

### High Priority

1. **Complete DetectorMap Overlay**
   - Uncomment and debug overlay code in `build_2d_figure()`
   - Test with selected fiber IDs
   - Add default behavior (highlight SCIENCE + observatoryfiller fibers)
   - Integrate with OB Code/Fiber ID selection

2. **Multi-arm/Multi-spectrograph Support**
   - Remove single-arm/spectrograph limitation
   - Options:
     - Multiple 2D/1D tabs for each arm/spectrograph combination
     - Tabbed/tiled layout for multiple panels
     - Sequential processing with combined display
   - Update core functions to handle multiple data IDs in parallel

3. **Export Functionality**
   - Implement PNG export for 2D images
   - Implement PNG/HTML export for 1D Bokeh plots
   - Consider PDF export for reports
   - Add export buttons to UI

### Medium Priority

4. **Enhanced Visit Discovery**
   - Add date-based filtering using `OBSDATE_UTC` parameter
   - Implement manual refresh button for visit list
   - Add visit metadata display (date, time, program info)

5. **Multi-visit Stacking**
   - Port stacking functionality from notebook ([check_quick_reduction_data.py:288-470](check_quick_reduction_data.py#L288-L470))
   - Add UI for multi-visit selection and stacking options
   - Display stacked 2D image and median/mean 1D spectra
   - Show individual visit spectra overlaid with stack

6. **Options Panel Restoration**
   - Uncomment options section in sidebar
   - Make sky subtraction and overlay options visible
   - Consider adding more display options:
     - Colormap selection
     - Stretch parameters (Q value, etc.)
     - Y-axis limits for 1D plots

7. **Enhanced Error Handling**
   - Add more specific error messages for common failures
   - Implement retry logic for Butler timeouts
   - Add data validation before processing
   - Better handling of missing data products

8. **Performance Optimization**
   - Cache Butler instances and data products
   - Implement lazy loading for large datasets
   - Add progress indicators for long operations
   - Consider async processing for 2D and 1D independently
   - Optimize image rendering for large detectors

### Low Priority

9. **Advanced Features**
   - Line identification overlay (see notebook imports: ReadLineListTask)
   - Spectral line measurements (EW, flux, redshift)
   - Comparison with reference spectra
   - Batch processing mode
   - Automated QA checks

10. **UI/UX Improvements**
    - Add keyboard shortcuts
    - Implement session saving/loading
    - Add more responsive design breakpoints
    - Custom color schemes/themes
    - Fiber map visualization (focal plane view)
    - Drag-and-drop visit file upload

11. **Documentation**
    - User manual with screenshots
    - API documentation for core functions
    - Deployment guide for different environments
    - Troubleshooting guide with common issues
    - Video tutorials

## Technical Notes

### Butler Collections Pattern
Collections are constructed per-visit: `base_collection/visit` (e.g., `u/obsproc/s25a/20250520b/126714`)

### Data ID Format
```python
dataId = {
    "visit": int,           # Visit number
    "spectrograph": int,    # 1, 2, 3, or 4
    "arm": str,             # "b", "r", "n", or "m"
}
```

### Fiber ID Range
Valid fiber IDs: 1-2394

### OB Code (Observation Code)
- String identifier for observation type/target
- Examples: `"obj_sky"`, `"obj_science"`, `"observatoryfiller_xxx"`
- Maps to specific sets of fiber IDs
- Used for target classification and fiber selection

### Target Types (from original notebook)
- `TargetType.SCIENCE`: Science targets
- Observatory fillers identified by `"observatoryfiller_"` in obCode
- Sky fibers identified by specific obCode patterns

### Image Scaling Algorithms
- **zscale** (default): `LuptonAsinhStretch(Q=1) + ZScaleInterval()`
  - Automatic scaling based on image statistics
  - Good for typical spectral images
- **minmax**: `AsinhStretch(a=1) + MinMaxInterval()`
  - Uses full dynamic range of image
  - Useful for faint features

### Bokeh Figure Configuration
- Width: 1400px (optimized for 1920px screen minus 320px sidebar)
- Height: 500px
- Default tool: box_zoom
- Responsive: `sizing_mode="scale_width"`
- Color palette: Category10_10 (cycles through 10 colors)

### MultiChoice Widget Options
- **Visit**: No limits (all options shown), dynamically populated on startup
- **OB Code**: `option_limit=20`, `search_option_limit=10`
- **Fiber ID**: `option_limit=20`, `search_option_limit=10`

### Application Startup Process
On application startup ([app.py:409-420](app.py#L409-L420)):
1. Loads environment configuration from `.env` file
2. Calls `discover_visits()` to query Butler for available visits
3. Populates visit MultiChoice widget with discovered visits
4. If visits are found, widget is ready for selection (no default selection)
5. If no visits are found, warning is logged and widget remains empty

## Testing & Debugging

### Test Data
Visit discovery is now automatic based on Butler collections.
The `.env` file controls which base collection is searched:
- `PFS_DATASTORE`: Path to Butler datastore
- `PFS_BASE_COLLECTION`: Base collection (e.g., `u/obsproc/s25a/20250520b`)
- `PFS_OBSDATE_UTC`: Observation date (currently for logging only, not yet used for filtering)

### Logging
Application uses loguru for logging. Check console output for detailed information:
- Info: Normal operation (data loading, selection changes)
- Warning: Non-critical issues (single arm/spectrograph limitation)
- Error: Failures (Butler errors, plotting failures)

### Common Issues

1. **Import Errors**: Ensure LSST stack is properly loaded before running
   - Run `source /work/stack/loadLSST.bash`
   - Run `setup -v pfs_pipe2d` and `setup -v display_matplotlib`

2. **Butler Errors**: Check datastore path and collection names
   - Verify `PFS_DATASTORE` points to valid Butler repository
   - Ensure `PFS_BASE_COLLECTION` exists and contains visit subcollections

3. **Missing Data Products**: Verify all required data products exist
   - 2D: calexp, pfsArm, sky1d, fiberProfiles, detectorMap, pfsConfig
   - 1D: pfsMerged, pfsConfig

4. **Memory Issues**: Large datasets may require more memory
   - Consider processing fewer fibers at once
   - Use Reset button to clear cached data

5. **Session State Issues**: If widgets behave unexpectedly
   - Reload the browser page to reset session
   - Check for circular reference in OB Code ↔ Fiber ID sync

## Original Source Reference

The web app is based on [check_quick_reduction_data.ipynb](check_quick_reduction_data.ipynb) which contains:
- Single-visit 2D/1D visualization (cells around lines 84-235)
- Multi-visit stacking (cells around lines 288-470)
- Interactive matplotlib plots with cursor support
- Comprehensive metadata display

Key differences from notebook:
- Panel web UI instead of Jupyter widgets
- Bokeh for 1D plots (instead of matplotlib) for better interactivity
- Separated workflow: Load Data → Select Fibers → Create Plots
- OB Code filtering and bidirectional OB Code ↔ Fiber ID linking
- Session-based state management for multi-user support
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

## Recent Changes

### 2025-10: Automatic Visit Discovery

1. **Visit Discovery Implementation** ([quicklook_core.py:103-152](quicklook_core.py#L103-L152)):
   - Added `discover_visits()` function to query Butler registry
   - Uses pattern matching (`base_collection/??????`) to find 6-digit visit numbers
   - Automatically populates visit widget on app startup
   - Replaces hardcoded test visits with dynamic discovery

2. **Configuration-based Visit Loading** ([app.py:409-420](app.py#L409-L420)):
   - Reads `PFS_BASE_COLLECTION` from `.env` file
   - Discovers all available visits in the specified collection
   - Logs discovery process for debugging
   - Graceful fallback to empty list if no visits found

3. **Future Enhancements**:
   - `OBSDATE_UTC` parameter preserved for future date-based filtering
   - Manual refresh button for visit list (planned)
   - Visit metadata display (planned)

### 2025-01: Major UI/UX Improvements

1. **Separated Workflow** (Load → Select → Plot):
   - Split single "Run" button into three independent buttons
   - "Load Data": Loads visit data and populates OB Code options
   - "Plot 2D": Creates 2D image (no fiber selection required)
   - "Plot 1D": Creates 1D spectra (requires fiber selection)
   - Benefits: Faster iteration, clearer workflow, better error messages

2. **OB Code Filtering**:
   - Added OB Code MultiChoice widget
   - Populated automatically after data load
   - Enables selection by observation type/target

3. **Bidirectional OB Code ↔ Fiber ID Linking**:
   - Select OB Code → Fiber IDs auto-selected
   - Select Fiber IDs → OB Codes auto-selected
   - Maintains consistency between selections
   - Circular reference prevention implemented

4. **Visit Widget Change**:
   - Changed from MultiSelect to MultiChoice
   - Consistent UI with other selectors
   - Search functionality available
   - No display limits (shows all visits)

5. **Auto Tab Switching**:
   - Plot 2D → Switches to 2D tab automatically
   - Plot 1D → Switches to 1D tab automatically
   - Immediate visual feedback

6. **Fixed Status Display**:
   - Height fixed at 60px to prevent layout shifts
   - Consistent spacing regardless of message length

7. **Options Panel**:
   - Temporarily commented out to simplify initial UI
   - Can be restored by uncommenting [app.py:344-349](app.py#L344-L349)
   - Default values still applied (sky subtraction on, zscale)

### Code Improvements

1. **Session State Management**:
   - Proper use of `pn.state.cache` for multi-user support
   - Circular reference prevention via `programmatic_update` flag
   - Clean reset functionality

2. **Enhanced Data Loading**:
   - `load_visit_data()` creates bidirectional mappings
   - Better error handling and logging
   - Status updates throughout process

3. **Improved Button States**:
   - Plot buttons disabled until data loaded
   - Clear visual indication of available actions
   - Proper state management on reset

## Contact & Support

This is a QuickLook tool for PFS observatory operations. For issues or feature requests, contact the development team or create an issue in the repository.
