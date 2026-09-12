"""Node 2: Intervention-Planner.

Two-stage design, deliberately split:

  Stage 1 (Gemini)  -- natural language  ->  a small typed intent object.
  Stage 2 (numpy)   -- intent + DEM      ->  actual pixels.

The spec calls this an "LLM-powered spatial reasoning agent", but language
models do not produce reliable raster coordinates: asked for a check-dam
location they will happily emit a plausible-looking row/col that sits on a
hilltop. So the LLM is confined to what it is good at -- reading intent out of
a sentence -- and every pixel is chosen by deterministic terrain analysis in
terrain.py.

Three properties fall out of that split:
  * a hallucinated coordinate cannot reach the generator;
  * the critic ablation is reproducible, because geometry is deterministic;
  * with no API key the node still runs, via keyword_fallback().
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field, ValidationError

from backend.agents import terrain
from backend.agents.logs import AGENT_PLANNER, make_logs
from backend.agents.state import GeoCounterfactualState
from backend.config import settings

logger = logging.getLogger(__name__)

STRUCTURE_TYPES = ("check_dam", "farm_pond", "contour_bund",
                   "percolation_pit", "afforestation")
PLACEMENT_STRATEGIES = ("stream_channel", "contour", "upper_catchment",
                        "field_boundary")


class InterventionPlan(BaseModel):
    """The only thing the LLM is trusted to produce."""

    structure_type: str = Field(description=f"One of {STRUCTURE_TYPES}")
    count: int = Field(ge=1, le=20, description="How many structures")
    placement_strategy: str = Field(description=f"One of {PLACEMENT_STRATEGIES}")
    buffer_radius_m: int = Field(ge=50, le=500, default=200,
                                 description="Riparian/recharge buffer radius")
    impound_height_m: float = Field(ge=0.5, le=8.0, default=3.0,
                                    description="Structure crest height")
    reasoning: str = Field(default="", description="One sentence of rationale")

    def normalized(self) -> "InterventionPlan":
        if self.structure_type not in STRUCTURE_TYPES:
            self.structure_type = "check_dam"
        if self.placement_strategy not in PLACEMENT_STRATEGIES:
            self.placement_strategy = "stream_channel"
        return self


SYSTEM_PROMPT = """You are a watershed engineering analyst for semi-arid India \
(Deccan plateau, 500-900 mm annual rainfall, MGNREGA-style interventions).

Read the user's proposed land intervention and extract its structured intent.
Do NOT invent coordinates, pixel positions, or latitudes - siting is handled
downstream by terrain analysis. Report only what the sentence implies.

Guidance:
- "check-dam", "stop-dam", "nala bund", "series of dams" -> check_dam, stream_channel
- "farm pond", "percolation tank", "khet talai"          -> farm_pond, contour
- "contour bund", "trench", "staggered trench"           -> contour_bund, contour
- "percolation pit", "recharge pit", "soak pit"          -> percolation_pit, field_boundary
- "afforest", "plantation", "tree cover", "native trees" -> afforestation, upper_catchment

If a count is not stated, infer a sensible one (a "series" implies 3-5).
Masonry/stop-dams impound higher (3-5 m) than earthen nala bunds (1.5-2.5 m).
"""


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model response."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = fenced.group(1) if fenced else None
    if raw is None:
        brace = re.search(r"\{.*\}", text, re.S)
        raw = brace.group(0) if brace else None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def parse_intent_with_gemini(text: str, years: int,
                             attempts: int = 2) -> tuple:
    """Stage 1. Returns (plan_or_None, diagnostic).

    The diagnostic is carried into execution_logs. Silently collapsing to the
    keyword heuristic would hide a transient 429/503 behind what looks like a
    deliberate offline run, and the planner would quietly get dumber without
    anyone noticing.
    """
    api_key = settings.gemini_api_key
    if not api_key:
        return None, "GEMINI_API_KEY not set"

    from langchain_google_genai import ChatGoogleGenerativeAI

    prompt = f"{SYSTEM_PROMPT}\n\nIntervention: {text}\nHorizon: {years} years."
    last_error = "unknown"

    for attempt in range(1, attempts + 1):
        llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=api_key,
            temperature=0.0,   # deterministic: the ablation must be repeatable
        )

        # Preferred path: schema-constrained structured output.
        try:
            plan = llm.with_structured_output(InterventionPlan).invoke(prompt)
            if isinstance(plan, InterventionPlan):
                return plan.normalized(), None
            if isinstance(plan, dict):
                return InterventionPlan(**plan).normalized(), None
            last_error = f"unexpected structured-output type {type(plan).__name__}"
        except (ValidationError, Exception) as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            logger.warning("Gemini structured parse failed on attempt %d (%s)",
                           attempt, last_error)

        # Fallback path: some model/SDK pairs reject the schema; ask for raw
        # JSON before giving up on the LLM entirely.
        try:
            schema = ('{"structure_type": str, "count": int, '
                      '"placement_strategy": str, "buffer_radius_m": int, '
                      '"impound_height_m": float, "reasoning": str}')
            reply = llm.invoke(
                f"{prompt}\nRespond with ONLY a JSON object of this shape: {schema}")
            payload = _extract_json(getattr(reply, "content", "") or "")
            if payload:
                return InterventionPlan(**payload).normalized(), None
            last_error = "model returned no parseable JSON"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            logger.warning("Gemini raw-JSON parse failed on attempt %d (%s)",
                           attempt, last_error)

    return None, last_error


def keyword_fallback(text: str) -> InterventionPlan:
    """Stage 1 without an LLM. Deterministic, offline, always available."""
    lowered = text.lower()

    if any(w in lowered for w in ("afforest", "plantation", "tree", "canopy",
                                  "acacia", "neem", "forest")):
        structure, strategy, height = "afforestation", "upper_catchment", 0.5
    elif any(w in lowered for w in ("farm pond", "pond", "percolation tank",
                                    "tank")):
        structure, strategy, height = "farm_pond", "contour", 2.5
    elif any(w in lowered for w in ("contour bund", "bunding", "trench")):
        structure, strategy, height = "contour_bund", "contour", 1.5
    elif any(w in lowered for w in ("percolation pit", "recharge pit",
                                    "soak pit")):
        structure, strategy, height = "percolation_pit", "field_boundary", 1.0
    else:
        structure, strategy, height = "check_dam", "stream_channel", 3.0

    numbers = [int(n) for n in re.findall(r"\b(\d{1,2})\b", lowered)]
    count = numbers[0] if numbers else (4 if "series" in lowered else 3)

    return InterventionPlan(
        structure_type=structure,
        count=max(1, min(count, 20)),
        placement_strategy=strategy,
        buffer_radius_m=200,
        impound_height_m=height,
        reasoning="Keyword heuristic (no LLM).",
    ).normalized()


def _pixel_to_lonlat(transform, row: int, col: int) -> tuple:
    """Cell centre in the scene CRS (metres for our UTM grids)."""
    x, y = transform * (col + 0.5, row + 0.5)
    return float(x), float(y)


def build_change_mask(
    plan: InterventionPlan,
    elevation: np.ndarray,
    slope: np.ndarray,
    cell_size: float = 10.0,
) -> tuple:
    """Stage 2. Intent + DEM -> weighted change mask and sited coordinates.

    Mask weights: 1.0 impounded water, 0.5 riparian/recharge buffer, 0 unchanged.
    """
    products = terrain.analyse(elevation, cell_size=cell_size)
    streams = products["streams"]
    accumulation = products["accumulation"]
    filled = products["filled"]

    if plan.placement_strategy == "upper_catchment":
        # Afforestation targets degraded upper slopes, not channels.
        sites: List[Dict[str, float]] = []
        upper = (accumulation < 200) & (slope > 3.0) & (slope < 25.0)
        core = np.zeros_like(streams, dtype=bool)
        buffer = upper
    else:
        sites = terrain.select_dam_sites(
            streams=streams,
            accumulation=accumulation,
            slope=slope,
            elevation=elevation,
            count=plan.count,
            cell_size=cell_size,
        )
        core = terrain.impoundment_mask(
            sites, filled, accumulation,
            impound_height_m=plan.impound_height_m,
            cell_size=cell_size,
        )
        buffer = terrain.buffer_mask(core, plan.buffer_radius_m, cell_size)

    mask = np.zeros(elevation.shape, dtype=np.float32)
    mask[buffer] = 0.5
    mask[core] = 1.0

    coords = []
    for s in sites:
        coords.append(dict(s))
    return mask, coords, products


def planner_node(state: GeoCounterfactualState) -> dict:
    text = state.get("intervention_text", "")
    years = int(state.get("intervention_year", 5))
    elevation = state["dem_elevation"]
    slope = state["dem_slope"]

    plan, llm_error = parse_intent_with_gemini(text, years)
    used_llm = plan is not None
    if plan is None:
        plan = keyword_fallback(text)

    mask, coords, products = build_change_mask(plan, elevation, slope)

    water_px = int(np.sum(mask >= 1.0))
    buffer_px = int(np.sum((mask > 0) & (mask < 1.0)))
    stream_px = int(np.sum(products["streams"]))
    cell_area = settings.target_scale_m ** 2

    source = (f"Gemini ({settings.gemini_model})" if used_llm
              else "keyword heuristic (no LLM)")
    entries = [
        ("info", f"Parsed intent via {source}: {plan.count}x "
                 f"{plan.structure_type.replace('_', ' ')}, "
                 f"{plan.placement_strategy.replace('_', ' ')}, "
                 f"{plan.buffer_radius_m} m buffer."),
        ("info", f"D8 flow routing: {stream_px} stream cells "
                 f"({stream_px * cell_area / 10_000:.1f} ha channel network)."),
    ]
    if coords:
        best = coords[0]
        entries.append(
            ("info", f"Sited {len(coords)} structure(s) on the main stem; "
                     f"largest drains {best['contributing_area_ha']:.0f} ha at "
                     f"{best['slope_deg']:.1f} deg slope."))
    else:
        entries.append(
            ("warn", "No channel sites met the slope constraint; "
                     "falling back to catchment-wide treatment."))
    entries.append(
        ("success", f"Change mask painted: {water_px} core px "
                    f"({water_px * cell_area / 10_000:.1f} ha), "
                    f"{buffer_px} buffer px."))
    if not used_llm:
        entries.insert(0, ("warn", f"Gemini unavailable ({llm_error}); "
                                   f"falling back to deterministic keyword "
                                   f"parsing."))

    return {
        "intervention_plan": plan.model_dump(),
        "spatial_change_mask": mask,
        "target_stream_coords": coords,
        "execution_logs": make_logs(state, AGENT_PLANNER, entries),
    }
