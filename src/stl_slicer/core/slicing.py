"""Slicing: contact regions, joint-modified cells, carving and runtime invariant checks.

Owns the three disjointness rules of docs/00_design.md §3:

1. union before subtract: ``cell' = (cell + union(males_out)) - union(females_in)``;
2. every male/female solid is clipped to the female cell's AABB (B2);
3. contact regions are inset by ``depth + clearance`` along interior rect edges (B1).

See docs/00_design.md §4.3 and docs/02_build_brief.md §2.4.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Sequence

from manifold3d import Manifold, OpType

from stl_slicer.core.errors import SliceInvariantError
from stl_slicer.core.geometry import Joint, Mesh, Piece, Region2D
from stl_slicer.core.models import (
    Axis,
    CellIndex,
    CutInterface,
    CutPlan,
    MaleSide,
    PieceInfo,
    SliceStats,
    SliceWarning,
    Vec3,
    WarningCode,
)

__all__ = ["carve", "check_pieces", "contact_regions", "joint_cells", "male_female"]

_CLIP_TOL = 1e-9
_OVERLAP_REL_TOL = 1e-6
# Intersecting face-adjacent pieces leaves coplanar slivers whose signed volume is kernel noise
# (~1e-12 mm³ on a 100 mm part). Overlaps below this fraction of the input volume report as 0.
_OVERLAP_NOISE_REL = 1e-9


def male_female(interface: CutInterface, rule: MaleSide) -> tuple[CellIndex, CellIndex]:
    """(male cell, female cell) of an interface under `rule`."""
    if rule is MaleSide.LOWER:
        return interface.lower, interface.upper
    return interface.upper, interface.lower


def contact_regions(
    mesh: Mesh, plan: CutPlan, edge_inset: float, eps: float = 1e-3
) -> dict[str, Region2D]:
    """Per interface id: material present on both sides of the cut, within the interface rect,
    inset by `edge_inset` along the rect edges that lie on another cut plane.

    Slicing at ±eps (rather than exactly on the plane) keeps a mesh face coplanar with the cut
    from overstating the contact area (M18).

    The mesh is sliced once per distinct cut plane ``(axis, position)``; interfaces on the same
    plane share u, v and normal and differ only in their in-plane origin, so each reuses the
    plane's section translated into its own frame."""
    sections: dict[tuple[Axis, float], tuple[Vec3, Region2D]] = {}
    out: dict[str, Region2D] = {}
    for interface in plan.interfaces:
        frame = interface.frame
        key = (interface.axis, interface.position)
        cached = sections.get(key)
        if cached is None:
            below = mesh.cross_section(frame, -eps)
            above = mesh.cross_section(frame, eps)
            cached = sections[key] = (frame.origin, below & above)
        origin, both = cached
        delta = [o - c for o, c in zip(frame.origin, origin, strict=True)]
        du = sum(d * u for d, u in zip(delta, frame.u, strict=True))
        dv = sum(d * v for d, v in zip(delta, frame.v, strict=True))
        section = both if du == 0.0 and dv == 0.0 else both.translate(-du, -dv)
        region = section & Region2D.rect(*interface.rect)
        if edge_inset > 0:
            region = region.inset_edges(edge_inset, interface.interior_edges, interface.rect)
        out[interface.id] = region
    return out


def joint_cells(
    plan: CutPlan, joints: Sequence[Joint]
) -> tuple[dict[str, Manifold], list[SliceWarning]]:
    """Cell solids after applying joints: ``(cube(cell) + males_out) - females_in``, with every
    male/female solid clipped to its female cell first. Warns JOINT_CLIPPED when clipping
    removed male volume that lay inside the plan bounds (i.e. would have reached another cell);
    overshoot past the plan's outer bounds is outside the mesh and ignored.

    Joint volume outside the plan's AABB lies outside every cell (and the mesh), so clipping it
    away is harmless; only volume inside it but outside the female cell would have reached a
    neighbouring cell, and that is what JOINT_CLIPPED reports."""
    boxes = {cell.id: Mesh.from_bounds(cell.bounds).manifold for cell in plan.cells}
    plan_box = Mesh.from_bounds(plan.bounds).manifold
    males_out: defaultdict[str, list[Manifold]] = defaultdict(list)
    females_in: defaultdict[str, list[Manifold]] = defaultdict(list)
    warnings: list[SliceWarning] = []

    for joint in joints:
        fbox = boxes[joint.female_cell.id]
        male_c = joint.male ^ fbox
        female_c = joint.female ^ fbox
        lost = float((joint.male ^ plan_box).volume()) - float(male_c.volume())
        if lost > _CLIP_TOL:
            warnings.append(
                SliceWarning(
                    code=WarningCode.JOINT_CLIPPED,
                    message=(
                        f"{joint.kind} joint at ({joint.placement.u:.2f}, "
                        f"{joint.placement.v:.2f}) clipped to cell {joint.female_cell.id}; "
                        f"{lost:.3f} mm³ of the male removed"
                    ),
                    subject=joint.interface_id,
                )
            )
        males_out[joint.male_cell.id].append(male_c)
        females_in[joint.female_cell.id].append(female_c)

    cells: dict[str, Manifold] = {}
    for cell in plan.cells:
        solid = boxes[cell.id]
        males = males_out.get(cell.id, [])
        if males:
            solid = Manifold.batch_boolean([solid, *males], OpType.Add)
        females = females_in.get(cell.id, [])
        if females:
            solid = solid - Manifold.batch_boolean(females, OpType.Add)
        cells[cell.id] = solid
    return cells, warnings


def carve(mesh: Mesh, cells: dict[str, Manifold], plan: CutPlan) -> list[Piece]:
    """``mesh ^ cell'`` per cell; empty results are dropped, zero-volume components removed.

    `fits_bed` / `print_offset` are placeholders filled in by the pipeline."""
    pieces: list[Piece] = []
    for cell in plan.cells:
        solid = cells.get(cell.id)
        if solid is None:
            continue
        piece = mesh & Mesh(solid)
        if piece.is_empty:
            continue
        comps = piece.components()
        if not comps:
            continue
        if len(comps) != len(piece.manifold.decompose()):
            piece = Mesh.union_all(comps)
        info = PieceInfo(
            piece_id=f"p_{cell.id}",
            cell=cell.index,
            component=0,
            bounds=piece.bounds,
            volume=piece.volume,
            triangle_count=piece.triangle_count,
            component_count=len(comps),
            fits_bed=False,
            print_offset=(0.0, 0.0, 0.0),
        )
        pieces.append(Piece(info=info, mesh=piece))
    return pieces


def check_pieces(
    pieces: Sequence[Piece],
    plan: CutPlan,
    input_volume: float,
    clearance_volume: float,
    duration_s: float,
) -> SliceStats:
    """Verify disjointness over the 26-neighbourhood and volume conservation.

    Raises SliceInvariantError on any violation beyond ``1e-6 * input_volume``. Overlaps at or
    below ``1e-9 * input_volume`` are kernel noise and reported as 0."""
    del plan  # reserved for future checks (e.g. pieces within their cells)
    tol = _OVERLAP_REL_TOL * input_volume
    noise = _OVERLAP_NOISE_REL * input_volume
    max_overlap = 0.0
    for a, b in itertools.combinations(pieces, 2):
        if a.info.cell == b.info.cell or not a.info.cell.is_neighbour(b.info.cell):
            continue
        ov = (a.mesh & b.mesh).volume
        if ov <= noise:
            continue
        max_overlap = max(max_overlap, ov)
        if ov > tol:
            raise SliceInvariantError(
                f"pieces {a.info.piece_id} and {b.info.piece_id} overlap by {ov:.6g} mm³"
            )

    output_volume = sum(p.info.volume for p in pieces)
    if output_volume < input_volume - clearance_volume - tol:
        raise SliceInvariantError(
            f"volume lost: pieces total {output_volume:.6g} mm³ < input {input_volume:.6g} mm³ "
            f"- clearance {clearance_volume:.6g} mm³"
        )
    if output_volume > input_volume + tol:
        raise SliceInvariantError(
            f"volume gained: pieces total {output_volume:.6g} mm³ > input {input_volume:.6g} mm³"
        )
    return SliceStats(
        piece_count=len(pieces),
        input_volume=input_volume,
        output_volume=output_volume,
        max_overlap_volume=max_overlap,
        duration_s=duration_s,
    )
