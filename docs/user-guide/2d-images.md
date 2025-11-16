# Working with 2D Spectral Images

This guide explains how to visualize and interact with 2D spectral images in PFS QuickLook.

## Overview

The 2D image view displays sky-subtracted spectral images from the detector. These images show the full 2D spectrum for each fiber, allowing you to assess data quality, check for instrumental issues, and verify sky subtraction quality.

## Prerequisites

Before creating 2D images, you must:
1. [Load visit data](loading-data.md) first
2. Ensure the "Loaded visit" status message is displayed

## Creating 2D Images

### Step-by-Step Instructions

1. **Click "Show 2D Images" Button**:
   - Button is enabled after loading visit data
   - Application begins processing images
   - Progress indicated in status display

2. **Wait for Processing**:
   - Processing time varies based on number of selected spectrographs and arms
   - Typically 30-60 seconds for all selected spectrographs
   - UI remains responsive during processing
   - You can continue working in other tabs

3. **View Results**:
   - Application automatically switches to the **2D Images** tab
   - Images appear in tabbed layout (one tab per spectrograph)

## Understanding the Layout

### Tab Organization

The 2D Images tab contains sub-tabs for each selected spectrograph:

- **SM1**: Spectrograph Module 1
- **SM2**: Spectrograph Module 2
- **SM3**: Spectrograph Module 3
- **SM4**: Spectrograph Module 4

Only tabs for selected spectrographs are shown.

### Arm Arrangement

Within each spectrograph tab, arms are arranged **horizontally** (side-by-side):

**Typical arrangement**:
- **Blue arm** (b) - **Red arm** (r) - **NIR arm** (n)
  - Or: **Blue arm** (b) - **Medium-Red arm** (m) - **NIR arm** (n)

The application automatically determines the arrangement based on available data.

### Missing Arms

If data for certain arms is not available:
- Only existing arms are displayed (no blank placeholders)
- An informational note appears below the plots indicating which arms are missing
- Example: "Note: Medium-Red arm (m) not available for SM1"

## Interactive Controls

Each 2D image plot provides interactive controls through the Bokeh toolbar:

### Pan
- **Action**: Click and drag on the image
- **Use**: Move around the image to examine different regions

### Zoom
- **Wheel Zoom**: Scroll mouse wheel to zoom in/out
- **Box Zoom**: Click and drag to select a region to zoom into
- **Zoom In/Out Buttons**: Click toolbar buttons for fixed zoom steps

### Hover
- **Action**: Move mouse over the image
- **Display**: Tooltip shows:
  - X, Y pixel coordinates
  - Intensity value at that position

### Reset
- **Action**: Click the reset button in the toolbar
- **Effect**: Restores original view (zoom and pan)

### Save
- **Action**: Click the save button in the toolbar
- **Effect**: Downloads image as PNG file

### Other Tools
- **Box Select**: Select a region (for future features)
- **Wheel Zoom**: Enable/disable wheel zoom
- **Help**: Show help for interactive tools

## Screenshot

[![2D Spectral Images](../img/screenshot_2dimage.png)](../img/screenshot_2dimage.png)

The screenshot shows:
- Tabbed layout with SM1-4 tabs
- Horizontal arrangement of arms within each tab
- Interactive Bokeh plots with toolbars
- Sky-subtracted 2D spectral images

## What to Look For

### Quality Checks

When inspecting 2D images, look for:

**Good Data Indicators**:
- ✅ Smooth, continuous spectral traces
- ✅ Uniform background after sky subtraction
- ✅ Clear emission/absorption lines
- ✅ No obvious artifacts or defects

**Potential Issues**:
- ❌ Broken or discontinuous traces (fiber problems)
- ❌ Residual sky lines (sky subtraction issues)
- ❌ Hot pixels or cosmic rays (data quality)
- ❌ Unusual patterns or artifacts (instrumental issues)
- ❌ Very faint or missing traces (pointing/guiding issues)

### Comparison Across Arms

Compare the same fibers across different arms:
- Spectral features should be consistent
- Trace quality should be similar
- Background levels should be comparable

### Comparison Across Spectrographs

Compare the same positions across different spectrographs:
- Overall quality should be similar
- Systematic differences may indicate issues

## Tips for Efficient Inspection

### Workflow for Quick Inspection

For routine quality checks:
1. Load visit data
2. Click "Show 2D Images"
3. Quickly scan all spectrograph tabs
4. Look for obvious issues or anomalies
5. If everything looks good, proceed to 1D spectra

### Workflow for Detailed Inspection

For thorough quality assessment:
1. Load visit data
2. Click "Show 2D Images"
3. Use zoom to focus on regions of interest
4. Use hover to examine pixel values and coordinates
5. Compare features across arms and spectrographs

### Multi-Window Comparison

For comparing multiple visits:
1. Open multiple browser tabs
2. Load different visits in each tab
3. Create 2D images in each tab
4. Switch between tabs to compare visually

**Note**: Each browser tab maintains independent state.

## Processing Details

### Data Processing Pipeline

When you click "Show 2D Images", the application:

1. **Retrieves data products** from Butler datastore:
   - `pfsConfig` - Fiber configuration
   - `calexp` - Calibrated exposures
   - `detectorMap` - Detector mapping
   - `pfsArm` - Extracted 1D spectra
   - `sky1d` - 1D sky spectra
   - `fiberProfiles` - Fiber trace profiles

2. **Applies sky subtraction**:
   - Uses `sky1d` spectra
   - Reconstructs 2D sky image from fiber traces
   - Subtracts from calibrated exposure

3. **Applies scaling**:
   - Automatic scaling for optimal display

4. **Creates interactive plots**:
   - HoloViews Image objects with Bokeh backend
   - Configures interactive tools
   - Arranges in tabbed layout

### Parallel Processing

For performance:
- Multiple spectrographs processed in parallel
- Multiple arms within each spectrograph processed in parallel
- Maximum parallelization: up to 16 images simultaneously
- Utilizes all available CPU cores

## Troubleshooting

### Images Don't Appear

**Symptom**: Blank or empty 2D Images tab after plotting

**Solutions**:
1. Check the **Log tab** for error messages
2. Verify all required data products exist in Butler datastore
3. Check for error notifications (toast messages)
4. Try reloading visit data and plotting again

### Very Slow Rendering

**Symptom**: Rendering takes much longer than expected

**Solutions**:
1. Deselect unneeded spectrographs before plotting
2. Check server load (contact administrator if consistently slow)
3. Check network connection to datastore

### Missing Arms

**Symptom**: Some arms don't appear in the display

**This is normal**: Not all arms may be available for every visit
- Check the informational note below plots for details
- Verify with data reduction team if arms should be available
- Missing arms do not indicate an application error

### Hover Shows No Values

**Symptom**: Hovering over image doesn't show tooltip

**Solutions**:
1. Ensure hover tool is enabled in the Bokeh toolbar
2. Move mouse slowly over the image
3. Try clicking the hover tool button to activate it
4. Reload page if hover remains unresponsive

### Plot Too Small/Large

**Symptom**: Images don't fit well on screen

**Solutions**:
1. Use zoom controls to adjust view
2. Adjust browser zoom level (Ctrl+Plus/Minus or Cmd+Plus/Minus)
3. Use fullscreen mode for better viewing (F11)
4. Consider monitor resolution and browser window size

## Current Limitations

### DetectorMap Overlay Not Available

The detector map fiber trace overlay feature is not yet implemented. This feature is planned for a future release and will allow you to:
- Highlight specific fibers on the 2D image
- Visualize fiber positions on the detector
- Cross-reference between fiber configuration table and 2D images

### Export Functionality

PNG export via the save button is available, but:
- No batch export of multiple images
- No programmatic export for automation
- Format limited to PNG (no FITS or other formats)

These features are planned for future releases.

## See Also

- [Loading Data](loading-data.md) - How to load visit data
- [1D Spectra](1d-spectra.md) - Viewing 1D spectra
- [User Guide Overview](index.md) - Complete workflow
- [Troubleshooting](../troubleshooting.md) - Common issues and solutions
