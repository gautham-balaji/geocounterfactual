"""Stage 3 bridge: turn accepted candidates into before/after training pairs.

Included here because "the output is ingestible by gee_loader" is a claim
worth proving rather than asserting. This script is the proof: it reads
candidates.geojson and calls the existing data engine with no adapter.

    python -m backend.experiments.extract_pairs --limit 5 --dry-run
    python -m backend.experiments.extract_pairs --confidence strong

Each accepted candidate yields two co-registered 512x512 scenes on one grid:
  before  post-monsoon of the early period (pre-construction)
  after   post-monsoon of the late period  (post-construction)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from backend.config import settings
from backend.data_engine import indices, raster_io
from backend.data_engine.cache import load_scene
from backend.data_engine.water_detection import DetectionConfig

CANDIDATES = Path("backend/data/candidates/candidates.geojson")
PAIRS_DIR = Path("backend/data/pairs")


def windows(cfg: DetectionConfig):
    """Post-monsoon windows matching the ones detection used.

    They must match, or a pair could show a season the detector never
    examined and the "before" frame might already contain the structure.
    """
    early = (f"{cfg.early_years[0]}-11-01", f"{cfg.early_years[0] + 1}-02-28")
    late = (f"{cfg.late_years[-1]}-11-01", f"{cfg.late_years[-1] + 1}-02-28")
    return early, late


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--confidence", choices=["strong", "accepted", "all"],
                    default="all")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve inputs and report, fetch nothing")
    args = ap.parse_args()

    if not CANDIDATES.is_file():
        print(f"No candidate file at {CANDIDATES}. Run detect_candidates "
              f"dispatch -> status -> collect first.")
        return 1

    feats = json.loads(CANDIDATES.read_text(encoding="utf-8"))["features"]
    if args.confidence != "all":
        feats = [f for f in feats
                 if f["properties"]["confidence"] == args.confidence]
    if args.limit:
        feats = feats[:args.limit]

    cfg = DetectionConfig()
    (early_start, early_end), (late_start, late_end) = windows(cfg)
    print(f"{len(feats)} candidate(s)")
    print(f"  before window : {early_start} to {early_end}")
    print(f"  after window  : {late_start} to {late_end}\n")

    if args.dry_run:
        for f in feats[:10]:
            p = f["properties"]
            bbox = [p["bbox_min_lon"], p["bbox_min_lat"],
                    p["bbox_max_lon"], p["bbox_max_lat"]]
            print(f"  {p['candidate_id']}  {p['area_ha']:.2f} ha  "
                  f"{p['confidence']:16s} bbox={bbox} crs={p['crs']}")
        print("\nDry run: no imagery fetched.")
        return 0

    PAIRS_DIR.mkdir(parents=True, exist_ok=True)
    written = failed = 0

    for f in feats:
        p = f["properties"]
        cid = p["candidate_id"]
        bbox = [p["bbox_min_lon"], p["bbox_min_lat"],
                p["bbox_max_lon"], p["bbox_max_lat"]]
        out = PAIRS_DIR / cid

        try:
            # The existing loader, unchanged. This is the whole point of
            # emitting bbox + crs in the candidate schema.
            before = load_scene(bbox, early_start, early_end, crs=p["crs"],
                                allow_synthetic=False)
            after = load_scene(bbox, late_start, late_end, crs=p["crs"],
                               allow_synthetic=False)
        except Exception as exc:  # noqa: BLE001
            print(f"  {cid:22s} FAILED {str(exc)[:56]}")
            failed += 1
            continue

        if before.shape != after.shape:
            print(f"  {cid:22s} SKIP shape mismatch "
                  f"{before.shape} vs {after.shape}")
            failed += 1
            continue

        out.mkdir(parents=True, exist_ok=True)
        raster_io.render_rgb(before.rgb, out / "before.png")
        raster_io.render_rgb(after.rgb, out / "after.png")
        raster_io.write_geotiff(out / "before.tif", before.bands,
                                before.transform, before.crs)
        raster_io.write_geotiff(out / "after.tif", after.bands,
                                after.transform, after.crs)

        b_ndvi = indices.ndvi(before.bands["B8"], before.bands["B4"])
        a_ndvi = indices.ndvi(after.bands["B8"], after.bands["B4"])
        (out / "meta.json").write_text(json.dumps({
            **p,
            "shape": list(before.shape),
            "ndvi_before": round(float(np.nanmean(b_ndvi)), 4),
            "ndvi_after": round(float(np.nanmean(a_ndvi)), 4),
            "caption": (
                f"satellite view, semi-arid Indian watershed, "
                f"{p['area_ha']:.2f} ha water harvesting structure, "
                f"{'elongated channel impoundment' if p['circularity'] < 0.45 else 'compact excavated pond'}, "
                f"slope {p['slope_deg']:.1f} degrees, 10 m Sentinel-2 true colour"
            ),
        }, indent=2), encoding="utf-8")

        written += 1
        print(f"  {cid:22s} ok  {before.shape}  "
              f"NDVI {np.nanmean(b_ndvi):+.3f} -> {np.nanmean(a_ndvi):+.3f}")

    print(f"\n{written} pair(s) written to {PAIRS_DIR}, {failed} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
