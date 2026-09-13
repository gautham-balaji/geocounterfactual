"""Stage 1 + 2 driver: dispatch, poll, and collect candidate detections.

Three subcommands, run in order:

    python -m backend.experiments.detect_candidates dispatch
    python -m backend.experiments.detect_candidates status --watch
    python -m backend.experiments.detect_candidates collect

Why batch Export rather than a synchronous call: a full-district 10 m
connectedPixelCount plus reduceRegion did not return inside ten minutes
interactively. Export tasks run under far higher limits and do not hold a
socket open, so the whole catalogue can be dispatched and left alone.

`collect` applies the rainfall confound filter CLIENT-SIDE. That is
deliberate: the thresholds are the part most likely to need tuning after
seeing real output, and re-running a six-hour export to change one number
would be indefensible. Every candidate carries its own rainfall evidence,
so re-filtering is instant.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

import ee

from backend.config import REGIONS, settings
from backend.data_engine.gee_auth import initialize_gee
from backend.data_engine.water_detection import (DetectionConfig,
                                                 build_candidates,
                                                 district_for_point,
                                                 patch_bbox)

ASSET_ROOT = "projects/geocounterfactual-backend/assets"
ASSET_FOLDER = f"{ASSET_ROOT}/candidates"
OUT_DIR = Path("backend/data/candidates")

# ---- Stage 2 thresholds, applied at collect time -------------------------
# A candidate must not be explainable by a wetter late period. 1.15 allows
# modest inter-annual variation while rejecting the marathwada case from the
# feasibility probe, where the late monsoon was 41% wetter and "new water"
# was almost certainly weather.
MAX_RAIN_RATIO = 1.15
# Sites that appeared DESPITE less rain are the strongest evidence of
# construction, and are flagged separately for the validation subset.
STRONG_RAIN_RATIO = 1.00


def _task_name(region_id: str) -> str:
    return f"gcf_cand_{region_id}"


def _asset_id(region_id: str) -> str:
    return f"{ASSET_FOLDER}/{region_id}"


def _ensure_folder():
    try:
        ee.data.createAsset({"type": "FOLDER"}, ASSET_FOLDER)
    except Exception:
        pass  # already exists


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------

def cmd_dispatch(args):
    initialize_gee()
    _ensure_folder()
    cfg = DetectionConfig()

    targets = args.regions or list(REGIONS)
    print(f"Dispatching {len(targets)} export task(s)\n")
    print(f"  early seasons : {cfg.early_years} (post-monsoon Nov-Feb)")
    print(f"  late seasons  : {cfg.late_years}")
    print(f"  persistence   : water in >={cfg.min_late_present} late, "
          f"<={cfg.max_early_present} early")
    print(f"  morphology    : {cfg.min_area_ha}-{cfg.max_area_ha} ha, "
          f"slope <= {cfg.max_slope_deg} deg, "
          f"valley >= {cfg.min_valley_depth_m} m\n")

    started = []
    for region_id in targets:
        region = REGIONS[region_id]
        lat = (region.bbox[1] + region.bbox[3]) / 2
        lon = (region.bbox[0] + region.bbox[2]) / 2

        # Search the whole district, not our 4 km demo tile: 240 km2 of tiles
        # cannot supply a fine-tuning set.
        district = district_for_point(lat, lon)
        geom = district.geometry()

        fc = build_candidates(geom, region.crs, cfg, region_id=region_id)

        if args.overwrite:
            try:
                ee.data.deleteAsset(_asset_id(region_id))
            except Exception:
                pass

        task = ee.batch.Export.table.toAsset(
            collection=fc,
            description=_task_name(region_id),
            assetId=_asset_id(region_id),
        )
        task.start()
        started.append((region_id, task.id))
        print(f"  [{task.id}] {region_id:13s} {region.name}")

    state = {"tasks": {r: t for r, t in started},
             "dispatched_at": time.time(),
             "config": {k: v for k, v in cfg.__dict__.items()}}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "tasks.json").write_text(json.dumps(state, indent=2),
                                        encoding="utf-8")
    print(f"\n{len(started)} task(s) running. Track with:  "
          f"python -m backend.experiments.detect_candidates status --watch")


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

def _statuses() -> Dict[str, dict]:
    state = json.loads((OUT_DIR / "tasks.json").read_text(encoding="utf-8"))
    out = {}
    for region_id, task_id in state["tasks"].items():
        try:
            out[region_id] = ee.data.getTaskStatus(task_id)[0]
        except Exception as exc:  # noqa: BLE001
            out[region_id] = {"state": "UNKNOWN", "error_message": str(exc)[:60]}
    return out


def cmd_status(args):
    initialize_gee()
    while True:
        rows = _statuses()
        done = sum(1 for s in rows.values()
                   if s.get("state") in ("COMPLETED", "FAILED", "CANCELLED"))
        print(f"\n{time.strftime('%H:%M:%S')}  {done}/{len(rows)} finished")
        for region_id, s in rows.items():
            st = s.get("state", "?")
            extra = ""
            if st == "FAILED":
                extra = f"  {s.get('error_message', '')[:70]}"
            elif st == "RUNNING" and s.get("start_timestamp_ms"):
                mins = (time.time() * 1000 - s["start_timestamp_ms"]) / 60000
                extra = f"  {mins:.0f} min"
            print(f"   {region_id:13s} {st:10s}{extra}")
        if not args.watch or done == len(rows):
            break
        time.sleep(60)


# --------------------------------------------------------------------------
# collect
# --------------------------------------------------------------------------

def _read_all_features(asset_id: str, page_size: int = 3000) -> List[dict]:
    """Read every feature from an exported table, paginated.

    FeatureCollection.getInfo() aborts past 5000 elements, which silently
    dropped five districts on the first collect -- including Anantapur, the
    primary demo region, and Kadapa, the highest-yield tile in the
    feasibility probe. The assets were complete; only the read was capped.

    ee.data.listFeatures pages server-side with no such ceiling, and it is a
    table read rather than a computation, so it still works while the
    project is in restricted mode.
    """
    features: List[dict] = []
    token = None
    while True:
        params = {"assetId": asset_id, "pageSize": page_size}
        if token:
            params["pageToken"] = token
        response = ee.data.listFeatures(params)
        features.extend(response.get("features", []))
        token = response.get("nextPageToken")
        if not token:
            return features


def _classify(props: dict) -> dict:
    """Stage 2 rainfall control, applied client-side."""
    early = props.get("rain_early_mm") or 0.0
    late = props.get("rain_late_mm") or 0.0
    ratio = (late / early) if early > 0 else float("inf")

    if ratio <= STRONG_RAIN_RATIO:
        confidence = "strong"      # appeared despite equal or less rain
    elif ratio <= MAX_RAIN_RATIO:
        confidence = "accepted"
    else:
        confidence = "rain_confounded"

    return {"rain_ratio": round(ratio, 3), "confidence": confidence}


def cmd_collect(args):
    initialize_gee()
    cfg = DetectionConfig()
    state = json.loads((OUT_DIR / "tasks.json").read_text(encoding="utf-8"))

    rows: List[dict] = []
    for region_id in state["tasks"]:
        try:
            feats = _read_all_features(_asset_id(region_id))
        except Exception as exc:  # noqa: BLE001
            print(f"  {region_id:13s} SKIP ({str(exc)[:60]})")
            continue

        kept = 0
        for i, f in enumerate(feats):
            p = f["properties"]
            lat, lon = p.get("lat"), p.get("lon")
            if lat is None or lon is None:
                continue
            verdict = _classify(p)
            row = {
                "candidate_id": f"{region_id}_{i:05d}",
                "region_id": region_id,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "area_ha": round(p.get("area_ha", 0), 4),
                "circularity": round(p.get("circularity", 0), 3),
                "slope_deg": round(p.get("slope_deg") or 0, 2),
                "valley_m": round(p.get("valley_m") or 0, 2),
                "late_seasons": round(p.get("late_seasons") or 0, 2),
                "early_seasons": round(p.get("early_seasons") or 0, 2),
                "rain_early_mm": round(p.get("rain_early_mm") or 0, 1),
                "rain_late_mm": round(p.get("rain_late_mm") or 0, 1),
                **verdict,
                "crs": REGIONS[region_id].crs,
            }
            bbox = patch_bbox(lat, lon, cfg)
            row.update({"bbox_min_lon": bbox[0], "bbox_min_lat": bbox[1],
                        "bbox_max_lon": bbox[2], "bbox_max_lat": bbox[3]})
            rows.append(row)
            kept += 1
        print(f"  {region_id:13s} {kept:5d} candidates")

    if not rows:
        print("\nNo candidates collected. Check `status` for failed tasks.")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    accepted = [r for r in rows if r["confidence"] != "rain_confounded"]
    strong = [r for r in accepted if r["confidence"] == "strong"]

    # CSV: everything, with the verdict, so nothing is silently discarded.
    csv_path = OUT_DIR / "candidates.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # GeoJSON: the accepted set, ready for Stage 3.
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
            "properties": r,
        } for r in accepted],
    }
    gj_path = OUT_DIR / "candidates.geojson"
    gj_path.write_text(json.dumps(geojson, indent=1), encoding="utf-8")

    print(f"\n  total detected     {len(rows):6d}")
    print(f"  rain-confounded    {len(rows) - len(accepted):6d}  "
          f"(late/early monsoon > {MAX_RAIN_RATIO})")
    print(f"  accepted           {len(accepted):6d}  -> {gj_path}")
    print(f"    of which strong  {len(strong):6d}  "
          f"(appeared on equal or LESS rain)")
    print(f"  full table         {csv_path}")
    print("\nStage 3 ingest: each row's bbox_* columns feed "
          "data_engine.cache.load_scene() directly.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dispatch", help="start Earth Engine export tasks")
    d.add_argument("--regions", nargs="*", help="subset of region ids")
    d.add_argument("--overwrite", action="store_true",
                   help="delete existing assets first")
    d.set_defaults(func=cmd_dispatch)

    s = sub.add_parser("status", help="poll task state")
    s.add_argument("--watch", action="store_true", help="poll until all finish")
    s.set_defaults(func=cmd_status)

    c = sub.add_parser("collect", help="read assets, filter, write CSV/GeoJSON")
    c.set_defaults(func=cmd_collect)

    args = ap.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
