"""Placement strategies shared by joint generators (docs/02_build_brief.md §2.3).

All coordinates are in an interface's (u, v) frame.
"""

from __future__ import annotations

import math

from stl_slicer.core.geometry import Region2D
from stl_slicer.core.models import Placement

__all__ = ["grid_placements", "strip_placements"]

_EPS = 1e-9


def _centred(lo: float, hi: float, spacing: float) -> list[float]:
    """`floor(width/spacing)+1` positions `spacing` apart, centred on (lo+hi)/2."""
    width = hi - lo
    n = max(1, math.floor(width / spacing + _EPS) + 1)
    centre = (lo + hi) / 2
    return [centre + (i - (n - 1) / 2) * spacing for i in range(n)]


def grid_placements(region: Region2D, footprint: Region2D, spacing: float) -> list[Placement]:
    """Centred grid over the bounds of `region`; keep positions whose translated footprint lies
    inside `region`. Falls back to the region's deepest point when no grid position fits."""
    if region.is_empty or footprint.is_empty:
        return []
    if spacing <= 0:
        raise ValueError(f"spacing must be > 0, got {spacing}")
    u0, v0, u1, v1 = region.bounds
    out = [
        Placement(u=u, v=v)
        for u in _centred(u0, u1, spacing)
        for v in _centred(v0, v1, spacing)
        if region.contains(footprint.translate(u, v))
    ]
    if out:
        return out
    p = region.deepest_point()
    if p is not None and region.contains(footprint.translate(p[0], p[1])):
        return [Placement(u=p[0], v=p[1])]
    return []


def _u_runs(region: Region2D) -> list[tuple[float, float]]:
    """Merged u-intervals of the region's components' bounds."""
    intervals = sorted((c.bounds[0], c.bounds[2]) for c in region.components())
    runs: list[tuple[float, float]] = []
    for lo, hi in intervals:
        if runs and lo <= runs[-1][1]:
            runs[-1] = (runs[-1][0], max(runs[-1][1], hi))
        else:
            runs.append((lo, hi))
    return runs


def strip_placements(region: Region2D, half_width: float, spacing: float) -> list[Placement]:
    """Positions along u whose strip `[u - hw, u + hw]` lies within the u-projection of
    `region`, as a centred pattern with `spacing`; v is the centre of the region bounds.
    Falls back to the midpoint of the widest u-run when no pattern position fits."""
    if region.is_empty:
        return []
    if spacing <= 0:
        raise ValueError(f"spacing must be > 0, got {spacing}")
    runs = _u_runs(region)
    if not runs:
        return []
    u0, v0, u1, v1 = region.bounds
    v = (v0 + v1) / 2
    hw = float(half_width)

    def fits(u: float) -> bool:
        return any(lo - _EPS <= u - hw and u + hw <= hi + _EPS for lo, hi in runs)

    usable = (u1 - u0) - 2 * hw
    out: list[Placement] = []
    if usable >= -_EPS:
        n = math.floor(max(usable, 0.0) / spacing + _EPS) + 1
        centre = (u0 + u1) / 2
        us = [centre + (i - (n - 1) / 2) * spacing for i in range(n)]
        out = [Placement(u=u, v=v) for u in us if fits(u)]
    if out:
        return out
    lo, hi = max(runs, key=lambda r: r[1] - r[0])
    if 2 * hw <= hi - lo + _EPS:
        return [Placement(u=(lo + hi) / 2, v=v)]
    return []
