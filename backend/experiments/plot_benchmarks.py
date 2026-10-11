"""Publication figures and table for the critic ablation.

Reads one or more CSVs written by run_ablation.py (rows from several seeds
merge naturally; each row is keyed by arm, region, intervention and seed)
and writes to backend/outputs/figures/:

    fig_violation_rates.{pdf,png}   per-rule and overall violation rates by
                                    arm, with Wilson 95% intervals
    fig_scores_iterations.{pdf,png} (a) plausibility scores per run with the
                                    mean and a bootstrap 95% interval;
                                    (b) iterations to approval
    table_summary.{tex,csv,md}      the same numbers as a table

Only status=ok rows are used, the last per case, exactly as the runner's own
summary does -- a figure and the console summary cannot disagree.

Encoding. The ablation is a 2x2 design, and the figures say so: colour is
the generator (Base blue, LoRA orange) and fill is the critic mode (Shadow
hatched and light, Gating solid). Reading hatched against solid within one
colour is the loop's effect; reading across colours is the fine-tune's.
Bar order is fixed, every figure has a legend, and the hatching survives
greyscale print, so no arm is identified by colour alone. Both palettes were
checked with a colour-vision-deficiency validator against a white page.

Vector PDFs embed TrueType (Type 42) fonts, which journals require; Type 3
fonts are rejected by most submission systems.

Usage:
    python -m backend.experiments.plot_benchmarks backend/outputs/ablation/run.csv
    python -m backend.experiments.plot_benchmarks a.csv b.csv --dpi 600
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from backend.config import BACKEND_DIR  # noqa: E402
from backend.experiments.run_ablation import (ARMS, RULES, latest_ok,  # noqa: E402
                                              read_rows)

OUT_DIR = BACKEND_DIR / "outputs" / "figures"     # gitignored

# ---- palette (validated: CVD dE 24.7, normal-vision dE 33.6 on white) -----
GENERATOR_COLOUR = {"base": "#2a78d6", "lora": "#eb6834"}
# Ordinal, one neutral hue: iteration counts must not borrow the generator
# blue, which already means "Base" in the same figure.
ITERATION_COLOURS = ("#a9a8a1", "#6f6e69", "#3a3936")
UNAPPROVED = "#d03b3b"          # status: critical, always with its label

INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

RULE_LABELS = {"R1": "R1 gravity", "R2": "R2 growth",
               "R3": "R3 red edge", "R4": "R4 conservation"}
ARM_LABELS = {"Base-Shadow": "Base, shadow", "Base-Gating": "Base, gating",
              "LoRA-Shadow": "LoRA, shadow", "LoRA-Gating": "LoRA, gating"}

DOUBLE_COLUMN_IN = 7.2          # 183 mm, the common double-column width
Z95 = 1.959963984540054


def style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans",
                            "DejaVu Sans"],
        "font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.6,
        "axes.labelcolor": INK, "text.color": INK,
        "xtick.color": INK_2, "ytick.color": INK_2,
        "xtick.major.size": 0, "ytick.major.size": 2.5,
        "ytick.major.width": 0.6,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": False, "hatch.linewidth": 0.6,
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    })


def _ygrid(ax) -> None:
    ax.yaxis.grid(True, color=GRID, linewidth=0.5, linestyle="-")
    ax.set_axisbelow(True)


def _xgrid(ax) -> None:
    ax.xaxis.grid(True, color=GRID, linewidth=0.5, linestyle="-")
    ax.set_axisbelow(True)


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def wilson(k: int, n: int, z: float = Z95) -> Tuple[float, float, float]:
    """Proportion with a Wilson score interval (Wilson, 1927).

    Unlike the normal approximation it stays inside [0, 1] and keeps nonzero
    width at 0% and 100% -- exactly where an ablation's arms tend to sit.
    """
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_mean_ci(values: Sequence[float], n_boot: int = 10_000,
                      seed: int = 0) -> Tuple[float, float, float]:
    """Mean with a percentile bootstrap 95% interval.

    Scores are bounded at 100 and pile up there, so a t-interval's symmetry
    assumption does not hold. Seeded, so the figure is reproducible.
    """
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return float("nan"), float("nan"), float("nan")
    if x.size == 1 or np.all(x == x[0]):
        return float(x.mean()), float(x.mean()), float(x.mean())
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n_boot, x.size), replace=True).mean(axis=1)
    return float(x.mean()), float(np.percentile(means, 2.5)), \
        float(np.percentile(means, 97.5))


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def load(paths: Sequence[Path]) -> Dict[str, List[Dict[str, str]]]:
    rows: List[Dict[str, str]] = []
    for path in paths:
        rows.extend(read_rows(path))
    by_arm: Dict[str, List[Dict[str, str]]] = {arm: [] for arm in ARMS}
    for row in latest_ok(rows).values():
        if row["arm"] in by_arm:
            by_arm[row["arm"]].append(row)
    return {arm: group for arm, group in by_arm.items() if group}


def _approved(row) -> bool:
    return str(row["approved"]).strip().lower() == "true"


def _failed(row, rule: str) -> bool:
    return int(row[f"{rule.lower()}_violations"]) > 0


def summarise(by_arm) -> List[Dict[str, object]]:
    out = []
    for arm, group in by_arm.items():
        n = len(group)
        violated = sum(not _approved(r) for r in group)
        scores = [float(r["score"]) for r in group]
        iters = [int(r["iterations"]) for r in group]
        entry = {
            "arm": arm, "n": n,
            "violation": wilson(violated, n),
            "score_mean": float(np.mean(scores)),
            "score_sd": float(np.std(scores, ddof=1)) if n > 1 else 0.0,
            "score_median": float(np.median(scores)),
            "score_ci": bootstrap_mean_ci(scores),
            "iter_mean": float(np.mean(iters)),
            "iter_median": float(np.median(iters)),
            "approved": wilson(n - violated, n),
        }
        for rule in RULES:
            entry[rule] = wilson(sum(_failed(r, rule) for r in group), n)
        out.append(entry)
    return out


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def _bar_style(arm: str) -> dict:
    variant, mode = ARMS[arm]
    colour = GENERATOR_COLOUR[variant]
    if mode == "shadow":
        # Light tint of the same hue, hatched in the hue itself: two
        # channels, so the mode reads in colour and in greyscale.
        tint = matplotlib.colors.to_rgba(colour, 0.22)
        return dict(facecolor=tint, edgecolor=colour, hatch="////",
                    linewidth=0.0)
    return dict(facecolor=colour, edgecolor=colour, linewidth=0.0)


def _legend_handles(summary) -> List[Patch]:
    return [Patch(label=f"{ARM_LABELS[s['arm']]} (n={s['n']})",
                  **_bar_style(s["arm"])) for s in summary]


def _stub_note(fig, stub: bool) -> None:
    if stub:
        # Below the deepest tick labels (three lines on the violation plot).
        fig.text(0.0, -0.12, "Stub generator: base and LoRA are identical by "
                 "construction. Plumbing data, not results.",
                 fontsize=7, color=UNAPPROVED, ha="left", va="top")


def figure_violation_rates(summary, out: Path, formats, dpi, stub) -> List[Path]:
    groups = ["any"] + list(RULES)
    labels = ["Any rule\n(released\nunapproved)"] + [
        RULE_LABELS[r].replace(" ", "\n", 1) for r in RULES]
    n_arms = len(summary)
    step = 0.8 / max(n_arms, 1)
    width = step * 0.86                      # the remainder is the gap

    fig, ax = plt.subplots(figsize=(DOUBLE_COLUMN_IN, 2.6))
    # Separate the headline group from the per-rule breakdown.
    x = np.array([0.0] + [1.35 + i for i in range(len(RULES))])

    for i, s in enumerate(summary):
        xs = x - 0.4 + step * (i + 0.5)
        stats = [s["violation"]] + [s[r] for r in RULES]
        p = np.array([v[0] for v in stats]) * 100
        lo = np.array([v[1] for v in stats]) * 100
        hi = np.array([v[2] for v in stats]) * 100
        ax.bar(xs, p, width=width, **_bar_style(s["arm"]), zorder=2)
        ax.errorbar(xs, p, yerr=[p - lo, hi - p], fmt="none",
                    ecolor=INK_2, elinewidth=0.6, capsize=1.6,
                    capthick=0.6, zorder=3)
        # No value labels. At the bar tip a label collides with the
        # whisker; above the whisker it reads as the interval's top -- a
        # 0% bar with a CI to 49% looked like ~50%. The table carries
        # every value with its interval.

    ax.axvline(0.675, color=GRID, linewidth=0.6, zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 104)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("Runs with violation on the released scene (%)")
    ax.set_xlim(-0.5, x[-1] + 0.5)
    _ygrid(ax)
    ax.legend(handles=_legend_handles(summary), loc="lower center",
              bbox_to_anchor=(0.5, 1.0), ncol=4, frameon=False,
              handlelength=1.6, columnspacing=1.6)
    _stub_note(fig, stub)
    return _save(fig, out / "fig_violation_rates", formats, dpi)


def figure_scores_iterations(by_arm, summary, out: Path, formats, dpi,
                             stub) -> List[Path]:
    fig, (ax_a, ax_b) = plt.subplots(
        1, 2, figsize=(DOUBLE_COLUMN_IN, 2.5),
        gridspec_kw={"width_ratios": [1.0, 1.15], "wspace": 0.42})
    arms = [s["arm"] for s in summary]
    rng = np.random.default_rng(7)               # jitter, reproducible

    # (a) every run's score, then the mean and its bootstrap interval
    for i, arm in enumerate(arms):
        variant, mode = ARMS[arm]
        colour = GENERATOR_COLOUR[variant]
        scores = np.array([float(r["score"]) for r in by_arm[arm]])
        jitter = rng.uniform(-0.16, 0.16, scores.size)
        # Hollow for shadow, filled for gating: the same mode encoding as
        # the hatching in the other figure.
        ax_a.scatter(i + jitter, scores, s=9,
                     facecolor="white" if mode == "shadow" else colour,
                     edgecolor=colour, linewidth=0.7, alpha=0.75, zorder=2)
        mean, lo, hi = summary[i]["score_ci"]
        ax_a.errorbar(i + 0.32, mean, yerr=[[mean - lo], [hi - mean]],
                      fmt="o", markersize=4.5, color=INK, ecolor=INK,
                      elinewidth=0.8, capsize=2, capthick=0.8, zorder=3)
    lowest = min(float(r["score"]) for g in by_arm.values() for r in g)
    ax_a.set_ylim(max(0.0, math.floor((lowest - 5) / 5) * 5), 101.5)
    ax_a.set_xticks(range(len(arms)))
    ax_a.set_xticklabels([ARM_LABELS[a].replace(", ", "\n") for a in arms])
    ax_a.set_xlim(-0.6, len(arms) - 0.4)
    ax_a.set_ylabel("Plausibility score")
    _ygrid(ax_a)
    ax_a.set_title("a  Plausibility score per run", loc="left",
                   fontsize=8, fontweight="bold", color=INK, pad=6)
    ax_a.text(1.0, -0.30, "Dots: runs.  Black: mean, bootstrap 95% CI.",
              transform=ax_a.transAxes, ha="right", fontsize=6.5,
              color=INK_2)

    # (b) where each arm's runs ended: approved at iteration k, or released
    categories = [("Approved, iteration 1", ITERATION_COLOURS[0], 1),
                  ("Approved, iteration 2", ITERATION_COLOURS[1], 2),
                  ("Approved, iteration 3", ITERATION_COLOURS[2], 3),
                  ("Released unapproved", UNAPPROVED, None)]
    y = np.arange(len(arms))[::-1]
    for row, arm in zip(y, arms):
        group = by_arm[arm]
        n = len(group)
        left = 0.0
        for label, colour, k in categories:
            if k is None:
                count = sum(not _approved(r) for r in group)
            else:
                count = sum(_approved(r) and int(r["iterations"]) == k
                            for r in group)
            share = 100.0 * count / n
            if share <= 0:
                continue
            # White edge = the surface gap between touching segments.
            ax_b.barh(row, share, left=left, height=0.55, color=colour,
                      edgecolor="white", linewidth=1.0, zorder=2)
            if share >= 9:
                lum = np.dot(matplotlib.colors.to_rgb(colour),
                             (0.2126, 0.7152, 0.0722))
                ax_b.text(left + share / 2, row, f"{share:.0f}%",
                          ha="center", va="center", fontsize=6.5,
                          color=INK if lum > 0.55 else "white")
            left += share
    ax_b.set_yticks(y)
    ax_b.set_yticklabels([ARM_LABELS[a] for a in arms])
    ax_b.tick_params(axis="y", length=0)
    ax_b.set_xlim(0, 100)
    ax_b.set_xticks(range(0, 101, 25))
    ax_b.set_xlabel("Share of runs (%)")
    _xgrid(ax_b)
    ax_b.set_title("b  Iterations to approval", loc="left", fontsize=8,
                   fontweight="bold", color=INK, pad=6)
    ax_b.legend(handles=[Patch(facecolor=c, edgecolor="white", label=l)
                         for l, c, _ in categories],
                loc="upper center", bbox_to_anchor=(0.45, -0.24), ncol=2,
                frameon=False, handlelength=1.2, columnspacing=1.2)
    _stub_note(fig, stub)
    return _save(fig, out / "fig_scores_iterations", formats, dpi)


def _save(fig, stem: Path, formats, dpi) -> List[Path]:
    stem.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for fmt in formats:
        path = stem.with_suffix(f".{fmt}")
        fig.savefig(path, dpi=dpi, facecolor="white",
                    metadata={"Creator": None} if fmt == "pdf" else None)
        paths.append(path)
    plt.close(fig)
    return paths


# --------------------------------------------------------------------------
# Table
# --------------------------------------------------------------------------

def _pct(stat) -> str:
    p, lo, hi = stat
    return f"{100 * p:.0f} [{100 * lo:.0f}, {100 * hi:.0f}]"


def write_table(summary, out: Path, stub: bool) -> List[Path]:
    header = ["Arm", "n", "Violation % [95% CI]", "Score mean (SD)",
              "Score median", "Iterations mean (median)", "Approved %"] + \
             [f"{r} fail %" for r in RULES]
    rows = []
    for s in summary:
        rows.append([ARM_LABELS[s["arm"]], str(s["n"]), _pct(s["violation"]),
                     f"{s['score_mean']:.1f} ({s['score_sd']:.1f})",
                     f"{s['score_median']:.1f}",
                     f"{s['iter_mean']:.2f} ({s['iter_median']:.0f})",
                     f"{100 * s['approved'][0]:.0f}"] +
                    [f"{100 * s[r][0]:.0f}" for r in RULES])

    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "table_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)

    md_path = out / "table_summary.md"
    md = ["| " + " | ".join(header) + " |",
          "|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|"]
    md += ["| " + " | ".join(r) + " |" for r in rows]
    if stub:
        md.append("\n*Stub generator: plumbing data, not results.*")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    # booktabs tabular, ready for \input{} inside a table environment.
    def tex(cell: str) -> str:
        return cell.replace("%", r"\%").replace("[", "{[}").replace("]", "{]}")
    tex_path = out / "table_summary.tex"
    lines = [
        "% Generated by backend/experiments/plot_benchmarks.py",
        "% Requires \\usepackage{booktabs}. Intervals: Wilson 95%.",
        "\\begin{tabular}{l" + "r" * (len(header) - 1) + "}",
        "\\toprule",
        " & ".join(tex(h) for h in header) + " \\\\",
        "\\midrule",
    ]
    lines += [" & ".join(tex(c) for c in r) + " \\\\" for r in rows]
    lines += ["\\bottomrule", "\\end{tabular}"]
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [tex_path, csv_path, md_path]


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="+", type=Path,
                    help="ablation CSV(s) from run_ablation.py")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--formats", default="pdf,png",
                    help="comma list, e.g. pdf,png,svg")
    ap.add_argument("--dpi", type=int, default=300,
                    help="raster resolution; PDF and SVG are vector")
    args = ap.parse_args()

    missing = [p for p in args.csv if not p.is_file()]
    if missing:
        sys.exit(f"not found: {missing}")
    by_arm = load(args.csv)
    if not by_arm:
        sys.exit("No status=ok rows in the input; nothing to plot.")
    stub = any(r["generator"] == "stub" for g in by_arm.values() for r in g)
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]

    style()
    summary = summarise(by_arm)
    written = []
    written += figure_violation_rates(summary, args.out, formats, args.dpi,
                                      stub)
    written += figure_scores_iterations(by_arm, summary, args.out, formats,
                                        args.dpi, stub)
    written += write_table(summary, args.out, stub)

    print(f"{sum(s['n'] for s in summary)} runs across {len(summary)} arm(s).")
    if stub:
        print("WARNING: stub generator rows. These figures check the "
              "plotting, not the science.")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
