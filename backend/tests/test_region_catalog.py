"""Every catalogued region must actually run the pipeline.

Land-cover statistics say a tile is non-urban; they do not say the terrain
analysis will find a channel there, or that a dam can be sited on it, or
that the critic loop converges. A region that looks good in WorldCover but
produces an empty change mask is a live demo failure, so each one is
exercised end to end.

Run:  python -m backend.tests.test_region_catalog
"""

from __future__ import annotations

import sys
import time

import numpy as np

from backend.agents import generator_node
from backend.agents.workflow import run_simulation
from backend.config import REGIONS, settings
from backend.generator.stub import StubGenerator

INTERVENTION = ("Build 3 series check-dams along the main dry stream bed to "
                "trap monsoon runoff and recharge shallow aquifers.")


def check_region(region_id: str) -> dict:
    generator_node.set_generator(StubGenerator(simulate_hallucination=True))
    started = time.time()
    state = run_simulation(region_id, INTERVENTION, 5)

    mask = np.asarray(state["spatial_change_mask"])
    slope = np.asarray(state["dem_slope"])
    ndvi = np.asarray(state["baseline_ndvi"])
    sites = state.get("target_stream_coords") or []

    return {
        "id": region_id,
        "source": state.get("scene_source"),
        "shape": state["baseline_optical_rgb"].shape[:2],
        "slope_max": float(np.nanmax(slope)),
        "ndvi_mean": float(np.nanmean(ndvi)),
        "sites": len(sites),
        "core_px": int((mask >= 1.0).sum()),
        "footprint_px": int((mask > 0).sum()),
        "iterations": int(state.get("iteration_count", 0)),
        "approved": bool(state.get("is_approved")),
        "score": float(state.get("plausibility_score", 0)),
        "rejections": len(state.get("rejection_history") or []),
        "seconds": time.time() - started,
    }


def run() -> int:
    print("=" * 108)
    print(f"REGION CATALOG VALIDATION - {len(REGIONS)} regions")
    print("=" * 108)
    print(f"{'region':13s} {'src':5s} {'shape':11s} {'slopeMax':>8s} "
          f"{'NDVI':>6s} {'sites':>5s} {'core':>6s} {'footprint':>9s} "
          f"{'iters':>5s} {'score':>6s} {'ok':>4s}  {'sec':>5s}")
    print("-" * 108)

    failures = []
    for region_id in REGIONS:
        try:
            r = check_region(region_id)
        except Exception as exc:  # noqa: BLE001
            print(f"{region_id:13s} EXCEPTION: {str(exc)[:80]}")
            failures.append((region_id, f"exception: {exc}"))
            continue

        ok = (r["source"] == "gee" and r["slope_max"] > 1.0 and r["sites"] > 0
              and r["core_px"] > 0 and r["approved"])
        print(f"{r['id']:13s} {str(r['source']):5s} "
              f"{r['shape'][0]}x{r['shape'][1]:<7} {r['slope_max']:8.1f} "
              f"{r['ndvi_mean']:6.3f} {r['sites']:5d} {r['core_px']:6d} "
              f"{r['footprint_px']:9d} {r['iterations']:5d} {r['score']:6.1f} "
              f"{'PASS' if ok else 'FAIL':>4s}  {r['seconds']:5.0f}")

        if not ok:
            why = []
            if r["source"] != "gee":
                why.append(f"scene source {r['source']}")
            if r["slope_max"] <= 1.0:
                why.append("slope raster flat/empty")
            if r["sites"] == 0:
                why.append("no dam sites")
            if r["core_px"] == 0:
                why.append("empty impoundment")
            if not r["approved"]:
                why.append("loop did not converge")
            failures.append((r["id"], ", ".join(why)))

    print("-" * 108)
    if failures:
        print(f"\n{len(failures)} REGION(S) FAILED:")
        for rid, why in failures:
            print(f"   {rid}: {why}")
    else:
        print(f"\nALL {len(REGIONS)} REGIONS VALIDATED")
    return 1 if failures else 0


def test_every_region_runs():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
