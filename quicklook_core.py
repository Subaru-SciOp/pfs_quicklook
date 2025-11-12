#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
from holoviews.operation.datashader import rasterize
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
    logger.error(f"LSST/PFS imports failed: {_import_err}")
    raise _import_err


# Load configuration file
load_dotenv(verbose=True)

DATASTORE = os.environ.get("PFS_DATASTORE", "/work/datastore")
BASE_COLLECTION = os.environ.get("PFS_BASE_COLLECTION", "u/obsproc/s25a/20250520b")
OBSDATE_UTC = os.environ.get(
    "PFS_OBSDATE_UTC", datetime.now(timezone.utc).strftime("%Y-%m-%d")
)
VISIT_REFRESH_INTERVAL = int(
    os.environ.get("PFS_VISIT_REFRESH_INTERVAL", "300")
)  # seconds, 0 = disabled

# Constants
ARM_NAMES = {"b": "Blue", "r": "Red", "n": "NIR", "m": "Medium-Red"}


# --- Config reload function ---
def reload_config():
    """Reload .env file and return updated configuration

    Returns
    -------
    datastore : str
        Path to Butler datastore
    base_collection : str
        Base collection name
    obsdate_utc : str
        Observation date in UTC (YYYY-MM-DD format)
    refresh_interval : int
        Auto-refresh interval in seconds

    Notes
    -----
    Called on each session start to allow runtime configuration changes
    without restarting the application.
    """
    load_dotenv(override=True, verbose=True)
    datastore = os.environ.get("PFS_DATASTORE", "/work/datastore")
    base_collection = os.environ.get("PFS_BASE_COLLECTION", "u/obsproc/s25a/20250520b")
    obsdate_utc = os.environ.get(
        "PFS_OBSDATE_UTC", datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    refresh_interval = int(os.environ.get("PFS_VISIT_REFRESH_INTERVAL", "300"))
    logger.info(
        f"Config reloaded - DATASTORE: {datastore}, BASE_COLLECTION: {base_collection}, "
        f"OBSDATE_UTC: {obsdate_utc}, VISIT_REFRESH_INTERVAL: {refresh_interval}s"
    )
    return datastore, base_collection, obsdate_utc, refresh_interval


# --- Helpers ---
def make_data_id(visit: int, spectrograph: int, arm: str):
    """Create Butler dataId dictionary

    Parameters
    ----------
    visit : int
        Visit number
    spectrograph : int
        Spectrograph number (1-4)
    arm : str
        Arm name ('b', 'r', 'n', or 'm')

    Returns
    -------
    dict
        Butler dataId with keys: visit, spectrograph, arm
    """
    return dict(visit=visit, spectrograph=spectrograph, arm=arm)


def get_transform(scale_algo: str):
    """Get astropy transform based on scaling algorithm

    Parameters
    ----------
    scale_algo : str
        Scaling algorithm: 'zscale' or 'minmax'

    Returns
    -------
    astropy transform
        Combined stretch and interval transform
    """
    return (
        LuptonAsinhStretch(Q=1) + ZScaleInterval()
        if scale_algo == "zscale"
        else AsinhStretch(a=1) + MinMaxInterval()
    )


def get_butler(datastore: str, base_collection: str, visit: int) -> "Butler":
    """Return a Butler for the collection of the specified visit

    Parameters
    ----------
    datastore : str
        Path to Butler datastore
    base_collection : str
        Base collection name
    visit : int
        Visit number

    Returns
    -------
    Butler
        Butler instance for the specified visit collection
    """
    collection = os.path.join(base_collection, str(visit))
    return Butler(datastore, collections=[collection], writeable=False)


def get_butler_cached(
    datastore: str, base_collection: str, visit: int, butler_cache: dict | None = None
) -> "Butler":
    """Return a Butler with optional session-level caching

    This function wraps get_butler() with caching support to avoid repeated
    Butler instance creation for the same visit. Butler instances are read-only
    and thread-safe, making them safe to cache and reuse.

    Parameters
    ----------
    datastore : str
        Path to Butler datastore
    base_collection : str
        Base collection name
    visit : int
        Visit number
    butler_cache : dict, optional
        Dictionary for caching Butler instances. Key format: (datastore, collection, visit).
        If None, no caching is performed (falls back to get_butler()).
        Default is None.

    Returns
    -------
    Butler
        Butler instance for the specified visit collection (cached or newly created)

    Notes
    -----
    Performance impact:
    - Saves ~0.1-0.2s per Butler creation
    - With 16 arms, saves ~1.6-3.2s total if cache is used
    - Butler instances are read-only and safe to share across arms/spectrographs
    """
    if butler_cache is None:
        # No caching requested, use standard get_butler
        return get_butler(datastore, base_collection, visit)

    # Create cache key
    cache_key = (datastore, base_collection, visit)

    # Check if Butler is already cached
    if cache_key in butler_cache:
        logger.debug(
            f"Using cached Butler for visit {visit} (datastore={datastore}, collection={base_collection})"
        )
        return butler_cache[cache_key]

    # Butler not in cache, create new one
    logger.debug(
        f"Creating new Butler for visit {visit} (datastore={datastore}, collection={base_collection})"
    )
    butler = get_butler(datastore, base_collection, visit)

    # Store in cache for future use
    butler_cache[cache_key] = butler

    return butler


def discover_visits(
    datastore: str,
    base_collection: str,
    obsdate_utc: str | None = None,
    cached_visits: dict | None = None,
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
        Observation date in "YYYY-MM-DD" format. If None, uses current UTC date.
    cached_visits : dict, optional
        Dictionary of {visit_id: obsdate_utc} for previously validated visits.
        If provided, only new visits will be checked against the date filter.

    Returns
    -------
    list of int
        Sorted list of available visit numbers
    dict
        Updated cache dictionary with {visit_id: obsdate_utc} for all validated visits
    """
    if obsdate_utc is None:
        obsdate_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if cached_visits is None:
        cached_visits = {}

    logger.info(
        f"Discovering visits for date: {obsdate_utc} (cached: {len(cached_visits)})"
    )

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
        all_visits = [int(coll.split("/")[-1]) for coll in collections]

        # Separate cached and new visits
        cached_valid_visits = []
        new_visits = []

        for visit in all_visits:
            if visit in cached_visits:
                # Check if cached date matches current filter
                if cached_visits[visit] == obsdate_utc:
                    cached_valid_visits.append(visit)
                    logger.debug(f"Visit {visit} found in cache (date matches)")
                else:
                    # Date filter changed, need to re-check
                    new_visits.append(visit)
                    logger.debug(
                        f"Visit {visit} in cache but date changed ({cached_visits[visit]} -> {obsdate_utc})"
                    )
            else:
                new_visits.append(visit)

        logger.info(
            f"Total visits: {len(all_visits)}, cached: {len(cached_valid_visits)}, new: {len(new_visits)}"
        )

        # Filter new visits by observation date by parsing directory names
        def check_visit_date(visit):
            """Check if visit matches the observation date by parsing directory structure

            The data is stored like {datastore}/{base_collection}/{visit}/YYYYMMDDThhmmssZ
            We can extract the date directly from the timestamp directory name instead
            of calling Butler, which is much faster (~100x speedup).
            """
            try:
                visit_path = os.path.join(datastore, base_collection, str(visit))

                # List subdirectories (timestamp directories like "20250521T111558Z")
                if not os.path.exists(visit_path):
                    logger.debug(f"Visit path does not exist: {visit_path}")
                    return (visit, None)

                # List subdirectories matching timestamp pattern (YYYYMMDDThhmmssZ)
                # Filter upfront to only include valid timestamp directories
                subdirs = [
                    d
                    for d in os.listdir(visit_path)
                    if (
                        os.path.isdir(os.path.join(visit_path, d))
                        and not d.startswith(".")  # Exclude hidden directories
                        and not d.endswith(".dmQa")  # Skip QA directories
                        and len(d) >= 15  # Full format is YYYYMMDDThhmmssZ (16 chars)
                        and d[8] == "T"  # T at position 8
                        and d[:8].isdigit()  # YYYYMMDD is numeric
                        and d[9:15].isdigit()  # hhmmss is numeric
                    )
                ]

                if not subdirs:
                    logger.debug(f"No timestamp directories found in {visit_path}")
                    return (visit, None)

                # Sort subdirectories to ensure deterministic selection
                # Use the most recent timestamp (last alphabetically)
                subdirs.sort()
                timestamp_dir = subdirs[-1]

                # Parse date from timestamp (format: YYYYMMDDThhmmssZ)
                # Extract YYYY-MM-DD from YYYYMMDDThhmmssZ
                # Use direct string slicing for maximum performance (~100x faster than datetime.strptime)
                date_str = timestamp_dir[:8]  # YYYYMMDD
                # Convert to YYYY-MM-DD format
                obstime = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                logger.debug(
                    f"Visit {visit} observation date: {obstime} (from {timestamp_dir})"
                )

                if obstime == obsdate_utc:
                    logger.debug(f"Visit {visit} date {obstime} matches {obsdate_utc}")
                    return (visit, obsdate_utc)

                return (visit, None)
            except Exception as e:
                logger.warning(f"Failed to check visit {visit}: {e}")
                return (visit, None)

        # Only check new visits if there are any
        new_valid_visits = []
        updated_cache = cached_visits.copy()

        if new_visits:
            # Parallel processing with max 32 cores
            logger.info(
                f"Checking {len(new_visits)} new visits for date: {obsdate_utc}"
            )
            results = Parallel(n_jobs=min(32, len(new_visits)), verbose=1)(
                delayed(check_visit_date)(visit) for visit in new_visits
            )

            # Update cache and collect valid visits
            for visit, date in results:
                if date is not None:
                    new_valid_visits.append(visit)
                    updated_cache[visit] = date
                else:
                    # Visit doesn't match date filter, remove from cache if present
                    updated_cache.pop(visit, None)

            logger.info(
                f"Found {len(new_valid_visits)} new valid visits out of {len(new_visits)} checked"
            )
        else:
            logger.info("No new visits to check")

        # Combine cached and new valid visits
        all_valid_visits = cached_valid_visits + new_valid_visits

        # Sort and return as list
        visit_list = sorted(all_valid_visits)
        logger.info(
            f"Total valid visits: {len(visit_list)} (cached: {len(cached_valid_visits)}, new: {len(new_valid_visits)})"
        )

        return visit_list, updated_cache

    except Exception as e:
        logger.error(f"Error discovering visits: {e}")
        logger.warning("Falling back to empty visit list")
        return [], cached_visits


def load_visit_data(datastore: str, base_collection: str, visit: int):
    """Load visit data and create bidirectional mapping between OB Code and Fiber ID

    Parameters
    ----------
    datastore : str
        Path to Butler datastore
    base_collection : str
        Base collection name
    visit : int
        Visit number

    Returns
    -------
    pfsConfig : PfsConfig
        PFS configuration object
    obcode_to_fibers_dict : dict
        Mapping from OB codes to lists of fiber IDs
    fiber_to_obcode_dict : dict
        Mapping from fiber IDs to OB codes
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
    pfsConfig_preloaded=None,
    butler_cache=None,
):
    """Build transformed numpy array for a single arm/spectrograph combination

    Helper function for parallel processing. Returns only pickle-able objects
    (numpy arrays, not HoloViews objects).

    Parameters
    ----------
    datastore : str
        Path to Butler datastore
    base_collection : str
        Base collection name
    visit : int
        Visit number
    spectrograph : int
        Spectrograph number (1-4)
    arm : str
        Arm name ('b', 'r', 'n', or 'm')
    subtract_sky : bool, optional
        Whether to subtract sky background. Default is True.
    overlay : bool, optional
        Whether to overlay detector map (not implemented). Default is False.
    fiber_ids : list of int, optional
        Fiber IDs for overlay (not implemented). Default is None.
    scale_algo : str, optional
        Scaling algorithm ('zscale' or 'minmax'). Default is 'zscale'.
    pfsConfig_preloaded : pfs.datamodel.PfsConfig, optional
        Pre-loaded pfsConfig object to avoid redundant Butler.get() calls.
        If provided, skips loading pfsConfig from Butler (saves ~0.177s per arm).
        Default is None (load from Butler).
    butler_cache : dict, optional
        Dictionary for caching Butler instances. Passed to get_butler_cached().
        If provided, enables Butler instance reuse (saves ~0.1-0.2s per arm).
        Default is None (no caching).

    Returns
    -------
    arm : str
        Arm name
    transformed_array : numpy.ndarray or None
        Transformed 2D array, or None on error
    metadata_dict : dict
        Metadata with width, height, bounds
    error_msg : str or None
        Error message if failed, None on success
    """
    try:
        # Use cached Butler if available (optimization to avoid repeated Butler creation)
        b = get_butler_cached(datastore, base_collection, visit, butler_cache)
        data_id = make_data_id(visit, spectrograph, arm)

        # data retrieval
        # Use pre-loaded pfsConfig if available (optimization to avoid redundant loads)
        if pfsConfig_preloaded is not None:
            pfs_config = pfsConfig_preloaded
            logger.debug(f"Using pre-loaded pfsConfig for arm {arm}, SM{spectrograph}")
        else:
            pfs_config = b.get("pfsConfig", data_id)
            logger.debug(
                f"Loaded pfsConfig from Butler for arm {arm}, SM{spectrograph}"
            )

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
        transform = get_transform(scale_algo)
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
            "raw_array": image_array,  # Store original raw array for hover tooltips
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
    pfsConfig_preloaded=None,
    butler_cache=None,
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
    pfsConfig_preloaded : pfs.datamodel.PfsConfig, optional
        Pre-loaded pfsConfig object shared across all arms. Passed to each
        _build_single_2d_array call to avoid redundant loading.
        Default is None (each arm loads independently).
    butler_cache : dict, optional
        Dictionary for caching Butler instances. Passed to each
        _build_single_2d_array call to enable Butler reuse.
        Default is None (no caching).

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
    # Pass pre-loaded pfsConfig and butler_cache to avoid redundant operations
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
            pfsConfig_preloaded,  # Share pfsConfig across all arms
            butler_cache,  # Share Butler cache across all arms
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

                # Flip arrays vertically so (0,0) is at lower-left corner (astronomical convention)
                # HoloViews by default has (0,0) at upper-left, so we flip the arrays
                flipped_array = np.flipud(transformed_array)

                # Also flip the raw array for hover tooltips
                raw_array = metadata.get("raw_array")
                flipped_raw = np.flipud(raw_array)

                # Stack arrays for multiple vdims: [scaled for display, raw for hover]
                combined_data = np.stack([flipped_array, flipped_raw], axis=-1)

                # Set bounds: (left, bottom, right, top)
                # With flipped array, (0,0) will be at lower-left
                # IMPORTANT: bounds should match the actual data dimensions
                img = hv.Image(
                    combined_data,
                    bounds=(0, 0, width, height),
                    kdims=["x", "y"],
                    vdims=[
                        "intensity",
                        "raw_value",
                    ],  # First vdim for display, second for hover
                )

                # Astropy transform already applied, use full range (0-100%) with linear scaling
                vmin = transformed_array.min()
                vmax = transformed_array.max()

                # Configure display options to match matplotlib appearance
                # Note: Using Image directly without rasterize for proper hover functionality
                # Calculate aspect ratio and plot dimensions
                BASE_SIZE = 512
                aspect_ratio = width / height
                plot_width, plot_height = (
                    (BASE_SIZE, int(BASE_SIZE / aspect_ratio))
                    if aspect_ratio >= 1.0
                    else (int(BASE_SIZE * aspect_ratio), BASE_SIZE)
                )
                logger.debug(
                    f"{arm}: aspect={aspect_ratio:.3f}, plot={plot_width}x{plot_height}"
                )

                img.opts(
                    cmap="cividis",
                    clim=(vmin, vmax),  # Linear scaling of full range
                    colorbar=False,  # Hide colorbar (scaled values not meaningful for users)
                    tools=[
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
                    hover_tooltips=[
                        ("X", "$x{0.0}"),  # Cursor position X
                        ("Y", "$y{0.0}"),  # Cursor position Y
                        (
                            "Raw Value",
                            "@raw_value{0.2f}",
                        ),  # Original pixel value from raw_array
                    ],
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


def create_rasterized_holoviews_from_arrays(
    array_results, spectrograph, raster_width=1024, raster_height=1024
):
    """
    Create Datashader-rasterized HoloViews images from numpy arrays for fast rendering.

    This function creates downsampled versions of the images using Datashader's
    dynamic rasterization, which provides ~97% reduction in data transfer to the
    browser and much faster pan/zoom interactions. However, this sacrifices exact
    pixel value hover tooltips.

    Parameters
    ----------
    array_results : list
        List of (arm, transformed_array, metadata, error_msg) tuples
    spectrograph : int
        Spectrograph number
    raster_width : int, optional
        Width of rasterized image in pixels (default: 1024)
    raster_height : int, optional
        Height of rasterized image in pixels (default: 1024)

    Returns
    -------
    list of tuples
        List of (arm, rasterized hv.Image, error_msg) tuples

    Notes
    -----
    Rasterized images provide significant performance improvements:
    - ~97% reduction in data transfer (4096×4096 → 1024×1024)
    - Much faster initial load (estimated 8× speedup)
    - Smooth pan/zoom with dynamic re-rendering
    - Automatic level-of-detail on zoom

    Trade-offs:
    - Pixel values in hover are approximate (mean of downsampled region)
    - Not suitable for precise pixel-level quality assessment
    - Saved images are downsampled (not full resolution)
    """
    logger.info(
        f"Creating rasterized HoloViews images for SM{spectrograph} "
        f"({raster_width}×{raster_height})"
    )

    hv_results = []
    for arm, transformed_array, metadata, error_msg in array_results:
        if transformed_array is not None and metadata is not None and error_msg is None:
            try:
                # Create HoloViews Image (same as non-rasterized version)
                height, width = metadata["height"], metadata["width"]

                logger.info(
                    f"Rasterizing image for {arm}: "
                    f"array shape={transformed_array.shape}, "
                    f"width={width}, height={height}"
                )

                # Flip arrays vertically (astronomical convention: (0,0) at lower-left)
                flipped_array = np.flipud(transformed_array)

                # Also flip the raw array for hover tooltips
                # Even with rasterization, we can show approximate raw values
                raw_array = metadata.get("raw_array")
                flipped_raw = np.flipud(raw_array)

                # Stack arrays for multiple vdims: [scaled for display, raw for hover]
                # Datashader will downsample both, but approximate raw values are better than nothing
                combined_data = np.stack([flipped_array, flipped_raw], axis=-1)

                img = hv.Image(
                    combined_data,
                    bounds=(0, 0, width, height),
                    kdims=["x", "y"],
                    vdims=[
                        "intensity",
                        "raw_value",
                    ],  # First vdim for display, second for hover
                )

                # Get scaling values
                vmin = transformed_array.min()
                vmax = transformed_array.max()

                # Calculate aspect ratio and plot dimensions
                BASE_SIZE = 512
                aspect_ratio = width / height
                plot_width, plot_height = (
                    (BASE_SIZE, int(BASE_SIZE / aspect_ratio))
                    if aspect_ratio >= 1.0
                    else (int(BASE_SIZE * aspect_ratio), BASE_SIZE)
                )
                logger.debug(
                    f"{arm}: aspect={aspect_ratio:.3f}, plot={plot_width}x{plot_height}"
                )

                # Apply rasterization with dynamic re-rendering
                # This creates a downsampled version that re-renders on zoom/pan
                rasterized_img = rasterize(
                    img,
                    aggregator="mean",  # Use mean aggregation for pixel values
                    width=raster_width,
                    height=raster_height,
                    dynamic=True,  # Enable dynamic re-rendering on zoom/pan
                )

                # Configure display options
                rasterized_img.opts(
                    cmap="cividis",
                    clim=(vmin, vmax),
                    colorbar=False,
                    tools=[
                        "box_zoom",
                        "wheel_zoom",
                        "pan",
                        "undo",
                        "redo",
                        "reset",
                        "save",
                    ],
                    active_tools=["box_zoom"],
                    default_tools=[],
                    # Note: Hover tooltips show approximate aggregated values from downsampled data
                    # raw_value shows the sky-subtracted value (after processing)
                    # Values are approximate (mean of pixels in each downsampled region)
                    hover_tooltips=[
                        ("X", "$x{0.0}"),
                        ("Y", "$y{0.0}"),
                        (
                            "Approx. Value",
                            "@raw_value{0.2f}",
                        ),  # Downsampled sky-subtracted pixel value
                    ],
                    frame_width=plot_width,
                    frame_height=plot_height,
                    data_aspect=1.0,
                    title=metadata["title"] + " [Fast Preview]",
                    xlabel="X (pixels)",
                    ylabel="Y (pixels)",
                    toolbar="above",
                    axiswise=True,
                    framewise=True,
                )

                hv_results.append((arm, rasterized_img, None))
                logger.info(
                    f"Created rasterized HoloViews image for arm {arm}, SM{spectrograph}"
                )

            except Exception as e:
                error_msg = str(e)
                logger.error(
                    f"Failed to create rasterized HoloViews image for arm {arm}, "
                    f"SM{spectrograph}: {error_msg}"
                )
                hv_results.append((arm, None, error_msg))
        else:
            # Pass through the error from array generation
            hv_results.append((arm, None, error_msg))

    logger.info(f"Rasterized HoloViews images created for spectrograph {spectrograph}")
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


# --- Helper function for automatic y-axis range calculation ---
def compute_percentile_ylim(
    flux_arrays, mask_arrays, variance_arrays=None, mask_flags=None
):
    """Calculate y-axis range from multiple fiber spectra using percentiles

    Aggregates flux values from all selected fibers, filters out bad pixels
    and outliers, then computes robust y-axis limits using percentiles.

    Parameters
    ----------
    flux_arrays : list of ndarray
        List of flux arrays, one per fiber
    mask_arrays : list of ndarray
        List of mask arrays (bitmask integers), one per fiber
    variance_arrays : list of ndarray, optional
        List of variance arrays, one per fiber. If provided, pixels with
        abnormally large variance will be excluded.
    mask_flags : int, optional
        Bitmask value to test for bad pixels. If None, assumes mask_arrays
        contain boolean values.

    Returns
    -------
    ylim : tuple of float
        Y-axis limits as (ymin, ymax)

    Notes
    -----
    - Uses 0.5th and 99.5th percentiles to exclude extreme outliers
    - Adds margins: 10% below, 20% above (wider for emission lines)
    - Filters pixels using mask and variance (if available)
    - Falls back to min/max if insufficient good pixels remain
    """

    all_good_flux = []

    # Collect good pixels from all fibers
    for i, flux in enumerate(flux_arrays):
        mask = mask_arrays[i] if i < len(mask_arrays) else None
        variance = (
            variance_arrays[i] if variance_arrays and i < len(variance_arrays) else None
        )

        # Determine good pixels based on mask
        if mask is not None:
            if mask_flags is not None:
                # Bitmask: test if any bad flags are set
                bad = (mask & mask_flags) != 0
                good = ~bad
            else:
                # Boolean mask: True = bad pixel
                good = ~mask
        else:
            good = np.ones(len(flux), dtype=bool)

        # Filter by variance if available
        if variance is not None and np.any(good):
            var_threshold = np.percentile(variance[good], 95)
            good &= variance < var_threshold

        # Collect good flux values
        if np.any(good):
            all_good_flux.extend(flux[good])

    # Convert to array
    all_good_flux = np.array(all_good_flux)

    # Check if we have enough good data
    if len(all_good_flux) < 10:
        # Fallback: use min/max of all data (ignoring masks)
        logger.warning(
            "Insufficient good pixels for percentile calculation, using min/max"
        )
        all_flux = np.concatenate(flux_arrays)
        return (float(np.min(all_flux)), float(np.max(all_flux)))

    # Calculate percentiles
    p_low = np.percentile(all_good_flux, 0.5)  # 0.5th percentile
    p_high = np.percentile(all_good_flux, 99.9)  # 99.9th percentile

    # Add margins
    span = p_high - p_low
    if span > 0:
        y_min = p_low - 0.1 * span  # 10% margin below
        y_max = p_high + 0.5 * span  # 50% margin above (wider for emission lines)
    else:
        # All values are identical (edge case)
        y_min = p_low - 100  # arbitrary margin
        y_max = p_high + 100

    return (float(y_min), float(y_max))


# --- 1D spectra builder using Bokeh (single visit) ---
def build_1d_bokeh_figure_single_visit(
    datastore: str,
    base_collection: str,
    visit: int,
    fiber_ids,
    ylim=None,
):
    """Build interactive Bokeh plot for 1D spectra of selected fibers

    Creates multi-fiber overlay plot with error bands, interactive legend,
    and hover tooltips showing fiber metadata.

    Parameters
    ----------
    datastore : str
        Path to Butler datastore
    base_collection : str
        Base collection name
    visit : int
        Visit number
    fiber_ids : list of int
        Fiber IDs to display
    ylim : tuple of float, optional
        Y-axis limits as (ymin, ymax). If None (default), automatically
        calculates limits using percentile-based method that handles
        emission lines and noise robustly.

    Returns
    -------
    bokeh.plotting.figure
        Bokeh figure object with configured plot
    """
    from bokeh.models import Band, ColumnDataSource
    from bokeh.palettes import Category10_10

    b = get_butler(datastore, base_collection, visit)
    pfsConfig = b.get("pfsConfig", visit=visit)
    pfsMerged = b.get("pfsMerged", visit=visit)

    # Get mask flags for bad pixel identification
    # Following the original notebook approach: exclude NO_DATA, SAT, BAD, CR pixels
    mask_flags = pfsMerged.flags.get("NO_DATA", "SAT", "BAD", "CR")

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

        # Collect flux/mask/variance for automatic ylim calculation
        flux_arrays = []
        mask_arrays = []
        variance_arrays = []

        for i, fid in enumerate(fiber_ids):
            sel = pfsMerged.select(pfsConfig, fiberId=fid)
            wav = sel.wavelength[0]
            flx = sel.flux[0]
            var = sel.variance[0]
            msk = sel.mask[0]
            err = (var**0.5) if var is not None else None

            # Collect arrays for ylim calculation
            flux_arrays.append(flx)
            mask_arrays.append(msk)
            if var is not None:
                variance_arrays.append(var)

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

        # Calculate and set y-axis limits
        if ylim is None:
            # Automatic ylim calculation using percentile-based method
            variance_for_calc = (
                variance_arrays if len(variance_arrays) == len(flux_arrays) else None
            )
            ylim = compute_percentile_ylim(
                flux_arrays, mask_arrays, variance_for_calc, mask_flags
            )
            logger.info(f"Auto-calculated ylim: {ylim}")

        # Apply y-axis limits
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


# --- 1D spectra as 2D image (single visit) ---
def build_1d_spectra_as_image(
    datastore: str,
    base_collection: str,
    visit: int,
    fiber_ids=None,
    scale_algo: str = "zscale",
):
    """
    Create a 2D image representation of all 1D spectra (similar to showAllSpectraAsImage).

    Parameters
    ----------
    datastore : str
        Path to Butler datastore
    base_collection : str
        Base collection name
    visit : int
        Visit number
    fiber_ids : list of int, optional
        Fiber IDs to display. If None, displays all fibers in pfsMerged.
    scale_algo : str, optional
        Scaling algorithm: 'zscale' (default) or 'minmax'

    Returns
    -------
    hv.Image
        HoloViews Image object with 2D representation of spectra
    """
    try:
        b = get_butler(datastore, base_collection, visit)
        pfsConfig = b.get("pfsConfig", visit=visit)
        pfsMerged = b.get("pfsMerged", visit=visit)

        # Always use all fibers (ignore fiber_ids parameter for this visualization)
        # This ensures complete overview of all spectra
        flux_array = pfsMerged.flux
        wavelength_array = pfsMerged.wavelength
        fiber_id_array = pfsMerged.fiberId

        n_fibers = len(fiber_id_array)
        n_wavelength = flux_array.shape[1]

        logger.info(f"Creating 1D spectra image for {n_fibers} fibers")
        logger.info(f"Flux array shape: {flux_array.shape}")
        logger.info(
            f"Flux range (raw): [{flux_array.min():.2f}, {flux_array.max():.2f}]"
        )

        # Get wavelength range from the middle fiber (similar to showAllSpectraAsImage)
        ibar = n_fibers // 2
        lam0, lam1 = wavelength_array[ibar][0], wavelength_array[ibar][-1]

        logger.info(f"Wavelength range: {lam0:.2f} - {lam1:.2f} nm")

        # Check if fiberId is continuous
        fid_min = fiber_id_array.min()
        fid_max = fiber_id_array.max()
        n_expected = fid_max - fid_min + 1
        is_continuous = n_fibers == n_expected
        logger.info(
            f"FiberId range: {fid_min} - {fid_max} (n={n_fibers}, expected={n_expected}, continuous={is_continuous})"
        )

        # Sample some fiberIds to check for gaps
        if n_fibers >= 10:
            logger.info(
                f"Sample fiberIds: {fiber_id_array[:5].tolist()} ... {fiber_id_array[-5:].tolist()}"
            )

        # Calculate pixel size for proper centering
        # Wavelength: assuming uniform spacing
        wavelength_step = (
            (lam1 - lam0) / (n_wavelength - 1) if n_wavelength > 1 else 1.0
        )
        # FiberId: spacing is 1 (consecutive integers)
        fid_step = 1.0

        logger.info(
            f"Creating full resolution image: {n_fibers} fibers × {n_wavelength} wavelengths = {n_fibers * n_wavelength} pixels"
        )
        logger.info(
            f"Pixel sizes: wavelength_step={wavelength_step:.3f} nm, fiberId_step={fid_step}"
        )

        # Apply scaling transformation - exactly like existing 2D code
        flux_array_float = flux_array.astype(np.float64)
        transform = get_transform(scale_algo)
        transformed_array = transform(flux_array_float)

        logger.info(
            f"Transformed array range: [{transformed_array.min():.4f}, {transformed_array.max():.4f}]"
        )

        # Flip array vertically - exactly like existing 2D code
        flipped_array = np.flipud(transformed_array)

        # Also flip the original flux array for hover display
        flipped_flux = np.flipud(flux_array_float)

        # Create fiberId lookup array for hover tool
        # Create a 2D array where each row contains the fiberId for that row
        # This allows hover to show fiberId
        flipped_fiber_ids = np.flipud(fiber_id_array)  # Match the flipped flux array

        # Tile fiberId array to match wavelength dimension
        fiber_id_2d = np.tile(flipped_fiber_ids[:, np.newaxis], (1, n_wavelength))

        # Stack flipped_array, flipped_flux, and fiber_id_2d along a new axis for multiple vdims
        # HoloViews Image can have multiple value dimensions
        # - intensity: transformed (scaled) values for display
        # - flux: original flux values for hover tooltip
        # - fiberId: fiber ID for hover tooltip
        combined_data = np.stack([flipped_array, flipped_flux, fiber_id_2d], axis=-1)

        # Create HoloViews Image with wavelength and fiber index coordinates
        # bounds = (left, bottom, right, top) in data coordinates
        # NOTE: fiberIds are not continuous (has gaps), so Y-axis uses fiber INDEX (0 to n-1)
        # Similar to showAllSpectraAsImage: extent=(lam0, lam1, -0.5, n-1+0.5)
        # X-axis: wavelength (lam0 to lam1) with half-pixel extension for accuracy
        # Y-axis: fiber index (0 to n-1) with half-pixel extension
        img = hv.Image(
            combined_data,
            bounds=(
                lam0 - wavelength_step / 2,
                -0.5,  # Fiber index starts at 0
                lam1 + wavelength_step / 2,
                n_fibers - 0.5,  # Fiber index ends at n-1
            ),
            kdims=["wavelength", "fiber_index"],
            vdims=["intensity", "flux", "fiberId"],  # Three value dimensions
        )

        # Calculate plot dimensions
        plot_width = 1000  # Reduced from 1400 for better layout
        plot_height = max(200, min(500, int(n_fibers * 0.25)))

        logger.info(
            f"Created image: {n_fibers} fibers × {n_wavelength} wavelengths, plot size {plot_width}x{plot_height}"
        )

        # Get vmin/vmax for color scaling
        vmin = transformed_array.min()
        vmax = transformed_array.max()

        # Apply options with hover_tooltips
        # NOTE: data_aspect=1.0 causes rendering issues with large non-square arrays
        # For 2D detector images (4k×4k square), data_aspect=1.0 works fine
        # For 1D spectra image (2394×11501 landscape), it prevents rendering
        img.opts(
            cmap="cividis",
            clim=(vmin, vmax),
            colorbar=False,  # Colorbar removed - scaled values not meaningful
            tools=[
                "hover",
                "box_zoom",
                "wheel_zoom",
                "pan",
                "undo",
                "redo",
                "reset",
                "save",
            ],
            active_tools=["box_zoom"],
            default_tools=[],
            frame_width=plot_width,
            frame_height=plot_height,
            # data_aspect removed - causes white screen with large landscape arrays
            xlabel="Wavelength (nm)",
            ylabel="Fiber Index",  # 0-based index, not fiberId (has gaps)
            title=f"1D Spectra as Image - Visit {visit} ({n_fibers} fibers, fiberIds {fid_min}-{fid_max})",
            toolbar="above",
            axiswise=True,  # Disable axis linking
            framewise=True,  # Each frame is independent
            hover_tooltips=[
                ("Wavelength", "$x{0.1f} nm"),
                ("Fiber Index", "$y{int}"),
                ("Fiber ID", "@fiberId"),
                ("Flux", "@flux{0.2f}"),
            ],
        )

        logger.info("1D spectra image created successfully")
        return img

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to create 1D spectra image: {error_msg}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")

        # Create simple error placeholder
        dummy = np.ones((100, 100))
        img = hv.Image(dummy, bounds=(0, 0, 100, 100))
        img.opts(
            title=f"Error: {error_msg}",
            frame_width=800,
            frame_height=400,
        )
        return img
