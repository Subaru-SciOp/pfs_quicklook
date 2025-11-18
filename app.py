#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading

import numpy as np
import panel as pn
from bokeh.models.widgets.tables import NumberFormatter
from loguru import logger

from quicklook_core import (
    ARM_NAMES,
    BASE_COLLECTION,
    DATASTORE,
    OBSDATE_UTC,
    VISIT_REFRESH_INTERVAL,
    build_1d_bokeh_figure_single_visit,
    build_1d_spectra_as_image,
    build_2d_arrays_multi_spectrograph,
    check_pfsmerged_exists,
    create_holoviews_from_arrays,
    create_pfsconfig_dataframe,
    discover_visits,
    get_butler_cached,
    load_visit_data,
    reload_config,
)
from version import __version__

pn.extension("tabulator", notifications=True)

# Log application version on module load
logger.info(f"PFS QuickLook version: {__version__}")


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
            "periodic_callbacks": {"discovery": None, "refresh": None},
            "config": {  # Session-specific configuration
                "datastore": None,
                "base_collection": None,
                "obsdate_utc": None,
                "refresh_interval": None,
            },
        }

    return ctx.app_state


def _stop_periodic_callbacks(state):
    """Stop any Panel periodic callbacks stored in session state."""

    callbacks = state.get("periodic_callbacks", {})
    for name, handle in callbacks.items():
        if handle is None:
            continue
        try:
            handle.stop()
            logger.debug(f"Stopped periodic callback '{name}' for session")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(f"Failed to stop periodic callback '{name}': {exc}")
        finally:
            callbacks[name] = None


def _ensure_session_cleanup_registered():
    """Register a one-time cleanup hook per Bokeh session to stop callbacks."""

    ctx = pn.state.curdoc.session_context
    if getattr(ctx, "_pfs_callbacks_cleanup_registered", False):
        return

    def _cleanup(session_context):
        app_state = getattr(session_context, "app_state", None)
        if not app_state:
            return
        _stop_periodic_callbacks(app_state)

    pn.state.curdoc.on_session_destroyed(_cleanup)
    ctx._pfs_callbacks_cleanup_registered = True


def show_notification_on_next_tick(message, notification_type="info", duration=3000):
    """Show notification on next Bokeh event loop tick

    Uses Bokeh's add_next_tick_callback to ensure notification is displayed
    after widget updates have been sent to the browser, avoiding race conditions
    where notifications are dismissed prematurely due to concurrent widget rendering.

    This is the proper solution for notification timing issues, as it uses Bokeh's
    internal event loop timing rather than arbitrary delays.

    Parameters
    ----------
    message : str
        Notification message to display
    notification_type : str, optional
        Type of notification: "success", "warning", "error", or "info" (default: "info")
    duration : int, optional
        Display duration in milliseconds (default: 3000)

    Notes
    -----
    This function must be called within a Bokeh server context where pn.state.curdoc
    is available. It will have no effect in standalone contexts.
    """
    def _show_notification():
        if notification_type == "success":
            pn.state.notifications.success(message, duration=duration)
        elif notification_type == "warning":
            pn.state.notifications.warning(message, duration=duration)
        elif notification_type == "error":
            pn.state.notifications.error(message, duration=duration)
        else:
            pn.state.notifications.info(message, duration=duration)

    # Schedule notification for next tick
    if pn.state.curdoc is not None:
        pn.state.curdoc.add_next_tick_callback(_show_notification)
    else:
        # Fallback for non-server contexts (shouldn't happen in production)
        _show_notification()


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
    sizing_mode="stretch_width",
)

subtract_sky_chk = pn.widgets.Checkbox(name="Sky subtraction", value=True)
detmap_overlay_switch = pn.widgets.Switch(
    name="Detector Map Overlay",
    value=True,
    sizing_mode="stretch_width",
    align=("start", "center"),  # Horizontal: left, Vertical: center
)
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

# Help/Documentation buttons
btn_github = pn.widgets.Button(
    name="GitHub Repository",
    button_type="primary",
    icon="brand-github",
    sizing_mode="stretch_width",
)
btn_user_guide = pn.widgets.Button(
    name="User Guide on GitHub",
    button_type="primary",
    icon="book-2",
    sizing_mode="stretch_width",
)

# JavaScript callbacks to open links in new tabs
btn_github.js_on_click(
    code="""
window.open('https://github.com/Subaru-SciOp/pfs_quicklook', '_blank');
"""
)
btn_user_guide.js_on_click(
    code="""
window.open('https://github.com/Subaru-SciOp/pfs_quicklook/blob/main/docs/user-guide/index.md', '_blank');
"""
)

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
        pn.state.notifications.warning("Select at least one visit.", duration=3000)
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

        # Check if pfsMerged exists before loading visit data
        pfsmerged_exists = check_pfsmerged_exists(datastore, base_collection, visit)

        if not pfsmerged_exists:
            pn.state.notifications.warning(
                f"Visit {visit} found, but data reduction may still be in progress.",
                duration=6000,
            )
            logger.warning(
                f"Visit {visit}: Data reduction appears incomplete (pfsMerged not found)"
            )

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
            "pfsmerged_exists": pfsmerged_exists,
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
        # Note: Explicitly list all columns to ensure fiberId is visible with selectable="checkbox"
        logger.info(f"DataFrame columns before Tabulator: {df_pfsconfig.columns.tolist()}")

        tabulator = pn.widgets.Tabulator(
            df_pfsconfig,
            pagination="local",
            page_size=250,
            sizing_mode="stretch_width",
            height=700,
            show_index=False,
            disabled=True,  # Read-only table
            selectable="checkbox",
            layout="fit_columns",  # Changed from fit_data_table to fit_columns
            frozen_columns=["fiberId"],  # Freeze fiberId column to ensure visibility
            widths={
                "fiberId": 90,
                "spectrograph": 60,
                "objId": 200,
                "obCode": 300,
            },
            text_align={"fiberId": "center", "spectrograph": "center", "catId": "right"},
            formatters={
                "catId": NumberFormatter(format="0"),
            },
            titles={
                "fiberId": "Fiber ID",
                "spectrograph": "Sp",
                "objId": "Object ID",
                "obCode": "OB Code",
                "ra": "RA",
                "dec": "Dec",
                "catId": "Catalog ID",
                "targetType": "Target Type",
                "fiberStatus": "Fiber Status",
                "proposalId": "Proposal ID",
            },
            header_filters={
                "fiberId": {"type": "input", "func": "like", "placeholder": "Filter"},
                "spectrograph": {"type": "input", "func": "like", "placeholder": "Filter"},
                "objId": {"type": "input", "func": "like", "placeholder": "Filter"},
                "obCode": {"type": "input", "func": "like", "placeholder": "Filter"},
                "catId": {"type": "input", "func": "like", "placeholder": "Filter"},
                "targetType": {"type": "input", "func": "like", "placeholder": "Filter"},
                "fiberStatus": {"type": "input", "func": "like", "placeholder": "Filter"},
                "proposalId": {"type": "input", "func": "like", "placeholder": "Filter"},
            },
        )

        # Apply styling
        tabulator.style.apply(style_science_bad_fibers, axis=1)

        # Add selection change callback for tabulator
        def on_tabulator_selection_change(event):
            """Update Fiber ID and OB Code widgets when tabulator selection changes

            Parameters
            ----------
            event : panel.io.state.Event
                Panel widget selection change event
            """
            state = get_session_state()
            if state.get("programmatic_update", False):
                return

            # Get selected row indices
            selected_indices = event.new
            if not selected_indices:
                # Clear fiber and OB code selection if no rows selected
                state["programmatic_update"] = True
                fibers_mc.value = []
                obcode_mc.value = []
                state["programmatic_update"] = False
                logger.debug("Tabulator selection cleared, widgets cleared")
                return

            # Extract fiberIds from selected rows
            selected_fiber_ids = df_pfsconfig.iloc[selected_indices]["fiberId"].tolist()

            # Get OB codes for selected fiber IDs
            fiber_to_obcode = state["visit_data"]["fiber_to_obcode"]
            obcodes = set()
            for fiber_id in selected_fiber_ids:
                obcode = fiber_to_obcode.get(fiber_id)
                if obcode:
                    obcodes.add(obcode)

            # Update both Fiber ID and OB Code widgets
            state["programmatic_update"] = True
            fibers_mc.value = selected_fiber_ids
            obcode_mc.value = sorted(obcodes)
            state["programmatic_update"] = False
            logger.info(f"Tabulator selection changed: {len(selected_fiber_ids)} fibers, {len(obcodes)} OB codes selected")

        tabulator.param.watch(on_tabulator_selection_change, "selection")

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

        # Switch to Target Info tab to show loaded data
        tabs.active = 0

        # Show notification on next tick to avoid race condition with widget/tab updates
        show_notification_on_next_tick(
            f"Visit {visit} loaded successfully",
            notification_type="success",
            duration=2000
        )

        log_md.object = f"""**Data loaded**
- visit: {visit}
- total fibers: {num_fibers}
- OB codes: {num_obcodes}
"""

    except Exception as e:
        pn.state.notifications.error(f"Failed to load visit data: {e}", duration=5000)
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
        # Enable plot buttons only if data was loaded successfully AND pfsMerged exists
        state = get_session_state()
        if state["visit_data"]["loaded"]:
            pfsmerged_available = state["visit_data"].get("pfsmerged_exists", False)
            if pfsmerged_available:
                # Enable all plot buttons only when pfsMerged is available
                btn_plot_2d.disabled = False
                btn_plot_1d.disabled = False
                btn_plot_1d_image.disabled = False
            else:
                # Keep all plot buttons disabled when pfsMerged is not available
                btn_plot_2d.disabled = True
                btn_plot_1d.disabled = True
                btn_plot_1d_image.disabled = True


def on_obcode_change(event):
    """Update Fiber ID selection and tabulator based on OB Code selection

    Callback for OB Code widget value changes. Automatically selects
    all fiber IDs associated with the selected OB codes and updates
    tabulator selection to match.

    Parameters
    ----------
    event : panel.io.state.Event
        Panel widget value change event

    Notes
    -----
    Implements bidirectional synchronization between OB Code, Fiber ID, and Tabulator.
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

    # Remove duplicates and sort
    unique_fiber_ids = sorted(set(fiber_ids))

    # Update fiber selection
    state["programmatic_update"] = True
    fibers_mc.value = unique_fiber_ids

    # Update tabulator selection to match fiber selection
    # pane_pfsconfig.objects = [header_pane, tabulator]
    # So objects[1] is the tabulator widget
    if len(pane_pfsconfig.objects) == 2:
        tabulator = pane_pfsconfig.objects[1]
        if hasattr(tabulator, 'value') and tabulator.value is not None:
            # Find row indices that match selected fiber IDs
            df = tabulator.value
            if 'fiberId' in df.columns:
                selected_indices = df.index[df['fiberId'].isin(unique_fiber_ids)].tolist()
                tabulator.selection = selected_indices
                logger.debug(f"Updated tabulator selection: {len(selected_indices)} rows")

    state["programmatic_update"] = False

    logger.info(
        f"Selected {len(fiber_ids)} fibers from {len(selected_obcodes)} OB codes"
    )


def on_fiber_change(event):
    """Update OB Code selection and tabulator based on Fiber ID selection

    Callback for Fiber ID widget value changes. Automatically selects
    all OB codes associated with the selected fiber IDs and updates
    tabulator selection to match.

    Parameters
    ----------
    event : panel.io.state.Event
        Panel widget value change event

    Notes
    -----
    Implements bidirectional synchronization between Fiber ID, OB Code, and Tabulator.
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

    # Update tabulator selection to match fiber selection
    # pane_pfsconfig.objects = [header_pane, tabulator]
    # So objects[1] is the tabulator widget
    if len(pane_pfsconfig.objects) == 2:
        tabulator = pane_pfsconfig.objects[1]
        if hasattr(tabulator, 'value') and tabulator.value is not None:
            # Find row indices that match selected fiber IDs
            df = tabulator.value
            if 'fiberId' in df.columns:
                selected_indices = df.index[df['fiberId'].isin(selected_fibers)].tolist()
                tabulator.selection = selected_indices
                logger.debug(f"Updated tabulator selection: {len(selected_indices)} rows")

    state["programmatic_update"] = False

    logger.info(f"Selected {len(obcodes)} OB codes from {len(selected_fibers)} fibers")


def clear_selection_callback(event=None):
    """Clear OB Code, Fiber ID, and Tabulator selections

    Callback for Clear Selection button. Clears all three widget
    selections simultaneously (OB Code, Fiber ID, and Tabulator).

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

    # Clear all selections
    state["programmatic_update"] = True
    obcode_mc.value = []
    fibers_mc.value = []

    # Clear tabulator selection
    # pane_pfsconfig.objects = [header_pane, tabulator]
    # So objects[1] is the tabulator widget
    if len(pane_pfsconfig.objects) == 2:
        tabulator = pane_pfsconfig.objects[1]
        if hasattr(tabulator, 'selection'):
            tabulator.selection = []
            logger.debug("Cleared tabulator selection")

    state["programmatic_update"] = False

    logger.info("Cleared OB Code, Fiber ID, and Tabulator selections")
    pn.state.notifications.info("Selection cleared", duration=2000)


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
        pn.state.notifications.warning("Load data first.", duration=3000)
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
        pn.state.notifications.warning(
            "Select at least one spectrograph.", duration=3000
        )
        toggle_buttons(disabled=False, include_load=True)
        return
    # Always attempt to load all 4 arms
    all_arms = ["b", "r", "n", "m"]
    fibers = fibers_mc.value if fibers_mc.value else None

    subtract_sky = subtract_sky_chk.value
    enable_detmap_overlay = detmap_overlay_switch.value
    scale_algo = scale_sel.value

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

        logger.info(
            f"Building arrays for {len(spectros)} spectrographs × {len(all_arms)} arms with unified parallelism"
        )
        spectrograph_panels = {}

        try:
            array_results_by_spec = build_2d_arrays_multi_spectrograph(
                datastore=datastore,
                base_collection=base_collection,
                visit=visit,
                spectrographs=spectros,
                arms=all_arms,
                subtract_sky=subtract_sky,
                enable_detmap_overlay=enable_detmap_overlay,
                fiber_ids=fibers if enable_detmap_overlay else None,
                scale_algo=scale_algo,
                n_jobs=16,
                pfsConfig_preloaded=pfs_config_shared,
                butler_cache=butler_cache,
            )
        except Exception as e:
            logger.error(f"Failed to build 2D arrays: {e}")
            raise

        logger.info("Arrays built, now creating HoloViews images in main thread")

        for spectro in spectros:
            array_results = array_results_by_spec.get(spectro, [])
            if array_results is not None:
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
                error = "No array results available"

            logger.info(
                f"Processing SM{spectro}: arm_results type={type(arm_results)}, error={error}"
            )

            if arm_results is not None and error is None:
                # Verify arm_results is a list
                if not isinstance(arm_results, list):
                    logger.error(
                        f"SM{spectro}: arm_results is not a list, got {type(arm_results)}: {arm_results}"
                    )
                    pn.state.notifications.error(
                        f"Invalid result type for SM{spectro}", duration=5000
                    )
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
                        f"Error processing arms for SM{spectro}: {e}", duration=5000
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
                        f"Failed to create plots for SM{spectro}: {error}",
                        duration=5000,
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
            f"2D plot created for {len(spectrograph_panels)} spectrograph(s)",
            duration=2000,
        )

        fiber_info = f"{len(fibers)} selected" if fibers else "none"
        log_md.object = f"""**2D plot created**
- visit: {visit}
- spectrographs: {', '.join([f'SM{s}' for s in sorted(spectros)])}
- fibers: {fiber_info}
- subtract_sky: {subtract_sky}, detmap_overlay: {enable_detmap_overlay}, scale: {scale_algo}
"""
    except Exception as e:
        error_pane = pn.pane.Markdown(f"**Error:** {e}")
        pane_2d.objects = [error_pane]
        pn.state.notifications.error(f"Failed to show 2D image: {e}", duration=5000)
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
        pn.state.notifications.warning("Load data first.", duration=3000)
        return

    if not fibers_mc.value:
        pn.state.notifications.warning("Select at least one fiber ID.", duration=3000)
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
        pn.state.notifications.success("1D plot created", duration=2000)

        log_md.object = f"""**1D plot created**
- visit: {visit}
- fibers: {len(fibers)} selected ({fibers[:10]}{'...' if len(fibers) > 10 else ''})
"""
    except Exception as e:
        error_pane = pn.pane.Markdown(f"**Error:** {e}")
        pane_1d.objects = [error_pane]
        pn.state.notifications.error(f"Failed to show 1D spectra: {e}", duration=5000)
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
        pn.state.notifications.warning("Load data first.", duration=3000)
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
        pn.state.notifications.success("1D spectra image created", duration=2000)

        fiber_info = f"{len(fibers)} selected" if fibers else "all fibers"
        log_md.object = f"""**1D spectra image created**
- visit: {visit}
- fibers: {fiber_info}
- scale: {scale_algo}
"""
    except Exception as e:
        error_pane = pn.pane.Markdown(f"**Error:** {e}")
        pane_1d_image.objects = [error_pane]
        pn.state.notifications.error(
            f"Failed to create 1D spectra image: {e}", duration=5000
        )
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

        # Show notification on next tick to avoid race condition with widget updates
        if old_count == 0:
            show_notification_on_next_tick(
                f"Found {new_count} visits",
                notification_type="success",
                duration=2000
            )
            logger.info(f"Initial visit discovery: {new_count} visits")
        elif new_count > old_count:
            show_notification_on_next_tick(
                f"Found {new_count - old_count} new visit(s) (total: {new_count})",
                notification_type="success",
                duration=2000
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

        # Show notification on next tick to avoid race condition with widget updates
        show_notification_on_next_tick(
            "No visits found for the specified date",
            notification_type="warning",
            duration=3000
        )

        state.update({"status": None, "updated_cache": None})
        return False

    elif status == "error":
        visit_mc.placeholder = "Error loading visits"
        visit_mc.disabled = False

        # Show notification on next tick to avoid race condition with widget updates
        show_notification_on_next_tick(
            f"Failed to discover visits: {state['error']}",
            notification_type="error",
            duration=5000
        )

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

    # Show notification on next tick to avoid race condition with widget updates
    show_notification_on_next_tick(
        "Configuration reloaded from .env file",
        notification_type="info",
        duration=3000
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

    # Register per-session periodic callbacks so every browser session remains independent
    _ensure_session_cleanup_registered()
    _stop_periodic_callbacks(session_state)

    callbacks = session_state.get("periodic_callbacks", {})
    callbacks["discovery"] = pn.state.add_periodic_callback(
        check_visit_discovery, period=500
    )
    logger.info("Registered visit discovery callback for this session")

    if refresh_interval > 0:
        refresh_interval_ms = refresh_interval * 1000
        callbacks["refresh"] = pn.state.add_periodic_callback(
            trigger_visit_refresh, period=refresh_interval_ms
        )
        logger.info(
            f"Auto-refresh enabled for this session: visit list every {refresh_interval} seconds"
        )
    else:
        callbacks["refresh"] = None


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
    detmap_overlay_switch,
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
    pn.layout.Divider(),
    btn_user_guide,
    btn_github,
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
