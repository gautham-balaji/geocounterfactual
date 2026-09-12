"""Node 4: Generator.

A thin adapter. All compute lives behind BaseGenerator, so this node is
identical whether synthesis runs as a procedural stub, CPU diffusion, or a
Colab T4 over HTTP.

It owns `iteration_count`: incrementing here (rather than in the critic) means
the counter reflects how many times synthesis has actually been attempted,
which is what the loop guard in workflow.py needs.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from backend.agents.logs import AGENT_GENERATOR, make_logs
from backend.agents.state import GeoCounterfactualState
from backend.generator.base import GenerationRequest, get_generator

logger = logging.getLogger(__name__)

_generator = None


def _resolve_generator():
    """Cached so a heavy backend loads weights once per process."""
    global _generator
    if _generator is None:
        _generator = get_generator()
    return _generator


def set_generator(generator) -> None:
    """Inject a generator (tests, ablation arms)."""
    global _generator
    _generator = generator


def build_prompt(state: GeoCounterfactualState) -> str:
    plan = state.get("intervention_plan") or {}
    years = state.get("intervention_year", 5)
    structure = str(plan.get("structure_type", "check_dam")).replace("_", " ")
    return (
        f"Aerial satellite view, semi-arid Indian watershed {years} years after "
        f"{plan.get('count', 3)} {structure} structures were built. "
        f"Seasonal water impoundment along the channel, riparian green belt, "
        f"surrounding farmland and terrain unchanged. 10 m resolution, "
        f"Sentinel-2 true colour."
    )


def generator_node(state: GeoCounterfactualState) -> dict:
    generator = _resolve_generator()
    iteration = int(state.get("iteration_count", 0))
    feedback = state.get("critic_feedback_mask")
    violations = state.get("violations") or []

    request = GenerationRequest(
        baseline_rgb=state["baseline_optical_rgb"],
        conditioning_map=state["controlnet_conditioning_map"],
        change_mask=state["spatial_change_mask"],
        dynamics_guidance=state.get("dynamics_guidance") or {},
        prompt=build_prompt(state),
        iteration=iteration,
        feedback_mask=feedback,
        violations=violations,
        baseline_ndvi=state.get("baseline_ndvi"),
        dem_slope=state.get("dem_slope"),
    )

    started = time.time()
    result = generator.generate(request)
    elapsed = time.time() - started

    if iteration == 0:
        entries = [("info", f"Synthesizing candidate scene via "
                            f"'{result.backend}' backend.")]
    else:
        entries = [("info", f"Re-synthesizing (iteration {iteration + 1}) with "
                            f"corrected elevation mask; "
                            f"{int(np.sum(np.asarray(feedback, dtype=bool)))} "
                            f"px penalised.")]
    for note in (result.notes or []):
        entries.append(("info", note))
    entries.append(("success", f"Candidate scene generated in {elapsed:.2f}s."))

    return {
        "candidate_future_rgb": result.rgb,
        "candidate_future_ndvi": result.ndvi,
        "iteration_count": iteration + 1,
        "execution_logs": make_logs(state, AGENT_GENERATOR, entries),
    }
