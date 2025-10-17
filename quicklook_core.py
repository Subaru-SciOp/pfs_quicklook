#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PFS QuickLook core (2D/1D only, no stacking)
- Butler I/O
- 2D sky-subtracted image (optional overlay)
- 1D spectrum for selected fibers (single-visit)
"""

import os
import sys
from datetime import datetime, timezone

import holoviews as hv
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
from joblib import Parallel, delayed
from loguru import logger

# Configure logger with INFO level
logger.remove()  # Remove default handler
logger.add(sys.stdout, level="INFO")

# Enable Bokeh backend for HoloViews
hv.extension("bokeh")

# --- LSST/PFS imports ---
try:
    from lsst.daf.butler import Butler
    from pfs.drp.stella import SpectrumSet
    from pfs.drp.stella.subtractSky1d import subtractSky1d

    logger.info("LSST/PFS imports succeeded.")
except Exception as _import_err:
    Butler = None
    SpectrumSet = None
    subtractSky1d = None
    logger.error("Warning: LSST/PFS imports failed:", _import_err)
    raise _import_err


# Load configuration file
load_dotenv(verbose=True)

DATASTORE = os.environ.get("PFS_DATASTORE", "/work/datastore")
BASE_COLLECTION = os.environ.get("PFS_BASE_COLLECTION", "u/obsproc/s25a/20250520b")
OBSDATE_UTC = os.environ.get("PFS_OBSDATE_UTC", None)
VISIT_REFRESH_INTERVAL = int(os.environ.get("PFS_VISIT_REFRESH_INTERVAL", "300"))  # seconds, 0 = disabled


# --- Config reload function ---
def reload_config():
    """Reload .env file and return updated configuration"""
    load_dotenv(override=True, verbose=True)
    datastore = os.environ.get("PFS_DATASTORE", "/work/datastore")
    base_collection = os.environ.get("PFS_BASE_COLLECTION", "u/obsproc/s25a/20250520b")
    obsdate_utc = os.environ.get("PFS_OBSDATE_UTC", None)
    refresh_interval = int(os.environ.get("PFS_VISIT_REFRESH_INTERVAL", "300"))
    logger.info(
        f"Config reloaded - DATASTORE: {datastore}, BASE_COLLECTION: {base_collection}, "
        f"OBSDATE_UTC: {obsdate_utc}, VISIT_REFRESH_INTERVAL: {refresh_interval}s"
    )
    return datastore, base_collection, obsdate_utc, refresh_interval


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
    return Butler(datastore, collections=cols, writeable=False)


def discover_visits(
    datastore: str, base_collection: str, obsdate_utc: str | None = None
):
    """
    Discover available visits from the Butler datastore for a given observation date.

    Parameters
    ----------
    datastore : str
        Path to Butler datastore
    base_collection : str
        Base collection name (e.g., "u/obsproc/s25a/20250520b")
    obsdate_utc : str, optional
        Observation date in "YYYY-MM-DD" format. If None, uses get_current_obsdate()

    Returns
    -------
    list of int
        Sorted list of available visit numbers
    """
    if Butler is None:
        raise RuntimeError("Butler is not available. Check LSST/PFS environment setup.")

    if obsdate_utc is None:
        obsdate_utc = get_current_obsdate()

    logger.info(f"Discovering visits for date: {obsdate_utc}")

    try:
        # Create Butler with wildcard collection pattern to search all subcollections
        # The actual data is stored in base_collection/visit subdirectories
        butler = Butler(datastore, writeable=False)

        # Query for pfsConfig datasets to find available visits
        # collection name is like "u/obsproc/s25a/20250520b/123456" for onsite processing
        collections = butler.registry.queryCollections(
            os.path.join(base_collection, "??????")
        )

        # Extract visit numbers and convert to integers
        visits = [int(coll.split("/")[-1]) for coll in collections]

        # If obsdate_utc is not specified or empty, return all visits
        if not obsdate_utc:
            visit_list = sorted(visits)
            logger.info(f"Found {len(visit_list)} visits under {base_collection} (no date filter)")
            return visit_list

        # Filter by observation date if specified using parallel processing
        def check_visit_date(visit):
            """Check if visit matches the observation date"""
            try:
                b = get_butler(datastore, base_collection, visit)
                obstime = b.get(
                    "pfsConfig", visit=visit, spectrograph=1, arm="b"
                ).obstime
                logger.debug(f"Visit {visit} observation date: {obstime}")
                if obstime.startswith(obsdate_utc):
                    logger.debug(f"Visit {visit} date {obstime} matches {obsdate_utc}")
                    return visit
                return None
            except Exception as e:
                logger.warning(f"Failed to check visit {visit}: {e}")
                return None

        # Parallel processing with max 16 cores
        logger.info(f"Filtering visits by observation date: {obsdate_utc}")
        results = Parallel(n_jobs=min(16, len(visits)), verbose=1)(
            delayed(check_visit_date)(visit) for visit in visits
        )

        # Filter out None values
        visits_use = [v for v in results if v is not None]

        # Sort and return as list
        visit_list = sorted(visits_use)
        logger.info(
            f"Found {len(visit_list)} visits out of {len(visits)} visits under {base_collection} (filtered by {obsdate_utc})"
        )

        return visit_list

    except Exception as e:
        logger.error(f"Error discovering visits: {e}")
        logger.warning("Falling back to empty visit list")
        return []


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

    logger.info(
        f"Loaded visit {visit}: {len(pfsConfig.fiberId)} fibers, {len(obcode_to_fibers)} OB codes"
    )

    return pfsConfig, obcode_to_fibers, fiber_to_obcode


# --- 2D image builder ---


def _build_single_2d_array(
    datastore: str,
    base_collection: str,
    visit: int,
    spectrograph: int,
    arm: str,
    subtract_sky: bool = True,
    overlay: bool = False,
    fiber_ids=None,
    scale_algo: str = "zscale",
):
    """
    Build transformed numpy array for a single arm/spectrograph combination.
    This is a helper function for parallel processing.

    Returns only pickle-able objects (numpy arrays, not HoloViews objects).

    Returns
    -------
    tuple
        (arm, transformed_array, metadata_dict, error_msg) where error_msg is None on success
    """
    ARM_NAMES = {"b": "Blue", "r": "Red", "n": "NIR", "m": "Medium-Red"}

    try:
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

        # Get numpy array
        image_array = exp.image.array.astype(np.float64)

        # Apply astropy transform
        if scale_algo == "zscale":
            transform = LuptonAsinhStretch(Q=1) + ZScaleInterval()
        else:
            transform = AsinhStretch(a=1) + MinMaxInterval()

        transformed_array = transform(image_array)

        logger.info(
            f"Arm {arm}, SM{spectrograph}: Transformed array range: [{transformed_array.min()}, {transformed_array.max()}]"
        )

        # Store metadata for HoloViews creation later
        height, width = transformed_array.shape
        logger.info(
            f"Arm {arm}, SM{spectrograph}: Array shape = {transformed_array.shape} -> height={height}, width={width}"
        )

        metadata = {
            "title": f"{ARM_NAMES.get(arm, arm)} ({arm}{spectrograph})",
            "width": width,
            "height": height,
            "spectrograph": spectrograph,
        }

        return (arm, transformed_array, metadata, None)

    except Exception as e:
        error_msg = str(e)
        logger.error(
            f"Failed to build 2D array for arm {arm}, SM{spectrograph}: {error_msg}"
        )
        return (arm, None, None, error_msg)


def build_2d_arrays_multi_arm(
    datastore: str,
    base_collection: str,
    visit: int,
    spectrograph: int,
    arms: list,
    subtract_sky: bool = True,
    overlay: bool = False,
    fiber_ids=None,
    scale_algo: str = "zscale",
    n_jobs: int = -1,
):
    """
    Build numpy arrays (pickle-able) for multiple arms.
    This function is safe to use in parallel processing.

    Parameters
    ----------
    arms : list of str
        List of arms to display, e.g., ['b', 'r', 'n'] or ['b', 'm', 'n']
    n_jobs : int, optional
        Number of parallel jobs. -1 means use all available CPUs (default: -1)

    Returns
    -------
    list of tuples
        List of (arm, transformed_array, metadata, error_msg) tuples, one per arm
    """
    n_arms = len(arms)
    if n_arms == 0:
        raise ValueError("At least one arm must be specified")

    logger.info(
        f"Building 2D arrays for SM{spectrograph} with {n_arms} arm(s) using parallel processing (n_jobs={n_jobs})"
    )

    # Parallel processing: build transformed arrays (pickle-able)
    array_results = Parallel(n_jobs=n_jobs, verbose=10)(
        delayed(_build_single_2d_array)(
            datastore,
            base_collection,
            visit,
            spectrograph,
            arm,
            subtract_sky,
            overlay,
            fiber_ids,
            scale_algo,
        )
        for arm in arms
    )

    logger.info(f"Arrays built for SM{spectrograph}")
    return array_results


def create_holoviews_from_arrays(array_results, spectrograph):
    """
    Create HoloViews images from numpy arrays.
    Must be called in main thread (HoloViews objects are not pickle-able).

    Parameters
    ----------
    array_results : list
        List of (arm, transformed_array, metadata, error_msg) tuples
    spectrograph : int
        Spectrograph number

    Returns
    -------
    list of tuples
        List of (arm, hv.Image, error_msg) tuples
    """
    logger.info(f"Creating HoloViews images for SM{spectrograph} in main thread")

    # Create HoloViews objects in main thread (not pickle-able, can't be parallelized)
    hv_results = []
    for arm, transformed_array, metadata, error_msg in array_results:
        if transformed_array is not None and metadata is not None and error_msg is None:
            try:
                # Create HoloViews Image
                height, width = metadata["height"], metadata["width"]

                # Debug: Log actual image dimensions
                logger.info(
                    f"Image dimensions for {arm}: array shape={transformed_array.shape}, width={width}, height={height}"
                )

                # Flip array vertically so (0,0) is at lower-left corner (astronomical convention)
                # HoloViews by default has (0,0) at upper-left, so we flip the array
                flipped_array = np.flipud(transformed_array)

                # Set bounds: (left, bottom, right, top)
                # With flipped array, (0,0) will be at lower-left
                # IMPORTANT: bounds should match the actual data dimensions
                img = hv.Image(
                    flipped_array,
                    bounds=(0, 0, width, height),
                    kdims=["x", "y"],
                    vdims=["intensity"],
                )

                # Astropy transform already applied, use full range (0-100%) with linear scaling
                vmin = transformed_array.min()
                vmax = transformed_array.max()

                # Create custom HoverTool with formatted coordinates
                from bokeh.models import HoverTool

                hover = HoverTool(
                    tooltips=[
                        (
                            "X",
                            "$x{0.0}",
                        ),  # Use $x for cursor position, not @x (data column)
                        ("Y", "$y{0.0}"),  # Use $y for cursor position
                        (
                            "Intensity",
                            "@image{0.2f}",
                        ),  # Use @image for pixel value in Image glyph
                    ]
                )

                # Configure display options to match matplotlib appearance
                # Note: Using Image directly without rasterize for proper hover functionality
                # Calculate aspect ratio from actual data dimensions
                aspect_ratio = width / height
                logger.info(
                    f"Image aspect ratio for {arm}: {aspect_ratio:.3f} (width={width}, height={height})"
                )

                # Set frame dimensions to maintain aspect ratio
                # For landscape images (width > height), fix width and adjust height
                # For portrait images (height > width), fix height and adjust width
                if aspect_ratio >= 1.0:
                    # Landscape or square: fix width
                    plot_width = 512
                    plot_height = int(512 / aspect_ratio)
                else:
                    # Portrait: fix height
                    plot_height = 512
                    plot_width = int(512 * aspect_ratio)

                logger.info(f"Plot dimensions for {arm}: {plot_width}x{plot_height}")

                img.opts(
                    cmap="cividis",
                    clim=(vmin, vmax),  # Linear scaling of full range
                    colorbar=True,
                    tools=[
                        hover,
                        "box_zoom",
                        "wheel_zoom",
                        "pan",
                        "undo",
                        "redo",
                        "reset",
                        "save",
                    ],
                    active_tools=["box_zoom"],
                    default_tools=[],  # Disable default tools to prevent duplicate tooltips
                    frame_width=plot_width,
                    frame_height=plot_height,
                    data_aspect=1.0,  # 1:1 pixel aspect ratio
                    title=metadata["title"],
                    xlabel="X (pixels)",
                    ylabel="Y (pixels)",
                    toolbar="above",
                    axiswise=True,  # Disable axis linking between plots
                    framewise=True,  # Each frame is independent
                )

                hv_results.append((arm, img, None))
                logger.info(f"Created HoloViews image for arm {arm}, SM{spectrograph}")

            except Exception as e:
                error_msg = str(e)
                logger.error(
                    f"Failed to create HoloViews image for arm {arm}, SM{spectrograph}: {error_msg}"
                )
                hv_results.append((arm, None, error_msg))
        else:
            # Pass through the error from array generation
            hv_results.append((arm, None, error_msg))

    logger.info(f"HoloViews images created for spectrograph {spectrograph}")
    return hv_results


def build_2d_figure_multi_arm(
    datastore: str,
    base_collection: str,
    visit: int,
    spectrograph: int,
    arms: list,
    subtract_sky: bool = True,
    overlay: bool = False,
    fiber_ids=None,
    scale_algo: str = "zscale",
    n_jobs: int = -1,
):
    """
    Build HoloViews images with multiple arms (b, r, n, m) for a single spectrograph.
    This is a convenience wrapper that combines array building and HoloViews creation.

    Parameters
    ----------
    arms : list of str
        List of arms to display, e.g., ['b', 'r', 'n'] or ['b', 'm', 'n']
    n_jobs : int, optional
        Number of parallel jobs. -1 means use all available CPUs (default: -1)

    Returns
    -------
    list of tuples
        List of (arm, hv.Image, error_msg) tuples, one per arm
    """
    # Build arrays in parallel
    array_results = build_2d_arrays_multi_arm(
        datastore,
        base_collection,
        visit,
        spectrograph,
        arms,
        subtract_sky,
        overlay,
        fiber_ids,
        scale_algo,
        n_jobs,
    )

    # Create HoloViews objects in main thread
    hv_results = create_holoviews_from_arrays(array_results, spectrograph)

    return hv_results


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
        p = bokeh_figure(width=512, height=300, title="Error")
        p.text(
            x=[0.5],
            y=[0.5],
            text=[f"1D build failed:\n{e}"],
            text_align="center",
            text_baseline="middle",
        )
        logger.error(f"Failed to build 1D Bokeh figure: {e}")

    return p
