"""Demo readiness: offline baselines and the live progress stream.

1. Pre-baked regions load with Earth Engine unreachable. The pre-bake script
   must write under exactly the key the input handler looks up; this is
   checked by making every Earth Engine fetch raise and requiring the
   pipeline's own loader to still return the real scene.
2. The pre-bake validator rejects what must never be cached: synthetic
   imagery, missing bands, and a flat slope band (the Terrain.slope
   projection failure that made the gravity rule pass everything).
3. The stream's progress events agree with the graph. `next` comes from the
   graph's routing for every critic outcome -- retry, approval, exhausted
   budget, shadow mode -- and the verdict carries what the interface shows.

Offline apart from the cached scenes. Run:
    python -m backend.tests.test_demo_readiness
"""

from __future__ import annotations

import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")

import backend.data_engine.cache as cache_mod  # noqa: E402
from backend.agents.input_handler import BASELINE_END, BASELINE_START  # noqa: E402
from backend.config import REGIONS, settings  # noqa: E402
from backend.data_engine.gee_loader import Scene  # noqa: E402
from backend.scripts.prebake_ee_data import region_key, validate  # noqa: E402
from backend.server import _progress  # noqa: E402


def test_prebaked_regions_load_offline():
    original = cache_mod.fetch_scene

    def no_network(*a, **k):
        raise RuntimeError("Earth Engine is unreachable in this test")

    cache_mod.fetch_scene = no_network
    try:
        for rid, region in REGIONS.items():
            scene = cache_mod.load_scene(region.bbox, BASELINE_START,
                                         BASELINE_END, crs=region.crs,
                                         allow_synthetic=False)
            assert scene.source != "synthetic", rid
            assert not validate(scene), (rid, validate(scene))
            assert region_key(region) == cache_mod.cache_key(
                region.bbox, BASELINE_START, BASELINE_END, region.crs,
                settings.target_scale_m), rid
    finally:
        cache_mod.fetch_scene = original
    print(f"  offline load   : all {len(REGIONS)} regions served from the "
          f"pre-baked cache with Earth Engine unreachable")


def test_validator_rejects_bad_scenes():
    region = REGIONS["kadapa"]
    good = cache_mod.load_from_cache(region_key(region))
    assert good is not None and not validate(good)

    def variant(**changes):
        bands = {k: v.copy() for k, v in good.bands.items()}
        bands.update(changes.pop("bands", {}))
        return Scene(bands=bands, transform=good.transform, crs=good.crs,
                     bbox=good.bbox, start_date=good.start_date,
                     end_date=good.end_date,
                     source=changes.get("source", good.source))

    flat = variant(bands={"slope": np.zeros_like(good.bands["slope"])})
    assert any("flat" in p for p in validate(flat)), validate(flat)

    holed = variant(bands={"B8": np.full_like(good.bands["B8"], np.nan)})
    assert any("B8" in p for p in validate(holed)), validate(holed)

    missing = variant()
    del missing.bands["elevation"]
    assert any("missing" in p for p in validate(missing))

    synthetic = variant(source="synthetic")
    assert any("synthetic" in p for p in validate(synthetic))
    print("  validator      : flat slope, empty band, missing band and "
          "synthetic imagery all rejected")


def _critic(approved, gating=True, done=1, failed=(), feedback_px=0,
            rules=None):
    mask = np.zeros((20, 20), bool)
    mask.ravel()[:feedback_px] = True
    update = {"is_approved": approved, "critic_gating": gating,
              "plausibility_score": 100.0 if approved else 95.8,
              "violations": [] if approved else ["Gravity violation: ..."],
              "critic_feedback_mask": mask}
    if not approved:
        update["rejection_history"] = [{"rule_ids": list(failed)}]
    merged = {"iteration_count": done, **update}
    if rules is not None:
        merged["critic_rules"] = rules
    return _progress("critic", update, merged)


def test_progress_events():
    # The fixed edges, and the pass opening when the generator is next.
    assert _progress("input_handler", {}, {})["next"] == "planner"
    dyn = _progress("dynamics", {}, {"iteration_count": 0})
    assert dyn["next"] == "generator" and dyn["pass"] == 1
    gen = _progress("generator", {}, {"iteration_count": 1})
    assert gen["next"] == "critic" and gen["pass"] == 1

    retry = _critic(False, done=1, failed=("R1",), feedback_px=55)
    assert retry["next"] == "generator" and retry["pass"] == 2
    v = retry["verdict"]
    assert (v["outcome"], v["failed_rules"], v["feedback_px"],
            v["iteration"]) == ("retry", ["R1"], 55, 1)

    ok = _critic(True, done=2)
    assert ok["next"] is None and ok["verdict"]["outcome"] == "approved"

    budget = settings.max_critic_iterations
    spent = _critic(False, done=budget, failed=("R3",))
    assert spent["next"] is None and spent["verdict"]["outcome"] == "exhausted"

    shadow = _critic(False, gating=False, done=1, failed=("R2",))
    assert shadow["next"] is None and shadow["verdict"]["outcome"] == "recorded"

    rgb = _critic(True, rules=["R1", "R4"])
    assert rgb["verdict"]["evaluated_rules"] == ["R1", "R4"]
    print("  progress events: fixed edges, retry opens the next pass, and "
          "approved / exhausted / shadow all end the run, as the graph routes")


def run() -> int:
    print("=" * 74)
    print("DEMO READINESS: offline baselines, live progress events")
    print("=" * 74)
    test_prebaked_regions_load_offline()
    test_validator_rejects_bad_scenes()
    test_progress_events()
    print("-" * 74)
    print("The demo runs without Earth Engine, and the live view follows the "
          "graph.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
