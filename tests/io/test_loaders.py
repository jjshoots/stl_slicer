"""Tests for stl_slicer.io.loaders using real (synthetic) geometry."""

from __future__ import annotations

import re

import numpy as np
import pytest
import trimesh

from stl_slicer.core.errors import MeshLoadError
from stl_slicer.core.geometry import Mesh
from stl_slicer.core.models import WarningCode
from stl_slicer.io.loaders import SUPPORTED_EXTENSIONS, load_mesh


def _export(mesh: Mesh, file_type: str) -> bytes:
    vertices, faces = mesh.to_arrays()
    data = trimesh.Trimesh(vertices=vertices, faces=faces, process=False).export(
        file_type=file_type
    )
    return data if isinstance(data, bytes) else data.encode()


@pytest.fixture
def box_stl() -> bytes:
    return _export(Mesh.box((10, 20, 30)), "stl")


def test_supported_extensions() -> None:
    assert {"stl", "obj", "ply", "off", "3mf", "glb", "gltf"} == SUPPORTED_EXTENSIONS


def test_stl_round_trip(box_stl: bytes) -> None:
    loaded = load_mesh(box_stl, "box.stl")
    asset = loaded.asset
    assert asset.triangle_count == 12
    assert loaded.mesh.triangle_count == 12
    assert asset.volume == pytest.approx(6000.0, rel=1e-6)
    assert asset.bounds.min == pytest.approx((-5.0, -10.0, -15.0))
    assert asset.bounds.max == pytest.approx((5.0, 10.0, 15.0))
    assert asset.filename == "box.stl"
    assert asset.scale == 1.0


def test_uppercase_extension(box_stl: bytes) -> None:
    assert load_mesh(box_stl, "BOX.STL").asset.triangle_count == 12


def test_scale_applied_at_upload(box_stl: bytes) -> None:
    loaded = load_mesh(box_stl, "box.stl", scale=2.0)
    assert loaded.asset.scale == 2.0
    assert loaded.asset.volume == pytest.approx(48000.0, rel=1e-6)
    assert loaded.mesh.volume == pytest.approx(48000.0, rel=1e-6)
    assert loaded.asset.bounds.max == pytest.approx((10.0, 20.0, 30.0))


@pytest.mark.parametrize("scale", [0.0, -1.0])
def test_non_positive_scale_rejected(box_stl: bytes, scale: float) -> None:
    with pytest.raises(MeshLoadError, match="scale"):
        load_mesh(box_stl, "box.stl", scale=scale)


def test_unmerged_stl_emits_vertices_merged_warning() -> None:
    data = trimesh.creation.box(extents=(4, 5, 6)).export(file_type="stl")
    assert isinstance(data, bytes)
    loaded = load_mesh(data, "soup.stl")
    codes = [w.code for w in loaded.asset.warnings]
    assert codes == [WarningCode.VERTICES_MERGED]
    assert loaded.asset.warnings[0].message == "merged 36 vertices into 8"
    assert loaded.asset.volume == pytest.approx(120.0, rel=1e-6)


def test_no_warning_when_nothing_to_merge() -> None:
    # OBJ keeps shared vertices, so merging changes nothing.
    loaded = load_mesh(_export(Mesh.box((1, 2, 3)), "obj"), "box.obj")
    assert loaded.asset.warnings == []


def test_open_box_is_rejected() -> None:
    vertices, faces = Mesh.box((10, 10, 10)).to_arrays()
    open_box = trimesh.Trimesh(vertices=vertices, faces=faces[:-1], process=False)
    data = open_box.export(file_type="stl")
    assert isinstance(data, bytes)
    with pytest.raises(MeshLoadError, match="manifold"):
        load_mesh(data, "open.stl")


@pytest.mark.parametrize("filename", ["box.dxf", "box", "box.", "archive.stl.zip"])
def test_unsupported_or_missing_extension(box_stl: bytes, filename: str) -> None:
    with pytest.raises(MeshLoadError):
        load_mesh(box_stl, filename)


@pytest.mark.parametrize(
    ("data", "filename"),
    [
        (b"this is not a mesh at all" * 20, "garbage.stl"),
        (b"\x00" * 200, "zeros.stl"),
        (b"not an obj", "garbage.obj"),
        (b"\xff\xfe\x00garbage", "garbage.glb"),
        (b"", "empty.stl"),
        (b"", "empty.obj"),
    ],
)
def test_garbage_and_empty_rejected(data: bytes, filename: str) -> None:
    with pytest.raises(MeshLoadError):
        load_mesh(data, filename)


def test_obj_round_trip() -> None:
    loaded = load_mesh(_export(Mesh.box((2, 4, 6), center=(1, 2, 3)), "obj"), "part.obj")
    assert loaded.asset.triangle_count == 12
    assert loaded.asset.volume == pytest.approx(48.0, rel=1e-6)
    assert loaded.asset.bounds.min == pytest.approx((0.0, 0.0, 0.0))
    assert loaded.asset.bounds.max == pytest.approx((2.0, 4.0, 6.0))


def test_glb_round_trip() -> None:
    loaded = load_mesh(_export(Mesh.sphere(5.0, 32), "glb"), "ball.glb")
    assert loaded.asset.volume == pytest.approx(Mesh.sphere(5.0, 32).volume, rel=1e-4)


def test_model_id_is_12_hex_and_unique(box_stl: bytes) -> None:
    a = load_mesh(box_stl, "box.stl").asset.model_id
    b = load_mesh(box_stl, "box.stl").asset.model_id
    assert re.fullmatch(r"[0-9a-f]{12}", a)
    assert re.fullmatch(r"[0-9a-f]{12}", b)
    assert a != b


def test_loaded_mesh_matches_asset(box_stl: bytes) -> None:
    loaded = load_mesh(box_stl, "box.stl")
    vertices, _ = loaded.mesh.to_arrays()
    assert np.asarray(loaded.asset.bounds.min) == pytest.approx(vertices.min(axis=0))
    assert loaded.asset.bounds == loaded.mesh.bounds
