# PFS QuickLook Web Application

## Project Overview

This is a web application for visualizing 2D and 1D spectral data from the PFS (Prime Focus Spectrograph) pipeline. The application is built using Panel and provides an interactive interface for observatory personnel to quickly inspect spectral data during observations.

## Current Status

### Completed Features

#### Core Infrastructure
- **Web Framework**: Panel-based web application ([app.py](app.py))
- **Core Functions**: Modular spectral processing functions ([quicklook_core.py](quicklook_core.py))
- **Butler Integration**: LSST Data Butler integration for data retrieval
- **Asynchronous Visit Discovery**: Non-blocking visit discovery with automatic refresh ([app.py:511-625](app.py#L511-L625))
  - Initial visit discovery on session start (background thread)
  - Optional auto-refresh every N seconds (configurable via `.env`)
  - Date-based filtering with parallel processing ([quicklook_core.py:144-182](quicklook_core.py#L144-L182))
- **Launch Script**: Bash script to set up environment and launch app ([launch_app.bash](launch_app.bash))
- **Session Management**: Per-session data caching using `pn.state.cache` for multi-user support

#### User Interface (app.py)

**Sidebar Structure**:
1. **Instrument Settings**
   - Spectrograph selection: 1, 2, 3, 4 (checkbox group)
   - Note: Arm selection removed - application automatically attempts to load all 4 arms (b, r, n, m)

2. **Data Selection**
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
- **2D Tab**: Tabbed layout showing multiple spectrographs with horizontal arm arrangements
  - SM1-4 tabs (one per selected spectrograph)
  - Within each tab: arms arranged horizontally (Blue, Red, NIR, Medium-Red)
  - Panel Row layout with HoloViews panes (interactive Bokeh backend)
- **1D Tab**: Bokeh interactive plot showing 1D spectra (550px height)
- **Log Tab**: Markdown pane showing execution status and parameters

**UI Features**:
- Toast notifications for warnings, errors, and success messages
  - "Updating visit list..." (3 seconds) during auto-refresh
  - "Found N visits" or "Found N new visit(s)" on completion
- Automatic tab switching: switches to 2D/1D tab after plot creation
- Fixed-height status display (60px) to prevent layout shifts
- Responsive design with min/max width constraints (280-400px sidebar)
- Non-blocking UI: visit discovery runs in background, UI remains responsive

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

**2D Image Display**:
- **Interactive Visualization with HoloViews + Datashader**:
  - **Interactive Features**: Zoom, pan, hover, box select, wheel zoom, reset, save
  - **Server-Side Rendering**: Datashader dynamically renders visible viewport for optimal performance
  - **Dynamic Resolution**: Automatically adjusts detail level based on zoom level
  - **Tools**: Hover displays pixel coordinates and intensity values
  - **Performance**: 5-10× faster initial load compared to static images
- **Multiple Arm/Spectrograph Support** ([quicklook_core.py:205-369](quicklook_core.py#L205-L369)):
  - Automatically attempts to load all 4 arms (b, r, n, m) for each spectrograph
  - Parallel processing via joblib for high performance
  - Two-level parallelization:
    - Level 1: Spectrographs processed in parallel
    - Level 2: Arms within each spectrograph processed in parallel
  - Maximum of 16 images (4 spectrographs × 4 arms) can be processed simultaneously
  - Utilizes all available CPU cores (128 cores on target system)
- **Display Layout** ([app.py:310-415](app.py#L310-L415)):
  - Tabbed interface: SM1, SM2, SM3, SM4 (one tab per selected spectrograph)
  - Within each tab: Panel Row layout with arms arranged horizontally
  - Arm display order automatically determined:
    - "brn" order (Blue, Red, NIR) if Red arm data exists
    - "bmn" order (Blue, Medium-Red, NIR) if Medium-Red arm data exists
  - Only existing arms are displayed (no placeholders for missing data)
  - Missing arms indicated by informational note below plots
  - Each pane is a HoloViews Image with Bokeh backend
- **Data Processing**:
  - Sky-subtracted 2D spectral images (sky1d subtraction via `subtractSky1d`)
  - Configurable scaling algorithms:
    - **zscale** (default): `LuptonAsinhStretch(Q=1) + ZScaleInterval()`
    - **minmax**: `AsinhStretch(a=1) + MinMaxInterval()`
  - HoloViews Image with datashader rasterization
  - Image reconstruction from 1D spectra using fiberProfiles and detectorMap
- **Error Handling** ([app.py:319-415](app.py#L319-L415)):
  - Missing data: Only displays available arms, with informational note for missing arms
  - Processing errors: Shows error details in informational note below plots
  - Graceful degradation: Continues processing available data when some combinations fail
  - No placeholder images for missing data (cleaner UI)

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

1. **DetectorMap Overlay**:
   - Feature not yet fully implemented
   - Warning shown when user attempts to enable
   - Overlay code exists but commented out ([quicklook_core.py:201-217](quicklook_core.py#L201-L217))

2. **Export Functionality**:
   - Not yet implemented
   - Future: PNG export for 2D images, PNG/HTML export for 1D plots

3. **Options Panel**:
   - Options widgets exist but are commented out in layout
   - Widgets still functional via default values:
     - Sky subtraction: True
     - DetectorMap overlay: False
     - Scale: zscale
   - Can be uncommented to expose in UI

4. **Multi-visit Stacking**:
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

**`discover_visits(datastore, base_collection, obsdate_utc)`** ([quicklook_core.py:103-187](quicklook_core.py#L103-L187)):
- Discovers available visits from Butler datastore
- Uses Butler registry to query collections matching `base_collection/??????` pattern (6-digit visit numbers)
- **Date filtering**: If `obsdate_utc` is specified, filters visits by observation date using parallel processing (max 16 cores)
- Parameters: datastore, base_collection, obsdate_utc (optional)
- Returns: Sorted list of visit numbers (as integers)
- Called asynchronously on app startup and periodically for auto-refresh

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

**`reset_app()`** ([app.py:483-507](app.py#L483-L507)):
- Clears all plots, cache, and selections
- Disables plot buttons
- Resets status to "Ready"

#### Asynchronous Visit Discovery

**`get_visit_discovery_state()`** ([app.py:512-520](app.py#L512-L520)):
- Returns session-specific visit discovery state from `pn.state.cache`
- State structure: `{"status": None, "result": None, "error": None}`
- Each user session has independent state

**`discover_visits_worker(state_dict)`** ([app.py:523-555](app.py#L523-L555)):
- Background thread worker function
- Calls `discover_visits()` and stores results in `state_dict`
- Status values: "running", "success", "no_data", "error"

**`check_visit_discovery()`** ([app.py:557-611](app.py#L557-L611)):
- Periodic callback (every 500ms) to check if background discovery is complete
- Updates visit widget with results
- Preserves user's current selection if still valid
- Shows notifications based on results
- Returns `False` to stop checking when complete

**`trigger_visit_refresh()`** ([app.py:614-625](app.py#L614-L625)):
- Triggered periodically if auto-refresh is enabled
- Shows "Updating visit list..." notification (3 seconds)
- Starts background thread and periodic callback
- Only runs if no discovery is already in progress

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
    'programmatic_update': bool,     # Circular reference prevention flag
    'visit_discovery': {
        'status': str,               # "running", "success", "error", "no_data", or None
        'result': list,              # List of discovered visit numbers
        'error': str,                # Error message if status is "error"
    }
}
```

**Circular Reference Prevention**:
- `programmatic_update` flag prevents infinite loops
- Set to `True` before programmatic widget updates
- Callbacks check flag and return early if `True`
- Ensures OB Code ↔ Fiber ID bidirectional sync doesn't cause loops

### Environment Configuration

**Environment Variables** ([quicklook_core.py:53-56](quicklook_core.py#L53-L56)):
- `PFS_DATASTORE`: Path to Butler datastore (default: `/work/datastore`)
- `PFS_BASE_COLLECTION`: Base collection name (default: `u/obsproc/s25a/20250520b`)
- `PFS_OBSDATE_UTC`: Observation date for visit filtering (format: "YYYY-MM-DD", optional)
- `PFS_VISIT_REFRESH_INTERVAL`: Auto-refresh interval in seconds (default: 300, set to 0 to disable)

**Configuration Reload** ([quicklook_core.py:60-71](quicklook_core.py#L60-L71)):
- `reload_config()` function reloads `.env` file
- Called on each session start
- Returns: `(datastore, base_collection, obsdate_utc, refresh_interval)`
- Allows runtime configuration changes without restarting the app

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
- joblib (parallel processing)

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

2. **Export Functionality**
   - Implement PNG export for 2D images
   - Implement PNG/HTML export for 1D Bokeh plots
   - Consider PDF export for reports
   - Add export buttons to UI

### Medium Priority

1. **Enhanced Visit Discovery**
   - Add date-based filtering using `OBSDATE_UTC` parameter
   - Implement manual refresh button for visit list
   - Add visit metadata display (date, time, program info)

2. **Multi-visit Stacking**
   - Port stacking functionality from notebook ([check_quick_reduction_data.py:288-470](check_quick_reduction_data.py#L288-L470))
   - Add UI for multi-visit selection and stacking options
   - Display stacked 2D image and median/mean 1D spectra
   - Show individual visit spectra overlaid with stack

3. **Options Panel Restoration**
   - Uncomment options section in sidebar
   - Make sky subtraction and overlay options visible
   - Consider adding more display options:
     - Colormap selection
     - Stretch parameters (Q value, etc.)
     - Y-axis limits for 1D plots

4. **Performance Optimization**
   - Cache Butler instances and data products
   - Implement lazy loading for large datasets
   - Add progress indicators for long operations
   - Optimize image rendering for large detectors
   - Fine-tune parallel processing parameters for optimal performance

### Low Priority

1. **Advanced Features**
   - Line identification overlay (see notebook imports: ReadLineListTask)
   - Spectral line measurements (EW, flux, redshift)
   - Comparison with reference spectra
   - Batch processing mode
   - Automated QA checks

2. **UI/UX Improvements**
   - Add keyboard shortcuts
   - Implement session saving/loading
   - Add more responsive design breakpoints
   - Custom color schemes/themes
   - Fiber map visualization (focal plane view)
   - Drag-and-drop visit file upload

3. **Documentation**
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

### 2025-10-16: Automatic All-Arm Loading with Smart Display Order

1. **Arm Selection Widget Removed** ([app.py:65-67](app.py#L65-L67)):
   - Removed `arm_rbg` (RadioButtonGroup) widget from UI
   - Removed "Arm" section from sidebar
   - Application now automatically attempts to load all 4 arms (b, r, n, m)
   - Simplifies UI by removing unnecessary user choice

2. **Smart Arm Display Order** ([app.py:359-385](app.py#L359-L385)):
   - Automatically determines display order based on available data:
     - If Red (r) exists: displays in "brn" order (Blue, Red, NIR)
     - If Medium-Red (m) exists: displays in "bmn" order (Blue, Medium-Red, NIR)
     - Handles edge cases (both r and m, or only b and n)
   - Only displays arms that have data (no empty placeholders)
   - Cleaner visual presentation

3. **Improved Error Handling** ([app.py:390-413](app.py#L390-L413)):
   - Missing arms: Shows concise informational note below plots
     - Example: "_Note: Red, Medium-Red arm(s) not available for this visit_"
   - Processing errors: Displays error details in notes section
   - No placeholder images for missing data (cleaner UI)
   - Maintains full plot area for existing data

4. **Enhanced Parallel Processing**:
   - Now attempts to load all 4 arms simultaneously
   - Maximum of 16 images (4 spectrographs × 4 arms) processed in parallel
   - Better utilization of available CPU cores
   - Faster detection of missing data

5. **Log Output Updates**:
   - Removed arm selection from log messages
   - Updated status messages to reflect automatic arm loading
   - Clearer indication of which arms were successfully loaded

**Benefits**:
- Simpler UI (one less widget to configure)
- Automatic detection of available arms
- Proper display order for brn/bmn configurations
- Cleaner visual presentation without empty placeholders
- Faster workflow (no need to select arms manually)

### 2025-10-16: HoloViews Migration Complete with Aspect Ratio Fix and Visit Date Filtering

1. **Complete Matplotlib Removal**:
   - Replaced all matplotlib-based 2D rendering with HoloViews (direct Image, no datashader)
   - Removed `build_2d_figure()` function (matplotlib-based)
   - Removed `build_1d_figure_single_visit()` function (matplotlib-based)
   - Removed matplotlib imports (`matplotlib.pyplot`, `matplotlib.figure.Figure`)
   - Removed `afwDisplay` import (only used for matplotlib rendering)
   - Removed `addPfsCursor` and `showDetectorMap` imports (matplotlib utilities)
   - Removed unused imports: `afwImage`, `TargetType`, `copy` module
   - Removed `holoviews.operation.datashader.rasterize` import (not needed)

2. **New HoloViews Implementation** ([quicklook_core.py:220-500](quicklook_core.py#L220-L500)):
   - `_build_single_2d_array()`: Pickle-able worker function that builds transformed numpy arrays
   - `build_2d_arrays_multi_arm()`: Parallel array generation for multiple arms
   - `create_holoviews_from_arrays()`: Creates HoloViews Image objects in main thread (not pickle-able)
   - `build_2d_figure_multi_arm()`: Convenience wrapper combining array building and HoloViews creation
   - **Direct HoloViews Image** (no datashader rasterization) to preserve hover functionality
   - Interactive tools: hover, box_zoom, wheel_zoom, pan, undo, redo, reset, save
   - **Aspect Ratio Fix**: Calculates `frame_width` and `frame_height` from actual data dimensions
     - For landscape/square images: fixes width at 512px, adjusts height proportionally
     - For portrait images: fixes height at 512px, adjusts width proportionally
     - Ensures 4k×4k images display as perfect squares with 1:1 pixel aspect ratio

3. **Hover Tooltip Improvements** ([quicklook_core.py:425-436](quicklook_core.py#L425-L436)):
   - Custom `HoverTool` with formatted coordinate display
   - Coordinates: `$x{0.0}` and `$y{0.0}` format (shows cursor position like "1000.0")
   - Intensity: `@image{0.2f}` format (shows pixel value from Image glyph)
   - No duplicate tooltips (using `default_tools=[]`)

4. **Visit Date Filtering** ([quicklook_core.py:144-182](quicklook_core.py#L144-L182)):
   - `discover_visits()` now filters visits by observation date (`obsdate_utc`)
   - Uses parallel processing (max 16 cores) to check `pfsConfig.obstime` for each visit
   - If `obsdate_utc` is empty or `None`, returns all visits without filtering
   - Logs filtering progress: "Found X visits out of Y visits under collection (filtered by date)"
   - Efficient for large numbers of visits in the Butler registry

5. **App Integration** ([app.py:302-313](app.py#L302-L313)):
   - Changed from `pn.pane.Matplotlib()` to `pn.pane.HoloViews(backend='bokeh')`
   - 1D plot pane changed from `pn.pane.Bokeh` to `pn.Column` for flexibility
   - Maintains same layout structure (tabs, rows)
   - Same error handling and graceful degradation

6. **Visual Improvements**:
   - Colormap changed from `gray` to `cividis` (more perceptually uniform)
   - Plot size reduced from 800px to 512px for better layout
   - Added `undo`/`redo` tools to toolbar
   - Linear scaling with `clim=(vmin, vmax)` based on array min/max values

7. **Dependencies**:
   - Added `holoviews>=1.18.0`
   - Added `datashader>=0.16.0` (for potential future use)
   - Added `colorcet` (additional colormaps)
   - Removed `ipympl` (matplotlib widget support, no longer needed)
   - `joblib` explicitly listed (already in use)

8. **Logging Configuration**:
   - Set logger level to INFO in both `quicklook_core.py` and `app.py`
   - `logger.remove()` and `logger.add(sys.stdout, level="INFO")` for consistent output

9. **Benefits**:
   - **Interactive**: Full zoom/pan capabilities on all 2D images with independent controls per detector
   - **Correct Aspect Ratio**: 4k×4k images display as perfect squares
   - **Hover Tooltips**: Show formatted coordinates (1000.0) and pixel intensity values
   - **Date Filtering**: Efficiently filter visits by observation date
   - **Performance**: Parallel processing at both spectrograph and arm levels
   - **Cleaner Code**: Removed ~200 lines of matplotlib-specific code

### 2025-10-16: Multi-Arm/Spectrograph Support with Parallel Processing

1. **Parallel Processing Implementation**:
   - Added joblib-based parallel processing for 2D image generation
   - Two-level parallelization:
     - Spectrographs processed in parallel (`n_jobs=len(spectros)`)
     - Arms within each spectrograph processed in parallel (`n_jobs=-1`)
   - Utilizes all 128 CPU cores for maximum performance
   - Dramatic speed improvement: 12 images (4×3) processed in ~1 minute vs ~12 minutes sequentially

2. **Multi-Arm/Spectrograph Layout** ([app.py:246-316](app.py#L246-L316)):
   - Removed single-arm/spectrograph limitation
   - Created tabbed interface for spectrographs (SM1-4)
   - Panel Row layout for horizontal arm arrangement within each tab
   - Arm titles: Blue (b), Red (r), NIR (n), Medium-Red (m)

3. **Core Function Updates** ([quicklook_core.py:323-474](quicklook_core.py#L323-L474)):
   - `_build_single_2d_subplot()`: New worker function for parallel processing
   - `build_2d_figure_multi_arm()`: Returns list of (arm, Figure, error) tuples
   - `build_2d_figure()`: Updated to enforce single arm/spectrograph (throws error if list provided)
   - Matplotlib backend set to 'Agg' for parallel processing compatibility

4. **Error Handling for Missing Data** ([app.py:316-354](app.py#L316-L354)):
   - Detects "could not be found" errors (missing data)
   - Displays user-friendly placeholders for missing data
   - Differentiates between expected missing data (INFO log) and unexpected errors (WARNING log)
   - Graceful degradation: continues processing available data
   - Suppresses notifications for expected missing data

5. **UI Improvements**:
   - Status message shows total number of images being processed
   - Success notification indicates number of spectrographs plotted
   - Error placeholders styled with background color and borders
   - Clear distinction between data availability issues and processing errors

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
