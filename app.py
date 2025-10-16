#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PFS QuickLook Panel App (2D/1Dのみ)
- Sidebar: visit / arm / spectrograph / fibers / options
- Tabs: 2D / 1D / Log
- Run/Reset/Export(PNG)
"""

import numpy as np
import panel as pn
from loguru import logger

from quicklook_core import (
    BASE_COLLECTION,
    DATASTORE,
    OBSDATE_UTC,
    build_1d_bokeh_figure_single_visit,
    build_2d_figure,
    get_current_obsdate,
    load_visit_data,
    reload_config,
)

pn.extension(
    "ipywidgets",
    notifications=True,
)


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
    value=[1],
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
    # solid=False,
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

status_text = pn.pane.Markdown("**Ready**", sizing_mode="stretch_width")

# --- Output panes ---
pane_2d = pn.pane.Matplotlib(height=700, sizing_mode="scale_width")
pane_1d = pn.pane.Bokeh(height=550, sizing_mode="scale_width")
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
        pfsConfig, obcode_to_fibers = load_visit_data(DATASTORE, BASE_COLLECTION, visit)

        # Update session cache
        pn.state.cache["visit_data"] = {
            "loaded": True,
            "visit": visit,
            "pfsConfig": pfsConfig,
            "obcode_to_fibers": obcode_to_fibers,
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


def plot_2d_callback(event=None):
    """Create 2D plot"""
    if not pn.state.cache["visit_data"]["loaded"]:
        pn.state.notifications.warning("Load data first.")
        return

    if len(arm_rbg.value) > 1:
        pn.state.notifications.warning(
            f"{arm_rbg.value} selected, only r arm will be used for now."
        )
    if type(spectro_cbg.value) is list and len(spectro_cbg.value) > 1:
        pn.state.notifications.warning(
            f"{spectro_cbg.value} selected, only the first spectrograph will be used for now."
        )

    visit = pn.state.cache["visit_data"]["visit"]
    spectro = spectro_cbg.value
    arm = arm_rbg.value
    fibers = list(fibers_mc.value) if fibers_mc.value else None

    subtract_sky = subtract_sky_chk.value
    overlay = overlay_chk.value
    scale_algo = scale_sel.value

    if overlay:
        pn.state.notifications.warning("DetectorMap overlay is not supported yet.")

    try:
        status_text.object = "**Creating 2D plot...**"
        fig2d = build_2d_figure(
            datastore=DATASTORE,
            base_collection=BASE_COLLECTION,
            visit=visit,
            spectrograph=spectro,
            arm=arm,
            subtract_sky=subtract_sky,
            overlay=overlay,
            fiber_ids=fibers if overlay else None,
            scale_algo=scale_algo,
        )
        pane_2d.object = fig2d
        tabs.active = 0  # Switch to 2D tab
        status_text.object = f"**2D plot created for visit {visit}**"
        pn.state.notifications.success("2D plot created")

        fiber_info = f"{len(fibers)} selected" if fibers else "none"
        log_md.object = f"""**2D plot created**
- visit: {visit}
- arm/spectrograph: {arm}/{spectro}
- fibers: {fiber_info}
- subtract_sky: {subtract_sky}, overlay: {overlay}, scale: {scale_algo}
"""
    except Exception as e:
        pane_2d.object = None
        pn.state.notifications.error(f"Failed to show 2D image: {e}")
        logger.error(f"Failed to show 2D image: {e}")
        status_text.object = "**Error creating 2D plot**"


def plot_1d_callback(event=None):
    """Create 1D plot"""
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
        p_fig1d = build_1d_bokeh_figure_single_visit(
            datastore=DATASTORE,
            base_collection=BASE_COLLECTION,
            visit=visit,
            fiber_ids=fibers,
        )
        pane_1d.object = p_fig1d
        tabs.active = 1  # Switch to 1D tab
        status_text.object = f"**1D plot created for visit {visit}**"
        pn.state.notifications.success("1D plot created")

        log_md.object = f"""**1D plot created**
- visit: {visit}
- fibers: {len(fibers)} selected ({fibers[:10]}{'...' if len(fibers) > 10 else ''})
"""
    except Exception as e:
        pane_1d.object = None
        pn.state.notifications.error(f"Failed to show 1D spectra: {e}")
        logger.error(f"Failed to show 1D spectra: {e}")
        status_text.object = "**Error creating 1D plot**"


def reset_app(event=None):
    """Reset application state"""
    pane_2d.object = None
    pane_1d.object = None
    log_md.object = "**Reset.**"
    status_text.object = "**Ready**"

    # Clear cache
    pn.state.cache["visit_data"] = {
        "loaded": False,
        "visit": None,
        "pfsConfig": None,
        "obcode_to_fibers": {},
    }

    # Disable plot buttons
    btn_plot_2d.disabled = True
    btn_plot_1d.disabled = True

    # Clear OB Code options
    obcode_mc.options = []
    obcode_mc.value = []


# Connect callbacks
btn_load_data.on_click(load_data_callback)
btn_plot_2d.on_click(plot_2d_callback)
btn_plot_1d.on_click(plot_1d_callback)
btn_reset.on_click(reset_app)
obcode_mc.param.watch(on_obcode_change, "value")


# --- Layout ---
sidebar = pn.Column(
    # "## Instrument Settings",
    "### Arm",
    arm_rbg,
    "### Spectrograph",
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
    # pn.layout.Divider(),  # hline
    # #
    # "## Options",
    # subtract_sky_chk,
    # overlay_chk,
    # scale_sel,
    #
    pn.layout.Divider(),  # hline
    #
    # "## Plot",
    pn.Row(btn_plot_2d, btn_plot_1d, btn_reset),
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


# Bootstrap options (dummy)
visit_mc.options = [126714, 126715, 126716, 126717]
visit_mc.value = [126714]
