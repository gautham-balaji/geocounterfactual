"""Sentinel-2 + Copernicus DEM ingestion via Earth Engine.

Every band and the terrain layers are packed into ONE GeoTIFF requested at a
single scale and CRS. That guarantees the optical, NIR, SWIR, elevation and
slope arrays share an identical grid and affine transform -- without it the
critic cannot overlay a slope raster on a generated RGB scene.

Corrections applied against IMPLEMENTATION_MASTER_SPEC.md section 4.3:

1. COPERNICUS/DEM/GLO30 is an ImageCollection, not an Image, and it is now
   deprecated in favour of COPERNICUS/DEM/GLO30_2024_1.
2. ee.Terrain.slope() on a .mosaic() returns a fully-masked band: a mosaic
   carries no meaningful projection. setDefaultProjection() is required, or
   the slope raster silently comes back empty and every gravity check passes.
3. QA60 is no longer reliably populated. Cloud masking uses the SCL scene
   classification plus the Cloud Score+ cs_cdf band.
4. Reflectance bands are selected BEFORE dividing by 10000, so SCL and the
   cloud-score bands are never rescaled.
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Dict, List, Optional, Sequence

import ee
import numpy as np
import rasterio
import requests
from rasterio.io import MemoryFile

from backend.config import settings
from backend.data_engine.gee_auth import initialize_gee

logger = logging.getLogger(__name__)

S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
CLOUD_SCORE_COLLECTION = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
DEM_COLLECTION = "COPERNICUS/DEM/GLO30_2024_1"

REFLECTANCE_BANDS: Sequence[str] = ("B2", "B3", "B4", "B8", "B11", "B12")

# SCL classes to reject: 3 cloud shadow, 8 cloud medium, 9 cloud high,
# 10 thin cirrus, 11 snow/ice.
SCL_REJECT_CLASSES: Sequence[int] = (3, 8, 9, 10, 11)

REFLECTANCE_SCALE = 10_000.0


@dataclass
class Scene:
    """A co-registered raster stack. Every array shares `transform` and `crs`."""

    bands: Dict[str, np.ndarray]
    transform: rasterio.Affine
    crs: str
    bbox: List[float]
    start_date: str
    end_date: str
    source: str = "gee"  # "gee" | "cache" | "synthetic"
    notes: List[str] = field(default_factory=list)

    @property
    def shape(self) -> tuple:
        return next(iter(self.bands.values())).shape

    @property
    def rgb(self) -> np.ndarray:
        """(H, W, 3) true-colour stack from B4/B3/B2."""
        return np.dstack([self.bands["B4"], self.bands["B3"], self.bands["B2"]])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Scene(shape={self.shape}, crs={self.crs}, source={self.source}, "
            f"bands={sorted(self.bands)})"
        )


def _mask_clouds(image: ee.Image) -> ee.Image:
    """Mask cloud, shadow and cirrus using SCL + Cloud Score+.

    Expects `cs_cdf` to have been attached via linkCollection().
    """
    scl = image.select("SCL")
    rejected = ee.Image.constant(0)
    for cls in SCL_REJECT_CLASSES:
        rejected = rejected.Or(scl.eq(cls))

    clear_enough = image.select("cs_cdf").gte(settings.cloud_score_threshold)
    return image.updateMask(rejected.Not().And(clear_enough))


def terrain_image(roi: ee.Geometry, crs: str) -> ee.Image:
    """Copernicus GLO-30 elevation plus slope in degrees, as two bands.

    The single definition of terrain for both the catalogue regions and
    uploads, so the projection fix below cannot be dropped from one of them.
    setDefaultProjection is load-bearing: a mosaic carries no meaningful
    projection, and without it Terrain.slope returns an entirely masked band
    -- the gravity rule then has no slope to test and passes everything.
    """
    dem = (
        ee.ImageCollection(DEM_COLLECTION)
        .filterBounds(roi)
        .select("DEM")
        .mosaic()
        .setDefaultProjection(crs, None, 30)
    )
    slope = ee.Terrain.slope(dem).rename("slope")
    return dem.rename("elevation").addBands(slope)


def build_scene_image(bbox: Sequence[float], start_date: str, end_date: str,
                      crs: str) -> ee.Image:
    """Compose the multi-band Earth Engine image for one region and window."""
    roi = ee.Geometry.BBox(*bbox)

    s2 = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", settings.max_cloudy_pixel_pct))
    )
    cloud_score = ee.ImageCollection(CLOUD_SCORE_COLLECTION).filterBounds(roi)

    # linkCollection joins on system:index, the documented way to pair a scene
    # with its Cloud Score+ record.
    composite = (
        s2.linkCollection(cloud_score, ["cs_cdf"])
        .map(_mask_clouds)
        .select(list(REFLECTANCE_BANDS))   # select BEFORE scaling
        .median()
        .divide(REFLECTANCE_SCALE)
        .clip(roi)
    )

    return composite.addBands(terrain_image(roi, crs)).clip(roi)


def _download_geotiff(image: ee.Image, bbox: Sequence[float], crs: str,
                      scale: int) -> bytes:
    """Fetch the image as a GeoTIFF byte payload."""
    url = image.getDownloadURL(
        {
            "region": ee.Geometry.BBox(*bbox),
            "scale": scale,
            "crs": crs,
            "format": "GEO_TIFF",
        }
    )
    logger.info("Downloading scene GeoTIFF from Earth Engine")
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    return response.content


def _read_geotiff(payload: bytes, band_order: Sequence[str]) -> tuple:
    """Parse GeoTIFF bytes into named arrays plus georeferencing.

    Earth Engine returns a plain GeoTIFF for single-scale requests and
    occasionally a zip of per-band TIFFs; handle both.
    """
    if payload[:2] == b"PK":  # zip archive
        bands: Dict[str, np.ndarray] = {}
        transform = crs = None
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".tif"):
                    continue
                with MemoryFile(archive.read(name)) as mem, mem.open() as src:
                    key = name.rsplit(".", 1)[0].split(".")[-1]
                    bands[key] = src.read(1).astype(np.float32)
                    transform, crs = src.transform, src.crs.to_string()
        return bands, transform, crs

    with MemoryFile(payload) as mem, mem.open() as src:
        descriptions = [d for d in (src.descriptions or []) if d]
        names = descriptions if len(descriptions) == src.count else list(band_order)
        bands = {
            name: src.read(i + 1).astype(np.float32)
            for i, name in enumerate(names[: src.count])
        }
        return bands, src.transform, src.crs.to_string()


def fetch_scene(
    bbox: Sequence[float],
    start_date: str,
    end_date: str,
    crs: str,
    scale: Optional[int] = None,
) -> Scene:
    """Download a co-registered Sentinel-2 + DEM stack for `bbox`.

    Raises on failure; callers wanting a graceful degrade should go through
    data_engine.cache.load_scene().
    """
    initialize_gee()
    scale = scale or settings.target_scale_m

    image = build_scene_image(bbox, start_date, end_date, crs)
    band_order = list(REFLECTANCE_BANDS) + ["elevation", "slope"]
    payload = _download_geotiff(image, bbox, crs, scale)
    bands, transform, actual_crs = _read_geotiff(payload, band_order)

    missing = [b for b in band_order if b not in bands]
    if missing:
        raise RuntimeError(f"Earth Engine response missing bands: {missing}")

    scene = Scene(
        bands=bands,
        transform=transform,
        crs=actual_crs or crs,
        bbox=list(bbox),
        start_date=start_date,
        end_date=end_date,
        source="gee",
    )
    logger.info("Fetched %s", scene)
    return scene


class TerrainUnavailableError(RuntimeError):
    """No usable DEM for an upload. Raised instead of fabricating terrain."""


# A DEM pixel with no data after warping is filled from its neighbours; more
# than this and the tile edge or a hole is too large to trust.
MAX_DEM_GAP_FRACTION = 0.05


def fetch_dem(bbox: Sequence[float], crs: str, scale: Optional[int] = None,
              dst_transform: Optional[rasterio.Affine] = None,
              dst_shape: Optional[tuple] = None) -> Dict[str, np.ndarray]:
    """Copernicus DEM elevation and slope for an arbitrary bbox.

    bbox is lon/lat. With dst_transform and dst_shape the result is warped
    onto that exact grid -- the grid of an uploaded image -- so slope and
    reflectance index the same ground. The optical data is never resampled
    to fit the DEM: interpolating reflectance would alter the very values the
    critic judges, whereas the DEM is already a 30 m product interpolated to
    10 m on every path.

    The request is padded by a few pixels so the warp has real data at the
    edges instead of holes. Slope is computed in Earth Engine on the 30 m DEM
    (via terrain_image), as for the catalogue regions, and then warped,
    rather than differentiated again from the upsampled elevation.
    """
    from rasterio.warp import Resampling, reproject
    from scipy import ndimage

    initialize_gee()
    scale = scale or settings.target_scale_m

    mid_lat = (bbox[1] + bbox[3]) / 2.0
    pad_lat = 5 * scale / 110_540.0
    pad_lon = 5 * scale / (111_320.0 * max(np.cos(np.radians(mid_lat)), 0.1))
    padded = [bbox[0] - pad_lon, bbox[1] - pad_lat,
              bbox[2] + pad_lon, bbox[3] + pad_lat]
    roi = ee.Geometry.BBox(*padded)

    payload = _download_geotiff(terrain_image(roi, crs).clip(roi), padded,
                                crs, scale)
    bands, transform, actual_crs = _read_geotiff(payload,
                                                 ["elevation", "slope"])
    missing = [b for b in ("elevation", "slope") if b not in bands]
    if missing:
        raise TerrainUnavailableError(f"DEM response missing {missing}")

    if dst_transform is None or dst_shape is None:
        return bands

    out: Dict[str, np.ndarray] = {}
    for name in ("elevation", "slope"):
        dst = np.full(dst_shape, np.nan, dtype=np.float32)
        reproject(source=bands[name].astype(np.float32), destination=dst,
                  src_transform=transform, src_crs=actual_crs or crs,
                  dst_transform=dst_transform, dst_crs=crs,
                  src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.bilinear)
        gaps = ~np.isfinite(dst)
        if gaps.mean() > MAX_DEM_GAP_FRACTION:
            raise TerrainUnavailableError(
                f"DEM covers only {100 * (1 - gaps.mean()):.0f}% of the "
                f"upload; is it outside Copernicus GLO-30 coverage?")
        if gaps.any():
            # Priority-flood and D8 cannot route through NaN; a NaN cell
            # compares false against everything and corrupts the queue.
            _, (rows, cols) = ndimage.distance_transform_edt(
                gaps, return_distances=True, return_indices=True)
            dst = dst[rows, cols]
        out[name] = dst.astype(np.float32)
    return out


def count_available_scenes(bbox: Sequence[float], start_date: str,
                           end_date: str) -> int:
    """How many S2 scenes pass the cloud filter -- useful for picking windows."""
    initialize_gee()
    return int(
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(ee.Geometry.BBox(*bbox))
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", settings.max_cloudy_pixel_pct))
        .size()
        .getInfo()
    )
