"""Cut planning: turn bounds + cell limits (+ optional explicit cuts) into a grid `CutPlan`.

Pure and deterministic; never touches a mesh. See docs/00_design.md §4.1.
"""

from __future__ import annotations

import itertools
import math

from stl_slicer.core.errors import PlanError
from stl_slicer.core.models import (
    Axis,
    AxisCuts,
    Bounds,
    Cell,
    CellIndex,
    CellLimits,
    CutInterface,
    CutPlan,
    PlaneFrame,
    RectEdge,
    SliceWarning,
    Vec3,
    WarningCode,
)

_AXES: tuple[Axis, Axis, Axis] = (Axis.X, Axis.Y, Axis.Z)
_TOL = 1e-9


def _unit(axis: Axis) -> Vec3:
    return (
        1.0 if axis is Axis.X else 0.0,
        1.0 if axis is Axis.Y else 0.0,
        1.0 if axis is Axis.Z else 0.0,
    )


def even_cuts(lo: float, hi: float, max_cell: float) -> list[float]:
    """Interior cut positions splitting [lo, hi] into n = ceil((hi-lo)/max_cell) equal cells."""
    if max_cell <= 0:
        raise PlanError(f"max_cell must be > 0, got {max_cell}")
    extent = hi - lo
    if extent <= 0:
        return []
    n = max(1, math.ceil(extent / max_cell - _TOL))
    if n <= 1:
        return []
    step = extent / n
    return [lo + step * i for i in range(1, n)]


def make_frame(axis: Axis, position: float, rect_center: Vec3) -> PlaneFrame:
    """Frame for a cut plane normal to +axis at `position`; origin is `rect_center` projected
    onto the plane. (u, v) are the cyclic next two axes, so u x v = normal."""
    u_axis, v_axis = axis.uv
    origin = list(rect_center)
    origin[axis.ordinal] = position
    return PlaneFrame(
        origin=(origin[0], origin[1], origin[2]),
        normal=_unit(axis),
        u=_unit(u_axis),
        v=_unit(v_axis),
    )


def _validate_cuts(axis: Axis, lo: float, hi: float, cuts: list[float], min_cell: float) -> None:
    name = axis.value
    for a, b in itertools.pairwise(cuts):
        if a == b:
            raise PlanError(f"duplicate cut at {a} on axis {name}")
        if a > b:
            raise PlanError(f"cuts on axis {name} are not sorted ascending: {cuts}")
    for c in cuts:
        if not lo < c < hi:
            raise PlanError(f"cut {c} on axis {name} is outside the open interval ({lo}, {hi})")
    edges = [lo, *cuts, hi]
    for a, b in itertools.pairwise(edges):
        if b - a < min_cell:
            raise PlanError(
                f"cells on axis {name} between {a} and {b} are thinner than "
                f"min_cell {min_cell} ({b - a:.4g} mm)"
            )


def plan_grid(bounds: Bounds, limits: CellLimits, cuts: AxisCuts | None = None) -> CutPlan:
    """Partition `bounds` into an axis-aligned grid of cells and the interfaces between them."""
    for axis in _AXES:
        if limits.max_cell[axis.ordinal] <= 0:
            raise PlanError(
                f"max_cell along {axis.value} must be > 0, got {limits.max_cell[axis.ordinal]}"
            )

    warnings: list[SliceWarning] = []
    per_axis: list[list[float]] = []
    for axis in _AXES:
        lo, hi = bounds.min[axis.ordinal], bounds.max[axis.ordinal]
        max_cell = limits.max_cell[axis.ordinal]
        if cuts is None:
            axis_cuts = even_cuts(lo, hi, max_cell)
        else:
            axis_cuts = list(cuts.for_axis(axis))
            _validate_cuts(axis, lo, hi, axis_cuts, limits.min_cell)
            for a, b in itertools.pairwise([lo, *axis_cuts, hi]):
                width = b - a
                if width > max_cell * (1 + _TOL):
                    warnings.append(
                        SliceWarning(
                            code=WarningCode.CELL_OVERSIZE,
                            message=(
                                f"cell along {axis.value} is {width:.2f} mm > max {max_cell:.2f} mm"
                            ),
                            subject=axis.value,
                        )
                    )
        per_axis.append(axis_cuts)

    edges = [[bounds.min[a.ordinal], *per_axis[a.ordinal], bounds.max[a.ordinal]] for a in _AXES]
    counts = [len(e) - 1 for e in edges]

    cells: list[Cell] = []
    for i, j, k in itertools.product(*(range(n) for n in counts)):
        lo3 = (edges[0][i], edges[1][j], edges[2][k])
        hi3 = (edges[0][i + 1], edges[1][j + 1], edges[2][k + 1])
        cells.append(Cell(index=CellIndex(i=i, j=j, k=k), bounds=Bounds(min=lo3, max=hi3)))

    interfaces: list[CutInterface] = []
    for axis in _AXES:
        a = axis.ordinal
        if counts[a] <= 1:
            continue
        u_axis, v_axis = axis.uv
        for other in (u_axis, v_axis):
            if bounds.extent(other) <= 0:
                raise PlanError(
                    f"bounds degenerate along {other.value}: cannot cut along {axis.value}"
                )
        others = [o for o in _AXES if o is not axis]  # ascending xyz order for iteration
        for c in range(counts[a] - 1):
            position = edges[a][c + 1]
            for oi, oj in itertools.product(
                range(counts[others[0].ordinal]), range(counts[others[1].ordinal])
            ):
                lower = [0, 0, 0]
                lower[a] = c
                lower[others[0].ordinal] = oi
                lower[others[1].ordinal] = oj
                upper = list(lower)
                upper[a] = c + 1
                lower_idx = CellIndex(i=lower[0], j=lower[1], k=lower[2])
                upper_idx = CellIndex(i=upper[0], j=upper[1], k=upper[2])

                center = [0.0, 0.0, 0.0]
                for o in others:
                    e = edges[o.ordinal]
                    n = lower[o.ordinal]
                    center[o.ordinal] = (e[n] + e[n + 1]) / 2
                center[a] = position
                u_i, v_i = lower[u_axis.ordinal], lower[v_axis.ordinal]
                eu, ev = edges[u_axis.ordinal], edges[v_axis.ordinal]
                interior: list[RectEdge] = []
                if u_i > 0:
                    interior.append("u_min")
                if u_i < counts[u_axis.ordinal] - 1:
                    interior.append("u_max")
                if v_i > 0:
                    interior.append("v_min")
                if v_i < counts[v_axis.ordinal] - 1:
                    interior.append("v_max")

                interfaces.append(
                    CutInterface(
                        id=f"{axis.value}{c}_{lower_idx.id}",
                        axis=axis,
                        position=position,
                        lower=lower_idx,
                        upper=upper_idx,
                        frame=make_frame(axis, position, (center[0], center[1], center[2])),
                        extent_u=eu[u_i + 1] - eu[u_i],
                        extent_v=ev[v_i + 1] - ev[v_i],
                        interior_edges=interior,
                    )
                )

    return CutPlan(
        bounds=bounds,
        limits=limits,
        cuts=AxisCuts(x=per_axis[0], y=per_axis[1], z=per_axis[2]),
        cells=cells,
        interfaces=interfaces,
        warnings=warnings,
    )
