"""Conformance suite for every registered joint generator (docs/00_design.md §4.2)."""

from __future__ import annotations

import math
from typing import Any

import pytest
from manifold3d import Manifold

from stl_slicer.core.geometry import LocalFrame, Region2D
from stl_slicer.core.joints.base import JointGenerator, ProfileStripJoint
from stl_slicer.core.joints.dovetail import DovetailJoint
from stl_slicer.core.joints.dowel import DowelJoint
from stl_slicer.core.joints.hexpin import HexPinJoint, hexagon
from stl_slicer.core.joints.jigsaw import JigsawJoint
from stl_slicer.core.joints.magnet import MagnetJoint
from stl_slicer.core.joints.registry import REGISTRY, get_generator, spec_clearance, spec_depth
from stl_slicer.core.joints.tab import TabJoint
from stl_slicer.core.joints.tongue import TongueJoint
from stl_slicer.core.models import (
    Axis,
    AxisCuts,
    Bounds,
    CellLimits,
    CutInterface,
    DovetailJointSpec,
    DowelJointSpec,
    HexPinJointSpec,
    JigsawJointSpec,
    MagnetJointSpec,
    NoJointSpec,
    Placement,
    TabJointSpec,
    TongueJointSpec,
)
from stl_slicer.core.planning import plan_grid

TOL = 1e-6
KINDS = sorted(REGISTRY)
POCKET_KINDS = [k for k in KINDS if not REGISTRY[k].has_male]


@pytest.fixture(scope="module")
def interface() -> CutInterface:
    plan = plan_grid(
        Bounds(min=(0, 0, 0), max=(100, 100, 100)), CellLimits(max_cell=(50, 100, 100))
    )
    assert len(plan.interfaces) == 1
    return plan.interfaces[0]


def _full(interface: CutInterface) -> Region2D:
    return Region2D.rect(*interface.rect)


def _sides(interface: CutInterface) -> list[tuple[Any, Any, bool]]:
    """(male, female, female_is_upper)."""
    return [(interface.lower, interface.upper, True), (interface.upper, interface.lower, False)]


def _bb(m: Manifold) -> list[float]:
    return [float(x) for x in m.bounding_box()]


@pytest.mark.parametrize("kind", KINDS)
def test_registry_kind_matches_spec(kind: str) -> None:
    gen = get_generator(kind)
    assert gen.kind == kind
    assert gen.spec_type().kind == kind


def test_unknown_kind() -> None:
    with pytest.raises(KeyError):
        get_generator("mortise")


def test_spec_depth_and_clearance() -> None:
    assert spec_depth(NoJointSpec()) == 0.0
    assert spec_clearance(NoJointSpec()) == 0.0
    assert spec_depth(DowelJointSpec(depth=7)) == 7.0
    assert spec_clearance(DovetailJointSpec(clearance=0.2)) == 0.2
    assert spec_depth(TabJointSpec(depth=5)) == 5.0
    assert spec_depth(HexPinJointSpec(depth=5)) == 5.0
    assert spec_depth(TongueJointSpec(depth=5)) == 5.0
    assert spec_depth(MagnetJointSpec(height=5)) == 0.0  # pockets: nothing protrudes
    assert spec_clearance(MagnetJointSpec()) == 0.1
    assert MagnetJointSpec(height=3, clearance=0.1).pocket_depth == pytest.approx(3.1)


def test_all_eight_kinds_registered() -> None:
    assert KINDS == ["dovetail", "dowel", "hexpin", "jigsaw", "magnet", "none", "tab", "tongue"]
    assert POCKET_KINDS == ["magnet"]


@pytest.mark.parametrize("kind", KINDS)
def test_wrong_spec_type_raises(kind: str, interface: CutInterface) -> None:
    gen = get_generator(kind)
    other = next(REGISTRY[k] for k in KINDS if k != kind)().spec_type()
    with pytest.raises(TypeError):
        gen.call(interface, _full(interface), other, interface.lower, interface.upper)


@pytest.mark.parametrize("kind", KINDS)
def test_empty_region(kind: str, interface: CutInterface) -> None:
    gen = get_generator(kind)
    for male, female, _ in _sides(interface):
        assert gen.call(interface, Region2D.empty(), gen.spec_type(), male, female) == []


@pytest.mark.parametrize("kind", KINDS)
def test_region_too_small(kind: str, interface: CutInterface) -> None:
    gen = get_generator(kind)
    spec = gen.spec_type()
    # survives the 3 mm edge margin but is far narrower than any footprint
    tiny = Region2D.rect(-3.5, -3.5, 3.5, 3.5)
    assert not tiny.inset(3.0).is_empty
    for male, female, _ in _sides(interface):
        assert gen.call(interface, tiny, spec, male, female) == []
        assert gen.call(interface, Region2D.rect(0, 0, 1, 1), spec, male, female) == []


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("female_upper", [True, False])
def test_joint_contract(kind: str, female_upper: bool, interface: CutInterface) -> None:
    gen: JointGenerator[Any] = get_generator(kind)
    spec = gen.spec_type()
    male_cell, female_cell = (
        (interface.lower, interface.upper) if female_upper else (interface.upper, interface.lower)
    )
    joints = gen.call(interface, _full(interface), spec, male_cell, female_cell)
    if kind == "none":
        assert joints == []
        return
    assert joints

    keys = [(j.placement.u, j.placement.v) for j in joints]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)

    depth = spec_depth(spec)
    c = spec_clearance(spec)
    a = interface.axis.ordinal
    pos = interface.position
    for j in joints:
        assert j.interface_id == interface.id
        assert j.kind == gen.kind
        assert j.male_cell == male_cell
        assert j.female_cell == female_cell
        assert isinstance(j.placement, Placement)

    if not gen.has_male:
        pocket_depth = float(spec.pocket_depth)
        for j in joints:
            assert j.male.is_empty()
            assert j.male_pocket is not None
            fv, pv = float(j.female.volume()), float(j.male_pocket.volume())
            assert fv > 0 and pv > 0
            assert j.clearance_volume == pytest.approx(fv + pv)
            fb, pb = _bb(j.female), _bb(j.male_pocket)
            f_lo, f_hi, p_lo, p_hi = fb[a], fb[a + 3], pb[a], pb[a + 3]
            if female_upper:  # female pocket above the plane, male pocket below
                assert f_lo >= pos - TOL and f_hi <= pos + pocket_depth + TOL
                assert p_hi <= pos + TOL and p_lo >= pos - pocket_depth - TOL
            else:
                assert f_hi <= pos + TOL and f_lo >= pos - pocket_depth - TOL
                assert p_lo >= pos - TOL and p_hi <= pos + pocket_depth + TOL
        return

    for j in joints:
        assert j.male_pocket is None
        mv, fv = float(j.male.volume()), float(j.female.volume())
        assert mv > 0
        assert float((j.male - j.female).volume()) <= 1e-9
        assert fv > mv
        assert j.clearance_volume == pytest.approx(fv - mv)

        mb, fb = _bb(j.male), _bb(j.female)
        m_lo, m_hi, f_lo, f_hi = mb[a], mb[a + 3], fb[a], fb[a + 3]
        if female_upper:
            assert m_lo >= pos - TOL
            assert f_lo >= pos - c - TOL  # female pocket overshoots the plane by `clearance`
            assert m_hi <= pos + depth + TOL
        else:
            assert m_hi <= pos + TOL
            assert f_hi <= pos + c + TOL
            assert m_lo >= pos - depth - TOL
        assert m_hi - m_lo <= depth + TOL
        assert f_hi - f_lo <= depth + 2 * c + TOL


def test_dowel_grid_count(interface: CutInterface) -> None:
    spec = DowelJointSpec(spacing=40, edge_margin=3)
    joints = DowelJoint().call(interface, _full(interface), spec, interface.lower, interface.upper)
    assert len(joints) == 9
    assert sorted({j.placement.u for j in joints}) == [-40.0, 0.0, 40.0]
    assert sorted({j.placement.v for j in joints}) == [-40.0, 0.0, 40.0]


def test_dowel_requires_clearance(interface: CutInterface) -> None:
    spec = DowelJointSpec.model_construct(clearance=0.0)
    with pytest.raises(ValueError):
        DowelJoint().solid(
            LocalFrame(interface.frame), Placement(u=0, v=0), spec, 100, 100, _full(interface)
        )


def test_dovetail_strips(interface: CutInterface) -> None:
    spec = DovetailJointSpec(spacing=60, edge_margin=3)
    joints = DovetailJoint().call(
        interface, _full(interface), spec, interface.lower, interface.upper
    )
    assert len(joints) == 2
    assert [j.placement.u for j in joints] == pytest.approx([-30.0, 30.0])
    for j in joints:
        # x-interface: v is world Z; the male slides through the whole cell and beyond
        bb = _bb(j.male)
        assert bb[2] == pytest.approx(0.0)
        assert bb[5] == pytest.approx(100.0)


def test_dovetail_interlocks(interface: CutInterface) -> None:
    spec = DovetailJointSpec()
    male, female = DovetailJoint().solid(
        LocalFrame(interface.frame), Placement(u=0, v=0), spec, 100, 100, _full(interface)
    )

    def width_at(z: float) -> float:
        b = [float(x) for x in male.slice(z).bounds()]
        return b[2] - b[0]

    near, far = width_at(0.01), width_at(spec.depth - 0.01)
    assert far > near
    assert near == pytest.approx(spec.neck_width, abs=0.02)
    assert far == pytest.approx(spec.head_width, abs=0.02)
    mb = [float(x) for x in male.bounding_box()]
    assert mb[1] == pytest.approx(-50.0)
    assert mb[4] == pytest.approx(50.0)
    fb = [float(x) for x in female.bounding_box()]
    assert fb[1] == pytest.approx(-50.0 - spec.clearance)
    assert fb[5] == pytest.approx(spec.depth + spec.clearance)


def test_jigsaw_strips(interface: CutInterface) -> None:
    spec = JigsawJointSpec(spacing=60, edge_margin=3)
    joints = JigsawJoint().call(interface, _full(interface), spec, interface.lower, interface.upper)
    assert len(joints) == 2
    assert [j.placement.u for j in joints] == pytest.approx([-30.0, 30.0])
    for j in joints:
        bb = _bb(j.male)  # x-interface: v is world Z; the knob runs through the whole cell
        assert bb[2] == pytest.approx(0.0)
        assert bb[5] == pytest.approx(100.0)


def test_jigsaw_interlocks(interface: CutInterface) -> None:
    spec = JigsawJointSpec(neck_width=8, head_diameter=14, depth=20)
    male, female = JigsawJoint().solid(
        LocalFrame(interface.frame), Placement(u=0, v=0), spec, 100, 100, _full(interface)
    )

    def width_at(z: float) -> float:
        b = [float(x) for x in male.slice(z).bounds()]
        return b[2] - b[0]

    head_z = spec.depth - spec.head_diameter / 2
    assert width_at(0.5) == pytest.approx(spec.neck_width)
    assert width_at(head_z) == pytest.approx(spec.head_diameter, abs=0.02)
    assert width_at(head_z) > width_at(0.5)  # undercut -> interlocks along the normal
    mb = [float(x) for x in male.bounding_box()]
    assert mb[2] == pytest.approx(0.0) and mb[5] == pytest.approx(spec.depth)
    assert mb[1] == pytest.approx(-50.0) and mb[4] == pytest.approx(50.0)
    fb = [float(x) for x in female.bounding_box()]
    assert fb[2] == pytest.approx(-spec.clearance)
    # round-join offset of a 48-gon sits a hair under the true arc at the apex
    assert fb[5] == pytest.approx(spec.depth + spec.clearance, abs=1e-3)
    assert fb[1] == pytest.approx(-50.0 - spec.clearance)


# --- tab ----------------------------------------------------------------------------------------


def test_tab_strips_are_plain_rectangles(interface: CutInterface) -> None:
    spec = TabJointSpec(width=10, depth=6, spacing=60, edge_margin=3)
    gen = TabJoint()
    assert not gen.interlocks
    joints = gen.call(interface, _full(interface), spec, interface.lower, interface.upper)
    assert len(joints) == 2
    assert [j.placement.u for j in joints] == pytest.approx([-30.0, 30.0])
    male, female = gen.solid(
        LocalFrame(interface.frame), Placement(u=0, v=0), spec, 100, 100, _full(interface)
    )

    def width_at(z: float) -> float:
        b = [float(x) for x in male.slice(z).bounds()]
        return b[2] - b[0]

    # constant width: no undercut, so the tab presses in along the normal
    assert width_at(0.01) == pytest.approx(spec.width)
    assert width_at(spec.depth - 0.01) == pytest.approx(spec.width)
    mb = _bb(male)
    assert mb[0] == pytest.approx(-5.0) and mb[3] == pytest.approx(5.0)
    assert mb[1] == pytest.approx(-50.0) and mb[4] == pytest.approx(50.0)  # through the cell
    assert mb[2] == pytest.approx(0.0) and mb[5] == pytest.approx(spec.depth)
    fb = _bb(female)
    c = spec.clearance
    assert fb[0] == pytest.approx(-5.0 - c) and fb[3] == pytest.approx(5.0 + c)
    assert fb[2] == pytest.approx(-c) and fb[5] == pytest.approx(spec.depth + c)
    assert float(male.volume()) == pytest.approx(10 * 6 * 100)


# --- hexpin -------------------------------------------------------------------------------------


def test_hexpin_grid_and_across_flats(interface: CutInterface) -> None:
    spec = HexPinJointSpec(width=8, depth=6, spacing=40, edge_margin=3)
    joints = HexPinJoint().call(interface, _full(interface), spec, interface.lower, interface.upper)
    assert len(joints) == 9  # same grid as the dowel
    male, female = HexPinJoint().solid(
        LocalFrame(interface.frame), Placement(u=0, v=0), spec, 100, 100, _full(interface)
    )
    mb = _bb(male)
    across_flats = mb[4] - mb[1]  # flats are perpendicular to v
    across_corners = mb[3] - mb[0]
    assert across_flats == pytest.approx(spec.width)
    assert across_corners == pytest.approx(spec.width * 2 / math.sqrt(3))
    assert mb[2] == pytest.approx(0.0) and mb[5] == pytest.approx(spec.depth)
    # hexagon area = (sqrt(3) / 2) * w^2
    assert float(male.volume()) == pytest.approx(math.sqrt(3) / 2 * spec.width**2 * spec.depth)
    fb = _bb(female)
    assert fb[4] - fb[1] == pytest.approx(spec.width + 2 * spec.clearance, abs=1e-3)
    assert fb[2] == pytest.approx(-spec.clearance)
    assert len(hexagon(spec.width).polygons()[0]) == 6  # six flat faces


# --- tongue -------------------------------------------------------------------------------------


def test_tongue_single_rib_spans_region_across_the_long_axis(interface: CutInterface) -> None:
    spec = TongueJointSpec(width=5, depth=4, clearance=0.15, edge_margin=2)
    gen = TongueJoint()
    assert not gen.interlocks
    # the 100x100 interface ties -> the rib runs along v, the profile across u
    joints = gen.call(interface, _full(interface), spec, interface.lower, interface.upper)
    assert len(joints) == 1
    (j,) = joints
    assert (j.placement.u, j.placement.v) == (0.0, 0.0)
    mb = _bb(j.male)
    a = interface.axis.ordinal
    pos = interface.position
    assert mb[a] == pytest.approx(pos) and mb[a + 3] == pytest.approx(pos + spec.depth)
    # frame (u=Y, v=Z) on an X cut: 5 mm across Y, the rib runs along Z over the inset region
    assert mb[4] - mb[1] == pytest.approx(spec.width)
    assert mb[2] == pytest.approx(2.0) and mb[5] == pytest.approx(98.0)
    fb = _bb(j.female)
    assert fb[2] == pytest.approx(2.0 - spec.clearance)
    assert fb[5] == pytest.approx(98.0 + spec.clearance)
    assert fb[4] - fb[1] == pytest.approx(spec.width + 2 * spec.clearance)


def test_tongue_rib_follows_the_region_not_the_rect(interface: CutInterface) -> None:
    spec = TongueJointSpec(width=5, depth=4, edge_margin=2)
    region = Region2D.rect(-50, -20, 50, 45)  # v (world Z) from 30 to 95 of the 100 mm cell
    joints = TongueJoint().call(interface, region, spec, interface.lower, interface.upper)
    assert len(joints) == 1
    mb = _bb(joints[0].male)
    assert mb[2] == pytest.approx(32.0) and mb[5] == pytest.approx(93.0)
    assert joints[0].placement.v == pytest.approx(12.5)


def test_tongue_rib_runs_along_the_long_axis_on_a_slab() -> None:
    gen = TongueJoint()
    spec = TongueJointSpec()
    slab = _plan_ifaces(SLAB, AxisCuts(x=[100], y=[100]))
    for axis, long_axis in ((Axis.X, 1), (Axis.Y, 0)):
        iface = slab[axis]
        joints = gen.call(iface, Region2D.rect(*iface.rect), spec, iface.lower, iface.upper)
        assert len(joints) == 1
        mb = _bb(joints[0].male)
        assert mb[long_axis + 3] - mb[long_axis] == pytest.approx(100 - 2 * spec.edge_margin)
        assert mb[5] - mb[2] == pytest.approx(spec.width)  # 5 mm across the 15 mm thickness
        assert mb[2] == pytest.approx(5.0) and mb[5] == pytest.approx(10.0)  # centred


def test_tongue_too_narrow_across_the_thickness(interface: CutInterface) -> None:
    spec = TongueJointSpec(width=8, edge_margin=2)
    region = Region2D.rect(-5, -50, 5, 50)  # 10 mm across (u), 6 after the inset
    joints = TongueJoint().call(interface, region, spec, interface.lower, interface.upper)
    assert joints == []


# --- magnet -------------------------------------------------------------------------------------


def test_magnet_pockets_on_both_faces(interface: CutInterface) -> None:
    spec = MagnetJointSpec(diameter=6, height=3, clearance=0.1, spacing=50, edge_margin=3)
    gen = MagnetJoint()
    assert not gen.has_male
    joints = gen.call(interface, _full(interface), spec, interface.lower, interface.upper)
    assert len(joints) == 4  # 2x2 at +-25
    assert sorted({j.placement.u for j in joints}) == pytest.approx([-25.0, 25.0])
    r = spec.diameter / 2 + spec.clearance
    for j in joints:
        assert j.male.is_empty() and j.male_pocket is not None
        fb, pb = _bb(j.female), _bb(j.male_pocket)
        assert fb[0] == pytest.approx(interface.position)
        assert fb[3] == pytest.approx(interface.position + spec.pocket_depth)
        assert pb[3] == pytest.approx(interface.position)
        assert pb[0] == pytest.approx(interface.position - spec.pocket_depth)
        assert fb[4] - fb[1] == pytest.approx(2 * r, abs=1e-3)
        assert pb[5] - pb[2] == pytest.approx(2 * r, abs=1e-3)
        expected = float(j.female.volume()) + float(j.male_pocket.volume())
        assert j.clearance_volume == pytest.approx(expected)
        # a 32-gon of radius r sunk pocket_depth deep, on both sides
        area = 32 / 2 * r**2 * math.sin(2 * math.pi / 32)
        assert float(j.female.volume()) == pytest.approx(area * spec.pocket_depth, rel=2e-2)


def test_magnet_solid_is_not_defined(interface: CutInterface) -> None:
    with pytest.raises(NotImplementedError):
        MagnetJoint().solid(
            LocalFrame(interface.frame),
            Placement(u=0, v=0),
            MagnetJointSpec(),
            100,
            100,
            _full(interface),
        )


SLAB = Bounds(min=(0, 0, 0), max=(200, 200, 15))
BAR = Bounds(min=(0, 0, 0), max=(30, 30, 200))
# strips that follow the thin-axis slide rule (the tongue inverts it and is tested above)
STRIP_KINDS = [
    k for k in KINDS if isinstance(get_generator(k), ProfileStripJoint) and k != "tongue"
]


def _plan_ifaces(bounds: Bounds, cuts: AxisCuts) -> dict[Axis, CutInterface]:
    plan = plan_grid(bounds, CellLimits(max_cell=(1000, 1000, 1000)), cuts)
    return {i.axis: i for i in plan.interfaces}


@pytest.mark.parametrize("kind", STRIP_KINDS)
def test_slide_axis_rule(kind: str) -> None:
    gen = get_generator(kind)
    assert isinstance(gen, ProfileStripJoint)
    slab = _plan_ifaces(SLAB, AxisCuts(x=[100], y=[100]))
    assert gen.slide_axis(slab[Axis.X]) is Axis.Z  # frame (u=Y, v=Z): v is thinner
    assert gen.slide_axis(slab[Axis.Y]) is Axis.Z  # frame (u=Z, v=X): u is thinner -> swapped
    bar = _plan_ifaces(BAR, AxisCuts(z=[100]))
    assert gen.slide_axis(bar[Axis.Z]) is Axis.Y  # 30x30 tie -> v = Y


@pytest.mark.parametrize("kind", STRIP_KINDS)
def test_strip_runs_along_the_thin_axis_on_a_y_cut(kind: str) -> None:
    gen = get_generator(kind)
    spec = gen.spec_type()
    iface = _plan_ifaces(SLAB, AxisCuts(x=[100], y=[100]))[Axis.Y]
    region = Region2D.rect(*iface.rect)
    joints = gen.call(iface, region, spec, iface.lower, iface.upper)
    assert joints
    # placements are sorted and spread across v (= X); the strip spans the whole 15 mm of Z
    keys = [(j.placement.u, j.placement.v) for j in joints]
    assert keys == sorted(keys)
    assert all(j.placement.u == pytest.approx(0.0) for j in joints)
    assert len({round(j.placement.v, 6) for j in joints}) == len(joints)
    depth = spec_depth(spec)
    for j in joints:
        bb = _bb(j.male)
        assert bb[2] == pytest.approx(0.0) and bb[5] == pytest.approx(15.0)  # world Z
        assert bb[1] >= iface.position - TOL and bb[4] <= iface.position + depth + TOL  # normal Y
        assert bb[3] - bb[0] < 100.0  # not a strip along X


def test_cells_must_belong_to_interface(interface: CutInterface) -> None:
    with pytest.raises(ValueError):
        DowelJoint().call(
            interface, _full(interface), DowelJointSpec(), interface.lower, interface.lower
        )
