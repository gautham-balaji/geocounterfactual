"""User uploads: normalisation, terrain alignment, rule degradation, API.

The upload path must change nothing it does not have to. The strongest
check of that is equivalence: a catalogue region exported as a GeoTIFF and
uploaded must produce exactly the run the region itself produces. Around it:

  * the Copernicus DEM fetched for an arbitrary bbox lands on the same
    ground as the terrain the region pipeline already uses;
  * an RGB-only image is judged on R1 and R4 alone, says so, and still
    satisfies the null-intervention invariant;
  * files the pipeline cannot use are refused with a reason, never guessed.

Needs Earth Engine for the DEM checks (the PNG has no terrain of its own).
Leaves no uploads or run directories behind.

Run:  python -m backend.tests.test_upload
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds

warnings.filterwarnings("ignore")

import backend.agents.planner as planner_mod  # noqa: E402
from backend.agents import generator_node  # noqa: E402
from backend.agents.dynamics import dynamics_node  # noqa: E402
from backend.agents.input_handler import (BASELINE_END, BASELINE_START,  # noqa: E402
                                          input_handler_node)
from backend.agents.planner import planner_node  # noqa: E402
from backend.agents.state import initial_state  # noqa: E402
from backend.agents.workflow import run_simulation  # noqa: E402
from backend.config import REGIONS, settings  # noqa: E402
from backend.critic import rules as R  # noqa: E402
from backend.critic.physics_critic import PhysicalPlausibilityCritic  # noqa: E402
from backend.data_engine import cache, raster_io  # noqa: E402
from backend.data_engine.gee_loader import fetch_dem  # noqa: E402
from backend.data_engine.raster_io import UploadError, read_upload  # noqa: E402
from backend.generator.stub import StubGenerator  # noqa: E402

REGION = "anantapur"
INTERVENTION = "Build 3 series check-dams along the main dry stream bed."
TMP = Path(tempfile.mkdtemp(prefix="geocf_upload_test_"))
CREATED_UPLOADS: list = []
CREATED_RUNS: list = []


def _region_scene():
    region = REGIONS[REGION]
    return cache.load_scene(region.bbox, BASELINE_START, BASELINE_END,
                            crs=region.crs)


def _lonlat_bbox(scene):
    h, w = scene.shape
    left, bottom, right, top = rasterio.transform.array_bounds(
        h, w, scene.transform)
    return list(transform_bounds(scene.crs, "EPSG:4326",
                                 left, bottom, right, top))


def _prepare(path, name, **kw):
    upload_id, scene = cache.prepare_upload(path, name, **kw)
    CREATED_UPLOADS.append(upload_id)
    return upload_id, scene


def _write_tif(path, arrays, crs, transform, dtype, descriptions=None):
    h, w = arrays[0].shape
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w,
                       count=len(arrays), dtype=dtype, crs=crs,
                       transform=transform) as dst:
        for i, a in enumerate(arrays, start=1):
            dst.write(a.astype(dtype), i)
            if descriptions:
                dst.set_band_description(i, descriptions[i - 1])


# --------------------------------------------------------------------------

def test_dem_alignment():
    """fetch_dem on the region's own grid must reproduce its terrain."""
    scene = _region_scene()
    terrain = fetch_dem(scene.bbox, scene.crs, dst_transform=scene.transform,
                        dst_shape=scene.shape)
    d_elev = np.abs(terrain["elevation"] - scene.bands["elevation"])
    d_slope = np.abs(terrain["slope"] - scene.bands["slope"])
    print(f"  DEM alignment   : elevation |diff| median {np.median(d_elev):.3f} m"
          f" (p99 {np.percentile(d_elev, 99):.2f}); slope median "
          f"{np.median(d_slope):.3f} deg (p99 {np.percentile(d_slope, 99):.2f})")
    assert np.median(d_elev) < 0.5, "fetched DEM is not on the same ground"
    assert np.median(d_slope) < 0.25, "fetched slope is not on the same ground"


def test_geotiff_roundtrip_matches_region():
    """A region exported and re-uploaded must yield the identical run."""
    scene = _region_scene()
    path = TMP / "anantapur_s2.tif"
    names = ["B2", "B3", "B4", "B8", "B11", "B12", "elevation", "slope"]
    raster_io.write_geotiff(path, {n: scene.bands[n] for n in names},
                            scene.transform, scene.crs)
    upload_id, up = _prepare(path, path.name)

    for n in names:
        assert np.array_equal(up.bands[n], scene.bands[n]), f"{n} altered"
    assert tuple(up.transform) == tuple(scene.transform)
    assert any("without resampling" in n for n in up.notes)

    region_run = run_simulation(REGION, INTERVENTION, 5)
    upload_run = run_simulation("upload", INTERVENTION, 5, upload_id=upload_id)
    assert upload_run["spectral_mode"] == "multispectral"
    assert upload_run["critic_rules"] == ["R1", "R2", "R3", "R4"]
    for key in ("spatial_change_mask", "candidate_future_rgb"):
        assert np.array_equal(region_run[key], upload_run[key]), f"{key} differs"
    for key in ("plausibility_score", "is_approved", "iteration_count"):
        assert region_run[key] == upload_run[key], f"{key} differs"
    print(f"  GeoTIFF upload  : bands bit-identical, run identical to the "
          f"region (score {upload_run['plausibility_score']:.0f}%, "
          f"{upload_run['iteration_count']} iterations)")


def test_rgb_png_degrades_honestly():
    scene = _region_scene()
    png = TMP / "anantapur_rgb.png"
    raster_io.render_rgb(scene.rgb, png)                 # 8-bit, no georef
    bbox = _lonlat_bbox(scene)
    upload_id, up = _prepare(png, png.name, bbox=bbox)
    assert set(up.bands) >= {"B2", "B3", "B4", "elevation", "slope"}
    assert "B8" not in up.bands

    state = initial_state("upload", [], INTERVENTION, 5, upload_id=upload_id)
    for node in (input_handler_node, planner_node, dynamics_node):
        state.update(node(state))
    assert state["spectral_mode"] == "rgb"
    assert state["critic_rules"] == ["R1", "R4"]
    assert set(state["critic_rules_disabled"]) == {"R2", "R3"}

    # Null intervention on the RGB scene: nothing changed, nothing to report.
    critic = PhysicalPlausibilityCritic()
    null = critic.evaluate_arrays(
        state["baseline_optical_rgb"], state["baseline_ndvi"],
        state["baseline_optical_rgb"], state["baseline_ndvi"],
        state["dem_slope"], state["spatial_change_mask"], years=5,
        scene_rules=("R1", "R4"), has_nir=False)
    assert null.is_approved and null.score == 100.0, null.violations
    assert null.metrics["evaluated_rules"] == ["R1", "R4"]

    # What R1 would have reported without judging only introduced water:
    # visible-band "water" is mostly terrain shadow on exactly the steep
    # ground R1 polices.
    naive = R.rule_gravity_slope(state["baseline_optical_rgb"], None,
                                 state["dem_slope"])
    print(f"  RGB upload      : rules {state['critic_rules']}, null scene "
          f"clean; without the baseline R1 would flag "
          f"{naive.metrics['violating_cells']} px of unchanged shadow")

    # Darkening an already-bluish pixel (greening, wetting, shade) is not
    # introducing water; painting water is. The visible test alone confuses
    # the first for the second.
    base = np.full((20, 20, 3), (0.62, 0.62, 0.68), np.float32)  # bluish rock
    base[:10] = (0.70, 0.60, 0.50)                            # brighter soil
    darkened = base.copy(); darkened[12:18, 2:8] *= 0.7
    painted = base.copy(); painted[2:8, 2:8] = (0.10, 0.20, 0.35)
    steep = np.full((20, 20), 10.0, np.float32)
    dark_r1 = R.rule_gravity_slope(darkened, None, steep, baseline_rgb=base)
    paint_r1 = R.rule_gravity_slope(painted, None, steep, baseline_rgb=base)
    assert dark_r1.passed, "darkening read as new water"
    assert not paint_r1.passed, "painted water on a slope not caught"

    run = run_simulation("upload", INTERVENTION, 5, upload_id=upload_id)
    audits = [e["text"] for e in run["execution_logs"]
              if e["text"].startswith("Physics audit")]
    assert audits and all("R2" not in a and "R3" not in a for a in audits)
    assert run["is_approved"], ("RGB run did not converge: "
                                f"{run.get('violations')}")
    print(f"  RGB full run    : approved={run['is_approved']} score "
          f"{run['plausibility_score']:.0f}% over R1+R4, "
          f"{run['iteration_count']} iteration(s)")
    return upload_id


def test_reprojection_preserves_reflectance():
    """A 2.5 m geographic image, area-averaged onto the 10 m UTM grid."""
    rng = np.random.default_rng(3)
    lon0, lat0 = 77.30, 14.70
    deg = 2.5 / 111_320.0
    h = w = 800                                           # ~2 km at 2.5 m
    bands = [np.clip(rng.normal(m, 0.03, (h, w)), 0, 1).astype(np.float32)
             for m in (0.20, 0.16, 0.12, 0.30)]
    path = TMP / "fine_rgbn.tif"
    _write_tif(path, bands, "EPSG:4326",
               from_bounds(lon0, lat0, lon0 + w * deg, lat0 + h * deg, w, h),
               "float32", ["red", "green", "blue", "nir"])
    up = read_upload(path)
    assert up.crs == "EPSG:32643", up.crs
    assert any("area-averaged" in n for n in up.notes)
    for name, src in zip(("B4", "B3", "B2", "B8"), bands):
        rel = abs(float(up.bands[name].mean()) - float(src.mean())) / float(src.mean())
        assert rel < 0.01, f"{name} mean shifted {100 * rel:.2f}%"
    print(f"  reprojection    : 2.5 m geographic -> {up.crs} 10 m, "
          f"{up.bands['B4'].shape}, band means preserved within 1%")


def test_rejections():
    rng = np.random.default_rng(5)
    utm = "EPSG:32643"
    t10 = from_bounds(700000, 1620000, 702000, 1622000, 200, 200)
    four = [rng.integers(500, 3000, (200, 200)) for _ in range(4)]

    def refused(fn, expect, status=None):
        try:
            fn()
        except UploadError as exc:
            assert expect in str(exc), str(exc)
            assert status is None or exc.status == status
            return str(exc)
        raise AssertionError(f"accepted; expected refusal containing '{expect}'")

    unlabelled = TMP / "four_band.tif"
    _write_tif(unlabelled, four, utm, t10, "uint16")
    refused(lambda: read_upload(unlabelled), "band_order")

    ok = read_upload(unlabelled, band_order=["blue", "green", "red", "nir"])
    assert np.allclose(ok.bands["B4"], four[2] / 10_000.0)
    assert np.allclose(ok.bands["B2"], four[0] / 10_000.0)

    png = TMP / "plain.png"
    from PIL import Image
    Image.fromarray(rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)).save(png)
    refused(lambda: read_upload(png), "georeferencing")
    refused(lambda: read_upload(png, bbox=[77.0, 14.0, 78.0, 15.0]),
            "per side", status=413)
    refused(lambda: read_upload(unlabelled, band_order=["red", "red",
                                                        "blue", "nir"]),
            "repeat")
    bmp = TMP / "x.bmp"
    bmp.write_bytes(b"BM")
    refused(lambda: read_upload(bmp), "Unsupported", status=415)
    print("  rejections      : unlabelled 4-band, ungeoreferenced PNG, "
          "oversized, repeated bands, bad type -- all refused with reasons")


def test_endpoint(rgb_png: Path, bbox):
    from fastapi.testclient import TestClient
    import backend.server as server

    client = TestClient(server.app)
    original_prune = server._prune_runs
    server._prune_runs = lambda: None        # never delete the user's runs
    try:
        with rgb_png.open("rb") as fh:
            r = client.post("/api/upload",
                            files={"file": ("scene.png", fh, "image/png")},
                            data={"bbox": ",".join(map(str, bbox))})
        assert r.status_code == 200, r.text
        body = r.json()
        CREATED_UPLOADS.append(body["upload_id"])
        assert body["spectral_mode"] == "rgb"
        assert body["critic_rules_evaluated"] == ["R1", "R4"]
        assert set(body["critic_rules_disabled"]) == {"R2", "R3"}
        assert client.get(body["preview_url"]).status_code == 200

        bad = client.post("/api/upload",
                          files={"file": ("scene.png", io.BytesIO(b"x"), "image/png")},
                          data={"bbox": "1,2,3"})
        assert bad.status_code == 422, bad.text
        wrong = client.post("/api/upload",
                            files={"file": ("a.bmp", io.BytesIO(b"x"), "image/bmp")})
        assert wrong.status_code == 415, wrong.text

        sim = client.post("/api/simulate", json={
            "upload_id": body["upload_id"], "intervention_text": INTERVENTION})
        assert sim.status_code == 200, sim.text
        payload = sim.json()
        CREATED_RUNS.append(payload["run_id"])
        scene = payload["scene"]
        assert scene["spectral_mode"] == "rgb" and scene["source"] == "upload"
        assert scene["critic_rules_evaluated"] == ["R1", "R4"]
        assert "ndvi" in scene["layer_notes"]

        for unknown in ("ffffffffffff", "../../etc"):
            miss = client.post("/api/simulate", json={
                "upload_id": unknown, "intervention_text": INTERVENTION})
            assert miss.status_code == 404, miss.text
        print(f"  endpoint        : upload 200 ({body['shape'][0]}x"
              f"{body['shape'][1]}, {body['spectral_mode']}), bad bbox 422, "
              f"bad type 415, simulate 200 with scene block, unknown id 404")
    finally:
        server._prune_runs = original_prune


def _cleanup():
    for upload_id in CREATED_UPLOADS:
        key = f"upload_{upload_id}"
        for suffix in (".npz", ".json"):
            (settings.cache_dir / f"{key}{suffix}").unlink(missing_ok=True)
        shutil.rmtree(settings.static_dir / "uploads" / upload_id,
                      ignore_errors=True)
    for run_id in CREATED_RUNS:
        shutil.rmtree(settings.static_dir / "runs" / run_id, ignore_errors=True)
    shutil.rmtree(TMP, ignore_errors=True)


def run() -> int:
    planner_mod.parse_intent_with_gemini = lambda *a, **k: (None, "offline")
    generator_node.set_generator(StubGenerator())
    print("=" * 74)
    print("UPLOADS: normalisation, terrain, rule degradation, API")
    print("=" * 74)
    try:
        test_reprojection_preserves_reflectance()
        test_rejections()
        test_dem_alignment()
        test_geotiff_roundtrip_matches_region()
        test_rgb_png_degrades_honestly()
        scene = _region_scene()
        png = TMP / "endpoint.png"
        raster_io.render_rgb(scene.rgb, png)
        test_endpoint(png, _lonlat_bbox(scene))
    finally:
        _cleanup()
    print("-" * 74)
    print("Uploads change nothing they do not have to, and say what they "
          "cannot judge.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
