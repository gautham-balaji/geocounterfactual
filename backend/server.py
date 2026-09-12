"""FastAPI bridge between the LangGraph pipeline and the React frontend.

Two execution paths, deliberately:

  POST /api/simulate          synchronous, returns the whole payload.
                              Matches the contract in spec 7.1 exactly.
  POST /api/simulate/async    returns a job_id immediately
  GET  /api/stream/{job_id}   SSE; each agent's logs arrive as they happen

The synchronous endpoint alone is not enough once a real generator is in
play. On the Colab T4 a three-iteration critic loop runs for minutes, and on
CPU for tens of minutes -- far past any browser's patience. More importantly
the whole point of the frontend terminal is watching the Critic reject and
the Generator retry; a single response at the end shows the transcript after
the drama is over. The SSE path streams node-by-node so the loop is visible
as it happens.

Run:  uvicorn backend.server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import shutil
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.config import REGIONS, settings
from backend.data_engine import indices, raster_io

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="GeoCounterfactual API", version="1.0.0")

# The Vite dev server proxies /api and /static, so same-origin covers the
# normal path; CORS is here for direct access (curl, a second origin, or the
# frontend served from somewhere other than the proxy).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                   "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings.ensure_dirs()
app.mount("/static", StaticFiles(directory=str(settings.static_dir)),
          name="static")


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class SimulateRequest(BaseModel):
    region_id: str = "anantapur"
    intervention_text: str
    target_years: int = Field(default=5, ge=1, le=20)
    bbox: Optional[List[float]] = None


class HealthResponse(BaseModel):
    status: str
    gee: str
    generator_backend: str
    planner_model: str
    regions: List[str]


# --------------------------------------------------------------------------
# Job registry for the streaming path
# --------------------------------------------------------------------------

_JOBS: Dict[str, Dict[str, Any]] = {}


MAX_TRACKED_JOBS = 24
MAX_RUN_DIRS = 12


def _prune_jobs() -> None:
    """Bound the registry. Without this every run leaks its request dict."""
    if len(_JOBS) <= MAX_TRACKED_JOBS:
        return
    for job_id in sorted(_JOBS, key=lambda k: _JOBS[k]["created"])[
            :len(_JOBS) - MAX_TRACKED_JOBS]:
        _JOBS.pop(job_id, None)


def _prune_runs() -> None:
    """Keep the newest N run directories; each is ~2.5 MB of PNGs."""
    runs_dir = settings.static_dir / "runs"
    if not runs_dir.is_dir():
        return
    dirs = sorted((d for d in runs_dir.iterdir() if d.is_dir()),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    for stale in dirs[MAX_RUN_DIRS:]:
        shutil.rmtree(stale, ignore_errors=True)


def _new_job(payload: SimulateRequest) -> str:
    _prune_jobs()
    job_id = uuid.uuid4().hex[:12]
    _JOBS[job_id] = {"request": payload, "created": time.time(),
                     "status": "pending", "result": None, "error": None}
    return job_id


# --------------------------------------------------------------------------
# Rendering + response assembly
# --------------------------------------------------------------------------

def _render_outputs(state: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    """Write the PNGs the slider needs and return their URLs.

    SatelliteSlider shows four band views with a before/after split, so eight
    images plus the critic mask. The flat keys from spec 7.1 are kept as
    aliases so the documented contract still resolves.
    """
    out_dir = settings.static_dir / "runs" / run_id
    base_rgb = state["baseline_optical_rgb"]
    future_rgb = state.get("candidate_future_rgb")
    if future_rgb is None:
        future_rgb = base_rgb

    base_ndvi = state["baseline_ndvi"]
    future_ndvi = state.get("candidate_future_ndvi")
    if future_ndvi is None:
        future_ndvi = base_ndvi

    base_ndmi = state.get("baseline_ndmi")
    if base_ndmi is None:
        base_ndmi = np.zeros_like(base_ndvi)
    # Moisture proxy after the intervention: the recharge plume lifts NDMI
    # inside its influence, bounded by the dynamics envelope.
    recharge = (state.get("dynamics_guidance") or {}).get("recharge_field")
    future_ndmi = (base_ndmi + 0.25 * np.asarray(recharge, dtype=np.float32)
                   if recharge is not None else base_ndmi)

    feedback = state.get("critic_feedback_mask")
    change = state.get("spatial_change_mask")

    raster_io.render_rgb(base_rgb, out_dir / "before_optical.png")
    raster_io.render_rgb(future_rgb, out_dir / "after_optical.png")
    raster_io.render_colormap(base_ndvi, out_dir / "before_ndvi.png",
                              cmap="RdYlGn", vmin=-0.2, vmax=0.8)
    raster_io.render_colormap(future_ndvi, out_dir / "after_ndvi.png",
                              cmap="RdYlGn", vmin=-0.2, vmax=0.8)
    raster_io.render_colormap(base_ndmi, out_dir / "before_moisture.png",
                              cmap="YlGnBu", vmin=-0.4, vmax=0.4)
    raster_io.render_colormap(future_ndmi, out_dir / "after_moisture.png",
                              cmap="YlGnBu", vmin=-0.4, vmax=0.4)
    raster_io.render_mask_overlay(
        base_rgb, np.asarray(change) > 0 if change is not None
        else np.zeros(base_rgb.shape[:2], bool),
        out_dir / "before_critic.png", colour=(0.2, 0.9, 1.0), alpha=0.45)
    raster_io.render_mask_overlay(
        future_rgb,
        np.asarray(feedback, dtype=bool) if feedback is not None
        else np.zeros(future_rgb.shape[:2], bool),
        out_dir / "after_critic.png", colour=(1.0, 0.15, 0.2), alpha=0.65)

    # --- transparent RGBA overlays for the xAI layer --------------------
    # Distinct from the four band views above: these have alpha 0 outside
    # the region they describe, so the frontend can stack them over the
    # optical scene and fade them, instead of swapping to a separate image.
    change_bool = (np.asarray(change) > 0 if change is not None
                   else np.zeros(base_rgb.shape[:2], bool))
    water_bool = (np.asarray(change) >= 1.0 if change is not None
                  else np.zeros(base_rgb.shape[:2], bool))

    # The FIRST rejection, not the last. On an approved run the final
    # feedback mask is all zeros, which rendered an empty grey frame for the
    # one artifact that demonstrates the critic actually did something.
    history = state.get("rejection_history") or []
    if history:
        first_reject = np.asarray(history[0]["mask"], dtype=bool)
    else:
        first_reject = np.zeros(base_rgb.shape[:2], dtype=bool)

    raster_io.render_rgba_mask(change_bool, out_dir / "ov_footprint.png",
                               colour=(0.13, 0.83, 1.0), alpha=0.85,
                               outline_only=True)
    raster_io.render_rgba_mask(water_bool, out_dir / "ov_impoundment.png",
                               colour=(0.20, 0.55, 1.0), alpha=0.70)
    raster_io.render_rgba_mask(first_reject, out_dir / "ov_rejection.png",
                               colour=(1.0, 0.16, 0.28), alpha=0.75)
    raster_io.render_rgba_diverging(
        np.asarray(future_ndvi) - np.asarray(base_ndvi),
        out_dir / "ov_ndvi_delta.png", threshold=0.05, vmin=-0.4, vmax=0.4)
    slope = state.get("dem_slope")
    raster_io.render_rgba_mask(
        (np.asarray(slope) > settings.max_slope_for_water_deg) if slope is not None
        else np.zeros(base_rgb.shape[:2], bool),
        out_dir / "ov_steep.png", colour=(1.0, 0.62, 0.0), alpha=0.38)

    base_url = f"/static/runs/{run_id}"
    return {
        "overlays": {
            "footprint": f"{base_url}/ov_footprint.png",
            "impoundment": f"{base_url}/ov_impoundment.png",
            "rejection": f"{base_url}/ov_rejection.png",
            "ndvi_delta": f"{base_url}/ov_ndvi_delta.png",
            "steep_terrain": f"{base_url}/ov_steep.png",
        },
        "overlay_stats": {
            "footprint_px": int(change_bool.sum()),
            "impoundment_px": int(water_bool.sum()),
            "rejection_px": int(first_reject.sum()),
            "rejection_iteration": (history[0]["iteration"] if history else None),
            "rejection_violations": (history[0]["violations"] if history else []),
        },
        "optical": {"before": f"{base_url}/before_optical.png",
                    "after": f"{base_url}/after_optical.png"},
        "ndvi": {"before": f"{base_url}/before_ndvi.png",
                 "after": f"{base_url}/after_ndvi.png"},
        "moisture": {"before": f"{base_url}/before_moisture.png",
                     "after": f"{base_url}/after_moisture.png"},
        "critic": {"before": f"{base_url}/before_critic.png",
                   "after": f"{base_url}/after_critic.png"},
        # spec 7.1 flat aliases
        "before_optical_url": f"{base_url}/before_optical.png",
        "after_optical_url": f"{base_url}/after_optical.png",
        "ndvi_heatmap_url": f"{base_url}/after_ndvi.png",
        "moisture_heatmap_url": f"{base_url}/after_moisture.png",
        "critic_mask_url": f"{base_url}/after_critic.png",
    }


def _metrics(state: Dict[str, Any]) -> Dict[str, str]:
    """Deltas measured inside the intervention footprint, not scene-wide.

    A scene-wide mean is dominated by the ~96% of pixels nothing touched and
    would report a near-zero change for a perfectly good intervention.
    """
    change = state.get("spatial_change_mask")
    inside = (np.asarray(change) > 0 if change is not None
              else np.ones(state["baseline_ndvi"].shape, bool))
    if not inside.any():
        inside = np.ones_like(inside)

    base_ndvi = np.asarray(state["baseline_ndvi"])
    fut_ndvi = np.asarray(state.get("candidate_future_ndvi", base_ndvi))
    ndvi_delta = float(np.mean(fut_ndvi[inside] - base_ndvi[inside]))

    guidance = state.get("dynamics_guidance") or {}
    recharge = guidance.get("recharge_field")
    moisture_delta = (float(np.mean(np.asarray(recharge)[inside])) * 25.0
                      if recharge is not None else 0.0)

    cell_area = settings.target_scale_m ** 2
    water_cells = int(np.sum(np.asarray(change) >= 1.0)) if change is not None else 0
    impound_m3 = water_cells * cell_area * 1.5   # ~1.5 m mean effective depth
    influenced = max(1.0, guidance.get("influenced_area_ha", 1.0))
    retention_delta = min(60.0, impound_m3 / (influenced * 100.0))

    return {
        "ndvi_delta": f"{ndvi_delta:+.2f}",
        "soil_moisture_delta": f"{moisture_delta:+.0f}%",
        "water_retention_delta": f"{retention_delta:+.0f}%",
        "impoundment_area_ha": f"{water_cells * cell_area / 10_000:.2f}",
    }


def _build_response(state: Dict[str, Any], run_id: str,
                    elapsed: float) -> Dict[str, Any]:
    logs = state.get("execution_logs") or []
    rejections = [e for e in logs if e.get("type") == "reject"]
    imagery = _render_outputs(state, run_id)
    return {
        "status": "success",
        "run_id": run_id,
        "execution_time_sec": round(elapsed, 1),
        "plausibility_score": round(float(state.get("plausibility_score", 0)), 1),
        "is_approved": bool(state.get("is_approved", False)),
        "critic_iterations": int(state.get("iteration_count", 0)),
        "critic_rejections": len(rejections),
        "violations": state.get("violations") or [],
        "scene_source": state.get("scene_source", "unknown"),
        "generator_backend": settings.generator_backend,
        "intervention_plan": state.get("intervention_plan") or {},
        "target_stream_coords": state.get("target_stream_coords") or [],
        "metrics_delta": _metrics(state),
        "imagery": imagery,
        "overlays": imagery.pop("overlays", {}),
        "overlay_stats": imagery.pop("overlay_stats", {}),
        "rejection_history": [
            {"iteration": h["iteration"], "score": h["score"],
             "violations": h["violations"], "rule_ids": h.get("rule_ids", []),
             "rejected_px": int(np.asarray(h["mask"]).sum())}
            for h in (state.get("rejection_history") or [])
        ],
        "execution_logs": logs,
    }


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    from backend.data_engine import gee_auth
    return HealthResponse(
        status="ok",
        gee="available" if gee_auth.is_available() else "unavailable",
        generator_backend=settings.generator_backend,
        planner_model=settings.gemini_model if settings.gemini_api_key
        else "keyword-fallback",
        regions=sorted(REGIONS),
    )


@app.get("/api/regions")
def list_regions() -> Dict[str, Any]:
    return {"regions": [
        {"id": r.id, "name": r.name, "state": r.state, "bbox": r.bbox,
         "crs": r.crs, "baseline_ndvi": r.baseline_ndvi,
         "climate_zone": r.climate_zone}
        for r in REGIONS.values()]}


@app.post("/api/simulate")
def simulate(req: SimulateRequest) -> Dict[str, Any]:
    """Synchronous run -- the spec 7.1 contract.

    Fine with the stub backend; with a real generator prefer the async +
    SSE pair, which will not sit on an open socket for minutes.
    """
    from backend.agents.workflow import run_simulation

    if req.region_id not in REGIONS:
        raise HTTPException(404, f"Unknown region '{req.region_id}'")

    run_id = uuid.uuid4().hex[:12]
    started = time.time()
    try:
        state = run_simulation(
            region_id=req.region_id,
            intervention_text=req.intervention_text,
            intervention_year=req.target_years,
            bbox=req.bbox,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Simulation failed")
        raise HTTPException(500, f"Simulation failed: {exc}") from exc

    response = _build_response(state, run_id, time.time() - started)
    _prune_runs()
    return response


@app.post("/api/simulate/async")
def simulate_async(req: SimulateRequest) -> Dict[str, str]:
    if req.region_id not in REGIONS:
        raise HTTPException(404, f"Unknown region '{req.region_id}'")
    job_id = _new_job(req)
    return {"job_id": job_id,
            "stream_url": f"/api/stream/{job_id}"}


@app.get("/api/stream/{job_id}")
async def stream(job_id: str):
    """Server-sent events: one message per node completion, then the payload.

    The graph is synchronous CPU/network work, so it runs in a worker thread
    and hands chunks back through an asyncio queue. Running it inline would
    block the event loop and stall every other request, including /health.
    """
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, f"Unknown job '{job_id}'")

    # A browser retry or double-click would otherwise run the entire graph a
    # second time, doubling GPU cost and interleaving two log streams.
    if job["status"] in ("running", "done"):
        raise HTTPException(409, f"Job '{job_id}' is already {job['status']}; "
                                 f"fetch /api/result/{job_id}")

    req: SimulateRequest = job["request"]
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def worker():
        from backend.agents.workflow import stream_simulation
        started = time.time()
        merged: Dict[str, Any] = {}
        emitted = 0
        try:
            for node_name, update in stream_simulation(
                    region_id=req.region_id,
                    intervention_text=req.intervention_text,
                    intervention_year=req.target_years,
                    bbox=req.bbox):
                # execution_logs uses an operator.add reducer, so each update
                # carries only that node's NEW entries -- accumulate here.
                for key, value in update.items():
                    if key == "execution_logs":
                        merged.setdefault("execution_logs", [])
                        merged["execution_logs"].extend(value or [])
                    else:
                        merged[key] = value

                new_logs = (merged.get("execution_logs") or [])[emitted:]
                emitted = len(merged.get("execution_logs") or [])
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "event": "node",
                    "data": json.dumps({"node": node_name, "logs": new_logs}),
                })

            run_id = uuid.uuid4().hex[:12]
            payload = _build_response(merged, run_id, time.time() - started)
            _prune_runs()
            job.update(status="done", result=payload)
            loop.call_soon_threadsafe(queue.put_nowait, {
                "event": "complete", "data": json.dumps(payload)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Streaming simulation failed")
            job.update(status="error", error=str(exc))
            loop.call_soon_threadsafe(queue.put_nowait, {
                "event": "error", "data": json.dumps({"message": str(exc)})})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    async def event_generator():
        job["status"] = "running"
        await loop.run_in_executor(None, lambda: None)
        task = loop.run_in_executor(None, worker)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            task.cancel()

    return EventSourceResponse(event_generator())


@app.get("/api/result/{job_id}")
def result(job_id: str) -> Dict[str, Any]:
    """Fetch a finished job's payload (for a client that lost the stream)."""
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, f"Unknown job '{job_id}'")
    if job["status"] == "error":
        raise HTTPException(500, job["error"])
    if job["status"] != "done":
        return {"status": job["status"]}
    return job["result"]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=True)
