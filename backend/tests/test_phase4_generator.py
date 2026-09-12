"""Phase 4 verification: real CPU diffusion on a real Sentinel-2 scene.

Proves the tensors align end to end -- reflectance in, reflectance out, on
the same grid, with the critic able to judge the result -- and reports the
measured CPU inference time.

Run:  python -m backend.tests.test_phase4_generator
"""

from __future__ import annotations

import sys
import time

import numpy as np

from backend.agents.dynamics import dynamics_node
from backend.agents.input_handler import input_handler_node
from backend.agents.planner import planner_node
from backend.agents.state import initial_state
from backend.config import REGIONS, settings
from backend.critic.physics_critic import PhysicalPlausibilityCritic
from backend.data_engine import raster_io
from backend.generator.base import GenerationRequest
from backend.generator.diffusion_local import LocalDiffusionGenerator

INTERVENTION = ("Build 3 series check-dams along the main dry stream bed to "
                "trap monsoon runoff and recharge shallow aquifers.")


def build_state():
    """Run nodes 1-3 to get a real conditioning tensor."""
    state = initial_state("anantapur", REGIONS["anantapur"].bbox,
                          INTERVENTION, 5)
    for node in (input_handler_node, planner_node, dynamics_node):
        state.update(node(state))
    return state


def run() -> int:
    print("=" * 74)
    print("PHASE 4 VERIFICATION  --  Local CPU diffusion generator")
    print("=" * 74)

    print("\n[1/4] Building conditioning inputs from nodes 1-3 ...")
    state = build_state()
    base_rgb = state["baseline_optical_rgb"]
    cond = state["controlnet_conditioning_map"]
    mask = state["spatial_change_mask"]
    print(f"      baseline RGB       {base_rgb.shape} "
          f"range [{base_rgb.min():.3f}, {base_rgb.max():.3f}]")
    print(f"      conditioning map   {cond.shape}")
    print(f"      change mask        {int((mask > 0).sum())} px editable")

    generator = LocalDiffusionGenerator(num_inference_steps=20)
    print(f"\n[2/4] Generator: {generator.describe()}")

    request = GenerationRequest(
        baseline_rgb=base_rgb,
        conditioning_map=cond,
        change_mask=mask,
        dynamics_guidance=state["dynamics_guidance"],
        prompt=("Aerial satellite view, semi-arid Indian watershed 5 years "
                "after 3 check-dams were built. Seasonal water impoundment "
                "along the channel, riparian green belt, surrounding farmland "
                "unchanged. 10 m resolution Sentinel-2 true colour."),
        iteration=0,
        baseline_ndvi=state["baseline_ndvi"],
        dem_slope=state["dem_slope"],
    )

    print("\n[3/4] Running diffusion (first call also downloads ~4 GB "
          "of weights) ...")
    wall_start = time.time()
    result = generator.generate(request)
    wall_total = time.time() - wall_start

    print(f"\n      backend            {result.backend}")
    for note in result.notes or []:
        print(f"      note               {note}")
    print(f"      TOTAL WALL TIME    {wall_total:.1f}s")

    # ---- tensor alignment -------------------------------------------
    print("\n[4/4] Verification")
    assert result.rgb.shape == base_rgb.shape, (
        f"Shape drift: {result.rgb.shape} != {base_rgb.shape}")
    print(f"[ok] output grid matches input exactly: {result.rgb.shape}")

    assert result.rgb.dtype == np.float32
    assert np.all(np.isfinite(result.rgb)), "Non-finite pixels in output"
    assert 0.0 <= result.rgb.min() and result.rgb.max() <= 1.0, (
        f"Output outside reflectance range: "
        f"[{result.rgb.min():.3f}, {result.rgb.max():.3f}]")
    print(f"[ok] reflectance units preserved: "
          f"[{result.rgb.min():.3f}, {result.rgb.max():.3f}] float32")

    assert result.ndvi is not None and result.ndvi.shape == base_rgb.shape[:2]
    print(f"[ok] NDVI layer {result.ndvi.shape}, "
          f"mean {result.ndvi.mean():+.3f} "
          f"(baseline {state['baseline_ndvi'].mean():+.3f})")

    editable = mask > 0
    changed = np.any(np.abs(result.rgb - base_rgb) > 1e-4, axis=-1)
    inside_changed = int(np.sum(changed & editable))
    outside_changed = int(np.sum(changed & ~editable))
    print(f"[ok] pixels altered inside the mask : {inside_changed}")
    print(f"[ok] pixels altered outside the mask: {outside_changed}")
    assert inside_changed > 0, "Diffusion produced no change at all"
    assert outside_changed == 0, (
        f"{outside_changed} px changed outside the editable region")

    # ---- the critic must be able to judge it ------------------------
    critic = PhysicalPlausibilityCritic()
    verdict = critic.evaluate_arrays(
        candidate_rgb=result.rgb, candidate_ndvi=result.ndvi,
        baseline_rgb=base_rgb, baseline_ndvi=state["baseline_ndvi"],
        dem_slope=state["dem_slope"], change_mask=mask, years=5,
        ndvi_ceiling=state["dynamics_guidance"].get("ndvi_ceiling"))
    print(f"\n[ok] critic evaluated the real generated scene: "
          f"approved={verdict.is_approved} score={verdict.score:.1f}%")
    for rid in ("R1", "R2", "R3", "R4"):
        m = verdict.metrics[rid]
        print(f"       {rid} {m['name']:<34} "
              f"{'pass' if m['passed'] else 'FAIL'}")
    for v in verdict.violations:
        print(f"       -> {v}")

    # ---- feedback path ----------------------------------------------
    print("\n[bonus] Re-running with a synthetic critic feedback mask ...")
    fake_feedback = np.zeros(mask.shape, dtype=bool)
    ys, xs = np.nonzero(editable)
    fake_feedback[ys[:len(ys) // 2], xs[:len(xs) // 2]] = True
    request2 = GenerationRequest(
        baseline_rgb=base_rgb, conditioning_map=cond, change_mask=mask,
        dynamics_guidance=state["dynamics_guidance"], prompt=request.prompt,
        iteration=1, feedback_mask=fake_feedback,
        baseline_ndvi=state["baseline_ndvi"])
    t0 = time.time()
    result2 = generator.generate(request2)
    print(f"        iteration 2 in {time.time() - t0:.1f}s "
          f"(weights already resident)")
    for note in result2.notes or []:
        print(f"        note {note}")
    locked_changed = int(np.sum(
        np.any(np.abs(result2.rgb - base_rgb) > 1e-4, axis=-1) & fake_feedback))
    assert locked_changed == 0, (
        f"{locked_changed} critic-rejected px were repainted")
    print(f"[ok] all {int(fake_feedback.sum())} critic-rejected px left "
          f"untouched")

    out = settings.static_dir / "phase4"
    raster_io.render_rgb(base_rgb, out / "01_baseline.png")
    raster_io.render_rgb(result.rgb, out / "02_generated.png")
    raster_io.render_colormap(result.ndvi, out / "03_generated_ndvi.png",
                              cmap="RdYlGn", vmin=-0.2, vmax=0.8)
    raster_io.render_mask_overlay(result.rgb, editable,
                                  out / "04_intervention.png",
                                  colour=(0.2, 0.9, 1.0), alpha=0.35)
    print(f"\n[ok] renders written to {out}")

    print("\n" + "=" * 74)
    print(f"PHASE 4 VERIFIED  --  CPU inference {wall_total:.1f}s wall")
    print("=" * 74)
    return 0


def test_phase4_local_diffusion():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
