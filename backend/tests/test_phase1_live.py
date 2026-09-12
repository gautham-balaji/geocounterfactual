"""Phase 1 verification: live Earth Engine ingestion for Anantapur.

Run directly:  python -m backend.tests.test_phase1_live
Or via pytest: pytest backend/tests/test_phase1_live.py -s
"""

from __future__ import annotations

import sys
import time

import numpy as np

from backend.config import REGIONS, settings
from backend.data_engine import indices, raster_io
from backend.data_engine.cache import load_scene, synthesize_scene

BASELINE_WINDOW = ("2019-01-01", "2019-06-30")


def run() -> int:
    region = REGIONS["anantapur"]
    print(f"Region : {region.name}")
    print(f"BBox   : {region.bbox}")
    print(f"CRS    : {region.crs}")

    started = time.time()
    scene = load_scene(region.bbox, *BASELINE_WINDOW, crs=region.crs)
    elapsed = time.time() - started

    print(f"\nSource : {scene.source}  ({elapsed:.1f}s)")
    for note in scene.notes:
        print(f"  note : {note}")
    print(f"Shape  : {scene.shape}")
    print(f"CRS    : {scene.crs}")
    print(f"Bands  : {sorted(scene.bands)}")

    # Every band must sit on one identical grid, or the critic cannot overlay
    # slope on generated RGB.
    shapes = {b: a.shape for b, a in scene.bands.items()}
    assert len(set(shapes.values())) == 1, f"Band grids diverge: {shapes}"
    print("\n[ok] all bands co-registered on one grid")

    idx = indices.compute_all(scene.bands)
    print("\n--- statistics ---")
    for name in ("ndvi", "ndwi", "ndmi"):
        s = indices.summarize(idx[name])
        print(f"{name.upper():6s} mean={s['mean']:+.3f} std={s['std']:.3f} "
              f"range=[{s['min']:+.3f}, {s['max']:+.3f}]")
    for name in ("elevation", "slope"):
        s = indices.summarize(scene.bands[name])
        print(f"{name:6s} mean={s['mean']:8.2f} range=[{s['min']:.2f}, {s['max']:.2f}]")

    # The spec's headline critic rule depends on a populated slope raster.
    slope_stats = indices.summarize(scene.bands["slope"])
    assert slope_stats["max"] > 0.5, (
        "Slope raster is flat/empty -- setDefaultProjection regression"
    )
    print("\n[ok] slope raster populated (Terrain.slope projection fix holding)")

    if scene.source == "gee":
        ndvi_mean = indices.summarize(idx["ndvi"])["mean"]
        assert 0.0 < ndvi_mean < 0.6, f"NDVI {ndvi_mean:.3f} implausible for semi-arid"
        print(f"[ok] NDVI mean {ndvi_mean:.3f} plausible "
              f"(mockData baseline {region.baseline_ndvi})")

    out = settings.static_dir / "phase1"
    raster_io.render_rgb(scene.rgb, out / "anantapur_optical.png")
    raster_io.render_colormap(idx["ndvi"], out / "anantapur_ndvi.png",
                              cmap="RdYlGn", vmin=-0.2, vmax=0.8)
    raster_io.render_colormap(idx["ndmi"], out / "anantapur_moisture.png",
                              cmap="YlGnBu", vmin=-0.4, vmax=0.4)
    raster_io.render_colormap(scene.bands["slope"], out / "anantapur_slope.png",
                              cmap="magma", vmin=0, vmax=20)
    raster_io.render_mask_overlay(scene.rgb, scene.bands["slope"] > 2.5,
                                  out / "anantapur_steep_mask.png")
    tif = raster_io.write_geotiff(out / "anantapur_baseline.tif", scene.bands,
                                  scene.transform, scene.crs)
    print(f"\n[ok] rendered PNGs + GeoTIFF -> {out}")
    print(f"     GeoTIFF: {tif.stat().st_size / 1e6:.2f} MB")

    # The synthetic fallback must produce an interchangeable Scene.
    synth = synthesize_scene(region.bbox, *BASELINE_WINDOW, crs=region.crs,
                             scale=settings.target_scale_m)
    assert set(synth.bands) == set(scene.bands), "Synthetic band set diverges"
    print(f"[ok] synthetic fallback shape={synth.shape} bands match live scene")

    print("\nPHASE 1 VERIFIED")
    return 0


def test_phase1_pipeline():
    """pytest entry point; requires network + Earth Engine credentials."""
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
