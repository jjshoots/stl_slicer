"""Conformance suite for every registered joint generator (docs/00_design.md §4.2)."""

from __future__ import annotations

from typing import Any

import pytest
from manifold3d import Manifold

from stl_slicer.core.geometry import LocalFrame, Region2D
from stl_slicer.core.joints.base import JointGenerator
from stl_slicer.core.joints.dovetail import DovetailJoint
from stl_slicer.core.joints.dowel import DowelJoint
from stl_slicer.core.joints.registry import REGISTRY, get_generator, spec_clearance, spec_depth
from stl_slicer.core.models import (
    Bounds,
    CellLimits,
    CutInterface,
    DovetailJointSpec,
    DowelJointSpec,
    NoJointSpec,
    Placement,
)
from stl_slicer.core.planning import plan_grid

TOL = 1e-6
KINDS = sorted(REGISTRY)


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

        assert j.interface_id == interface.id
        assert j.kind == gen.kind
        assert j.male_cell == male_cell
        assert j.female_cell == female_cell
        assert isinstance(j.placement, Placement)


def test_dowel_grid_count(interface: CutInterface) -> None:
    spec = DowelJointSpec(spacing=40, edge_margin=3)
    joints = DowelJoint().call(interface, _full(interface), spec, interface.lower, interface.upper)
    assert len(joints) == 9
    assert sorted({j.placement.u for j in joints}) == [-40.0, 0.0, 40.0]
    assert sorted({j.placement.v for j in joints}) == [-40.0, 0.0, 40.0]


def test_dowel_requires_clearance(interface: CutInterface) -> None:
    spec = DowelJointSpec.model_construct(clearance=0.0)
    with pytest.raises(ValueError):
        DowelJoint().solid(LocalFrame(interface.frame), Placement(u=0, v=0), spec, 100, 100)


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
        LocalFrame(interface.frame), Placement(u=0, v=0), spec, 100, 100
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


def test_cells_must_belong_to_interface(interface: CutInterface) -> None:
    with pytest.raises(ValueError):
        DowelJoint().call(
            interface, _full(interface), DowelJointSpec(), interface.lower, interface.lower
        )
