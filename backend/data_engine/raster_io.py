"""Raster persistence and PNG rendering for the frontend.

The slider in src/components/SatelliteSlider.jsx shows four band views
(optical, NDVI, moisture, critic mask), so every simulation renders a matching
set of PNGs into backend/static/.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import rasterio
from scipy import ndimage
import matplotlib
from matplotlib.colors import Normalize
from PIL import Image
from rasterio.crs import CRS
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import Affine, from_bounds
from rasterio.warp import (Resampling, calculate_default_transform,
                           reproject, transform_bounds)

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
# User uploads
# --------------------------------------------------------------------------

UPLOAD_EXTENSIONS = (".tif", ".tiff", ".png", ".jpg", ".jpeg")

# The pipeline is tuned for scenes of a few kilometres at 10 m: D8 routing,
# the 1280 m generation windows and the critic all assume it.
MIN_UPLOAD_PX = 64          # 640 m: smaller cannot hold a drainage network
MAX_UPLOAD_PX = 1024        # 10.24 km
MAX_NODATA_FRACTION = 0.20

# Band names the pipeline uses, keyed by every spelling an upload may carry.
# None marks a band to ignore.
BAND_ALIASES: Dict[str, Optional[str]] = {
    "b2": "B2", "b02": "B2", "blue": "B2", "b": "B2",
    "b3": "B3", "b03": "B3", "green": "B3", "g": "B3",
    "b4": "B4", "b04": "B4", "red": "B4", "r": "B4",
    "b8": "B8", "b08": "B8", "nir": "B8", "n": "B8",
    "b11": "B11", "swir1": "B11", "swir": "B11",
    "b12": "B12", "swir2": "B12",
    "elevation": "elevation", "dem": "elevation", "height": "elevation",
    "slope": "slope",
    "alpha": None, "skip": None, "-": None,
}
SPECTRAL_BANDS = ("B2", "B3", "B4", "B8", "B11", "B12")


class UploadError(ValueError):
    """An upload the pipeline cannot use. The message is shown to the user."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


@dataclass
class UploadedRaster:
    """An upload normalised onto the pipeline's 10 m metric grid.

    `bands` holds reflectance in [0, 1] under pipeline names (B2, B3, B4 and
    optionally B8, B11, B12) plus `elevation` if the file carried one.
    """
    bands: Dict[str, np.ndarray]
    transform: Affine
    crs: str
    bbox: List[float]                       # lon/lat, EPSG:4326
    notes: List[str] = field(default_factory=list)


def _alias(name: Optional[str]) -> Optional[str]:
    key = (name or "").strip().lower()
    if key not in BAND_ALIASES:
        raise UploadError(f"Unknown band name '{name}'. Use one of: "
                          f"{sorted(k for k in BAND_ALIASES if len(k) > 1)}")
    return BAND_ALIASES[key]


def _identify_bands(src, band_order: Optional[Sequence[str]],
                    notes: List[str]) -> List[Optional[str]]:
    """Name every band of the file, or refuse.

    Precedence: an explicit band_order, then band descriptions, then GDAL's
    colour interpretation, then a 3-band file taken as R, G, B. Anything else
    is refused rather than guessed: 4-band products disagree on order (NAIP
    is R,G,B,NIR; PlanetScope is B,G,R,NIR), and a wrong guess swaps red and
    blue without any error, which corrupts every index downstream.
    """
    count = src.count
    if band_order:
        if len(band_order) != count:
            raise UploadError(f"band_order names {len(band_order)} bands but "
                              f"the file has {count}.")
        notes.append(f"Bands named by the uploader: {list(band_order)}.")
        return [_alias(b) for b in band_order]

    descriptions = list(src.descriptions or [])
    if len(descriptions) == count and all(
            (d or "").strip().lower() in BAND_ALIASES for d in descriptions):
        notes.append("Bands identified from the file's band descriptions.")
        return [_alias(d) for d in descriptions]

    interp = [ci.name for ci in src.colorinterp]
    if {"red", "green", "blue"} <= set(interp):
        notes.append("Bands identified from the file's colour interpretation.")
        return [_alias(c) if c in BAND_ALIASES else None for c in interp]

    if count == 3:
        notes.append("Unlabelled 3-band file read as red, green, blue.")
        return ["B4", "B3", "B2"]

    raise UploadError(
        f"Cannot tell which of the file's {count} bands is which. Pass "
        f"band_order, e.g. 'red,green,blue,nir' for NAIP or "
        f"'blue,green,red,nir' for PlanetScope.")


def _reflectance_scale(spectral: Dict[str, np.ndarray], dtype: str,
                       notes: List[str]) -> float:
    """One factor converting every spectral band to reflectance in [0, 1].

    Decided once per file, never per band: bands scaled differently would
    corrupt every ratio between them, and the indices are all ratios.
    """
    if dtype == "uint8":
        notes.append("8-bit values scaled by 1/255: these are display "
                     "brightness, not calibrated reflectance.")
        return 1.0 / 255.0
    peak = max((float(np.nanmax(a)) for a in spectral.values()
                if np.isfinite(a).any()), default=0.0)
    if np.issubdtype(np.dtype(dtype), np.integer) or peak > 1.5:
        notes.append("Values scaled by 1/10000 (Sentinel-2 L2A convention).")
        return 1.0 / 10_000.0
    return 1.0


def _resolution_m(crs: CRS, transform: Affine, lat: float) -> float:
    """Approximate pixel size in metres, for choosing a resampling method."""
    if crs.is_projected and crs.linear_units in ("metre", "meter"):
        return abs(transform.a)
    return abs(transform.a) * 111_320.0 * np.cos(np.radians(lat))


def utm_crs_for(lon: float, lat: float) -> str:
    zone = int((lon + 180.0) // 6.0) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def _is_native_grid(crs: CRS, transform: Affine, scale: float) -> bool:
    """Already metric, north-up and at the target resolution?"""
    if not (crs.is_projected and crs.linear_units in ("metre", "meter")):
        return False
    if transform.b != 0 or transform.d != 0:
        return False
    return (abs(abs(transform.a) - scale) / scale < 0.01
            and abs(abs(transform.e) - scale) / scale < 0.01)


def _fill_nodata(array: np.ndarray) -> np.ndarray:
    """Replace NaNs with the nearest valid value."""
    missing = ~np.isfinite(array)
    if not missing.any():
        return array
    _, (rows, cols) = ndimage.distance_transform_edt(
        missing, return_distances=True, return_indices=True)
    return array[rows, cols]


def read_upload(path: Path, bbox: Optional[Sequence[float]] = None,
                band_order: Optional[Sequence[str]] = None,
                scale: Optional[float] = None,
                max_px: int = MAX_UPLOAD_PX) -> UploadedRaster:
    """Read a GeoTIFF, PNG or JPEG onto the pipeline's 10 m metric grid.

    A georeferenced file keeps its own georeferencing; `bbox` is required
    only for a plain image, which carries none, and is read as
    [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.

    A file already at 10 m in a metric CRS is used as-is, so its reflectance
    is never resampled. Anything else is warped to the local UTM zone at
    10 m -- with area averaging when coarsening, which preserves mean
    reflectance, and bilinear interpolation when refining. Downstream
    thresholds (the 500 m^2 water-body floor, the D8 stream threshold, the
    1280 m generation windows) are all defined on that grid.
    """
    from backend.config import settings

    scale = float(scale or settings.target_scale_m)
    path = Path(path)
    if path.suffix.lower() not in UPLOAD_EXTENSIONS:
        raise UploadError(f"Unsupported file type '{path.suffix}'. Upload a "
                          f"GeoTIFF, PNG or JPEG.", status=415)
    notes: List[str] = []

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(path) as src:
                names = _identify_bands(src, band_order, notes)
                named = [n for n in names if n is not None]
                if len(named) != len(set(named)):
                    raise UploadError(f"Band names repeat: {names}.")
                valid = src.dataset_mask() > 0
                raw = {}
                for i, name in enumerate(names, start=1):
                    if name is None or name in raw:
                        continue
                    band = src.read(i).astype(np.float32)
                    band[~valid] = np.nan
                    raw[name] = band
                dtype = src.dtypes[0]
                src_crs = src.crs
                src_transform = src.transform
                width, height = src.width, src.height
    except UploadError:
        raise
    except rasterio.errors.RasterioIOError as exc:
        raise UploadError(f"Could not read the file as an image: {exc}",
                          status=415) from exc

    missing = [b for b in ("B4", "B3", "B2") if b not in raw]
    if missing:
        raise UploadError(f"The pipeline needs red, green and blue; missing "
                          f"{missing}.")

    factor = _reflectance_scale(
        {n: a for n, a in raw.items() if n in SPECTRAL_BANDS}, dtype, notes)
    for name in list(raw):
        if name in SPECTRAL_BANDS:
            raw[name] = raw[name] * factor

    georeferenced = src_crs is not None and not src_transform.is_identity
    if georeferenced:
        if bbox is not None:
            notes.append("File is georeferenced; the supplied bbox was "
                         "ignored in favour of its own coordinates.")
    else:
        if bbox is None:
            raise UploadError("This image carries no georeferencing. Supply "
                              "bbox as min_lon,min_lat,max_lon,max_lat.")
        src_crs = CRS.from_epsg(4326)
        src_transform = from_bounds(*bbox, width, height)
        notes.append(f"Georeferenced from the supplied bbox {list(bbox)}.")

    if _is_native_grid(src_crs, src_transform, scale):
        dst_crs, dst_transform = src_crs, src_transform
        dst_w, dst_h = width, height
        bands = raw
        notes.append(f"Already on a {scale:.0f} m metric grid; reflectance "
                     f"used without resampling.")
    else:
        left, bottom, right, top = rasterio.transform.array_bounds(
            height, width, src_transform)
        lon_min, lat_min, lon_max, lat_max = transform_bounds(
            src_crs, "EPSG:4326", left, bottom, right, top)
        dst_crs = (src_crs if src_crs.is_projected
                   and src_crs.linear_units in ("metre", "meter")
                   else CRS.from_string(utm_crs_for((lon_min + lon_max) / 2,
                                                    (lat_min + lat_max) / 2)))
        dst_transform, dst_w, dst_h = calculate_default_transform(
            src_crs, dst_crs, width, height, left, bottom, right, top,
            resolution=scale)
        # Area averaging when coarsening preserves mean reflectance; bilinear
        # would alias a 1 m image sampled down to 10 m.
        coarsening = _resolution_m(src_crs, src_transform,
                                   (lat_min + lat_max) / 2) < scale
        bands = {}
        for name, array in raw.items():
            out = np.full((dst_h, dst_w), np.nan, dtype=np.float32)
            reproject(source=array, destination=out,
                      src_transform=src_transform, src_crs=src_crs,
                      dst_transform=dst_transform, dst_crs=dst_crs,
                      src_nodata=np.nan, dst_nodata=np.nan,
                      resampling=(Resampling.average if coarsening
                                  else Resampling.bilinear))
            bands[name] = out
        notes.append(f"Warped to {dst_crs.to_string()} at {scale:.0f} m "
                     f"({'area-averaged' if coarsening else 'bilinear'}).")

    if not (MIN_UPLOAD_PX <= dst_w <= max_px and MIN_UPLOAD_PX <= dst_h <= max_px):
        raise UploadError(
            f"At {scale:.0f} m the scene is {dst_w}x{dst_h} px; it must be "
            f"between {MIN_UPLOAD_PX} and {max_px} px per side "
            f"({MIN_UPLOAD_PX * scale / 1000:.2f}-{max_px * scale / 1000:.2f} "
            f"km).", status=413)

    nodata = float(np.mean(~np.isfinite(bands["B4"])))
    if nodata > MAX_NODATA_FRACTION:
        raise UploadError(f"{100 * nodata:.0f}% of the scene has no data; at "
                          f"most {100 * MAX_NODATA_FRACTION:.0f}% is allowed.")
    if nodata > 0:
        notes.append(f"{100 * nodata:.1f}% no-data pixels filled from their "
                     f"nearest valid neighbour.")
    bands = {name: _fill_nodata(array).astype(np.float32)
             for name, array in bands.items()}

    median = float(np.median(np.dstack([bands["B4"], bands["B3"],
                                        bands["B2"]])))
    if median > 0.6:
        notes.append(f"Median visible value {median:.2f} is high for surface "
                     f"reflectance; the scaling may be wrong.")

    left, bottom, right, top = rasterio.transform.array_bounds(
        dst_h, dst_w, dst_transform)
    bbox_ll = list(transform_bounds(dst_crs, "EPSG:4326",
                                    left, bottom, right, top))

    return UploadedRaster(bands=bands, transform=dst_transform,
                          crs=dst_crs.to_string(), bbox=bbox_ll, notes=notes)


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
