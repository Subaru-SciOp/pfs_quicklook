# PFS QuickLook User Guide

Welcome to the PFS QuickLook user guide! This documentation is designed for summit and remote observers performing real-time quality assessment of spectral data during PFS observations.

## Overview

PFS QuickLook is a web application that provides interactive visualization of 2D and 1D spectral data from the PFS (Prime Focus Spectrograph) data reduction pipeline. The application allows you to quickly inspect reduced data and assess data quality during observations.

## Key Features

### Core Functionality

- **Fiber Configuration Viewer**: Interactive table showing fiber pointing details, target information, and fiber status
- **2D Spectral Images**: Sky-subtracted detector images with interactive zoom and pan
- **1D Gallery View**: 2D representation showing all fiber spectra at once
- **1D Spectra Visualization**: Interactive plots with fiber selection and filtering
- **Automatic Visit Discovery**: Background discovery with configurable auto-refresh
- **Real-time Configuration Display**: Shows current datastore, collection, and observation date

### Performance Features

- **Parallel Processing**: Fast data loading utilizing multiple CPU cores
- **Session Caching**: Intelligent caching for improved performance
- **Non-blocking UI**: All long operations run in background
- **Multi-user Support**: Independent sessions for concurrent users

### User Interface

- **Bidirectional Fiber Selection**: Automatic linking between OB codes and Fiber IDs
- **Visit List**: Newest visits first for easy access to recent observations
- **Toast Notifications**: User-friendly feedback for all operations
- **Responsive Design**: Works on various screen sizes

## Basic Workflow

The typical workflow for using PFS QuickLook involves five main steps:

### 1. Configuration Check

Verify the configuration display in the sidebar shows the correct:

- Datastore path
- Base collection name
- Observation date (UTC)

This information is loaded from the server's configuration file and updates when you reload the browser. If you find any discrepancies, please contact Support Astronomers.

### 2. Load Visit Data

1. Select a visit from the Visit dropdown menu
   - Visits are sorted with newest first
   - Use the search function to find specific visits
   - Visit list auto-refreshes based on configuration (default: 5 minutes)
2. Click the **"Load Visit"** button
3. Wait for the status message: "Loaded visit XXXXX: N fibers, M OB codes"

### 3. Select Spectrograph

Choose which spectrographs (1-4) to visualize in 2D image visualization step using the checkbox group in the sidebar. All spectrographs are selected by default. You can deselect any spectrograph you don't need to inspect.

### 4. Visualize Data

After loading visit data, you can create visualizations:

- **Show 2D Images (Optional)**: Display sky-subtracted 2D images for all selected spectrographs and arms (showing `calexp` images)
- **Show 1D Spectra Image (Recommended)**: Show a gallery view of all 1D fiber spectra (showing `pfsMerged` images)
- **Show 1D Spectra (Recommended)**: Display individual 1D spectra for selected fibers (showing `pfsMerged` spectra)

### 5. Filter Fibers (Optional)

For focused analysis of specific fibers:

- Select by **OB Code** (observation code) - Fiber IDs auto-populate
- Select by **Fiber ID** directly - OB codes auto-populate
- The selection boxes are bidirectionally synchronized

## Quick Navigation

For detailed instructions on each operation, see:

- **[Loading Visit Data](loading-data.md)** - How to select and load visits
- **[2D Images](2d-images.md)** - Working with 2D spectral images
- **[1D Spectra](1d-spectra.md)** - Viewing individual and gallery 1D spectra

## Tips for Efficient Use

### Typical Inspection Workflow

For routine quality checks:

1. Load visit data
2. (Optional) View 2D images for quick visual check
3. Check 1D Gallery view for overall spectral quality and find interesting objects from hover tooltips
4. View 1D Spectra for detailed inspection of selected fibers

### Multi-Session Use

Each browser session is independent:

- You can open multiple browser tabs for different visits
- Each session maintains its own state
- No interference between concurrent users

## Understanding the Interface

### Sidebar (Left Panel)

The sidebar contains all controls and is organized into sections:

1. **Visit Selection Section**

   - Visit selection dropdown
   - Load Visit button

2. **Visualize 2D Images Section**

   - Detector map overlay switch
   - Spectrograph selection (checkboxes for SM1-4)
   - "Show 2D Images" button

3. **Visualize 1D Spectra Image Section**

   - "Show 1D Spectra Image" button

4. **Visualize 1D Spectra Section**

   - OB Code dropdown (multi-select)
   - Fiber ID dropdown (multi-select)
   - "Show 1D Spectra" button
   - "Clear Selection" button

5. **Reset Section**

   - Reset button

6. **Status Display**

   - Status display
   - Current datastore path
   - Base collection name
   - Observation date (UTC)

### Main Panel (Right)

The main panel contains tabbed views:

- **Target Info**: Fiber configuration table (displayed first)
- **2D Images**: Tabs for each spectrograph (SM1-4) with horizontal arm layout
- **1D Image**: Gallery view of all fiber spectra
- **1D Spectra**: Interactive plot of selected fiber spectra
- **Log**: Execution status and parameter information

## Getting Help

If you encounter issues:

1. Check the **[Troubleshooting Guide](../troubleshooting.md)** for common problems
2. Review the configuration display to verify settings
3. Check the Log tab for error messages
4. Contact support (see main [README](../README.md) for contact information)

## Next Steps

Ready to start using the application? Begin with:

- **[Loading Visit Data](loading-data.md)** - Learn how to load your first visit

For administrators setting up the application:

- **[Setup Guide](../setup.md)** - Installation and configuration instructions
