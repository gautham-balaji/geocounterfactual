"""Stage 1: detect candidate water-harvesting structures from Sentinel-2.

The goal is a set of locations where surface water APPEARED and STAYED
between roughly 2019 and 2024, at check-dam scale, on terrain where such a
structure could plausibly be built.

Three design decisions carry most of the weight:

1. POST-MONSOON WINDOW (Nov-Feb). By November the ephemeral flow that fills
   every nala in the monsoon has stopped. Water still standing in February
   is impounded water, which is what a check-dam produces. Comparing
   monsoon-season imagery would mostly compare rainfall.

2. MULTI-YEAR PERSISTENCE, not a single before/after pair. A measured probe
   over five pilot tiles showed the naive two-year difference tracks
   rainfall, not construction: where the 2023 monsoon was 136 mm wetter than
   2018 we "detected" 99 ha of new water and 0.4 ha lost, and where it was
   179 mm drier the sign flipped. Requiring water in >= 2 of three recent
   post-monsoons AND absence in >= 2 of three early ones removes anything
   that is one wet season.

3. RAINFALL IS RECORDED, NOT ASSUMED AWAY. CHIRPS monsoon totals for both
   periods ride along on every candidate so the filter threshold can be
   tuned at collect time without re-running Earth Engine. In the probe,
   Kadapa gained 76.5 ha net on 14 mm LESS rain -- that is the signature
   worth keeping, and it is only visible if rainfall travels with the data.

Sentinel-2 L2A over India is only usable from Nov 2018 (32 scenes in that
post-monsoon window against 18 the year before), which is what sets the
early window rather than any modelling preference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import ee

S2 = "COPERNICUS/S2_SR_HARMONIZED"
CLOUD_SCORE = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
CHIRPS = "UCSB-CHG/CHIRPS/DAILY"
DEM = "COPERNICUS/DEM/GLO30_2024_1"
GAUL = "FAO/GAUL/2015/level2"


@dataclass
class DetectionConfig:
    """Every threshold in one place so the run is reproducible."""

    # --- temporal ---
    early_years: List[int] = field(default_factory=lambda: [2018, 2019, 2020])
    late_years: List[int] = field(default_factory=lambda: [2022, 2023, 2024])
    season_start_md: str = "-11-01"      # post-monsoon
    season_end_md: str = "-02-28"

    # --- persistence (the anti-rainfall filter) ---
    min_late_present: int = 2            # of len(late_years)
    max_early_present: int = 1           # of len(early_years)

    # --- water index ---
    mndwi_threshold: float = 0.0
    cloud_score_min: float = 0.55
    max_cloud_pct: int = 40
    # Water must be seen in this many separate passes within one season.
    # 1 admits single-scene cloud-shadow artifacts; 3+ throws away real
    # structures that draw down quickly. Measured on a 36 km2 test area,
    # APPEARED pixels went 346 / 83 / 38 / 22 for thresholds 1 / 2 / 3 / 4.
    min_obs_per_season: int = 2

    # --- morphology ---
    min_area_ha: float = 0.05            # 5 cells at 10 m
    max_area_ha: float = 5.0             # above this it is a tank/reservoir
    max_slope_deg: float = 2.5           # same limit rule R1 enforces
    valley_radius_m: int = 500           # focal window for valley position
    min_valley_depth_m: float = 0.5      # must sit below local mean terrain

    # --- export ---
    scale_m: int = 10
    max_pixels: int = int(1e10)
    patch_px: int = 512                  # training patch, 512 px @ 10 m


# --------------------------------------------------------------------------
# Water
# --------------------------------------------------------------------------

def _season(year: int, cfg: DetectionConfig):
    return f"{year}{cfg.season_start_md}", f"{year + 1}{cfg.season_end_md}"


def seasonal_water(geom, year: int, cfg: DetectionConfig) -> ee.Image:
    """Binary water mask for one post-monsoon season.

    MNDWI (green vs SWIR) rather than NDWI: SWIR is strongly absorbed by
    water and barely by dry soil, which matters on the bright red-soil
    backgrounds these districts have.

    Counts per-image water detections and thresholds the COUNT, rather than
    thresholding a seasonal median composite. A median over Nov-Feb samples
    the middle of the drawdown curve, so a structure that fills in November
    and is dry by February reads as land: on a test area the median approach
    found 11 candidate pixels where counting found 83. Requiring two
    separate passes keeps that sensitivity without admitting single-scene
    cloud-shadow artifacts.
    """
    start, end = _season(year, cfg)
    col = (ee.ImageCollection(S2)
           .filterBounds(geom)
           .filterDate(start, end)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cfg.max_cloud_pct))
           .linkCollection(ee.ImageCollection(CLOUD_SCORE), ["cs_cdf"]))

    def mask(img):
        return img.updateMask(img.select("cs_cdf").gte(cfg.cloud_score_min))

    def is_water(img):
        # unmask(0): a cloud-masked pixel counts as "not observed as water"
        # rather than propagating a mask that would void the whole sum.
        return (img.normalizedDifference(["B3", "B11"])
                .gt(cfg.mndwi_threshold).unmask(0).rename("w"))

    observations = col.map(mask).map(is_water).sum()

    # The band name must be constant across years. Naming it w2022, w2023
    # etc. makes the collection heterogeneous and ImageCollection.sum()
    # refuses it; the year is carried as a property instead.
    return (observations.gte(cfg.min_obs_per_season)
            .rename("water").set("season_year", year))


def persistence(geom, years: List[int], cfg: DetectionConfig) -> ee.Image:
    """How many of `years` had standing post-monsoon water, per pixel."""
    stack = [seasonal_water(geom, y, cfg) for y in years]
    return ee.ImageCollection(stack).sum().rename("count")


# --------------------------------------------------------------------------
# Rainfall
# --------------------------------------------------------------------------

def monsoon_total(years: List[int]) -> ee.Image:
    """Mean June-September rainfall across `years`, mm.

    The monsoon that fills a structure is the one preceding the post-monsoon
    observation, so year alignment matches the water seasons above.
    """
    per_year = [ee.ImageCollection(CHIRPS)
                .filterDate(f"{y}-06-01", f"{y}-09-30").sum()
                for y in years]
    return ee.ImageCollection(per_year).mean().rename("rain_mm")


# --------------------------------------------------------------------------
# Terrain
# --------------------------------------------------------------------------

def terrain(geom, crs: str, cfg: DetectionConfig) -> Dict[str, ee.Image]:
    """Slope and valley position.

    setDefaultProjection is load-bearing: ee.Terrain.slope on a raw mosaic
    returns a fully-masked band, which would silently pass every site.

    `valley_depth` is elevation below the local focal mean. A real
    impoundment sits in a depression; a bright field or a rooftop does not.
    It stands in for flow accumulation, which is impractical server-side --
    Stage 3 re-checks each surviving site against the proper D8 network in
    agents/terrain.py.
    """
    dem = (ee.ImageCollection(DEM).filterBounds(geom).select("DEM").mosaic()
           .setDefaultProjection(crs, None, 30))
    slope = ee.Terrain.slope(dem).rename("slope")
    focal = dem.focalMean(radius=cfg.valley_radius_m, units="meters")
    valley_depth = focal.subtract(dem).rename("valley_depth")
    return {"dem": dem, "slope": slope, "valley_depth": valley_depth}


# --------------------------------------------------------------------------
# Candidate assembly
# --------------------------------------------------------------------------

def district_for_point(lat: float, lon: float) -> ee.Feature:
    """The GAUL district containing a point.

    Resolving by geometry rather than by name sidesteps GAUL's pre-rename
    spellings (Cuddapah for Kadapa, Bellary for Ballari) entirely.
    """
    return ee.Feature(ee.FeatureCollection(GAUL)
                      .filterBounds(ee.Geometry.Point([lon, lat])).first())


def build_candidates(geom, crs: str, cfg: DetectionConfig,
                     region_id: str = "") -> ee.FeatureCollection:
    """Full Stage 1 + Stage 2 graph for one district.

    Returns polygons, one per candidate impoundment, carrying everything the
    collect step needs to filter further without touching Earth Engine.
    """
    early = persistence(geom, cfg.early_years, cfg)
    late = persistence(geom, cfg.late_years, cfg)

    appeared = (late.gte(cfg.min_late_present)
                .And(early.lte(cfg.max_early_present)))

    t = terrain(geom, crs, cfg)
    plausible = (t["slope"].lte(cfg.max_slope_deg)
                 .And(t["valley_depth"].gte(cfg.min_valley_depth_m)))

    candidate = appeared.And(plausible).selfMask().rename("candidate")

    # Vectorise. eightConnected because these pools follow diagonal channels;
    # a four-neighbourhood fragments them into unusable slivers.
    vectors = candidate.reduceToVectors(
        geometry=geom,
        scale=cfg.scale_m,
        geometryType="polygon",
        eightConnected=True,
        labelProperty="candidate",
        crs=crs,
        maxPixels=cfg.max_pixels,
        bestEffort=False,
    )

    # Attach the evidence. Rainfall rides along so the confound threshold is
    # tunable at collect time rather than baked into a six-hour export.
    stats = (t["slope"].rename("slope_deg")
             .addBands(t["valley_depth"].rename("valley_m"))
             .addBands(late.rename("late_seasons"))
             .addBands(early.rename("early_seasons"))
             .addBands(monsoon_total(cfg.early_years).rename("rain_early_mm"))
             .addBands(monsoon_total(cfg.late_years).rename("rain_late_mm")))

    enriched = stats.reduceRegions(collection=vectors,
                                   reducer=ee.Reducer.mean(),
                                   scale=cfg.scale_m,
                                   crs=crs)

    def annotate(f):
        g = f.geometry()
        area_m2 = g.area(maxError=1)
        perimeter = g.perimeter(maxError=1)
        centroid = g.centroid(maxError=1).coordinates()
        # 4*pi*A / P^2. A channel-following pool is elongated (low value);
        # an excavated farm pond is compact (high). Recorded, not filtered --
        # both are legitimate interventions and the distinction is useful
        # later as a caption label.
        circularity = area_m2.multiply(4 * 3.141592653589793) \
            .divide(perimeter.pow(2).max(1))
        return f.set({
            "region_id": region_id,
            "area_ha": area_m2.divide(1e4),
            "perimeter_m": perimeter,
            "circularity": circularity,
            "lon": ee.List(centroid).get(0),
            "lat": ee.List(centroid).get(1),
        })

    annotated = enriched.map(annotate)

    return annotated.filter(ee.Filter.And(
        ee.Filter.gte("area_ha", cfg.min_area_ha),
        ee.Filter.lte("area_ha", cfg.max_area_ha),
    ))


def patch_bbox(lat: float, lon: float, cfg: DetectionConfig) -> List[float]:
    """Training-patch bbox centred on a candidate.

    512 px at 10 m = 5.12 km, which is both the native Stable Diffusion
    training size and directly ingestible by data_engine.gee_loader.
    """
    import math
    half_m = cfg.patch_px * cfg.scale_m / 2.0
    dlat = half_m / 110_540.0
    dlon = half_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return [round(lon - dlon, 6), round(lat - dlat, 6),
            round(lon + dlon, 6), round(lat + dlat, 6)]
