"""Unit tests for the manifold3d wrappers. Synthetic geometry only."""

import math

import manifold3d
import numpy as np
import pytest

from stl_slicer.core.errors import MeshLoadError
from stl_slicer.core.geometry import (
    Joint,
    LoadedModel,
    LocalFrame,
    Mesh,
    Piece,
    Region2D,
)
from stl_slicer.core.models import Bounds, CellIndex, MeshAsset, PieceInfo, Placement, PlaneFrame

X_FRAME = PlaneFrame(origin=(0, 0, 0), normal=(1, 0, 0), u=(0, 1, 0), v=(0, 0, 1))
Y_FRAME = PlaneFrame(origin=(0, 0, 0), normal=(0, 1, 0), u=(0, 0, 1), v=(1, 0, 0))
Z_FRAME = PlaneFrame(origin=(0, 0, 0), normal=(0, 0, 1), u=(1, 0, 0), v=(0, 1, 0))


def approx_tuple(values: tuple[float, ...], abs_tol: float = 1e-6) -> object:
    return pytest.approx(values, abs=abs_tol)


# --- Mesh ----------------------------------------------------------------------------------------


def test_box_volume_bounds_triangles() -> None:
    m = Mesh.box((10, 20, 30), center=(1, 2, 3))
    assert m.volume == pytest.approx(6000)
    assert m.bounds.min == approx_tuple((-4, -8, -12))
    assert m.bounds.max == approx_tuple((6, 12, 18))
    assert m.triangle_count == 12
    assert not m.is_empty


def test_from_bounds_is_exact_aabb() -> None:
    b = Bounds(min=(-4.5, 2.0, 10.0), max=(6.0, 12.25, 18.0))
    m = Mesh.from_bounds(b)
    assert m.bounds.min == approx_tuple(b.min)
    assert m.bounds.max == approx_tuple(b.max)
    assert m.volume == pytest.approx(10.5 * 10.25 * 8.0)
    assert m.triangle_count == 12
    ref = Mesh.box(b.size, b.center)
    assert (m - ref).volume == pytest.approx(0.0, abs=1e-6)


def test_sphere_volume() -> None:
    r = 10.0
    assert Mesh.sphere(r).volume == pytest.approx(4 / 3 * math.pi * r**3, rel=0.02)


def test_from_arrays_round_trip() -> None:
    box = Mesh.box((2, 3, 4))
    verts, faces = box.to_arrays()
    assert verts.dtype == np.float64 and verts.shape[1] == 3
    assert faces.dtype == np.int64 and faces.shape == (12, 3)
    again = Mesh.from_arrays(verts, faces)
    assert again.volume == pytest.approx(24)
    assert again.bounds == box.bounds


def test_from_arrays_accepts_other_dtypes() -> None:
    verts, faces = Mesh.box((1, 1, 1)).to_arrays()
    m = Mesh.from_arrays(verts.astype(np.float32), faces.astype(np.int32))  # type: ignore[arg-type]
    assert m.volume == pytest.approx(1)


def test_from_arrays_open_mesh_raises() -> None:
    verts, faces = Mesh.box((1, 1, 1)).to_arrays()
    with pytest.raises(MeshLoadError, match="not manifold"):
        Mesh.from_arrays(verts, faces[:-1])


def test_disjoint_intersection_is_empty() -> None:
    a = Mesh.box((1, 1, 1))
    b = Mesh.box((1, 1, 1), center=(10, 0, 0))
    empty = a & b
    assert empty.is_empty
    assert empty.volume == 0
    assert empty.bounds == Bounds(min=(0, 0, 0), max=(0, 0, 0))


def test_translate_and_scale() -> None:
    m = Mesh.box((2, 2, 2)).translate((5, 0, -1))
    assert m.bounds.min == approx_tuple((4, -1, -2))
    s = Mesh.box((2, 2, 2)).scale(3)
    assert s.bounds.max == approx_tuple((3, 3, 3))
    assert s.volume == pytest.approx(216)


def test_components_of_disjoint_union() -> None:
    a = Mesh.box((1, 1, 1))
    b = Mesh.box((2, 2, 2), center=(10, 0, 0))
    comps = (a | b).components()
    assert len(comps) == 2
    assert sorted(c.volume for c in comps) == pytest.approx([1, 8])


def test_boolean_volumes() -> None:
    a = Mesh.box((10, 10, 10), center=(0, 0, 0))
    b = Mesh.box((10, 10, 10), center=(5, 5, 5))
    assert (a & b).volume == pytest.approx(125)
    assert (a | b).volume == pytest.approx(2000 - 125)
    assert (a - b).volume == pytest.approx(1000 - 125)


def test_manifold_property_is_manifold() -> None:
    assert isinstance(Mesh.box((1, 1, 1)).manifold, manifold3d.Manifold)


# --- cross sections ------------------------------------------------------------------------------


def test_cross_section_normal_x() -> None:
    region = Mesh.box((20, 20, 20)).cross_section(X_FRAME)
    assert region.area == pytest.approx(400)
    assert region.bounds == approx_tuple((-10, -10, 10, 10))


def test_cross_section_normal_y_axes() -> None:
    # u = z, v = x: a box long in z shows up long in u.
    region = Mesh.box((20, 20, 40)).cross_section(Y_FRAME)
    assert region.area == pytest.approx(800)
    assert region.bounds == approx_tuple((-20, -10, 20, 10))


def test_cross_section_offset_shifts_plane() -> None:
    m = Mesh.box((10, 10, 10), center=(5, 0, 0))  # x in [0, 10]
    frame = PlaneFrame(origin=(-1, 0, 0), normal=(1, 0, 0), u=(0, 1, 0), v=(0, 0, 1))
    assert m.cross_section(frame, offset=2).area == pytest.approx(100)
    assert m.cross_section(frame, offset=-2).is_empty


def test_cross_section_non_identity_origin() -> None:
    m = Mesh.box((10, 10, 10), center=(0, 0, 0)) | Mesh.box((4, 4, 4), center=(0, 0, 10))
    frame = PlaneFrame(origin=(3, 1, 10), normal=(0, 0, 1), u=(1, 0, 0), v=(0, 1, 0))
    region = m.cross_section(frame)
    assert region.area == pytest.approx(16)
    assert region.bounds == approx_tuple((-5, -3, -1, 1))


# --- Region2D ------------------------------------------------------------------------------------


def test_rect_area_bounds() -> None:
    r = Region2D.rect(-1, 2, 3, 5)
    assert r.area == pytest.approx(12)
    assert r.bounds == approx_tuple((-1, 2, 3, 5))
    assert Region2D.rect(0, 0, 0, 1).is_empty


def test_circle_and_polygon_area() -> None:
    assert Region2D.circle(5, 128).area == pytest.approx(math.pi * 25, rel=0.01)
    assert Region2D.polygon([(0, 0), (4, 0), (0, 3)]).area == pytest.approx(6)
    assert Region2D.polygon([(0, 0), (0, 3), (4, 0)]).area == pytest.approx(6)  # clockwise


def test_inset() -> None:
    r = Region2D.rect(0, 0, 10, 10)
    assert r.inset(1).area == pytest.approx(64)
    assert r.inset(0).area == pytest.approx(100)
    assert r.inset(-3) is r
    assert r.inset(6).is_empty


def test_offset_grows() -> None:
    r = Region2D.rect(0, 0, 10, 10)
    grown = r.offset(1)
    assert grown.area > r.area
    assert grown.bounds == approx_tuple((-1, -1, 11, 11), abs_tol=1e-3)


def test_inset_edges_only_named() -> None:
    rect = (-10.0, -10.0, 10.0, 10.0)
    r = Region2D.rect(*rect)
    shrunk = r.inset_edges(2, ["u_min", "v_max"], rect)
    assert shrunk.bounds == approx_tuple((-8, -10, 10, 8))
    assert r.inset_edges(2, [], rect).area == pytest.approx(400)
    assert r.inset_edges(11, ["u_min", "u_max"], rect).is_empty


def test_contains() -> None:
    big = Region2D.rect(0, 0, 10, 10)
    assert big.contains(Region2D.rect(1, 1, 2, 2))
    assert big.contains(big)
    assert not big.contains(Region2D.rect(9, 9, 11, 11))


def test_region_components() -> None:
    r = Region2D.rect(0, 0, 1, 1) | Region2D.rect(5, 5, 7, 7)
    comps = r.components()
    assert len(comps) == 2
    assert sorted(c.area for c in comps) == pytest.approx([1, 4])


def test_region_operators_and_translate() -> None:
    a = Region2D.rect(0, 0, 10, 10)
    b = Region2D.rect(5, 5, 15, 15)
    assert (a & b).area == pytest.approx(25)
    assert (a | b).area == pytest.approx(175)
    assert (a - b).area == pytest.approx(75)
    assert a.translate(3, -2).bounds == approx_tuple((3, -2, 13, 8))
    assert isinstance(a.cs, manifold3d.CrossSection)


def test_deepest_point_rect_centre() -> None:
    pt = Region2D.rect(0, 0, 20, 10).deepest_point()
    assert pt is not None
    assert type(pt[0]) is float and type(pt[1]) is float
    assert math.dist(pt, (10, 5)) < 1.0


def test_deepest_point_ring_inside() -> None:
    ring = Region2D.rect(0, 0, 20, 20) - Region2D.rect(5, 5, 15, 15)
    pt = ring.deepest_point()
    assert pt is not None
    assert ring.contains(Region2D.circle(0.1).translate(*pt))


def test_deepest_point_prefers_largest_component() -> None:
    r = Region2D.rect(0, 0, 2, 2) | Region2D.rect(10, 0, 30, 20)
    pt = r.deepest_point()
    assert pt is not None
    assert math.dist(pt, (20, 10)) < 1.0


def test_deepest_point_empty_is_none() -> None:
    assert Region2D.rect(0, 0, 1, 1).inset(5).deepest_point() is None


# --- LocalFrame ----------------------------------------------------------------------------------


def test_local_frame_matrix_columns() -> None:
    frame = PlaneFrame(origin=(1, 2, 3), normal=(1, 0, 0), u=(0, 1, 0), v=(0, 0, 1))
    m = LocalFrame(frame).matrix
    assert m.shape == (4, 4)
    np.testing.assert_allclose(m[:3, 0], frame.u)
    np.testing.assert_allclose(m[:3, 1], frame.v)
    np.testing.assert_allclose(m[:3, 2], frame.normal)
    np.testing.assert_allclose(m[:3, 3], frame.origin)
    np.testing.assert_allclose(m[3], (0, 0, 0, 1))


def test_extrude_local_bounds() -> None:
    lf = LocalFrame(Z_FRAME)
    solid = Mesh(lf.extrude(Region2D.rect(-1, -2, 1, 2), -3, 5))
    assert solid.bounds.min == approx_tuple((-1, -2, -3))
    assert solid.bounds.max == approx_tuple((1, 2, 5))
    with pytest.raises(ValueError):
        lf.extrude(Region2D.rect(0, 0, 1, 1), 1, 1)


def test_to_world_maps_local_z_to_normal() -> None:
    frame = PlaneFrame(origin=(10, 0, 0), normal=(1, 0, 0), u=(0, 1, 0), v=(0, 0, 1))
    lf = LocalFrame(frame)
    local = lf.extrude(Region2D.rect(-1, -2, 1, 2), 0, 4)
    world = Mesh(lf.to_world(local))
    # local x=u→world y, local y=v→world z, local z=normal→world x, shifted by origin.
    assert world.bounds.min == approx_tuple((10, -1, -2))
    assert world.bounds.max == approx_tuple((14, 1, 2))


def test_inverse_composes_to_identity() -> None:
    frame = PlaneFrame(origin=(3, -4, 7), normal=(0, 1, 0), u=(0, 0, 1), v=(1, 0, 0))
    lf = LocalFrame(frame)
    np.testing.assert_allclose(lf.inverse_matrix @ lf.matrix, np.eye(4), atol=1e-12)
    m = Mesh.box((2, 4, 6), center=(1, 2, 3))
    back = Mesh(lf.to_world(lf.to_local(m.manifold)))
    assert back.bounds.min == approx_tuple(m.bounds.min)
    assert back.bounds.max == approx_tuple(m.bounds.max)


# --- records -------------------------------------------------------------------------------------


def test_records_construct() -> None:
    mesh = Mesh.box((1, 1, 1))
    bounds = mesh.bounds
    joint = Joint(
        interface_id="x0",
        kind="dowel",
        male_cell=CellIndex(i=0, j=0, k=0),
        female_cell=CellIndex(i=1, j=0, k=0),
        placement=Placement(u=0, v=0),
        male=mesh.manifold,
        female=mesh.manifold,
        clearance_volume=0.0,
    )
    assert joint.kind == "dowel"
    info = PieceInfo(
        piece_id="x0_y0_z0",
        cell=CellIndex(i=0, j=0, k=0),
        bounds=bounds,
        volume=1.0,
        triangle_count=12,
        component_count=1,
        fits_bed=True,
        print_offset=(0, 0, 0),
    )
    assert Piece(info=info, mesh=mesh).mesh is mesh
    asset = MeshAsset(
        model_id="m", filename="a.stl", scale=1, triangle_count=12, bounds=bounds, volume=1
    )
    assert LoadedModel(asset=asset, mesh=mesh).asset.model_id == "m"
    with pytest.raises(AttributeError):
        joint.kind = "x"  # type: ignore[misc]
