"""Raster persistence and PNG rendering for the frontend.

The slider in src/components/SatelliteSlider.jsx shows four band views
(optical, NDVI, moisture, critic mask), so every simulation renders a matching
set of PNGs into backend/static/.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np
import rasterio
from scipy import ndimage
import matplotlib
from matplotlib.colors import Normalize
from PIL import Image
from rasterio.transform import Affine

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# GeoTIFF
# --------------------------------------------------------------------------

def write_geotiff(path: Path, bands: Dict[str, np.ndarray], transform: Affine,
                  crs: str) -> Path:
    """Write a named band stack as a multi-band float32 GeoTIFF."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    names = list(bands)
    first = bands[names[0]]

    with rasterio.open(
        path, "w", driver="GTiff",
        height=first.shape[0], width=first.shape[1],
        count=len(names), dtype="float32",
        crs=crs, transform=transform, compress="deflate",
    ) as dst:
        for i, name in enumerate(names, start=1):
            dst.write(bands[name].astype("float32"), i)
            dst.set_band_description(i, name)
    return path


def read_geotiff(path: Path) -> tuple:
    """Read a multi-band GeoTIFF back into (bands, transform, crs)."""
    with rasterio.open(path) as src:
        names = [d or f"band_{i+1}" for i, d in enumerate(src.descriptions or [])]
        if len(names) != src.count:
            names = [f"band_{i+1}" for i in range(src.count)]
        bands = {n: src.read(i + 1).astype(np.float32) for i, n in enumerate(names)}
        return bands, src.transform, src.crs.to_string()


# --------------------------------------------------------------------------
# PNG rendering
# --------------------------------------------------------------------------

def stretch(array: np.ndarray, low: float = 2.0, high: float = 98.0) -> np.ndarray:
    """Percentile contrast stretch to [0, 1]; robust to outliers and NaNs."""
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros_like(array, dtype=np.float32)
    lo, hi = np.percentile(finite, [low, high])
    if hi - lo < 1e-9:
        return np.zeros_like(array, dtype=np.float32)
    return np.clip((array - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)


def render_rgb(rgb: np.ndarray, path: Path) -> Path:
    """Save an (H, W, 3) reflectance stack as a contrast-stretched PNG."""
    stacked = np.dstack([stretch(rgb[:, :, i]) for i in range(3)])
    return _save(np.nan_to_num(stacked), path)


def render_colormap(array: np.ndarray, path: Path, cmap: str = "RdYlGn",
                    vmin: float = -0.2, vmax: float = 0.8) -> Path:
    """Save a single-band raster through a matplotlib colormap."""
    norm = Normalize(vmin=vmin, vmax=vmax, clip=True)
    # matplotlib.colormaps[...] -- cm.get_cmap was removed in matplotlib 3.9.
    coloured = matplotlib.colormaps[cmap](norm(np.nan_to_num(array)))[:, :, :3]
    return _save(coloured, path)


def render_mask_overlay(base_rgb: np.ndarray, mask: np.ndarray, path: Path,
                        colour: Sequence[float] = (1.0, 0.15, 0.2),
                        alpha: float = 0.65) -> Path:
    """Tint `mask` pixels over a desaturated base -- the critic feedback view."""
    grey = np.nan_to_num(np.mean(np.dstack([stretch(base_rgb[:, :, i])
                                            for i in range(3)]), axis=-1))
    out = np.dstack([grey * 0.7] * 3)
    m = np.asarray(mask, dtype=bool)
    for c in range(3):
        out[:, :, c][m] = (1 - alpha) * out[:, :, c][m] + alpha * colour[c]
    return _save(out, path)


def render_rgba_mask(mask: np.ndarray, path: Path,
                     colour: Sequence[float] = (1.0, 0.15, 0.2),
                     alpha: float = 0.72,
                     outline_only: bool = False) -> Path:
    """Save a boolean mask as a TRANSPARENT RGBA PNG.

    render_mask_overlay bakes the tint onto an opaque base image, which means
    the frontend can only display it as its own layer -- it can never be
    stacked over the optical view or faded with an opacity slider. An xAI
    overlay needs the mask itself, with alpha 0 everywhere it does not apply.

    `outline_only` emits just the boundary, for showing an intervention
    footprint without hiding the imagery underneath it.
    """
    mask = np.asarray(mask, dtype=bool)
    if outline_only and mask.any():
        eroded = ndimage.binary_erosion(mask, iterations=1)
        mask = mask & ~eroded

    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for c in range(3):
        rgba[:, :, c] = int(np.clip(colour[c], 0, 1) * 255)
    rgba[:, :, 3] = (mask * int(np.clip(alpha, 0, 1) * 255)).astype(np.uint8)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path)
    return path


def render_rgba_diverging(values: np.ndarray, path: Path,
                          threshold: float = 0.05,
                          vmin: float = -0.4, vmax: float = 0.4,
                          cmap: str = "BrBG", alpha: float = 0.80) -> Path:
    """Save a signed field (e.g. NDVI delta) as a transparent RGBA PNG.

    Pixels whose magnitude is below `threshold` get alpha 0, so the overlay
    marks only where something actually changed rather than tinting the whole
    frame with noise.
    """
    values = np.nan_to_num(np.asarray(values, dtype=np.float32))
    norm = Normalize(vmin=vmin, vmax=vmax, clip=True)
    coloured = matplotlib.colormaps[cmap](norm(values))
    rgba = (coloured * 255).astype(np.uint8)
    rgba[:, :, 3] = ((np.abs(values) >= threshold)
                     * int(np.clip(alpha, 0, 1) * 255)).astype(np.uint8)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path)
    return path


def _save(array01: np.ndarray, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((np.clip(array01, 0, 1) * 255).astype(np.uint8)).save(path)
    return path
