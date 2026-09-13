"""Stage 3: turn accepted candidates into before/after training pairs.

    python -m backend.experiments.extract_pairs --sample 1500 --confidence strong

Three things this has to survive, all learned the hard way upstream:

RESUMABILITY. 1,500 pairs is 3,000 Earth Engine download calls against a
project already in restricted mode. The run WILL be interrupted. Every pair
is checked on disk before fetching, so re-running the identical command
picks up exactly where it stopped.

STRATIFICATION. District yields range from 1,374 (Jodhpur) to 15,670
(Bellary). Uniform random sampling would hand ~35% of the training set to
two districts and teach the model their specific terrain. Sampling is
balanced across districts by default.

DISK. A 512x512x8-band float32 GeoTIFF pair is ~8 MB, so 1,500 pairs is
~12 GB. Diffusion fine-tuning only consumes the RGB PNGs (~1 MB/pair), so
--png-only is the default and GeoTIFFs are opt-in for the evaluation subset
that the critic actually needs to measure.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from PIL import Image

from backend.data_engine import indices, raster_io
from backend.data_engine.cache import load_scene
from backend.data_engine.water_detection import DetectionConfig

CANDIDATES = Path("backend/data/candidates/candidates.geojson")
PAIRS_DIR = Path("backend/data/pairs")
MANIFEST = PAIRS_DIR / "manifest.jsonl"


def windows(cfg: DetectionConfig):
    """Windows must match the ones detection used, or a 'before' frame
    could already contain the structure."""
    return ((f"{cfg.early_years[0]}-11-01", f"{cfg.early_years[0] + 1}-02-28"),
            (f"{cfg.late_years[-1]}-11-01", f"{cfg.late_years[-1] + 1}-02-28"))


def stratified_sample(feats, n, seed):
    """Balanced across districts, then filled proportionally.

    Each district first contributes an equal share; districts with fewer
    candidates than that share give back their shortfall, which is then
    redistributed to the larger districts in proportion. The result covers
    every district without letting Bellary dominate.
    """
    rng = random.Random(seed)
    by_region = defaultdict(list)
    for f in feats:
        by_region[f["properties"]["region_id"]].append(f)
    for v in by_region.values():
        rng.shuffle(v)

    regions = sorted(by_region)
    quota = {r: 0 for r in regions}
    remaining, pool = n, list(regions)

    while remaining > 0 and pool:
        share = max(1, remaining // len(pool))
        progressed = False
        for r in list(pool):
            if remaining <= 0:
                break
            can = min(share, len(by_region[r]) - quota[r])
            if can <= 0:
                pool.remove(r)
                continue
            quota[r] += can
            remaining -= can
            progressed = True
        if not progressed:
            break

    out = []
    for r in regions:
        out.extend(by_region[r][:quota[r]])
    rng.shuffle(out)
    return out


def span_bbox(lat: float, lon: float, span_m: int):
    """Bbox of a given ground span centred on a point.

    The candidate file stores a 5.12 km bbox (512 px at native 10 m), which
    is the wrong framing for these targets: 70% of strong candidates are
    ~44 m across, which is 4.4 px in a 512 px frame -- under 1% of the
    image. Before and after would be visually identical and the model would
    learn nothing. A tighter span puts the structure at roughly 10% of the
    frame instead.
    """
    import math
    half = span_m / 2.0
    dlat = half / 110_540.0
    dlon = half / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return [round(lon - dlon, 6), round(lat - dlat, 6),
            round(lon + dlon, 6), round(lat + dlat, 6)]


def save_rgb(rgb, path, out_px):
    """Render and resample to the training edge length.

    Upsampling from ~128 native pixels to 512 is honest about the limit:
    Sentinel-2 holds no more detail at 10 m. The alternative -- a wider
    frame at native scale -- makes the structure too small to learn.
    """
    raster_io.render_rgb(rgb, path)
    if out_px:
        img = Image.open(path)
        if img.size != (out_px, out_px):
            img.resize((out_px, out_px), Image.LANCZOS).save(path)


def already_done(cid: str, png_only: bool) -> bool:
    d = PAIRS_DIR / cid
    need = ["before.png", "after.png", "meta.json"]
    if not png_only:
        need += ["before.tif", "after.tif"]
    return all((d / f).is_file() for f in need)


def caption(p: dict) -> str:
    shape = ("elongated channel impoundment" if p["circularity"] < 0.45
             else "compact excavated pond")
    return (f"aerial satellite view, semi-arid Indian watershed, "
            f"{p['area_ha']:.2f} hectare water harvesting structure, "
            f"{shape}, slope {p['slope_deg']:.1f} degrees, "
            f"10 m Sentinel-2 true colour")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=None,
                    help="number of pairs to extract")
    ap.add_argument("--confidence", choices=["strong", "accepted", "all"],
                    default="strong")
    ap.add_argument("--seed", type=int, default=42,
                    help="sampling seed; same seed = same sample")
    ap.add_argument("--no-stratify", action="store_true",
                    help="uniform random instead of district-balanced")
    ap.add_argument("--with-geotiff", action="store_true",
                    help="also write 8-band GeoTIFFs (~8 MB/pair)")
    ap.add_argument("--min-area-ha", type=float, default=1.0,
                    help="skip structures smaller than this; below ~1 ha the "
                         "structure is under 3%% of the frame and the pair is "
                         "not learnable")
    ap.add_argument("--patch-span-m", type=int, default=1280,
                    help="ground span of the training patch in metres")
    ap.add_argument("--out-px", type=int, default=512,
                    help="output edge in pixels; patches are resampled to this")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="seconds between pairs; raise if quota-throttled")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not CANDIDATES.is_file():
        print(f"No candidates at {CANDIDATES}. Run detect_candidates first.")
        return 1

    feats = json.loads(CANDIDATES.read_text(encoding="utf-8"))["features"]
    if args.confidence != "all":
        feats = [f for f in feats
                 if f["properties"]["confidence"] == args.confidence]

    if args.min_area_ha:
        before_n = len(feats)
        feats = [f for f in feats
                 if f["properties"]["area_ha"] >= args.min_area_ha]
        print(f"area filter >= {args.min_area_ha} ha : "
              f"{before_n} -> {len(feats)}")

    total_available = len(feats)
    if args.sample and args.sample < total_available:
        feats = (random.Random(args.seed).sample(feats, args.sample)
                 if args.no_stratify
                 else stratified_sample(feats, args.sample, args.seed))

    cfg = DetectionConfig()
    (b_start, b_end), (a_start, a_end) = windows(cfg)
    png_only = not args.with_geotiff

    dist = Counter(f["properties"]["region_id"] for f in feats)
    print(f"available ({args.confidence}) : {total_available}")
    print(f"selected                  : {len(feats)}  "
          f"({'uniform' if args.no_stratify else 'stratified'}, seed {args.seed})")
    print(f"before window             : {b_start} .. {b_end}")
    print(f"after  window             : {a_start} .. {a_end}")
    print(f"outputs                   : "
          f"{'PNG only' if png_only else 'PNG + 8-band GeoTIFF'}")
    native_px = args.patch_span_m / 10
    print(f"patch                     : {args.patch_span_m} m span, "
          f"{native_px:.0f} px native -> {args.out_px} px "
          f"({args.out_px / native_px:.1f}x resample)")
    print(f"\ndistrict balance:")
    for r, c in sorted(dist.items()):
        print(f"   {r:13s} {c:5d}")

    pending = [f for f in feats
               if not already_done(f["properties"]["candidate_id"], png_only)]
    done_already = len(feats) - len(pending)
    est_gb = len(feats) * (0.0011 if png_only else 0.0085) \
        * (args.out_px / 512.0) ** 2
    print(f"\nalready on disk           : {done_already}")
    print(f"to fetch                  : {len(pending)}  "
          f"({len(pending) * 2} Earth Engine calls)")
    print(f"estimated disk            : ~{est_gb:.1f} GB total")

    if args.dry_run:
        print("\nDry run: nothing fetched.")
        return 0

    PAIRS_DIR.mkdir(parents=True, exist_ok=True)
    written = failed = 0
    started = time.time()

    for i, f in enumerate(pending, 1):
        p = f["properties"]
        cid = p["candidate_id"]
        bbox = span_bbox(p["lat"], p["lon"], args.patch_span_m)
        out = PAIRS_DIR / cid

        before = after = None
        for attempt in range(1, args.retries + 1):
            try:
                before = load_scene(bbox, b_start, b_end, crs=p["crs"],
                                    allow_synthetic=False)
                after = load_scene(bbox, a_start, a_end, crs=p["crs"],
                                   allow_synthetic=False)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == args.retries:
                    print(f"  [{i}/{len(pending)}] {cid:20s} FAILED "
                          f"{str(exc)[:52]}")
                    failed += 1
                else:
                    # Exponential backoff. Restricted mode throttles rather
                    # than hard-fails, so waiting is usually enough.
                    time.sleep(2 ** attempt)
        if before is None or after is None:
            continue

        if before.shape != after.shape:
            print(f"  [{i}/{len(pending)}] {cid:20s} SKIP shape "
                  f"{before.shape} vs {after.shape}")
            failed += 1
            continue

        out.mkdir(parents=True, exist_ok=True)
        save_rgb(before.rgb, out / "before.png", args.out_px)
        save_rgb(after.rgb, out / "after.png", args.out_px)
        if args.with_geotiff:
            raster_io.write_geotiff(out / "before.tif", before.bands,
                                    before.transform, before.crs)
            raster_io.write_geotiff(out / "after.tif", after.bands,
                                    after.transform, after.crs)

        b_ndvi = float(np.nanmean(indices.ndvi(before.bands["B8"],
                                               before.bands["B4"])))
        a_ndvi = float(np.nanmean(indices.ndvi(after.bands["B8"],
                                               after.bands["B4"])))
        meta = {**p, "shape": list(before.shape),
                "ndvi_before": round(b_ndvi, 4),
                "ndvi_after": round(a_ndvi, 4),
                "caption": caption(p)}
        (out / "meta.json").write_text(json.dumps(meta, indent=2),
                                       encoding="utf-8")
        with MANIFEST.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": cid, "dir": str(out),
                                 "caption": meta["caption"]}) + "\n")

        written += 1
        if written % 10 == 0 or written == 1:
            rate = written / max(time.time() - started, 1e-9)
            eta_min = (len(pending) - i) / max(rate, 1e-9) / 60
            print(f"  [{i}/{len(pending)}] {cid:20s} ok  "
                  f"{rate * 60:.1f}/min  ETA {eta_min:.0f} min")

        if args.sleep:
            time.sleep(args.sleep)

    print(f"\n{written} written, {failed} failed, "
          f"{done_already} already present")
    print(f"manifest: {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
