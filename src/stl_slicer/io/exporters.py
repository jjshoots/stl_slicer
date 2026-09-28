"""Serialise meshes and pieces for the viewer (GLB, model frame) and printing (STL, print frame).

See docs/00_design.md R6: GLB scenes stay in the model frame so the viewer can explode pieces;
STL downloads are translated by `PieceInfo.print_offset` (min z = 0, xy-centred).
"""

from __future__ import annotations

import json
import struct
import zipfile
from collections.abc import Sequence
from io import BytesIO

import trimesh

from stl_slicer.core.geometry import Mesh, Piece
from stl_slicer.core.models import SliceResult

__all__ = ["mesh_to_glb", "mesh_to_stl", "pieces_to_glb", "pieces_to_zip"]


def _to_trimesh(mesh: Mesh) -> trimesh.Trimesh:
    vertices, faces = mesh.to_arrays()
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def _as_bytes(data: object) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode()
    raise TypeError(f"unexpected export payload type {type(data).__name__}")


def mesh_to_stl(mesh: Mesh) -> bytes:
    """Binary STL of `mesh`, in whatever frame the mesh is in."""
    return _as_bytes(_to_trimesh(mesh).export(file_type="stl"))


def mesh_to_glb(mesh: Mesh) -> bytes:
    """Binary glTF of `mesh` (single node)."""
    return _as_bytes(_to_trimesh(mesh).export(file_type="glb"))


def _empty_glb() -> bytes:
    """A minimal valid GLB with one empty scene (trimesh refuses to export empty scenes)."""
    doc = {"asset": {"version": "2.0", "generator": "stl-slicer"}, "scene": 0, "scenes": [{}]}
    chunk = json.dumps(doc, separators=(",", ":")).encode()
    chunk += b" " * (-len(chunk) % 4)
    header = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(chunk))
    return header + struct.pack("<I4s", len(chunk), b"JSON") + chunk


def pieces_to_glb(pieces: Sequence[Piece]) -> bytes:
    """One GLB scene, model frame; geometry and node are both named by `piece_id`."""
    if not pieces:
        return _empty_glb()
    scene = trimesh.Scene()
    for piece in pieces:
        pid = piece.info.piece_id
        scene.add_geometry(_to_trimesh(piece.mesh), geom_name=pid, node_name=pid)
    return _as_bytes(scene.export(file_type="glb"))  # type: ignore[no-untyped-call]


def pieces_to_zip(pieces: Sequence[Piece], result: SliceResult) -> bytes:
    """Zip of `{piece_id}.stl` (print frame) for each piece plus `manifest.json` (= result)."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for piece in pieces:
            printed = piece.mesh.translate(piece.info.print_offset)
            zf.writestr(f"{piece.info.piece_id}.stl", mesh_to_stl(printed))
        zf.writestr("manifest.json", result.model_dump_json(indent=2))
    return buf.getvalue()
