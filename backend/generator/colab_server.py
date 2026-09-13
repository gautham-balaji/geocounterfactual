"""Colab-side GPU server for Compute Option A.

Runs INSIDE a Google Colab T4 notebook, not on the dev machine. It wraps the
same LocalDiffusionGenerator logic in FastAPI and speaks the wire format in
remote_client.py, so `GENERATOR_BACKEND=remote` swaps compute without any
change to the graph.

This file is deliberately self-contained -- it imports nothing from the rest
of `backend/`, because Colab will only have this one file uploaded. The
duplication with diffusion_local.py is intentional and worth it: the
alternative is installing rasterio, earthengine-api and the whole data engine
on a GPU runtime that only needs to run a UNet.

Deployment is documented at the bottom of this file and in the Phase 4 notes.
"""

from __future__ import annotations

import base64
import io
import time
from typing import Any, Dict, List, Optional

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI
from PIL import Image
from pydantic import BaseModel

MODEL_ID = "stable-diffusion-v1-5/stable-diffusion-inpainting"
CONTROLNET_CANNY = "lllyasviel/control_v11p_sd15_canny"

# Must match backend/config.py generation_patch_span_m / _px and the
# extract_pairs run that produced the training set. The adapter is only
# valid at the scale it was trained on.
PATCH_SPAN_M = 1280
PATCH_PX = 512
SCALE_M = 10
MAX_PATCHES = 8
LORA_PATH = "/content/geocf_lora.safetensors"   # upload alongside this file
LORA_SCALE = 0.85

NEGATIVE_PROMPT = (
    "blurry, distorted, cartoon, painting, illustration, text, watermark, "
    "buildings on water, water on hillside, lake on slope, unnatural colours, "
    "oversaturated green, uniform flat texture"
)
FEEDBACK_NEGATIVE = ("water on steep terrain, reservoir on a ridge, "
                     "floating water, vegetation on bare rock")

app = FastAPI(title="GeoCounterfactual GPU Generator")
_PIPE = None


# --------------------------------------------------------------------------
# Wire format (must mirror backend/generator/remote_client.py exactly)
# --------------------------------------------------------------------------

class ArrayPayload(BaseModel):
    dtype: str
    shape: List[int]
    data: str


class GenerateRequest(BaseModel):
    prompt: str
    iteration: int = 0
    violations: List[str] = []
    baseline_rgb: ArrayPayload
    conditioning_map: ArrayPayload
    change_mask: ArrayPayload
    feedback_mask: Optional[ArrayPayload] = None
    baseline_ndvi: Optional[ArrayPayload] = None
    guidance: Dict[str, Any] = {}


def decode(payload: Optional[ArrayPayload]) -> Optional[np.ndarray]:
    if payload is None:
        return None
    raw = base64.b64decode(payload.data)
    return np.frombuffer(raw, dtype=np.dtype(payload.dtype)).reshape(
        payload.shape).copy()


def encode(array: Optional[np.ndarray]) -> Optional[Dict[str, Any]]:
    if array is None:
        return None
    arr = np.ascontiguousarray(array, dtype=np.float32)
    return {"dtype": "float32", "shape": list(arr.shape),
            "data": base64.b64encode(arr.tobytes()).decode("ascii")}


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def get_pipeline():
    global _PIPE
    if _PIPE is not None:
        return _PIPE

    from diffusers import (ControlNetModel,
                           StableDiffusionControlNetInpaintPipeline,
                           UniPCMultistepScheduler)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    # SD1.5-inpainting ships safetensors only under variant="fp16"; its fp32
    # copies are pickled .bin, which transformers >= 5 refuses to load under
    # torch < 2.6 (CVE-2025-32434). Always request the fp16 safetensors and
    # let torch_dtype decide the compute precision.
    controlnet = ControlNetModel.from_pretrained(CONTROLNET_CANNY,
                                                 torch_dtype=dtype,
                                                 use_safetensors=True)
    pipe = StableDiffusionControlNetInpaintPipeline.from_pretrained(
        MODEL_ID, controlnet=controlnet, torch_dtype=dtype,
        variant="fp16", use_safetensors=True,
        safety_checker=None, requires_safety_checker=False)
    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)

    import os
    if os.path.isfile(LORA_PATH):
        from safetensors.torch import load_file
        raw = load_file(LORA_PATH)
        # get_peft_model_state_dict exports UNet-relative keys; without the
        # "unet." prefix diffusers logs a warning, activates nothing, and
        # silently runs the base model.
        prefixed = {(k if k.startswith("unet.") else f"unet.{k}"): v
                    for k, v in raw.items()}
        pipe.load_lora_weights(prefixed, adapter_name="geocf")
        active = pipe.get_active_adapters()
        if not active:
            raise RuntimeError("LoRA loaded no adapters; refusing to run as "
                               "if fine-tuned.")
        pipe.set_adapters(active, adapter_weights=[LORA_SCALE])
        print("LoRA active:", active, "@", LORA_SCALE)

    pipe = pipe.to(device)
    pipe.set_progress_bar_config(disable=True)
    if device == "cuda":
        # A T4 has 16 GB but Colab shares it; slicing keeps headroom.
        pipe.enable_attention_slicing()
    _PIPE = pipe
    return pipe


def plan_windows(editable, span_px, max_patches=MAX_PATCHES):
    """1280 m windows covering the editable region, largest blob first."""
    from scipy import ndimage
    h, w = editable.shape
    labels, n = ndimage.label(
        editable, structure=ndimage.generate_binary_structure(2, 2))
    if n == 0:
        return []
    sizes = ndimage.sum(editable, labels, range(1, n + 1))
    centres = ndimage.center_of_mass(editable, labels, range(1, n + 1))
    windows, covered = [], np.zeros_like(editable, dtype=bool)
    for idx in np.argsort(sizes)[::-1]:
        if len(windows) >= max_patches:
            break
        blob = labels == (idx + 1)
        if covered[blob].mean() > 0.8:
            continue
        cy, cx = centres[idx]
        r0 = int(np.clip(round(cy) - span_px // 2, 0, max(0, h - span_px)))
        c0 = int(np.clip(round(cx) - span_px // 2, 0, max(0, w - span_px)))
        r1, c1 = min(h, r0 + span_px), min(w, c0 + span_px)
        windows.append((r0, c0, r1, c1))
        covered[r0:r1, c0:c1] = True
    return windows


def round8(n: int) -> int:
    return int(np.ceil(n / 8.0) * 8)


def to_uint8(rgb: np.ndarray):
    lo = np.zeros(3, dtype=np.float32)
    hi = np.ones(3, dtype=np.float32)
    out = np.zeros(rgb.shape, dtype=np.float32)
    for c in range(3):
        band = rgb[:, :, c]
        finite = band[np.isfinite(band)]
        if finite.size:
            lo[c], hi[c] = np.percentile(finite, [2, 98])
        if hi[c] - lo[c] < 1e-9:
            hi[c] = lo[c] + 1e-6
        out[:, :, c] = np.clip((band - lo[c]) / (hi[c] - lo[c]), 0, 1)
    return Image.fromarray((out * 255).astype(np.uint8)), lo, hi


def from_uint8(img: Image.Image, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    arr = np.asarray(img, dtype=np.float32) / 255.0
    out = np.zeros(arr.shape, dtype=np.float32)
    for c in range(3):
        out[:, :, c] = arr[:, :, c] * (hi[c] - lo[c]) + lo[c]
    return np.clip(out, 0.0, 1.0)


def fit_ndvi(baseline_rgb, baseline_ndvi):
    if baseline_ndvi is None:
        return None
    rgb = np.asarray(baseline_rgb, dtype=np.float64).reshape(-1, 3)
    y = np.asarray(baseline_ndvi, dtype=np.float64).reshape(-1)
    good = np.isfinite(y) & np.all(np.isfinite(rgb), axis=1)
    if good.sum() < 100:
        return None
    rgb, y = rgb[good], y[good]
    design = np.column_stack([np.ones(len(rgb)), rgb, rgb ** 2,
                              rgb[:, 0] * rgb[:, 1], rgb[:, 1] * rgb[:, 2],
                              rgb[:, 0] * rgb[:, 2]])
    coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
    return coeffs


def apply_ndvi(coeffs, rgb):
    if coeffs is None:
        return np.zeros(rgb.shape[:2], dtype=np.float32)
    flat = np.asarray(rgb, dtype=np.float64).reshape(-1, 3)
    design = np.column_stack([np.ones(len(flat)), flat, flat ** 2,
                              flat[:, 0] * flat[:, 1], flat[:, 1] * flat[:, 2],
                              flat[:, 0] * flat[:, 2]])
    return np.clip(design @ coeffs, -1, 1).reshape(rgb.shape[:2]).astype(
        np.float32)


def predict_ndvi(baseline_rgb, generated_rgb, baseline_ndvi):
    """NDVI anchored on the measured baseline; see diffusion_local._predict_ndvi.

    Must stay identical to the local backend. Returning the raw regression
    estimate instead makes the fit's residual look like vegetation growth,
    and rule 2 then rejects terrain the generator never touched.
    """
    if baseline_ndvi is None:
        return np.zeros(generated_rgb.shape[:2], dtype=np.float32)
    coeffs = fit_ndvi(baseline_rgb, baseline_ndvi)
    if coeffs is None:
        return np.asarray(baseline_ndvi, dtype=np.float32).copy()
    delta = apply_ndvi(coeffs, generated_rgb) - apply_ndvi(coeffs, baseline_rgb)
    return np.clip(np.asarray(baseline_ndvi, dtype=np.float32) + delta,
                   -1.0, 1.0).astype(np.float32)


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "gpu": (torch.cuda.get_device_name(0)
                if torch.cuda.is_available() else None),
        "pipeline_loaded": _PIPE is not None,
        "torch": torch.__version__,
    }


@app.post("/generate")
def generate(req: GenerateRequest):
    from skimage.feature import canny

    t_start = time.time()
    base_rgb = decode(req.baseline_rgb)
    cond = decode(req.conditioning_map)
    change_mask = decode(req.change_mask)
    feedback = decode(req.feedback_mask)
    baseline_ndvi = decode(req.baseline_ndvi)

    h, w = base_rgb.shape[:2]

    editable = np.asarray(change_mask, dtype=np.float32) > 0
    if feedback is not None:
        editable = editable & ~(np.asarray(feedback) > 0)

    notes = []

    if not editable.any():
        return {"rgb": encode(base_rgb),
                "ndvi": encode(predict_ndvi(base_rgb, base_rgb, baseline_ndvi)),
                "notes": ["Editable region empty; baseline returned."],
                "device": "cuda" if torch.cuda.is_available() else "cpu"}

    _, lo, hi = to_uint8(base_rgb)

    negative = NEGATIVE_PROMPT
    if feedback is not None and np.any(feedback):
        negative = f"{NEGATIVE_PROMPT}, {FEEDBACK_NEGATIVE}"
        notes.append(f"Critic feedback: {int((feedback > 0).sum())} px locked.")

    pipe = get_pipeline()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    generator = torch.Generator(device=device).manual_seed(42 + req.iteration)

    t0 = time.time()
    # Structure only, not the riparian buffer: the adapter trained on masks
    # covering 0.8-3.5% of the frame, and the full footprint is ~43%.
    core = (np.asarray(change_mask, dtype=np.float32) >= 1.0)
    if feedback is not None:
        core = core & ~(np.asarray(feedback) > 0)
    patch_mask = core if core.any() else editable
    span_px = max(8, PATCH_SPAN_M // SCALE_M)
    windows = plan_windows(patch_mask, span_px)
    generated = base_rgb.copy()

    for (r0, c0, r1, c1) in windows:
        win_mask = patch_mask[r0:r1, c0:c1]
        if not win_mask.any():
            continue
        win_rgb = base_rgb[r0:r1, c0:c1]
        wi, _, _ = to_uint8(win_rgb)
        wi = wi.resize((PATCH_PX, PATCH_PX), Image.BILINEAR)
        wm = Image.fromarray((win_mask * 255).astype(np.uint8)).resize(
            (PATCH_PX, PATCH_PX), Image.NEAREST)
        we = canny(cond[r0:r1, c0:c1, 0].astype(np.float64),
                   sigma=1.6).astype(np.float32)
        wc = Image.fromarray((np.dstack([we] * 3) * 255).astype(np.uint8)).resize(
            (PATCH_PX, PATCH_PX), Image.NEAREST)

        out = pipe(prompt=req.prompt, negative_prompt=negative,
                   image=wi, mask_image=wm, control_image=wc,
                   num_inference_steps=20, guidance_scale=7.5,
                   controlnet_conditioning_scale=0.8, strength=0.85,
                   height=PATCH_PX, width=PATCH_PX, generator=generator)
        # Scene-wide stretch bounds, not per-window: per-window bounds make
        # each patch tone-shift against its surroundings.
        native = out.images[0].resize((c1 - c0, r1 - r0), Image.BILINEAR)
        patch = from_uint8(native, lo, hi)
        sel = win_mask.astype(bool)
        for c in range(3):
            generated[r0:r1, c0:c1, c][sel] = patch[:, :, c][sel]

    infer_s = time.time() - t0
    notes.append(f"{len(windows)} window(s) of {PATCH_SPAN_M} m at {PATCH_PX} px")

    notes.append(f"GPU inference {infer_s:.1f}s over {len(windows)} patch(es); "
                 f"total {time.time() - t_start:.1f}s.")
    return {"rgb": encode(generated),
            "ndvi": encode(predict_ndvi(base_rgb, generated, baseline_ndvi)),
            "notes": notes, "device": device}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ==========================================================================
# COLAB DEPLOYMENT
# ==========================================================================
#
# Runtime > Change runtime type > T4 GPU, then run these cells:
#
# 1) Dependencies
#    !pip install -q diffusers==0.40.0 transformers accelerate safetensors \
#                   fastapi uvicorn nest-asyncio pyngrok scikit-image
#
# 2) Upload this file (Files pane, or):
#    from google.colab import files; files.upload()      # colab_server.py
#
# 3) Authenticate ngrok (free account -> dashboard.ngrok.com, copy authtoken)
#    !ngrok config add-authtoken YOUR_TOKEN
#
# 4) Launch the server and open the tunnel
#    import nest_asyncio, uvicorn, threading
#    from pyngrok import ngrok
#    from colab_server import app
#    nest_asyncio.apply()
#    tunnel = ngrok.connect(8000, "http")
#    print("PUBLIC URL:", tunnel.public_url)
#    threading.Thread(
#        target=lambda: uvicorn.run(app, host="0.0.0.0", port=8000),
#        daemon=True).start()
#
# 5) Warm the weights once, so the first real request is not a cold start
#    !curl -s http://localhost:8000/health
#
# 6) On this machine, put the printed URL in .env and switch backends:
#    GENERATOR_BACKEND=remote
#    REMOTE_GENERATOR_URL=https://<something>.ngrok-free.app
#
# Caveats
#  * A free ngrok URL changes every restart -- update .env each session.
#  * Colab disconnects after ~90 min idle; the tunnel dies with it.
#  * Verify the GPU is actually in use: /health must report device "cuda".
#    If it says "cpu", the runtime type was never switched to T4 and you are
#    paying network latency for no speedup.
# ==========================================================================
