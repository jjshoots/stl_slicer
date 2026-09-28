"""Unit tests for `core.joints.auto.resolve_joint` (docs/00_design.md §4.6)."""

from __future__ import annotations

import pytest

from stl_slicer.core.joints.auto import clamp, resolve_joint
from stl_slicer.core.models import (
    Bounds,
    DovetailJointSpec,
    DowelJointSpec,
    HexPinJointSpec,
    JigsawJointSpec,
    JointSpec,
    MagnetJointSpec,
    NoJointSpec,
    PrintVolume,
    TabJointSpec,
    TongueJointSpec,
)

ALL_SIZED = [
    DowelJointSpec,
    DovetailJointSpec,
    JigsawJointSpec,
    TabJointSpec,
    HexPinJointSpec,
    TongueJointSpec,
    MagnetJointSpec,
]


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


@pytest.mark.parametrize("kind", ALL_SIZED)
@pytest.mark.parametrize("env", [MID, TINY, HUGE])
def test_resolved_spec_validates_and_round_trips(
    kind: type[JointSpec], env: tuple[Bounds, PrintVolume, float]
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


# --- tab / hexpin / tongue / magnet (docs/03_more_joints.md) --------------------------------------


def test_tab_mid_values() -> None:
    # width = clamp(0.10 * 200, 5, 30) = 20; depth = clamp(10, 3, 15); margin = min(12, 0.25 t)
    got = resolve_joint(TabJointSpec(auto=True), *MID)
    assert got == TabJointSpec(width=20.0, depth=10.0, spacing=100.0, edge_margin=5.0)


def test_tab_clamps_and_scales() -> None:
    tiny = resolve_joint(TabJointSpec(auto=True), *TINY)
    assert isinstance(tiny, TabJointSpec)
    assert (tiny.width, tiny.depth, tiny.spacing, tiny.edge_margin) == (5.0, 3.0, 25.0, 1.5)
    huge = resolve_joint(TabJointSpec(auto=True), *HUGE)
    assert isinstance(huge, TabJointSpec)
    assert (huge.width, huge.depth, huge.spacing, huge.edge_margin) == (30.0, 15.0, 150.0, 15.0)
    scaled = resolve_joint(TabJointSpec(auto=True, size_scale=0.5, depth_scale=2.0), *MID)
    assert isinstance(scaled, TabJointSpec)
    assert (scaled.width, scaled.depth) == (10.0, 10.0)  # clamp(5, 3, 15) * 2
    assert scaled.edge_margin == 5.0  # min(7, 0.25 t)
    assert (scaled.size_scale, scaled.depth_scale) == (0.5, 2.0)


def test_hexpin_follows_the_dowel_rule() -> None:
    for env in (MID, TINY, HUGE):
        hexpin = resolve_joint(HexPinJointSpec(auto=True, size_scale=1.5), *env)
        dowel = resolve_joint(DowelJointSpec(auto=True, size_scale=1.5), *env)
        assert isinstance(hexpin, HexPinJointSpec) and isinstance(dowel, DowelJointSpec)
        assert hexpin.width == dowel.diameter
        assert (hexpin.depth, hexpin.spacing, hexpin.edge_margin, hexpin.clearance) == (
            dowel.depth,
            dowel.spacing,
            dowel.edge_margin,
            dowel.clearance,
        )
    got = resolve_joint(HexPinJointSpec(auto=True), *MID)
    assert got == HexPinJointSpec(width=7.0, depth=10.5, spacing=80.0, edge_margin=5.0)


def test_tongue_mid_values() -> None:
    # width = clamp(20 / 3, 2, 12) = 6.7; depth = clamp(0.8 * 6.7, 3, 15) = 5.4;
    # margin = min(clamp(0.5 * 6.7 + 1, 2, 8), 5) = 4.35 -> 4.3 or 4.4 (float rounding)
    got = resolve_joint(TongueJointSpec(auto=True), *MID)
    assert isinstance(got, TongueJointSpec)
    assert (got.width, got.depth, got.clearance) == (6.7, 5.4, 0.15)
    assert got.edge_margin == pytest.approx(4.35, abs=0.051)
    assert "spacing" not in got.model_dump()


def test_tongue_clamps_and_scales() -> None:
    tiny = resolve_joint(TongueJointSpec(auto=True), *TINY)  # t = 6 -> width 2, margin cap 1.5
    assert isinstance(tiny, TongueJointSpec)
    assert (tiny.width, tiny.depth, tiny.edge_margin) == (2.0, 3.0, 1.5)
    huge = resolve_joint(TongueJointSpec(auto=True), *HUGE)
    assert isinstance(huge, TongueJointSpec)
    assert (huge.width, huge.depth, huge.edge_margin) == (12.0, 9.6, 7.0)
    scaled = resolve_joint(TongueJointSpec(auto=True, size_scale=1.5, depth_scale=0.5), *MID)
    assert isinstance(scaled, TongueJointSpec)
    assert scaled.width == pytest.approx(10.0)  # clamp(20 / 3, 2, 12) * 1.5 = 10.0
    assert scaled.depth == pytest.approx(0.5 * clamp(0.8 * scaled.width, 3, 15), abs=0.051)
    slab = resolve_joint(TongueJointSpec(auto=True), _bounds(300, 300, 15), _bed(250), 2.0)
    assert isinstance(slab, TongueJointSpec)
    assert (slab.width, slab.depth, slab.edge_margin) == (5.0, 4.0, 3.5)


def test_magnet_stock_sizes() -> None:
    mid = resolve_joint(MagnetJointSpec(auto=True), *MID)  # t = 20 -> 8 x 3
    assert mid == MagnetJointSpec(
        diameter=8.0, height=3.0, spacing=80.0, edge_margin=5.0, clearance=0.1
    )
    # t = 6, margin cap 1.5: no stock magnet fits the 3 mm left, so it bottoms out at 4 x 2
    tiny = resolve_joint(MagnetJointSpec(auto=True), *TINY)
    assert isinstance(tiny, MagnetJointSpec)
    assert (tiny.diameter, tiny.height, tiny.spacing, tiny.edge_margin) == (4.0, 2.0, 20.0, 1.5)
    huge = resolve_joint(MagnetJointSpec(auto=True), *HUGE)  # t >= 25 -> 10 x 3
    assert isinstance(huge, MagnetJointSpec)
    assert (huge.diameter, huge.height, huge.spacing, huge.edge_margin) == (10.0, 3.0, 100.0, 7.0)
    assert huge.pocket_depth == pytest.approx(3.1)
    assert huge.depth == 0.0


def test_magnet_scales_snap_to_stock() -> None:
    small = resolve_joint(MagnetJointSpec(auto=True, size_scale=0.5), *MID)  # 8 * 0.5 -> 4 x 2
    assert isinstance(small, MagnetJointSpec)
    assert (small.diameter, small.height) == (4.0, 2.0)
    big = resolve_joint(MagnetJointSpec(auto=True, size_scale=3.0), *HUGE)  # 30 -> 12
    assert isinstance(big, MagnetJointSpec)
    assert (big.diameter, big.height) == (12.0, 3.0)
    # on t = 20 the margin (5) leaves 10 mm: 12 and 10 mm pockets step down to the 8 mm one
    capped = resolve_joint(MagnetJointSpec(auto=True, size_scale=3.0), *MID)
    assert isinstance(capped, MagnetJointSpec)
    assert (capped.diameter, capped.edge_margin) == (8.0, 5.0)
    between = resolve_joint(MagnetJointSpec(auto=True, size_scale=0.875), *MID)  # 7 -> 6 (ties low)
    assert isinstance(between, MagnetJointSpec)
    assert between.diameter == 6.0
    tall = resolve_joint(MagnetJointSpec(auto=True, depth_scale=1.4), *MID)  # 4.2 -> 4.0
    assert isinstance(tall, MagnetJointSpec)
    assert tall.height == 4.0
    flat = resolve_joint(MagnetJointSpec(auto=True, depth_scale=0.25), *MID)  # 0.75 -> 1.0
    assert isinstance(flat, MagnetJointSpec)
    assert flat.height == 1.0
    assert (tall.size_scale, tall.depth_scale) == (1.0, 1.4)


def test_magnet_steps_down_to_fit_the_thickness() -> None:
    # t = 15: nominal 8 mm, but margin = min(6, 3.75) = 3.8 leaves 7.4 mm for an 8.2 mm pocket
    got = resolve_joint(MagnetJointSpec(auto=True), _bounds(300, 300, 15), _bed(250), 2.0)
    assert isinstance(got, MagnetJointSpec)
    assert (got.diameter, got.height, got.edge_margin) == (6.0, 3.0, 3.8)
    assert got.diameter + 2 * got.clearance <= 15 - 2 * got.edge_margin
    # t = 17: margin 0.25 t = 4.25 -> 4.2; 17 - 8.4 = 8.6 >= 8.2 -> the nominal 8 mm fits
    got = resolve_joint(MagnetJointSpec(auto=True), _bounds(300, 300, 17), _bed(250), 2.0)
    assert isinstance(got, MagnetJointSpec)
    assert (got.diameter, got.edge_margin) == (8.0, 4.2)
