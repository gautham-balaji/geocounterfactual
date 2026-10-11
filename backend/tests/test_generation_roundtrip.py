"""Reflectance survives the 8-bit round trip through generation.

Each generation window is converted from reflectance to 8-bit for the
diffusion model and back. Both directions must use the same stretch bounds.
They once did not: windows were encoded with their own percentiles and
decoded with the scene's, so even a pixel the model reproduced exactly came
back distorted -- a median 5.3% reflectance error, enough alone to cross
rule 3's greening threshold in 10 of 21 windows.

The claim, for every pixel x inside the stretch range [lo, hi] of its band:

    |decode(encode(x)) - x| <= (hi - lo) / (2 * 255)

Encoding maps x to (x - lo) / (hi - lo) in [0, 1] and rounds 255 times that
to an integer, an error of at most half a step; decoding is the exact affine
inverse, scaling that half step by (hi - lo) / 255. Pixels outside [lo, hi]
saturate to the nearer bound, which is what a percentile stretch does, so
for them the decoded value must equal the bound.

Checked three ways, on the real generation windows the planner sites in all
15 regions:
  1. the encode/decode functions of both backends directly;
  2. the local backend's full window path, _run_pipe;
  3. the Colab server's full window path, _generate.
For 2 and 3 the diffusion pipeline is replaced by an identity -- it returns
the image it is given -- and the patch size is set to the window's native
size, where PIL resizing is exactly the identity. Any remaining error is
then the encoding's alone.

A negative control re-applies the old scene-bounds decode and requires it
to fail by a wide margin, so the test is shown to detect the defect.

Offline apart from cached scenes. Run:
    python -m backend.tests.test_generation_roundtrip
"""

from __future__ import annotations

import sys
import warnings

import numpy as np
from PIL import Image

warnings.filterwarnings("ignore")

import backend.agents.planner as planner_mod  # noqa: E402
import backend.generator.colab_server as cs  # noqa: E402
from backend.agents.dynamics import dynamics_node  # noqa: E402
from backend.agents.input_handler import input_handler_node  # noqa: E402
from backend.agents.planner import planner_node  # noqa: E402
from backend.agents.state import initial_state  # noqa: E402
from backend.config import REGIONS, settings  # noqa: E402
from backend.generator.diffusion_local import LocalDiffusionGenerator  # noqa: E402

INTERVENTION = "Build 3 series check-dams along the main dry stream bed."
WINDOW_PX = settings.generation_patch_span_m // settings.target_scale_m  # 128
FLOAT_SLACK = 1e-6      # float32 arithmetic on top of the half step


class IdentityPipe:
    """Stands in for the diffusion pipeline: returns its input image."""

    class _Out:
        def __init__(self, image):
            self.images = [image]

    def __call__(self, image=None, **_):
        return self._Out(image)

    def set_adapters(self, *a, **k):
        pass


def _scenes():
    """Real planner states for every catalogue region."""
    planner_mod.parse_intent_with_gemini = lambda *a, **k: (None, "offline")
    out = []
    for rid, region in REGIONS.items():
        state = initial_state(rid, region.bbox, INTERVENTION, 5)
        for node in (input_handler_node, planner_node, dynamics_node):
            state.update(node(state))
        out.append((rid, state))
    return out


def _windows(state):
    core = np.asarray(state["spatial_change_mask"]) >= 1.0
    if not core.any():
        return []
    gen = LocalDiffusionGenerator.__new__(LocalDiffusionGenerator)
    return gen._windows(core)


def _check(original, decoded, lo, hi, label):
    """Assert the round-trip bound; return the worst in-range error."""
    worst = 0.0
    for c in range(3):
        x, y = original[..., c], decoded[..., c]
        bound = (hi[c] - lo[c]) / (2 * 255) + FLOAT_SLACK
        inside = (x >= lo[c]) & (x <= hi[c])
        err = np.abs(y[inside] - x[inside])
        assert err.max(initial=0.0) <= bound, (
            f"{label} band {c}: in-range error {err.max():.6f} exceeds the "
            f"half-step bound {bound:.6f}")
        # Out of range: saturates to the nearer bound, within half a step.
        sat = np.clip(x[~inside], lo[c], hi[c])
        assert np.all(np.abs(y[~inside] - sat) <= bound), (
            f"{label} band {c}: saturated pixels do not decode to the bound")
        worst = max(worst, float(err.max(initial=0.0)))
    return worst


def test_codecs(scenes):
    """1. Both backends' encode/decode, on every real generation window."""
    worst, n = 0.0, 0
    for rid, state in scenes:
        rgb = state["baseline_optical_rgb"]
        for (r0, c0, r1, c1) in _windows(state):
            win = rgb[r0:r1, c0:c1]
            for enc, dec, name in (
                    (LocalDiffusionGenerator._to_uint8,
                     LocalDiffusionGenerator._from_uint8, "local"),
                    (cs.to_uint8, cs.from_uint8, "colab")):
                img, lo, hi = enc(win)
                worst = max(worst, _check(win, dec(img, lo, hi), lo, hi,
                                          f"{name} codec {rid}"))
            n += 1
    print(f"  codecs         : {n} windows x 2 backends, worst in-range "
          f"error {worst:.6f} (within the half-step bound everywhere)")
    return n


def test_local_window_path(scenes):
    """2. LocalDiffusionGenerator._run_pipe with an identity pipeline."""
    original_px = settings.generation_patch_px
    settings.generation_patch_px = WINDOW_PX
    gen = LocalDiffusionGenerator(lora_path="", patch_mode=True)
    gen._pipe = IdentityPipe()
    try:
        worst, n = 0.0, 0
        for rid, state in scenes:
            rgb = state["baseline_optical_rgb"]
            cond = state["controlnet_conditioning_map"]
            core = np.asarray(state["spatial_change_mask"]) >= 1.0
            req = type("Req", (), {"prompt": "p", "iteration": 0})()
            for (r0, c0, r1, c1) in _windows(state):
                win = rgb[r0:r1, c0:c1]
                out = gen._run_pipe(win, core[r0:r1, c0:c1],
                                    cond[r0:r1, c0:c1], req, "n")
                _, lo, hi = LocalDiffusionGenerator._to_uint8(win)
                worst = max(worst, _check(win, out, lo, hi, f"local {rid}"))
                n += 1
    finally:
        settings.generation_patch_px = original_px
    print(f"  local _run_pipe: {n} windows, worst in-range error "
          f"{worst:.6f}")


def test_colab_window_path(scenes):
    """3. colab_server._generate end to end, identity pipeline."""
    original = (cs.PATCH_PX, cs.get_pipeline)
    cs.PATCH_PX = WINDOW_PX
    cs.get_pipeline = lambda: IdentityPipe()
    try:
        worst, checked = 0.0, 0
        for rid, state in scenes:
            if not _windows(state):
                continue
            rgb = state["baseline_optical_rgb"]
            req = cs.GenerateRequest(
                prompt="p", iteration=0,
                baseline_rgb=cs.ArrayPayload(**cs.encode(rgb)),
                conditioning_map=cs.ArrayPayload(
                    **cs.encode(state["controlnet_conditioning_map"])),
                change_mask=cs.ArrayPayload(
                    **cs.encode(state["spatial_change_mask"])),
                baseline_ndvi=cs.ArrayPayload(
                    **cs.encode(state["baseline_ndvi"])))
            out = cs.decode(cs.ArrayPayload(**cs._generate(req)["rgb"]))
            core = np.asarray(state["spatial_change_mask"]) >= 1.0
            # Windows can overlap, and where they do the later one's output
            # is what was composited -- encoded with ITS bounds. Replay the
            # windows in order to know which bounds each pixel was last
            # written with, then judge every pixel against those.
            lo_map = np.zeros(rgb.shape, np.float32)
            hi_map = np.zeros(rgb.shape, np.float32)
            written = np.zeros(core.shape, bool)
            for (r0, c0, r1, c1) in cs.plan_windows(
                    core, max(8, cs.PATCH_SPAN_M // cs.SCALE_M)):
                sel = core[r0:r1, c0:c1]
                _, lo, hi = cs.to_uint8(rgb[r0:r1, c0:c1])
                for c in range(3):
                    lo_map[r0:r1, c0:c1, c][sel] = lo[c]
                    hi_map[r0:r1, c0:c1, c][sel] = hi[c]
                written[r0:r1, c0:c1] |= sel
                checked += 1
            # Core pixels no window reached (plan_windows skips components
            # already mostly covered, and caps the count) are never encoded
            # at all, so they must be the baseline to the bit.
            assert np.array_equal(out[core & ~written], rgb[core & ~written]), \
                f"colab {rid}: core pixels outside every window changed"
            x, y = rgb[written], out[written]
            lo_px, hi_px = lo_map[written], hi_map[written]
            bound = (hi_px - lo_px) / (2 * 255) + FLOAT_SLACK
            expected = np.clip(x, lo_px, hi_px)     # saturation is the stretch
            err = np.abs(y - expected)
            assert np.all(err <= bound), (
                f"colab {rid}: error {err.max():.6f} exceeds the half-step "
                f"bound of the window that wrote the pixel")
            inside = (x >= lo_px) & (x <= hi_px)
            worst = max(worst, float(np.abs(y - x)[inside].max(initial=0.0)))
            # Nothing outside the core changed at all.
            assert np.array_equal(out[~core], rgb[~core]), \
                f"colab {rid}: pixels outside the editable core changed"
    finally:
        cs.PATCH_PX, cs.get_pipeline = original
    print(f"  colab _generate: {checked} windows end to end, worst in-range "
          f"error {worst:.6f}; pixels outside the core untouched")


def test_negative_control(scenes):
    """The old scene-bounds decode must fail this test decisively."""
    worst_ratio = 0.0
    for rid, state in scenes:
        rgb = state["baseline_optical_rgb"]
        _, s_lo, s_hi = LocalDiffusionGenerator._to_uint8(rgb)
        for (r0, c0, r1, c1) in _windows(state):
            win = rgb[r0:r1, c0:c1]
            img, lo, hi = LocalDiffusionGenerator._to_uint8(win)
            old = LocalDiffusionGenerator._from_uint8(img, s_lo, s_hi)
            for c in range(3):
                inside = (win[..., c] >= lo[c]) & (win[..., c] <= hi[c])
                err = np.abs(old[..., c][inside] - win[..., c][inside]).max()
                worst_ratio = max(worst_ratio,
                                  err / ((hi[c] - lo[c]) / (2 * 255)))
    assert worst_ratio > 10, "the test would not have caught the old defect"
    print(f"  negative control: the old scene-bounds decode misses the bound "
          f"by up to {worst_ratio:.0f}x -- the test detects the defect")


def run() -> int:
    print("=" * 74)
    print("GENERATION ROUND TRIP: reflectance -> 8-bit -> reflectance")
    print("=" * 74)
    assert np.array_equal(
        np.asarray(Image.fromarray(np.arange(48, dtype=np.uint8).reshape(4, 4, 3))
                   .resize((4, 4), Image.BILINEAR)),
        np.arange(48, dtype=np.uint8).reshape(4, 4, 3)), \
        "same-size resize is not the identity; the path tests are invalid"
    scenes = _scenes()
    test_codecs(scenes)
    test_local_window_path(scenes)
    test_colab_window_path(scenes)
    test_negative_control(scenes)
    print("-" * 74)
    print("Every unchanged pixel returns within half a quantisation step.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
