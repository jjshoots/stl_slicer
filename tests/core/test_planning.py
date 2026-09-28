"""Tests for core.planning — contract items docs/00_design.md §4.1.1-6."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from stl_slicer.core.errors import PlanError
from stl_slicer.core.models import (
    Axis,
    AxisCuts,
    Bounds,
    CellIndex,
    CellLimits,
    CutPlan,
    WarningCode,
)
from stl_slicer.core.planning import even_cuts, make_frame, plan_grid

AXES = (Axis.X, Axis.Y, Axis.Z)
BOX = Bounds(min=(0, 0, 0), max=(100, 50, 20))
BIG = CellLimits(max_cell=(1000, 1000, 1000))


def _oversize(plan: CutPlan) -> list[str | None]:
    return [w.subject for w in plan.warnings if w.code is WarningCode.CELL_OVERSIZE]


# --- even_cuts -------------------------------------------------------------------------------


def test_even_cuts_exact_values() -> None:
    assert even_cuts(0, 100, 40) == pytest.approx([100 / 3, 200 / 3])


def test_even_cuts_exact_multiple_does_not_add_a_cell() -> None:
    assert even_cuts(0, 100, 25) == pytest.approx([25, 50, 75])


@pytest.mark.parametrize(("lo", "hi", "m"), [(0, 40, 40), (0, 10, 40), (5, 5, 1), (0, 1e-12, 1)])
def test_even_cuts_empty_when_extent_fits(lo: float, hi: float, m: float) -> None:
    assert even_cuts(lo, hi, m) == []


@pytest.mark.parametrize("m", [0.0, -1.0])
def test_even_cuts_rejects_non_positive_max_cell(m: float) -> None:
    with pytest.raises(PlanError):
        even_cuts(0, 100, m)


# --- property tests (auto path) --------------------------------------------------------------

extents = st.floats(min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False)
max_cells = st.floats(min_value=0.1, max_value=500, allow_nan=False, allow_infinity=False)
origins = st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False)


@st.composite
def auto_cases(draw: st.DrawFn) -> tuple[Bounds, CellLimits]:
    lo = tuple(draw(origins) for _ in range(3))
    ext = [draw(extents) for _ in range(3)]
    mc = tuple(draw(max_cells) for _ in range(3))
    # keep the grid small enough to be fast
    for a in range(3):
        if ext[a] / mc[a] > 12:
            ext[a] = mc[a] * 12
    hi = tuple(lo[a] + ext[a] for a in range(3))
    return Bounds(min=lo, max=hi), CellLimits(max_cell=mc, min_cell=0.01)


@given(auto_cases())
@settings(max_examples=100, deadline=None)
def test_even_cuts_properties(case: tuple[Bounds, CellLimits]) -> None:
    bounds, limits = case
    for a in AXES:
        lo, hi, m = bounds.min[a.ordinal], bounds.max[a.ordinal], limits.max_cell[a.ordinal]
        cuts = even_cuts(lo, hi, m)
        edges = [lo, *cuts, hi]
        assert edges == sorted(edges)
        assert all(b - a_ <= m * (1 + 1e-9) for a_, b in itertools.pairwise(edges))
        assert len(cuts) + 1 == max(1, math.ceil((hi - lo) / m - 1e-9))


@given(auto_cases())
@settings(max_examples=100, deadline=None)
def test_plan_grid_auto_properties(case: tuple[Bounds, CellLimits]) -> None:
    bounds, limits = case
    plan = plan_grid(bounds, limits)
    counts = []
    for a in AXES:
        o = a.ordinal
        cuts = plan.cuts.for_axis(a)
        lo, hi = bounds.min[o], bounds.max[o]
        boundaries = sorted(
            {c.bounds.min[o] for c in plan.cells} | {c.bounds.max[o] for c in plan.cells}
        )
        assert boundaries == [lo, *cuts, hi]  # exact tiling
        for c in plan.cells:
            assert c.bounds.max[o] - c.bounds.min[o] <= limits.max_cell[o] * (1 + 1e-9)
        n = max(1, math.ceil((hi - lo) / limits.max_cell[o] - 1e-9))
        assert len(cuts) + 1 == n
        counts.append(n)
    assert len(plan.cells) == math.prod(counts)
    expected_ifaces = sum(
        (counts[a] - 1) * math.prod(counts[b] for b in range(3) if b != a) for a in range(3)
    )
    assert len(plan.interfaces) == expected_ifaces
    assert not _oversize(plan)
    assert len({c.id for c in plan.cells}) == len(plan.cells)
    assert len({i.id for i in plan.interfaces}) == len(plan.interfaces)
    for iface in plan.interfaces:
        lo_t, up_t = iface.lower.as_tuple(), iface.upper.as_tuple()
        diff = [u - lo_ for lo_, u in zip(lo_t, up_t, strict=True)]
        expected = [0, 0, 0]
        expected[iface.axis.ordinal] = 1
        assert diff == expected


def test_plan_grid_is_deterministic() -> None:
    limits = CellLimits(max_cell=(30, 30, 30))
    assert plan_grid(BOX, limits) == plan_grid(BOX, limits)


def test_cells_ordered_and_ids() -> None:
    plan = plan_grid(BOX, CellLimits(max_cell=(50, 25, 20)))
    assert [c.id for c in plan.cells] == ["x0_y0_z0", "x0_y1_z0", "x1_y0_z0", "x1_y1_z0"]
    assert plan.cells[3].bounds == Bounds(min=(50, 25, 0), max=(100, 50, 20))
    assert plan.limits == CellLimits(max_cell=(50, 25, 20))


# --- limits / explicit cut validation --------------------------------------------------------


@pytest.mark.parametrize("mc", [(0, 10, 10), (10, -1, 10), (10, 10, 0)])
def test_non_positive_max_cell_component_raises(mc: tuple[float, float, float]) -> None:
    with pytest.raises(PlanError):
        plan_grid(BOX, CellLimits(max_cell=mc))


@pytest.mark.parametrize(
    "cuts",
    [
        AxisCuts(x=[60, 30]),  # unsorted
        AxisCuts(x=[30, 30]),  # duplicate
        AxisCuts(x=[0]),  # == min
        AxisCuts(x=[100]),  # == max
        AxisCuts(x=[150]),  # beyond max
        AxisCuts(y=[-5]),  # beyond min
        AxisCuts(x=[30, 30.5]),  # closer than min_cell to each other
    ],
    ids=["unsorted", "duplicate", "at-min", "at-max", "beyond-max", "beyond-min", "too-close"],
)
def test_invalid_explicit_cuts_raise(cuts: AxisCuts) -> None:
    with pytest.raises(PlanError):
        plan_grid(BOX, BIG, cuts)


@pytest.mark.parametrize("cuts", [AxisCuts(x=[0.5]), AxisCuts(x=[99.5]), AxisCuts(z=[19.9])])
def test_thin_explicit_cell_raises_plan_error_b2(cuts: AxisCuts) -> None:
    with pytest.raises(PlanError, match="min_cell"):
        plan_grid(BOX, CellLimits(max_cell=(1000, 1000, 1000), min_cell=1.0), cuts)


def test_gap_exactly_min_cell_is_allowed() -> None:
    plan = plan_grid(BOX, CellLimits(max_cell=(1000, 1000, 1000), min_cell=1.0), AxisCuts(x=[1, 2]))
    assert plan.cuts.x == [1, 2]


def test_wide_explicit_cell_warns_once_naming_axis() -> None:
    plan = plan_grid(BOX, CellLimits(max_cell=(60, 60, 60)), AxisCuts(x=[20]))
    assert _oversize(plan) == ["x"]
    (w,) = plan.warnings
    assert "x" in w.message and "80.00" in w.message and "60.00" in w.message


def test_explicit_cuts_equal_to_even_cuts_do_not_warn() -> None:
    limits = CellLimits(max_cell=(40, 30, 7))
    auto = plan_grid(BOX, limits)
    explicit = plan_grid(
        BOX,
        limits,
        AxisCuts(x=even_cuts(0, 100, 40), y=even_cuts(0, 50, 30), z=even_cuts(0, 20, 7)),
    )
    assert explicit.warnings == []
    assert explicit == auto


def test_explicit_empty_cuts_is_single_cell_and_may_warn_per_axis() -> None:
    plan = plan_grid(BOX, CellLimits(max_cell=(10, 10, 10)), AxisCuts())
    assert len(plan.cells) == 1
    assert plan.interfaces == []
    assert _oversize(plan) == ["x", "y", "z"]


def test_flat_bounds_single_cell_ok_but_degenerate_interface_raises() -> None:
    flat = Bounds(min=(0, 0, 0), max=(100, 50, 0))
    plan = plan_grid(flat, CellLimits(max_cell=(200, 200, 200)))
    assert len(plan.cells) == 1
    with pytest.raises(PlanError, match="degenerate"):
        plan_grid(flat, CellLimits(max_cell=(40, 200, 200)))


# --- cut-axis selection ----------------------------------------------------------------------

TALL = Bounds(min=(0, 0, 0), max=(100, 100, 300))


def test_excluded_axis_gets_no_cuts_and_warns_oversize() -> None:
    limits = CellLimits(max_cell=(60, 60, 60))
    plan = plan_grid(TALL, limits, axes=[Axis.X, Axis.Y])
    assert plan.cuts.z == []
    assert plan.cuts.x == pytest.approx([50.0]) and plan.cuts.y == pytest.approx([50.0])
    assert _oversize(plan) == ["z"]
    assert len(plan.cells) == 4
    assert all(c.bounds.min[2] == 0 and c.bounds.max[2] == 300 for c in plan.cells)
    assert {i.axis for i in plan.interfaces} == {Axis.X, Axis.Y}
    assert plan == plan_grid(TALL, limits, axes=[Axis.Y, Axis.X])  # order is irrelevant


def test_excluded_axis_within_max_cell_does_not_warn() -> None:
    plan = plan_grid(BOX, CellLimits(max_cell=(60, 60, 60)), axes=[Axis.X])
    assert plan.cuts.x == pytest.approx([50.0]) and plan.cuts.y == [] and plan.cuts.z == []
    assert plan.warnings == []


def test_axes_none_or_all_is_the_default() -> None:
    limits = CellLimits(max_cell=(30, 30, 30))
    assert plan_grid(BOX, limits, axes=None) == plan_grid(BOX, limits)
    assert plan_grid(BOX, limits, axes=AXES) == plan_grid(BOX, limits)


def test_explicit_cut_on_excluded_axis_raises() -> None:
    with pytest.raises(PlanError, match="excluded"):
        plan_grid(TALL, BIG, AxisCuts(z=[150]), axes=[Axis.X, Axis.Y])
    # an empty list on the excluded axis is fine (and still reports oversize)
    plan = plan_grid(TALL, CellLimits(max_cell=(200, 200, 200)), AxisCuts(x=[50]), axes=[Axis.X])
    assert plan.cuts.x == [50] and plan.cuts.z == []
    assert _oversize(plan) == ["z"]


@given(auto_cases(), st.sets(st.sampled_from(AXES)))
@settings(max_examples=100, deadline=None)
def test_plan_grid_axes_properties(case: tuple[Bounds, CellLimits], allowed: set[Axis]) -> None:
    bounds, limits = case
    plan = plan_grid(bounds, limits, axes=sorted(allowed))
    oversize = _oversize(plan)
    for a in AXES:
        o = a.ordinal
        cuts = plan.cuts.for_axis(a)
        lo, hi = bounds.min[o], bounds.max[o]
        boundaries = sorted(
            {c.bounds.min[o] for c in plan.cells} | {c.bounds.max[o] for c in plan.cells}
        )
        assert boundaries == [lo, *cuts, hi]  # exact tiling regardless of restriction
        if a in allowed:
            assert cuts == even_cuts(lo, hi, limits.max_cell[o])
            assert a.value not in oversize
        else:
            assert cuts == []
            assert (a.value in oversize) == (hi - lo > limits.max_cell[o] * (1 + 1e-9))
    assert all(i.axis in allowed for i in plan.interfaces)


# --- frames ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("axis", "normal", "u", "v"),
    [
        (Axis.X, (1, 0, 0), (0, 1, 0), (0, 0, 1)),
        (Axis.Y, (0, 1, 0), (0, 0, 1), (1, 0, 0)),
        (Axis.Z, (0, 0, 1), (1, 0, 0), (0, 1, 0)),
    ],
)
def test_make_frame_axes_and_handedness(
    axis: Axis, normal: tuple[int, int, int], u: tuple[int, int, int], v: tuple[int, int, int]
) -> None:
    f = make_frame(axis, 7.0, (1.0, 2.0, 3.0))
    assert f.normal == normal and f.u == u and f.v == v
    np.testing.assert_array_equal(np.cross(f.u, f.v), f.normal)
    expected_origin = [1.0, 2.0, 3.0]
    expected_origin[axis.ordinal] = 7.0
    assert list(f.origin) == expected_origin


def test_interface_frame_single_x_cut() -> None:
    plan = plan_grid(BOX, BIG, AxisCuts(x=[40]))
    (iface,) = plan.interfaces
    assert iface.id == "x0_x0_y0_z0"
    assert iface.axis is Axis.X and iface.position == 40
    assert iface.lower == CellIndex(i=0, j=0, k=0) and iface.upper == CellIndex(i=1, j=0, k=0)
    assert iface.frame.origin == (40, 25, 10)
    assert iface.frame.normal == (1, 0, 0)
    assert iface.extent_u == 50 and iface.extent_v == 20
    assert iface.interior_edges == []


def test_interface_origin_at_rect_centre_off_origin_bounds() -> None:
    b = Bounds(min=(-10, 5, 100), max=(10, 25, 130))
    plan = plan_grid(b, BIG, AxisCuts(y=[15], z=[110]))
    by_id = {i.id: i for i in plan.interfaces}
    y_iface = by_id["y0_x0_y0_z1"]  # y cut, upper-z row
    assert y_iface.frame.origin == (0, 15, 120)
    assert (y_iface.extent_u, y_iface.extent_v) == (20, 20)  # u=Z [110,130], v=X [-10,10]
    z_iface = by_id["z0_x0_y1_z0"]
    assert z_iface.frame.origin == (0, 20, 110)
    assert (z_iface.extent_u, z_iface.extent_v) == (20, 10)  # u=X, v=Y [15,25]


# --- interior edges and ids ------------------------------------------------------------------


def test_interior_edges_2x2x1() -> None:
    plan = plan_grid(BOX, BIG, AxisCuts(x=[50], y=[25]))
    by_id = {i.id: i for i in plan.interfaces}
    assert list(by_id) == ["x0_x0_y0_z0", "x0_x0_y1_z0", "y0_x0_y0_z0", "y0_x1_y0_z0"]
    assert by_id["x0_x0_y0_z0"].interior_edges == ["u_max"]
    assert by_id["x0_x0_y1_z0"].interior_edges == ["u_min"]
    # y interface: u = Z (one cell), v = X
    assert by_id["y0_x0_y0_z0"].interior_edges == ["v_max"]
    assert by_id["y0_x1_y0_z0"].interior_edges == ["v_min"]


def test_interior_edges_2x2x2_and_ordering() -> None:
    plan = plan_grid(BOX, BIG, AxisCuts(x=[50], y=[25], z=[10]))
    assert len(plan.cells) == 8
    assert len(plan.interfaces) == 12
    ids = [i.id for i in plan.interfaces]
    assert ids[:4] == ["x0_x0_y0_z0", "x0_x0_y0_z1", "x0_x0_y1_z0", "x0_x0_y1_z1"]
    assert [i.axis for i in plan.interfaces] == [Axis.X] * 4 + [Axis.Y] * 4 + [Axis.Z] * 4
    by_id = {i.id: i for i in plan.interfaces}
    # x interface, lower (0,1,0): u=Y index 1 -> u_min interior; v=Z index 0 -> v_max interior
    assert by_id["x0_x0_y1_z0"].interior_edges == ["u_min", "v_max"]
    assert by_id["x0_x0_y0_z1"].interior_edges == ["u_max", "v_min"]
    # z interface, lower (1,0,0): u=X index 1 -> u_min; v=Y index 0 -> v_max
    z = by_id["z0_x1_y0_z0"]
    assert z.interior_edges == ["u_min", "v_max"]
    assert z.upper == CellIndex(i=1, j=0, k=1)
    assert z.frame.origin == (75, 12.5, 10)


def test_interface_ids_multi_cut() -> None:
    plan = plan_grid(BOX, BIG, AxisCuts(x=[25, 50, 75]))
    assert [i.id for i in plan.interfaces] == ["x0_x0_y0_z0", "x1_x1_y0_z0", "x2_x2_y0_z0"]
    assert [i.position for i in plan.interfaces] == [25, 50, 75]
