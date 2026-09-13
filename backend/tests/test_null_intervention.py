"""The null-intervention invariant.

If the generator changes nothing, the Critic must report nothing. Any
violation on an unmodified scene is unfixable by construction: the
feedback mask names pixels the generator never touched, so regenerating
cannot clear them and the loop burns its entire retry budget before
releasing a scene it was never going to approve.

This is exactly how the NDVI ceiling bug survived. The suite was green
throughout, because every existing test fed the Critic a scene that had
been deliberately modified. Nothing asserted the identity case.

Run:  python -m backend.tests.test_null_intervention
"""

from __future__ import annotations

import sys

import numpy as np

import backend.agents.planner as planner_mod
from backend.agents.dynamics import dynamics_node
from backend.agents.input_handler import input_handler_node
from backend.agents.planner import planner_node
from backend.agents.state import initial_state
from backend.config import REGIONS
from backend.critic.physics_critic import PhysicalPlausibilityCritic

INTERVENTION = "Build 3 series check-dams along the main dry stream bed."

# Regions spanning the NDVI range in the catalogue. Anantapur is the one
# that actually failed: its irrigated canopy reaches 0.792 against what was
# a hard 0.75 ceiling.
REGION_IDS = ["anantapur", "kadapa", "marathwada", "sagar"]


def check(region_id: str) -> dict:
    # Offline planner: this invariant is about physics, not intent parsing,
    # and the Gemini free tier would rate-limit a multi-region test.
    planner_mod.parse_intent_with_gemini = lambda *a, **k: (None, "offline")

    region = REGIONS[region_id]
    state = initial_state(region_id, region.bbox, INTERVENTION, 5)
    for node in (input_handler_node, planner_node, dynamics_node):
        state.update(node(state))

    baseline_rgb = state["baseline_optical_rgb"]
    baseline_ndvi = state["baseline_ndvi"]
    ceiling = state["dynamics_guidance"]["ndvi_ceiling"]

    # The null intervention: candidate IS the baseline, byte for byte.
    verdict = PhysicalPlausibilityCritic().evaluate_arrays(
        candidate_rgb=baseline_rgb,
        candidate_ndvi=baseline_ndvi,
        baseline_rgb=baseline_rgb,
        baseline_ndvi=baseline_ndvi,
        dem_slope=state["dem_slope"],
        change_mask=state["spatial_change_mask"],
        years=5,
        ndvi_ceiling=ceiling,
    )
    return {
        "id": region_id,
        "verdict": verdict,
        "ndvi_max": float(np.nanmax(baseline_ndvi)),
        "ceiling_max": float(np.nanmax(ceiling)),
        "below_baseline": int(np.sum(ceiling < baseline_ndvi - 1e-6)),
    }


def run() -> int:
    print("=" * 76)
    print("NULL INTERVENTION: an unchanged scene must be judged clean")
    print("=" * 76)
    print(f"{'region':13s} {'NDVI max':>9s} {'ceil max':>9s} "
          f"{'ceil<base':>10s} {'score':>7s}  verdict")
    print("-" * 76)

    failures = []
    for region_id in REGION_IDS:
        r = check(region_id)
        v = r["verdict"]
        ok = v.is_approved and not v.violations
        print(f"{r['id']:13s} {r['ndvi_max']:9.3f} {r['ceiling_max']:9.3f} "
              f"{r['below_baseline']:10d} {v.score:7.1f}  "
              f"{'PASS' if ok else 'FAIL'}")
        for line in v.violations:
            print(f"                -> {line[:96]}")
        if not ok:
            failures.append(r["id"])

        # The ceiling caps growth; it may never sit below what is already
        # there, or those pixels violate rule 2 with nothing applied.
        if r["below_baseline"]:
            failures.append(f"{r['id']} (ceiling below baseline)")

    print("-" * 76)
    if failures:
        print(f"\n{len(failures)} FAILURE(S): {failures}")
        return 1
    print(f"\nAll {len(REGION_IDS)} regions judge an unchanged scene clean.")
    return 0


def test_null_intervention_is_clean():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
