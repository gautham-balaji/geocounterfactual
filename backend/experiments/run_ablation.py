"""Critic ablation: does the physics loop matter, and does fine-tuning absorb it?

Four arms, crossing the generator with the critic mode:

    Base-Shadow   base SD 1.5,  critic scores but never gates    (A)
    Base-Gating   base SD 1.5,  critic rejects and regenerates   (B)
    LoRA-Shadow   fine-tuned,   critic scores but never gates    (C)
    LoRA-Gating   fine-tuned,   critic rejects and regenerates   (D)

Shadow mode is the measuring control arm: every rule is evaluated and the
honest verdict recorded, but nothing is sent back. critic_off() cannot serve
here -- it evaluates no rules, so it reports a 4-way physics breach as
approved at 100%.

Hypotheses read off the summary:
    H1  B < A          the loop reduces violations on the base model
    H2  (A-B) >> (C-D) fine-tuning absorbs most of what the loop enforces
    H3  C > 0          the fine-tuned model still violates, so runtime
                       enforcement is not redundant

Two controls keep the arms differing in exactly one variable:
  * Both generator variants run in PATCH mode at the training scale. The
    local backend otherwise ties patch mode to the presence of an adapter,
    so a base run would also change framing (whole scene at 10 m/px versus
    1280 m windows at 2.5 m/px) and the adapter would be credited with it.
  * Intent is parsed by the deterministic keyword planner, not Gemini. An
    LLM that is up for some cases and rate-limited for others would plan
    different interventions across arms. --llm-planner overrides this.

Every row is appended and flushed as it completes, so a long sweep can be
interrupted and resumed by re-running the same command: rows already
recorded as ok are skipped.

Usage:
    # plumbing check, seconds, no GPU (stub has no adapter: base == LoRA)
    python -m backend.experiments.run_ablation --generator stub \\
        --regions anantapur,kadapa --interventions check_dam

    # the real sweep on the Colab T4
    python -m backend.experiments.run_ablation --generator remote

    # re-print the summary of a finished or partial sweep
    python -m backend.experiments.run_ablation --summarize path/to/run.csv
"""

from __future__ import annotations

import argparse
import csv
import gc
import logging
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.config import BACKEND_DIR, REGIONS, settings

logger = logging.getLogger(__name__)

# label -> (generator variant, critic mode)
ARMS: Dict[str, Tuple[str, str]] = {
    "Base-Shadow": ("base", "shadow"),
    "Base-Gating": ("base", "gating"),
    "LoRA-Shadow": ("lora", "shadow"),
    "LoRA-Gating": ("lora", "gating"),
}

# Phrased so keyword_fallback() parses each to its own structure type; the
# runner checks the parse and marks a mismatch rather than trusting it.
INTERVENTIONS: Dict[str, str] = {
    "check_dam": "Build 3 series check-dams along the main dry stream bed.",
    "farm_pond": "Dig 5 farm ponds to harvest monsoon runoff for "
                 "supplemental irrigation.",
    "contour_bund": "Construct contour bunding across the upper slopes.",
    "percolation_pit": "Dig 20 percolation pits along the field boundaries.",
    "afforestation": "Afforest 150 hectares of degraded upland with native "
                     "dryland species.",
}
# The adapter learned impounded water from detected structures. Bunds, pits
# and plantations create no impoundment core, which puts them outside its
# training distribution; they are available but not swept by default.
DEFAULT_INTERVENTIONS = ("check_dam", "farm_pond")

RULES = ("R1", "R2", "R3", "R4")

COLUMNS = [
    # requested
    "arm", "region", "intervention", "score",
    "r1_violations", "r2_violations", "r3_violations", "r4_violations",
    "iterations", "approved",
    # provenance and validity
    "first_pass_score", "first_pass_approved", "rules_failed",
    "structure_type", "generator", "adapter", "critic_mode", "seed",
    "max_iterations", "scene_source", "status", "elapsed_s", "error",
    "timestamp",
]

OUT_DIR = BACKEND_DIR / "outputs" / "ablation"   # gitignored

FALLBACK_MARKER = "fell back to"


# --------------------------------------------------------------------------
# Instrumentation
# --------------------------------------------------------------------------

class RecordingCritic:
    """Pass-through critic that keeps every verdict of a run.

    critic_node keeps only the final score and violation strings in state,
    and the per-rule pixel counts the CSV needs live on the RuleResults.
    """

    def __init__(self, inner):
        self.inner = inner
        self.verdicts: List[Dict[str, Any]] = []

    @property
    def name(self) -> str:
        return getattr(self.inner, "name", "recording")

    def evaluate(self, state) -> Dict[str, Any]:
        verdict = self.inner.evaluate(state)
        self.verdicts.append(verdict)
        return verdict


def make_generator(backend: str, variant: str, seed: int):
    if backend == "stub":
        from backend.generator.stub import StubGenerator
        return StubGenerator()
    if backend == "local":
        from backend.generator.diffusion_local import LocalDiffusionGenerator
        # lora_path=None means "use the configured default", so the base
        # variant has to pass an empty path to get no adapter at all.
        lora = str(settings.lora_weights_path) if variant == "lora" else ""
        return LocalDiffusionGenerator(lora_path=lora, patch_mode=True,
                                       seed=seed)
    if backend == "remote":
        from backend.generator.remote_client import RemoteGenerator
        return RemoteGenerator(use_lora=(variant == "lora"), seed=seed)
    raise ValueError(f"unknown generator backend '{backend}'")


def preflight(backend: str, variants: List[str]) -> None:
    """Refuse to start a sweep whose arms could not be what they claim."""
    if backend == "stub":
        print("NOTE: the stub has no adapter, so base and LoRA arms are "
              "identical by construction.\n      This sweep checks plumbing "
              "only; its numbers are not results.\n")
        return
    if backend == "local" and "lora" in variants:
        path = settings.lora_weights_path
        if not (path and Path(path).is_file()):
            sys.exit(f"LoRA weights not found at {path}.")
        print("NOTE: local CPU runs ~7 min per diffusion pass; a full sweep "
              "takes days. Use --generator remote.\n")
    if backend == "remote":
        from backend.generator.remote_client import (ABLATION_PROTOCOL,
                                                     RemoteGenerator)
        try:
            health = RemoteGenerator().health()
        except Exception as exc:  # noqa: BLE001
            sys.exit(f"Colab server unreachable ({exc}). Is the notebook "
                     f"running, and is REMOTE_GENERATOR_URL current?")
        protocol = int(health.get("protocol", 1))
        if protocol < ABLATION_PROTOCOL:
            sys.exit(f"Colab server speaks protocol {protocol}; the ablation "
                     f"needs {ABLATION_PROTOCOL}. Re-upload "
                     f"backend/generator/colab_server.py and restart the "
                     f"server cell. (An old server ignores use_lora, so the "
                     f"base arms would silently run the adapter.)")
        if "lora" in variants and not health.get("lora_file_present"):
            sys.exit("Colab server has no geocf_lora.safetensors at "
                     "/content/; the LoRA arms cannot run.")
        print(f"Colab server: {health.get('gpu') or health.get('device')}, "
              f"protocol {protocol}, adapter file present: "
              f"{health.get('lora_file_present')}\n")


# --------------------------------------------------------------------------
# One run
# --------------------------------------------------------------------------

def run_case(arm: str, region: str, intervention: str, generator,
             backend: str, seed: int, years: int) -> Dict[str, Any]:
    from backend.agents import critic_node, generator_node
    from backend.agents.workflow import run_simulation
    from backend.critic.physics_critic import (PhysicalPlausibilityCritic,
                                               critic_shadow)

    variant, mode = ARMS[arm]
    inner = critic_shadow() if mode == "shadow" else PhysicalPlausibilityCritic()
    recorder = RecordingCritic(inner)

    row: Dict[str, Any] = {
        "arm": arm, "region": region, "intervention": intervention,
        "generator": backend, "adapter": variant if backend != "stub"
        else "n/a (stub)", "critic_mode": mode, "seed": seed,
        "max_iterations": settings.max_critic_iterations,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "error": "",
    }

    previous_critic = critic_node.get_critic()
    critic_node.set_critic(recorder)
    generator_node.set_generator(generator)
    started = time.time()
    try:
        state = run_simulation(region, INTERVENTIONS[intervention], years)
    except Exception as exc:  # noqa: BLE001
        row.update(status="error", error=f"{type(exc).__name__}: {exc}"[:300],
                   elapsed_s=round(time.time() - started, 1))
        return row
    finally:
        critic_node.set_critic(previous_critic)

    row["elapsed_s"] = round(time.time() - started, 1)

    if not recorder.verdicts:
        row.update(status="error", error="critic never ran")
        return row

    final, first = recorder.verdicts[-1], recorder.verdicts[0]
    by_rule = {r.rule_id: r for r in (final.get("results") or [])}
    failed = []
    for rid in RULES:
        result = by_rule.get(rid)
        px = 0
        if result is not None and not result.passed:
            px = int(np.sum(np.asarray(result.mask, dtype=bool)))
            failed.append(rid)
        row[f"{rid.lower()}_violations"] = px

    plan = state.get("intervention_plan") or {}
    logs = state.get("execution_logs") or []
    row.update(
        score=round(float(state.get("plausibility_score", 0.0)), 2),
        iterations=int(state.get("iteration_count", 0)),
        approved=bool(state.get("is_approved", False)),
        first_pass_score=round(float(first["score"]), 2),
        first_pass_approved=bool(first["is_approved"]),
        rules_failed="+".join(failed),
        structure_type=plan.get("structure_type", ""),
        scene_source=state.get("scene_source", "unknown"),
    )

    # A run is only evidence if every condition the arm claims held.
    if any(FALLBACK_MARKER in str(e.get("text", "")) for e in logs):
        row.update(status="generator_fallback",
                   error="primary generator failed; the stub ran instead")
    elif row["scene_source"] == "synthetic":
        row.update(status="synthetic_scene",
                   error="Earth Engine unavailable; fabricated imagery")
    elif row["structure_type"] != intervention:
        row.update(status="plan_mismatch",
                   error=f"planner produced {row['structure_type']}")
    else:
        row["status"] = "ok"
    return row


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------

def _key(row: Dict[str, Any]) -> Tuple:
    return (row["arm"], row["region"], row["intervention"], str(row["seed"]))


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def latest_ok(rows: List[Dict[str, str]]) -> Dict[Tuple, Dict[str, str]]:
    """Last ok row per case; a re-run after a failure supersedes it."""
    out: Dict[Tuple, Dict[str, str]] = {}
    for row in rows:
        if row.get("status") == "ok":
            out[_key(row)] = row
    return out


def append_row(path: Path, row: Dict[str, Any]) -> None:
    new = not path.is_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerow(row)
        fh.flush()


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

def _truthy(value: str) -> bool:
    return str(value).strip().lower() == "true"


def summarize(path: Path) -> None:
    rows = list(latest_ok(read_rows(path)).values())
    print("=" * 78)
    print(f"ABLATION SUMMARY  {path}")
    print("=" * 78)
    if not rows:
        print("No completed (status=ok) rows yet.")
        return

    stub = any(r["generator"] == "stub" for r in rows)
    by_arm: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)

    print(f"{'arm':12s} {'n':>3s} {'viol.rate':>9s} {'score':>6s} "
          f"{'iters':>5s} {'approved':>8s}   " +
          " ".join(f"{rid:>5s}" for rid in RULES))
    print("-" * 78)
    rate: Dict[str, float] = {}
    for arm in ARMS:
        group = by_arm.get(arm, [])
        if not group:
            continue
        n = len(group)
        violated = sum(not _truthy(r["approved"]) for r in group) / n
        rate[arm] = violated
        rule_rates = [sum(int(r[f"{rid.lower()}_violations"]) > 0
                          for r in group) / n for rid in RULES]
        print(f"{arm:12s} {n:3d} {100 * violated:8.1f}% "
              f"{np.mean([float(r['score']) for r in group]):6.1f} "
              f"{np.mean([int(r['iterations']) for r in group]):5.2f} "
              f"{100 * (1 - violated):7.1f}%   " +
              " ".join(f"{100 * x:4.0f}%" for x in rule_rates))
    print("  viol.rate = runs released with >=1 violation; rule columns = "
          "share of runs\n  in which that rule still failed on the "
          "released scene.")

    # Shadow and gating arms run identical first passes (same seed, same
    # inputs, iteration 0), so their first-pass scores must agree. If they
    # do not, generation is nondeterministic and arm differences are
    # partly noise.
    pairs = mismatched = 0
    for variant in ("base", "lora"):
        shadow = {(r["region"], r["intervention"], r["seed"]): r
                  for r in by_arm.get(f"{'Base' if variant == 'base' else 'LoRA'}"
                                      f"-Shadow", [])}
        for r in by_arm.get(f"{'Base' if variant == 'base' else 'LoRA'}"
                            f"-Gating", []):
            s = shadow.get((r["region"], r["intervention"], r["seed"]))
            if s is None:
                continue
            pairs += 1
            if abs(float(s["score"]) - float(r["first_pass_score"])) > 0.05:
                mismatched += 1
    if pairs:
        verdict = ("deterministic" if not mismatched else
                   f"{mismatched} MISMATCHED - generation is not "
                   f"reproducible; treat arm differences with caution")
        print(f"\nDeterminism: {pairs} shadow/gating first-pass pair(s), "
              f"{verdict}.")

    a, b = rate.get("Base-Shadow"), rate.get("Base-Gating")
    c, d = rate.get("LoRA-Shadow"), rate.get("LoRA-Gating")
    print("\nHypotheses (violation rates):")
    if a is not None and b is not None:
        print(f"  H1  loop effect on base       A-B = {100 * a:.1f}% - "
              f"{100 * b:.1f}% = {100 * (a - b):+.1f} pts")
    if a is not None and c is not None:
        print(f"      fine-tune effect, no loop A-C = {100 * a:.1f}% - "
              f"{100 * c:.1f}% = {100 * (a - c):+.1f} pts")
    if None not in (a, b, c, d):
        print(f"  H2  loop effect, base vs LoRA (A-B) vs (C-D) = "
              f"{100 * (a - b):+.1f} vs {100 * (c - d):+.1f} pts")
    if c is not None:
        print(f"  H3  LoRA unconstrained        C   = {100 * c:.1f}% "
              f"({'> 0: runtime enforcement still needed' if c > 0 else '= 0 in this sample'})")
    n_min = min(len(g) for g in by_arm.values())
    print(f"\n  Smallest arm n = {n_min}. Descriptive only; no significance "
          f"test is applied.")
    if stub:
        print("\n  PLUMBING ONLY: stub generator, base and LoRA arms are "
              "identical by construction.")


# --------------------------------------------------------------------------
# Sweep
# --------------------------------------------------------------------------

def _parse_list(value: str, universe, name: str) -> List[str]:
    if value == "all":
        return list(universe)
    items = [v.strip() for v in value.split(",") if v.strip()]
    unknown = [v for v in items if v not in universe]
    if unknown:
        sys.exit(f"unknown {name}: {unknown}. Known: {sorted(universe)}")
    return items


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--generator", choices=("stub", "local", "remote"),
                    default="remote")
    ap.add_argument("--regions", default="all",
                    help="comma list of region ids, or 'all'")
    ap.add_argument("--interventions", default=",".join(DEFAULT_INTERVENTIONS),
                    help=f"comma list from {sorted(INTERVENTIONS)}, or 'all'")
    ap.add_argument("--arms", default="all",
                    help=f"comma list from {list(ARMS)}, or 'all'")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--out", type=Path, default=None,
                    help="CSV path; an existing file is resumed")
    ap.add_argument("--llm-planner", action="store_true",
                    help="parse intent with Gemini instead of the "
                         "deterministic keyword planner")
    ap.add_argument("--keep-going", action="store_true",
                    help="continue after a generator fallback instead of "
                         "aborting")
    ap.add_argument("--summarize", type=Path, default=None,
                    help="print the summary of an existing CSV and exit")
    args = ap.parse_args()

    warnings.filterwarnings("ignore")
    logging.basicConfig(level=logging.ERROR)

    if args.summarize:
        summarize(args.summarize)
        return 0

    regions = _parse_list(args.regions, REGIONS, "regions")
    interventions = _parse_list(args.interventions, INTERVENTIONS,
                                "interventions")
    arms = _parse_list(args.arms, ARMS, "arms")
    variants = [v for v in ("base", "lora")
                if any(ARMS[a][0] == v for a in arms)]

    out = args.out or OUT_DIR / (f"ablation_{args.generator}_seed{args.seed}_"
                                 f"{datetime.now():%Y%m%d_%H%M%S}.csv")

    np.random.seed(args.seed)
    if args.generator == "local":
        import torch
        torch.manual_seed(args.seed)

    if not args.llm_planner:
        import backend.agents.planner as planner_mod
        planner_mod.parse_intent_with_gemini = (
            lambda *a, **k: (None, "ablation uses the keyword planner for "
                                   "reproducibility"))

    preflight(args.generator, variants)

    done = latest_ok(read_rows(out))
    plan = [(arm, region, iv)
            for variant in variants          # one model in memory at a time
            for region in regions
            for iv in interventions
            for arm in arms if ARMS[arm][0] == variant]
    todo = [p for p in plan
            if (p[0], p[1], p[2], str(args.seed)) not in done]

    print(f"Sweep: {len(arms)} arm(s) x {len(regions)} region(s) x "
          f"{len(interventions)} intervention(s) = {len(plan)} run(s); "
          f"{len(plan) - len(todo)} already done, {len(todo)} to run.")
    print(f"Seed {args.seed}, horizon {args.years} yr, critic budget "
          f"{settings.max_critic_iterations}, planner "
          f"{'Gemini' if args.llm_planner else 'keyword'}.")
    print(f"Output: {out}\n")

    generator, loaded_variant = None, None
    elapsed: List[float] = []
    try:
        for i, (arm, region, iv) in enumerate(todo, 1):
            variant = ARMS[arm][0]
            if variant != loaded_variant:
                generator = None
                gc.collect()
                generator = make_generator(args.generator, variant, args.seed)
                loaded_variant = variant

            row = run_case(arm, region, iv, generator, args.generator,
                           args.seed, args.years)
            append_row(out, row)
            elapsed.append(float(row.get("elapsed_s") or 0))

            eta = np.mean(elapsed) * (len(todo) - i) / 60
            status = ("approved" if row.get("approved") else "REJECTED") \
                if row["status"] == "ok" else row["status"].upper()
            print(f"[{i:3d}/{len(todo)}] {arm:12s} {region:12s} {iv:15s} "
                  f"score {row.get('score', 0):5.1f}  "
                  f"iters {row.get('iterations', 0)}  {status:9s} "
                  f"{row.get('rules_failed') or '-':11s} "
                  f"{row['elapsed_s']:6.1f}s  eta {eta:5.1f} min")
            if row["status"] == "error":
                print(f"      error: {row['error']}")

            if row["status"] == "generator_fallback" and not args.keep_going:
                print("\nABORTED: the primary generator failed and the stub "
                      "ran in its place, so this row is not evidence. Fix "
                      "the backend, then re-run the same command to resume.")
                return 1
    except KeyboardInterrupt:
        print("\nInterrupted. Completed rows are saved; re-run the same "
              "command with --out to resume.")
        print(f"  --out {out}")
        return 130

    print()
    summarize(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
