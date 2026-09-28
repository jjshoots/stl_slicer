"""Turn uploaded mesh files into a `LoadedModel` (docs/02_build_brief.md §2.6).

trimesh is used for parsing only (R2); the only repair performed is `merge_vertices`. A mesh that
is still not a closed manifold afterwards is rejected with `MeshLoadError` (R10). `scale` is
applied here, at upload, and recorded on `MeshAsset.scale` (R4).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import PurePath
from uuid import uuid4

import numpy as np
import trimesh

from stl_slicer.core.errors import MeshLoadError
from stl_slicer.core.geometry import LoadedModel, Mesh
from stl_slicer.core.models import MeshAsset, SliceWarning, WarningCode

__all__ = ["SUPPORTED_EXTENSIONS", "load_mesh"]

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({"stl", "obj", "ply", "off", "3mf", "glb", "gltf"})


def _extension(filename: str) -> str:
    ext = PurePath(filename).suffix.lower().lstrip(".")
    if not ext:
        raise MeshLoadError(f"cannot determine file type of {filename!r}: no extension")
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise MeshLoadError(f"unsupported file type {ext!r}; expected one of: {supported}")
    return ext


def _parse(data: bytes, ext: str) -> trimesh.Trimesh:
    if not data:
        raise MeshLoadError("file is empty")
    try:
        loaded = trimesh.load(file_obj=BytesIO(data), file_type=ext, force="mesh", process=False)
    except Exception as exc:
        raise MeshLoadError(f"could not parse {ext} file: {exc}") from exc
    if not isinstance(loaded, trimesh.Trimesh):
        raise MeshLoadError(f"{ext} file did not contain a single triangle mesh")
    if len(loaded.faces) == 0:
        raise MeshLoadError(f"{ext} file contains no triangles")
    return loaded


def load_mesh(data: bytes, filename: str, scale: float = 1.0) -> LoadedModel:
    """Parse `data` (format from `filename`'s extension), merge vertices, scale, validate.

    Raises:
        MeshLoadError: unsupported/empty/unparseable input, non-positive scale, a mesh that is
            not a closed manifold after vertex merging, or a zero-volume mesh.
    """
    if not scale > 0:
        raise MeshLoadError(f"scale must be > 0, got {scale}")
    ext = _extension(filename)
    tm = _parse(data, ext)

    warnings: list[SliceWarning] = []
    before = len(tm.vertices)
    tm.merge_vertices()
    after = len(tm.vertices)
    if after != before:
        warnings.append(
            SliceWarning(
                code=WarningCode.VERTICES_MERGED,
                message=f"merged {before} vertices into {after}",
            )
        )

    vertices = np.asarray(tm.vertices, dtype=np.float64)
    if scale != 1.0:
        vertices = vertices * float(scale)
    mesh = Mesh.from_arrays(vertices, np.asarray(tm.faces, dtype=np.int64))
    if mesh.is_empty:
        raise MeshLoadError("mesh is empty or has zero volume")

    asset = MeshAsset(
        model_id=uuid4().hex[:12],
        filename=filename,
        scale=scale,
        triangle_count=mesh.triangle_count,
        bounds=mesh.bounds,
        volume=mesh.volume,
        warnings=warnings,
    )
    return LoadedModel(asset=asset, mesh=mesh)
