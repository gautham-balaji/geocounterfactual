"""Pre-bake the Earth Engine baseline for every catalogue region.

A live demo should not depend on Earth Engine answering. This fetches each
region's co-registered Sentinel-2 + DEM stack once and stores it in the
scene cache the pipeline already reads first (`data_engine.cache`), under
exactly the key the input handler asks for. A run on a pre-baked region
then makes no Earth Engine call at all; uploads, which have no catalogue
entry, still fetch their terrain live.

What is stored: the six reflectance bands (B2, B3, B4, B8, B11, B12),
elevation and slope, with their transform and CRS. RGB is three of those
bands and NDVI is computed from B8 and B4 when the scene loads -- a few
milliseconds -- so neither is stored twice, and a stored NDVI can never
drift from the bands it came from.

The cache is the reference dataset, not merely a speed-up. Earth Engine
recomputes the median composite on every request from a collection that is
reprocessed and re-scored for cloud over time: refetching Kadapa a month
after it was cached changed 11-31% of pixels per band (99th percentile
about 0.004 reflectance) and NDVI on 36% of pixels, by up to 0.048. Results
are reproducible only against the cached scenes, so --force rewrites the
baseline every result depends on and should not be run once experiments
have started. Archive the cache directory with any published results.

Each scene is validated before it is trusted. In particular a slope band
that is flat or empty is rejected: that is the signature of Terrain.slope
run on a mosaic without a default projection, which once made the gravity
rule pass every scene while testing nothing.

Usage:
    python -m backend.scripts.prebake_ee_data            # fetch what is missing
    python -m backend.scripts.prebake_ee_data --check    # report only, no network
    python -m backend.scripts.prebake_ee_data --force    # refetch everything
    python -m backend.scripts.prebake_ee_data --regions kadapa,anantapur

Exits non-zero if any requested region is missing or invalid, so it doubles
as a pre-flight check before a demo.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import warnings
from pathlib import Path
from typing import List, Optional

import numpy as np

from backend.agents.input_handler import BASELINE_END, BASELINE_START
from backend.config import REGIONS, settings
from backend.data_engine import cache, indices
from backend.data_engine.gee_loader import REFLECTANCE_BANDS, Scene, fetch_scene

REQUIRED_BANDS = tuple(REFLECTANCE_BANDS) + ("elevation", "slope")
MIN_FINITE_FRACTION = 0.99
MIN_SLOPE_RANGE_DEG = 0.5      # a real tile spans tens of degrees


def region_key(region) -> str:
    """The cache key the input handler's load_scene() will look up."""
    return cache.cache_key(region.bbox, BASELINE_START, BASELINE_END,
                           region.crs, settings.target_scale_m)


def validate(scene: Scene) -> List[str]:
    """Reasons this scene must not be trusted; empty if it is sound."""
    problems = []
    if scene.source == "synthetic":
        problems.append("synthetic imagery")
    missing = [b for b in REQUIRED_BANDS if b not in scene.bands]
    if missing:
        return problems + [f"missing bands {missing}"]
    h, w = scene.shape
    if min(h, w) < 64:
        problems.append(f"too small ({h}x{w})")
    for name in REQUIRED_BANDS:
        finite = float(np.mean(np.isfinite(scene.bands[name])))
        if finite < MIN_FINITE_FRACTION:
            problems.append(f"{name} only {100 * finite:.1f}% finite")
    slope = scene.bands["slope"]
    if np.isfinite(slope).any() and np.nanmax(slope) - np.nanmin(slope) \
            < MIN_SLOPE_RANGE_DEG:
        problems.append("slope band is flat (Terrain.slope projection "
                        "failure?)")
    rgb = np.dstack([scene.bands[b] for b in ("B4", "B3", "B2")])
    median = float(np.nanmedian(rgb))
    if not 0.0 < median < 0.6:
        problems.append(f"implausible reflectance (median {median:.3f})")
    return problems


def _summary(scene: Scene) -> str:
    ndvi = indices.ndvi(scene.bands["B8"], scene.bands["B4"])
    h, w = scene.shape
    return (f"{h}x{w}  NDVI {float(np.nanmean(ndvi)):+.3f}  slope max "
            f"{float(np.nanmax(scene.bands['slope'])):4.1f} deg")


def _size_mb(key: str) -> float:
    return sum(p.stat().st_size for p in cache._paths(key) if p.is_file()) / 1e6


def bake(region_id: str, force: bool, check_only: bool) -> Optional[str]:
    """Bake one region. Returns None on success, else the failure reason."""
    region = REGIONS[region_id]
    key = region_key(region)
    started = time.time()

    cached = None if force else cache.load_from_cache(key)
    if cached is not None:
        problems = validate(cached)
        if not problems:
            print(f"  {region_id:12s} cached    {_summary(cached)}  "
                  f"{_size_mb(key):5.1f} MB")
            return None
        print(f"  {region_id:12s} INVALID   {'; '.join(problems)}"
              + ("" if check_only else " -- refetching"))
        if check_only:
            return "invalid cache entry"
    elif check_only:
        print(f"  {region_id:12s} MISSING")
        return "not cached"

    try:
        # fetch_scene, not load_scene: load_scene falls back to synthetic
        # imagery on failure, which here would bake fabricated data in.
        scene = fetch_scene(region.bbox, BASELINE_START, BASELINE_END,
                            region.crs, settings.target_scale_m)
    except Exception as exc:  # noqa: BLE001
        print(f"  {region_id:12s} FAILED    {type(exc).__name__}: "
              f"{str(exc)[:120]}")
        return "fetch failed"

    problems = validate(scene)
    if problems:
        print(f"  {region_id:12s} REJECTED  {'; '.join(problems)} "
              f"(not cached)")
        return "fetched scene invalid"
    cache.save_to_cache(key, scene)
    print(f"  {region_id:12s} fetched   {_summary(scene)}  "
          f"{_size_mb(key):5.1f} MB  {time.time() - started:5.1f}s")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regions", default="all",
                    help="comma list of region ids, or 'all'")
    ap.add_argument("--force", action="store_true",
                    help="refetch even regions already cached. Replaces the "
                         "reference baseline: Earth Engine's composite "
                         "drifts over time, so existing results will no "
                         "longer reproduce")
    ap.add_argument("--check", action="store_true",
                    help="report cache status only; no network")
    args = ap.parse_args()
    if args.force and args.check:
        sys.exit("--force and --check are mutually exclusive")

    warnings.filterwarnings("ignore")
    logging.basicConfig(level=logging.ERROR)

    regions = (list(REGIONS) if args.regions == "all"
               else [r.strip() for r in args.regions.split(",") if r.strip()])
    unknown = [r for r in regions if r not in REGIONS]
    if unknown:
        sys.exit(f"unknown regions {unknown}; known: {sorted(REGIONS)}")

    if args.force:
        print("WARNING: --force replaces the cached baselines with today's "
              "Earth Engine composite, which drifts over time. Results "
              "produced against the old cache will not reproduce.\n")
    print(f"Scene cache: {Path(settings.cache_dir).resolve()}")
    print(f"Baseline {BASELINE_START} .. {BASELINE_END}, "
          f"{settings.target_scale_m} m\n")
    failures = {}
    for region_id in regions:
        reason = bake(region_id, args.force, args.check)
        if reason:
            failures[region_id] = reason

    print()
    ready = len(regions) - len(failures)
    print(f"{ready}/{len(regions)} region(s) ready for an offline demo.")
    if failures:
        for region_id, reason in failures.items():
            print(f"  {region_id}: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
