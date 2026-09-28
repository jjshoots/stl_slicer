"""Tests for core.slicing — docs/00_design.md §3, §4.3 and docs/02_build_brief.md §2.4."""

from __future__ import annotations

import math

import pytest
from manifold3d import Manifold

from stl_slicer.core.errors import SliceInvariantError
from stl_slicer.core.geometry import Joint, LocalFrame, Mesh, Piece, Region2D
from stl_slicer.core.models import (
    AxisCuts,
    Bounds,
    CellIndex,
    CellLimits,
    CutInterface,
    CutPlan,
    MaleSide,
    PieceInfo,
    Placement,
    WarningCode,
)
from stl_slicer.core.planning import plan_grid
from stl_slicer.core.slicing import (
    carve,
    check_pieces,
    contact_regions,
    joint_cells,
    male_female,
)

REL = 1e-6
RADIUS, CLEARANCE = 4.0, 0.15
# Just inside a region inset from an edge: dowel radius + clearance + a hair.
EDGE_STANDOFF = RADIUS + CLEARANCE + 0.01


def make_dowel_joint(
    interface: CutInterface,
    male: CellIndex,
    female: CellIndex,
    u: float,
    v: float,
    radius: float = RADIUS,
    depth: float = 6.0,
    clearance: float = CLEARANCE,
) -> Joint:
    local = LocalFrame(interface.frame)
    prof = Region2D.circle(radius, 32).translate(u, v)
    m = local.extrude(prof, 0.0, depth)
    f = local.extrude(
        Region2D.circle(radius, 32).offset(clearance).translate(u, v),
        -clearance,
        depth + clearance,
    )
    if female == interface.lower:  # female side is local -z: mirror
        m = m.mirror([0, 0, 1])
        f = f.mirror([0, 0, 1])
    m, f = local.to_world(m), local.to_world(f)
    return Joint(
        interface.id, "dowel", male, female, Placement(u=u, v=v), m, f, f.volume() - m.volume()
    )


def _box_mesh(lo: tuple[float, float, float], hi: tuple[float, float, float]) -> Mesh:
    size = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    center = ((hi[0] + lo[0]) / 2, (hi[1] + lo[1]) / 2, (hi[2] + lo[2]) / 2)
    return Mesh.box(size, center)


def _cube(plan: CutPlan, index: CellIndex) -> Manifold:
    b = plan.cell(index).bounds
    return Manifold.cube(list(b.size)).translate(list(b.min))


def _plan_2x1() -> tuple[Mesh, CutPlan]:
    mesh = _box_mesh((0, 0, 0), (100, 100, 100))
    plan = plan_grid(
        Bounds(min=(0, 0, 0), max=(100, 100, 100)),
        CellLimits(max_cell=(100, 100, 100)),
        AxisCuts(x=[50]),
    )
    return mesh, plan


def _plan_2x2() -> tuple[Mesh, CutPlan]:
    mesh = _box_mesh((0, 0, 0), (100, 100, 100))
    plan = plan_grid(Bounds(min=(0, 0, 0), max=(100, 100, 100)), CellLimits(max_cell=(50, 50, 100)))
    return mesh, plan


def _idx(i: int, j: int, k: int) -> CellIndex:
    return CellIndex(i=i, j=j, k=k)


# --- male_female ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "male_is_lower"), [(MaleSide.LOWER, True), (MaleSide.UPPER, False)]
)
def test_male_female(rule: MaleSide, male_is_lower: bool) -> None:
    _, plan = _plan_2x1()
    iface = plan.interfaces[0]
    male, female = male_female(iface, rule)
    if male_is_lower:
        assert (male, female) == (iface.lower, iface.upper)
    else:
        assert (male, female) == (iface.upper, iface.lower)


# --- contact_regions -----------------------------------------------------------------------------


def test_contact_region_full_face_single_cut() -> None:
    mesh, plan = _plan_2x1()
    regions = contact_regions(mesh, plan, edge_inset=0)
    assert set(regions) == {i.id for i in plan.interfaces}
    iface = plan.interfaces[0]
    region = regions[iface.id]
    assert region.area == pytest.approx(100 * 100, rel=REL)
    assert region.bounds == pytest.approx(iface.rect, abs=1e-6)


def test_contact_region_inset_only_on_interior_edges() -> None:
    mesh, plan = _plan_2x2()
    regions = contact_regions(mesh, plan, edge_inset=6.15)
    x_ifaces = [i for i in plan.interfaces if i.axis.value == "x"]
    assert len(x_ifaces) == 2
    for iface in x_ifaces:
        u0, v0, u1, v1 = regions[iface.id].bounds
        assert u1 - u0 == pytest.approx(50 - 6.15, abs=1e-6)
        assert v1 - v0 == pytest.approx(100, abs=1e-6)
        assert regions[iface.id].area == pytest.approx((50 - 6.15) * 100, rel=REL)


@pytest.mark.parametrize(
    ("step_parts", "naive_area"),
    [
        # Wide box below, narrow box above: A's top-right face is coplanar with z=50.
        ((((0, 0, 0), (100, 100, 50)), ((0, 0, 50), (50, 100, 100))), 5000.0),
        # Narrow box below, wide box above: B's bottom-right face is coplanar with z=50.
        ((((0, 0, 50), (100, 100, 100)), ((0, 0, 0), (50, 100, 50))), 10000.0),
    ],
    ids=["coplanar_top_face", "coplanar_bottom_face"],
)
def test_coplanar_face_does_not_overstate_contact_m18(
    step_parts: tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...],
    naive_area: float,
) -> None:
    step = Mesh.union_all(_box_mesh(lo, hi) for lo, hi in step_parts)
    plan = plan_grid(
        Bounds(min=(0, 0, 0), max=(100, 100, 100)),
        CellLimits(max_cell=(100, 100, 100)),
        AxisCuts(z=[50]),
    )
    (iface,) = plan.interfaces
    region = contact_regions(step, plan, edge_inset=0)[iface.id]
    assert region.area == pytest.approx(50 * 100, rel=REL)
    # manifold3d slices half-open: a face coplanar with the plane counts when the solid lies
    # above it. So the naive single slice is right for a coplanar top face but reports the full
    # 100x100 for a coplanar bottom face; the slice(-eps) & slice(+eps) version is right for both.
    naive = step.cross_section(iface.frame, 0.0)
    assert naive.area == pytest.approx(naive_area, rel=REL)


def test_contact_region_hollow_box_has_hole() -> None:
    hollow = Mesh.box((80, 80, 80)) - Mesh.box((60, 60, 60))
    plan = plan_grid(
        Bounds(min=(-40, -40, -40), max=(40, 40, 40)),
        CellLimits(max_cell=(80, 80, 80)),
        AxisCuts(x=[0]),
    )
    (iface,) = plan.interfaces
    region = contact_regions(hollow, plan, edge_inset=0)[iface.id]
    assert region.area == pytest.approx(80**2 - 60**2, rel=REL)
    assert len(region.components()) == 1
    assert len(region.polygons()) == 2  # outer contour + hole
    p = region.deepest_point()
    assert p is not None
    assert region.contains_point(*p)
    assert max(abs(p[0]), abs(p[1])) >= 30  # in the wall ring, not the hole


# --- joint_cells ---------------------------------------------------------------------------------


def test_joint_cells_male_lower_adds_to_lower_subtracts_from_upper() -> None:
    _, plan = _plan_2x1()
    iface = plan.interfaces[0]
    joint = make_dowel_joint(iface, iface.lower, iface.upper, 0.0, 0.0)
    cells, warnings = joint_cells(plan, [joint])
    assert warnings == []
    assert cells["x0_y0_z0"].volume() == pytest.approx(
        50 * 100 * 100 + joint.male.volume(), rel=REL
    )
    assert cells["x1_y0_z0"].volume() == pytest.approx(
        50 * 100 * 100 - joint.female.volume() + _female_spill(plan, joint), rel=REL
    )


def _female_spill(plan: CutPlan, joint: Joint) -> float:
    """Female volume that lies outside the female cell (the -clearance lip) and is clipped."""
    return float(joint.female.volume() - (joint.female ^ _cube(plan, joint.female_cell)).volume())


def test_joint_cells_male_upper_mirrored() -> None:
    _, plan = _plan_2x1()
    iface = plan.interfaces[0]
    joint = make_dowel_joint(iface, iface.upper, iface.lower, 0.0, 0.0)
    lo, hi = joint.male.bounding_box()[0], joint.male.bounding_box()[3]
    assert lo == pytest.approx(44.0, abs=1e-6)
    assert hi == pytest.approx(50.0, abs=1e-6)
    cells, warnings = joint_cells(plan, [joint])
    assert warnings == []
    upper = cells["x1_y0_z0"].volume()
    lower = cells["x0_y0_z0"].volume()
    assert upper == pytest.approx(50 * 100 * 100 + joint.male.volume(), rel=REL)
    assert lower == pytest.approx(
        50 * 100 * 100 - joint.female.volume() + _female_spill(plan, joint), rel=REL
    )
    assert lower < 50 * 100 * 100 < upper


def test_joint_clipped_to_female_cell_b2() -> None:
    plan = plan_grid(
        Bounds(min=(0, 0, 0), max=(150, 100, 100)), CellLimits(max_cell=(50, 100, 100))
    )
    assert len(plan.cells) == 3
    iface = next(i for i in plan.interfaces if i.lower == _idx(0, 0, 0))
    joint = make_dowel_joint(iface, iface.lower, iface.upper, 0.0, 0.0, depth=60.0)
    assert joint.male.bounding_box()[3] == pytest.approx(110.0, abs=1e-6)
    cells, warnings = joint_cells(plan, [joint])
    assert [w.code for w in warnings] == [WarningCode.JOINT_CLIPPED]
    assert warnings[0].subject == iface.id
    assert cells["x0_y0_z0"].bounding_box()[3] <= 100.0 + 1e-9
    assert (cells["x0_y0_z0"] ^ _cube(plan, _idx(2, 0, 0))).volume() == 0.0
    # The female hole stays in cell 1 too: cell 2 is untouched.
    assert cells["x2_y0_z0"].volume() == pytest.approx(50 * 100 * 100, rel=REL)


def test_joint_cells_without_joints_are_boxes() -> None:
    _, plan = _plan_2x2()
    cells, warnings = joint_cells(plan, [])
    assert warnings == []
    assert set(cells) == {c.id for c in plan.cells}
    for c in plan.cells:
        assert cells[c.id].volume() == pytest.approx(50 * 50 * 100, rel=REL)


# --- carve + check_pieces ------------------------------------------------------------------------


def test_carve_sphere_into_eight_pieces() -> None:
    sphere = Mesh.sphere(30.0)
    plan = plan_grid(sphere.bounds, CellLimits(max_cell=(30, 30, 30)))
    assert len(plan.cells) == 8
    cells, _ = joint_cells(plan, [])
    pieces = carve(sphere, cells, plan)
    assert len(pieces) == 8
    for p in pieces:
        assert p.info.piece_id == f"p_{p.info.cell.id}"
        assert p.info.component_count == 1
        assert p.info.fits_bed is False
        assert p.info.print_offset == (0.0, 0.0, 0.0)
        assert p.info.volume == pytest.approx(p.mesh.volume)
    assert sum(p.info.volume for p in pieces) == pytest.approx(sphere.volume, rel=REL)
    stats = check_pieces(pieces, plan, sphere.volume, 0.0, 1.5)
    assert stats.piece_count == 8
    assert stats.max_overlap_volume == 0.0
    assert stats.output_volume == pytest.approx(sphere.volume, rel=REL)
    assert stats.duration_s == 1.5


def test_carve_drops_empty_cells() -> None:
    small = _box_mesh((5, 5, 5), (20, 20, 20))
    plan = plan_grid(Bounds(min=(0, 0, 0), max=(100, 100, 100)), CellLimits(max_cell=(50, 50, 50)))
    cells, _ = joint_cells(plan, [])
    pieces = carve(small, cells, plan)
    assert [p.info.piece_id for p in pieces] == ["p_x0_y0_z0"]
    assert pieces[0].info.volume == pytest.approx(15**3, rel=REL)


def test_carve_counts_disconnected_components() -> None:
    blobs = _box_mesh((5, 5, 5), (15, 15, 15)) | _box_mesh((30, 30, 30), (40, 40, 40))
    plan = plan_grid(Bounds(min=(0, 0, 0), max=(100, 50, 50)), CellLimits(max_cell=(50, 50, 50)))
    cells, _ = joint_cells(plan, [])
    pieces = carve(blobs, cells, plan)
    assert len(pieces) == 1
    assert pieces[0].info.component_count == 2
    assert pieces[0].info.volume == pytest.approx(2 * 10**3, rel=REL)


def _dowels_near_interior_edges(
    plan: CutPlan, regions: dict[str, Region2D], use_deepest: bool
) -> list[Joint]:
    """A dowel per interface just inside its region, nearest the interior rect edge (worst case
    for B1), optionally plus one at the region's deepest point. Male side LOWER throughout."""
    joints: list[Joint] = []
    for iface in plan.interfaces:
        region = regions[iface.id]
        u0, v0, u1, v1 = region.bounds
        (edge,) = iface.interior_edges  # 2x2x1: exactly one interior edge per interface
        u, v = 0.0, 0.0
        if edge == "u_max":
            u = u1 - EDGE_STANDOFF
        elif edge == "u_min":
            u = u0 + EDGE_STANDOFF
        elif edge == "v_max":
            v = v1 - EDGE_STANDOFF
        else:
            v = v0 + EDGE_STANDOFF
        male, female = male_female(iface, MaleSide.LOWER)
        joints.append(make_dowel_joint(iface, male, female, u, v))
        if use_deepest:
            dp = region.deepest_point()
            assert dp is not None
            joints.append(make_dowel_joint(iface, male, female, *dp))
    return joints


def _clearance(plan: CutPlan, joints: list[Joint]) -> float:
    total = 0.0
    for j in joints:
        box = _cube(plan, j.female_cell)
        total += float((j.female ^ box).volume() - (j.male ^ box).volume())
    return total


def test_diagonal_pieces_do_not_overlap_b1() -> None:
    mesh, plan = _plan_2x2()
    regions = contact_regions(mesh, plan, edge_inset=6.0 + CLEARANCE)
    joints = _dowels_near_interior_edges(plan, regions, use_deepest=True)
    assert len(joints) == 8
    cells, warnings = joint_cells(plan, joints)
    assert warnings == []
    pieces = carve(mesh, cells, plan)
    assert len(pieces) == 4
    stats = check_pieces(pieces, plan, mesh.volume, _clearance(plan, joints), 0.0)
    assert stats.max_overlap_volume == 0.0


def test_without_inset_diagonal_pieces_would_overlap() -> None:
    mesh, plan = _plan_2x2()
    regions = contact_regions(mesh, plan, edge_inset=0)
    joints = _dowels_near_interior_edges(plan, regions, use_deepest=False)
    cells, _ = joint_cells(plan, joints)
    pieces = {p.info.piece_id: p for p in carve(mesh, cells, plan)}
    diagonal = (pieces["p_x0_y1_z0"].mesh & pieces["p_x1_y0_z0"].mesh).volume
    assert diagonal > 1e-3
    with pytest.raises(SliceInvariantError, match="overlap"):
        check_pieces(list(pieces.values()), plan, mesh.volume, _clearance(plan, joints), 0.0)


def _piece(mesh: Mesh, index: CellIndex) -> Piece:
    info = PieceInfo(
        piece_id=f"p_{index.id}",
        cell=index,
        bounds=mesh.bounds,
        volume=mesh.volume,
        triangle_count=mesh.triangle_count,
        component_count=1,
        fits_bed=False,
        print_offset=(0.0, 0.0, 0.0),
    )
    return Piece(info=info, mesh=mesh)


def test_check_pieces_raises_on_neighbour_overlap() -> None:
    _, plan = _plan_2x1()
    a = _piece(_box_mesh((0, 0, 0), (60, 100, 100)), _idx(0, 0, 0))
    b = _piece(_box_mesh((40, 0, 0), (100, 100, 100)), _idx(1, 0, 0))
    with pytest.raises(SliceInvariantError, match="overlap"):
        check_pieces([a, b], plan, 100.0**3, 0.0, 0.0)


def test_check_pieces_ignores_non_neighbours() -> None:
    """Documented behaviour: only the 26-neighbourhood is checked."""
    _, plan = _plan_2x1()
    a = _piece(_box_mesh((0, 0, 0), (10, 10, 10)), _idx(0, 0, 0))
    b = _piece(_box_mesh((5, 5, 5), (15, 15, 15)), _idx(2, 0, 0))
    total = a.info.volume + b.info.volume
    stats = check_pieces([a, b], plan, total, 0.0, 0.0)
    assert stats.max_overlap_volume == 0.0


def test_check_pieces_raises_on_volume_loss_and_gain() -> None:
    _, plan = _plan_2x1()
    a = _piece(_box_mesh((0, 0, 0), (50, 100, 100)), _idx(0, 0, 0))
    b = _piece(_box_mesh((50, 0, 0), (100, 100, 100)), _idx(1, 0, 0))
    with pytest.raises(SliceInvariantError, match="lost"):
        check_pieces([a, b], plan, 2 * 100.0**3, 0.0, 0.0)
    with pytest.raises(SliceInvariantError, match="gained"):
        check_pieces([a, b], plan, 0.5 * 100.0**3, 0.0, 0.0)
    # Loss within the declared clearance volume is fine.
    stats = check_pieces([a, b], plan, 100.0**3 + 10.0, 10.0, 0.0)
    assert stats.output_volume == pytest.approx(100.0**3, rel=REL)
    assert math.isclose(stats.volume_ratio, 100.0**3 / (100.0**3 + 10.0))
