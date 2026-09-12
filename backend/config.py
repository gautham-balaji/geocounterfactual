"""Central configuration: settings, paths, and the pilot-region registry.

Region ids and baseline metrics intentionally mirror src/data/mockData.js so the
frontend can fall back to mock data without the shapes diverging.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent


def utm_epsg_for_lon(lon: float, northern: bool = True) -> str:
    """Return the UTM EPSG code covering `lon`.

    Slope, distances and areas must be computed on a metric grid; doing that in
    EPSG:4326 would make a degree-sized pixel and corrupt every physics rule.
    """
    zone = int((lon + 180.0) / 6.0) + 1
    return f"EPSG:{(32600 if northern else 32700) + zone}"


class Region(BaseModel):
    """A pilot watershed. bbox is [min_lon, min_lat, max_lon, max_lat]."""

    id: str
    name: str
    state: str
    bbox: List[float]
    baseline_ndvi: float
    climate_zone: str

    @property
    def crs(self) -> str:
        centre_lon = (self.bbox[0] + self.bbox[2]) / 2.0
        centre_lat = (self.bbox[1] + self.bbox[3]) / 2.0
        return utm_epsg_for_lon(centre_lon, northern=centre_lat >= 0)


# Bboxes are ~4 km squares. At 10 m that is ~440x440 px x 8 bands -- well
# inside Earth Engine's 32 MB / 50 M-pixel getDownloadURL ceiling, so scenes
# download synchronously with no Drive export.
#
# IMPORTANT -- these are NOT the coordinates in IMPLEMENTATION_MASTER_SPEC.md
# or src/data/mockData.js. Those were district-headquarters city centroids and
# measured 75%, 89% and 44% built-up against ESA WorldCover: dense urban, with
# no stream beds to dam. Each has been relocated to a rural watershed in the
# same district, selected by scanning ~150 candidate tiles for zero built-up
# cover plus a balance of flat valley floor (dam sites) and >5 deg ridges (so
# the critic's gravity rule is genuinely exercised). Region ids are unchanged
# so the frontend contract still matches.
REGIONS: Dict[str, Region] = {
    "anantapur": Region(
        id="anantapur",
        name="Uravakonda Watershed, Anantapur",
        state="Andhra Pradesh, India",
        # Braided dry stream bed (nala) with riparian fringe and red-soil
        # farmland. 0.0% built-up, 31.8% slope<2.5deg, 32.7% slope>5deg.
        bbox=[77.38, 14.90, 77.42, 14.94],
        baseline_ndvi=0.171,
        climate_zone="Semi-Arid Rain Shadow",
    ),
    "marathwada": Region(
        id="marathwada",
        name="Beed Basin Watershed, Marathwada",
        state="Maharashtra, India",
        # 0.78% built-up, 44.4% flat, 38.4% steep.
        bbox=[75.35, 18.75, 75.39, 18.79],
        baseline_ndvi=0.18,
        climate_zone="Deccan Trap Arid Plateau",
    ),
    "bundelkhand": Region(
        id="bundelkhand",
        name="Panna Plateau Watershed, Bundelkhand",
        state="Madhya Pradesh, India",
        # 0.00% built-up, 44.9% flat, 35.9% steep.
        bbox=[79.80, 24.45, 79.84, 24.49],
        baseline_ndvi=0.28,
        climate_zone="Hard-Rock Granitic Terrain",
    ),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Earth Engine ---
    gee_project_id: str = "geocounterfactual-backend"
    gee_key_path: Path = BACKEND_DIR / "secrets" / "gcf-backend.json"

    # --- Planner LLM (Gemini) ---
    # Model id is configurable rather than hardcoded: the available Gemini
    # model names move, and a stale literal would surface as a runtime 404.
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"

    # --- Generator backend: stub | local | remote (see generator/base.py) ---
    generator_backend: str = "stub"
    remote_generator_url: Optional[str] = None

    # --- Data engine ---
    target_scale_m: int = 10
    cloud_score_threshold: float = 0.60
    max_cloudy_pixel_pct: int = 35
    allow_synthetic_fallback: bool = True

    # --- Critic ---
    max_critic_iterations: int = 3
    max_slope_for_water_deg: float = 2.5
    max_annual_ndvi_delta: float = 0.35
    min_outside_ssim: float = 0.90

    # --- Paths ---
    cache_dir: Path = BACKEND_DIR / "data" / "cache"
    static_dir: Path = BACKEND_DIR / "static"

    def ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
