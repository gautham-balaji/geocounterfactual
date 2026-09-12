"""Node 5: Physical-Plausibility Critic -- graph adapter.

SCOPE NOTE. Phase 2 delivers the graph wiring and a PROVISIONAL evaluator that
implements rule 1 only (gravity / water on slopes). That is enough to prove
the cyclic edge fires, rejects, and converges.

Phase 3 replaces `ProvisionalCritic` with the full engine in
critic/physics_critic.py -- rules 2 (NDVI growth ceiling), 3 (red-edge
spectral consistency) and 4 (unchanged-area SSIM) plus proper scoring. The
evaluator is injected through set_critic(), so that swap touches no graph code.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Protocol

import numpy as np
from scipy import ndimage

from backend.agents.logs import AGENT_CRITIC, make_logs
from backend.agents.state import GeoCounterfactualState
from backend.config import settings

logger = logging.getLogger(__name__)

# One Sentinel-2 cell is 100 m^2, so the spec's 500 m^2 minimum water body is
# 5 cells. Smaller blobs are speckle, not a reservoir.
MIN_WATER_BODY_CELLS = 5


class CriticProtocol(Protocol):
    def evaluate(self, state: GeoCounterfactualState) -> Dict[str, Any]: ...


def detect_water(rgb: np.ndarray, ndvi: Optional[np.ndarray]) -> np.ndarray:
    """Water candidates in a synthesized scene.

    Open water is blue-dominant and has strongly negative NDVI. Phase 3 will
    compute true NDWI once the generator emits a NIR band; until then this
    pairing is far more selective than the spec's bare green-vs-red test,
    which also fires on bright rooftops and haze.
    """
    red, _green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    candidate = blue > red
    if ndvi is not None:
        candidate &= np.asarray(ndvi) < 0.0
    return candidate


class ProvisionalCritic:
    """Rule 1 only: surface water cannot rest on steep ground."""

    name = "provisional (rule 1 only)"

    def evaluate(self, state: GeoCounterfactualState) -> Dict[str, Any]:
        rgb = state["candidate_future_rgb"]
        slope = np.asarray(state["dem_slope"])
        ndvi = state.get("candidate_future_ndvi")

        violations = []
        feedback = np.zeros(rgb.shape[:2], dtype=bool)

        water = detect_water(rgb, ndvi)
        steep_water = water & (slope > settings.max_slope_for_water_deg)

        # Drop speckle: only contiguous blobs at or above the spec's minimum
        # water-body area count as a violation.
        labels, count = ndimage.label(steep_water)
        offending = np.zeros_like(steep_water)
        worst_slope = 0.0
        for label in range(1, count + 1):
            blob = labels == label
            if blob.sum() >= MIN_WATER_BODY_CELLS:
                offending |= blob
                worst_slope = max(worst_slope, float(slope[blob].max()))

        if np.any(offending):
            area_m2 = int(offending.sum()) * settings.target_scale_m ** 2
            violations.append(
                f"Gravity violation: {area_m2} m2 of standing water on slopes "
                f"up to {worst_slope:.1f} deg "
                f"(limit {settings.max_slope_for_water_deg} deg)"
            )
            feedback |= offending

        score = max(50.0, 100.0 - 20.0 * len(violations))
        return {
            "is_approved": not violations,
            "score": score,
            "violations": violations,
            "feedback_mask": feedback,
        }


_critic: CriticProtocol = ProvisionalCritic()


def set_critic(critic: CriticProtocol) -> None:
    """Swap the evaluator -- used by Phase 3 and by the ablation's OFF arm."""
    global _critic
    _critic = critic


def get_critic() -> CriticProtocol:
    return _critic


def critic_node(state: GeoCounterfactualState) -> dict:
    iteration = int(state.get("iteration_count", 0))
    verdict = _critic.evaluate(state)

    violations = verdict["violations"]
    approved = bool(verdict["is_approved"])
    exhausted = iteration >= settings.max_critic_iterations

    entries = []
    if approved:
        entries.append(
            ("success", f"Passed all checks with {verdict['score']:.0f}% "
                        f"plausibility score on iteration {iteration}."))
    elif exhausted:
        # Spec 3.3: after max retries the best candidate is released rather
        # than looping forever, but it must be labelled honestly.
        entries.append(
            ("warn", f"Iteration {iteration} still violates physics but the "
                     f"retry budget ({settings.max_critic_iterations}) is "
                     f"exhausted; releasing best-effort scene."))
        for v in violations:
            entries.append(("warn", f"Unresolved: {v}"))
    else:
        for v in violations:
            entries.append(("reject", f"Iteration {iteration} rejected: {v}"))
        entries.append(
            ("info", f"Feedback mask built over "
                     f"{int(np.sum(verdict['feedback_mask']))} px; "
                     f"returning to generator."))

    # `is_approved` stays the HONEST verdict. Exhaustion is a routing concern,
    # handled by check_critic_decision() in workflow.py (spec 3.3). Marking an
    # exhausted run "approved" here would report a physics-violating scene as
    # passing, and would zero out the violation rate that the critic-ON vs
    # critic-OFF experiment is supposed to measure.
    return {
        "is_approved": approved,
        "plausibility_score": float(verdict["score"]),
        "violations": violations,
        "critic_feedback_mask": verdict["feedback_mask"],
        "execution_logs": make_logs(state, AGENT_CRITIC, entries),
    }
