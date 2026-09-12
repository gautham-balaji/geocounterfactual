"""Generator interface -- the seam that makes Compute Option A work.

One interface, three implementations selected by GENERATOR_BACKEND:

    stub    procedural, no torch. Graph wiring, CI, ablation dry-runs.
    local   CPU Stable Diffusion inpaint + ControlNet on this machine.
    remote  HTTP to a Colab T4 (this machine has no NVIDIA GPU).

Because `local` and `remote` satisfy the same contract, the LangGraph node
never learns which one is running, and swapping compute never touches the
graph. Only `stub` exists in Phase 2; the other two arrive in Phase 4.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np


@dataclass
class GenerationRequest:
    """Everything a generator needs for one synthesis pass."""

    baseline_rgb: np.ndarray               # (H, W, 3) surface reflectance 0-1
    conditioning_map: np.ndarray           # (H, W, 5) from dynamics node
    change_mask: np.ndarray                # weighted intervention footprint
    dynamics_guidance: Dict[str, Any]
    prompt: str
    iteration: int = 0
    feedback_mask: Optional[np.ndarray] = None   # critic-rejected pixels
    violations: Optional[list] = None
    # Needed to calibrate a reflectance->NDVI mapping per scene, since an
    # RGB diffusion backbone cannot emit a NIR band directly.
    baseline_ndvi: Optional[np.ndarray] = None
    dem_slope: Optional[np.ndarray] = None


@dataclass
class GenerationResult:
    rgb: np.ndarray                        # (H, W, 3) synthesized future scene
    ndvi: Optional[np.ndarray] = None
    backend: str = "unknown"
    notes: Optional[list] = None


class BaseGenerator(ABC):
    """Contract every generator backend implements."""

    name: str = "base"

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Synthesize the future scene for one iteration."""

    def describe(self) -> str:
        return self.name


def get_generator(backend: Optional[str] = None) -> BaseGenerator:
    """Factory driven by settings.generator_backend."""
    from backend.config import settings

    choice = (backend or settings.generator_backend or "stub").lower()

    if choice == "stub":
        from backend.generator.stub import StubGenerator
        return StubGenerator()
    if choice == "local":
        from backend.generator.diffusion_local import LocalDiffusionGenerator
        return LocalDiffusionGenerator()
    if choice == "remote":
        from backend.generator.remote_client import RemoteGenerator
        return RemoteGenerator()
    raise ValueError(f"Unknown GENERATOR_BACKEND '{choice}' "
                     f"(expected stub | local | remote)")
