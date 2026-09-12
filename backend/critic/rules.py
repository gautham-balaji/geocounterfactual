"""The four physical-plausibility rules (spec section 6.1).

Each rule is an independent function returning a RuleResult, so the critic
ablation can enable or disable them individually and attribute a change in
violation rate to a specific physical law rather than to "the critic" as a
black box.

Every rule returns three things the generator can act on:
  * a specific violation string naming the quantity and the limit breached,
  * a boolean feedback mask of exactly the offending pixels,
  * a severity in [0, 1] so the score degrades continuously rather than in
    fixed 20-point steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np
from scipy import ndimage
from skimage.metrics import structural_similarity as ssim

# One Sentinel-2 cell is 100 m^2, so the spec's 500 m^2 minimum water body is
# 5 cells. Anything smaller is speckle, not a reservoir.
MIN_WATER_BODY_CELLS = 5

# 8-connectivity: the channels here run diagonally, and a 4-neighbourhood
# would fragment a diagonal pool into unconnected single pixels.
CONNECTIVITY = ndimage.generate_binary_structure(2, 2)


@dataclass
class RuleResult:
    rule_id: str
    name: str
    passed: bool
    severity: float                       # 0.0 clean .. 1.0 maximally violated
    message: str                          # "" when passed
    mask: np.ndarray                      # bool, offending pixels
    metrics: Dict[str, Any] = field(default_factory=dict)


def _empty(shape) -> np.ndarray:
    return np.zeros(shape, dtype=bool)


def infer_nir(red: np.ndarray, ndvi: np.ndarray) -> np.ndarray:
    """Recover the NIR band from red reflectance and NDVI.

    NDVI = (NIR - RED) / (NIR + RED)  =>  NIR = RED * (1 + NDVI) / (1 - NDVI)

    The generator emits RGB plus an NDVI layer, not a full six-band cube, so
    rules 1 and 3 -- both of which need NIR -- reconstruct it algebraically
    rather than guessing from the visible bands. Exact, not an approximation.
    """
    ndvi = np.clip(np.asarray(ndvi, dtype=np.float32), -0.999, 0.999)
    red = np.asarray(red, dtype=np.float32)
    return np.clip(red * (1.0 + ndvi) / (1.0 - ndvi), 0.0, 2.0)


def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """McFeeters NDWI. Positive over open water."""
    denom = green + nir
    out = np.zeros_like(green, dtype=np.float32)
    valid = np.abs(denom) > 1e-6
    out[valid] = (green[valid] - nir[valid]) / denom[valid]
    return np.clip(out, -1.0, 1.0)


def detect_water(rgb: np.ndarray, ndvi: np.ndarray,
                 ndwi_threshold: float = 0.0) -> np.ndarray:
    """Open-water mask. Shared by rules 1 and 3 so they cannot disagree.

    NDWI alone is not sufficient when NIR is inferred from NDVI. Vegetation
    whose NDVI has been held down by the growth ceiling yields a low inferred
    NIR, so green > NIR and NDWI turns positive -- a green field then reads
    as a lake, and on sloping ground rule 1 raises a gravity violation for
    water that was never painted.

    The blue band resolves it. Chlorophyll absorbs blue strongly, so any
    vegetation has green > blue; water reflects blue at least as well as
    green. Requiring both conditions makes the classifier stable regardless
    of how NDVI was clamped.
    """
    rgb = np.asarray(rgb, dtype=np.float32)
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    nir = infer_nir(red, ndvi)
    return (compute_ndwi(green, nir) > ndwi_threshold) & (blue >= green)


# --------------------------------------------------------------------------
# Rule 1 -- Gravity & slope invariance
# --------------------------------------------------------------------------

def rule_gravity_slope(
    candidate_rgb: np.ndarray,
    candidate_ndvi: np.ndarray,
    dem_slope: np.ndarray,
    max_slope_deg: float = 2.5,
    cell_size_m: float = 10.0,
    ndwi_threshold: float = 0.0,
) -> RuleResult:
    """Surface water bodies >= 500 m^2 cannot rest on slopes > max_slope_deg.

    Water is detected by NDWI rather than the spec's green-vs-blue reflectance
    ratio, which also fires on bright rooftops, dry salt pans and haze.
    """
    shape = candidate_rgb.shape[:2]
    water = detect_water(candidate_rgb, candidate_ndvi, ndwi_threshold)
    steep_water = water & (np.asarray(dem_slope) > max_slope_deg)

    # Only contiguous blobs at or above the minimum water-body area count.
    labels, n = ndimage.label(steep_water, structure=CONNECTIVITY)
    offending = _empty(shape)
    worst_slope = 0.0
    if n:
        sizes = ndimage.sum(steep_water, labels, range(1, n + 1))
        for label_id, size in enumerate(sizes, start=1):
            if size >= MIN_WATER_BODY_CELLS:
                blob = labels == label_id
                offending |= blob
                worst_slope = max(worst_slope, float(np.max(dem_slope[blob])))

    count = int(offending.sum())
    area_m2 = count * cell_size_m ** 2
    total_cells = int(np.prod(shape))
    # 2% of the scene under illegal water is treated as maximal severity.
    severity = float(min(1.0, count / max(1.0, 0.02 * total_cells)))

    message = ""
    if count:
        message = (f"Gravity violation: {area_m2:.0f} m2 of standing water on "
                   f"slopes up to {worst_slope:.1f} deg "
                   f"(limit {max_slope_deg} deg)")

    return RuleResult(
        rule_id="R1", name="Gravity / slope invariance",
        passed=count == 0, severity=severity, message=message, mask=offending,
        metrics={"violating_cells": count, "violating_area_m2": area_m2,
                 "worst_slope_deg": worst_slope,
                 "total_water_cells": int(water.sum())},
    )


# --------------------------------------------------------------------------
# Rule 2 -- Biological NDVI growth ceiling
# --------------------------------------------------------------------------

def rule_ndvi_growth(
    candidate_ndvi: np.ndarray,
    baseline_ndvi: np.ndarray,
    years: int,
    max_annual_delta: float = 0.35,
    ndvi_ceiling: Optional[np.ndarray] = None,
    tolerance: float = 0.02,
) -> RuleResult:
    """Vegetation cannot outgrow its biological rate.

    Two ceilings apply, whichever is stricter:
      * the spec's absolute cap, delta NDVI <= max_annual_delta * years;
      * the dynamics node's per-pixel ceiling, which additionally accounts for
        available moisture and terrain -- so a barren ridge 400 m from any
        recharge cannot green even if the absolute cap would allow it.
    """
    candidate_ndvi = np.asarray(candidate_ndvi, dtype=np.float32)
    baseline_ndvi = np.asarray(baseline_ndvi, dtype=np.float32)

    absolute_cap = float(max_annual_delta) * int(years)
    delta = candidate_ndvi - baseline_ndvi

    exceeds_absolute = delta > (absolute_cap + tolerance)
    if ndvi_ceiling is not None:
        exceeds_spatial = candidate_ndvi > (np.asarray(ndvi_ceiling,
                                                       dtype=np.float32)
                                            + tolerance)
    else:
        exceeds_spatial = _empty(candidate_ndvi.shape)

    offending = exceeds_absolute | exceeds_spatial
    count = int(offending.sum())
    max_delta = float(delta.max()) if delta.size else 0.0
    severity = 0.0
    message = ""

    if count:
        excess = float(np.mean(delta[offending] - absolute_cap)) if np.any(
            exceeds_absolute) else 0.0
        severity = float(min(1.0, max(
            count / max(1.0, 0.05 * delta.size),
            max(0.0, max_delta - absolute_cap) / max(absolute_cap, 0.1),
        )))
        # Quote the limit that actually bound, not whichever is handy: with a
        # spatial ceiling in play the absolute cap is often far away, and
        # naming it would send the generator chasing the wrong constraint.
        if np.any(exceeds_absolute):
            message = (f"Biological violation: NDVI rose by up to "
                       f"{max_delta:+.3f} over {years} yr on {count} px, "
                       f"exceeding the absolute growth cap of "
                       f"{absolute_cap:+.2f} by {excess:+.3f}")
        else:
            worst = float(np.max(candidate_ndvi[offending]
                                 - np.asarray(ndvi_ceiling)[offending]))
            message = (f"Biological violation: NDVI exceeds the "
                       f"moisture/terrain growth envelope on {count} px by up "
                       f"to {worst:+.3f} (insufficient recharge or too steep "
                       f"to support that canopy)")

    return RuleResult(
        rule_id="R2", name="NDVI growth ceiling",
        passed=count == 0, severity=severity, message=message, mask=offending,
        metrics={"violating_cells": count, "max_delta_ndvi": max_delta,
                 "absolute_cap": absolute_cap},
    )


# --------------------------------------------------------------------------
# Rule 3 -- Spectral signature consistency (the red edge)
# --------------------------------------------------------------------------

def rule_spectral_consistency(
    candidate_rgb: np.ndarray,
    baseline_rgb: np.ndarray,
    candidate_ndvi: np.ndarray,
    min_vegetation_ndvi: float = 0.15,
    greening_threshold: float = 0.015,
    min_patch_cells: int = MIN_WATER_BODY_CELLS,
) -> RuleResult:
    """Anything that turned green must also have turned bright in NIR.

    Real vegetation produces the "red edge": a sharp reflectance jump between
    red and NIR. A diffusion model painting green pixels reproduces the
    visible signature but not the infrared one, which is the single most
    reliable tell that a scene was hallucinated rather than grown.

    Flags pixels whose VISIBLE greenness rose while NDVI stayed at
    non-vegetated levels. Keying on the change from baseline rather than on
    absolute greenness avoids flagging terrain that was always like that.

    Visible greenness is (green - red) / (green + red), NOT raw green
    reflectance. Healthy vegetation is DARKER than bare soil in every visible
    band -- chlorophyll absorbs, so a canopy's green reflectance (~0.09) sits
    below that of bright semi-arid soil (~0.16). What distinguishes them is
    the relationship between the bands: vegetation reflects more green than
    red, red soil the reverse. Testing raw green would miss every painted
    pixel and, worse, would flag a scene for drying out.
    """
    shape = candidate_rgb.shape[:2]
    candidate_ndvi = np.asarray(candidate_ndvi, dtype=np.float32)
    baseline_rgb = np.asarray(baseline_rgb, dtype=np.float32)

    def visible_greenness(rgb: np.ndarray) -> np.ndarray:
        red, green = rgb[:, :, 0], rgb[:, :, 1]
        denom = green + red
        out = np.zeros(denom.shape, dtype=np.float32)
        valid = denom > 1e-6
        out[valid] = (green[valid] - red[valid]) / denom[valid]
        return out

    delta_green = (visible_greenness(candidate_rgb)
                   - visible_greenness(baseline_rgb))

    greened = delta_green > greening_threshold
    nir_deficient = candidate_ndvi < min_vegetation_ndvi

    # Open water must be excluded, or every legitimate reservoir this project
    # exists to create is flagged as a hallucination: water reflects more
    # green than red AND has strongly negative NDVI, precisely the signature
    # this rule hunts for.
    #
    # NDWI alone cannot separate the two here. Painted vegetation has low
    # NDVI, so its inferred NIR is low, so green > NIR and NDWI comes out
    # positive -- water and paint look identical. The blue band separates
    # them: chlorophyll absorbs blue strongly, so vegetation (real or
    # painted) always has green > blue, whereas water reflects blue at least
    # as well as green.
    is_water = detect_water(candidate_rgb, candidate_ndvi)

    flagged = greened & nir_deficient & ~is_water

    # Minimum contiguous area, as rule 1 applies to water bodies. A handful
    # of isolated pixels at an index boundary is resampling noise, not a
    # hallucinated forest, and without this floor a single stray pixel can
    # hold the whole feedback loop open until the retry budget runs out.
    labels, n = ndimage.label(flagged, structure=CONNECTIVITY)
    offending = _empty(shape)
    if n:
        sizes = ndimage.sum(flagged, labels, range(1, n + 1))
        for label_id, size in enumerate(sizes, start=1):
            if size >= min_patch_cells:
                offending |= labels == label_id

    count = int(offending.sum())
    greened_count = int(greened.sum())
    fraction = count / greened_count if greened_count else 0.0
    severity = float(min(1.0, fraction * 2.0))

    message = ""
    if count:
        mean_ndvi = float(np.mean(candidate_ndvi[offending]))
        message = (f"Spectral violation: {count} px gained visible green "
                   f"without NIR response (mean NDVI {mean_ndvi:+.3f} < "
                   f"{min_vegetation_ndvi}) - synthetic paint, not vegetation")

    return RuleResult(
        rule_id="R3", name="Spectral signature consistency",
        passed=count == 0, severity=severity, message=message, mask=offending,
        metrics={"violating_cells": count, "greened_cells": greened_count,
                 "painted_fraction": fraction},
    )


# --------------------------------------------------------------------------
# Rule 4 -- Unchanged-area spatial conservation
# --------------------------------------------------------------------------

def rule_unchanged_ssim(
    candidate_rgb: np.ndarray,
    baseline_rgb: np.ndarray,
    change_mask: np.ndarray,
    min_ssim: float = 0.90,
    local_floor: float = 0.60,
) -> RuleResult:
    """Terrain outside the intervention footprint must survive untouched.

    Implementation note -- the spec's blueprint calls
    `ssim(base_gray[outside_mask], future_gray[outside_mask])`. Boolean-mask
    indexing flattens to 1-D, and structural_similarity requires a 2-D image,
    so that call raises. The fix is to run SSIM on the full frame with
    `full=True`, then average the per-pixel similarity map over the mask. That
    also yields a spatial map, which the flattened form could never provide --
    so the rule can hand the generator the exact pixels it corrupted rather
    than only a scalar.
    """
    shape = candidate_rgb.shape[:2]
    base_gray = np.asarray(np.mean(baseline_rgb, axis=-1), dtype=np.float64)
    cand_gray = np.asarray(np.mean(candidate_rgb, axis=-1), dtype=np.float64)

    outside = ~(np.asarray(change_mask) > 0)
    if not np.any(outside):
        return RuleResult("R4", "Unchanged-area conservation", True, 0.0, "",
                          _empty(shape), {"outside_ssim": 1.0,
                                          "outside_cells": 0})

    data_range = float(max(base_gray.max() - base_gray.min(), 1e-6))
    _score, ssim_map = ssim(base_gray, cand_gray, data_range=data_range,
                            full=True)

    outside_ssim = float(np.mean(ssim_map[outside]))
    # Pixels the generator actually damaged, for the feedback mask.
    offending = outside & (ssim_map < local_floor)

    passed = outside_ssim >= min_ssim
    severity = 0.0
    message = ""
    if not passed:
        severity = float(np.clip((min_ssim - outside_ssim) / max(min_ssim - 0.5,
                                                                 1e-6), 0, 1))
        message = (f"Drift violation: terrain outside the intervention "
                   f"footprint was altered (SSIM {outside_ssim:.3f} < "
                   f"{min_ssim:.2f}) across {int(offending.sum())} px")

    return RuleResult(
        rule_id="R4", name="Unchanged-area conservation",
        passed=passed, severity=severity, message=message, mask=offending,
        metrics={"outside_ssim": outside_ssim,
                 "outside_cells": int(outside.sum()),
                 "damaged_cells": int(offending.sum())},
    )
