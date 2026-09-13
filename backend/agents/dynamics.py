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

# Fraction of the absolute annual NDVI cap (settings.max_annual_ndvi_delta)
# that each intervention type can realistically achieve in a semi-arid,
# largely rainfed setting. The cap is the Critic's hard limit; these are the
# typical envelopes the Dynamics agent holds the generator to.
GROWTH_RATE_BY_TYPE = {
    "check_dam": 1.00,        # riparian belt on a recharged channel
    "farm_pond": 0.85,
    "percolation_pit": 0.60,
    "contour_bund": 0.55,
    "afforestation": 0.45,    # rainfed plantation: slower than riparian
}

# How far vegetation establishment bleeds past a planted boundary.
PLANTATION_EDGE_DECAY_M = 40.0
MAX_PLANTATION_SPREAD_M = 80.0


def infiltration_field(core_mask: np.ndarray, cell_size: float) -> np.ndarray:
    """Normalised (0-1) recharge influence decaying away from surface water."""
    if not np.any(core_mask):
        return np.zeros(core_mask.shape, dtype=np.float32)
    distance_m = ndimage.distance_transform_edt(~core_mask) * cell_size
    field = np.exp(-distance_m / RECHARGE_DECAY_LENGTH_M)
    field[distance_m > MAX_RECHARGE_DISTANCE_M] = 0.0
    field[core_mask] = 1.0
    return field.astype(np.float32)


def plantation_field(treated: np.ndarray, cell_size: float) -> np.ndarray:
    """Growth potential for a DIRECTLY PLANTED area.

    Afforestation does not depend on a surface-water recharge plume -- the
    trees are put in the ground and survive on rainfall. Its growth potential
    is therefore ~1 across the planted polygon, decaying just past the edge
    as seedlings spread, rather than radiating from an impoundment.
    """
    if not np.any(treated):
        return np.zeros(treated.shape, dtype=np.float32)
    outside_m = ndimage.distance_transform_edt(~treated) * cell_size
    field = np.exp(-outside_m / PLANTATION_EDGE_DECAY_M)
    # Hard cutoff: exp() never reaches zero, so without it every pixel in the
    # scene picks up a trace of greening and the generator reports a change
    # across the whole frame for a 150 ha plantation.
    field[outside_m > MAX_PLANTATION_SPREAD_M] = 0.0
    field[treated] = 1.0
    return field.astype(np.float32)


def growth_potential(change_mask: np.ndarray, structure_type: str,
                     cell_size: float) -> tuple:
    """Return (growth_field, recharge_field) for this intervention.

    These are two different physical quantities and conflating them was a
    real bug: the original code derived BOTH from the surface-water core, so
    an afforestation plan -- which creates no impoundment -- got a recharge
    field of all zeros, hence a growth ceiling of exactly the baseline, hence
    a generator that changed nothing at all. Verified: 0 pixels altered.

    Water interventions drive growth through recharge. Planting drives growth
    directly. Moisture, by contrast, only rises where there IS water, so the
    recharge field stays empty for a plantation and the moisture layer
    correctly reports no gain.
    """
    mask = np.asarray(change_mask, dtype=np.float32)
    water_core = mask >= 1.0
    treated = mask > 0.0

    recharge = infiltration_field(water_core, cell_size)
    growth = (recharge if np.any(water_core)
              else plantation_field(treated, cell_size))

    # The growth field drives what the generator repaints, so it MUST NOT
    # extend past the declared change mask -- rule 4 rejects any alteration
    # outside that footprint, and it is right to. Both fields naturally spill
    # beyond it (recharge to 250 m, plantation to 80 m) while the mask's
    # buffer is narrower, which had the generator greening 51868 px of
    # "unchanged" ground and the loop burning its whole retry budget.
    #
    # recharge_field is deliberately left unclipped: groundwater genuinely
    # does not respect our polygon, and the moisture layer should show that.
    # Only the generator's instruction is constrained.
    return (growth * treated.astype(np.float32)), recharge


def ndvi_growth_ceiling(baseline_ndvi: np.ndarray, recharge: np.ndarray,
                        years: int, slope: np.ndarray,
                        rate_factor: float = 1.0) -> np.ndarray:
    """Maximum physically defensible NDVI after `years`.

    Three constraints compose:
      * an absolute annual growth cap (spec rule 2),
      * available moisture -- growth scales with recharge influence,
      * terrain -- steep ground holds less soil and water, so it greens less.
    """
    annual_cap = settings.max_annual_ndvi_delta * float(rate_factor)
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

    plan = state.get("intervention_plan") or {}
    structure_type = str(plan.get("structure_type", "check_dam"))
    rate_factor = GROWTH_RATE_BY_TYPE.get(structure_type, 1.0)

    growth, recharge = growth_potential(change_mask, structure_type, cell_size)

    # Nothing grows on water that is already there. Several catalogued
    # watersheds contain a tank or reservoir inside the recharge buffer, and
    # without this the generator painted canopy over open water: NDVI rose
    # only from -0.26 to 0.11 while the visible bands turned green, which
    # rule 3 correctly reported as synthetic paint. Jalna failed this way on
    # 86 px every iteration, so the loop could never converge -- no amount of
    # regeneration fixes an instruction that was wrong to begin with.
    existing_water = np.asarray(state.get("baseline_ndwi"), dtype=np.float32) > 0.0 \
        if state.get("baseline_ndwi") is not None else np.zeros(growth.shape, bool)
    growth = np.where(existing_water, 0.0, growth).astype(np.float32)

    ceiling = ndvi_growth_ceiling(baseline_ndvi, growth, years, slope,
                                  rate_factor=rate_factor)

    conditioning = build_conditioning_map(
        rgb, slope, change_mask, growth,
        feedback_mask=state.get("critic_feedback_mask"),
    )

    influenced = int(np.sum(growth > 0.05))
    max_delta = float(np.max(ceiling - baseline_ndvi)) if ceiling.size else 0.0

    guidance: Dict[str, Any] = {
        "target_years": years,
        "max_annual_ndvi_delta": settings.max_annual_ndvi_delta,
        "max_total_ndvi_delta": settings.max_annual_ndvi_delta * years,
        "recharge_decay_length_m": RECHARGE_DECAY_LENGTH_M,
        "max_recharge_distance_m": MAX_RECHARGE_DISTANCE_M,
        "max_slope_for_water_deg": settings.max_slope_for_water_deg,
        "structure_type": structure_type,
        "growth_rate_factor": rate_factor,
        "ndvi_ceiling": ceiling,
        "growth_field": growth,
        "recharge_field": recharge,
        "influenced_cells": influenced,
        "influenced_area_ha": influenced * cell_size ** 2 / 10_000.0,
    }

    driver = ("recharge plume from surface water" if np.any(recharge > 0.05)
              else "direct planting (rainfed, no impoundment)")
    entries = [
        ("info", f"Growth driver: {driver}. {influenced} cells "
                 f"({guidance['influenced_area_ha']:.1f} ha) influenced."),
        ("info", f"NDVI growth envelope for {years} yr ({structure_type}, "
                 f"rate x{rate_factor:.2f}): max delta {max_delta:+.3f} "
                 f"(hard cap {settings.max_annual_ndvi_delta * years:+.2f})."),
        ("success", f"Conditioning tensor built: {conditioning.shape[2]} channels "
                    f"at {conditioning.shape[0]}x{conditioning.shape[1]}."),
    ]

    return {
        "dynamics_guidance": guidance,
        "controlnet_conditioning_map": conditioning,
        "execution_logs": make_logs(state, AGENT_DYNAMICS, entries),
    }
