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
        # Rejections accumulate across a run. Applying only the newest mask
        # lets previously-retracted water reappear on the next pass, so the
        # loop oscillates instead of converging.
        self._retracted: Optional[np.ndarray] = None

    def generate(self, request: GenerationRequest) -> GenerationResult:
        rgb = np.array(request.baseline_rgb, dtype=np.float32, copy=True)
        mask = np.asarray(request.change_mask, dtype=np.float32)
        guidance = request.dynamics_guidance or {}
        notes = []

        core = mask >= 1.0
        buffer = (mask > 0.0) & (mask < 1.0)

        if request.iteration == 0:
            self._retracted = np.zeros(core.shape, dtype=bool)

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
            if self._retracted is None:
                self._retracted = np.zeros(core.shape, dtype=bool)
            self._retracted |= np.asarray(request.feedback_mask, dtype=bool)

        if self._retracted is not None and np.any(self._retracted):
            removed = int(np.sum(water & self._retracted))
            water &= ~self._retracted
            notes.append(f"Retracted water from {removed} cells "
                         f"({int(self._retracted.sum())} rejected cumulatively).")

        # --- paint water ----------------------------------------------------
        for c, value in enumerate(WATER_RGB):
            rgb[:, :, c][water] = value

        # --- greening, bounded by the dynamics NDVI ceiling -----------------
        # growth_field, not recharge_field: a plantation greens without any
        # impoundment, and keying greening off recharge made afforestation a
        # no-op (verified: 0 px changed).
        growth = guidance.get("growth_field", guidance.get("recharge_field"))
        if growth is None:
            growth = buffer.astype(np.float32)
        growth = np.asarray(growth, dtype=np.float32)

        greening = np.clip(growth, 0.0, 1.0)

        # Paint only as much green as the NDVI ceiling can justify. Scaling
        # the visible bands by `growth` while clamping NDVI to the ceiling
        # separately lets the two disagree: on ground where the ceiling is
        # tight (steep, or far from recharge) the stub painted a canopy whose
        # NDVI could not exceed 0.15, and rule 3 correctly called it
        # synthetic paint. Jalna failed exactly this way on 86 px and burned
        # its whole retry budget, because no amount of regeneration fixes an
        # inconsistency baked into the generator.
        ceiling = guidance.get("ndvi_ceiling")
        baseline_ndvi = request.baseline_ndvi
        if ceiling is not None and baseline_ndvi is not None:
            headroom = (np.asarray(ceiling, dtype=np.float32)
                        - np.asarray(baseline_ndvi, dtype=np.float32))
            # A full-strength canopy needs ~0.35 NDVI of headroom.
            greening = np.minimum(greening,
                                  np.clip(headroom / 0.35, 0.0, 1.0))

        greening[water] = 0.0
        # Rejected pixels are left alone on regeneration, whichever rule
        # rejected them -- as the diffusion backends do by removing them from
        # the editable region. Retracting only water let a pixel rejected for
        # its spectrum be repainted identically on every pass.
        if self._retracted is not None:
            greening[self._retracted] = 0.0
        base_rgb = rgb.copy()
        for c, value in enumerate(VEG_RGB):
            rgb[:, :, c] = rgb[:, :, c] * (1 - greening) + value * greening

        rgb = np.clip(rgb, 0.0, 1.0)

        # NDVI anchored to the measured baseline: baseline + (proxy(new) -
        # proxy(old)). Re-deriving NDVI from scratch with the crude proxy
        # below ignores what was measured: on dense riparian canopy it came
        # out BELOW the true baseline, so a pixel the stub greened reported
        # falling NDVI -- visible greening without an NIR response, which
        # rule 3 rightly rejects and the loop could never clear. The
        # diffusion backend was anchored the same way for the same reason.
        # Clamped to the ceiling so the stub never violates rule 2 (we want
        # rule 1 exercised in isolation).
        ceiling = guidance.get("ndvi_ceiling")

        def proxy_ndvi(bands: np.ndarray, boost: np.ndarray) -> np.ndarray:
            nir = np.clip(bands[:, :, 1] * 2.4 + boost * 0.25, 0.0, 1.0)
            red = bands[:, :, 0]
            denom = nir + red
            out = np.zeros_like(red)
            valid = denom > 1e-6
            out[valid] = (nir[valid] - red[valid]) / denom[valid]
            return out

        if baseline_ndvi is not None:
            ndvi = (np.asarray(baseline_ndvi, dtype=np.float32)
                    + proxy_ndvi(rgb, greening)
                    - proxy_ndvi(base_rgb, np.zeros_like(greening)))
            ndvi = np.clip(ndvi, -1.0, 1.0)
        else:
            ndvi = proxy_ndvi(rgb, greening)
        ndvi[water] = -0.25
        if ceiling is not None:
            ndvi = np.minimum(ndvi, np.asarray(ceiling, dtype=np.float32))

        return GenerationResult(
            rgb=rgb,
            ndvi=ndvi.astype(np.float32),
            backend=self.name,
            notes=notes,
        )
