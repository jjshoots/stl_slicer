"""The slicing pipeline: compose planning, contacts, joints, carving and checks into one call.

``plan_grid → contact_regions → JointGenerator.call (per interface) → joint_cells → carve →
check_pieces`` composed into ``SliceOutput(result, pieces)``. See docs/00_design.md §3, §4.4 and
docs/02_build_brief.md §2.5.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Protocol

from stl_slicer.core.errors import Cancelled
from stl_slicer.core.geometry import Joint, LoadedModel, Mesh, Piece, Region2D, SliceOutput
from stl_slicer.core.joints.base import ProfileStripJoint
from stl_slicer.core.joints.registry import get_generator, spec_clearance, spec_depth
from stl_slicer.core.models import (
    Axis,
    Cell,
    CellIndex,
    CellLimits,
    CutPlan,
    JointInfo,
    SliceResult,
    SliceSpec,
    SliceWarning,
    WarningCode,
)
from stl_slicer.core.planning import plan_grid
from stl_slicer.core.slicing import carve, check_pieces, contact_regions, joint_cells, male_female

__all__ = ["CancelToken", "ProgressSink", "cell_limits", "slice_model"]


class ProgressSink(Protocol):
    def __call__(self, fraction: float, step: str) -> None: ...


class CancelToken:
    """A cancellation flag safe to set from another thread; checked between pipeline steps."""

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise Cancelled("job cancelled")


def _no_progress(fraction: float, step: str) -> None:
    del fraction, step


def cell_limits(spec: SliceSpec) -> CellLimits:
    """Bed-fit reservation (docs/00_design.md §3): with a fixed male side a piece protrudes past
    its cell by `depth` on one side per axis, so ``max_cell = bed - depth - 2 * bed_margin``.
    ``min_cell = depth + clearance + 1``. Non-positive components are rejected by `plan_grid`."""
    depth = spec_depth(spec.joint)
    clearance = spec_clearance(spec.joint)
    margin = spec.partition.bed_margin
    bed = spec.print_volume
    max_cell = (
        bed.x - depth - 2 * margin,
        bed.y - depth - 2 * margin,
        bed.z - depth - 2 * margin,
    )
    return CellLimits(max_cell=max_cell, min_cell=depth + clearance + 1.0)


def _cell_occupied(mesh: Mesh, cell: Cell) -> bool:
    return not (mesh & Mesh.from_bounds(cell.bounds)).is_empty


def _place_joints(
    model: LoadedModel,
    spec: SliceSpec,
    plan: CutPlan,
    regions: dict[str, Region2D],
    cancel: CancelToken | None,
) -> tuple[list[Joint], list[SliceWarning]]:
    gen = get_generator(spec.joint.kind)
    occupied: dict[str, bool] = {}

    def is_occupied(index: CellIndex) -> bool:
        key = index.id
        if key not in occupied:
            occupied[key] = _cell_occupied(model.mesh, plan.cell(index))
        return occupied[key]

    joints: list[Joint] = []
    warnings: list[SliceWarning] = []
    for interface in plan.interfaces:
        if cancel is not None:
            cancel.raise_if_cancelled()
        region = regions[interface.id]
        if region.is_empty:
            if is_occupied(interface.lower) and is_occupied(interface.upper):
                warnings.append(
                    SliceWarning(
                        code=WarningCode.NO_CONTACT_FOR_JOINT,
                        message=(
                            f"no material contact across interface {interface.id} "
                            f"(after the {spec.joint.depth + spec.joint.clearance:.2f} mm edge "
                            "inset); pieces there are not joined"
                        ),
                        subject=interface.id,
                    )
                )
            continue
        male, female = male_female(interface, spec.male_side)
        placed = gen.call(interface, region, spec.joint, male, female)
        if not placed:
            warnings.append(
                SliceWarning(
                    code=WarningCode.NO_CONTACT_FOR_JOINT,
                    message=(
                        f"contact across interface {interface.id} ({region.area:.1f} mm²) is too "
                        f"small for any {spec.joint.kind} placement; pieces there are not joined"
                    ),
                    subject=interface.id,
                )
            )
        joints.extend(placed)
    return joints, warnings


def _assembly_conflicts(
    plan: CutPlan, joints: list[Joint], piece_ids: set[str], kind: str
) -> list[SliceWarning]:
    """Strip joints (dovetail, jigsaw) slide along `generator.slide_axis(interface)`; a piece
    whose joints slide along different axes cannot be assembled by sliding
    (docs/00_design.md §4.2)."""
    gen = get_generator(kind)
    if not isinstance(gen, ProfileStripJoint):
        return []
    interfaces = {i.id: i for i in plan.interfaces}
    axes: defaultdict[str, set[Axis]] = defaultdict(set)
    for joint in joints:
        axis = gen.slide_axis(interfaces[joint.interface_id])
        axes[f"p_{joint.male_cell.id}"].add(axis)
        axes[f"p_{joint.female_cell.id}"].add(axis)
    warnings: list[SliceWarning] = []
    for cell in plan.cells:
        piece_id = f"p_{cell.id}"
        found = axes.get(piece_id, set())
        if piece_id in piece_ids and len(found) > 1:
            names = ", ".join(sorted(a.value for a in found))
            warnings.append(
                SliceWarning(
                    code=WarningCode.ASSEMBLY_CONFLICT,
                    message=(
                        f"piece {piece_id} has sliding joints along different axes ({names}); "
                        "it cannot be assembled by sliding alone"
                    ),
                    subject=piece_id,
                )
            )
    return warnings


def slice_model(
    model: LoadedModel,
    spec: SliceSpec,
    progress: ProgressSink | None = None,
    cancel: CancelToken | None = None,
    job_id: str = "",
) -> SliceOutput:
    """Partition `model` per `spec`; raises `Cancelled` between steps when `cancel` is set,
    `PlanError` for an impossible partition and `SliceInvariantError` on a kernel bug."""
    report: ProgressSink = progress if progress is not None else _no_progress

    def check() -> None:
        if cancel is not None:
            cancel.raise_if_cancelled()

    started = time.perf_counter()
    warnings: list[SliceWarning] = []

    report(0.0, "planning")
    plan = plan_grid(
        model.mesh.bounds, cell_limits(spec), spec.partition.cuts, axes=spec.partition.axes
    )
    warnings.extend(plan.warnings)
    check()

    report(0.1, "contacts")
    has_joints = spec.joint.kind != "none"
    edge_inset = spec_depth(spec.joint) + spec_clearance(spec.joint)
    regions = contact_regions(model.mesh, plan, edge_inset) if has_joints else {}
    check()

    report(0.2, "joints")
    joints: list[Joint] = []
    if has_joints:
        joints, joint_warnings = _place_joints(model, spec, plan, regions, cancel)
        warnings.extend(joint_warnings)
    check()

    cells, clip_warnings = joint_cells(plan, joints)
    warnings.extend(clip_warnings)

    raw: list[Piece] = []
    n = len(plan.cells)
    for i, cell in enumerate(plan.cells):
        report(0.3 + 0.6 * i / n, f"cutting {i + 1}/{n}")
        check()
        raw.extend(carve(model.mesh, {cell.id: cells[cell.id]}, plan))

    report(0.95, "checking")
    check()
    clearance_volume = sum(j.clearance_volume for j in joints)
    stats = check_pieces(
        raw, plan, model.mesh.volume, clearance_volume, time.perf_counter() - started
    )

    pieces: list[Piece] = []
    for piece in raw:
        b = piece.info.bounds
        cx, cy, _ = b.center
        fits = b.fits_in(spec.print_volume)
        info = piece.info.model_copy(
            update={"fits_bed": fits, "print_offset": (-cx, -cy, -b.min[2])}
        )
        pieces.append(Piece(info=info, mesh=piece.mesh))
        if not fits:
            sx, sy, sz = b.size
            bed = spec.print_volume
            warnings.append(
                SliceWarning(
                    code=WarningCode.PIECE_OVERSIZE,
                    message=(
                        f"piece {info.piece_id} is {sx:.1f}x{sy:.1f}x{sz:.1f} mm, larger than "
                        f"the {bed.x:g}x{bed.y:g}x{bed.z:g} mm bed"
                    ),
                    subject=info.piece_id,
                )
            )
        if info.component_count > 1:
            warnings.append(
                SliceWarning(
                    code=WarningCode.DISCONNECTED_PIECE,
                    message=(
                        f"piece {info.piece_id} has {info.component_count} disconnected parts"
                    ),
                    subject=info.piece_id,
                )
            )

    warnings.extend(
        _assembly_conflicts(plan, joints, {p.info.piece_id for p in pieces}, spec.joint.kind)
    )

    joint_infos = [
        JointInfo(
            interface_id=j.interface_id,
            kind=j.kind,
            male_piece=f"p_{j.male_cell.id}",
            female_piece=f"p_{j.female_cell.id}",
            placement=j.placement,
        )
        for j in joints
    ]
    result = SliceResult(
        job_id=job_id,
        model_id=model.asset.model_id,
        spec=spec,
        plan=plan,
        pieces=[p.info for p in pieces],
        joints=joint_infos,
        stats=stats,
        warnings=warnings,
    )
    report(1.0, "done")
    return SliceOutput(result=result, pieces=pieces)
