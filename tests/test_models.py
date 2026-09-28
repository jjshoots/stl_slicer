import pytest
from pydantic import TypeAdapter, ValidationError

from stl_slicer.core.models import (
    Axis,
    Bounds,
    CellIndex,
    DovetailJointSpec,
    DowelJointSpec,
    JointSpec,
    NoJointSpec,
    PrintVolume,
    SliceSpec,
)


def test_bounds_size_center_extent() -> None:
    b = Bounds(min=(0, -1, 2), max=(4, 1, 2))
    assert b.size == (4, 2, 0)
    assert b.center == (2, 0, 2)
    assert b.extent(Axis.Y) == 2


def test_bounds_rejects_inverted() -> None:
    with pytest.raises(ValidationError):
        Bounds(min=(1, 0, 0), max=(0, 1, 1))


def test_bounds_fits_in_bed() -> None:
    assert Bounds(min=(0, 0, 0), max=(10, 10, 10)).fits_in(PrintVolume(x=10, y=10, z=10))
    assert not Bounds(min=(0, 0, 0), max=(10.1, 10, 10)).fits_in(PrintVolume(x=10, y=10, z=10))


def test_axis_uv_is_cyclic() -> None:
    assert Axis.X.uv == (Axis.Y, Axis.Z)
    assert Axis.Y.uv == (Axis.Z, Axis.X)
    assert Axis.Z.uv == (Axis.X, Axis.Y)


def test_cell_index_id_and_neighbourhood() -> None:
    a, b, c = CellIndex(i=0, j=0, k=0), CellIndex(i=1, j=1, k=1), CellIndex(i=2, j=0, k=0)
    assert a.id == "x0_y0_z0"
    assert a.is_neighbour(b) and not a.is_neighbour(c)


def test_joint_spec_discriminated_union_round_trips() -> None:
    adapter: TypeAdapter[NoJointSpec | DowelJointSpec | DovetailJointSpec] = TypeAdapter(JointSpec)
    spec = adapter.validate_python({"kind": "dovetail", "neck_width": 6, "head_width": 9})
    assert isinstance(spec, DovetailJointSpec)
    assert adapter.validate_python(adapter.dump_python(spec)) == spec
    assert isinstance(adapter.validate_python({"kind": "none"}), NoJointSpec)


def test_dovetail_must_flare() -> None:
    with pytest.raises(ValidationError):
        DovetailJointSpec(neck_width=10, head_width=10)


def test_every_joint_spec_exposes_depth_and_clearance() -> None:
    assert NoJointSpec().depth == 0 and NoJointSpec().clearance == 0
    assert DowelJointSpec().depth == 6 and DowelJointSpec().clearance == 0.15


def test_slice_spec_defaults_to_no_joint() -> None:
    spec = SliceSpec(print_volume=PrintVolume(x=200, y=200, z=200))
    assert spec.joint.kind == "none"
    assert spec.male_side == "lower"


def test_slice_spec_json_schema_uses_discriminator() -> None:
    schema = SliceSpec.model_json_schema()
    joint = schema["properties"]["joint"]
    assert "discriminator" in joint or "oneOf" in joint


def test_cut_plan_cell_lookup_is_cached_and_not_serialised() -> None:
    from stl_slicer.core.models import AxisCuts, Bounds, Cell, CellIndex, CellLimits, CutPlan

    bounds = Bounds(min=(0, 0, 0), max=(10, 10, 10))
    cells = [
        Cell(
            index=CellIndex(i=i, j=0, k=0),
            bounds=Bounds(min=(5 * i, 0, 0), max=(5 * i + 5, 10, 10)),
        )
        for i in range(2)
    ]
    plan = CutPlan(
        bounds=bounds,
        limits=CellLimits(max_cell=(5, 10, 10)),
        cuts=AxisCuts(x=[5.0]),
        cells=cells,
        interfaces=[],
    )
    assert plan.cell(CellIndex(i=1, j=0, k=0)) is cells[1]
    assert plan.cells_by_id is plan.cells_by_id  # built once
    with pytest.raises(KeyError, match="x7_y0_z0"):
        plan.cell(CellIndex(i=7, j=0, k=0))
    assert "cells_by_id" not in plan.model_dump()
    assert plan == CutPlan.model_validate_json(plan.model_dump_json())


def test_jigsaw_spec_validates_knob_shape() -> None:
    from stl_slicer.core.models import JigsawJointSpec

    assert JigsawJointSpec().kind == "jigsaw"
    with pytest.raises(ValidationError):
        JigsawJointSpec(neck_width=10, head_diameter=10)
    with pytest.raises(ValidationError):
        JigsawJointSpec(head_diameter=14, depth=12)


def test_partition_axes_default_to_all_three() -> None:
    from stl_slicer.core.models import PartitionSpec

    assert PartitionSpec().axes == [Axis.X, Axis.Y, Axis.Z]
    assert PartitionSpec(axes=["x", "y"]).axes == [Axis.X, Axis.Y]
