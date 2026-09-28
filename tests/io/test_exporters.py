"""Tests for stl_slicer.io.exporters using real (synthetic) geometry."""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
import trimesh

from stl_slicer.core.geometry import Mesh, Piece
from stl_slicer.core.models import (
    AxisCuts,
    Bounds,
    Cell,
    CellIndex,
    CellLimits,
    CutPlan,
    PieceInfo,
    PrintVolume,
    SliceResult,
    SliceSpec,
    SliceStats,
)
from stl_slicer.io.exporters import (
    mesh_to_glb,
    mesh_to_stl,
    piece_to_stl,
    pieces_to_glb,
    pieces_to_zip,
)


def _make_piece(i: int, mesh: Mesh) -> Piece:
    cell = CellIndex(i=i, j=0, k=0)
    b = mesh.bounds
    cx, cy, _ = b.center
    info = PieceInfo(
        piece_id=cell.id,
        cell=cell,
        bounds=b,
        volume=mesh.volume,
        triangle_count=mesh.triangle_count,
        component_count=1,
        fits_bed=True,
        print_offset=(-cx, -cy, -b.min[2]),
    )
    return Piece(info=info, mesh=mesh)


@pytest.fixture
def pieces() -> list[Piece]:
    return [
        _make_piece(0, Mesh.box((10, 10, 10), center=(5, 5, 5))),
        _make_piece(1, Mesh.box((10, 10, 20), center=(15, 7, 12))),
    ]


def _result(pieces: list[Piece]) -> SliceResult:
    bounds = Bounds(min=(0, 0, 0), max=(20, 12, 22))
    plan = CutPlan(
        bounds=bounds,
        limits=CellLimits(max_cell=(10, 100, 100)),
        cuts=AxisCuts(x=[10.0]),
        cells=[Cell(index=p.info.cell, bounds=p.info.bounds) for p in pieces],
        interfaces=[],
    )
    volume = sum(p.info.volume for p in pieces)
    return SliceResult(
        job_id="job123",
        model_id="model456",
        spec=SliceSpec(print_volume=PrintVolume(x=100, y=100, z=100)),
        plan=plan,
        pieces=[p.info for p in pieces],
        joints=[],
        stats=SliceStats(
            piece_count=len(pieces),
            input_volume=volume,
            output_volume=volume,
            max_overlap_volume=0.0,
            duration_s=0.01,
        ),
    )


def _load_trimesh(data: bytes, file_type: str) -> trimesh.Trimesh:
    tm = trimesh.load(file_obj=BytesIO(data), file_type=file_type, force="mesh", process=False)
    assert isinstance(tm, trimesh.Trimesh)
    tm.merge_vertices()
    return tm


def test_mesh_to_stl_round_trip() -> None:
    mesh = Mesh.box((10, 20, 30))
    data = mesh_to_stl(mesh)
    assert isinstance(data, bytes)
    assert len(data) == 84 + 50 * 12  # binary STL: header + count + 50 bytes per triangle
    tm = _load_trimesh(data, "stl")
    assert len(tm.faces) == 12
    assert tm.is_watertight
    assert tm.volume == pytest.approx(6000.0, rel=1e-6)


def test_mesh_to_glb_round_trip() -> None:
    mesh = Mesh.sphere(4.0, 24)
    data = mesh_to_glb(mesh)
    assert data[:4] == b"glTF"
    tm = _load_trimesh(data, "glb")
    assert len(tm.faces) == mesh.triangle_count
    assert tm.volume == pytest.approx(mesh.volume, rel=1e-5)


def test_pieces_to_glb_names_and_model_frame(pieces: list[Piece]) -> None:
    data = pieces_to_glb(pieces)
    assert data[:4] == b"glTF"
    scene = trimesh.load(file_obj=BytesIO(data), file_type="glb")
    assert isinstance(scene, trimesh.Scene)
    ids = {p.info.piece_id for p in pieces}
    assert ids == {"x0_y0_z0", "x1_y0_z0"}
    assert set(scene.geometry) == ids
    assert set(scene.graph.nodes_geometry) == ids
    for node in scene.graph.nodes_geometry:
        _, geom_name = scene.graph[node]
        assert geom_name == node
    for piece in pieces:
        geom = scene.geometry[piece.info.piece_id]
        assert len(geom.faces) == piece.info.triangle_count
        assert tuple(geom.bounds[0]) == pytest.approx(piece.info.bounds.min, abs=1e-5)
        assert tuple(geom.bounds[1]) == pytest.approx(piece.info.bounds.max, abs=1e-5)
    # Scene-level bounds are the union in the model frame (no node transforms applied).
    assert tuple(scene.bounds[0]) == pytest.approx((0.0, 0.0, 0.0), abs=1e-5)
    assert tuple(scene.bounds[1]) == pytest.approx((20.0, 12.0, 22.0), abs=1e-5)


def test_pieces_to_glb_empty() -> None:
    data = pieces_to_glb([])
    assert data[:4] == b"glTF"
    assert len(data) % 4 == 0
    scene = trimesh.load(file_obj=BytesIO(data), file_type="glb")
    assert isinstance(scene, trimesh.Scene)
    assert len(scene.geometry) == 0


def test_pieces_to_zip(pieces: list[Piece]) -> None:
    result = _result(pieces)
    data = pieces_to_zip(pieces, result)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert zf.namelist() == ["x0_y0_z0.stl", "x1_y0_z0.stl", "manifest.json"]
        assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in zf.infolist())
        assert SliceResult.model_validate_json(zf.read("manifest.json")) == result
        for piece in pieces:
            tm = _load_trimesh(zf.read(f"{piece.info.piece_id}.stl"), "stl")
            assert len(tm.faces) == piece.info.triangle_count
            assert tm.volume == pytest.approx(piece.info.volume, rel=1e-6)
            lo, hi = tm.bounds
            assert lo[2] == pytest.approx(0.0, abs=1e-5)
            assert (lo[0] + hi[0]) / 2 == pytest.approx(0.0, abs=1e-5)
            assert (lo[1] + hi[1]) / 2 == pytest.approx(0.0, abs=1e-5)
            size = piece.info.bounds.size
            assert tuple(hi - lo) == pytest.approx(size, abs=1e-5)


def test_pieces_to_zip_does_not_mutate_pieces(pieces: list[Piece]) -> None:
    before = [p.mesh.bounds for p in pieces]
    pieces_to_zip(pieces, _result(pieces))
    assert [p.mesh.bounds for p in pieces] == before


def test_pieces_to_zip_empty(pieces: list[Piece]) -> None:
    data = pieces_to_zip([], _result(pieces))
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert zf.namelist() == ["manifest.json"]


def test_piece_to_stl_is_print_frame(pieces: list[Piece]) -> None:
    piece = pieces[1]
    data = piece_to_stl(piece)
    assert data == mesh_to_stl(piece.mesh.translate(piece.info.print_offset))
    tm = _load_trimesh(data, "stl")
    assert tm.bounds[0] == pytest.approx((-5, -5, 0), abs=1e-6)
    assert tm.bounds[1] == pytest.approx((5, 5, 20), abs=1e-6)


def test_pieces_to_zip_uses_piece_to_stl(pieces: list[Piece]) -> None:
    with zipfile.ZipFile(BytesIO(pieces_to_zip(pieces, _result(pieces)))) as zf:
        for piece in pieces:
            assert zf.read(f"{piece.info.piece_id}.stl") == piece_to_stl(piece)
