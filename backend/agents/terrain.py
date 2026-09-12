"""Deterministic terrain analysis: depression filling, D8 flow routing,
flow accumulation and stream-network extraction.

This is the geometry half of the Intervention-Planner. The LLM decides WHAT to
build and roughly where in the landscape; this module decides WHICH PIXELS,
using only the DEM. Keeping pixel selection deterministic means the critic
ablation is reproducible and a hallucinated coordinate can never reach the
generator.

All routines operate on the 10 m resampled Copernicus DEM in a metric CRS, so
distances and cell areas are in metres.
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import ndimage

# 8-connected neighbourhood, clockwise from north.
NEIGHBOURS: Tuple[Tuple[int, int], ...] = (
    (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1),
)
# Euclidean step length in cells for each neighbour (diagonals are sqrt(2)).
STEP_LENGTH = np.array([1.0, np.sqrt(2), 1.0, np.sqrt(2),
                        1.0, np.sqrt(2), 1.0, np.sqrt(2)], dtype=np.float32)


def fill_depressions(dem: np.ndarray, epsilon: float = 1e-4) -> np.ndarray:
    """Priority-flood depression filling with an epsilon gradient
    (Barnes, Lehman & Mulla 2014, the "Priority-Flood + epsilon" variant).

    Sinks stall flow routing and leave a disconnected stream network. Plain
    filling raises each sink to exactly its spill elevation, which trades the
    sink for a perfectly FLAT surface -- and a flat cell has zero drop, so D8
    still cannot route across it. On a 30 m DEM resampled to 10 m that is
    fatal: bilinear resampling already produces large runs of equal-valued
    cells, and without epsilon roughly half the grid ends up with no defined
    downstream neighbour, capping flow accumulation at single digits.

    Adding `epsilon` per step imposes a monotonic downhill path across filled
    flats toward the outlet. At 1e-4 m even a 1000-cell flat accrues 0.1 m,
    far below the DEM's own vertical error.
    """
    dem = np.asarray(dem, dtype=np.float64)
    h, w = dem.shape
    filled = np.empty_like(dem)
    closed = np.zeros((h, w), dtype=bool)
    queue: List[Tuple[float, int, int]] = []

    # Seed with the domain boundary -- flow must exit somewhere.
    for i in range(h):
        for j in (0, w - 1):
            heapq.heappush(queue, (dem[i, j], i, j))
            closed[i, j] = True
            filled[i, j] = dem[i, j]
    for j in range(1, w - 1):
        for i in (0, h - 1):
            heapq.heappush(queue, (dem[i, j], i, j))
            closed[i, j] = True
            filled[i, j] = dem[i, j]

    while queue:
        elev, i, j = heapq.heappop(queue)
        for di, dj in NEIGHBOURS:
            ni, nj = i + di, j + dj
            if 0 <= ni < h and 0 <= nj < w and not closed[ni, nj]:
                closed[ni, nj] = True
                # +epsilon, so a filled flat still slopes toward its outlet.
                filled[ni, nj] = max(dem[ni, nj], elev + epsilon)
                heapq.heappush(queue, (filled[ni, nj], ni, nj))

    return filled.astype(np.float32)


def d8_flow_direction(filled: np.ndarray, cell_size: float) -> np.ndarray:
    """Index (0-7) of the steepest-descent neighbour, or -1 where undefined.

    Vectorised over the 8 candidate directions rather than looping pixels.
    """
    h, w = filled.shape
    best_slope = np.full((h, w), -np.inf, dtype=np.float32)
    direction = np.full((h, w), -1, dtype=np.int8)

    for k, (di, dj) in enumerate(NEIGHBOURS):
        shifted = np.full((h, w), np.nan, dtype=np.float32)
        # Source slice receives the neighbour's elevation.
        si = slice(max(0, -di), h - max(0, di))
        sj = slice(max(0, -dj), w - max(0, dj))
        ti = slice(max(0, di), h - max(0, -di))
        tj = slice(max(0, dj), w - max(0, -dj))
        shifted[si, sj] = filled[ti, tj]

        drop = (filled - shifted) / (STEP_LENGTH[k] * cell_size)
        better = np.isfinite(drop) & (drop > best_slope)
        best_slope[better] = drop[better]
        direction[better] = k

    # A non-positive drop means flat or a pit: no defined downstream cell.
    direction[best_slope <= 0] = -1
    return direction


def flow_accumulation(direction: np.ndarray, filled: np.ndarray) -> np.ndarray:
    """Number of upstream cells draining through each cell.

    Processes cells in descending elevation so every donor is handled before
    its receiver -- a single O(n log n) pass, no iteration to convergence.
    """
    h, w = direction.shape
    n = h * w
    acc = np.ones(n, dtype=np.float64)

    flat_dir = direction.ravel()
    receiver = np.full(n, -1, dtype=np.int64)
    rows, cols = np.divmod(np.arange(n), w)
    for k, (di, dj) in enumerate(NEIGHBOURS):
        sel = flat_dir == k
        if not np.any(sel):
            continue
        ni = rows[sel] + di
        nj = cols[sel] + dj
        valid = (ni >= 0) & (ni < h) & (nj >= 0) & (nj < w)
        idx = np.where(sel)[0][valid]
        receiver[idx] = ni[valid] * w + nj[valid]

    order = np.argsort(filled.ravel(), kind="stable")[::-1]
    for idx in order:
        tgt = receiver[idx]
        if tgt >= 0:
            acc[tgt] += acc[idx]

    return acc.reshape(h, w).astype(np.float32)


def extract_streams(accumulation: np.ndarray,
                    threshold_cells: int = 400) -> np.ndarray:
    """Boolean stream network: cells draining more than `threshold_cells`.

    At 10 m resolution 400 cells is a 4 ha contributing area -- roughly the
    scale at which an ephemeral nala becomes visible in Sentinel-2.
    """
    return np.asarray(accumulation) >= threshold_cells


def analyse(dem: np.ndarray, cell_size: float = 10.0,
            stream_threshold: int = 400) -> Dict[str, np.ndarray]:
    """Run the full terrain chain and return every intermediate product."""
    filled = fill_depressions(dem)
    direction = d8_flow_direction(filled, cell_size)
    accumulation = flow_accumulation(direction, filled)
    streams = extract_streams(accumulation, stream_threshold)
    return {
        "filled": filled,
        "direction": direction,
        "accumulation": accumulation,
        "streams": streams,
    }


def select_dam_sites(
    streams: np.ndarray,
    accumulation: np.ndarray,
    slope: np.ndarray,
    elevation: np.ndarray,
    count: int,
    max_site_slope_deg: float = 5.0,
    min_spacing_m: float = 300.0,
    cell_size: float = 10.0,
    border_margin_m: float = 400.0,
) -> List[Dict[str, float]]:
    """Pick `count` check-dam sites along the main stem.

    Candidates must sit on the stream network and on ground flatter than
    `max_site_slope_deg` (spec section 3.2, Node 2). Sites are taken in order
    of descending contributing area -- the largest channels first -- subject to
    a minimum spacing so a "series of check-dams" is actually a series and not
    a cluster on one pixel.

    `border_margin_m` excludes a frame around the tile. Flow accumulation is
    maximal exactly where flow LEAVES the domain, so ranking by raw
    accumulation otherwise always sites the first dam on the boundary pixel --
    an artifact of the analysis window, not a feature of the watershed. Such a
    site also has its impoundment clipped by the tile edge and a contributing
    area equal to the whole scene, which is meaningless.
    """
    h, w = streams.shape
    margin = int(round(border_margin_m / cell_size))
    interior = np.zeros((h, w), dtype=bool)
    if 2 * margin < min(h, w):
        interior[margin:h - margin, margin:w - margin] = True
    else:  # tile too small to trim; fall back to the full extent
        interior[:] = True

    candidates = (streams & interior & (slope < max_site_slope_deg)
                  & np.isfinite(elevation))
    if not np.any(candidates):
        return []

    rows, cols = np.nonzero(candidates)
    scores = accumulation[rows, cols]
    order = np.argsort(scores)[::-1]

    min_spacing_cells = min_spacing_m / cell_size
    chosen: List[Dict[str, float]] = []
    for idx in order:
        r, c = int(rows[idx]), int(cols[idx])
        if any((r - s["row"]) ** 2 + (c - s["col"]) ** 2 < min_spacing_cells ** 2
               for s in chosen):
            continue
        chosen.append({
            "row": r,
            "col": c,
            "elevation_m": float(elevation[r, c]),
            "slope_deg": float(slope[r, c]),
            "contributing_cells": float(accumulation[r, c]),
            "contributing_area_ha": float(accumulation[r, c] * cell_size ** 2 / 10_000.0),
        })
        if len(chosen) >= count:
            break
    return chosen


def impoundment_mask(
    sites: List[Dict[str, float]],
    filled: np.ndarray,
    accumulation: np.ndarray,
    impound_height_m: float = 3.0,
    max_radius_m: float = 400.0,
    cell_size: float = 10.0,
    stream_threshold: int = 400,
    slope: Optional[np.ndarray] = None,
    max_water_slope_deg: float = 2.5,
) -> np.ndarray:
    """Water surface that forms behind each dam.

    A check-dam ponds water upstream up to its crest height. Approximated as
    the connected set of cells that are (a) within `max_radius_m` of the dam,
    (b) no higher than crest elevation, and (c) part of the channel network
    rather than adjacent hillside.

    The channel gate is `min(10% of the dam's own contributing area, the
    stream-network threshold)`. Keying it purely to the dam's own accumulation
    fails on a main stem: at 106k contributing cells a 5% gate admits only the
    trunk line itself, yielding a 3-pixel "reservoir". Capping the gate at the
    stream threshold lets the pool back up the mapped channel the way water
    actually does, while still refusing to climb the hillslope.

    max_radius_m is 400 m because on the 0.7 deg valley floors here a 3 m
    crest backs water up roughly 3/tan(0.7 deg) = 245 m, and a tighter cap
    would clip the pool before physics does.
    """
    if not sites:
        return np.zeros(filled.shape, dtype=bool)

    h, w = filled.shape
    pooled = np.zeros((h, w), dtype=bool)
    radius_cells = int(round(max_radius_m / cell_size))
    yy, xx = np.mgrid[0:h, 0:w]

    for site in sites:
        r, c = int(site["row"]), int(site["col"])
        crest = filled[r, c] + impound_height_m
        near = (yy - r) ** 2 + (xx - c) ** 2 <= radius_cells ** 2
        below_crest = filled <= crest
        # Require a real channel, so the pool follows the valley rather than
        # spreading as a disc across flat ground.
        channelised = accumulation >= min(0.10 * accumulation[r, c],
                                          float(stream_threshold))
        candidate = near & below_crest & channelised

        # Water cannot rest on ground steeper than the Critic's gravity
        # limit. Omitting this lets the Planner site pool cells that rule 1
        # will reject on every single iteration, so the feedback loop can
        # never converge -- the generator keeps being told to remove water
        # the planner keeps putting back. Planner and Critic must share the
        # same physics.
        if slope is not None:
            candidate &= np.asarray(slope) <= max_water_slope_deg

        # Keep only the blob physically connected to the dam. 8-connectivity
        # is required: ndimage.label defaults to a 4-neighbourhood, under
        # which a diagonal channel -- and the main nala here runs NE-SW -- is
        # not connected at all, so the pool collapses to a single pixel.
        labels, _ = ndimage.label(
            candidate, structure=ndimage.generate_binary_structure(2, 2))
        if labels[r, c] > 0:
            pooled |= labels == labels[r, c]
        else:
            pooled[r, c] = True

    return pooled


def buffer_mask(core: np.ndarray, radius_m: float,
                cell_size: float = 10.0) -> np.ndarray:
    """Cells within `radius_m` of `core` but not in it -- the riparian fringe."""
    if not np.any(core):
        return np.zeros(core.shape, dtype=bool)
    distance = ndimage.distance_transform_edt(~core) * cell_size
    return (distance <= radius_m) & ~core
