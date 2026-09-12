"""Node 3: Eco-Hydrological Dynamics.

A rules engine, not a model. It converts "3 check-dams, 5 years" into the
physical envelope the generator must stay inside, and packs that envelope into
the multi-channel conditioning tensor ControlNet consumes in Phase 4.

The ceilings it emits are the same numbers the Critic later enforces, so the
generator is told the rules before it is judged by them.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import numpy as np
from scipy import ndimage

from backend.agents.logs import AGENT_DYNAMICS, make_logs
from backend.agents.state import GeoCounterfactualState
from backend.config import settings

logger = logging.getLogger(__name__)

# Empirical semi-arid recharge behaviour. A check-dam's influence on shallow
# groundwater decays with distance from the impoundment; beyond roughly 200 m
# the water-table response in hard-rock Deccan terrain is negligible.
RECHARGE_DECAY_LENGTH_M = 120.0
MAX_RECHARGE_DISTANCE_M = 250.0


def infiltration_field(core_mask: np.ndarray, cell_size: float) -> np.ndarray:
    """Normalised (0-1) recharge influence decaying away from surface water."""
    if not np.any(core_mask):
        return np.zeros(core_mask.shape, dtype=np.float32)
    distance_m = ndimage.distance_transform_edt(~core_mask) * cell_size
    field = np.exp(-distance_m / RECHARGE_DECAY_LENGTH_M)
    field[distance_m > MAX_RECHARGE_DISTANCE_M] = 0.0
    field[core_mask] = 1.0
    return field.astype(np.float32)


def ndvi_growth_ceiling(baseline_ndvi: np.ndarray, recharge: np.ndarray,
                        years: int, slope: np.ndarray) -> np.ndarray:
    """Maximum physically defensible NDVI after `years`.

    Three constraints compose:
      * an absolute annual growth cap (spec rule 2),
      * available moisture -- growth scales with recharge influence,
      * terrain -- steep ground holds less soil and water, so it greens less.
    """
    annual_cap = settings.max_annual_ndvi_delta
    slope_factor = np.clip(1.0 - (slope / 30.0), 0.2, 1.0)
    achievable = annual_cap * years * recharge * slope_factor
    # Semi-arid canopy saturates well below rainforest density.
    return np.clip(baseline_ndvi + achievable, -1.0, 0.75).astype(np.float32)


def build_conditioning_map(
    baseline_rgb: np.ndarray,
    slope: np.ndarray,
    change_mask: np.ndarray,
    recharge: np.ndarray,
    feedback_mask: np.ndarray | None = None,
) -> np.ndarray:
    """(H, W, 5) guidance tensor consumed by the ControlNet stack in Phase 4.

    Channels: structural luminance, normalised slope, intervention footprint,
    recharge potential, and critic-rejected regions (zero on the first pass).
    """
    luminance = np.clip(np.mean(baseline_rgb, axis=-1) * 3.0, 0.0, 1.0)
    slope_norm = np.clip(slope / 30.0, 0.0, 1.0)
    rejected = (np.zeros(slope.shape, dtype=np.float32)
                if feedback_mask is None
                else np.asarray(feedback_mask, dtype=np.float32))
    return np.dstack([
        luminance.astype(np.float32),
        slope_norm.astype(np.float32),
        np.asarray(change_mask, dtype=np.float32),
        recharge.astype(np.float32),
        rejected,
    ])


def dynamics_node(state: GeoCounterfactualState) -> dict:
    years = int(state.get("intervention_year", 5))
    cell_size = float(settings.target_scale_m)

    change_mask = state["spatial_change_mask"]
    baseline_ndvi = state["baseline_ndvi"]
    slope = state["dem_slope"]
    rgb = state["baseline_optical_rgb"]

    core = np.asarray(change_mask) >= 1.0
    recharge = infiltration_field(core, cell_size)
    ceiling = ndvi_growth_ceiling(baseline_ndvi, recharge, years, slope)

    conditioning = build_conditioning_map(
        rgb, slope, change_mask, recharge,
        feedback_mask=state.get("critic_feedback_mask"),
    )

    influenced = int(np.sum(recharge > 0.05))
    max_delta = float(np.max(ceiling - baseline_ndvi)) if ceiling.size else 0.0

    guidance: Dict[str, Any] = {
        "target_years": years,
        "max_annual_ndvi_delta": settings.max_annual_ndvi_delta,
        "max_total_ndvi_delta": settings.max_annual_ndvi_delta * years,
        "recharge_decay_length_m": RECHARGE_DECAY_LENGTH_M,
        "max_recharge_distance_m": MAX_RECHARGE_DISTANCE_M,
        "max_slope_for_water_deg": settings.max_slope_for_water_deg,
        "ndvi_ceiling": ceiling,
        "recharge_field": recharge,
        "influenced_cells": influenced,
        "influenced_area_ha": influenced * cell_size ** 2 / 10_000.0,
    }

    entries = [
        ("info", f"Recharge plume modelled: {influenced} cells "
                 f"({guidance['influenced_area_ha']:.1f} ha) within "
                 f"{MAX_RECHARGE_DISTANCE_M:.0f} m of surface water."),
        ("info", f"NDVI growth envelope for {years} yr: "
                 f"max delta {max_delta:+.3f} "
                 f"(hard cap {settings.max_annual_ndvi_delta * years:+.2f})."),
        ("success", f"Conditioning tensor built: {conditioning.shape[2]} channels "
                    f"at {conditioning.shape[0]}x{conditioning.shape[1]}."),
    ]

    return {
        "dynamics_guidance": guidance,
        "controlnet_conditioning_map": conditioning,
        "execution_logs": make_logs(state, AGENT_DYNAMICS, entries),
    }
