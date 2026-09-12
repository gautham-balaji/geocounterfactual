"""Spectral indices derived from Sentinel-2 surface reflectance.

All functions take and return float32 arrays on a shared grid and clip to the
theoretical [-1, 1] range so masked/no-data pixels cannot produce infinities
that would poison the critic's statistics.
"""

from __future__ import annotations

from typing import Dict

import numpy as np

EPS = 1e-6


def _normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(a - b) / (a + b), safe against zero and negative denominators."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = a + b
    out = np.zeros_like(a, dtype=np.float32)
    valid = np.abs(denom) > EPS
    out[valid] = (a[valid] - b[valid]) / denom[valid]
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Normalized Difference Vegetation Index: (B8 - B4) / (B8 + B4)."""
    return _normalized_difference(nir, red)


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """McFeeters NDWI: (B3 - B8) / (B3 + B8). Positive over open water.

    Used for the critic's water detection instead of the spec's green-vs-blue
    reflectance heuristic, which also fires on bright rooftops and haze.
    """
    return _normalized_difference(green, nir)


def ndmi(nir: np.ndarray, swir: np.ndarray) -> np.ndarray:
    """Normalized Difference Moisture Index: (B8 - B11) / (B8 + B11).

    Serves as the soil-moisture proxy reported to the frontend.
    """
    return _normalized_difference(nir, swir)


def compute_all(bands: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Compute every index the pipeline needs from a band dict."""
    return {
        "ndvi": ndvi(bands["B8"], bands["B4"]),
        "ndwi": ndwi(bands["B3"], bands["B8"]),
        "ndmi": ndmi(bands["B8"], bands["B11"]),
    }


def water_mask(ndwi_array: np.ndarray, threshold: float = 0.0) -> np.ndarray:
    """Boolean open-water mask from NDWI."""
    return np.asarray(ndwi_array) > threshold


def summarize(array: np.ndarray) -> Dict[str, float]:
    """Finite-only summary stats, safe on fully-masked rasters."""
    finite = np.asarray(array)[np.isfinite(array)]
    if finite.size == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
    }
