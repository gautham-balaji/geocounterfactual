"""Local CPU backend: Stable Diffusion 1.5 inpainting + ControlNet.

Runs the same contract as the remote Colab backend (Compute Option A), so the
LangGraph node cannot tell which is executing.

Three problems have to be solved to put a satellite raster through an RGB
diffusion model and get something the Critic can judge:

1. UNITS. Sentinel-2 gives surface reflectance in [0, 1]; the pipeline wants
   8-bit sRGB. A naive round-trip loses the mapping, and every Critic
   threshold (NDWI, red-edge, water colour) is expressed in reflectance. So
   the per-channel percentile stretch used on the way in is retained and
   inverted on the way out.

2. GEOMETRY. SD needs dimensions divisible by 8. The scene is 448x436, so it
   is padded to 448x440 and cropped back, rather than resampled to 512 --
   resampling would blur field boundaries and cost SSIM under rule 4.

3. NIR. Diffusion emits three channels; NDVI needs NIR. A per-scene
   reflectance->NDVI regression is fitted on the BASELINE, where both are
   known, and applied to the generated frame. See _fit_ndvi_model for why
   this keeps rules 2 and 3 meaningful, and where it is weaker than a true
   multispectral generator.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.feature import canny

from backend.config import settings
from backend.generator.base import (BaseGenerator, GenerationRequest,
                                    GenerationResult)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "stable-diffusion-v1-5/stable-diffusion-inpainting"
CONTROLNET_CANNY = "lllyasviel/control_v11p_sd15_canny"
CONTROLNET_DEPTH = "lllyasviel/control_v11f1p_sd15_depth"

NEGATIVE_PROMPT = (
    "blurry, distorted, cartoon, painting, illustration, text, watermark, "
    "buildings on water, water on hillside, lake on slope, unnatural colours, "
    "oversaturated green, uniform flat texture"
)

# Appended when the critic has rejected a previous attempt.
FEEDBACK_NEGATIVE = ("water on steep terrain, reservoir on a ridge, "
                     "floating water, vegetation on bare rock")


def _round8(n: int) -> int:
    return int(np.ceil(n / 8.0) * 8)


class LocalDiffusionGenerator(BaseGenerator):
    name = "local"

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        conditioning_mode: str = "canny",     # "canny" | "depth"
        num_inference_steps: int = 20,
        guidance_scale: float = 7.5,
        controlnet_conditioning_scale: float = 0.8,
        strength: float = 0.85,
        max_dimension: int = 512,
        composite_unchanged: bool = True,
        seed: int = 42,
        device: str = "cpu",
        patch_mode: Optional[bool] = None,
        lora_path: Optional[str] = None,
    ):
        self.model_id = model_id
        self.conditioning_mode = conditioning_mode
        self.num_inference_steps = num_inference_steps
        self.guidance_scale = guidance_scale
        self.controlnet_conditioning_scale = controlnet_conditioning_scale
        self.strength = strength
        self.max_dimension = max_dimension
        self.composite_unchanged = composite_unchanged
        self.seed = seed
        self.device = device
        # Patch mode is on whenever a fine-tuned adapter exists, because the
        # adapter is only valid at the scale it was trained on.
        self.lora_path = (lora_path if lora_path is not None
                          else (str(settings.lora_weights_path)
                                if settings.lora_weights_path
                                and Path(settings.lora_weights_path).is_file()
                                else None))
        self.patch_mode = (bool(self.lora_path) if patch_mode is None
                           else patch_mode)
        self._pipe = None
        self._rejected_so_far: Optional[np.ndarray] = None

    def describe(self) -> str:
        mode = (f"patch {settings.generation_patch_span_m}m"
                if self.patch_mode else "whole-scene")
        lora = "+LoRA" if self.lora_path else "base"
        return (f"local SD1.5-inpaint{lora} "
                f"+ ControlNet-{self.conditioning_mode} "
                f"@{self.num_inference_steps} steps, {mode}, {self.device}")

    # -- model ------------------------------------------------------------

    def _load_pipeline(self):
        """Lazy load; weights are ~4 GB and must not be fetched at import."""
        if self._pipe is not None:
            return self._pipe

        import torch
        from diffusers import (ControlNetModel,
                               StableDiffusionControlNetInpaintPipeline,
                               UniPCMultistepScheduler)

        controlnet_id = (CONTROLNET_DEPTH if self.conditioning_mode == "depth"
                         else CONTROLNET_CANNY)
        logger.info("Loading %s + %s on %s", self.model_id, controlnet_id,
                    self.device)
        t0 = time.time()

        # Compute in float32: torch's CPU backend lacks float16 kernels for
        # several ops in this pipeline.
        #
        # But the WEIGHTS must come from safetensors, and SD1.5-inpainting
        # publishes safetensors only in its fp16 variant (the fp32 copies are
        # pickled .bin). transformers >= 5 refuses to torch.load a .bin under
        # torch < 2.6 (CVE-2025-32434), so requesting the default fp32 files
        # aborts the load outright. Pulling variant="fp16" and upcasting via
        # torch_dtype=float32 sidesteps torch.load entirely, keeps full-
        # precision compute, and halves the download.
        controlnet = ControlNetModel.from_pretrained(
            controlnet_id, torch_dtype=torch.float32, use_safetensors=True)
        pipe = StableDiffusionControlNetInpaintPipeline.from_pretrained(
            self.model_id, controlnet=controlnet, torch_dtype=torch.float32,
            variant="fp16", use_safetensors=True,
            safety_checker=None, requires_safety_checker=False)

        # UniPC converges in far fewer steps than PNDM, which matters a great
        # deal when each step costs seconds on CPU.
        pipe.scheduler = UniPCMultistepScheduler.from_config(
            pipe.scheduler.config)
        pipe = pipe.to(self.device)
        pipe.set_progress_bar_config(disable=True)
        if self.device == "cpu":
            pipe.enable_attention_slicing()   # trades a little speed for RAM

        if self.lora_path:
            from safetensors.torch import load_file
            raw = load_file(self.lora_path)
            # get_peft_model_state_dict(unet) exports keys relative to the
            # UNet, but load_lora_weights looks for a "unet." prefix. Without
            # it diffusers logs "No LoRA keys associated to
            # UNet2DConditionModel", leaves active_adapters empty, and runs
            # the BASE model -- a silent no-op rather than an error.
            prefixed = {(k if k.startswith("unet.") else f"unet.{k}"): v
                        for k, v in raw.items()}
            pipe.load_lora_weights(prefixed, adapter_name="geocf")
            active = pipe.get_active_adapters()
            if not active:
                raise RuntimeError(
                    f"LoRA at {self.lora_path} loaded no adapters; refusing "
                    f"to run as if fine-tuned.")
            pipe.set_adapters(active, adapter_weights=[settings.lora_scale])
            logger.info("LoRA active: %s @ %.2f", active, settings.lora_scale)

        logger.info("Pipeline ready in %.1fs", time.time() - t0)
        self._pipe = pipe
        return pipe

    # -- units -------------------------------------------------------------

    @staticmethod
    def _to_uint8(rgb: np.ndarray) -> Tuple[Image.Image, np.ndarray, np.ndarray]:
        """Reflectance -> 8-bit sRGB, returning the stretch bounds to invert."""
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

    @staticmethod
    def _from_uint8(img: Image.Image, lo: np.ndarray,
                    hi: np.ndarray) -> np.ndarray:
        """Invert the stretch so the Critic sees reflectance, not sRGB."""
        arr = np.asarray(img, dtype=np.float32) / 255.0
        out = np.zeros(arr.shape, dtype=np.float32)
        for c in range(3):
            out[:, :, c] = arr[:, :, c] * (hi[c] - lo[c]) + lo[c]
        return np.clip(out, 0.0, 1.0)

    # -- conditioning ------------------------------------------------------

    def _control_image(self, request: GenerationRequest,
                       size: Tuple[int, int]) -> Image.Image:
        """Build the 3-channel ControlNet hint.

        canny: edges of the baseline scene. Directly serves rule 4 -- field
               boundaries, roads and parcel edges are the structure that must
               survive outside the intervention footprint.
        depth: normalised DEM. Encodes the topographic constraint from spec
               5.1, but over a 4 km tile with ~100 m of relief the gradient
               is gentle and guides weakly, so canny is the default.
        """
        cond = np.asarray(request.conditioning_map, dtype=np.float32)
        luminance, slope_norm = cond[:, :, 0], cond[:, :, 1]

        if self.conditioning_mode == "depth":
            hint = np.clip(slope_norm, 0, 1)
            stack = np.dstack([hint, hint, hint])
        else:
            edges = canny(luminance.astype(np.float64), sigma=1.6)
            e = edges.astype(np.float32)
            stack = np.dstack([e, e, e])

        img = Image.fromarray((stack * 255).astype(np.uint8))
        return img.resize(size, Image.NEAREST)

    def _inpaint_mask(self, request: GenerationRequest) -> np.ndarray:
        """Where the model may repaint.

        The intervention footprint, MINUS anything the Critic rejected. This
        is the concrete meaning of "penalise the feedback mask": rejected
        pixels are removed from the editable region, so they revert to the
        untouched baseline instead of being regenerated. Combined with the
        strengthened negative prompt, a rejection both forbids the region and
        tells the model what it got wrong.
        """
        mask = np.asarray(request.change_mask, dtype=np.float32) > 0

        # Rejections must ACCUMULATE. critic_feedback_mask carries only the
        # current pass, so applying it alone lets pixels corrected at
        # iteration 1 become editable again at iteration 3 -- the oscillation
        # (57800 -> 2700 -> 4800 m2) diagnosed in Phase 3. The stub was fixed
        # then; the real backends were not.
        if request.iteration == 0:
            self._rejected_so_far = None
        if request.feedback_mask is not None:
            new_rejects = np.asarray(request.feedback_mask, dtype=bool)
            self._rejected_so_far = (new_rejects if self._rejected_so_far is None
                                     else self._rejected_so_far | new_rejects)
        if self._rejected_so_far is not None:
            mask = mask & ~self._rejected_so_far
        return mask

    # -- NDVI --------------------------------------------------------------

    @staticmethod
    def _fit_ndvi_model(baseline_rgb: np.ndarray,
                        baseline_ndvi: np.ndarray) -> Optional[np.ndarray]:
        """Least-squares reflectance -> NDVI fit on the baseline scene.

        An RGB backbone cannot emit NIR, so NDVI has to be inferred. Fitting
        on the baseline -- where real reflectance and real NDVI are both
        known -- ties the estimate to this scene's actual vegetation rather
        than to a generic assumption.

        What this preserves and what it costs:
          * Rule 2 stays meaningful: painting a canopy brighter/greener than
            anything in the baseline extrapolates to an NDVI above the
            growth ceiling, and the rule fires.
          * Rule 3 stays partially meaningful: the fit uses all three bands,
            so an out-of-distribution green (high G AND high B, unlike real
            chlorophyll) maps to a low NDVI while visible greenness is high
            -- exactly the paint signature.
          * But it is weaker than a true multispectral generator. NDVI is
            now a function of RGB, so rule 3 cannot catch a hallucination
            that happens to have realistic RGB statistics. Emitting a real
            NIR band would need a 4-channel fine-tune; noted as a limitation.
        """
        if baseline_ndvi is None:
            return None
        rgb = np.asarray(baseline_rgb, dtype=np.float64).reshape(-1, 3)
        y = np.asarray(baseline_ndvi, dtype=np.float64).reshape(-1)
        good = np.isfinite(y) & np.all(np.isfinite(rgb), axis=1)
        if good.sum() < 100:
            return None
        rgb, y = rgb[good], y[good]
        # Quadratic terms: the reflectance-NDVI relation is not linear.
        design = np.column_stack([
            np.ones(len(rgb)), rgb, rgb ** 2,
            rgb[:, 0] * rgb[:, 1], rgb[:, 1] * rgb[:, 2], rgb[:, 0] * rgb[:, 2],
        ])
        coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
        return coeffs

    @staticmethod
    def _apply_ndvi_model(coeffs: Optional[np.ndarray],
                          rgb: np.ndarray) -> np.ndarray:
        if coeffs is None:
            return np.zeros(rgb.shape[:2], dtype=np.float32)
        flat = np.asarray(rgb, dtype=np.float64).reshape(-1, 3)
        design = np.column_stack([
            np.ones(len(flat)), flat, flat ** 2,
            flat[:, 0] * flat[:, 1], flat[:, 1] * flat[:, 2],
            flat[:, 0] * flat[:, 2],
        ])
        return np.clip(design @ coeffs, -1.0, 1.0).reshape(
            rgb.shape[:2]).astype(np.float32)

    @classmethod
    def _predict_ndvi(cls, baseline_rgb: np.ndarray, generated_rgb: np.ndarray,
                      baseline_ndvi: Optional[np.ndarray]) -> np.ndarray:
        """Candidate NDVI, anchored on the measured baseline.

            NDVI_future = NDVI_baseline_measured
                          + ( f(RGB_future) - f(RGB_baseline) )

        Using f(RGB_future) directly is wrong, and wrong in a way that
        quietly breaks the Critic. Rule 2 compares candidate NDVI against the
        MEASURED baseline, so any regression residual -- the fit is good, not
        perfect -- reads as vegetation growth. Measured on the first real run
        that produced 45659 rule-2 violations on a frame where the generator
        had altered only 7129 pixels: the critic was rejecting untouched
        terrain for the fit's error.

        Differencing cancels the residual. Where the generator changed
        nothing, f(RGB_future) == f(RGB_baseline) exactly, the delta is zero,
        and the candidate NDVI is the measured baseline to the bit. Rule 2
        then sees only the change the generator actually made.
        """
        if baseline_ndvi is None:
            return np.zeros(generated_rgb.shape[:2], dtype=np.float32)
        coeffs = cls._fit_ndvi_model(baseline_rgb, baseline_ndvi)
        if coeffs is None:
            return np.asarray(baseline_ndvi, dtype=np.float32).copy()
        delta = (cls._apply_ndvi_model(coeffs, generated_rgb)
                 - cls._apply_ndvi_model(coeffs, baseline_rgb))
        return np.clip(np.asarray(baseline_ndvi, dtype=np.float32) + delta,
                       -1.0, 1.0).astype(np.float32)


    # -- patch planning ----------------------------------------------------

    def _windows(self, editable: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Pick 1280 m windows covering the editable region.

        Derived from the mask rather than from target_stream_coords so this
        works for every intervention type -- afforestation sites no dams and
        would otherwise get no windows at all.

        Windows are centred on connected components, largest first, and a
        component already covered by an accepted window is skipped so three
        adjacent pool fragments do not become three near-identical passes.
        """
        span_px = max(8, settings.generation_patch_span_m // settings.target_scale_m)
        h, w = editable.shape
        labels, n = ndimage.label(
            editable, structure=ndimage.generate_binary_structure(2, 2))
        if n == 0:
            return []

        sizes = ndimage.sum(editable, labels, range(1, n + 1))
        order = np.argsort(sizes)[::-1]
        centres = ndimage.center_of_mass(editable, labels, range(1, n + 1))

        windows: List[Tuple[int, int, int, int]] = []
        covered = np.zeros_like(editable, dtype=bool)

        for idx in order:
            if len(windows) >= settings.max_patches_per_scene:
                break
            blob = labels == (idx + 1)
            # Skip if this component is already inside an accepted window.
            if covered[blob].mean() > 0.8:
                continue
            cy, cx = centres[idx]
            r0 = int(np.clip(round(cy) - span_px // 2, 0, max(0, h - span_px)))
            c0 = int(np.clip(round(cx) - span_px // 2, 0, max(0, w - span_px)))
            r1, c1 = min(h, r0 + span_px), min(w, c0 + span_px)
            windows.append((r0, c0, r1, c1))
            covered[r0:r1, c0:c1] = True

        return windows

    def _run_pipe(self, base_rgb, editable, cond, request, negative, lo, hi):
        """One inpainting pass over an arbitrary array, returning reflectance."""
        import torch

        out_px = settings.generation_patch_px
        img_u8, _, _ = self._to_uint8(base_rgb)
        base_img = img_u8.resize((out_px, out_px), Image.BILINEAR)
        mask_img = Image.fromarray((editable * 255).astype(np.uint8)).resize(
            (out_px, out_px), Image.NEAREST)

        if self.conditioning_mode == "depth":
            hint = np.clip(cond[:, :, 1], 0, 1)
        else:
            hint = canny(cond[:, :, 0].astype(np.float64), sigma=1.6).astype(np.float32)
        control_img = Image.fromarray(
            (np.dstack([hint] * 3) * 255).astype(np.uint8)).resize(
            (out_px, out_px), Image.NEAREST)

        pipe = self._load_pipeline()
        generator = torch.Generator(device=self.device).manual_seed(
            self.seed + request.iteration)
        result = pipe(
            prompt=request.prompt, negative_prompt=negative,
            image=base_img, mask_image=mask_img, control_image=control_img,
            num_inference_steps=self.num_inference_steps,
            guidance_scale=self.guidance_scale,
            controlnet_conditioning_scale=self.controlnet_conditioning_scale,
            strength=self.strength, height=out_px, width=out_px,
            generator=generator,
        ).images[0]

        # Back to the window's native pixel grid, then to reflectance using
        # the stretch bounds of the FULL scene, not this window: per-window
        # bounds would make each patch tone-shift against its surroundings.
        native = result.resize((base_rgb.shape[1], base_rgb.shape[0]),
                               Image.BILINEAR)
        return self._from_uint8(native, lo, hi)

    # -- generate ----------------------------------------------------------

    def generate(self, request: GenerationRequest) -> GenerationResult:
        import torch

        notes = []
        base_rgb = np.asarray(request.baseline_rgb, dtype=np.float32)
        h, w = base_rgb.shape[:2]

        # Pad to a multiple of 8 rather than resampling to 512.
        gen_h, gen_w = _round8(h), _round8(w)
        scale = min(1.0, self.max_dimension / max(gen_h, gen_w))
        if scale < 1.0:
            gen_h, gen_w = _round8(int(gen_h * scale)), _round8(int(gen_w * scale))
            notes.append(f"Downscaled to {gen_w}x{gen_h} to bound CPU cost.")

        base_img, lo, hi = self._to_uint8(base_rgb)
        base_img_r = base_img.resize((gen_w, gen_h), Image.BILINEAR)

        mask_arr = self._inpaint_mask(request)
        mask_img = Image.fromarray((mask_arr * 255).astype(np.uint8)).resize(
            (gen_w, gen_h), Image.NEAREST)
        control_img = self._control_image(request, (gen_w, gen_h))

        negative = NEGATIVE_PROMPT
        if request.feedback_mask is not None and np.any(request.feedback_mask):
            negative = f"{NEGATIVE_PROMPT}, {FEEDBACK_NEGATIVE}"
            notes.append(
                f"Critic feedback applied: {int(np.sum(request.feedback_mask))} "
                f"px removed from the editable region and added to the "
                f"negative prompt.")

        if not np.any(mask_arr):
            notes.append("Editable region is empty after critic feedback; "
                         "returning the baseline unchanged.")
            return GenerationResult(
                rgb=base_rgb.copy(),
                ndvi=self._predict_ndvi(base_rgb, base_rgb,
                                        request.baseline_ndvi),
                backend=self.name, notes=notes)

        # ---- patch mode ---------------------------------------------------
        # The adapter was trained on 1280 m rendered to 512 px (2.5 m/px).
        # Running it over a whole 4.4 km scene resized to ~448 px would be
        # 10 m/px, a 4x scale mismatch against everything it learned. So we
        # generate per-window at the training scale and composite back.
        if self.patch_mode:
            # Inpaint the STRUCTURE, not the whole footprint.
            #
            # The change mask is core impoundment plus a ~150 m riparian
            # buffer, which is 43.5% of a 1280 m window. The adapter was
            # trained on centred ellipses covering 0.8-3.5% of the frame, so
            # handing it 43.5% is a different task entirely: measured output
            # was amorphous blobs with the underlying field texture
            # destroyed. Restricted to the core the mask is 1.1%, inside the
            # training distribution.
            #
            # The buffer is a vegetation response, not a built structure;
            # it is handled by the dynamics-driven greening rather than by
            # the diffusion model.
            core = np.asarray(request.change_mask, dtype=np.float32) >= 1.0
            if self._rejected_so_far is not None:
                core = core & ~self._rejected_so_far
            patch_mask = core if core.any() else mask_arr
            if core.any():
                notes.append(
                    f"Inpainting the impoundment core only "
                    f"({100 * core.mean():.2f}% of scene); the riparian "
                    f"buffer is left to the dynamics greening.")
            else:
                notes.append("No impoundment core; adapter is out of "
                             "distribution for this intervention type.")

            windows = self._windows(patch_mask)
            if not windows:
                notes.append("No window covers the editable region; "
                             "returning the baseline unchanged.")
                return GenerationResult(
                    rgb=base_rgb.copy(),
                    ndvi=self._predict_ndvi(base_rgb, base_rgb,
                                            request.baseline_ndvi),
                    backend=self.name, notes=notes)

            cond_full = np.asarray(request.conditioning_map, dtype=np.float32)
            generated = base_rgb.copy()
            started = time.time()

            for n, (r0, c0, r1, c1) in enumerate(windows, 1):
                win_mask = patch_mask[r0:r1, c0:c1]
                if not win_mask.any():
                    continue
                patch = self._run_pipe(
                    base_rgb[r0:r1, c0:c1], win_mask,
                    cond_full[r0:r1, c0:c1], request, negative, lo, hi)
                # Composite only inside the editable region of this window,
                # so neighbouring windows cannot overwrite each other's
                # untouched context and leave visible seams.
                sel = win_mask.astype(bool)
                for ch in range(3):
                    generated[r0:r1, c0:c1, ch][sel] = patch[:, :, ch][sel]

            elapsed = time.time() - started
            span = settings.generation_patch_span_m
            notes.append(
                f"Patch mode: {len(windows)} window(s) of {span} m at "
                f"{settings.generation_patch_px} px in {elapsed:.1f}s "
                f"({elapsed / max(len(windows), 1):.1f}s each).")
            if self.lora_path:
                notes.append(f"Fine-tuned adapter applied at scale "
                             f"{settings.lora_scale}.")

            ndvi = self._predict_ndvi(base_rgb, generated, request.baseline_ndvi)
            return GenerationResult(rgb=generated, ndvi=ndvi,
                                    backend=self.name, notes=notes)

        # ---- whole-scene mode (no adapter) --------------------------------
        pipe = self._load_pipeline()
        generator = torch.Generator(device=self.device).manual_seed(
            self.seed + request.iteration)

        started = time.time()
        output = pipe(
            prompt=request.prompt,
            negative_prompt=negative,
            image=base_img_r,
            mask_image=mask_img,
            control_image=control_img,
            num_inference_steps=self.num_inference_steps,
            guidance_scale=self.guidance_scale,
            controlnet_conditioning_scale=self.controlnet_conditioning_scale,
            strength=self.strength,
            height=gen_h,
            width=gen_w,
            generator=generator,
        )
        elapsed = time.time() - started
        notes.append(f"Diffusion: {self.num_inference_steps} steps in "
                     f"{elapsed:.1f}s ({elapsed / self.num_inference_steps:.2f}"
                     f" s/step) at {gen_w}x{gen_h}.")

        result_img = output.images[0].resize((w, h), Image.BILINEAR)
        generated = self._from_uint8(result_img, lo, hi)

        if self.composite_unchanged:
            # Hard-composite outside the editable region. The VAE round-trip
            # perturbs every pixel it touches, which would fail rule 4 across
            # the whole frame for reasons unrelated to what the model painted.
            # Rule 4 consequently acts as a regression guard on mask handling
            # rather than a measure of model drift for this backend.
            keep = ~mask_arr
            for c in range(3):
                generated[:, :, c][keep] = base_rgb[:, :, c][keep]
            notes.append("Composited: pixels outside the editable region are "
                         "byte-identical to the baseline.")

        ndvi = self._predict_ndvi(base_rgb, generated, request.baseline_ndvi)
        if request.baseline_ndvi is None:
            notes.append("No baseline NDVI supplied; NDVI layer is zeroed.")

        return GenerationResult(rgb=generated, ndvi=ndvi,
                                backend=self.name, notes=notes)
