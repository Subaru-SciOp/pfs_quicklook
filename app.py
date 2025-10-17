#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PFS QuickLook Panel App (2D/1D)
- Sidebar: visit / arm / spectrograph / fibers / options
- Tabs: 2D / 1D / Log
- Run/Reset/Export(PNG)
"""

import sys

import numpy as np
import panel as pn
from joblib import Parallel, delayed
from loguru import logger

from quicklook_core import (
    BASE_COLLECTION,
    DATASTORE,
    OBSDATE_UTC,
    build_1d_bokeh_figure_single_visit,
    build_2d_arrays_multi_arm,
    create_holoviews_from_arrays,
    discover_visits,
    get_current_obsdate,
    load_visit_data,
    reload_config,
)

pn.extension(notifications=True)


# Configure logger with INFO level
logger.remove()  # Remove default handler
logger.add(sys.stdout, level="INFO")


# --- Session initialization ---
def on_session_created():
    """Called when a new browser session starts (page load/reload)"""
    datastore, base_collection, obsdate_utc = reload_config()
    logger.info(
        f"Session started with DATASTORE={datastore}, BASE_COLLECTION={base_collection}, OBSDATE_UTC={obsdate_utc}"
    )
    pn.state.notifications.info("Configuration loaded from .env file")

    # Initialize session cache
    if "visit_data" not in pn.state.cache:
        pn.state.cache["visit_data"] = {
            "loaded": False,
            "visit": None,
            "pfsConfig": None,
            "obcode_to_fibers": {},
            "fiber_to_obcode": {},
        }
    if "programmatic_update" not in pn.state.cache:
        pn.state.cache["programmatic_update"] = False


# Register the callback to run on each session start
pn.state.onload(on_session_created)


# --- Widgets ---
arm_rbg = pn.widgets.RadioButtonGroup(
    name="Arm",
    options=["brn", "bmn"],
    value="brn",
    button_type="light",
)
spectro_cbg = pn.widgets.CheckButtonGroup(
    name="Spectrograph",
    options=[1, 2, 3, 4],
    value=[1, 2, 3, 4],
    button_type="light",
)

visit_mc = pn.widgets.MultiChoice(
    name="Visit",
    options=[],
)

obcode_mc = pn.widgets.MultiChoice(
    name="OB Code",
    options=[],
    option_limit=20,
    search_option_limit=10,
)

fibers_mc = pn.widgets.MultiChoice(
    name="FiberId",
    options=np.arange(1, 2395, dtype=int).tolist(),
    option_limit=20,
    search_option_limit=10,
)

subtract_sky_chk = pn.widgets.Checkbox(name="Sky subtraction", value=True)
overlay_chk = pn.widgets.Checkbox(name="DetectorMap overlay", value=False)
scale_sel = pn.widgets.Select(
    name="Scale", options=["zscale", "minmax"], value="zscale"
)

btn_load_data = pn.widgets.Button(name="Load Data", button_type="primary")
btn_plot_2d = pn.widgets.Button(name="Plot 2D", button_type="primary", disabled=True)
btn_plot_1d = pn.widgets.Button(name="Plot 1D", button_type="primary", disabled=True)
btn_reset = pn.widgets.Button(name="Reset")

status_text = pn.pane.Markdown("**Ready**", sizing_mode="stretch_width", height=60)

# --- Output panes ---
# pane_2d can hold either a Matplotlib pane or a Tabs object (for multiple spectrographs)
pane_2d = pn.Column(sizing_mode="scale_width")
# pane_1d holds Bokeh figures
pane_1d = pn.Column(height=550, sizing_mode="scale_width")
log_md = pn.pane.Markdown("**Ready.**")

tabs = pn.Tabs(("2D", pane_2d), ("1D", pane_1d), ("Log", log_md))


# --- Callbacks ---
def load_data_callback(event=None):
    """Load visit data and update OB Code options"""
    if not visit_mc.value:
        pn.state.notifications.warning("Select at least one visit.")
        logger.warning("No visit selected.")
        return

    visit = list(visit_mc.value)[0]

    try:
        status_text.object = f"**Loading visit {visit}...**"
        pfsConfig, obcode_to_fibers, fiber_to_obcode = load_visit_data(
            DATASTORE, BASE_COLLECTION, visit
        )

        # Update session cache
        pn.state.cache["visit_data"] = {
            "loaded": True,
            "visit": visit,
            "pfsConfig": pfsConfig,
            "obcode_to_fibers": obcode_to_fibers,
            "fiber_to_obcode": fiber_to_obcode,
        }

        # Update OB Code options
        pn.state.cache["programmatic_update"] = True
        obcode_mc.options = sorted(obcode_to_fibers.keys())
        obcode_mc.value = []  # Clear selection
        pn.state.cache["programmatic_update"] = False

        # Enable plot buttons
        btn_plot_2d.disabled = False
        btn_plot_1d.disabled = False

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
        btn_plot_2d.disabled = True
        btn_plot_1d.disabled = True


def on_obcode_change(event):
    """Update Fiber ID selection based on OB Code selection"""
    if pn.state.cache.get("programmatic_update", False):
        return

    if not pn.state.cache["visit_data"]["loaded"]:
        return

    selected_obcodes = obcode_mc.value
    if not selected_obcodes:
        return

    # Get fiber IDs for selected OB codes
    obcode_to_fibers = pn.state.cache["visit_data"]["obcode_to_fibers"]
    fiber_ids = []
    for obcode in selected_obcodes:
        fiber_ids.extend(obcode_to_fibers.get(obcode, []))

    # Update fiber selection
    pn.state.cache["programmatic_update"] = True
    fibers_mc.value = sorted(set(fiber_ids))
    pn.state.cache["programmatic_update"] = False

    logger.info(
        f"Selected {len(fiber_ids)} fibers from {len(selected_obcodes)} OB codes"
    )


def on_fiber_change(event):
    """Update OB Code selection based on Fiber ID selection"""
    if pn.state.cache.get("programmatic_update", False):
        return

    if not pn.state.cache["visit_data"]["loaded"]:
        return

    selected_fibers = fibers_mc.value
    if not selected_fibers:
        return

    # Get OB codes for selected fiber IDs
    fiber_to_obcode = pn.state.cache["visit_data"]["fiber_to_obcode"]
    obcodes = set()
    for fiber_id in selected_fibers:
        obcode = fiber_to_obcode.get(fiber_id)
        if obcode:
            obcodes.add(obcode)

    # Update OB code selection
    pn.state.cache["programmatic_update"] = True
    obcode_mc.value = sorted(obcodes)
    pn.state.cache["programmatic_update"] = False

    logger.info(f"Selected {len(obcodes)} OB codes from {len(selected_fibers)} fibers")


def plot_2d_callback(event=None):
    """Create 2D plot with support for multiple arms and spectrographs"""
    if not pn.state.cache["visit_data"]["loaded"]:
        pn.state.notifications.warning("Load data first.")
        return

    visit = pn.state.cache["visit_data"]["visit"]
    spectros = (
        spectro_cbg.value
        if isinstance(spectro_cbg.value, list)
        else [spectro_cbg.value]
    )
    arms = list(arm_rbg.value)
    fibers = list(fibers_mc.value) if fibers_mc.value else None

    subtract_sky = subtract_sky_chk.value
    overlay = overlay_chk.value
    scale_algo = scale_sel.value

    if overlay:
        pn.state.notifications.warning("DetectorMap overlay is not supported yet.")

    try:
        n_total = len(spectros) * len(arms)
        status_text.object = f"**Creating {n_total} 2D plot(s)...**"
        logger.info(
            f"Building 2D plots: {len(spectros)} spectrographs × {len(arms)} arms = {n_total} total images"
        )

        # Process spectrographs in parallel (only array generation)
        # Two-level parallelization: spectrographs in parallel, arms within each spectrograph in parallel
        spectrograph_panels = {}
        ARM_NAMES = {"b": "Blue", "r": "Red", "n": "NIR", "m": "Medium-Red"}

        def build_arrays_for_spectrograph(spectro):
            """Build arrays for a single spectrograph (pickle-able)"""
            logger.info(f"Building 2D arrays for SM{spectro} with arms {arms}")
            try:
                array_results = build_2d_arrays_multi_arm(
                    datastore=DATASTORE,
                    base_collection=BASE_COLLECTION,
                    visit=visit,
                    spectrograph=spectro,
                    arms=arms,
                    subtract_sky=subtract_sky,
                    overlay=overlay,
                    fiber_ids=fibers if overlay else None,
                    scale_algo=scale_algo,
                    n_jobs=-1,  # Use all available CPUs for arms within each spectrograph
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

                # Create a Row layout with all arm HoloViews images
                arm_panes = []
                try:
                    for arm, hv_img, arm_error in arm_results:
                        if hv_img is not None and arm_error is None:
                            arm_panes.append(
                                pn.pane.HoloViews(
                                    hv_img,
                                    backend="bokeh",
                                    # Don't use sizing_mode to preserve aspect ratio set in HoloViews
                                )
                            )
                        else:
                            # Create error placeholder
                            arm_name = ARM_NAMES.get(arm, arm)

                            # Check if it's a "not found" error (data doesn't exist)
                            is_not_found = (
                                arm_error and "could not be found" in arm_error
                            )

                            if is_not_found:
                                # More concise message for missing data
                                error_text = f"""
### {arm_name} ({arm}{spectro})

**Data Not Available**

This arm/spectrograph combination does not have data for this visit.

_Error: Dataset not found in collection_
"""
                                logger.info(
                                    f"SM{spectro} {arm_name}: Data not available (expected for some configurations)"
                                )
                            else:
                                # Full error for other types of errors
                                error_text = f"""
### {arm_name} ({arm}{spectro})

**Error Loading Data**

```
{arm_error}
```
"""
                                logger.warning(f"SM{spectro} {arm_name}: {arm_error}")

                            arm_panes.append(
                                pn.pane.Markdown(
                                    error_text,
                                    sizing_mode="stretch_width",
                                    styles={
                                        "background": "#f0f0f0",
                                        "padding": "20px",
                                        "border": "1px solid #ddd",
                                    },
                                )
                            )
                except Exception as e:
                    logger.error(f"Error iterating arm_results for SM{spectro}: {e}")
                    pn.state.notifications.error(
                        f"Error processing arms for SM{spectro}: {e}"
                    )
                    continue

                if arm_panes:
                    # Arrange arms horizontally
                    spectrograph_panels[spectro] = pn.Row(
                        *arm_panes, sizing_mode="stretch_width"
                    )
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

        # Clear existing content and add new tabs
        pane_2d.clear()
        pane_2d.append(pn.Tabs(*tab_items))

        tabs.active = 0  # Switch to 2D tab
        status_text.object = f"**2D plot created for visit {visit}**"
        pn.state.notifications.success(
            f"2D plot created for {len(spectrograph_panels)} spectrograph(s)"
        )

        fiber_info = f"{len(fibers)} selected" if fibers else "none"
        log_md.object = f"""**2D plot created**
- visit: {visit}
- arms: {', '.join(arms)}
- spectrographs: {', '.join([f'SM{s}' for s in sorted(spectros)])}
- fibers: {fiber_info}
- subtract_sky: {subtract_sky}, overlay: {overlay}, scale: {scale_algo}
"""
    except Exception as e:
        pane_2d.clear()
        pn.state.notifications.error(f"Failed to show 2D image: {e}")
        logger.error(f"Failed to show 2D image: {e}")
        status_text.object = "**Error creating 2D plot**"


def plot_1d_callback(event=None):
    """Create 1D plot using Bokeh"""
    if not pn.state.cache["visit_data"]["loaded"]:
        pn.state.notifications.warning("Load data first.")
        return

    if not fibers_mc.value:
        pn.state.notifications.warning("Select at least one fiber ID.")
        logger.warning("No fiber ID selected.")
        return

    visit = pn.state.cache["visit_data"]["visit"]
    fibers = list(fibers_mc.value)

    try:
        status_text.object = "**Creating 1D plot...**"

        # Clear existing content
        pane_1d.clear()

        # Use Bokeh for rendering
        p_fig1d = build_1d_bokeh_figure_single_visit(
            datastore=DATASTORE,
            base_collection=BASE_COLLECTION,
            visit=visit,
            fiber_ids=fibers,
        )
        pane_1d.append(pn.pane.Bokeh(p_fig1d, sizing_mode="scale_width"))

        tabs.active = 1  # Switch to 1D tab
        status_text.object = f"**1D plot created for visit {visit}**"
        pn.state.notifications.success("1D plot created")

        log_md.object = f"""**1D plot created**
- visit: {visit}
- fibers: {len(fibers)} selected ({fibers[:10]}{'...' if len(fibers) > 10 else ''})
"""
    except Exception as e:
        pane_1d.clear()
        pn.state.notifications.error(f"Failed to show 1D spectra: {e}")
        logger.error(f"Failed to show 1D spectra: {e}")
        status_text.object = "**Error creating 1D plot**"


def reset_app(event=None):
    """Reset application state"""
    pane_2d.clear()
    pane_1d.clear()  # Clear Column instead of setting object to None
    log_md.object = "**Reset.**"
    status_text.object = "**Ready**"

    # Clear cache
    pn.state.cache["visit_data"] = {
        "loaded": False,
        "visit": None,
        "pfsConfig": None,
        "obcode_to_fibers": {},
        "fiber_to_obcode": {},
    }

    # Disable plot buttons
    btn_plot_2d.disabled = True
    btn_plot_1d.disabled = True

    # Clear OB Code and Fiber ID selections
    obcode_mc.options = []
    obcode_mc.value = []
    fibers_mc.value = []


# Connect callbacks
btn_load_data.on_click(load_data_callback)
btn_plot_2d.on_click(plot_2d_callback)
btn_plot_1d.on_click(plot_1d_callback)
btn_reset.on_click(reset_app)
obcode_mc.param.watch(on_obcode_change, "value")
fibers_mc.param.watch(on_fiber_change, "value")


# --- Layout ---
sidebar = pn.Column(
    # "## Instrument Settings",
    "#### Arm",
    arm_rbg,
    "#### Spectrograph",
    spectro_cbg,
    #
    pn.layout.Divider(),  # hline
    #
    # "## Data Selection",
    # "### Visit",
    visit_mc,
    btn_load_data,
    status_text,
    #
    pn.layout.Divider(),  # hline
    #
    # "## Fiber Selection",
    # "### OB Code",
    obcode_mc,
    # "### Fiber ID",
    fibers_mc,
    #
    pn.layout.Divider(),  # hline
    #
    # "## Plot",
    pn.Row(btn_plot_2d, btn_plot_1d, btn_reset),
    #
    f"**Base collection:** {BASE_COLLECTION}<br>"
    f"**Datastore:** {DATASTORE}<br>"
    f"**Observation Date (UTC):** {OBSDATE_UTC}",
    #
    min_width=280,  # 最小幅
    max_width=400,  # 最大幅
    sizing_mode="stretch_width",  # レスポンシブ
)

main = pn.Column(tabs, sizing_mode="stretch_both")

pn.template.FastListTemplate(
    title="PFS Quick Look",
    sidebar=[sidebar],
    main=[main],
    # header_background="#0B3D91",
    sidebar_width=320,  # 1920px幅の画面でサイドバー固定
).servable()


# Discover available visits from Butler
logger.info(
    f"Discovering visits for observation date: {OBSDATE_UTC or get_current_obsdate()}"
)
discovered_visits = discover_visits(
    DATASTORE,
    BASE_COLLECTION,
    OBSDATE_UTC,
)

if discovered_visits:
    visit_mc.options = discovered_visits
    # visit_mc.value = [discovered_visits[0]]  # Select first visit by default
    visit_mc.value = []
    logger.info(f"Loaded {len(discovered_visits)} visits")
else:
    logger.warning("No visits discovered. Visit list will be empty.")
    visit_mc.options = []
    visit_mc.value = []
