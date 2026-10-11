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


def green_leaf_index(red: np.ndarray, green: np.ndarray,
                     blue: np.ndarray) -> np.ndarray:
    """GLI = (2G - R - B) / (2G + R + B), Louhaichi et al. (2001).

    A visible-band vegetation index for scenes with no NIR. Bounded to
    [-1, 1] like NDVI and monotone in canopy greenness, so it can RANK
    vegetation -- the planner's afforestation siting needs only that. It is
    not NDVI: it has no red-edge component and a different scale, which is
    why the NIR-dependent rules are disabled wherever it stands in.
    """
    red = np.asarray(red, dtype=np.float32)
    green = np.asarray(green, dtype=np.float32)
    blue = np.asarray(blue, dtype=np.float32)
    num = 2.0 * green - red - blue
    den = 2.0 * green + red + blue
    out = np.zeros_like(green, dtype=np.float32)
    valid = np.abs(den) > EPS
    out[valid] = num[valid] / den[valid]
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def visible_water(rgb: np.ndarray) -> np.ndarray:
    """Open-water mask from the visible bands alone, for scenes with no NIR.

    Water reflects blue at least as strongly as green or red, while semi-arid
    soil is red-dominant and vegetation green-dominant. Requiring a pixel to
    be blue-dominant AND darker than the scene median also rejects bright
    blue-white surfaces such as roofs and salt crusts. Both tests are ratios
    or scene-relative, so they hold whether the upload is calibrated
    reflectance or 8-bit display values.

    Conservative by construction: turbid, green-dominant water is missed. Its
    main false positive is shadow, which is also blue-dominant and dark --
    rule 1 therefore judges only water that is new relative to the baseline,
    so terrain shadow present in both images cannot register as a violation.
    """
    rgb = np.asarray(rgb, dtype=np.float32)
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    brightness = (red + green + blue) / 3.0
    finite = brightness[np.isfinite(brightness)]
    dark = brightness < (float(np.median(finite)) if finite.size else np.inf)
    return (blue >= green) & (blue >= red) & dark


def compute_available(bands: Dict[str, np.ndarray]) -> tuple:
    """Indices for whatever bands a scene actually has.

    Returns (indices, spectral). `spectral` records what is measured and what
    is a proxy, so downstream code and the UI can say which is which:

      multispectral  B2-B4, B8, B11: every index measured.
      rgb_nir        no SWIR: NDMI unavailable, reported as zeros.
      rgb            no NIR: NDVI replaced by GLI, NDWI by a visible water
                     indicator (+1 water, -1 not), NDMI unavailable.
    """
    has_nir = "B8" in bands
    has_swir = "B11" in bands
    shape = bands["B4"].shape
    proxies: Dict[str, str] = {}

    if has_nir:
        out = {"ndvi": ndvi(bands["B8"], bands["B4"]),
               "ndwi": ndwi(bands["B3"], bands["B8"])}
    else:
        rgb = np.dstack([bands["B4"], bands["B3"], bands["B2"]])
        out = {"ndvi": green_leaf_index(bands["B4"], bands["B3"], bands["B2"]),
               "ndwi": np.where(visible_water(rgb), 1.0, -1.0).astype(np.float32)}
        proxies["ndvi"] = "GLI (visible-band greenness), not NDVI"
        proxies["ndwi"] = "visible-band water indicator, not NDWI"

    if has_nir and has_swir:
        out["ndmi"] = ndmi(bands["B8"], bands["B11"])
    else:
        out["ndmi"] = np.zeros(shape, dtype=np.float32)
        proxies["ndmi"] = "unavailable (needs NIR and SWIR); zeros"

    mode = ("multispectral" if has_nir and has_swir
            else "rgb_nir" if has_nir else "rgb")
    spectral = {"mode": mode, "has_nir": has_nir, "has_swir": has_swir,
                "proxies": proxies}
    return out, spectral


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
