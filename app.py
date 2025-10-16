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

visit_ms = pn.widgets.MultiSelect(name="Visit", options=[], size=8)
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

btn_run = pn.widgets.Button(name="Run", button_type="primary")
btn_reset = pn.widgets.Button(name="Reset")

# --- Output panes ---
pane_2d = pn.pane.Matplotlib(height=700, sizing_mode="scale_width")
pane_1d = pn.pane.Bokeh(height=550, sizing_mode="scale_width")
log_md = pn.pane.Markdown("**Ready.**")

tabs = pn.Tabs(("2D", pane_2d), ("1D", pane_1d), ("Log", log_md))


# --- Callbacks ---
def run_app(event=None):

    if len(arm_rbg.value) > 1:
        pn.state.notifications.warning(
            f"{arm_rbg.value} selected, only r arm will be used for now."
        )
    if type(spectro_cbg.value) is list and len(spectro_cbg.value) > 1:
        pn.state.notifications.warning(
            f"{spectro_cbg.value} selected, only the first spectrograph will be used for now."
        )
    if not visit_ms.value:
        pn.state.notifications.warning("Select at least one visit.")
        logger.warning("No visit selected.")
        return
    if not fibers_mc.value:
        pn.state.notifications.warning("Select at least one fiber ID.")
        logger.warning("No fiber ID selected.")
        return

    visit = list(visit_ms.value)[0]
    spectro = spectro_cbg.value
    arm = arm_rbg.value
    fibers = list(fibers_mc.value)

    subtract_sky = subtract_sky_chk.value
    overlay = overlay_chk.value
    scale_algo = scale_sel.value

    if overlay:
        pn.state.notifications.warning("DetectorMap overlay is not supported yet.")

    # 2D
    try:
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
    except Exception as e:
        pane_2d.object = None
        pn.state.notifications.error(f"Failed to show 2D image: {e}")
        logger.error(f"Failed to show 2D image: {e}")

    # 1D
    try:
        p_fig1d = build_1d_bokeh_figure_single_visit(
            datastore=DATASTORE,
            base_collection=BASE_COLLECTION,
            visit=visit,
            fiber_ids=fibers,
        )
        pane_1d.object = p_fig1d
    except Exception as e:
        pane_1d.object = None
        pn.state.notifications.error(f"Failed to show 1D spectra: {e}")
        logger.error(f"Failed to show 1D spectra: {e}")

    log_md.object = f"""**Run completed**
- visit: {visit}
- arm/spectrograph: {arm}/{spectro}
- fibers: {fibers}
- subtract_sky: {subtract_sky}, overlay: {overlay}, scale: {scale_algo}
"""


def reset_app(event=None):
    pane_2d.object = None
    pane_1d.object = None
    log_md.object = "**Reset.**"


btn_run.on_click(run_app)
btn_reset.on_click(reset_app)


# --- Layout ---
sidebar = pn.Column(
    "## Instrument Settings",
    "### Arm",
    arm_rbg,
    "### Spectrograph",
    spectro_cbg,
    #
    pn.layout.Divider(),  # hline
    #
    "## Visits & Fiber IDs",
    visit_ms,
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
    pn.Row(btn_run, btn_reset),
    # btn_export,
    # sizing_mode="stretch_width",
    # width=320,  # sidebar width
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
visit_ms.options = [126714, 126715, 126716, 126717]
visit_ms.value = [126714]
# fibers_ms.options = [141, 412, 418, 437]
fibers_mc.value = [141, 412, 418, 437]
