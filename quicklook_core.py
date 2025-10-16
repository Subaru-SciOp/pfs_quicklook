#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PFS QuickLook core (2D/1D only, no stacking)
- Butler I/O
- 2D sky-subtracted image (optional overlay)
- 1D spectrum for selected fibers (single-visit)
"""

import copy
import os
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import numpy as np
from astropy.visualization import (
    AsinhStretch,
    LuptonAsinhStretch,
    MinMaxInterval,
    ZScaleInterval,
)
from bokeh.models import HoverTool, Legend
from bokeh.plotting import figure as bokeh_figure
from dotenv import load_dotenv
from loguru import logger
from matplotlib.figure import Figure

# --- LSST/PFS imports ---
try:
    import lsst.afw.display as afwDisplay
    import lsst.afw.image as afwImage
    from lsst.daf.butler import Butler
    from pfs.datamodel import TargetType
    from pfs.drp.stella import SpectrumSet
    from pfs.drp.stella.subtractSky1d import subtractSky1d
    from pfs.drp.stella.utils import addPfsCursor, showDetectorMap

    logger.info("LSST/PFS imports succeeded.")
except Exception as _import_err:
    afwDisplay = None
    Butler = None
    SpectrumSet = None
    subtractSky1d = None
    addPfsCursor = None
    showDetectorMap = None
    TargetType = None
    logger.error("Warning: LSST/PFS imports failed:", _import_err)
    raise _import_err


# Load configuration file
load_dotenv(verbose=True)

DATASTORE = os.environ.get("PFS_DATASTORE", "/work/datastore")
BASE_COLLECTION = os.environ.get("PFS_BASE_COLLECTION", "u/obsproc/s25a/20250520b")
OBSDATE_UTC = os.environ.get("PFS_OBSDATE_UTC", None)


# --- Config reload function ---
def reload_config():
    """Reload .env file and return updated configuration"""
    load_dotenv(override=True, verbose=True)
    datastore = os.environ.get("PFS_DATASTORE", "/work/datastore")
    base_collection = os.environ.get("PFS_BASE_COLLECTION", "u/obsproc/s25a/20250520b")
    obsdate_utc = os.environ.get("PFS_OBSDATE_UTC", None)
    logger.info(
        f"Config reloaded - DATASTORE: {datastore}, BASE_COLLECTION: {base_collection}, OBSDATE_UTC: {obsdate_utc}"
    )
    return datastore, base_collection, obsdate_utc


# --- Helpers ---
def collections_for_visit(base_collection: str, visit: int):
    """Return sub-collection for each visit"""
    return [os.path.join(base_collection, f"{visit}")]


def get_current_obsdate():
    """
    Get the current observation date (UTC) for filtering visits.
    Returns the value from OBSDATE_UTC if set, otherwise returns today's UTC date.

    Note: Uses datetime.now(timezone.utc) instead of deprecated datetime.utcnow()
    """
    if OBSDATE_UTC:
        return OBSDATE_UTC
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def make_data_id(visit: int, spectrograph: int, arm: str):
    """Butler dataId"""
    return dict(visit=visit, spectrograph=spectrograph, arm=arm)


def get_butler(datastore: str, base_collection: str, visit: int) -> "Butler":
    """Return a Butler for the collection of the specified visit"""
    if Butler is None:
        raise RuntimeError("Butler is not available. Check LSST/PFS environment setup.")
    cols = collections_for_visit(base_collection, visit)
    return Butler(datastore, collections=cols)


def load_visit_data(datastore: str, base_collection: str, visit: int):
    """
    Load visit data and create bidirectional mapping between OB Code and Fiber ID.

    Returns:
        tuple: (pfsConfig, obcode_to_fibers_dict, fiber_to_obcode_dict)
            - pfsConfig: PfsConfig object
            - obcode_to_fibers_dict: dict mapping OB codes to lists of fiber IDs
            - fiber_to_obcode_dict: dict mapping fiber IDs to OB codes
    """
    b = get_butler(datastore, base_collection, visit)
    pfsConfig = b.get("pfsConfig", visit=visit)

    # Create bidirectional mappings
    obcode_to_fibers = {}
    fiber_to_obcode = {}

    for fiber_id, ob_code in zip(pfsConfig.fiberId, pfsConfig.obCode):
        fiber_id_int = int(fiber_id)

        # OB Code -> Fiber IDs
        if ob_code not in obcode_to_fibers:
            obcode_to_fibers[ob_code] = []
        obcode_to_fibers[ob_code].append(fiber_id_int)

        # Fiber ID -> OB Code
        fiber_to_obcode[fiber_id_int] = ob_code

    # Sort fiber IDs for each OB code
    for ob_code in obcode_to_fibers:
        obcode_to_fibers[ob_code] = sorted(obcode_to_fibers[ob_code])

    logger.info(f"Loaded visit {visit}: {len(pfsConfig.fiberId)} fibers, {len(obcode_to_fibers)} OB codes")

    return pfsConfig, obcode_to_fibers, fiber_to_obcode


# --- 2D image builder ---
def build_2d_figure(
    datastore: str,
    base_collection: str,
    visit: int,
    spectrograph: int,
    arm: str,
    subtract_sky: bool = True,
    overlay: bool = False,
    fiber_ids=None,
    scale_algo: str = "zscale",
) -> Figure:
    """
    Return a Matplotlib Figure of 2D image for the specified visit.
    """
    # return None

    if afwDisplay is None:
        raise RuntimeError(
            "afwDisplay is not available. Check LSST/PFS environment setup."
        )

    if type(spectrograph) is list:
        spectrograph = spectrograph[0]  # MultiSelect -> int
        logger.warning("Only the first spectrograph is supported now.")

    if len(arm) > 1:
        arm = "r"
        logger.warning(f"Only the {arm} arm is supported now.")

    b = get_butler(datastore, base_collection, visit)
    data_id = make_data_id(visit, spectrograph, arm)

    # data retrieval
    pfs_config = b.get("pfsConfig", data_id)
    exp = b.get("calexp", data_id)
    det_map = b.get("detectorMap", data_id)

    pfs_arm = b.get("pfsArm", data_id)
    # Sky subtraction
    if subtract_sky:
        sky1d = b.get("sky1d", data_id)
        subtractSky1d(pfs_arm, pfs_config, sky1d)
        _flux = pfs_arm.flux
        pfs_arm.flux = pfs_arm.sky

    spectra = SpectrumSet.fromPfsArm(pfs_arm)
    profiles = b.get("fiberProfiles", data_id)
    traces = profiles.makeFiberTracesFromDetectorMap(det_map)
    image = spectra.makeImage(exp.getDimensions(), traces)

    del spectra

    if subtract_sky:
        pfs_arm.flux = _flux
        del _flux
    exp.image -= image

    # Display
    title = f"calexp {visit} {arm}{spectrograph}"

    fig = plt.figure(figsize=(10, 10))
    afwDisplay.setDefaultBackend("matplotlib")
    disp = afwDisplay.Display(fig)

    # 1. numpy 配列として取得
    image_array = exp.image.array.astype(np.float64)

    # 2. astropy transform を適用
    if scale_algo == "zscale":
        # transform = AsinhStretch(a=1) + ZScaleInterval()
        transform = LuptonAsinhStretch(Q=1) + ZScaleInterval()
        # transform = LuptonAsinhZscaleStretch(image_array, Q=1)
    else:
        transform = AsinhStretch(a=1) + MinMaxInterval()

    transformed_array = transform(image_array)

    # 3. 新しい Image オブジェクトを作成
    exp_disp = copy.deepcopy(exp)
    # ImageF (float) または ImageD (double) で新しい Image を作成
    new_image = afwImage.ImageF(transformed_array.astype(np.float32))
    exp_disp.setImage(new_image)

    logger.info(f"Original array dtype: {exp.image.array.dtype}")
    logger.info(f"Original array shape: {exp.image.array.shape}")
    logger.info(f"Transformed array dtype: {transformed_array.dtype}")
    logger.info(f"Transformed array shape: {transformed_array.shape}")
    logger.info(
        f"Transformed array range: [{transformed_array.min()}, {transformed_array.max()}]"
    )
    logger.info(f"Has NaN: {np.any(np.isnan(transformed_array))}")
    logger.info(f"Has Inf: {np.any(np.isinf(transformed_array))}")

    disp.scale("linear", "minmax")

    disp.mtv(exp_disp, title=title)

    # # DetectorMap overlay
    # if overlay:
    #     if fiber_ids is None:
    #         try:
    #             # Default: highlight SCIENCE & observatoryfiller_ fibers
    #             fiber_ids = [
    #                 fid
    #                 for fid, tt, ob in zip(
    #                     pfs_config.fiberId, pfs_config.targetType, pfs_config.obCode
    #                 )
    #                 if (tt == TargetType.SCIENCE) and ("observatoryfiller_" in ob)
    #             ]
    #         except Exception:
    #             fiber_ids = []
    #     showDetectorMap(
    #         disp, pfs_config, det_map, fiberIds=fiber_ids, width=4, alpha=0.5, xcen=0
    #     )

    # add cursor
    addPfsCursor(disp, det_map)

    logger.info("2D image built.")
    return fig


# --- 1D spectra builder (single visit) ---
def build_1d_figure_single_visit(
    datastore: str,
    base_collection: str,
    visit: int,
    fiber_ids,
    ylim=(-5000, 10000),
) -> Figure:
    """
    指定 visit の選択ファイバー 1D スペクトルを重ね描きする。
    """
    b = get_butler(datastore, base_collection, visit)
    pfsConfig = b.get("pfsConfig", visit=visit)
    pfsMerged = b.get("pfsMerged", visit=visit)

    fig = plt.figure(figsize=(9, 5))
    ax = fig.subplots()

    try:
        # 複数ファイバー重ね描き
        for fid in fiber_ids:
            sel = pfsMerged.select(pfsConfig, fiberId=fid)
            wav = sel.wavelength[0]
            flx = sel.flux[0]
            var = sel.variance[0]
            err = (var**0.5) if var is not None else None

            ax.plot(wav, flx, lw=1, alpha=0.85, label=f"fid={fid}")
            if err is not None:
                ax.fill_between(wav, flx - err, flx + err, color="C1", alpha=0.25)

        ax.legend(loc="upper left", fontsize=9)
        ax.set_title(f"visit={visit}")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Flux (electrons/nm)")
        ax.axhline(0, ls="--", c="k", lw=1)
        if ylim:
            ax.set_ylim(*ylim)
    except Exception as e:
        plt.close(fig)
        fig = Figure(figsize=(8, 3))
        ax = fig.subplots()
        ax.text(0.02, 0.5, f"1D build failed:\n{e}", va="center")
        ax.axis("off")

    return fig


# --- 1D spectra builder using Bokeh (single visit) ---
def build_1d_bokeh_figure_single_visit(
    datastore: str,
    base_collection: str,
    visit: int,
    fiber_ids,
    ylim=(-5000, 10000),
):
    """
    指定 visit の選択ファイバー 1D スペクトルを Bokeh で重ね描きする。
    Returns a Bokeh figure object.
    """
    from bokeh.models import Band, ColumnDataSource
    from bokeh.palettes import Category10_10

    b = get_butler(datastore, base_collection, visit)
    pfsConfig = b.get("pfsConfig", visit=visit)
    pfsMerged = b.get("pfsMerged", visit=visit)

    # Create Bokeh figure
    # 1920x1080画面でサイドバー(320px)を引いた残り ~1500pxに最適化
    p = bokeh_figure(
        width=1400,
        height=500,
        title=f"1D Spectra - visit={visit}",
        x_axis_label="Wavelength (nm)",
        y_axis_label="Flux (electrons/nm)",
        tools="pan,wheel_zoom,box_zoom,undo,redo,reset,save",
        active_drag="box_zoom",  # デフォルトツールをbox zoomに設定
        sizing_mode="scale_width",
    )

    # Add hover tool
    hover = HoverTool(
        tooltips=[
            ("Fiber ID", "@fiber_id"),
            ("Object ID", "@obj_id"),
            ("OB Code", "@ob_code"),
            ("Wavelength", "@wavelength{0.2f} nm"),
            ("Flux", "@flux{0.2f}"),
        ]
    )
    p.add_tools(hover)

    try:
        # 複数ファイバー重ね描き
        colors = Category10_10

        # 各fiberのレンダラーをグループ化して管理
        legend_items = []

        for i, fid in enumerate(fiber_ids):
            sel = pfsMerged.select(pfsConfig, fiberId=fid)
            wav = sel.wavelength[0]
            flx = sel.flux[0]
            var = sel.variance[0]
            err = (var**0.5) if var is not None else None

            # pfsConfigから該当fiberの情報を取得
            pfs_sel = pfsConfig.select(fiberId=fid)
            obj_id = pfs_sel.objId[0]
            ob_code = pfs_sel.obCode[0]

            color = colors[i % len(colors)]

            # 初期状態: 最初のfid以外はmute
            is_muted = i != 0

            # ColumnDataSourceを使用してメタデータを含める
            source = ColumnDataSource(
                data=dict(
                    wavelength=wav,
                    flux=flx,
                    fiber_id=[fid] * len(wav),
                    obj_id=[obj_id] * len(wav),
                    ob_code=[ob_code] * len(wav),
                )
            )

            # Plot line
            line = p.line(
                "wavelength",
                "flux",
                source=source,
                line_width=2,
                alpha=0.85,
                color=color,
                name=f"fid={fid}",
                muted_alpha=0.1,  # ミュート時の透明度
                muted_color=color,
            )
            # 初期状態でミュート設定
            line.muted = is_muted

            # レンダラーのリスト（line + band）
            renderers = [line]

            # Add error band if available
            if err is not None:
                source = ColumnDataSource(
                    data=dict(
                        base=wav,
                        lower=flx - err,
                        upper=flx + err,
                    )
                )
                band = Band(
                    base="base",
                    lower="lower",
                    upper="upper",
                    source=source,
                    level="underlay",
                    fill_alpha=0.25,
                    fill_color=color,
                )
                band_renderer = p.add_layout(band)
                # bandもmuteする
                if hasattr(band_renderer, "muted"):
                    band_renderer.muted = is_muted

            # legend itemに追加
            from bokeh.models import LegendItem

            legend_items.append(LegendItem(label=f"fid={fid}", renderers=[line]))

        # Add zero line
        p.line(
            [wav.min(), wav.max()],
            [0, 0],
            line_dash="dashed",
            color="black",
            line_width=1,
        )

        # Configure legend - 手動でlegendを作成

        legend = Legend(items=legend_items, location="top_left", click_policy="mute")
        legend.label_text_font_size = "12pt"
        p.add_layout(legend, "right")

        # Set y-axis limits if provided
        if ylim:
            p.y_range.start = ylim[0]
            p.y_range.end = ylim[1]

    except Exception as e:
        # Create error figure
        p = bokeh_figure(width=800, height=300, title="Error")
        p.text(
            x=[0.5],
            y=[0.5],
            text=[f"1D build failed:\n{e}"],
            text_align="center",
            text_baseline="middle",
        )
        logger.error(f"Failed to build 1D Bokeh figure: {e}")

    return p
