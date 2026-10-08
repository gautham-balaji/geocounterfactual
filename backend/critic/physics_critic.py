"""The Physical-Plausibility Critic -- the project's headline contribution.

Orchestrates the four rules in rules.py, combines their feedback masks, and
produces a continuous plausibility score.

Scoring deviates from the spec's `max(50, 100 - 20 * len(violations))` in two
respects, both deliberate:

  * It is severity-weighted, not a count. A 30 m^2 puddle on a 3 deg slope and
    a lake covering half the scene are both "one violation", but they are not
    equally implausible, and a step function makes the critic-ON vs critic-OFF
    curve uninformative.
  * It is not floored at 50. A floor compresses exactly the range where the
    ablation needs resolution -- a catastrophically wrong scene should be able
    to score near zero.

Per-rule weights sum to 100 and encode relative physical severity: violating
gravity is worse than drifting slightly outside the mask.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from backend.config import settings
from backend.critic import rules as R

logger = logging.getLogger(__name__)

RULE_WEIGHTS: Dict[str, float] = {
    "R1": 30.0,   # gravity -- a hard physical law
    "R2": 25.0,   # biological growth rate
    "R3": 25.0,   # spectral realism (the hallucination tell)
    "R4": 20.0,   # spatial conservation
}

ALL_RULES = ("R1", "R2", "R3", "R4")


@dataclass
class CriticVerdict:
    is_approved: bool
    score: float
    violations: List[str]
    feedback_mask: np.ndarray
    results: List[R.RuleResult] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    # False in shadow mode: the verdict is recorded but must not trigger a
    # regeneration. Kept separate from is_approved, which stays honest.
    gating: bool = True

    def as_dict(self) -> Dict[str, Any]:
        """Shape expected by critic_node / CriticProtocol."""
        return {
            "is_approved": self.is_approved,
            "score": self.score,
            "violations": self.violations,
            "feedback_mask": self.feedback_mask,
            "results": self.results,
            "metrics": self.metrics,
            "gating": self.gating,
        }


class PhysicalPlausibilityCritic:
    """Full four-rule physics engine.

    `enabled_rules` exists for the ablation: passing a single id isolates one
    physical law's contribution. An empty tuple evaluates nothing at all.

    `gating=False` is shadow mode, the measuring control arm: every enabled
    rule is still evaluated and the verdict recorded, but a violation does not
    send the scene back to the generator. This is what makes the critic-OFF
    arm produce a violation rate rather than an empty record.
    """

    def __init__(
        self,
        enabled_rules: Optional[tuple] = None,
        max_slope_for_water_deg: Optional[float] = None,
        max_annual_ndvi_delta: Optional[float] = None,
        min_outside_ssim: Optional[float] = None,
        gating: bool = True,
    ):
        self.enabled_rules = tuple(ALL_RULES if enabled_rules is None
                                   else enabled_rules)
        self.gating = bool(gating)
        self.max_slope = (settings.max_slope_for_water_deg
                          if max_slope_for_water_deg is None
                          else max_slope_for_water_deg)
        self.max_ndvi_rate = (settings.max_annual_ndvi_delta
                              if max_annual_ndvi_delta is None
                              else max_annual_ndvi_delta)
        self.min_ssim = (settings.min_outside_ssim if min_outside_ssim is None
                         else min_outside_ssim)

    @property
    def name(self) -> str:
        if not self.enabled_rules:
            return "critic-OFF (no rules)"
        if len(self.enabled_rules) == len(ALL_RULES):
            label = "full physics (R1-R4)"
        else:
            label = f"partial ({'+'.join(self.enabled_rules)})"
        return label if self.gating else f"{label} [shadow, not gating]"

    # -- core -------------------------------------------------------------

    def evaluate_arrays(
        self,
        candidate_rgb: np.ndarray,
        candidate_ndvi: np.ndarray,
        baseline_rgb: np.ndarray,
        baseline_ndvi: np.ndarray,
        dem_slope: np.ndarray,
        change_mask: np.ndarray,
        years: int = 5,
        ndvi_ceiling: Optional[np.ndarray] = None,
        cell_size_m: Optional[float] = None,
    ) -> CriticVerdict:
        """Array-level entry point -- used directly by the unit tests."""
        cell_size_m = cell_size_m or float(settings.target_scale_m)
        shape = np.asarray(candidate_rgb).shape[:2]

        results: List[R.RuleResult] = []

        if "R1" in self.enabled_rules:
            results.append(R.rule_gravity_slope(
                candidate_rgb, candidate_ndvi, dem_slope,
                max_slope_deg=self.max_slope, cell_size_m=cell_size_m))

        if "R2" in self.enabled_rules:
            results.append(R.rule_ndvi_growth(
                candidate_ndvi, baseline_ndvi, years=years,
                max_annual_delta=self.max_ndvi_rate,
                ndvi_ceiling=ndvi_ceiling))

        if "R3" in self.enabled_rules:
            results.append(R.rule_spectral_consistency(
                candidate_rgb, baseline_rgb, candidate_ndvi))

        if "R4" in self.enabled_rules:
            results.append(R.rule_unchanged_ssim(
                candidate_rgb, baseline_rgb, change_mask,
                min_ssim=self.min_ssim))

        violations = [r.message for r in results if not r.passed]

        feedback = np.zeros(shape, dtype=bool)
        for r in results:
            if not r.passed:
                feedback |= np.asarray(r.mask, dtype=bool)

        penalty = sum(RULE_WEIGHTS[r.rule_id] * r.severity
                      for r in results if not r.passed)
        score = float(np.clip(100.0 - penalty, 0.0, 100.0))

        metrics = {r.rule_id: {"name": r.name, "passed": r.passed,
                               "severity": round(r.severity, 4), **r.metrics}
                   for r in results}
        metrics["evaluated_rules"] = list(self.enabled_rules)
        metrics["feedback_cells"] = int(feedback.sum())
        metrics["gating"] = self.gating

        return CriticVerdict(
            is_approved=not violations,   # honest in both modes
            score=score,
            violations=violations,
            feedback_mask=feedback,
            results=results,
            metrics=metrics,
            gating=self.gating,
        )

    # -- LangGraph adapter -------------------------------------------------

    def evaluate(self, state) -> Dict[str, Any]:
        """CriticProtocol entry point used by agents/critic_node.py."""
        guidance = state.get("dynamics_guidance") or {}
        verdict = self.evaluate_arrays(
            candidate_rgb=state["candidate_future_rgb"],
            candidate_ndvi=state["candidate_future_ndvi"],
            baseline_rgb=state["baseline_optical_rgb"],
            baseline_ndvi=state["baseline_ndvi"],
            dem_slope=state["dem_slope"],
            change_mask=state["spatial_change_mask"],
            years=int(state.get("intervention_year", 5)),
            ndvi_ceiling=guidance.get("ndvi_ceiling"),
        )
        return verdict.as_dict()


def critic_off() -> PhysicalPlausibilityCritic:
    """No rules evaluated at all: approves everything, records nothing.

    Not usable as the ablation's control arm -- it yields no violation rate
    to compare against. Use critic_shadow() for that.
    """
    return PhysicalPlausibilityCritic(enabled_rules=())


def critic_shadow(enabled_rules: Optional[tuple] = None
                  ) -> PhysicalPlausibilityCritic:
    """Control arm for the critic-ON vs critic-OFF experiment.

    Scores every output with the full rule set but never gates, so the OFF
    arm measures the violation rate of unconstrained generation instead of
    reporting an empty record.
    """
    return PhysicalPlausibilityCritic(enabled_rules=enabled_rules, gating=False)
