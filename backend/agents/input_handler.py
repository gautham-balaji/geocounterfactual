"""Node 1: Input Handler.

Resolves the scene -- a catalogue region pulled through the caching data
engine, or a user upload prepared by POST /api/upload -- and derives the
baseline spectral indices.

It also decides what the scene can be judged on. A catalogue region is a
full Sentinel-2 stack; an upload may lack NIR or SWIR, and the rules that
test NIR physics cannot run without NIR. That decision is made once, here,
and carried in state, so no later node silently treats a proxy as a
measurement.
"""

from __future__ import annotations

import logging

from backend.agents.logs import AGENT_INPUT, make_logs
from backend.agents.state import GeoCounterfactualState
from backend.config import REGIONS, settings
from backend.critic.physics_critic import ALL_RULES
from backend.data_engine import indices
from backend.data_engine.cache import load_scene, load_uploaded_scene

logger = logging.getLogger(__name__)

# Pre-intervention window. Sentinel-2 L2A begins 2017-03, so a 5-year horizon
# validated against real outcomes has to start here.
BASELINE_START = "2019-01-01"
BASELINE_END = "2019-06-30"

# Rules that need a measured NIR band, and why.
NIR_RULES = {
    "R2": "no NIR band: NDVI growth cannot be measured, only a visible-band "
          "proxy",
    "R3": "no NIR band: the red-edge test compares visible greening with the "
          "NIR response",
}


def scene_capabilities(bands) -> dict:
    """What a band stack can support: indices, proxies, and critic rules.

    The single decision used by both POST /api/upload, which reports it
    before any run, and this node, which enforces it -- so the two cannot
    disagree about which rules a scene is judged on.
    """
    idx, spectral = indices.compute_available(bands)
    disabled = {} if spectral["has_nir"] else dict(NIR_RULES)
    return {
        "indices": idx,
        "spectral": spectral,
        "critic_rules": [r for r in ALL_RULES if r not in disabled],
        "critic_rules_disabled": disabled,
        "available_bands": sorted(b for b in bands
                                  if b not in ("elevation", "slope")),
    }


def _load(state: GeoCounterfactualState):
    """Return (scene, label, region_id, bbox)."""
    upload_id = state.get("upload_id")
    if upload_id:
        scene = load_uploaded_scene(upload_id)
        return scene, f"uploaded scene {upload_id}", "upload", scene.bbox

    region_id = state.get("region_id", "anantapur")
    region = REGIONS.get(region_id)
    if region is None:
        raise ValueError(f"Unknown region_id '{region_id}'. "
                         f"Known: {sorted(REGIONS)}")
    bbox = state.get("bbox") or region.bbox
    scene = load_scene(bbox, BASELINE_START, BASELINE_END, crs=region.crs)
    return scene, region.name, region_id, bbox


def input_handler_node(state: GeoCounterfactualState) -> dict:
    scene, label, region_id, bbox = _load(state)
    caps = scene_capabilities(scene.bands)
    idx, spectral = caps["indices"], caps["spectral"]
    disabled = caps["critic_rules_disabled"]
    critic_rules = caps["critic_rules"]
    available = caps["available_bands"]

    ndvi_stats = indices.summarize(idx["ndvi"])
    slope_stats = indices.summarize(scene.bands["slope"])

    if scene.source == "upload":
        ingest = f"Ingested {label}: bands {available}."
    else:
        ingest = (f"Ingested Sentinel-2 L2A composite for {label} "
                  f"({BASELINE_START} to {BASELINE_END}).")
    vegetation = "NDVI" if spectral["has_nir"] else "GLI proxy"
    entries = [
        ("info", ingest),
        ("info", f"Scene {scene.shape[0]}x{scene.shape[1]} px @ "
                 f"{settings.target_scale_m} m, {scene.crs}, source={scene.source}."),
        ("info", f"Baseline {vegetation} mean {ndvi_stats['mean']:+.3f}; "
                 f"slope {slope_stats['min']:.1f}-{slope_stats['max']:.1f} deg."),
    ]
    if any(n.startswith("Loaded from disk cache") for n in scene.notes):
        entries.append(("info", "Baseline served from the local scene cache "
                                "(pre-baked; no Earth Engine call)."))
    if scene.source == "synthetic":
        entries.append(
            ("warn", "SYNTHETIC imagery in use - Earth Engine unavailable. "
                     "Results are not valid for evaluation."))
    if scene.source == "upload":
        for note in scene.notes:
            if not note.startswith("Loaded from disk cache"):
                entries.append(("info", f"Upload: {note}"))
    for rule, reason in disabled.items():
        entries.append(("warn", f"{rule} not evaluated - {reason}."))
    for index, proxy in spectral["proxies"].items():
        entries.append(("warn", f"{index.upper()} is {proxy}."))

    return {
        "region_id": region_id,
        "bbox": list(bbox),
        "baseline_optical_rgb": scene.rgb,
        "baseline_nir": scene.bands.get("B8"),
        "baseline_swir": scene.bands.get("B11"),
        "baseline_ndvi": idx["ndvi"],
        "baseline_ndwi": idx["ndwi"],
        "baseline_ndmi": idx["ndmi"],
        "dem_elevation": scene.bands["elevation"],
        "dem_slope": scene.bands["slope"],
        "geotransform": scene.transform,
        "crs": scene.crs,
        "scene_source": scene.source,
        "available_bands": available,
        "spectral_mode": spectral["mode"],
        "has_nir": spectral["has_nir"],
        "index_proxies": spectral["proxies"],
        "critic_rules": critic_rules,
        "critic_rules_disabled": disabled,
        "execution_logs": make_logs(state, AGENT_INPUT, entries),
    }
