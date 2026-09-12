"""Content-addressed scene cache with an offline synthetic fallback.

Three-tier resolution:
  1. disk cache  -- instant, and what makes repeated runs cheap
  2. Earth Engine -- authoritative
  3. synthetic   -- statistically plausible stand-in so the LangGraph, critic
                    and API work stays unblocked when GEE is unreachable

A synthetic scene is always tagged source="synthetic" and carries a note, so a
run on fabricated data can never be mistaken for a real one in the logs or the
API response.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.config import settings
from backend.data_engine import gee_auth
from backend.data_engine.gee_loader import REFLECTANCE_BANDS, Scene, fetch_scene

logger = logging.getLogger(__name__)


def cache_key(bbox: Sequence[float], start_date: str, end_date: str, crs: str,
              scale: int) -> str:
    payload = json.dumps(
        {"bbox": [round(float(v), 6) for v in bbox], "start": start_date,
         "end": end_date, "crs": crs, "scale": scale},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _paths(key: str) -> tuple:
    base = Path(settings.cache_dir)
    return base / f"{key}.npz", base / f"{key}.json"


def save_to_cache(key: str, scene: Scene) -> None:
    npz_path, meta_path = _paths(key)
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz_path, **scene.bands)
    meta_path.write_text(
        json.dumps(
            {
                "transform": list(scene.transform)[:6],
                "crs": scene.crs,
                "bbox": scene.bbox,
                "start_date": scene.start_date,
                "end_date": scene.end_date,
                "source": scene.source,
                "notes": scene.notes,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Cached scene %s -> %s", key, npz_path.name)


def load_from_cache(key: str) -> Optional[Scene]:
    npz_path, meta_path = _paths(key)
    if not (npz_path.is_file() and meta_path.is_file()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        with np.load(npz_path) as data:
            bands = {k: data[k].astype(np.float32) for k in data.files}
        return Scene(
            bands=bands,
            transform=rasterio.Affine(*meta["transform"]),
            crs=meta["crs"],
            bbox=meta["bbox"],
            start_date=meta["start_date"],
            end_date=meta["end_date"],
            source=meta.get("source", "cache"),
            notes=list(meta.get("notes", [])) + ["Loaded from disk cache."],
        )
    except Exception as exc:  # noqa: BLE001 - a corrupt entry must not be fatal
        logger.warning("Cache entry %s unreadable (%s); refetching", key, exc)
        return None


# --------------------------------------------------------------------------
# Synthetic fallback
# --------------------------------------------------------------------------

def _fractal_noise(shape: tuple, rng: np.random.Generator,
                   octaves: int = 5) -> np.ndarray:
    """Sum-of-octaves value noise in [0, 1] -- cheap terrain-like structure."""
    h, w = shape
    field = np.zeros(shape, dtype=np.float32)
    amplitude, total = 1.0, 0.0
    for octave in range(octaves):
        res = max(2, 2 ** (octave + 1))
        coarse = rng.random((res, res)).astype(np.float32)
        ys = np.linspace(0, res - 1, h)
        xs = np.linspace(0, res - 1, w)
        y0 = np.clip(ys.astype(int), 0, res - 2)
        x0 = np.clip(xs.astype(int), 0, res - 2)
        fy = (ys - y0)[:, None]
        fx = (xs - x0)[None, :]
        top = coarse[y0][:, x0] * (1 - fx) + coarse[y0][:, x0 + 1] * fx
        bot = coarse[y0 + 1][:, x0] * (1 - fx) + coarse[y0 + 1][:, x0 + 1] * fx
        field += amplitude * (top * (1 - fy) + bot * fy)
        total += amplitude
        amplitude *= 0.5
    return field / max(total, 1e-6)


def synthesize_scene(bbox: Sequence[float], start_date: str, end_date: str,
                     crs: str, scale: int, seed: int = 42) -> Scene:
    """Fabricate a semi-arid scene with the right shape, dtype and statistics."""
    rng = np.random.default_rng(seed)

    # Match the pixel grid a real request at this scale would produce.
    lon_span_m = (bbox[2] - bbox[0]) * 111_320 * np.cos(np.radians((bbox[1] + bbox[3]) / 2))
    lat_span_m = (bbox[3] - bbox[1]) * 110_540
    width = max(64, int(round(lon_span_m / scale)))
    height = max(64, int(round(lat_span_m / scale)))
    shape = (height, width)

    elevation = 330.0 + 40.0 * _fractal_noise(shape, rng)
    gy, gx = np.gradient(elevation, scale)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)

    # Semi-arid baseline: low, patchy vegetation (target NDVI mean ~0.22).
    veg = _fractal_noise(shape, rng, octaves=4)
    red = (0.20 - 0.06 * veg).astype(np.float32)
    nir = (0.28 + 0.22 * veg).astype(np.float32)
    green = (0.16 - 0.02 * veg).astype(np.float32)
    blue = (0.13 - 0.01 * veg).astype(np.float32)
    swir1 = (0.30 - 0.08 * veg).astype(np.float32)
    swir2 = (0.24 - 0.06 * veg).astype(np.float32)

    bands = {
        "B2": blue, "B3": green, "B4": red,
        "B8": nir, "B11": swir1, "B12": swir2,
        "elevation": elevation.astype(np.float32),
        "slope": slope,
    }

    return Scene(
        bands=bands,
        transform=from_origin(bbox[0], bbox[3],
                              (bbox[2] - bbox[0]) / width,
                              (bbox[3] - bbox[1]) / height),
        crs=crs,
        bbox=list(bbox),
        start_date=start_date,
        end_date=end_date,
        source="synthetic",
        notes=["SYNTHETIC DATA - Earth Engine unavailable. Not valid for evaluation."],
    )


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def load_scene(
    bbox: Sequence[float],
    start_date: str,
    end_date: str,
    crs: str,
    scale: Optional[int] = None,
    use_cache: bool = True,
    allow_synthetic: Optional[bool] = None,
) -> Scene:
    """Resolve a scene from cache, then Earth Engine, then synthetic."""
    scale = scale or settings.target_scale_m
    allow_synthetic = (settings.allow_synthetic_fallback
                       if allow_synthetic is None else allow_synthetic)
    key = cache_key(bbox, start_date, end_date, crs, scale)

    if use_cache:
        cached = load_from_cache(key)
        if cached is not None:
            return cached

    try:
        scene = fetch_scene(bbox, start_date, end_date, crs, scale)
        save_to_cache(key, scene)
        return scene
    except Exception as exc:  # noqa: BLE001
        if not allow_synthetic:
            raise
        logger.warning("Earth Engine fetch failed (%s); using synthetic scene", exc)
        scene = synthesize_scene(bbox, start_date, end_date, crs, scale)
        scene.notes.append(f"Fetch error: {exc}")
        return scene
