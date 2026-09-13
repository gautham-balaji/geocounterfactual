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
        name="Uravakonda Watershed",
        state="Anantapur District, Andhra Pradesh",
        # Verified 0.00% built-up, 31.8% slope<2.5deg,
        # 32.7% slope>5deg, baseline NDVI 0.171.
        bbox=[77.38, 14.9, 77.42, 14.94],
        baseline_ndvi=0.171,
        climate_zone="Semi-Arid Rain Shadow",
    ),
    "kadapa": Region(
        id="kadapa",
        name="Kadapa Schist Basin",
        state="Kadapa District, Andhra Pradesh",
        # Verified 0.04% built-up, 46.8% slope<2.5deg,
        # 44.4% slope>5deg, baseline NDVI 0.159.
        bbox=[79.0898, 14.6622, 79.1298, 14.7022],
        baseline_ndvi=0.159,
        climate_zone="Semi-Arid Rain Shadow",
    ),
    "kurnool": Region(
        id="kurnool",
        name="Kurnool Erra Basin",
        state="Kurnool District, Andhra Pradesh",
        # Verified 0.22% built-up, 44.9% slope<2.5deg,
        # 40.4% slope>5deg, baseline NDVI 0.179.
        bbox=[77.9201, 15.3924, 77.9601, 15.4324],
        baseline_ndvi=0.179,
        climate_zone="Semi-Arid Rain Shadow",
    ),
    "kolar": Region(
        id="kolar",
        name="Kolar Plateau",
        state="Kolar District, Karnataka",
        # Verified 0.61% built-up, 37.6% slope<2.5deg,
        # 35.6% slope>5deg, baseline NDVI 0.208.
        bbox=[77.8552, 13.7526, 77.8952, 13.7926],
        baseline_ndvi=0.208,
        climate_zone="Semi-Arid Deccan Scrub",
    ),
    "chitradurga": Region(
        id="chitradurga",
        name="Chitradurga Scrubland",
        state="Chitradurga District, Karnataka",
        # Verified 0.45% built-up, 38.4% slope<2.5deg,
        # 36.8% slope>5deg, baseline NDVI 0.268.
        bbox=[76.4728, 13.969, 76.5128, 14.009],
        baseline_ndvi=0.268,
        climate_zone="Semi-Arid Deccan Scrub",
    ),
    "bellary": Region(
        id="bellary",
        name="Ballari Granite Scrub",
        state="Ballari District, Karnataka",
        # Verified 0.08% built-up, 46.4% slope<2.5deg,
        # 36.7% slope>5deg, baseline NDVI 0.168.
        bbox=[76.5646, 15.1563, 76.6046, 15.1963],
        baseline_ndvi=0.168,
        climate_zone="Semi-Arid Deccan Scrub",
    ),
    "marathwada": Region(
        id="marathwada",
        name="Beed Basin Watershed",
        state="Beed District, Maharashtra",
        # Verified 0.78% built-up, 44.4% slope<2.5deg,
        # 38.4% slope>5deg, baseline NDVI 0.180.
        bbox=[75.35, 18.75, 75.39, 18.79],
        baseline_ndvi=0.18,
        climate_zone="Deccan Trap Arid Plateau",
    ),
    "jalna": Region(
        id="jalna",
        name="Jalna Basalt Upland",
        state="Jalna District, Maharashtra",
        # Verified 0.62% built-up, 34.6% slope<2.5deg,
        # 43.8% slope>5deg, baseline NDVI 0.210.
        bbox=[75.9906, 20.5278, 76.0306, 20.5678],
        baseline_ndvi=0.21,
        climate_zone="Deccan Trap Arid Plateau",
    ),
    "ahmednagar": Region(
        id="ahmednagar",
        name="Ahmednagar Rain Shadow",
        state="Ahmednagar District, Maharashtra",
        # Verified 0.82% built-up, 40.0% slope<2.5deg,
        # 44.9% slope>5deg, baseline NDVI 0.173.
        bbox=[74.2788, 19.2805, 74.3188, 19.3205],
        baseline_ndvi=0.173,
        climate_zone="Deccan Trap Arid Plateau",
    ),
    "jodhpur": Region(
        id="jodhpur",
        name="Jodhpur Arid Fringe",
        state="Jodhpur District, Rajasthan",
        # Verified 0.13% built-up, 38.0% slope<2.5deg,
        # 36.1% slope>5deg, baseline NDVI 0.130.
        bbox=[73.2394, 26.7518, 73.2794, 26.7918],
        baseline_ndvi=0.13,
        climate_zone="Arid Aravalli Fringe",
    ),
    "pali": Region(
        id="pali",
        name="Pali Aravalli Foothills",
        state="Pali District, Rajasthan",
        # Verified 0.24% built-up, 45.3% slope<2.5deg,
        # 37.9% slope>5deg, baseline NDVI 0.217.
        bbox=[73.1795, 24.9573, 73.2195, 24.9973],
        baseline_ndvi=0.217,
        climate_zone="Arid Aravalli Fringe",
    ),
    "jhansi": Region(
        id="jhansi",
        name="Jhansi Bundelkhand Plateau",
        state="Jhansi District, Uttar Pradesh",
        # Verified 0.08% built-up, 30.5% slope<2.5deg,
        # 36.4% slope>5deg, baseline NDVI 0.255.
        bbox=[79.3442, 25.6108, 79.3842, 25.6508],
        baseline_ndvi=0.255,
        climate_zone="Bundelkhand Dry Plateau",
    ),
    "bundelkhand": Region(
        id="bundelkhand",
        name="Panna Plateau Watershed",
        state="Panna District, Madhya Pradesh",
        # Verified 0.00% built-up, 44.9% slope<2.5deg,
        # 35.9% slope>5deg, baseline NDVI 0.280.
        bbox=[79.8, 24.45, 79.84, 24.49],
        baseline_ndvi=0.28,
        climate_zone="Hard-Rock Granitic Terrain",
    ),
    "tikamgarh": Region(
        id="tikamgarh",
        name="Tikamgarh Granite Belt",
        state="Tikamgarh District, Madhya Pradesh",
        # Verified 0.53% built-up, 37.8% slope<2.5deg,
        # 32.3% slope>5deg, baseline NDVI 0.216.
        bbox=[78.9274, 25.0931, 78.9674, 25.1331],
        baseline_ndvi=0.216,
        climate_zone="Hard-Rock Granitic Terrain",
    ),
    "sagar": Region(
        id="sagar",
        name="Sagar Vindhyan Upland",
        state="Sagar District, Madhya Pradesh",
        # Verified 0.05% built-up, 42.5% slope<2.5deg,
        # 42.0% slope>5deg, baseline NDVI 0.270.
        bbox=[78.6533, 23.8725, 78.6933, 23.9125],
        baseline_ndvi=0.27,
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
    # Verified present in the live models.list() for this key alongside
    # gemini-3.5-flash. Override with GEMINI_MODEL.
    gemini_model: str = "gemini-3.8-flash"

    # --- Generator backend: stub | local | remote (see generator/base.py) ---
    generator_backend: str = "stub"
    remote_generator_url: Optional[str] = None
    # Used when the primary backend raises (expired ngrok tunnel, dead Colab
    # runtime). "stub" is instant; "local" would stall a demo for minutes.
    generator_fallback: str = "stub"

    # --- Fine-tuned adapter and the scale it was trained at ---
    # MUST match extract_pairs --patch-span-m / --out-px. The LoRA learned
    # structures at 1280 m rendered to 512 px (2.5 m/px). Generating over a
    # whole 4.4 km scene resized to ~448 px is 10 m/px, a 4x difference,
    # and shows the adapter terrain at a scale it never saw.
    generation_patch_span_m: int = 1280
    generation_patch_px: int = 512
    max_patches_per_scene: int = 8
    lora_weights_path: Optional[Path] = (
        BACKEND_DIR / "generator" / "weights" / "geocf_lora.safetensors")
    lora_scale: float = 0.85

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
