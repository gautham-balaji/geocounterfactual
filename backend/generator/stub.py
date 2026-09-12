"""Procedural stand-in generator -- no torch, no weights, milliseconds per call.

Purpose is to exercise the graph, not to produce publishable imagery. It is
what makes the Phase 2 verification gate and the critic ablation runnable
before the diffusion stack exists.

It deliberately reproduces the failure mode the Critic was built to catch: on
its first pass it lets the impoundment spill uphill onto terrain steeper than
gravity allows, exactly as an unconstrained diffusion model does when told
"add a reservoir here". On later passes it honours critic_feedback_mask. That
gives the cyclic edge something real to reject and then accept, rather than a
rejection faked by a flag.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from scipy import ndimage

from backend.generator.base import (BaseGenerator, GenerationRequest,
                                    GenerationResult)

# Approximate surface reflectance of shallow turbid water in a semi-arid
# impoundment, as (B4, B3, B2).
WATER_RGB = (0.035, 0.075, 0.095)
# Healthy irrigated/riparian canopy.
VEG_RGB = (0.045, 0.095, 0.040)


class StubGenerator(BaseGenerator):
    name = "stub"

    def __init__(self, simulate_hallucination: bool = True,
                 spill_radius_px: int = 9):
        # simulate_hallucination=False gives a compliant generator, used as the
        # control arm in the critic-ON vs critic-OFF experiment.
        self.simulate_hallucination = simulate_hallucination
        self.spill_radius_px = spill_radius_px

    def generate(self, request: GenerationRequest) -> GenerationResult:
        rgb = np.array(request.baseline_rgb, dtype=np.float32, copy=True)
        mask = np.asarray(request.change_mask, dtype=np.float32)
        guidance = request.dynamics_guidance or {}
        notes = []

        core = mask >= 1.0
        buffer = (mask > 0.0) & (mask < 1.0)

        water = core.copy()

        # --- the hallucination the critic exists to catch -------------------
        if self.simulate_hallucination and request.iteration == 0 and np.any(core):
            bleed = ndimage.binary_dilation(
                core, iterations=self.spill_radius_px) & ~core
            water |= bleed
            notes.append(f"Unconstrained synthesis: water spilled onto "
                         f"{int(np.sum(bleed))} adjacent cells.")

        # --- honour critic feedback on regeneration -------------------------
        if request.feedback_mask is not None:
            rejected = np.asarray(request.feedback_mask, dtype=bool)
            removed = int(np.sum(water & rejected))
            water &= ~rejected
            notes.append(f"Retracted water from {removed} critic-rejected cells.")

        # --- paint water ----------------------------------------------------
        for c, value in enumerate(WATER_RGB):
            rgb[:, :, c][water] = value

        # --- greening, bounded by the dynamics NDVI ceiling -----------------
        recharge = guidance.get("recharge_field")
        if recharge is None:
            recharge = buffer.astype(np.float32)
        recharge = np.asarray(recharge, dtype=np.float32)

        greening = np.clip(recharge, 0.0, 1.0)
        greening[water] = 0.0
        for c, value in enumerate(VEG_RGB):
            rgb[:, :, c] = rgb[:, :, c] * (1 - greening) + value * greening

        rgb = np.clip(rgb, 0.0, 1.0)

        # NDVI implied by the synthesized bands, clamped to the ceiling so the
        # stub never violates rule 2 (we want rule 1 exercised in isolation).
        ceiling = guidance.get("ndvi_ceiling")
        nir = np.clip(rgb[:, :, 1] * 2.4 + greening * 0.25, 0.0, 1.0)
        red = rgb[:, :, 0]
        denom = nir + red
        ndvi = np.zeros_like(red)
        valid = denom > 1e-6
        ndvi[valid] = (nir[valid] - red[valid]) / denom[valid]
        ndvi[water] = -0.25
        if ceiling is not None:
            ndvi = np.minimum(ndvi, np.asarray(ceiling, dtype=np.float32))

        return GenerationResult(
            rgb=rgb,
            ndvi=ndvi.astype(np.float32),
            backend=self.name,
            notes=notes,
        )
