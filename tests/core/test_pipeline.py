"""Tests for core.pipeline — docs/00_design.md §3, §4.4 and docs/02_build_brief.md §2.5."""

from __future__ import annotations

import itertools

import pytest

from stl_slicer.core.errors import Cancelled, PlanError
from stl_slicer.core.geometry import LoadedModel, Mesh
from stl_slicer.core.models import (
    Axis,
    AxisCuts,
    DovetailJointSpec,
    DowelJointSpec,
    JigsawJointSpec,
    JointSpec,
    MeshAsset,
    NoJointSpec,
    PartitionSpec,
    PrintVolume,
    SliceResult,
    SliceSpec,
    WarningCode,
)
from stl_slicer.core.pipeline import CancelToken, cell_limits, slice_model

REL = 1e-6


def make_model(mesh: Mesh, model_id: str = "m") -> LoadedModel:
    asset = MeshAsset(
        model_id=model_id,
        filename="synthetic.stl",
        scale=1.0,
        triangle_count=mesh.triangle_count,
        bounds=mesh.bounds,
        volume=mesh.volume,
    )
    return LoadedModel(asset=asset, mesh=mesh)


def _spec(
    bed: float | tuple[float, float, float],
    joint: JointSpec | None = None,
    cuts: AxisCuts | None = None,
    axes: list[Axis] | None = None,
) -> SliceSpec:
    x, y, z = bed if isinstance(bed, tuple) else (bed, bed, bed)
    partition = (
        PartitionSpec(cuts=cuts, bed_margin=2.0)
        if axes is None
        else PartitionSpec(cuts=cuts, bed_margin=2.0, axes=axes)
    )
    return SliceSpec(
        print_volume=PrintVolume(x=x, y=y, z=z),
        partition=partition,
        joint=joint if joint is not None else NoJointSpec(),
    )


def _box(lo: tuple[float, float, float], hi: tuple[float, float, float]) -> Mesh:
    size = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    center = ((hi[0] + lo[0]) / 2, (hi[1] + lo[1]) / 2, (hi[2] + lo[2]) / 2)
    return Mesh.box(size, center)


def _codes(result: SliceResult) -> list[WarningCode]:
    return [w.code for w in result.warnings]


def _subjects(result: SliceResult, code: WarningCode) -> list[str | None]:
    return [w.subject for w in result.warnings if w.code is code]


def _assert_consistent(result: SliceResult) -> None:
    """Invariants every successful slice satisfies."""
    ids = {p.piece_id for p in result.pieces}
    assert len(ids) == len(result.pieces)
    for j in result.joints:
        assert j.male_piece in ids
        assert j.female_piece in ids
    stats = result.stats
    assert stats.piece_count == len(result.pieces)
    assert stats.max_overlap_volume == 0.0
    assert stats.output_volume <= stats.input_volume * (1 + REL)
    assert stats.output_volume == pytest.approx(sum(p.volume for p in result.pieces), rel=1e-12)
    for p in result.pieces:
        cx, cy, _ = p.bounds.center
        assert p.print_offset == pytest.approx((-cx, -cy, -p.bounds.min[2]))


# --- cell_limits ---------------------------------------------------------------------------------


def test_cell_limits_formula() -> None:
    bed = (220.0, 220.0, 250.0)
    dowel = cell_limits(_spec(bed, DowelJointSpec()))
    assert dowel.max_cell == pytest.approx((210, 210, 240))
    assert dowel.min_cell == pytest.approx(7.15)
    none = cell_limits(_spec(bed, NoJointSpec()))
    assert none.max_cell == pytest.approx((216, 216, 246))
    assert none.min_cell == pytest.approx(1.0)


def test_cell_limits_uses_joint_depth() -> None:
    limits = cell_limits(_spec(100.0, DovetailJointSpec(depth=10.0, clearance=0.2)))
    assert limits.max_cell == pytest.approx((86, 86, 86))
    assert limits.min_cell == pytest.approx(11.2)


# --- end to end ----------------------------------------------------------------------------------


def test_sphere_dovetail_end_to_end() -> None:
    sphere = Mesh.sphere(30.0, 64)
    out = slice_model(make_model(sphere), _spec(40.0, DovetailJointSpec()), job_id="j1")
    result = out.result
    assert result.job_id == "j1"
    assert result.model_id == "m"
    assert len(result.plan.cells) == 8  # max_cell 40 - 6 - 4 = 30 -> 2x2x2
    assert len(result.pieces) == 8 == len(out.pieces)
    assert [p.info for p in out.pieces] == result.pieces
    assert len(result.joints) > 0
    assert all(j.kind == "dovetail" for j in result.joints)
    assert all(p.fits_bed for p in result.pieces)
    assert WarningCode.PIECE_OVERSIZE not in _codes(result)
    assert result.stats.volume_ratio > 0.95
    _assert_consistent(result)


def test_sphere_dowel_end_to_end() -> None:
    sphere = Mesh.sphere(30.0, 64)
    result = slice_model(make_model(sphere), _spec(40.0, DowelJointSpec())).result
    assert len(result.pieces) == 8
    assert len(result.joints) > 0
    assert {j.interface_id for j in result.joints} == {i.id for i in result.plan.interfaces}
    assert all(p.fits_bed for p in result.pieces)
    assert WarningCode.PIECE_OVERSIZE not in _codes(result)  # JOINT_CLIPPED may appear
    assert result.stats.volume_ratio > 0.95
    _assert_consistent(result)


def test_hollow_box_dowels_deepest_point_fallback() -> None:
    """Every interface of a hollow box sees an L-shaped slice of the wall ring; the grid point
    at the centre of its bounds falls in the hole, so placement relies on the deepest point.

    A 10 mm wall cannot hold the default 8 mm dowel with a 3 mm edge margin (8 + 2*3 > 10), so
    a 4 mm dowel with a 2 mm margin is used (see the default-spec test below)."""
    hollow = Mesh.box((80, 80, 80)) - Mesh.box((60, 60, 60))
    spec = _spec(60.0, DowelJointSpec(diameter=4.0, edge_margin=2.0))
    result = slice_model(make_model(hollow), spec).result
    assert len(result.plan.cells) == 8  # max_cell 60 - 6 - 4 = 50 -> 2x2x2
    assert len(result.pieces) == 8
    assert {j.interface_id for j in result.joints} == {i.id for i in result.plan.interfaces}
    assert WarningCode.NO_CONTACT_FOR_JOINT not in _codes(result)
    for j in result.joints:  # in the wall corner of the quadrant, not at the rect centre
        assert min(abs(j.placement.u), abs(j.placement.v)) > 10
    assert result.stats.volume_ratio > 0.95
    _assert_consistent(result)


def test_hollow_box_default_dowel_too_big_for_wall_warns() -> None:
    hollow = Mesh.box((80, 80, 80)) - Mesh.box((60, 60, 60))
    result = slice_model(make_model(hollow), _spec(60.0, DowelJointSpec())).result
    assert result.joints == []
    assert sorted(s or "" for s in _subjects(result, WarningCode.NO_CONTACT_FOR_JOINT)) == sorted(
        i.id for i in result.plan.interfaces
    )
    assert all("placement" in w.message for w in result.warnings)
    assert len(result.pieces) == 8
    _assert_consistent(result)


def test_nojoint_sphere_conserves_volume_exactly() -> None:
    sphere = Mesh.sphere(30.0, 64)
    result = slice_model(make_model(sphere), _spec(40.0, NoJointSpec())).result
    assert result.stats.output_volume == pytest.approx(result.stats.input_volume, rel=1e-9)
    assert result.stats.max_overlap_volume == 0.0
    assert result.joints == []
    assert len(result.pieces) == 8
    assert all(p.fits_bed for p in result.pieces)
    assert result.warnings == []
    _assert_consistent(result)


# --- progress and cancellation -------------------------------------------------------------------


class _Recorder:
    def __init__(self, cancel_on: str | None = None, token: CancelToken | None = None) -> None:
        self.events: list[tuple[float, str]] = []
        self._cancel_on = cancel_on
        self._token = token

    def __call__(self, fraction: float, step: str) -> None:
        self.events.append((fraction, step))
        if self._token is not None and self._cancel_on and step.startswith(self._cancel_on):
            self._token.cancel()

    @property
    def steps(self) -> list[str]:
        return [s for _, s in self.events]


def test_progress_sequence_and_cancel() -> None:
    model = make_model(Mesh.sphere(30.0, 32))
    spec = _spec(40.0, DowelJointSpec())

    rec = _Recorder()
    slice_model(model, spec, progress=rec)
    steps = rec.steps
    assert steps[0] == "planning"
    assert steps[-1] == "done"
    for expected in ("contacts", "joints", "checking"):
        assert expected in steps
    assert "cutting 1/8" in steps
    assert "cutting 8/8" in steps
    order = [steps.index(s) for s in ("planning", "contacts", "joints", "cutting 1/8", "checking")]
    assert order == sorted(order)
    fractions = [f for f, _ in rec.events]
    assert all(0.0 <= f <= 1.0 for f in fractions)
    assert all(a <= b for a, b in itertools.pairwise(fractions))

    pre = CancelToken()
    pre.cancel()
    assert pre.is_cancelled
    rec = _Recorder()
    with pytest.raises(Cancelled):
        slice_model(model, spec, progress=rec, cancel=pre)
    assert not any(s.startswith("cutting") for s in rec.steps)

    token = CancelToken()
    assert not token.is_cancelled
    rec = _Recorder(cancel_on="cutting 2/", token=token)
    with pytest.raises(Cancelled, match="cancelled"):
        slice_model(model, spec, progress=rec, cancel=token)
    assert rec.steps[-1].startswith("cutting 2/")
    assert "checking" not in rec.steps
    assert "done" not in rec.steps


def test_cancel_token_raise_if_cancelled() -> None:
    token = CancelToken()
    token.raise_if_cancelled()
    token.cancel()
    with pytest.raises(Cancelled):
        token.raise_if_cancelled()


# --- per-piece fields and warnings ---------------------------------------------------------------


def test_print_offset_and_fits_bed() -> None:
    bar = _box((10, -20, 5), (110, 10, 35))
    result = slice_model(make_model(bar), _spec(60.0)).result
    assert len(result.pieces) == 2
    for p in result.pieces:
        cx, cy, _ = p.bounds.center
        assert p.print_offset == pytest.approx((-cx, -cy, -p.bounds.min[2]))
        assert p.fits_bed
    assert result.pieces[0].print_offset == pytest.approx((-35.0, 5.0, -5.0))
    assert result.warnings == []

    big = _box((0, 0, 0), (100, 100, 100))
    result = slice_model(make_model(big), _spec(60.0, cuts=AxisCuts())).result
    assert len(result.pieces) == 1
    (piece,) = result.pieces
    assert piece.fits_bed is False
    assert piece.print_offset == pytest.approx((-50.0, -50.0, 0.0))
    assert WarningCode.CELL_OVERSIZE in _codes(result)
    assert _subjects(result, WarningCode.PIECE_OVERSIZE) == [piece.piece_id]


def test_disconnected_piece_warning() -> None:
    blobs = _box((0, 0, 0), (10, 10, 10)) | _box((30, 30, 30), (40, 40, 40))
    result = slice_model(make_model(blobs), _spec(60.0)).result
    assert len(result.pieces) == 1
    (piece,) = result.pieces
    assert piece.component_count == 2
    assert _subjects(result, WarningCode.DISCONNECTED_PIECE) == [piece.piece_id]


def test_no_contact_warning_when_region_empty() -> None:
    parts = _box((0, 0, 0), (49, 100, 100)) | _box((51, 0, 0), (100, 100, 100))
    spec = _spec(60.0, DowelJointSpec(), cuts=AxisCuts(x=[50.0], y=[50.0], z=[50.0]))
    result = slice_model(make_model(parts), spec).result
    no_contact = set(_subjects(result, WarningCode.NO_CONTACT_FOR_JOINT))
    x_ifaces = {i.id for i in result.plan.interfaces if i.axis.value == "x"}
    assert no_contact == x_ifaces
    assert not x_ifaces & {j.interface_id for j in result.joints}
    assert len(result.pieces) == 8
    _assert_consistent(result)

    # Planned cut in x only (max_cell 50 x 110 x 110): one interface, both cells occupied.
    spec = _spec((60, 120, 120), DowelJointSpec())
    result = slice_model(make_model(parts), spec).result
    (iface,) = result.plan.interfaces
    assert _subjects(result, WarningCode.NO_CONTACT_FOR_JOINT) == [iface.id]
    assert result.joints == []
    assert len(result.pieces) == 2
    _assert_consistent(result)


def test_no_contact_not_warned_next_to_empty_cell() -> None:
    """An L-shaped slab leaves cell x1_y1 empty: its two interfaces have no contact but must not
    warn, since the empty cell produces no piece to join."""
    ell = _box((0, 0, 0), (100, 40, 20)) | _box((0, 0, 0), (40, 100, 20))
    result = slice_model(make_model(ell), _spec(60.0, DowelJointSpec())).result
    assert len(result.plan.cells) == 4
    assert sorted(p.piece_id for p in result.pieces) == [
        "p_x0_y0_z0",
        "p_x0_y1_z0",
        "p_x1_y0_z0",
    ]
    assert WarningCode.NO_CONTACT_FOR_JOINT not in _codes(result)
    assert len({j.interface_id for j in result.joints}) == 2
    _assert_consistent(result)


@pytest.mark.parametrize(
    "joint", [DovetailJointSpec(), JigsawJointSpec(depth=10, neck_width=5, head_diameter=8)]
)
def test_assembly_conflict_warning(joint: JointSpec) -> None:
    # 90 mm cube, bed 60 -> 2x2x2; every interface is 45x45 (a tie -> slide along v):
    # X cuts slide along Z, Y cuts along X, Z cuts along Y -> every piece conflicts.
    cube = _box((0, 0, 0), (90, 90, 90))
    result = slice_model(make_model(cube), _spec(60.0, joint)).result
    assert len(result.plan.cells) == 8
    assert len(result.pieces) == 8
    assert len(result.joints) >= 12
    conflicts = _subjects(result, WarningCode.ASSEMBLY_CONFLICT)
    assert sorted(s or "" for s in conflicts) == sorted(p.piece_id for p in result.pieces)
    _assert_consistent(result)

    # flat slab, cuts in x and y only (bed 70 -> 2x2 for both depths): both slide along Z (the
    # thickness) -> no conflict
    slab = _box((0, 0, 0), (100, 100, 20))
    result = slice_model(make_model(slab), _spec(70.0, joint)).result
    assert len(result.pieces) == 4
    assert len(result.joints) == 4
    assert WarningCode.ASSEMBLY_CONFLICT not in _codes(result)
    _assert_consistent(result)


def test_dovetail_y_cut_on_a_slab_slides_along_z() -> None:
    """A Y cut has frame (u=Z, v=X); on a slab u is the thinner extent, so the strip runs along
    Z and is placed across X: the male spans the whole slab thickness."""
    strip = _box((0, 0, 0), (40, 100, 20))
    out = slice_model(make_model(strip), _spec(60.0, DovetailJointSpec()))
    result = out.result
    assert [i.axis for i in result.plan.interfaces] == [Axis.Y]
    assert len(result.joints) == 1
    assert result.joints[0].placement.v == pytest.approx(20.0 - 20.0)  # v = X, centred at 20
    _assert_consistent(result)


def test_dowels_never_raise_assembly_conflict() -> None:
    slab = _box((0, 0, 0), (100, 100, 20))
    result = slice_model(make_model(slab), _spec(60.0, DowelJointSpec())).result
    assert len(result.joints) > 0
    assert WarningCode.ASSEMBLY_CONFLICT not in _codes(result)


def test_result_serialises() -> None:
    sphere = Mesh.sphere(30.0, 32)
    result = slice_model(make_model(sphere), _spec(40.0, DovetailJointSpec()), job_id="x").result
    again = SliceResult.model_validate_json(result.model_dump_json())
    assert again == result


def test_dovetail_full_length_strip_is_never_reported_as_clipped() -> None:
    """The dovetail strip spans exactly the interface rect along v, so clipping to the female
    cell removes nothing: no JOINT_CLIPPED, whether or not there is a cut along the slide axis."""
    slab = _box((0, 0, 0), (100, 50, 20))
    result = slice_model(make_model(slab), _spec(60, DovetailJointSpec())).result
    _assert_consistent(result)
    assert len(result.joints) > 0
    assert WarningCode.JOINT_CLIPPED not in _codes(result)

    tall = _box((0, 0, 0), (60, 30, 60))  # bed 40 -> x-cut and z-cut; x-dovetails slide along Z
    result2 = slice_model(make_model(tall), _spec(40, DovetailJointSpec())).result
    _assert_consistent(result2)
    assert any(i.axis.value == "z" for i in result2.plan.interfaces)
    assert WarningCode.JOINT_CLIPPED not in _codes(result2)


# --- cut-axis selection and jigsaw -----------------------------------------------------------


def test_axes_restriction_flat_slab_no_z_cuts() -> None:
    slab = _box((0, 0, 0), (300, 300, 15))
    result = slice_model(make_model(slab), _spec(100.0, axes=[Axis.X, Axis.Y])).result
    assert result.plan.cuts.z == []
    assert len(result.plan.cuts.x) == 3 and len(result.plan.cuts.y) == 3  # max_cell 96 -> 4x4
    assert len(result.pieces) == 16
    assert all(p.fits_bed for p in result.pieces)
    assert result.warnings == []
    _assert_consistent(result)


def test_axes_restriction_oversize_axis_is_reported_twice() -> None:
    """Excluding an axis the model overflows yields CELL_OVERSIZE (planner, subject = axis) and
    PIECE_OVERSIZE per piece, exactly as before."""
    tall = _box((0, 0, 0), (50, 50, 150))
    result = slice_model(make_model(tall), _spec(100.0, axes=[Axis.X, Axis.Y])).result
    assert result.plan.cuts == AxisCuts()
    assert len(result.pieces) == 1
    assert _subjects(result, WarningCode.CELL_OVERSIZE) == ["z"]
    assert _subjects(result, WarningCode.PIECE_OVERSIZE) == ["p_x0_y0_z0"]
    assert not result.pieces[0].fits_bed


def test_axes_restriction_rejects_explicit_cut_on_excluded_axis() -> None:
    slab = _box((0, 0, 0), (100, 100, 20))
    with pytest.raises(PlanError, match="excluded"):
        slice_model(make_model(slab), _spec(60.0, cuts=AxisCuts(z=[10]), axes=[Axis.X]))


def test_jigsaw_flat_puzzle_end_to_end() -> None:
    slab = _box((0, 0, 0), (200, 200, 15))
    # bed 130: max_cell = 130 - 18 (depth) - 4 = 108 -> 2x2; pieces are 100 + 18 = 118 mm wide
    spec = _spec(130.0, JigsawJointSpec(), axes=[Axis.X, Axis.Y])
    result = slice_model(make_model(slab), spec).result
    assert result.plan.cuts.z == []
    assert len(result.plan.cells) == 4
    assert len(result.pieces) == 4
    assert result.stats.max_overlap_volume == 0.0
    assert all(p.fits_bed for p in result.pieces)
    assert len(result.joints) > 0
    assert all(j.kind == "jigsaw" for j in result.joints)
    # both X and Y cuts slide along Z (the 15 mm thickness): a flat puzzle, no conflicts
    assert {j.interface_id for j in result.joints} == {i.id for i in result.plan.interfaces}
    assert result.warnings == []
    _assert_consistent(result)
