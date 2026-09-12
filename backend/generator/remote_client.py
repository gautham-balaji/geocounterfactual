"""Remote backend: offload synthesis to a Colab T4 (Compute Option A).

Satisfies the same BaseGenerator contract as the local CPU backend, so the
LangGraph node is unchanged by where the GPU lives.

Wire format: float32 arrays are sent as base64-encoded raw buffers plus an
explicit shape and dtype, NOT as PNGs. Encoding to PNG would quantise
reflectance to 8 bits and silently destroy the precision every Critic
threshold depends on; NDVI differences of 0.02 matter to rule 2.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any, Dict, Optional

import numpy as np
import requests

from backend.config import settings
from backend.generator.base import (BaseGenerator, GenerationRequest,
                                    GenerationResult)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 600


def encode_array(array: Optional[np.ndarray]) -> Optional[Dict[str, Any]]:
    """Pack a numpy array losslessly for JSON transport."""
    if array is None:
        return None
    arr = np.ascontiguousarray(array, dtype=np.float32)
    return {
        "dtype": "float32",
        "shape": list(arr.shape),
        "data": base64.b64encode(arr.tobytes()).decode("ascii"),
    }


def decode_array(payload: Optional[Dict[str, Any]]) -> Optional[np.ndarray]:
    if not payload:
        return None
    raw = base64.b64decode(payload["data"])
    return np.frombuffer(raw, dtype=np.dtype(payload["dtype"])).reshape(
        payload["shape"]).copy()


class RemoteGeneratorError(RuntimeError):
    pass


class RemoteGenerator(BaseGenerator):
    name = "remote"

    def __init__(self, url: Optional[str] = None,
                 timeout_s: int = DEFAULT_TIMEOUT_S,
                 retries: int = 2):
        self.url = (url or settings.remote_generator_url or "").rstrip("/")
        self.timeout_s = timeout_s
        self.retries = retries
        if not self.url:
            raise RemoteGeneratorError(
                "REMOTE_GENERATOR_URL is not set. Start colab_server.py on "
                "Colab, expose it with ngrok, and put the https URL in .env.")

    def describe(self) -> str:
        return f"remote GPU at {self.url}"

    def health(self) -> Dict[str, Any]:
        response = requests.get(f"{self.url}/health", timeout=30)
        response.raise_for_status()
        return response.json()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = {
            "prompt": request.prompt,
            "iteration": request.iteration,
            "violations": request.violations or [],
            "baseline_rgb": encode_array(request.baseline_rgb),
            "conditioning_map": encode_array(request.conditioning_map),
            "change_mask": encode_array(request.change_mask),
            "feedback_mask": encode_array(
                None if request.feedback_mask is None
                else np.asarray(request.feedback_mask, dtype=np.float32)),
            "baseline_ndvi": encode_array(request.baseline_ndvi),
            "guidance": {
                k: v for k, v in (request.dynamics_guidance or {}).items()
                if isinstance(v, (int, float, str, bool))
            },
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                started = time.time()
                response = requests.post(f"{self.url}/generate", json=payload,
                                         timeout=self.timeout_s)
                response.raise_for_status()
                body = response.json()
                elapsed = time.time() - started

                rgb = decode_array(body.get("rgb"))
                if rgb is None:
                    raise RemoteGeneratorError("Response contained no 'rgb'")

                notes = list(body.get("notes") or [])
                notes.append(f"Remote round-trip {elapsed:.1f}s "
                             f"(device={body.get('device', 'unknown')}).")
                return GenerationResult(
                    rgb=rgb, ndvi=decode_array(body.get("ndvi")),
                    backend=self.name, notes=notes)

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Remote generate attempt %d/%d failed: %s",
                               attempt, self.retries, exc)

        raise RemoteGeneratorError(
            f"Remote generator at {self.url} failed after {self.retries} "
            f"attempts: {last_error}")
