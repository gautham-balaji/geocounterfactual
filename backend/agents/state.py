"""Global LangGraph state for the GeoCounterfactual pipeline.

Mirrors IMPLEMENTATION_MASTER_SPEC.md section 3.1, with one deliberate change:
`execution_logs` carries an `operator.add` reducer.

Why that matters: LangGraph's default reducer REPLACES a channel's value. This
graph is cyclic -- the Critic can send the Generator back around up to three
times -- so with the default reducer iteration 2 would overwrite iteration 1's
logs and the rejection message would vanish. The rejection history is the one
thing the live terminal in AgentOrchestrationView.jsx exists to show, so logs
must accumulate.

Consequence for node authors: a node returns ONLY its new log entries, never
the whole list. Every other channel keeps replace semantics, which is correct
(`violations` should reset on each critic pass, not pile up).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, TypedDict


class GeoCounterfactualState(TypedDict, total=False):
    # --- Input metadata ---
    region_id: str
    bbox: List[float]                 # [min_lon, min_lat, max_lon, max_lat]
    intervention_text: str            # plain-language instruction
    intervention_year: int            # target horizon in years (e.g. 5)

    # --- Ingested geospatial rasters (all share `geotransform` and `crs`) ---
    baseline_optical_rgb: Any         # (H, W, 3) from B4/B3/B2
    baseline_nir: Any                 # B8
    baseline_swir: Any                # B11
    baseline_ndvi: Any
    baseline_ndwi: Any
    baseline_ndmi: Any
    dem_elevation: Any
    dem_slope: Any                    # degrees
    geotransform: Any                 # affine transform for GeoTIFF export
    crs: str
    scene_source: str                 # "gee" | "cache" | "synthetic"

    # --- Agent artifacts ---
    spatial_change_mask: Any          # weighted: 1.0 water, 0.5 riparian buffer
    target_stream_coords: List[Dict]  # sited check-dam / bunding locations
    intervention_plan: Dict[str, Any] # structured intent parsed from the text
    dynamics_guidance: Dict[str, Any]
    controlnet_conditioning_map: Any  # (H, W, C) guidance tensor

    # --- Generative output ---
    candidate_future_rgb: Any
    candidate_future_ndvi: Any

    # --- Critic & feedback loop ---
    iteration_count: int              # capped at max_critic_iterations
    plausibility_score: float         # 0.0 - 100.0
    violations: List[str]
    critic_feedback_mask: Any         # spatial mask of THIS pass's rejects
    is_approved: bool
    # Every rejection, kept. critic_feedback_mask has replace semantics, so
    # on a successful run it is all-zeros by the end -- which meant the one
    # artifact the frontend most needs to show (what the Critic threw out)
    # was discarded before it could be rendered.
    rejection_history: Annotated[List[Dict[str, Any]], operator.add]

    # --- Streaming logs (accumulating; see module docstring) ---
    execution_logs: Annotated[List[Dict[str, str]], operator.add]


def initial_state(
    region_id: str,
    bbox: List[float],
    intervention_text: str,
    intervention_year: int = 5,
) -> GeoCounterfactualState:
    """Seed a run. Channels the nodes populate are left absent, not None."""
    return GeoCounterfactualState(
        region_id=region_id,
        bbox=list(bbox),
        intervention_text=intervention_text,
        intervention_year=intervention_year,
        iteration_count=0,
        plausibility_score=0.0,
        violations=[],
        is_approved=False,
        rejection_history=[],
        execution_logs=[],
    )
