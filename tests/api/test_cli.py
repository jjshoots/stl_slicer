"""CLI tests (typer CliRunner). Pipeline-backed cases skip until core.pipeline exists."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import trimesh
from typer.testing import CliRunner

from stl_slicer.cli import app
from stl_slicer.core.models import DowelJointSpec, JigsawJointSpec, SliceResult

SPHERE = Path(__file__).parents[1] / "fixtures" / "sphere.stl"
runner = CliRunner()

needs_pipeline = pytest.mark.skipif(
    importlib.util.find_spec("stl_slicer.core.pipeline") is None,
    reason="stl_slicer.core.pipeline not available yet",
)


def test_openapi_prints_schema() -> None:
    res = runner.invoke(app, ["openapi"])
    assert res.exit_code == 0, res.output
    doc = json.loads(res.stdout)
    assert "/api/models" in doc["paths"]
    assert "SliceSpec" in doc["components"]["schemas"]


@pytest.mark.parametrize("bed", ["220x220", "axbxc", "10x0x10", "10x-5x10", ""])
def test_slice_rejects_bad_bed(bed: str, tmp_path: Path) -> None:
    res = runner.invoke(app, ["slice", str(SPHERE), "--bed", bed, "-o", str(tmp_path)])
    assert res.exit_code != 0


def test_slice_rejects_bad_joint(tmp_path: Path) -> None:
    res = runner.invoke(app, ["slice", str(SPHERE), "--joint", "glue", "-o", str(tmp_path)])
    assert res.exit_code != 0


def test_slice_rejects_missing_file(tmp_path: Path) -> None:
    res = runner.invoke(app, ["slice", str(tmp_path / "nope.stl"), "-o", str(tmp_path / "o")])
    assert res.exit_code != 0
    assert not (tmp_path / "o").exists()


@needs_pipeline
def test_slice_sphere_writes_pieces_and_manifest(tmp_path: Path) -> None:
    out = tmp_path / "out"
    args = ["slice", str(SPHERE), "--bed", "40x40x40", "--joint", "none", "-o", str(out)]
    res = runner.invoke(app, args)
    assert res.exit_code == 0, res.output
    stls = sorted(out.glob("*.stl"))
    assert len(stls) >= 2
    result = SliceResult.model_validate_json((out / "manifest.json").read_text())
    assert len(result.pieces) == len(stls)
    assert {p.piece_id for p in result.pieces} == {s.stem for s in stls}
    for stl in stls:
        mesh = trimesh.load(stl, file_type="stl", force="mesh")
        assert mesh.bounds[0][2] == pytest.approx(0.0, abs=1e-6)


@needs_pipeline
def test_slice_sphere_dovetail(tmp_path: Path) -> None:
    args = ["slice", str(SPHERE), "--bed", "40x40x40", "--joint", "dovetail", "-o", str(tmp_path)]
    res = runner.invoke(app, args)
    assert res.exit_code == 0, res.output
    assert (tmp_path / "manifest.json").is_file()


@needs_pipeline
def test_slice_joint_is_auto_sized_by_default(tmp_path: Path) -> None:
    args = ["slice", str(SPHERE), "--bed", "40x40x40", "--joint", "jigsaw", "-o", str(tmp_path)]
    res = runner.invoke(app, args)
    assert res.exit_code == 0, res.output
    result = SliceResult.model_validate_json((tmp_path / "manifest.json").read_text())
    joint = result.spec.joint
    assert isinstance(joint, JigsawJointSpec)
    assert joint.auto is False
    assert joint != JigsawJointSpec()  # sized from the model and bed, not the kind's defaults
    assert result.plan.resolved_joint == joint
    assert "joint (auto) jigsaw: " in res.output
    assert f"head_diameter={joint.head_diameter:g}" in res.output


@needs_pipeline
def test_slice_manual_uses_kind_defaults(tmp_path: Path) -> None:
    args = ["slice", str(SPHERE), "--bed", "40x40x40", "--joint", "dowel", "--manual"]
    res = runner.invoke(app, [*args, "-o", str(tmp_path)])
    assert res.exit_code == 0, res.output
    result = SliceResult.model_validate_json((tmp_path / "manifest.json").read_text())
    assert result.spec.joint == DowelJointSpec()
    assert result.plan.resolved_joint == DowelJointSpec()
    assert "joint (manual) dowel: " in res.output
