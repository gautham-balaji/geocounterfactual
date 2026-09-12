# GeoCounterfactual — Master Implementation Spec & Claude Code Onboarding Document

> **Target Audience:** AI Coding Agent (Claude Code in VS Code) & Development Team  
> **Document Purpose:** Complete technical onboarding, architectural blueprint, repository state, data engineering protocols, and phased implementation roadmap to transition from the frontend UI prototype into the real LangGraph multi-agent backend.  
> **Date of Generation:** September 2026  
> **Source Documents Integrated:** `GeoCounterfactual_Onboarding_Doc.md`, Frontend Prototype Codebase (`src/`), Review Presentation Scripts, and System Architecture Diagrams.

---

## Table of Contents
1. [Project Identity & Research Mission](#1-project-identity--research-mission)
2. [Current Repository State & Frontend Inventory](#2-current-repository-state--frontend-inventory)
3. [Target System Architecture (LangGraph Multi-Agent Engine)](#3-target-system-architecture-langgraph-multi-agent-engine)
4. [Earth Observation & Data Ingestion Pipeline (GEE + Sentinel-2)](#4-earth-observation--data-ingestion-pipeline-gee--sentinel-2)
5. [Generative Core (Diffusion + ControlNet Conditioning)](#5-generative-core-diffusion--controlnet-conditioning)
6. [The Physical-Plausibility Critic (Rules & Physics Engine)](#6-the-physical-plausibility-critic-rules--physics-engine)
7. [API Contract & Frontend-Backend Integration](#7-api-contract--frontend-backend-integration)
8. [Open Decisions & Technical Trade-Offs](#8-open-decisions--technical-trade-offs)
9. [Step-by-Step Implementation Roadmap for Claude Code](#9-step-by-step-implementation-roadmap-for-claude-code)

---

## 1. Project Identity & Research Mission

### 1.1 The One-Line Pitch
**GeoCounterfactual** is a multi-agent generative framework where specialized AI agents collaborate with a physics-based critic to generate high-resolution future satellite imagery demonstrating the outcome of rural environmental interventions (e.g., check-dams, afforestation) years after execution, allowing rural planners to *visually verify* physical feasibility before allocating capital.

### 1.2 The Core Problem & Social Cause
In India, rural environmental and water conservation interventions under schemes like MGNREGA, watershed development programs, and afforestation drives are planned and funded blind:
1. **No Visual Counterfactual:** Officials rely on dry statistical tables or intuition. Existing GIS AI models classify historical land cover or predict isolated metrics (e.g., *"NDVI will rise by 0.15"*), which fails to intuitively communicate outcomes to village panchayats and funding review panels.
2. **Generative Hallucination Risk:** Asking a naive generative model (like unconstrained Stable Diffusion or DALLE) to "imagine the future" results in physical absurdities—such as water bodies resting on 15° slopes or forests blooming where soil moisture cannot support them.
3. **Academic Novelty Defense:** This project is deliberately built around **generative image synthesis with a closed critic feedback loop**, not recommendation or decision-making. This directly defeats the common critique: *"Why couldn't ChatGPT or Claude just do this with text?"* A georeferenced, physics-constrained synthetic satellite image cannot be produced by an LLM alone.

### 1.3 Key Success Criteria for the Academic Jury
- Deliver an end-to-end working pipeline: Current satellite scene + text intervention $\to$ Georeferenced future satellite image.
- Demonstrate a **statistically measurable benefit from the closed Critic loop** (Plausibility violation rate with Critic-ON vs. Critic-OFF).
- Validate the model on **historical interventions** where the actual outcome already occurred (measured via SSIM, NDVI RMSE, and spectral consistency).

---

## 2. Current Repository State & Frontend Inventory

The project currently contains a fully responsive, dark-mode, command-center frontend prototype built with React, Vite, Tailwind CSS, Framer Motion, and Three.js.

### 2.1 File Tree
```
c:\Users\vsriv\GeoCounterfactual/
├── GeoCounterfactual_Onboarding_Doc.md   # Original onboarding and context notes
├── IMPLEMENTATION_MASTER_SPEC.md          # THIS MASTER SPECIFICATION FILE
├── index.html                             # Web application entry HTML
├── package.json                           # Dependencies (React 18, Vite, Three.js, Lucide, Framer-Motion)
├── postcss.config.js                      # PostCSS config
├── tailwind.config.js                     # Tailwind theme extensions, glows, custom keyframes
├── vite.config.js                         # Vite configuration (port 3000)
├── dist/                                  # Production build bundle
└── src/
    ├── main.jsx                           # React root mount
    ├── App.jsx                            # Main application container & tab router
    ├── index.css                          # Global styles, scanlines, glassmorphism, scrollbars
    ├── data/
    │   └── mockData.js                    # Mock data for regions, agent steps, chatter, methodology
    └── components/
        ├── Header.jsx                     # Top navigation bar, status indicators, tabs
        ├── Globe3D.jsx                    # Interactive Three.js 3D Earth globe with region markers
        ├── SimulatorView.jsx              # Main simulation workspace (Globe + Prompt + Slider + Metrics)
        ├── SatelliteSlider.jsx            # Split Before/After slider with 4 spectral band views
        ├── MetricsPanel.jsx               # Plausibility score gauge, deltas, critic audit checklist
        ├── AgentOrchestrationView.jsx     # 5-node LangGraph flowchart + red critic loop + live terminal
        └── MethodologyView.jsx            # Research methodology, GEE data cards, formulas, benchmarks
```

### 2.2 What the Frontend Simulates Today
- **3D Globe (`Globe3D.jsx`)**: Renders a dark-space 3D globe with interactive coordinates for Anantapur (AP), Marathwada (MH), and Bundelkhand (MP).
- **Intervention Input**: Allows custom natural language typing or selection of presets.
- **Before/After Slider (`SatelliteSlider.jsx`)**: Client-side SVG-based simulation of Optical RGB, NDVI Heatmaps, Soil Moisture Index, and Critic Constraint Masks.
- **Metrics Panel (`MetricsPanel.jsx`)**: Displays plausibility score (94%), NDVI delta (+0.18), soil moisture delta (+14%), and runoff retention (+28%).
- **Multi-Agent Flowchart (`AgentOrchestrationView.jsx`)**: Visualizes data packet flow across the 5 nodes, animates the red feedback rejection loop from Node 5 back to Node 4, and streams step-by-step agent chatter in a mock terminal.

---

## 3. Target System Architecture (LangGraph Multi-Agent Engine)

The core backend will be developed in **Python** using **LangGraph** to model a cyclic state machine.

```
                  ┌────────────────────────────────────────────────────────┐
                  │                      User Request                      │
                  │  (Sentinel-2 GeoTIFF / BBox + Text: "Build 3 check-dams")│
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │   Node 1: Input Handler │
                                 │  - Parses NL intervention
                                 │  - Pulls Sentinel-2 & DEM
                                 └────────────┬────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │ Node 2: Intervention-   │
                                 │         Planner         │
                                 │  - Locates stream beds  │
                                 │  - Paints change mask   │
                                 └────────────┬────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │ Node 3: Eco-Hydrological│
                                 │         Dynamics        │
                                 │  - Infiltration buffer  │
                                 │  - 5-yr growth envelope │
                                 └────────────┬────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                        ┌───────►│ Node 4: Generator       │◄──────────────┐
                        │        │  - ControlNet Diffusion │               │
                        │        │  - Synthesizes future   │               │
                        │        └────────────┬────────────┘               │
                        │                     │                            │
                        │                     ▼                            │
                        │        ┌─────────────────────────┐               │
                        │        │ Node 5: Physical-       │               │
                        │        │         Plausibility    │               │
                        │        │         Critic          │               │
                        │        │  - Checks slope/DEM     │               │
                        │        │  - Checks NDVI limits   │               │
                        │        └────────────┬────────────┘               │
                        │                     │                            │
                        │          [Plausibility Check]                    │
                        │                     │                            │
                        │           Violations Detected?                   │
                        │             (Iterations < 3)                     │
                        │            /                \                    │
                        │          YES                 NO                  │
                        │          /                    \                  │
                        │         ▼                      ▼                 │
                        │   [Rejection Mask]       [Approved Scene]        │
                        └─ Feedback Loop ───────────► Final Output ────────┘
```

### 3.1 LangGraph Global State Schema
```python
from typing import TypedDict, List, Dict, Optional, Any
import numpy as np

class GeoCounterfactualState(TypedDict):
    # Input metadata
    region_id: str
    bbox: List[float]               # [min_lon, min_lat, max_lon, max_lat]
    intervention_text: str          # Plain-language instruction
    intervention_year: int          # Target horizon (e.g., +5 years)
    
    # Ingested geospatial rasters (numpy arrays / georeferenced paths)
    baseline_optical_rgb: Any       # Sentinel-2 B4, B3, B2 (H, W, 3)
    baseline_nir: Any               # Sentinel-2 B8 (H, W)
    baseline_swir: Any              # Sentinel-2 B11 (H, W)
    baseline_ndvi: Any              # Computed baseline NDVI
    dem_elevation: Any              # Copernicus 30m DEM elevation
    dem_slope: Any                  # Computed slope raster in degrees
    geotransform: Any               # Affine transform for GeoTIFF export
    crs: str                        # e.g., "EPSG:4326" or UTM
    
    # Agent Artifacts
    spatial_change_mask: Any        # Binary/weighted mask of intervention footprint
    target_stream_coords: List[Dict]# Identified check-dam / bunding coordinates
    dynamics_guidance: Dict[str, Any]# Infiltration radius, NDVI growth ceilings
    controlnet_conditioning_map: Any# Multi-channel guidance tensor for diffusion
    
    # Generative Output
    candidate_future_rgb: Any       # Synthesized future satellite image
    candidate_future_ndvi: Any      # Inferred / synthesized NDVI layer
    
    # Critic & Feedback Loop State
    iteration_count: int            # Counter to prevent infinite loops (max: 3)
    plausibility_score: float       # 0.0 to 100.0%
    violations: List[str]           # Descriptions of rule violations
    critic_feedback_mask: Any       # Spatial mask indicating rejected pixels
    is_approved: bool               # Final decision flag
    execution_logs: List[Dict[str, str]] # Streaming logs for frontend terminal
```

### 3.2 The 5 Agents: Detailed Specifications

#### Node 1: Input Handler
* **Input:** Raw user prompt + region coordinates.
* **Functionality:**
  - Invokes Google Earth Engine Python API (`ee`) to query Sentinel-2 Level-2A surface reflectance data for the region.
  - Pulls cloud-free composite (<5% cloud cover) for the pre-intervention date.
  - Queries Copernicus 30m Global DEM (`COPERNICUS/DEM/GLO30`) to compute elevation and slope matrices.
  - Calculates baseline NDVI: $\text{NDVI} = \frac{\text{B8} - \text{B4}}{\text{B8} + \text{B4}}$.
  - Appends initialization message to `execution_logs`.
* **Output:** Updates `baseline_optical_rgb`, `baseline_nir`, `baseline_ndvi`, `dem_slope`, and `dem_elevation`.

#### Node 2: Intervention-Planner
* **Input:** `intervention_text`, `dem_slope`, `dem_elevation`, `baseline_ndvi`.
* **Functionality:**
  - LLM-powered spatial reasoning agent (prompted with domain knowledge of watershed engineering).
  - Identifies natural drainage pathways using simple flow accumulation / terrain depressions.
  - Translates text intent (e.g., *"Build 3 check-dams along central stream"*) into spatial coordinates along stream reaches with slopes $< 5^\circ$.
  - Generates a `spatial_change_mask` indicating where earthworks, water bodies, and riparian buffers will emerge.
* **Output:** Updates `spatial_change_mask` and `target_stream_coords`.

#### Node 3: Eco-Hydrological Dynamics
* **Input:** `spatial_change_mask`, `baseline_ndvi`, `intervention_year`.
* **Functionality:**
  - Domain physics rules engine.
  - Encodes multi-year empirical growth curves for semi-arid agro-climatic zones.
  - Defines the maximum permissible vegetation growth boundary (e.g., an annual $\Delta\text{NDVI}$ cap of $+0.35$ max; vegetation can only spread radially within $200\text{m}$ of surface water check-dam recharge plumes).
  - Produces the conditioning tensor for the generator.
* **Output:** Updates `dynamics_guidance` and pre-computes `controlnet_conditioning_map`.

#### Node 4: Generator (Diffusion Core)
* **Input:** `baseline_optical_rgb`, `controlnet_conditioning_map`, and optional `critic_feedback_mask` (if looping back from rejection).
* **Functionality:**
  - Fine-tuned Latent Diffusion backbone (e.g., Stable Diffusion 1.5/2.1 or SD-Inpainting) with ControlNet conditioning on elevation, edge layout, and the intervention mask.
  - If `critic_feedback_mask` is present, zeroes out or penalizes the rejected spatial regions and adjusts conditioning prompt weighting.
  - Synthesizes the candidate future satellite scene (`candidate_future_rgb`).
* **Output:** Updates `candidate_future_rgb` and increments `iteration_count`.

#### Node 5: Physical-Plausibility Critic (The Gatekeeper)
* **Input:** `candidate_future_rgb`, `dem_slope`, `baseline_ndvi`, `dynamics_guidance`.
* **Functionality:**
  - Runs algorithmic physics checks (see Section 6 for full rule specifications).
  - Computes violation penalty index.
  - If violations exist and `iteration_count` $< 3$: marks `is_approved = False`, creates `critic_feedback_mask`, logs rejection reason.
  - If checks pass or `iteration_count` $\ge 3$: marks `is_approved = True`, calculates final `plausibility_score`.
* **Output:** Updates `is_approved`, `plausibility_score`, `violations`, and `critic_feedback_mask`.

### 3.3 Cyclic Conditional Edge (LangGraph)
```python
def check_critic_decision(state: GeoCounterfactualState) -> str:
    if state["is_approved"]:
        return "approved_output"
    elif state["iteration_count"] >= 3:
        # Fallback safeguard after max retries
        return "approved_output"
    else:
        # Loop back to generator with feedback mask
        return "generator_node"
```

---

## 4. Earth Observation & Data Ingestion Pipeline (GEE + Sentinel-2)

### 4.1 Datasets
1. **Sentinel-2 MSI (Level-2A, Surface Reflectance)**:
   - GEE Collection: `COPERNICUS/S2_SR_HARMONIZED`
   - Spatial Resolution: 10m (B2, B3, B4, B8), 20m (B11, B12).
   - Cloud Masking: Use SCL (Scene Classification Layer) or QA60 band to filter out clouds, cirrus, and cloud shadows.
2. **Copernicus DEM (30m Global Elevation)**:
   - GEE Asset: `COPERNICUS/DEM/GLO30`
   - Used to derive elevation profile and compute terrain slope via GDAL / `ee.Terrain.slope()`.

### 4.2 Target Pilot Regions (Proof-of-Concept)
To prevent out-of-distribution errors, the initial prototype is scoped to specific semi-arid watershed regions in India:
- **Region A (Primary):** *Anantapur Watershed Zone, Andhra Pradesh* (Lat: `14.6819°N`, Lon: `77.6006°E`)
  - Rain-shadow dry zone, low baseline NDVI (~0.22), severe groundwater depletion, frequent check-dam interventions.
- **Region B:** *Marathwada Basin, Maharashtra* (Lat: `19.8762°N`, Lon: `75.3433°E`)
  - Deccan trap basaltic soil, extreme drought cycles, farm-pond initiatives.

### 4.3 Python Ingestion Snippet (`data_engine/gee_loader.py`)
```python
import ee
import numpy as np
import rasterio

def initialize_gee(project_id: str):
    ee.Initialize(project=project_id)

def fetch_sentinel2_composite(bbox: list, start_date: str, end_date: str):
    """
    Pulls cloud-masked Sentinel-2 Surface Reflectance composite.
    bbox: [min_lon, min_lat, max_lon, max_lat]
    """
    roi = ee.Geometry.BBox(*bbox)
    
    def mask_s2_clouds(image):
        qa = image.select('QA60')
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
            qa.bitwiseAnd(cirrus_bit_mask).eq(0)
        )
        return image.updateMask(mask).divide(10000)

    dataset = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
        .map(mask_s2_clouds)
        .median()
        .clip(roi)
    )
    
    dem = ee.Image('COPERNICUS/DEM/GLO30').select('DEM').clip(roi)
    slope = ee.Terrain.slope(dem)
    
    return dataset, dem, slope
```

---

## 5. Generative Core (Diffusion + ControlNet Conditioning)

### 5.1 Strategic Model Selection
*As decided in the onboarding plan:*
- **Do NOT train a diffusion model from scratch.** That would consume weeks without adding novelty.
- Use a **pretrained Latent Diffusion model** (e.g., `runwayml/stable-diffusion-v1-5` or `stabilityai/stable-diffusion-2-inpainting`) combined with **ControlNet** conditioning.
- **Conditioning Channels:**
  1. *Source RGB Satellite Frame* (structural anchor).
  2. *Elevation / Slope Map* from Copernicus DEM (topographic constraint).
  3. *Intervention Spatial Mask* from Planner Agent (boundary constraint).
- **Novelty Locus:** The novelty lies in the *agent orchestration and closed-loop critic*, not the raw diffusion weights.

### 5.2 ControlNet Inpainting / Guidance Architecture
- Unchanged pixels (farmland, existing roads, settlements, mountain ridges) outside the intervention mask must remain structurally identical ($\text{SSIM} \ge 0.92$).
- The intervention zone (the stream channel and surrounding $200\text{m}$ buffer) is synthesized using conditioning tokens indicating *"check-dam reservoir, accumulated seasonal water body, riparian green belt"*.

---

## 6. The Physical-Plausibility Critic (Rules & Physics Engine)

The Critic is the **headline contribution** of this research. It evaluates the generated image before it is approved.

### 6.1 Algorithmic Verification Rules
1. **Rule 1: Gravity & Slope Invariance (No Water on Slopes)**
   - Extract water candidate pixels from `candidate_future_rgb` using NDWI (or green/blue reflectance ratios).
   - Overlay on `dem_slope`.
   - **Constraint:** Surface water bodies $\ge 500\text{m}^2$ cannot exist on slopes $> 2.5^\circ$ unless an upstream check-dam wall is physically registered.
   - *Violation Action:* Reject image; mask out invalid slope pixels into `critic_feedback_mask`.

2. **Rule 2: Biological NDVI Growth Rate Ceilings**
   - Compute candidate future NDVI: $\text{NDVI}_{\text{future}}$.
   - **Constraint:** $\Delta\text{NDVI} = \text{NDVI}_{\text{future}} - \text{NDVI}_{\text{baseline}} \le (0.35 \times \text{years})$.
   - *Reason:* A barren plot cannot become an Amazonian dense canopy in 3 years in a semi-arid zone without irrigation.

3. **Rule 3: Spectral Signature Consistency**
   - Natural vegetation must exhibit the characteristic "red edge" jump between Red (Band 4) and NIR (Band 8).
   - If candidate pixels show high green reflectance without NIR elevation, flag as "synthetic paint / hallucination".

4. **Rule 4: Unchanged-Area Spatial Conservation**
   - Outside the `spatial_change_mask`, compute Structural Similarity (SSIM):
   - **Constraint:** $\text{SSIM}(\text{baseline}_{\text{outside}}, \text{future}_{\text{outside}}) \ge 0.90$.

### 6.2 Critic Code Blueprint (`critic/physics_critic.py`)
```python
import numpy as np
from skimage.metrics import structural_similarity as ssim

class PhysicalPlausibilityCritic:
    def __init__(self, max_slope_for_water=2.5, max_annual_ndvi_delta=0.35):
        self.max_slope = max_slope_for_water
        self.max_ndvi_rate = max_annual_ndvi_delta

    def evaluate(self, candidate_rgb, baseline_rgb, dem_slope, change_mask, years=5):
        violations = []
        feedback_mask = np.zeros(candidate_rgb.shape[:2], dtype=bool)
        
        # 1. Slope Check on Water
        # Estimate water mask via high green/blue vs red
        water_mask = (candidate_rgb[:, :, 2] > candidate_rgb[:, :, 0]) & (candidate_rgb[:, :, 1] > 0.2)
        steep_water = water_mask & (dem_slope > self.max_slope)
        
        if np.sum(steep_water) > 20:  # more than 20 pixels violated
            violations.append(f"Gravity violation: Water detected on slope > {self.max_slope}°")
            feedback_mask |= steep_water

        # 2. Outside SSIM Check
        outside_mask = ~change_mask
        base_gray = np.mean(baseline_rgb, axis=-1)
        future_gray = np.mean(candidate_rgb, axis=-1)
        outside_ssim = ssim(base_gray[outside_mask], future_gray[outside_mask], data_range=1.0)
        
        if outside_ssim < 0.88:
            violations.append(f"Drift violation: Background terrain corrupted (SSIM: {outside_ssim:.2f} < 0.88)")

        is_approved = len(violations) == 0
        plausibility_score = max(50.0, 100.0 - (len(violations) * 20.0))
        
        return {
            "is_approved": is_approved,
            "score": plausibility_score,
            "violations": violations,
            "feedback_mask": feedback_mask
        }
```

---

## 7. API Contract & Frontend-Backend Integration

To connect our existing React frontend to the new Python backend, implement a **FastAPI** server running at `http://localhost:8000`.

### 7.1 Key Endpoints

#### `POST /api/simulate`
* **Request:**
  ```json
  {
    "region_id": "anantapur",
    "intervention_text": "Build 3 check-dams along central dry stream bed",
    "target_years": 5,
    "bbox": [77.58, 14.66, 77.62, 14.70]
  }
  ```
* **Response:**
  ```json
  {
    "status": "success",
    "execution_time_sec": 12.4,
    "plausibility_score": 94,
    "critic_iterations": 2,
    "metrics_delta": {
      "ndvi_delta": "+0.18",
      "soil_moisture_delta": "+14%",
      "water_retention_delta": "+28%"
    },
    "imagery": {
      "before_optical_url": "/static/anantapur_before_rgb.png",
      "after_optical_url": "/static/anantapur_after_rgb.png",
      "ndvi_heatmap_url": "/static/anantapur_ndvi_delta.png",
      "moisture_heatmap_url": "/static/anantapur_moisture.png",
      "critic_mask_url": "/static/anantapur_critic_mask.png"
    },
    "execution_logs": [
      { "step": 1, "agent": "Input Handler", "type": "info", "text": "Ingested Sentinel-2 L2A composite." },
      { "step": 2, "agent": "Physical-Plausibility Critic", "type": "reject", "text": "Iteration 1 rejected: Water on 14° slope." },
      { "step": 3, "agent": "Generator (Diffusion)", "type": "info", "text": "Re-synthesizing with corrected elevation mask." },
      { "step": 4, "agent": "Physical-Plausibility Critic", "type": "success", "text": "Passed with 94% Plausibility Score." }
    ]
  }
  ```

#### `GET /api/stream-agent-logs` (WebSocket or SSE)
Streams real-time agent thoughts directly to the live terminal in `AgentOrchestrationView.jsx`.

---

## 8. Open Decisions & Technical Trade-Offs

Before executing code in Claude Code, finalize these 5 choices:

| Decision Area | Status | Recommended Path | Alternatives |
|---|---|---|---|
| **Intervention Type** | Finalized | **Watershed / Check-Dams & Groundwater Recharge** (strongest hydrological & slope constraints for the Critic). | Afforestation alone (weaker physical slope constraints). |
| **Target Pilot Region** | Finalized | **Anantapur District, Andhra Pradesh** (semi-arid, high availability of documented historical check-dams). | Marathwada, Maharashtra. |
| **LLM for Reasoning Agents** | Open | **Claude 3.5 Sonnet / OpenAI GPT-4o API** for Planner & Input agents (fast, reliable spatial reasoning). | Local Ollama Llama-3.1-8B (requires local GPU memory allocation). |
| **Generative Diffusion Model** | Open | **Stable Diffusion v1.5 Inpainting + ControlNet-Depth/Canny** (lightweight, runs easily on single RTX 3080/4090 or Google Colab). | SDXL Inpainting (heavier VRAM requirement). |
| **Google Earth Engine Auth** | Open | **GEE Service Account Key** with JSON credentials, or local `earthengine authenticate` token. | Pre-downloaded static Sentinel-2 GeoTIFF tiles for offline development. |

---

## 9. Step-by-Step Implementation Roadmap for Claude Code

When you open this repository with Claude Code in VS Code, execute the implementation in **5 sequential phases**:

### Phase 1: Python Environment & Data Ingestion Engine
1. Create a `backend/` directory in the repository root.
2. Setup `backend/requirements.txt`:
   ```text
   fastapi==0.115.0
   uvicorn==0.30.0
   langgraph==0.2.20
   langchain-core==0.3.0
   earthengine-api==0.1.415
   rasterio==1.3.10
   geopandas==1.0.1
   numpy==1.26.4
   scikit-image==0.24.0
   torch==2.4.0
   diffusers==0.30.0
   transformers==4.44.0
   pydantic==2.8.2
   ```
3. Implement `backend/data_engine/gee_loader.py` to authenticate and download Sentinel-2 RGB + NIR + SWIR bands and Copernicus 30m DEM for the Anantapur test coordinates.
4. Provide an offline fallback mode with pre-cached `.tif` tiles so development doesn't stall if GEE credentials are being configured.

### Phase 2: LangGraph Multi-Agent Workflow
1. Implement `backend/agents/state.py` defining `GeoCounterfactualState`.
2. Implement individual agent nodes in `backend/agents/`:
   - `input_handler.py`: Parses prompt & loads rasters.
   - `planner.py`: Identifies stream channels and draws `spatial_change_mask`.
   - `dynamics.py`: Computes 5-year growth boundaries.
3. Build the core graph in `backend/agents/workflow.py` wiring nodes with `StateGraph`.

### Phase 3: Physical-Plausibility Critic Implementation
1. Implement `backend/critic/physics_critic.py` with:
   - Elevation & slope gradient evaluation.
   - Vegetation rate cap calculator.
   - SSIM invariance evaluator.
2. Wire the cyclic conditional edge in `workflow.py` connecting the Critic back to the Generator when violations are detected.

### Phase 4: Generator Diffusion Integration
1. Implement `backend/generator/diffusion_generator.py` using `diffusers.StableDiffusionControlNetInpaintPipeline`.
2. Map the base image, spatial change mask, and DEM slope into the conditioning tensor.
3. Handle feedback loop re-generation when `critic_feedback_mask` is active.

### Phase 5: FastAPI Bridge & React UI Integration
1. Create `backend/server.py` exposing `/api/simulate` and `/api/health`.
2. Update the React frontend `src/components/SimulatorView.jsx` to fetch real simulation data from `http://localhost:8000/api/simulate` when the user clicks **"Simulate Counterfactual"**, while seamlessly falling back to mock data if the backend server is offline.
3. Verify end-to-end execution: User types intervention $\to$ GEE pulls imagery $\to$ LangGraph coordinates agents $\to$ Critic validates physics $\to$ Frontend slider displays live generated satellite scene!

---

*End of Master Implementation Specification. You are ready to launch Claude Code in VS Code and begin Phase 1.*
