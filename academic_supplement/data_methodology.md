# Data methodology

Supplementary material for the GeoCounterfactual paper: study area, Earth
observation inputs, the detection of water-harvesting structures, the
rainfall confound, and the construction of the training set.

## How to read this document

Every quantitative statement is tagged with its provenance, so that the
paper cites only what was measured and states design choices as choices.

- **[M]** Measured from the data or code in this repository. The source is
  given, and the figure can be regenerated.
- **[D]** A design decision, with its rationale. Not an empirical claim.
- **[P]** A figure from a development-time probe that is recorded in the
  code, but whose full run output is not stored in the repository.
- **[N]** Not yet measured. Do not state it as a result.

All paths are relative to the repository root. Figures were verified
against the code and the local data on 2026-10-11.

---

## 1. Study area

**Selection criteria [D].** Fifteen rural watersheds in semi-arid peninsular
and central India, in six states (Andhra Pradesh, Karnataka, Maharashtra,
Madhya Pradesh, Rajasthan, Uttar Pradesh). Each tile is about 4.4 × 4.4 km.
Each is in a district where small water-harvesting structures (check dams,
farm ponds, percolation tanks) are built under MGNREGA and watershed
programmes. Each tile was required to contain:

1. **Almost no built-up land.** Built-up area, measured against ESA
   WorldCover, is 0.00–0.82% across the 15 tiles [M; `backend/config.py`,
   comment above each region]. Urban texture would dominate the structural
   similarity term of the critic (rule R4) and would contain no stream beds
   to dam.
2. **Both flat valley floors and steep ground.** Between 30.5% and 46.8% of
   each tile is below 2.5° [M; same source]. The gravity rule (R1) needs
   flat ground where water may rest *and* steep ground where it may not, or
   it cannot discriminate.

**Relocation from district centres [M].** The original project
specification placed three pilot regions at district-headquarters
centroids. Against WorldCover these measured **75%, 89% and 44% built-up**
[M; `backend/config.py:51-54`]. Each was relocated to a rural watershed in
the same district by scanning about 150 candidate tiles for zero built-up
cover and a mix of flat and steep terrain. The paper should report this: a
watershed study sited on a city block would have measured nothing.

**Administrative labels [D].** District names were checked by
point-in-polygon against FAO GAUL level 2, not taken from the bounding box
that was drawn (`district_for_point` in `water_detection.py`). [P] During
site selection this caught two candidate tiles that fell outside their
nominal district (a "Kolar" pick in Chittoor, Andhra Pradesh, and a
"Jhansi" pick in Tikamgarh, Madhya Pradesh), which were re-sited. The
current tiles all lie in the districts named in `backend/config.py`. This
episode is recorded in the development log, not the repository; cite it as
a procedural note, if at all.

---

## 2. Earth observation inputs

| Input | Product | Use |
|---|---|---|
| Optical | Sentinel-2 L2A, `COPERNICUS/S2_SR_HARMONIZED` | B2, B3, B4, B8 (10 m); B11, B12 (20 m, delivered on the 10 m grid) |
| Cloud mask | Scene Classification (SCL) + Cloud Score+ `cs_cdf` | SCL classes 3, 8, 9, 10, 11 rejected; `cs_cdf ≥ 0.60` |
| Elevation | Copernicus GLO-30, `COPERNICUS/DEM/GLO30_2024_1` | Elevation; slope via `ee.Terrain.slope` |
| Rainfall | CHIRPS daily, `UCSB-CHG/CHIRPS/DAILY` | June–September monsoon totals |
| Land cover | ESA WorldCover | Region screening only |
| Boundaries | FAO GAUL 2015 level 2 | District labels |

**Baseline scene [M; `backend/agents/input_handler.py`,
`backend/data_engine/gee_loader.py`].** For each region, a median composite
of cloud-masked scenes from 1 January–30 June 2019. Scenes with
`CLOUDY_PIXEL_PERCENTAGE ≥ 35` are excluded before masking. Reflectance
bands are selected *before* dividing by 10,000, so the SCL and cloud-score
bands are never rescaled.

**Single-request co-registration [D].** All reflectance bands, elevation and
slope are requested from Earth Engine as one multi-band image at one scale
(10 m) and one projected CRS (the local UTM zone). Every array therefore
shares one affine transform. The critic overlays a slope raster on a
generated RGB scene pixel by pixel, so a sub-pixel misregistration between
terrain and optics would corrupt every gravity verdict.

**Two corrections to the Earth Engine recipe [M].** Both are worth a
methods footnote, because each produces wrong results silently:

1. `COPERNICUS/DEM/GLO30` is an ImageCollection, not an Image, and is
   deprecated in favour of `GLO30_2024_1`.
2. `ee.Terrain.slope()` applied to a `.mosaic()` returns a fully masked
   band, because a mosaic has no meaningful projection.
   `setDefaultProjection(crs, None, 30)` is required. Without it the slope
   raster is empty and **the gravity rule passes every scene while testing
   nothing**. Terrain is defined once, in `terrain_image()`
   (`backend/data_engine/gee_loader.py`), and shared by the region pipeline
   and the upload pipeline so the fix cannot be lost from either.

**Spectral indices [D; `backend/data_engine/indices.py`].**

| Index | Formula | Role |
|---|---|---|
| NDVI | (B8 − B4)/(B8 + B4) | Vegetation; rule R2 growth ceiling, rule R3 |
| NDWI (McFeeters) | (B3 − B8)/(B3 + B8) | Open water in the critic (R1, R3) |
| NDMI | (B8 − B11)/(B8 + B11) | Soil-moisture proxy for the moisture layer |
| MNDWI | (B3 − B11)/(B3 + B11) | Water in candidate detection |

Detection uses MNDWI rather than NDWI. SWIR is strongly absorbed by water
and only weakly by dry soil, which matters on the bright red-soil
backgrounds of these districts.

---

## 3. Why 10 m Sentinel-2

The claim to make is that Sentinel-2 at 10 m is **the best trade-off among
openly licensed sensors** for structures of this size. Not that 10 m is
optimal in any absolute sense. The argument has five parts.

**3.1 Structure size [M].** Candidate structures are 0.05–5 ha by
construction (the morphology filter). The 1,155 training structures are
1.00–4.97 ha, median 1.80 ha, mean 2.17 ha [M; `backend/data/pairs/*/meta.json`].

| Sensor (ground sampling) | Pixels covered by a 1 ha structure | By the 0.05 ha detection floor |
|---|---|---|
| Sentinel-2 (10 m) | 100 | 5 |
| Landsat 8/9 (30 m) | ~11 | < 1 |
| MODIS (250 m) | 0.16 | ≪ 1 |

At 30 m, the smallest structures in the study fall below a single pixel,
and a typical one spans a handful of mixed pixels. Its shape, and so its
plausibility under rules R1 and R4, cannot be judged.

**3.2 Spectral content [D].** The four bands the critic depends on most
(B2, B3, B4 for the image and B8 for NDVI and NDWI) are native 10 m.
Commercial very-high-resolution products (e.g. PlanetScope at about 3 m) are
not openly licensed, lack SWIR, and their NIR calibration varies between
satellites in the constellation. That weakens a physics critic built on
band ratios. SWIR (B11) is 20 m native; MNDWI-based detection therefore has
an effective resolution of 20 m, which is one reason for the 0.05 ha (5
cell) minimum area.

**3.3 Temporal density [M/D].** Detection requires a pixel to be seen as
water on at least two separate overpasses within one post-monsoon season
(§4.2). That requires a revisit of a few days through the November–February
window. The code records that Sentinel-2 L2A over India becomes reliably
usable from November 2018 (32 scenes in that post-monsoon window against 18
the year before) [P; `backend/data_engine/water_detection.py`, module
docstring]. That sets the earliest "before" season.

**3.4 The DEM bounds useful resolution [D].** Slope comes from the 30 m
Copernicus DEM. Finer optical imagery would not sharpen the gravity test,
because the terrain it is checked against is itself 30 m.

**3.5 What 10 m cannot do [D].** At 10 m the dam wall (masonry a few metres
wide) is not resolved. Structures are identified by their **impoundment**,
the standing water and the wetted fringe, not their masonry. The generated
counterfactuals inherit this limit (see `limitations.md` §3).

---

## 4. Detecting water-harvesting structures

MGNREGA asset records were the intended ground truth. [P] They proved
inaccessible: the GeoMGNREGA application returned HTTP 403, and all 606
Integrated Watershed Management Programme layers enumerated on ISRO Bhuvan
contain drainage lines but no structure points. (Assessed in September
2026; the evidence is in the development log, not the repository. Access
may differ for institutional users, and NRSC was contacted separately.) The
training set was therefore built by
**detecting** structures from Sentinel-2 directly. The structures are
detections, not verified records (`limitations.md` §5).

The method is in `backend/data_engine/water_detection.py`
(`DetectionConfig` holds every threshold). It was run as Earth Engine batch
exports by `backend/experiments/detect_candidates.py`.

### 4.1 Post-monsoon window [D]

Water is observed from **1 November to 28 February**. By November the
monsoon's ephemeral stream flow has stopped, so water still standing in
February is impounded water, which is what a check dam produces. Comparing
monsoon-season imagery would mostly compare rainfall.

### 4.2 Per-observation counting, not a seasonal composite [M]

Each cloud-free observation is classified as water where MNDWI > 0
(`cs_cdf ≥ 0.55`; scenes with cloud > 40% excluded). A pixel counts as water
for the season if it is water on **at least two separate overpasses**.

- **A seasonal median composite misses draw-down.** A structure that fills
  in November and is dry by February reads as land in a median. On a test
  area, the median approach found **11** candidate pixels where per-image
  counting found **83** [P; `water_detection.py`, `seasonal_water`
  docstring].
- **Sensitivity of the two-observation threshold.** On a 36 km² test area,
  requiring 1, 2, 3 or 4 observations gave **346 / 83 / 38 / 22** newly
  appearing pixels [P; `DetectionConfig.min_obs_per_season` comment]. One
  observation admits single-scene cloud-shadow artefacts; three or more
  discard real structures that draw down quickly.

### 4.3 Multi-year persistence [D]

| Window | Seasons |
|---|---|
| Early | post-monsoon 2018–19, 2019–20, 2020–21 |
| Late | post-monsoon 2022–23, 2023–24, 2024–25 |

A pixel is a candidate if it holds water in **≥ 2 of the 3 late seasons**
and in **≤ 1 of the 3 early seasons**. Requiring persistence across
seasons, rather than comparing one year with another, removes anything
explained by a single wet season. §5 explains why that matters.

### 4.4 Morphology and terrain [D]

Connected water components are kept if they are:

- **0.05–5 ha.** Smaller is speckle; larger is a tank or reservoir, not a
  small structure.
- **On slope ≤ 2.5°.** The same limit the critic's rule R1 enforces.
- **At least 0.5 m below the mean terrain within 500 m.** The structure
  must sit in a valley position.

### 4.5 Output [M; `backend/data/candidates/candidates.csv`]

**82,516 candidates** in **12** of the 15 regions. The detection exports
were dispatched for 12 regions. Bundelkhand, Jhansi and Pali have no
candidate set; the paper must not imply all 15 were surveyed.

---

## 5. The rainfall confound

This is the central methodological finding of the data pipeline. The paper
should give it its own subsection.

### 5.1 The naive method measures weather [P]

The obvious way to find new structures is to compare one "before" season
with one "after" season and call new water a new structure. A feasibility
probe did this for five pilot tiles, comparing post-monsoon 2018 with 2023
(single years). It recorded both water that **appeared** and water that
**disappeared**. The disappearing column is a built-in control: genuine
construction adds water, while rainfall variability moves it in both
directions.

| Tile | Δ monsoon rainfall, 2023 vs 2018 | New water | Lost water | Net |
|---|---|---|---|---|
| Marathwada | **+136 mm** | 99.1 ha | 0.4 ha | +98.8 ha |
| Tikamgarh | −179 mm | 4.9 ha | 11.8 ha | −6.9 ha |
| Kadapa | **−14 mm** | 77.2 ha | 0.6 ha | **+76.5 ha** |

Provenance: the Marathwada (+136 mm, 99 ha new, 0.4 ha lost) and Kadapa
(+76.5 ha net on 14 mm less rain) figures are recorded in the
`water_detection.py` module docstring. The tile 179 mm drier "flipped the
sign" (same docstring); its per-tile figures, and the labelling of that
tile as Tikamgarh, come from the probe's run output, which is not stored in
the repository. The paper should either cite all three rows as a pilot
observation or re-run the probe; rerunning is cheap.

**Interpretation.** Where the later monsoon was wetter (Marathwada, about
41% wetter, per `detect_candidates.py`), a large area of "new water"
appeared and almost none disappeared. That is the signature of rainfall,
not construction. Where it was drier, the sign flipped. **Kadapa gained
76.5 ha net on slightly *less* rain**, which no weather explanation
accounts for; it is the signature of construction. Without the rainfall
record, Marathwada would have ranked as the most successful district, and
the training set would have taught the generator that "a wetter year looks
wetter".

### 5.2 The filter [D; M for thresholds]

Two defences are applied:

1. **Persistence (§4.3)** removes changes that are a single wet season.
2. **A rainfall ratio** is recorded on every candidate. CHIRPS daily
   rainfall is summed over **1 June–29 September** of each year (the Earth
   Engine end date is exclusive), averaged over the three years of each
   window, and expressed as

       rain_ratio = mean late-window monsoon / mean early-window monsoon

| Tier | Rule | Meaning |
|---|---|---|
| `strong` | rain_ratio ≤ **1.00** | Water appeared **despite** no more rain: strongest evidence of construction |
| `accepted` | 1.00 < rain_ratio ≤ **1.15** | Water appeared with at most 15% more rain |
| `rain_confounded` | rain_ratio > 1.15 | Plausibly explained by a wetter late period; excluded |

[M; `backend/experiments/detect_candidates.py`, `MAX_RAIN_RATIO`,
`STRONG_RAIN_RATIO`.] The filter is applied **at collection time, on the
client**, not inside the Earth Engine export, so thresholds can be revised
without re-running a six-hour export. Each candidate carries its own rainfall
evidence.

### 5.3 Result [M; `candidates.csv`]

| Tier | Candidates | Share |
|---|---|---|
| strong | 65,334 | 79.2% |
| accepted | 13,729 | 16.6% |
| rain_confounded | 3,453 | 4.2% |
| **total** | **82,516** | |

### 5.4 The tier is effectively a district property [M]

CHIRPS has a native resolution of about 0.05° (~5.5 km), comparable to a
whole study tile. All candidates in a district therefore share nearly the
same rain ratio, and **tier membership is decided by district rainfall
regime, not by individual structures**:

| District | strong | accepted | rain_confounded |
|---|---|---|---|
| Ahmednagar | 3,273 | 1,633 | 0 |
| Anantapur | 11,478 | 1,214 | 0 |
| Bellary | 15,670 | 0 | 0 |
| Chitradurga | 2,710 | 6 | 0 |
| Jalna | 3,211 | 1,740 | 33 |
| Jodhpur | 0 | 44 | 1,330 |
| Kadapa | 9,198 | 2,260 | 0 |
| Kolar | 983 | 3,521 | 1,304 |
| Kurnool | 14,273 | 0 | 0 |
| Marathwada | 133 | 1,891 | 786 |
| Sagar | 4,274 | 0 | 0 |
| Tikamgarh | 131 | 1,420 | 0 |

Bellary, Kurnool and Sagar are entirely `strong`; Jodhpur is 97%
`rain_confounded`. The paper must state the consequence: **the tiers differ
in geography and rainfall regime as well as in evidential strength**. A
per-structure rainfall test would need rainfall data at finer resolution
than CHIRPS.

---

## 6. Training pairs

### 6.1 Selection [M]

Training pairs were drawn from the **`accepted` tier only** (`extract_pairs
--confidence accepted` selects exactly that tier), with area ≥ 1 ha. That
pool contains **1,155 structures**, and all 1,155 were extracted. The run
requested a sample of 1,500 but the pool was smaller. **The training set is
the complete accepted-tier, ≥ 1 ha population, not a random sample of it.**

| District | Pairs |
|---|---|
| Kolar | 379 |
| Kadapa | 228 |
| Marathwada | 154 |
| Anantapur | 142 |
| Jalna | 117 |
| Tikamgarh | 68 |
| Ahmednagar | 65 |
| Chitradurga | 1 |
| Jodhpur | 1 |

[M; `backend/data/pairs/manifest.jsonl` joined to `candidates.csv`.]

The training set is geographically skewed (Kolar alone is 33%). **Bellary,
Kurnool and Sagar contribute nothing**, because §5.4 placed all their
candidates in the `strong` tier.

Properties of the 1,155 structures [M]:

| Property | Value |
|---|---|
| Area | 1.00–4.97 ha (median 1.80, mean 2.17) |
| Rain ratio | 1.000–1.150 (median 1.038) |
| Slope at the structure | median 0.97° |
| Depth below 500 m mean terrain | median 3.08 m |
| Circularity | median 0.159; 79% below 0.25 |

Low circularity reflects the morphology: these are elongated **channel
impoundments** behind check dams, not round ponds.

### 6.2 The held-out set [M/N]

The `strong` tier (65,334 candidates; **5,047 of them ≥ 1 ha**) was **never
used for training**, and the detection code earmarks it for validation.
This gives a held-out set separated from the training set by a
pre-registered rule. Two properties must be stated with it:

- **It is not identically distributed.** It differs in district and
  rainfall regime (§5.4), so an evaluation on it measures generalisation
  across districts as well as within them.
- **[N] Historical validation on it has not yet been run.** The paper must
  not report validation metrics until it has.

### 6.3 Framing [M/D]

Each pair is a **1,280 m** window centred on the structure, at 10 m (about
129–130 px native). It is percentile-stretched to 8-bit and resampled to
**512 × 512 px** with a Lanczos filter (about 4×, 2.5 m/px)
[M; `meta.json` shapes; `extract_pairs.py`].

- "Before" is the post-monsoon composite of **November 2018–February 2019**.
- "After" is **November 2024–February 2025**.

The 1,280 m span is a design choice [D]. In a 5,120 m frame (512 px at
10 m) the median structure would occupy well under 1% of the image, and
before and after would be nearly identical. At 1,280 m the synthetic
training masks (`architecture_decisions.md` §3.5) cover **0.78–3.45%** of the
frame, median 1.36% [M].

Each pair carries a caption generated from its metadata, for example:
*"aerial satellite view, semi-arid Indian watershed, 1.79 hectare water
harvesting structure, elongated channel impoundment, slope 1.5 degrees, 10 m
Sentinel-2 true colour."*

---

## 7. Reproducibility

| Step | Command |
|---|---|
| Detection | `python -m backend.experiments.detect_candidates dispatch / status / collect` |
| Pairs | `python -m backend.experiments.extract_pairs --confidence accepted --min-area-ha 1.0 --patch-span-m 1280 --out-px 512 --seed 42` |
| Region data check | `python -m backend.tests.test_phase1_live` |
| Region catalogue | `python -m backend.tests.test_region_catalog` |

Earth Engine project: `geocounterfactual-backend`. Every detection threshold
is in `DetectionConfig`, every critic threshold in `backend/config.py`
(`Settings`).

## References to cite (verify bibliographic details before submission)

- Funk, C. et al. (2015). The climate hazards infrared precipitation with
  stations (CHIRPS). *Scientific Data*.
- McFeeters, S. K. (1996). The use of the Normalized Difference Water Index
  (NDWI) in the delineation of open water features. *IJRS*.
- Xu, H. (2006). Modification of normalised difference water index (MNDWI).
  *IJRS*.
- Tucker, C. J. (1979). Red and photographic infrared linear combinations
  for monitoring vegetation. *Remote Sensing of Environment*.
- Gao, B.-C. (1996). NDWI: a normalized difference water index for remote
  sensing of vegetation liquid water. *Remote Sensing of Environment*
  (the SWIR-based index used here as NDMI).
- Pasquarella, V. J. et al. (2023). Cloud Score+ for Sentinel-2.
  *CVPR Workshops*.
- Zanaga, D. et al. ESA WorldCover 10 m (2020/2021), v100/v200.
- Copernicus DEM GLO-30, European Space Agency.
- Pekel, J.-F. et al. (2016). High-resolution mapping of global surface
  water and its long-term changes. *Nature*. Relevant because the JRC
  Global Surface Water record did not extend to the 2022–2024 "late" window
  when this pipeline was built [P; check the current dataset version before
  stating it], which is why detection uses Sentinel-2 MNDWI directly.
