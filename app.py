#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading

import numpy as np
import panel as pn
from bokeh.models.widgets.tables import NumberFormatter
from joblib import Parallel, delayed
from loguru import logger

# Global flag and lock to track if periodic callbacks are registered (server-level)
_periodic_callbacks_registered = False
_periodic_callbacks_lock = threading.Lock()

from quicklook_core import (
    ARM_NAMES,
    BASE_COLLECTION,
    DATASTORE,
    OBSDATE_UTC,
    VISIT_REFRESH_INTERVAL,
    build_1d_bokeh_figure_single_visit,
    build_1d_spectra_as_image,
    build_2d_arrays_multi_arm,
    create_holoviews_from_arrays,
    create_pfsconfig_dataframe,
    discover_visits,
    get_butler_cached,
    load_visit_data,
    reload_config,
)

pn.extension("tabulator", notifications=True)


# --- Session State Management ---
def get_session_state():
    """Get session-specific state object

    Uses pn.state.curdoc.session_context.app_state (public attribute)
    to ensure each browser session has independent state.

    This approach is recommended over using private attributes like
    _session_state, as it uses the public API and is more stable
    across Panel versions.

    Returns:
        dict: Session-specific state dictionary
    """
    ctx = pn.state.curdoc.session_context

    # Initialize app_state as a public attribute on session_context
    if not hasattr(ctx, "app_state"):
        ctx.app_state = {
            "visit_data": {
                "loaded": False,
                "visit": None,
                "pfsConfig": None,
                "obcode_to_fibers": {},
                "fiber_to_obcode": {},
            },
            "programmatic_update": False,
            "visit_discovery": {"status": None, "result": None, "error": None},
            "visit_cache": {},  # {visit_id: obsdate_utc} - caches validated visits
            "butler_cache": {},  # {(datastore, collection, visit): Butler} - caches Butler instances
            "config": {  # Session-specific configuration
                "datastore": None,
                "base_collection": None,
                "obsdate_utc": None,
                "refresh_interval": None,
            },
        }

    return ctx.app_state


def should_skip_update(state):
    """Check if widget update should be skipped

    Returns True if either:
    - Update is programmatic (to prevent circular updates)
    - Visit data is not loaded yet

    Parameters
    ----------
    state : dict
        Session state dictionary

    Returns
    -------
    bool
        True if update should be skipped
    """
    return state["programmatic_update"] or not state["visit_data"]["loaded"]


def get_config():
    """Get session-specific configuration

    Returns configuration from session state. If not initialized,
    returns default global values.

    Returns
    -------
    tuple
        (datastore, base_collection, obsdate_utc, refresh_interval)
    """
    state = get_session_state()
    config = state["config"]

    # If config is not initialized, use global defaults
    if config["datastore"] is None:
        return DATASTORE, BASE_COLLECTION, OBSDATE_UTC, VISIT_REFRESH_INTERVAL

    return (
        config["datastore"],
        config["base_collection"],
        config["obsdate_utc"],
        config["refresh_interval"],
    )


# --- Widgets ---
spectro_cbg = pn.widgets.CheckButtonGroup(
    name="Spectrograph",
    options=[f"SM{i}" for i in range(1, 5)],
    value=[f"SM{i}" for i in range(1, 5)],
    button_type="primary",
    button_style="outline",
    sizing_mode="stretch_width",
    stylesheets=[
        """
        .bk-btn.bk-btn-primary.bk-active {
            color: white !important;
        }
        """
    ],
)

visit_mc = pn.widgets.MultiChoice(
    # name="Visit",
    options=[],
    max_items=1,  # temporary limit to single visit mode
    placeholder="Loading visits...",  # Initial state shows loading
)

obcode_mc = pn.widgets.MultiChoice(
    name="OB Code",
    options=[],
    option_limit=20,
    search_option_limit=10,
)

fibers_mc = pn.widgets.MultiChoice(
    name="Fiber ID",
    options=np.arange(1, 2605, dtype=int).tolist(),
    option_limit=20,
    search_option_limit=10,
)

btn_clear_selection = pn.widgets.Button(
    name="Clear Selection",
    button_type="default",
    min_width=140,
    sizing_mode="fixed",
)

subtract_sky_chk = pn.widgets.Checkbox(name="Sky subtraction", value=True)
overlay_chk = pn.widgets.Checkbox(name="DetectorMap overlay", value=False)
scale_sel = pn.widgets.Select(
    name="Scale", options=["zscale", "minmax"], value="zscale"
)

btn_load_data = pn.widgets.Button(name="Load Visit", button_type="primary")
btn_plot_2d = pn.widgets.Button(
    name="Show 2D Images (Optional, Slow)",
    button_type="primary",
    disabled=True,
    sizing_mode="stretch_width",
)
btn_plot_1d_image = pn.widgets.Button(
    name="Show 1D Spectra Image",
    button_type="primary",
    disabled=True,
    sizing_mode="stretch_width",
)
btn_plot_1d = pn.widgets.Button(
    name="Show 1D Spectra",
    button_type="primary",
    disabled=True,
    min_width=140,
    sizing_mode="stretch_width",
)
btn_reset = pn.widgets.Button(name="Reset", sizing_mode="stretch_width")

status_text = pn.pane.Markdown("**Ready**", sizing_mode="stretch_width", height=60)

# Configuration info text (will be populated when session starts)
config_info_text = pn.pane.Markdown(
    "_Configuration will be displayed when session starts._",
    sizing_mode="stretch_width",
)

# --- Output panes ---
pane_pfsconfig = pn.Column(sizing_mode="scale_width")
pane_2d = pn.Column(sizing_mode="scale_width")
pane_1d = pn.Column(height=550, sizing_mode="scale_width")
pane_1d_image = pn.Column(sizing_mode="scale_width")
log_md = pn.pane.Markdown("**Ready.**")


# --- Loading spinner helpers ---
def create_loading_overlay(message):
    """Build a fresh loading spinner overlay for a target pane."""

    return pn.Column(
        pn.Spacer(height=100),
        pn.indicators.LoadingSpinner(value=True, size=100),
        pn.pane.Markdown(
            f"**{message}**",
            styles={"font-size": "1.2em", "text-align": "center"},
        ),
        align="center",
        sizing_mode="scale_width",
    )


tabs = pn.Tabs(
    ("Target Info", pane_pfsconfig),
    ("2D Images", pane_2d),
    ("1D Image", pane_1d_image),
    ("1D Spectra", pane_1d),
    ("Log", log_md),
)


def toggle_buttons(disabled=True, include_load=False):
    """Enable or disable all action buttons

    Parameters
    ----------
    disabled : bool, optional
        If True, disable buttons. If False, enable buttons. Default is True.
    include_load : bool, optional
        If True, also toggle the Load Data button. Default is False.
    """
    if include_load:
        btn_load_data.disabled = disabled
    btn_plot_2d.disabled = disabled
    btn_plot_1d.disabled = disabled
    btn_plot_1d_image.disabled = disabled
    btn_reset.disabled = disabled


def show_loading_spinner(message, tab_index=None):
    """Show loading spinner in main panel

    Parameters
    ----------
    message : str
        Message to display below the spinner
    tab_index : int, optional
        Tab index to show spinner in (0=pfsConfig, 1=2D Images, 2=1D Image, 3=1D Spectra, 4=Log).
        If None, shows in currently active tab.
    """
    overlay = create_loading_overlay(message)

    # Determine which tab to show spinner in
    if tab_index is None:
        tab_index = tabs.active

    # Clear the appropriate pane and show spinner
    if tab_index == 0:
        pane_pfsconfig.objects = [overlay]
    elif tab_index == 1:
        pane_2d.objects = [overlay]
    elif tab_index == 2:
        pane_1d_image.objects = [overlay]
    elif tab_index == 3:
        pane_1d.objects = [overlay]


def hide_loading_spinner():
    """No-op placeholder retained for backward compatibility."""


# --- Callbacks ---
def load_data_callback(event=None):
    """Load visit data and update OB Code options

    Loads pfsConfig for the selected visit, creates bidirectional
    mappings between OB codes and fiber IDs, and populates the
    OB Code widget options.

    Parameters
    ----------
    event : panel.io.state.Event, optional
        Panel button click event (unused)

    Notes
    -----
    Updates session state with loaded data and enables plot buttons.
    Shows notifications on success or failure.
    Clears existing plots from tabs when loading a new visit.
    """
    if not visit_mc.value:
        pn.state.notifications.warning("Select at least one visit.")
        logger.warning("No visit selected.")
        return

    visit = visit_mc.value[0]

    # Disable all buttons during loading
    toggle_buttons(disabled=True, include_load=True)

    # Clear existing plots when loading a new visit
    pane_2d.objects = []
    pane_1d.objects = []
    pane_1d_image.objects = []

    try:
        status_text.object = f"**Loading visit {visit}...**"
        datastore, base_collection, _, _ = get_config()
        pfsConfig, obcode_to_fibers, fiber_to_obcode = load_visit_data(
            datastore, base_collection, visit
        )

        # Update session state
        state = get_session_state()
        state["visit_data"] = {
            "loaded": True,
            "visit": visit,
            "pfsConfig": pfsConfig,
            "obcode_to_fibers": obcode_to_fibers,
            "fiber_to_obcode": fiber_to_obcode,
        }

        # Create pfsConfig DataFrame and display in Tabulator
        df_pfsconfig = create_pfsconfig_dataframe(pfsConfig)
        logger.info(f"Created pfsConfig DataFrame with shape: {df_pfsconfig.shape}")
        logger.info(f"DataFrame columns: {df_pfsconfig.columns.tolist()}")

        # Style function to highlight different fiber types
        def style_science_bad_fibers(row):
            """Apply styling based on targetType and fiberStatus

            - SCIENCE + GOOD: Bold + black (important science targets)
            - SCIENCE + not GOOD: Bold + gray (problematic science targets)
            - SKY: Medium gray
            - FLUXSTD: Medium gray
            - Others: Light gray
            """
            if row["targetType"] == "SCIENCE" and row["fiberStatus"] == "GOOD":
                return ["font-weight: bold"] * len(row)
            elif row["targetType"] == "SCIENCE" and row["fiberStatus"] != "GOOD":
                return ["font-weight: bold; color: #999999"] * len(row)
            elif row["targetType"] == "SKY":
                return ["color: #999999"] * len(row)
            elif row["targetType"] == "FLUXSTD":
                return ["color: #999999"] * len(row)
            else:
                return ["color: #CCCCCC"] * len(row)

        # Configure column-specific settings
        tabulator = pn.widgets.Tabulator(
            df_pfsconfig,
            pagination="local",
            page_size=250,
            sizing_mode="stretch_width",
            height=700,
            show_index=False,
            layout="fit_data_table",
            disabled=True,  # Read-only table
            widths={
                "objId": 200,  # Wide enough for 64-bit integers (up to 20 digits)
                "obCode": 300,  # Double width for observation codes
            },
            text_align={"spectrograph": "center", "catId": "right"},
            formatters={
                "catId": NumberFormatter(
                    format="0"
                ),  # Display without thousand separators
            },
            configuration={
                "columns": [
                    {"field": "fiberId", "headerFilter": True, "title": "Fiber ID"},
                    {
                        "field": "spectrograph",
                        "headerFilter": True,
                        "title": "Sp",
                    },
                    {"field": "objId", "headerFilter": True, "title": "Object ID"},
                    {"field": "obCode", "headerFilter": True, "title": "OB Code"},
                    {"field": "ra", "headerFilter": False, "title": "RA"},
                    {"field": "dec", "headerFilter": False, "title": "Dec"},
                    {"field": "catId", "headerFilter": True, "title": "Catalog ID"},
                    {
                        "field": "targetType",
                        "headerFilter": True,
                        "title": "Target Type",
                    },
                    {
                        "field": "fiberStatus",
                        "headerFilter": True,
                        "title": "Fiber Status",
                    },
                    {
                        "field": "proposalId",
                        "headerFilter": True,
                        "title": "Proposal ID",
                    },
                ],
            },
        )

        # Apply styling
        tabulator.style.apply(style_science_bad_fibers, axis=1)

        # Create header information from pfsConfig
        header_info = f"""
### Visit {visit} - Pointing Information

- **pfsDesign ID**: {pfsConfig.pfsDesignId} (0x{pfsConfig.pfsDesignId:016x})
- **RA**: {pfsConfig.raBoresight:.6f} deg
- **Dec**: {pfsConfig.decBoresight:.6f} deg
- **PA**: {pfsConfig.posAng:.2f} deg
- **Arms**: {pfsConfig.arms}
- **Design Name**: {pfsConfig.designName if hasattr(pfsConfig, 'designName') else 'N/A'}
"""
        header_pane = pn.pane.Markdown(header_info, sizing_mode="stretch_width")

        pane_pfsconfig.objects = [header_pane, tabulator]
        logger.info("Tabulator widget created and added to pane_pfsconfig")

        # Update OB Code options
        state["programmatic_update"] = True
        obcode_mc.options = sorted(obcode_to_fibers.keys())
        obcode_mc.value = []  # Clear selection
        fibers_mc.value = []  # Clear selection
        state["programmatic_update"] = False

        num_fibers = len(pfsConfig.fiberId)
        num_obcodes = len(obcode_to_fibers)
        status_text.object = (
            f"**Loaded visit {visit}**: {num_fibers} fibers, {num_obcodes} OB codes"
        )
        pn.state.notifications.success(f"Visit {visit} loaded successfully")

        log_md.object = f"""**Data loaded**
- visit: {visit}
- total fibers: {num_fibers}
- OB codes: {num_obcodes}
"""

    except Exception as e:
        pn.state.notifications.error(f"Failed to load visit data: {e}")
        logger.error(f"Failed to load visit data: {e}")
        status_text.object = "**Error loading data**"
        # On error, disable plot buttons
        btn_plot_2d.disabled = True
        btn_plot_1d.disabled = True
        btn_plot_1d_image.disabled = True
    finally:
        # Always re-enable Load Data and Reset buttons
        btn_load_data.disabled = False
        btn_reset.disabled = False
        # Enable plot buttons only if data was loaded successfully
        state = get_session_state()
        if state["visit_data"]["loaded"]:
            btn_plot_2d.disabled = False
            btn_plot_1d.disabled = False
            btn_plot_1d_image.disabled = False


def on_obcode_change(event):
    """Update Fiber ID selection based on OB Code selection

    Callback for OB Code widget value changes. Automatically selects
    all fiber IDs associated with the selected OB codes.

    Parameters
    ----------
    event : panel.io.state.Event
        Panel widget value change event

    Notes
    -----
    Implements bidirectional synchronization between OB Code and Fiber ID.
    Skips update if programmatic or data not loaded.
    """
    state = get_session_state()
    if should_skip_update(state):
        return

    selected_obcodes = obcode_mc.value

    # Get fiber IDs for selected OB codes (empty list if no OB codes selected)
    obcode_to_fibers = state["visit_data"]["obcode_to_fibers"]
    fiber_ids = []
    for obcode in selected_obcodes:
        fiber_ids.extend(obcode_to_fibers.get(obcode, []))

    # Update fiber selection
    state["programmatic_update"] = True
    fibers_mc.value = sorted(set(fiber_ids))
    state["programmatic_update"] = False

    logger.info(
        f"Selected {len(fiber_ids)} fibers from {len(selected_obcodes)} OB codes"
    )


def on_fiber_change(event):
    """Update OB Code selection based on Fiber ID selection

    Callback for Fiber ID widget value changes. Automatically selects
    all OB codes associated with the selected fiber IDs.

    Parameters
    ----------
    event : panel.io.state.Event
        Panel widget value change event

    Notes
    -----
    Implements bidirectional synchronization between Fiber ID and OB Code.
    Skips update if programmatic or data not loaded.
    """
    state = get_session_state()
    if should_skip_update(state):
        return

    selected_fibers = fibers_mc.value

    # Get OB codes for selected fiber IDs (empty set if no fibers selected)
    fiber_to_obcode = state["visit_data"]["fiber_to_obcode"]
    obcodes = set()
    for fiber_id in selected_fibers:
        obcode = fiber_to_obcode.get(fiber_id)
        if obcode:
            obcodes.add(obcode)

    # Update OB code selection
    state["programmatic_update"] = True
    obcode_mc.value = sorted(obcodes)
    state["programmatic_update"] = False

    logger.info(f"Selected {len(obcodes)} OB codes from {len(selected_fibers)} fibers")


def clear_selection_callback(event=None):
    """Clear both OB Code and Fiber ID selections

    Callback for Clear Selection button. Clears both OB Code and Fiber ID
    widget selections simultaneously.

    Parameters
    ----------
    event : panel.io.state.Event, optional
        Panel button click event (unused)

    Notes
    -----
    Uses programmatic_update flag to prevent circular reference issues
    with bidirectional synchronization.
    """
    state = get_session_state()

    # Clear both selections
    state["programmatic_update"] = True
    obcode_mc.value = []
    fibers_mc.value = []
    state["programmatic_update"] = False

    logger.info("Cleared OB Code and Fiber ID selections")
    pn.state.notifications.info("Selection cleared")


def plot_2d_callback(event=None):
    """Create 2D plot with support for multiple arms and spectrographs

    Creates interactive HoloViews 2D spectral images for all selected
    spectrographs and arms. Automatically attempts to load all 4 arms
    (b, r, n, m) and displays them in appropriate layout.

    Parameters
    ----------
    event : panel.io.state.Event, optional
        Panel button click event (unused)

    Notes
    -----
    Uses parallel processing for multiple spectrographs/arms.
    Automatically switches to 2D tab after successful plot creation.
    Shows informational notes for missing arms and errors.
    """
    state = get_session_state()

    if not state["visit_data"]["loaded"]:
        pn.state.notifications.warning("Load data first.")
        return

    # Disable all buttons during processing
    toggle_buttons(disabled=True, include_load=True)

    visit = state["visit_data"]["visit"]

    # Get session configuration
    datastore, base_collection, _, _ = get_config()

    # Get pre-loaded pfsConfig from session state (already loaded in load_data_callback)
    # This avoids redundant Butler.get() calls for each arm (saves ~0.177s × 15 arms = ~2.7s)
    pfs_config_shared = state["visit_data"]["pfsConfig"]
    if pfs_config_shared is None:
        logger.warning("pfsConfig not found in session state, will be loaded per-arm")
    else:
        logger.info("Using pre-loaded pfsConfig from session state (optimization)")

    # Get Butler cache from session state for Butler instance reuse
    # This avoids repeated Butler creation (saves ~0.1-0.2s per arm × 16 arms = ~1.6-3.2s)
    butler_cache = state["butler_cache"]
    logger.info("Using Butler cache from session state (optimization)")

    spectro_selection = (
        spectro_cbg.value
        if isinstance(spectro_cbg.value, list)
        else [spectro_cbg.value]
    )
    spectros = []
    for item in spectro_selection:
        label = str(item).strip()
        if not label.startswith("SM"):
            logger.warning(f"Ignoring unexpected spectrograph label: {item}")
            continue

        try:
            spectros.append(int(label[2:]))
        except ValueError:
            logger.warning(f"Ignoring malformed spectrograph label: {item}")

    if not spectros:
        pn.state.notifications.warning("Select at least one spectrograph.")
        toggle_buttons(disabled=False, include_load=True)
        return
    # Always attempt to load all 4 arms
    all_arms = ["b", "r", "n", "m"]
    fibers = fibers_mc.value if fibers_mc.value else None

    subtract_sky = subtract_sky_chk.value
    overlay = overlay_chk.value
    scale_algo = scale_sel.value

    if overlay:
        pn.state.notifications.warning("DetectorMap overlay is not supported yet.")

    try:
        # Show loading spinner in 2D tab
        show_loading_spinner("Processing 2D images (may take a while)...", tab_index=1)
        tabs.active = 1  # Switch to 2D tab to show spinner

        status_text.object = (
            "**Checking data availability and creating 2D plots (may take a while)...**"
        )
        logger.info(
            f"Attempting to load all {len(all_arms)} arms for {len(spectros)} spectrographs"
        )

        # Process spectrographs in parallel (only array generation)
        # Two-level parallelization: spectrographs in parallel, arms within each spectrograph in parallel
        spectrograph_panels = {}

        def build_arrays_for_spectrograph(spectro):
            """Build arrays for a single spectrograph (pickle-able)"""
            logger.info(f"Building 2D arrays for SM{spectro} with all arms {all_arms}")
            try:
                array_results = build_2d_arrays_multi_arm(
                    datastore=datastore,
                    base_collection=base_collection,
                    visit=visit,
                    spectrograph=spectro,
                    arms=all_arms,
                    subtract_sky=subtract_sky,
                    overlay=overlay,
                    fiber_ids=fibers if overlay else None,
                    scale_algo=scale_algo,
                    n_jobs=-1,  # Use all available CPUs for arms within each spectrograph
                    pfsConfig_preloaded=pfs_config_shared,  # Share pfsConfig across all arms
                    butler_cache=butler_cache,  # Share Butler cache across all arms
                )
                return (spectro, array_results, None)
            except Exception as e:
                logger.error(f"Failed to build 2D arrays for SM{spectro}: {e}")
                return (spectro, None, str(e))

        # Parallel processing across spectrographs (arrays only, pickle-able)
        logger.info(f"Building arrays for {len(spectros)} spectrographs in parallel")
        array_results_all = Parallel(n_jobs=len(spectros), verbose=10)(
            delayed(build_arrays_for_spectrograph)(spectro) for spectro in spectros
        )

        # Create HoloViews objects in main thread (not pickle-able)
        logger.info("Arrays built, now creating HoloViews images in main thread")

        for spectro, array_results, error in array_results_all:
            if array_results is not None and error is None:
                # Create HoloViews objects from arrays
                try:
                    arm_results = create_holoviews_from_arrays(array_results, spectro)
                    error = None
                except Exception as e:
                    logger.error(
                        f"Failed to create HoloViews images for SM{spectro}: {e}"
                    )
                    arm_results = None
                    error = str(e)
            else:
                arm_results = None
            logger.info(
                f"Processing SM{spectro}: arm_results type={type(arm_results)}, error={error}"
            )

            if arm_results is not None and error is None:
                # Verify arm_results is a list
                if not isinstance(arm_results, list):
                    logger.error(
                        f"SM{spectro}: arm_results is not a list, got {type(arm_results)}: {arm_results}"
                    )
                    pn.state.notifications.error(f"Invalid result type for SM{spectro}")
                    continue

                # Separate successful plots from missing/error arms
                successful_arms = {}  # arm -> HoloViews pane
                missing_arms = []  # List of missing arm names
                error_arms = []  # List of (arm, error_msg) tuples for real errors

                try:
                    for arm, hv_img, arm_error in arm_results:
                        if hv_img is not None and arm_error is None:
                            # Successfully loaded
                            successful_arms[arm] = pn.pane.HoloViews(
                                hv_img,
                                backend="bokeh",
                                # Don't use sizing_mode to preserve aspect ratio set in HoloViews
                            )
                        else:
                            # Check if it's a "not found" error (data doesn't exist)
                            is_not_found = (
                                arm_error and "could not be found" in arm_error
                            )

                            arm_name = ARM_NAMES.get(arm, arm)

                            if is_not_found:
                                # Data doesn't exist - add to missing list
                                missing_arms.append(arm_name)
                                logger.info(
                                    f"SM{spectro} {arm_name}: Data not available (expected for some configurations)"
                                )
                            else:
                                # Real error - add to error list
                                error_arms.append((arm_name, arm_error))
                                logger.warning(f"SM{spectro} {arm_name}: {arm_error}")

                except Exception as e:
                    logger.error(f"Error iterating arm_results for SM{spectro}: {e}")
                    pn.state.notifications.error(
                        f"Error processing arms for SM{spectro}: {e}"
                    )
                    continue

                # Determine display order based on which arms are available
                # brn order: b, r, n
                # bmn order: b, m, n
                if successful_arms:
                    # Check if we have 'r' or 'm' to determine order
                    has_r = "r" in successful_arms
                    has_m = "m" in successful_arms

                    if has_r and not has_m:
                        # brn configuration
                        display_order = ["b", "r", "n"]
                    elif has_m and not has_r:
                        # bmn configuration
                        display_order = ["b", "m", "n"]
                    elif has_r and has_m:
                        # Both exist (unusual), prefer brn order
                        display_order = ["b", "r", "n", "m"]
                    else:
                        # Only b and/or n
                        display_order = ["b", "n"]

                    # Create arm panes in the determined order
                    arm_panes = [
                        successful_arms[arm]
                        for arm in display_order
                        if arm in successful_arms
                    ]

                    # Create the row with successful arms
                    arm_row = pn.Row(*arm_panes, sizing_mode="stretch_width")

                    # Create informational notes for missing/error arms
                    notes = []
                    if missing_arms:
                        missing_str = ", ".join(missing_arms)
                        notes.append(
                            f"_Note: {missing_str} arm(s) not available for this visit_"
                        )

                    if error_arms:
                        for arm_name, err_msg in error_arms:
                            notes.append(f"_Error loading {arm_name}: {err_msg}_")

                    # Combine row and notes
                    if notes:
                        notes_md = pn.pane.Markdown(
                            "\n\n".join(notes),
                            sizing_mode="stretch_width",
                            styles={"font-size": "0.9em", "color": "#666"},
                        )
                        spectrograph_panels[spectro] = pn.Column(
                            arm_row, notes_md, sizing_mode="stretch_width"
                        )
                    else:
                        spectrograph_panels[spectro] = arm_row
                else:
                    logger.warning(f"SM{spectro}: No valid arm panes created")
            else:
                # Only show error notification if it's not a "data not found" error
                if error and "could not be found" not in error:
                    pn.state.notifications.error(
                        f"Failed to create plots for SM{spectro}: {error}"
                    )
                else:
                    logger.info(f"SM{spectro}: Skipped due to missing data")

        if not spectrograph_panels:
            raise RuntimeError(
                "No 2D plots were successfully created. "
                "Check that the selected arm/spectrograph combinations have data available."
            )

        # Create tabbed layout for multiple spectrographs
        tab_items = []
        for spectro in sorted(spectrograph_panels.keys()):
            tab_items.append((f"SM{spectro}", spectrograph_panels[spectro]))

        # Replace loading spinner with new tabs in one atomic operation
        new_tabs = pn.Tabs(*tab_items)
        pane_2d.objects = [new_tabs]

        tabs.active = 1  # Switch to 2D tab
        status_text.object = f"**2D plot created for visit {visit}**"
        pn.state.notifications.success(
            f"2D plot created for {len(spectrograph_panels)} spectrograph(s)"
        )

        fiber_info = f"{len(fibers)} selected" if fibers else "none"
        log_md.object = f"""**2D plot created**
- visit: {visit}
- spectrographs: {', '.join([f'SM{s}' for s in sorted(spectros)])}
- fibers: {fiber_info}
- subtract_sky: {subtract_sky}, overlay: {overlay}, scale: {scale_algo}
"""
    except Exception as e:
        error_pane = pn.pane.Markdown(f"**Error:** {e}")
        pane_2d.objects = [error_pane]
        pn.state.notifications.error(f"Failed to show 2D image: {e}")
        logger.error(f"Failed to show 2D image: {e}")
        status_text.object = "**Error creating 2D plot**"
    finally:
        # Hide loading spinner and re-enable buttons after processing
        hide_loading_spinner()
        toggle_buttons(disabled=False, include_load=True)


def plot_1d_callback(event=None):
    """Create 1D plot using Bokeh

    Creates interactive Bokeh plot showing 1D spectra for selected fibers.
    Displays multiple fibers with error bands, interactive legend, and
    hover tooltips.

    Parameters
    ----------
    event : panel.io.state.Event, optional
        Panel button click event (unused)

    Notes
    -----
    Requires fiber selection (shows warning if none selected).
    Automatically switches to 1D tab after successful plot creation.
    """
    state = get_session_state()

    if not state["visit_data"]["loaded"]:
        pn.state.notifications.warning("Load data first.")
        return

    if not fibers_mc.value:
        pn.state.notifications.warning("Select at least one fiber ID.")
        logger.warning("No fiber ID selected.")
        return

    # Disable all buttons during processing
    toggle_buttons(disabled=True, include_load=True)

    visit = state["visit_data"]["visit"]
    fibers = fibers_mc.value

    try:
        # Show loading spinner in 1D Spectra tab
        show_loading_spinner("Creating 1D spectra plot...", tab_index=3)
        tabs.active = 3  # Switch to 1D Spectra tab to show spinner

        status_text.object = "**Creating 1D plot...**"

        # Get session configuration
        datastore, base_collection, _, _ = get_config()

        # Use Bokeh for rendering
        p_fig1d = build_1d_bokeh_figure_single_visit(
            datastore=datastore,
            base_collection=base_collection,
            visit=visit,
            fiber_ids=fibers,
        )

        # Replace spinner with plot in one atomic operation
        bokeh_pane = pn.pane.Bokeh(p_fig1d, sizing_mode="scale_width")
        pane_1d.objects = [bokeh_pane]
        status_text.object = f"**1D plot created for visit {visit}**"
        pn.state.notifications.success("1D plot created")

        log_md.object = f"""**1D plot created**
- visit: {visit}
- fibers: {len(fibers)} selected ({fibers[:10]}{'...' if len(fibers) > 10 else ''})
"""
    except Exception as e:
        error_pane = pn.pane.Markdown(f"**Error:** {e}")
        pane_1d.objects = [error_pane]
        pn.state.notifications.error(f"Failed to show 1D spectra: {e}")
        logger.error(f"Failed to show 1D spectra: {e}")
        status_text.object = "**Error creating 1D plot**"
    finally:
        # Hide loading spinner and re-enable buttons after processing
        hide_loading_spinner()
        toggle_buttons(disabled=False, include_load=True)


def plot_1d_image_callback(event=None):
    """Create 2D representation of all 1D spectra

    Creates a 2D image where each row represents one fiber's 1D spectrum.
    Uses HoloViews for interactive visualization with zoom and pan.

    Parameters
    ----------
    event : panel.io.state.Event, optional
        Panel button click event (unused)

    Notes
    -----
    Displays all fibers if none selected.
    Automatically switches to 1D Image tab after successful creation.
    """
    state = get_session_state()

    if not state["visit_data"]["loaded"]:
        pn.state.notifications.warning("Load data first.")
        return

    # Disable all buttons during processing
    toggle_buttons(disabled=True, include_load=True)

    visit = state["visit_data"]["visit"]
    fibers = fibers_mc.value if fibers_mc.value else None
    scale_algo = scale_sel.value

    try:
        # Show loading spinner in 1D Image tab
        show_loading_spinner("Creating 1D spectra image...", tab_index=2)
        tabs.active = 2  # Switch to 1D Image tab to show spinner

        status_text.object = "**Creating 1D spectra image...**"

        # Get session configuration
        datastore, base_collection, _, _ = get_config()

        # Build 1D spectra as 2D image
        hv_img = build_1d_spectra_as_image(
            datastore=datastore,
            base_collection=base_collection,
            visit=visit,
            fiber_ids=fibers,
            scale_algo=scale_algo,
        )

        # Replace spinner with image in one atomic operation
        hv_pane = pn.pane.HoloViews(hv_img, backend="bokeh")
        pane_1d_image.objects = [hv_pane]
        status_text.object = f"**1D spectra image created for visit {visit}**"
        pn.state.notifications.success("1D spectra image created")

        fiber_info = f"{len(fibers)} selected" if fibers else "all fibers"
        log_md.object = f"""**1D spectra image created**
- visit: {visit}
- fibers: {fiber_info}
- scale: {scale_algo}
"""
    except Exception as e:
        error_pane = pn.pane.Markdown(f"**Error:** {e}")
        pane_1d_image.objects = [error_pane]
        pn.state.notifications.error(f"Failed to create 1D spectra image: {e}")
        logger.error(f"Failed to create 1D spectra image: {e}")
        status_text.object = "**Error creating 1D spectra image**"
    finally:
        # Hide loading spinner and re-enable buttons after processing
        hide_loading_spinner()
        toggle_buttons(disabled=False, include_load=True)


def reset_app(event=None):
    """Reset application state

    Clears all plots, session state, and widget selections.
    Returns application to initial ready state.

    Parameters
    ----------
    event : panel.io.state.Event, optional
        Panel button click event (unused)

    Notes
    -----
    Disables plot buttons and re-enables Load Data button.
    Clears OB Code options and all selections.
    """
    pane_pfsconfig.objects = []
    pane_2d.objects = []
    pane_1d.objects = []
    pane_1d_image.objects = []
    log_md.object = "**Reset.**"
    status_text.object = "**Ready**"

    # Clear session state
    state = get_session_state()
    state["visit_data"] = {
        "loaded": False,
        "visit": None,
        "pfsConfig": None,
        "obcode_to_fibers": {},
        "fiber_to_obcode": {},
    }

    # Disable plot buttons, enable Load Data and Reset
    btn_plot_2d.disabled = True
    btn_plot_1d.disabled = True
    btn_plot_1d_image.disabled = True
    btn_load_data.disabled = False
    btn_reset.disabled = False

    # Clear OB Code and Fiber ID selections
    visit_mc.value = []
    obcode_mc.options = []
    obcode_mc.value = []
    fibers_mc.value = []


# --- Asynchronous visit discovery ---
def get_visit_discovery_state():
    """Get or create visit discovery state for current session

    Returns
    -------
    dict
        Visit discovery state with keys: 'status', 'result', 'error'
    """
    state = get_session_state()
    return state["visit_discovery"]


def discover_visits_worker(
    state_dict, visit_cache, datastore, base_collection, obsdate_utc
):
    """Worker function that runs in background thread

    Parameters
    ----------
    state_dict : dict
        Dictionary reference to store results (passed from main thread)
    visit_cache : dict
        Dictionary of {visit_id: obsdate_utc} for previously validated visits
    datastore : str
        Path to Butler datastore
    base_collection : str
        Base collection name
    obsdate_utc : str
        Observation date in UTC (YYYY-MM-DD format)
    """
    try:
        logger.info(f"Starting visit discovery for date: {obsdate_utc}")
        state_dict["status"] = "running"

        # Discover visits with caching (this is the slow part)
        discovered_visits, updated_cache = discover_visits(
            datastore,
            base_collection,
            obsdate_utc,
            cached_visits=visit_cache,
        )

        # Store results
        if discovered_visits:
            state_dict["status"] = "success"
            state_dict["result"] = discovered_visits
            state_dict["updated_cache"] = updated_cache
            logger.info(f"Loaded {len(discovered_visits)} visits")
        else:
            state_dict["status"] = "no_data"
            state_dict["updated_cache"] = updated_cache
            logger.warning("No visits discovered. Visit list will be empty.")

    except Exception as e:
        logger.error(f"Error during visit discovery: {e}")
        state_dict["status"] = "error"
        state_dict["error"] = str(e)


def check_visit_discovery():
    """Check if background visit discovery is complete and update widget

    Periodic callback that checks visit discovery status and updates
    the visit MultiChoice widget when complete.

    Returns
    -------
    bool
        True to continue periodic checking, False to stop
    """
    state = get_visit_discovery_state()
    session_state = get_session_state()
    status = state.get("status")

    if status == "success":
        discovered_visits = state["result"]
        updated_cache = state.get("updated_cache", {})
        old_count = len(visit_mc.options) if visit_mc.options else 0
        new_count = len(discovered_visits) if discovered_visits else 0

        # Update session cache
        session_state["visit_cache"] = updated_cache
        logger.info(f"Updated visit cache: {len(updated_cache)} visits")

        # Update widget
        visit_mc.options = discovered_visits
        visit_mc.placeholder = "Select visit..."
        visit_mc.disabled = False

        # Preserve user's selection if valid
        if visit_mc.value and discovered_visits:
            current_selection = list(visit_mc.value)
            if not all(v in discovered_visits for v in current_selection):
                visit_mc.value = []

        # Show notification
        if old_count == 0:
            pn.state.notifications.success(f"Found {new_count} visits")
            logger.info(f"Initial visit discovery: {new_count} visits")
        elif new_count > old_count:
            pn.state.notifications.success(
                f"Found {new_count - old_count} new visit(s) (total: {new_count})"
            )
            logger.info(
                f"Visit list updated: +{new_count - old_count} visits (total: {new_count})"
            )
        else:
            logger.info(f"Visit list refreshed: {new_count} visits (no changes)")

        # Reset and stop
        state.update({"status": None, "result": None, "updated_cache": None})
        return False

    elif status == "no_data":
        updated_cache = state.get("updated_cache", {})

        # Update session cache even when no data
        session_state["visit_cache"] = updated_cache

        visit_mc.options = []
        visit_mc.value = []
        visit_mc.placeholder = "No visits found"
        visit_mc.disabled = False
        pn.state.notifications.warning("No visits found for the specified date")

        state.update({"status": None, "updated_cache": None})
        return False

    elif status == "error":
        visit_mc.placeholder = "Error loading visits"
        visit_mc.disabled = False
        pn.state.notifications.error(f"Failed to discover visits: {state['error']}")

        state.update({"status": None, "error": None})
        return False

    # Still running
    return True


def trigger_visit_refresh():
    """Trigger a background visit refresh

    Called periodically if auto-refresh is enabled. Starts background
    thread and periodic callback to update visit list.

    Notes
    -----
    Only runs if no discovery is already in progress.
    """
    state = get_visit_discovery_state()
    session_state = get_session_state()

    if state.get("status") != "running":
        logger.info("Auto-refreshing visit list...")
        pn.state.notifications.info("Updating visit list...", duration=3000)

        # Get session configuration
        datastore, base_collection, obsdate_utc, _ = get_config()

        # Pass current cache to worker
        visit_cache = session_state.get("visit_cache", {})

        thread = threading.Thread(
            target=discover_visits_worker,
            args=(state, visit_cache, datastore, base_collection, obsdate_utc),
            daemon=True,
        )
        thread.start()

        # Note: check_visit_discovery is already registered as a periodic callback
        # in on_session_created(). It will automatically check this state and
        # stop when the discovery is complete (returns False).


# --- Session initialization ---
def on_session_created():
    """Called when a new browser session starts (page load/reload)

    Reloads configuration from .env file, initializes session state,
    and starts background visit discovery. Sets up auto-refresh if enabled.

    Notes
    -----
    Registered via pn.state.onload() to run on each session start.
    """
    datastore, base_collection, obsdate_utc, refresh_interval = reload_config()
    logger.info(
        f"Session started with DATASTORE={datastore}, BASE_COLLECTION={base_collection}, "
        f"OBSDATE_UTC={obsdate_utc}, VISIT_REFRESH_INTERVAL={refresh_interval}s"
    )
    pn.state.notifications.info("Configuration reloaded from .env file", duration=3000)

    # Initialize session state and store configuration
    session_state = get_session_state()
    session_state["config"] = {
        "datastore": datastore,
        "base_collection": base_collection,
        "obsdate_utc": obsdate_utc,
        "refresh_interval": refresh_interval,
    }

    # Update sidebar info text with session-specific configuration
    config_info_text.object = (
        f"**Datastore:** {datastore}<br>"
        f"**Base collection:** {base_collection}<br>"
        f"**Observation Date (UTC):** {obsdate_utc}"
    )

    # Reset visit widget to loading state
    visit_mc.placeholder = "Loading visits..."
    visit_mc.disabled = True
    visit_mc.options = []
    visit_mc.value = []

    # Get session-specific state
    state = get_visit_discovery_state()

    # Get current cache (empty for new sessions, may have data for existing sessions)
    visit_cache = session_state.get("visit_cache", {})

    # Start initial visit discovery in background thread
    logger.info("Starting initial visit discovery for this session...")
    thread = threading.Thread(
        target=discover_visits_worker,
        args=(state, visit_cache, datastore, base_collection, obsdate_utc),
        daemon=True,
    )
    thread.start()

    # Register periodic callbacks only once at server level (thread-safe)
    # IMPORTANT: These callbacks are shared across ALL sessions. Each callback uses
    # get_session_state() which returns the state of whichever session is "current"
    # when the callback fires. In multi-session scenarios, only one session's state
    # is checked/updated per callback invocation, which is a known limitation.
    #
    # NOTE: The refresh_interval used for the periodic callback period is read only once
    # during first registration. Changes to VISIT_REFRESH_INTERVAL in .env will only
    # affect the callback period after a server restart. However, visit discovery itself
    # uses session-specific config values from get_config(), so each session can have
    # different datastore/collection/obsdate values that reload properly on browser refresh.
    global _periodic_callbacks_registered
    with _periodic_callbacks_lock:
        if not _periodic_callbacks_registered:
            # Start periodic callback to check for results (every 500ms)
            # The callback will automatically stop when it returns False
            pn.state.add_periodic_callback(check_visit_discovery, period=500)

            # If auto-refresh is enabled, set up periodic refresh
            if refresh_interval > 0:
                refresh_interval_ms = (
                    refresh_interval * 1000
                )  # Convert seconds to milliseconds
                logger.info(
                    f"Auto-refresh enabled: visit list will update every {refresh_interval} seconds"
                )
                pn.state.add_periodic_callback(
                    trigger_visit_refresh, period=refresh_interval_ms
                )

            # Mark callbacks as registered globally
            _periodic_callbacks_registered = True
            logger.info(
                "Periodic callbacks registered (server-level, shared across sessions)"
            )


# Register the callback to run on each session start
pn.state.onload(on_session_created)


# Connect callbacks
btn_load_data.on_click(load_data_callback)
btn_plot_2d.on_click(plot_2d_callback)
btn_plot_1d.on_click(plot_1d_callback)
btn_plot_1d_image.on_click(plot_1d_image_callback)
btn_reset.on_click(reset_app)
btn_clear_selection.on_click(clear_selection_callback)
obcode_mc.param.watch(on_obcode_change, "value")
fibers_mc.param.watch(on_fiber_change, "value")


# --- Layout ---
sidebar = pn.Column(
    visit_mc,
    btn_load_data,
    pn.layout.Divider(),
    spectro_cbg,
    pn.Column(btn_plot_2d),
    pn.layout.Divider(),
    pn.Column(btn_plot_1d_image),
    pn.layout.Divider(),
    # btn_clear_selection,
    obcode_mc,
    fibers_mc,
    pn.Row(btn_plot_1d, btn_clear_selection),
    pn.layout.Divider(),
    pn.Column(btn_reset),
    pn.layout.Divider(),
    status_text,
    config_info_text,
    min_width=280,
    max_width=400,
    sizing_mode="stretch_width",
)

main = pn.Column(tabs, sizing_mode="stretch_both")

pn.template.FastListTemplate(
    title="PFS Quick Look",
    sidebar=[sidebar],
    main=[main],
    sidebar_width=320,
    raw_css=[
        """
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        :root {
            --body-font: 'Inter', sans-serif !important;
        }
        """
    ],
).servable()
