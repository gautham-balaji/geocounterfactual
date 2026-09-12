"""Phase 3 unit tests: each physics rule against a synthetic violation.

Every rule is tested twice -- once on a clean scene it must accept, once on a
scene containing only that rule's violation, which it must reject. Testing
rejection alone would not distinguish a working rule from one that fires on
everything.

Run:  python -m backend.tests.test_phase3_critic
"""

from __future__ import annotations

import sys

import numpy as np

from backend.critic import rules as R
from backend.critic.physics_critic import (ALL_RULES,
                                           PhysicalPlausibilityCritic,
                                           critic_off)

H = W = 96
CELL = 10.0
YEARS = 5

# Reflectances used to build the fixtures.
SOIL = (0.20, 0.16, 0.13)     # semi-arid red soil (R, G, B)
WATER = (0.035, 0.075, 0.095)
VEG = (0.045, 0.095, 0.040)


def _flat_scene():
    """Baseline: uniform bare soil, flat ground, low NDVI."""
    rgb = np.zeros((H, W, 3), dtype=np.float32)
    for c, v in enumerate(SOIL):
        rgb[:, :, c] = v
    # Faint texture so SSIM has real structure to compare against.
    rng = np.random.default_rng(7)
    rgb += rng.normal(0, 0.004, rgb.shape).astype(np.float32)
    rgb = np.clip(rgb, 0, 1)

    ndvi = np.full((H, W), 0.18, dtype=np.float32)
    slope = np.full((H, W), 1.0, dtype=np.float32)   # gentle everywhere
    change_mask = np.zeros((H, W), dtype=np.float32)
    change_mask[40:56, 40:56] = 1.0                  # 16x16 intervention zone
    return rgb, ndvi, slope, change_mask


def _paint(rgb, region, colour):
    out = rgb.copy()
    for c, v in enumerate(colour):
        out[:, :, c][region] = v
    return out


def _banner(title):
    print(f"\n{'-' * 74}\n{title}\n{'-' * 74}")


# ==========================================================================
# Rule 1 -- gravity / slope
# ==========================================================================

def test_rule1_gravity():
    _banner("RULE 1  Gravity / slope invariance")
    rgb, ndvi, slope, mask = _flat_scene()

    # Clean: water sits inside the flat intervention zone.
    legal = np.zeros((H, W), bool); legal[44:52, 44:52] = True
    clean_rgb = _paint(rgb, legal, WATER)
    clean_ndvi = ndvi.copy(); clean_ndvi[legal] = -0.25
    res = R.rule_gravity_slope(clean_rgb, clean_ndvi, slope,
                               max_slope_deg=2.5, cell_size_m=CELL)
    print(f"  clean scene  : passed={res.passed} "
          f"water_cells={res.metrics['total_water_cells']}")
    assert res.passed, f"False positive on legal water: {res.message}"

    # Violation: identical water, but the ground beneath it is a 14 deg ridge.
    steep = slope.copy(); steep[44:52, 44:52] = 14.0
    res = R.rule_gravity_slope(clean_rgb, clean_ndvi, steep,
                               max_slope_deg=2.5, cell_size_m=CELL)
    print(f"  water on 14 deg: passed={res.passed} severity={res.severity:.2f}")
    print(f"    -> {res.message}")
    assert not res.passed
    assert res.metrics["violating_area_m2"] == 6400.0
    assert abs(res.metrics["worst_slope_deg"] - 14.0) < 1e-6
    assert res.mask.sum() == 64, f"mask covers {res.mask.sum()} px, expected 64"
    print(f"    feedback mask: {int(res.mask.sum())} px, exactly the pool")

    # Speckle below the 500 m^2 minimum must NOT trip the rule.
    speck = np.zeros((H, W), bool); speck[10, 10] = True
    sp_rgb = _paint(rgb, speck, WATER)
    sp_ndvi = ndvi.copy(); sp_ndvi[speck] = -0.25
    sp_slope = slope.copy(); sp_slope[10, 10] = 20.0
    res = R.rule_gravity_slope(sp_rgb, sp_ndvi, sp_slope, 2.5, CELL)
    print(f"  1-px speckle : passed={res.passed} (below 500 m2 minimum)")
    assert res.passed, "Speckle should not count as a water body"


# ==========================================================================
# Rule 2 -- NDVI growth ceiling
# ==========================================================================

def test_rule2_ndvi_growth():
    _banner("RULE 2  Biological NDVI growth ceiling")
    _rgb, ndvi, _slope, _mask = _flat_scene()
    cap = 0.35 * YEARS                       # 1.75 over 5 years

    legal = ndvi + 0.30                      # well inside the cap
    res = R.rule_ndvi_growth(legal, ndvi, YEARS, max_annual_delta=0.35)
    print(f"  +0.30 delta  : passed={res.passed} (cap {cap:+.2f})")
    assert res.passed, f"False positive: {res.message}"

    # Barren plot to dense canopy in 5 years.
    absurd = ndvi.copy(); absurd[20:40, 20:40] = 0.95      # delta +0.77
    res = R.rule_ndvi_growth(absurd, ndvi, YEARS, max_annual_delta=0.10)
    print(f"  +0.77 vs cap +0.50: passed={res.passed} "
          f"severity={res.severity:.2f}")
    print(f"    -> {res.message}")
    assert not res.passed
    assert res.mask.sum() == 400
    print(f"    feedback mask: {int(res.mask.sum())} px")

    # Per-pixel ceiling from the dynamics node is stricter than the absolute
    # cap: a ridge far from recharge may not green even by a legal amount.
    ceiling = np.full_like(ndvi, 0.20)
    modest = ndvi + 0.25                     # legal absolutely, illegal here
    res = R.rule_ndvi_growth(modest, ndvi, YEARS, max_annual_delta=0.35,
                             ndvi_ceiling=ceiling)
    print(f"  vs moisture envelope: passed={res.passed}")
    print(f"    -> {res.message}")
    assert not res.passed, "Spatial ceiling was not enforced"


# ==========================================================================
# Rule 3 -- spectral signature consistency
# ==========================================================================

def test_rule3_spectral():
    _banner("RULE 3  Spectral signature consistency (red edge)")
    rgb, ndvi, _slope, _mask = _flat_scene()
    zone = np.zeros((H, W), bool); zone[30:50, 30:50] = True

    # Honest vegetation: visibly greener AND NIR-bright (high NDVI).
    honest_rgb = _paint(rgb, zone, VEG)
    honest_ndvi = ndvi.copy(); honest_ndvi[zone] = 0.62
    res = R.rule_spectral_consistency(honest_rgb, rgb, honest_ndvi)
    print(f"  real vegetation (NDVI 0.62): passed={res.passed}")
    assert res.passed, f"False positive on real vegetation: {res.message}"

    # Hallucinated paint: identical pixels in RGB, no infrared response.
    painted_ndvi = ndvi.copy(); painted_ndvi[zone] = 0.05
    res = R.rule_spectral_consistency(honest_rgb, rgb, painted_ndvi)
    print(f"  painted green (NDVI 0.05) : passed={res.passed} "
          f"severity={res.severity:.2f}")
    print(f"    -> {res.message}")
    assert not res.passed
    assert res.mask.sum() == 400
    print(f"    feedback mask: {int(res.mask.sum())} px "
          f"({res.metrics['painted_fraction']:.0%} of greened area)")


# ==========================================================================
# Rule 4 -- unchanged-area conservation
# ==========================================================================

def test_rule4_ssim():
    _banner("RULE 4  Unchanged-area spatial conservation (SSIM)")
    rgb, _ndvi, _slope, mask = _flat_scene()

    # Legal: only the intervention zone changed.
    inside = mask > 0
    legal = _paint(rgb, inside, WATER)
    res = R.rule_unchanged_ssim(legal, rgb, mask, min_ssim=0.90)
    print(f"  change confined to mask: passed={res.passed} "
          f"SSIM={res.metrics['outside_ssim']:.3f}")
    assert res.passed, f"False positive: {res.message}"

    # Violation: the generator also rewrote a large area outside the mask.
    rng = np.random.default_rng(3)
    drifted = legal.copy()
    drifted[5:70, 5:70] += rng.normal(0, 0.09, (65, 65, 3)).astype(np.float32)
    drifted = np.clip(drifted, 0, 1)
    res = R.rule_unchanged_ssim(drifted, rgb, mask, min_ssim=0.90)
    print(f"  background corrupted   : passed={res.passed} "
          f"SSIM={res.metrics['outside_ssim']:.3f} severity={res.severity:.2f}")
    print(f"    -> {res.message}")
    assert not res.passed
    assert res.mask.sum() > 0, "SSIM rule produced no spatial feedback"
    assert not np.any(res.mask & inside), "Feedback leaked inside the mask"
    print(f"    feedback mask: {int(res.mask.sum())} px, none inside the mask")


# ==========================================================================
# Integration: the full critic and the ablation switch
# ==========================================================================

def test_critic_integration():
    _banner("INTEGRATION  Full critic, scoring and ablation")
    rgb, ndvi, slope, mask = _flat_scene()
    critic = PhysicalPlausibilityCritic()

    inside = mask > 0
    clean_rgb = _paint(rgb, inside, WATER)
    clean_ndvi = ndvi.copy(); clean_ndvi[inside] = -0.25

    v = critic.evaluate_arrays(clean_rgb, clean_ndvi, rgb, ndvi, slope, mask,
                               years=YEARS)
    print(f"  clean scene : approved={v.is_approved} score={v.score:.1f}% "
          f"violations={len(v.violations)}")
    assert v.is_approved and v.score == 100.0

    # A scene that breaks all four laws at once.
    bad_slope = slope.copy(); bad_slope[inside] = 14.0
    bad_rgb = clean_rgb.copy()
    green_zone = np.zeros((H, W), bool); green_zone[10:30, 10:30] = True
    bad_rgb = _paint(bad_rgb, green_zone, VEG)          # R3: paint
    rng = np.random.default_rng(11)
    bad_rgb[60:90, 60:90] += rng.normal(0, 0.10, (30, 30, 3)).astype(np.float32)
    bad_rgb = np.clip(bad_rgb, 0, 1)                    # R4: drift
    bad_ndvi = clean_ndvi.copy()
    bad_ndvi[green_zone] = 0.02                         # R3: no NIR response
    bad_ndvi[70:85, 10:25] = 0.99                       # R2: impossible growth

    v = critic.evaluate_arrays(bad_rgb, bad_ndvi, rgb, ndvi, bad_slope, mask,
                               years=YEARS, ndvi_ceiling=np.full_like(ndvi, 0.3))
    print(f"  4-way breach: approved={v.is_approved} score={v.score:.1f}% "
          f"violations={len(v.violations)}")
    for line in v.violations:
        print(f"    XX {line}")
    assert not v.is_approved
    assert len(v.violations) == 4, f"Expected all 4 rules to fire, got {len(v.violations)}"
    assert v.score < 50.0, f"Score {v.score} too lenient for a 4-way breach"
    assert v.feedback_mask.sum() > 0
    print(f"    combined feedback mask: {int(v.feedback_mask.sum())} px")

    # Severity weighting: a worse scene must score strictly lower.
    mild_slope = slope.copy(); mild_slope[44:48, 44:48] = 14.0
    mild = critic.evaluate_arrays(clean_rgb, clean_ndvi, rgb, ndvi,
                                  mild_slope, mask, years=YEARS)
    severe_slope = slope.copy(); severe_slope[inside] = 14.0
    severe = critic.evaluate_arrays(clean_rgb, clean_ndvi, rgb, ndvi,
                                    severe_slope, mask, years=YEARS)
    print(f"  severity scaling: small breach {mild.score:.1f}% > "
          f"large breach {severe.score:.1f}%")
    assert mild.score > severe.score, "Score is not severity-weighted"

    # Ablation arms.
    off = critic_off()
    v_off = off.evaluate_arrays(bad_rgb, bad_ndvi, rgb, ndvi, bad_slope, mask,
                                years=YEARS)
    print(f"  critic-OFF  : approved={v_off.is_approved} "
          f"score={v_off.score:.1f}% (same scene, no rules)")
    assert v_off.is_approved, "critic-OFF must approve everything"

    solo = PhysicalPlausibilityCritic(enabled_rules=("R1",))
    v_solo = solo.evaluate_arrays(bad_rgb, bad_ndvi, rgb, ndvi, bad_slope,
                                  mask, years=YEARS)
    print(f"  R1 only     : violations={len(v_solo.violations)} "
          f"({solo.name})")
    assert len(v_solo.violations) == 1, "Rule isolation failed"


def run() -> int:
    print("=" * 74)
    print("PHASE 3 VERIFICATION  --  Physical-Plausibility Critic")
    print("=" * 74)
    test_rule1_gravity()
    test_rule2_ndvi_growth()
    test_rule3_spectral()
    test_rule4_ssim()
    test_critic_integration()
    print("\n" + "=" * 74)
    print("PHASE 3 VERIFIED  --  all 4 rules trigger correctly, no false positives")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(run())
