"""Unit tests for `core.joints.auto.resolve_joint` (docs/00_design.md §4.6)."""

from __future__ import annotations

import pytest

from stl_slicer.core.joints.auto import clamp, resolve_joint
from stl_slicer.core.models import (
    Bounds,
    DovetailJointSpec,
    DowelJointSpec,
    JigsawJointSpec,
    JointSpec,
    NoJointSpec,
    PrintVolume,
)


def _bounds(sx: float, sy: float, sz: float) -> Bounds:
    return Bounds(min=(0, 0, 0), max=(sx, sy, sz))


def _bed(size: float) -> PrintVolume:
    return PrintVolume(x=size, y=size, z=size)


# e = min(200 - 0, 300) = 200; t = 20 (edge_margin cap 5)
MID = (_bounds(300, 100, 20), _bed(200), 0.0)
# e = min(200, 10) = 10; t = 6 (edge_margin cap 1.5)
TINY = (_bounds(10, 10, 6), _bed(200), 0.0)
# e = min(1000, 2000) = 1000; t = 2000
HUGE = (_bounds(2000, 2000, 2000), _bed(1000), 0.0)


def test_clamp() -> None:
    assert clamp(5, 1, 10) == 5
    assert clamp(-1, 1, 10) == 1
    assert clamp(50, 1, 10) == 10


@pytest.mark.parametrize("spec", [NoJointSpec(), DowelJointSpec(), JigsawJointSpec(auto=False)])
def test_non_auto_and_none_pass_through(spec: JointSpec) -> None:
    assert resolve_joint(spec, *MID) is spec


def test_jigsaw_mid_values() -> None:
    got = resolve_joint(JigsawJointSpec(auto=True), *MID)
    assert got == JigsawJointSpec(
        head_diameter=24.0,
        neck_width=13.2,
        depth=31.2,
        spacing=100.0,
        edge_margin=5.0,  # min(14, 0.25 t)
        clearance=0.15,
    )
    assert got.auto is False


def test_dovetail_mid_values() -> None:
    got = resolve_joint(DovetailJointSpec(auto=True), *MID)
    assert got == DovetailJointSpec(
        head_width=20.0, neck_width=13.0, depth=12.0, spacing=100.0, edge_margin=5.0
    )


def test_dowel_mid_values() -> None:
    # 0.35 t = 7 < 0.05 e = 10: thickness governs
    got = resolve_joint(DowelJointSpec(auto=True), *MID)
    assert got == DowelJointSpec(diameter=7.0, depth=10.5, spacing=80.0, edge_margin=5.0)


def test_low_clamps() -> None:
    jig = resolve_joint(JigsawJointSpec(auto=True), *TINY)
    assert isinstance(jig, JigsawJointSpec)
    assert (jig.head_diameter, jig.neck_width, jig.depth) == (6.0, 3.3, 7.8)
    assert (jig.spacing, jig.edge_margin) == (25.0, 1.5)

    dov = resolve_joint(DovetailJointSpec(auto=True), *TINY)
    assert isinstance(dov, DovetailJointSpec)
    assert (dov.head_width, dov.neck_width, dov.depth) == (6.0, 3.9, 4.0)
    assert (dov.spacing, dov.edge_margin) == (25.0, 1.5)

    dow = resolve_joint(DowelJointSpec(auto=True), *TINY)
    assert isinstance(dow, DowelJointSpec)
    # 0.35 t = 2.1, 0.05 e = 0.5 -> clamped up to 3; edge_margin = min(3.5, 1.5)
    assert (dow.diameter, dow.depth, dow.spacing, dow.edge_margin) == (3.0, 4.5, 20.0, 1.5)


def test_edge_margin_uncapped_on_thick_model() -> None:
    thick = (_bounds(300, 100, 100), _bed(200), 0.0)  # t = 100 -> cap 25, above every rule
    jig = resolve_joint(JigsawJointSpec(auto=True), *thick)
    assert isinstance(jig, JigsawJointSpec)
    assert jig.edge_margin == 14.0
    dow = resolve_joint(DowelJointSpec(auto=True), *thick)
    assert isinstance(dow, DowelJointSpec)
    assert dow.edge_margin == 7.0  # diameter min(35, 10) = 10 -> 0.5 * 10 + 2


def test_high_clamps() -> None:
    jig = resolve_joint(JigsawJointSpec(auto=True), *HUGE)
    assert isinstance(jig, JigsawJointSpec)
    assert (jig.head_diameter, jig.spacing, jig.edge_margin) == (40.0, 150.0, 15.0)

    dov = resolve_joint(DovetailJointSpec(auto=True), *HUGE)
    assert isinstance(dov, DovetailJointSpec)
    assert (dov.head_width, dov.depth, dov.spacing, dov.edge_margin) == (30.0, 18.0, 150.0, 15.0)

    dow = resolve_joint(DowelJointSpec(auto=True), *HUGE)
    assert isinstance(dow, DowelJointSpec)
    assert (dow.diameter, dow.depth, dow.spacing, dow.edge_margin) == (12.0, 18.0, 100.0, 8.0)


def test_rounds_to_tenth_mm() -> None:
    # e = min(250 - 4, 300) = 246 -> 0.12 e = 29.52 -> 29.5
    got = resolve_joint(JigsawJointSpec(auto=True), _bounds(300, 300, 15), _bed(250), 2.0)
    assert isinstance(got, JigsawJointSpec)
    assert got.head_diameter == 29.5
    assert got.spacing == 123.0
    assert got.edge_margin == 3.8  # 0.25 * 15 = 3.75 -> 3.8
    assert got.clearance == 0.15
    for value in got.model_dump(exclude={"kind", "auto", "clearance"}).values():
        assert round(value, 1) == value


def test_edge_uses_model_when_smaller_than_bed() -> None:
    # e = min(246, 100) = 100
    got = resolve_joint(DovetailJointSpec(auto=True), _bounds(100, 50, 10), _bed(250), 2.0)
    assert isinstance(got, DovetailJointSpec)
    assert got.head_width == 10.0
    assert got.spacing == 50.0


@pytest.mark.parametrize("kind", [DowelJointSpec, DovetailJointSpec, JigsawJointSpec])
@pytest.mark.parametrize("env", [MID, TINY, HUGE])
def test_resolved_spec_validates_and_round_trips(
    kind: type[DowelJointSpec] | type[DovetailJointSpec] | type[JigsawJointSpec],
    env: tuple[Bounds, PrintVolume, float],
) -> None:
    got = resolve_joint(kind(auto=True), *env)
    assert type(got) is kind
    assert got.auto is False
    assert kind.model_validate(got.model_dump()) == got
    assert resolve_joint(got, *env) is got


def test_scale_one_is_identity_and_coefficients_are_echoed() -> None:
    base = resolve_joint(JigsawJointSpec(auto=True), *MID)
    scaled = resolve_joint(JigsawJointSpec(auto=True, size_scale=1.0, depth_scale=1.0), *MID)
    assert scaled == base
    assert base.size_scale == 1.0 and base.depth_scale == 1.0
    got = resolve_joint(JigsawJointSpec(auto=True, size_scale=1.5, depth_scale=0.8), *MID)
    assert (got.size_scale, got.depth_scale) == (1.5, 0.8)
    assert got.auto is False


def test_size_scale_scales_width_and_dependent_neck() -> None:
    got = resolve_joint(JigsawJointSpec(auto=True, size_scale=2.0), *MID)
    assert isinstance(got, JigsawJointSpec)
    assert got.head_diameter == 48.0  # 24 * 2
    assert got.neck_width == pytest.approx(26.4)
    dowel = resolve_joint(DowelJointSpec(auto=True, size_scale=0.5), *MID)
    assert isinstance(dowel, DowelJointSpec)
    assert dowel.diameter == pytest.approx(3.5)  # min(0.35*20, 0.05*200) = 7 -> * 0.5


def test_depth_scale_scales_depth_but_jigsaw_head_stays_past_plane() -> None:
    got = resolve_joint(JigsawJointSpec(auto=True, depth_scale=0.5), *MID)
    assert isinstance(got, JigsawJointSpec)
    assert got.depth == got.head_diameter == 24.0  # 15.6 lifted back to the head diameter
    deep = resolve_joint(JigsawJointSpec(auto=True, depth_scale=2.0), *MID)
    assert isinstance(deep, JigsawJointSpec)
    assert deep.depth == pytest.approx(62.4)
    dt = resolve_joint(DovetailJointSpec(auto=True, depth_scale=0.5), *MID)
    assert isinstance(dt, DovetailJointSpec)
    assert dt.depth == pytest.approx(6.0)  # clamp(0.6*20, 4, 20) = 12 -> * 0.5


def test_manual_specs_ignore_scales() -> None:
    spec = DowelJointSpec(auto=False, size_scale=2.0)
    assert resolve_joint(spec, *MID) is spec
