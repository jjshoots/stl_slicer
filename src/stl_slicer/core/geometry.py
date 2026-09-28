"""Thin, typed wrappers over the manifold3d kernel.

Every length is millimetres in the model frame. `Mesh` wraps a 3D `manifold3d.Manifold`,
`Region2D` wraps a 2D `manifold3d.CrossSection` expressed in an interface's (u, v) frame, and
`LocalFrame` maps between an interface's local frame and the world. See docs/00_design.md.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import manifold3d
import numpy as np
from manifold3d import CrossSection, FillRule, JoinType, Manifold, OpType
from manifold3d import Mesh as _MeshData
from numpy.typing import NDArray

from stl_slicer.core.errors import MeshLoadError
from stl_slicer.core.models import (
    Bounds,
    CellIndex,
    MeshAsset,
    PieceInfo,
    Placement,
    PlaneFrame,
    SliceResult,
    Vec3,
)

__all__ = [
    "Joint",
    "LoadedModel",
    "LocalFrame",
    "Mesh",
    "Piece",
    "Region2D",
    "SliceOutput",
]

_DEEPEST_MIN_STEP = 0.05


# --- 3D ------------------------------------------------------------------------------------------


class Mesh:
    """Immutable wrapper over manifold3d.Manifold. All lengths in mm, model frame."""

    __slots__ = ("_m",)

    def __init__(self, manifold: manifold3d.Manifold) -> None:
        self._m: Any = manifold

    # constructors ---------------------------------------------------------------------------

    @classmethod
    def from_arrays(cls, vertices: NDArray[np.float64], faces: NDArray[np.int64]) -> Mesh:
        """Build from (N,3) vertices and (M,3) triangle indices; raise MeshLoadError if the
        result is not a valid manifold."""
        verts = np.ascontiguousarray(np.asarray(vertices, dtype=np.float32).reshape(-1, 3))
        tris = np.ascontiguousarray(np.asarray(faces, dtype=np.uint32).reshape(-1, 3))
        manifold = Manifold(_MeshData(vert_properties=verts, tri_verts=tris))
        status = manifold.status()
        if status != manifold3d.Error.NoError:
            raise MeshLoadError(f"mesh is not manifold: {status.name}")
        return cls(manifold)

    @classmethod
    def box(cls, size: Vec3, center: Vec3 = (0.0, 0.0, 0.0)) -> Mesh:
        sx, sy, sz = (float(s) for s in size)
        cube = Manifold.cube([sx, sy, sz])
        return cls(cube.translate([center[0] - sx / 2, center[1] - sy / 2, center[2] - sz / 2]))

    @classmethod
    def from_bounds(cls, bounds: Bounds) -> Mesh:
        """Axis-aligned box spanning `bounds` exactly (min corner at `bounds.min`)."""
        size = [float(s) for s in bounds.size]
        return cls(Manifold.cube(size).translate([float(x) for x in bounds.min]))

    @classmethod
    def sphere(cls, radius: float, segments: int = 64) -> Mesh:
        return cls(Manifold.sphere(float(radius), int(segments)))

    def to_arrays(self) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
        data = self._m.to_mesh()
        verts = np.atleast_2d(np.asarray(data.vert_properties, dtype=np.float64))
        faces = np.asarray(data.tri_verts, dtype=np.int64).reshape(-1, 3)
        return np.ascontiguousarray(verts[:, :3]), faces

    # properties -----------------------------------------------------------------------------

    @property
    def manifold(self) -> manifold3d.Manifold:
        return self._m

    @property
    def volume(self) -> float:
        return float(self._m.volume())

    @property
    def bounds(self) -> Bounds:
        if self._m.is_empty():
            return Bounds(min=(0.0, 0.0, 0.0), max=(0.0, 0.0, 0.0))
        b = [float(x) for x in self._m.bounding_box()]
        return Bounds(min=(b[0], b[1], b[2]), max=(b[3], b[4], b[5]))

    @property
    def triangle_count(self) -> int:
        return int(self._m.num_tri())

    @property
    def is_empty(self) -> bool:
        return bool(self._m.is_empty()) or self.volume == 0.0

    # transforms -----------------------------------------------------------------------------

    def translate(self, offset: Vec3) -> Mesh:
        return Mesh(self._m.translate([float(o) for o in offset]))

    def scale(self, factor: float) -> Mesh:
        f = float(factor)
        return Mesh(self._m.scale([f, f, f]))

    def components(self) -> list[Mesh]:
        """Connected components; zero-volume components are dropped."""
        return [Mesh(c) for c in self._m.decompose() if float(c.volume()) > 0.0]

    def cross_section(self, frame: PlaneFrame, offset: float = 0.0) -> Region2D:
        """Slice by the plane `frame` shifted `offset` along its normal, returned in (u, v)."""
        local = self._m.transform(LocalFrame(frame).inverse_matrix[:3, :])
        return Region2D(local.slice(float(offset)))

    # booleans -------------------------------------------------------------------------------

    def __and__(self, o: Mesh) -> Mesh:
        return Mesh(self._m ^ o._m)

    def __or__(self, o: Mesh) -> Mesh:
        return Mesh(self._m + o._m)

    def __sub__(self, o: Mesh) -> Mesh:
        return Mesh(self._m - o._m)

    @staticmethod
    def union_all(meshes: Iterable[Mesh]) -> Mesh:
        """Union of many meshes in one batched boolean (empty input → empty mesh)."""
        items = [m._m for m in meshes]
        if not items:
            return Mesh(Manifold())
        return Mesh(Manifold.batch_boolean(items, OpType.Add))

    def __repr__(self) -> str:
        return f"Mesh(triangles={self.triangle_count}, volume={self.volume:.3f})"


# --- 2D ------------------------------------------------------------------------------------------


class Region2D:
    """Wrapper over manifold3d.CrossSection in an interface's (u, v) frame."""

    __slots__ = ("_cs",)

    def __init__(self, cs: manifold3d.CrossSection) -> None:
        self._cs: Any = cs

    @classmethod
    def empty(cls) -> Region2D:
        return cls(CrossSection())

    @classmethod
    def rect(cls, u_min: float, v_min: float, u_max: float, v_max: float) -> Region2D:
        w, h = float(u_max) - float(u_min), float(v_max) - float(v_min)
        if w <= 0 or h <= 0:
            return cls.empty()
        return cls(CrossSection.square([w, h]).translate([float(u_min), float(v_min)]))

    @classmethod
    def circle(cls, radius: float, segments: int = 32) -> Region2D:
        return cls(CrossSection.circle(float(radius), int(segments)))

    @classmethod
    def polygon(cls, points: Sequence[tuple[float, float]]) -> Region2D:
        """A simple polygon; either winding order is accepted."""
        contour = [[float(x), float(y)] for x, y in points]
        if len(contour) < 3:
            return cls.empty()
        return cls(CrossSection([contour], FillRule.NonZero))

    @property
    def cs(self) -> manifold3d.CrossSection:
        return self._cs

    @property
    def area(self) -> float:
        return float(self._cs.area())

    @property
    def is_empty(self) -> bool:
        return bool(self._cs.is_empty()) or self.area == 0.0

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(u_min, v_min, u_max, v_max); all zeros when empty."""
        if self._cs.is_empty():
            return (0.0, 0.0, 0.0, 0.0)
        b = [float(x) for x in self._cs.bounds()]
        return (b[0], b[1], b[2], b[3])

    def inset(self, d: float) -> Region2D:
        if d <= 0:
            return self
        return Region2D(self._cs.offset(-float(d), JoinType.Round))

    def inset_edges(
        self, d: float, edges: Iterable[str], rect: tuple[float, float, float, float]
    ) -> Region2D:
        """Intersect with `rect` shrunk by `d` on the named edges only."""
        u_min, v_min, u_max, v_max = (float(x) for x in rect)
        for edge in edges:
            if edge == "u_min":
                u_min += d
            elif edge == "u_max":
                u_max -= d
            elif edge == "v_min":
                v_min += d
            elif edge == "v_max":
                v_max -= d
            else:
                raise ValueError(f"unknown rect edge: {edge!r}")
        if u_min >= u_max or v_min >= v_max:
            return Region2D.empty()
        return self & Region2D.rect(u_min, v_min, u_max, v_max)

    def offset(self, d: float) -> Region2D:
        return Region2D(self._cs.offset(float(d), JoinType.Round))

    def translate(self, u: float, v: float) -> Region2D:
        return Region2D(self._cs.translate([float(u), float(v)]))

    def transpose(self) -> Region2D:
        """Swap the two coordinates: (u, v) -> (v, u) (a mirror across the line u = v)."""
        return Region2D(self._cs.mirror([1.0, -1.0]))

    def contains(self, other: Region2D, tol: float = 1e-9) -> bool:
        return (other - self).area <= tol

    def components(self) -> list[Region2D]:
        return [Region2D(c) for c in self._cs.decompose() if float(c.area()) > 0.0]

    def polygons(self) -> list[NDArray[np.float64]]:
        """Contours as (K,2) float arrays (outer CCW, holes CW)."""
        return [np.asarray(p, dtype=np.float64).reshape(-1, 2) for p in self._cs.to_polygons()]

    def contains_point(self, u: float, v: float) -> bool:
        """Even-odd point-in-region test over all contours."""
        inside = False
        for poly in self.polygons():
            x0, y0 = poly[:, 0], poly[:, 1]
            x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
            crosses = (y0 > v) != (y1 > v)
            with np.errstate(divide="ignore", invalid="ignore"):
                xs = x0 + (v - y0) * (x1 - x0) / (y1 - y0)
            inside ^= bool(np.count_nonzero(crosses & (u < xs)) % 2)
        return inside

    def centroid(self) -> tuple[float, float] | None:
        """Area-weighted centroid (signed contours, so holes subtract); None when empty."""
        a_sum = cx = cy = 0.0
        for poly in self.polygons():
            x0, y0 = poly[:, 0], poly[:, 1]
            x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
            cross = x0 * y1 - x1 * y0
            a_sum += float(cross.sum()) / 2
            cx += float(((x0 + x1) * cross).sum()) / 6
            cy += float(((y0 + y1) * cross).sum()) / 6
        if a_sum == 0.0:
            return None
        return (cx / a_sum, cy / a_sum)

    def deepest_point(self, step: float | None = None) -> tuple[float, float] | None:
        """Approximate pole of inaccessibility (docs/00_design.md O3).

        Insets progressively deeper, halving the step whenever the next inset would be empty,
        until the step drops below 0.05 mm; returns a point of the largest component of the
        last non-empty inset (its centroid if that lies inside, else its nearest vertex)."""
        if self.is_empty:
            return None
        u0, v0, u1, v1 = self.bounds
        s = float(step) if step is not None and step > 0 else min(u1 - u0, v1 - v0) / 8
        floor = min(_DEEPEST_MIN_STEP, s)
        depth = 0.0
        last: Region2D = self
        while s >= floor and s > 0:
            candidate = self.inset(depth + s)
            if candidate.is_empty:
                s /= 2
            else:
                depth += s
                last = candidate
        comps = last.components() or [last]
        best = max(comps, key=lambda c: c.area)
        c = best.centroid()
        if c is not None and best.contains_point(*c):
            return (float(c[0]), float(c[1]))
        verts = np.concatenate(best.polygons())
        target = np.asarray(c if c is not None else verts.mean(axis=0))
        nearest = verts[int(np.argmin(((verts - target) ** 2).sum(axis=1)))]
        return (float(nearest[0]), float(nearest[1]))

    def __and__(self, o: Region2D) -> Region2D:
        return Region2D(self._cs ^ o._cs)

    def __or__(self, o: Region2D) -> Region2D:
        return Region2D(self._cs + o._cs)

    def __sub__(self, o: Region2D) -> Region2D:
        return Region2D(self._cs - o._cs)

    def __repr__(self) -> str:
        return f"Region2D(area={self.area:.3f}, bounds={self.bounds})"


# --- frames --------------------------------------------------------------------------------------


class LocalFrame:
    """Transforms between an interface's local frame (x=u, y=v, z=normal, origin on plane) and
    world."""

    __slots__ = ("_inv", "_mat")

    def __init__(self, frame: PlaneFrame) -> None:
        mat = np.eye(4, dtype=np.float64)
        mat[:3, 0] = frame.u
        mat[:3, 1] = frame.v
        mat[:3, 2] = frame.normal
        mat[:3, 3] = frame.origin
        rot_t = mat[:3, :3].T
        inv = np.eye(4, dtype=np.float64)
        inv[:3, :3] = rot_t
        inv[:3, 3] = -rot_t @ mat[:3, 3]
        self._mat: NDArray[np.float64] = mat
        self._inv: NDArray[np.float64] = inv

    @property
    def matrix(self) -> NDArray[np.float64]:
        """4x4 local→world (rotation + translation)."""
        return self._mat.copy()

    @property
    def inverse_matrix(self) -> NDArray[np.float64]:
        """4x4 world→local; the frame is rigid so this is [R^T | -R^T t]."""
        return self._inv.copy()

    def to_world(self, m: manifold3d.Manifold) -> manifold3d.Manifold:
        out: manifold3d.Manifold = m.transform(self._mat[:3, :])
        return out

    def to_local(self, m: manifold3d.Manifold) -> manifold3d.Manifold:
        out: manifold3d.Manifold = m.transform(self._inv[:3, :])
        return out

    def extrude(self, region: Region2D, z0: float, z1: float) -> manifold3d.Manifold:
        """Prism over `region` from local z0 to z1 (local frame; requires z0 < z1)."""
        if not z1 > z0:
            raise ValueError(f"extrude requires z0 < z1, got {z0} >= {z1}")
        out: manifold3d.Manifold = Manifold.extrude(region.cs, float(z1 - z0)).translate(
            [0.0, 0.0, float(z0)]
        )
        return out


# --- pipeline records ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Joint:
    interface_id: str
    kind: str
    male_cell: CellIndex
    female_cell: CellIndex
    placement: Placement
    male: manifold3d.Manifold  # WORLD frame; both solids sit on the female side
    female: manifold3d.Manifold
    clearance_volume: float  # female.volume - male.volume (+ male_pocket.volume)
    male_pocket: manifold3d.Manifold | None = None
    """Pocket joints only (no male tab): the pocket carved out of the MALE piece, in the world
    frame on the male side of the plane. `male` is then empty and `female` is the female pocket."""


@dataclass(frozen=True)
class Piece:
    info: PieceInfo
    mesh: Mesh


@dataclass(frozen=True)
class LoadedModel:
    asset: MeshAsset
    mesh: Mesh


@dataclass(frozen=True)
class SliceOutput:
    result: SliceResult
    pieces: list[Piece]
