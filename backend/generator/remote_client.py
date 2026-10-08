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


class AdapterMismatchError(RemoteGeneratorError):
    """The server did not run the adapter state that was requested.

    Deterministic, so it is never retried.
    """


# ngrok free tier returns an HTML interstitial (ERR_NGROK_6024) to any
# request it thinks came from a browser. requests would then receive HTML
# where JSON was expected. This header opts out of the interstitial.
NGROK_HEADERS = {"ngrok-skip-browser-warning": "true"}


# colab_server.py protocol that understands use_lora and seed. An older
# server silently ignores both fields -- pydantic drops unknown keys -- so
# a "base" request would quietly run the fine-tuned adapter.
ABLATION_PROTOCOL = 2


class RemoteGenerator(BaseGenerator):
    name = "remote"

    def __init__(self, url: Optional[str] = None,
                 timeout_s: int = DEFAULT_TIMEOUT_S,
                 retries: int = 2,
                 use_lora: Optional[bool] = None,
                 seed: Optional[int] = None):
        """use_lora: None lets the server use its adapter if it has one;
        True/False forces it on or off and is verified against the reply.
        seed: None keeps the server default (42)."""
        self.url = (url or settings.remote_generator_url or "").rstrip("/")
        self.timeout_s = timeout_s
        self.retries = retries
        self.use_lora = use_lora
        self.seed = seed
        # Rejections accumulate across a run, exactly as the local and stub
        # backends do. The server is stateless and applies only the mask it
        # is sent; sending just the newest one lets water retracted on an
        # earlier pass reappear, and the loop oscillates instead of
        # converging.
        self._rejected_so_far: Optional[np.ndarray] = None
        if not self.url:
            raise RemoteGeneratorError(
                "REMOTE_GENERATOR_URL is not set. Start colab_server.py on "
                "Colab, expose it with ngrok, and put the https URL in .env.")

    def describe(self) -> str:
        adapter = {None: "", True: " +LoRA", False: " base"}[self.use_lora]
        return f"remote GPU{adapter} at {self.url}"

    def _cumulative_feedback(self, request: GenerationRequest
                             ) -> Optional[np.ndarray]:
        if request.iteration == 0:
            self._rejected_so_far = None
        if request.feedback_mask is not None:
            new = np.asarray(request.feedback_mask, dtype=bool)
            self._rejected_so_far = (new if self._rejected_so_far is None
                                     else self._rejected_so_far | new)
        return self._rejected_so_far

    def health(self) -> Dict[str, Any]:
        response = requests.get(f"{self.url}/health", timeout=30,
                                headers=NGROK_HEADERS)
        response.raise_for_status()
        return response.json()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        feedback = self._cumulative_feedback(request)
        payload = {
            "prompt": request.prompt,
            "iteration": request.iteration,
            "violations": request.violations or [],
            "baseline_rgb": encode_array(request.baseline_rgb),
            "conditioning_map": encode_array(request.conditioning_map),
            "change_mask": encode_array(request.change_mask),
            "feedback_mask": encode_array(
                None if feedback is None
                else np.asarray(feedback, dtype=np.float32)),
            "baseline_ndvi": encode_array(request.baseline_ndvi),
            "guidance": {
                k: v for k, v in (request.dynamics_guidance or {}).items()
                if isinstance(v, (int, float, str, bool))
            },
        }
        if self.use_lora is not None:
            payload["use_lora"] = self.use_lora
        if self.seed is not None:
            payload["seed"] = self.seed

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                started = time.time()
                response = requests.post(f"{self.url}/generate", json=payload,
                                         timeout=self.timeout_s,
                                         headers=NGROK_HEADERS)
                response.raise_for_status()
                body = response.json()
                elapsed = time.time() - started

                rgb = decode_array(body.get("rgb"))
                if rgb is None:
                    raise RemoteGeneratorError("Response contained no 'rgb'")
                self._check_adapter(body)

                notes = list(body.get("notes") or [])
                notes.append(f"Remote round-trip {elapsed:.1f}s "
                             f"(device={body.get('device', 'unknown')}).")
                return GenerationResult(
                    rgb=rgb, ndvi=decode_array(body.get("ndvi")),
                    backend=self.name, notes=notes)

            except AdapterMismatchError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Remote generate attempt %d/%d failed: %s",
                               attempt, self.retries, exc)

        raise RemoteGeneratorError(
            f"Remote generator at {self.url} failed after {self.retries} "
            f"attempts: {last_error}")

    def _check_adapter(self, body: Dict[str, Any]) -> None:
        """Refuse a reply that did not honour use_lora.

        Without this, an outdated server would run the adapter for a request
        that asked for the base model, and the ablation's base arms would
        silently be fine-tuned arms.
        """
        if self.use_lora is None:
            return
        active = body.get("adapter_active")
        if active is None:
            raise AdapterMismatchError(
                "Colab server ignored use_lora: it predates ablation "
                f"protocol {ABLATION_PROTOCOL}. Re-upload colab_server.py "
                "and restart the server cell.")
        if bool(active) != self.use_lora:
            raise AdapterMismatchError(
                f"Requested use_lora={self.use_lora} but the server ran with "
                f"adapter_active={active}.")
