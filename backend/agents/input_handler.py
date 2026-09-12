"""Node 1: Input Handler.

Resolves the region, pulls the co-registered Sentinel-2 + DEM stack through
the caching data engine, and derives the baseline spectral indices.
"""

from __future__ import annotations

import logging

from backend.agents.logs import AGENT_INPUT, make_logs
from backend.agents.state import GeoCounterfactualState
from backend.config import REGIONS, settings
from backend.data_engine import indices
from backend.data_engine.cache import load_scene

logger = logging.getLogger(__name__)

# Pre-intervention window. Sentinel-2 L2A begins 2017-03, so a 5-year horizon
# validated against real outcomes has to start here.
BASELINE_START = "2019-01-01"
BASELINE_END = "2019-06-30"


def input_handler_node(state: GeoCounterfactualState) -> dict:
    region_id = state.get("region_id", "anantapur")
    region = REGIONS.get(region_id)
    if region is None:
        raise ValueError(f"Unknown region_id '{region_id}'. "
                         f"Known: {sorted(REGIONS)}")

    bbox = state.get("bbox") or region.bbox
    scene = load_scene(bbox, BASELINE_START, BASELINE_END, crs=region.crs)
    idx = indices.compute_all(scene.bands)

    ndvi_stats = indices.summarize(idx["ndvi"])
    slope_stats = indices.summarize(scene.bands["slope"])

    entries = [
        ("info", f"Ingested Sentinel-2 L2A composite for {region.name} "
                 f"({BASELINE_START} to {BASELINE_END})."),
        ("info", f"Scene {scene.shape[0]}x{scene.shape[1]} px @ "
                 f"{settings.target_scale_m} m, {scene.crs}, source={scene.source}."),
        ("info", f"Baseline NDVI mean {ndvi_stats['mean']:+.3f}; "
                 f"slope {slope_stats['min']:.1f}-{slope_stats['max']:.1f} deg."),
    ]
    if scene.source == "synthetic":
        entries.append(
            ("warn", "SYNTHETIC imagery in use - Earth Engine unavailable. "
                     "Results are not valid for evaluation."))

    return {
        "region_id": region_id,
        "bbox": list(bbox),
        "baseline_optical_rgb": scene.rgb,
        "baseline_nir": scene.bands["B8"],
        "baseline_swir": scene.bands["B11"],
        "baseline_ndvi": idx["ndvi"],
        "baseline_ndwi": idx["ndwi"],
        "baseline_ndmi": idx["ndmi"],
        "dem_elevation": scene.bands["elevation"],
        "dem_slope": scene.bands["slope"],
        "geotransform": scene.transform,
        "crs": scene.crs,
        "scene_source": scene.source,
        "execution_logs": make_logs(state, AGENT_INPUT, entries),
    }
