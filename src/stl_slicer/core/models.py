"""Serialisable contracts shared by every layer.

Leaf module: imports nothing from the package. All lengths are millimetres in the model frame
(the uploaded mesh after `MeshAsset.scale` has been applied). See docs/00_design.md §5.
"""

from __future__ import annotations

import functools
import math
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Vec3 = tuple[float, float, float]


class Axis(StrEnum):
    X = "x"
    Y = "y"
    Z = "z"

    @property
    def ordinal(self) -> int:
        return "xyz".find(self.value)

    @property
    def uv(self) -> tuple[Axis, Axis]:
        """The two in-plane axes for a cut normal to this axis, in cyclic order."""
        order = [Axis.X, Axis.Y, Axis.Z]
        i = self.ordinal
        return order[(i + 1) % 3], order[(i + 2) % 3]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Bounds(_Frozen):
    min: Vec3
    max: Vec3

    @model_validator(mode="after")
    def _ordered(self) -> Bounds:
        if any(lo > hi for lo, hi in zip(self.min, self.max, strict=True)):
            raise ValueError("bounds.min must be <= bounds.max on every axis")
        return self

    @property
    def size(self) -> Vec3:
        return tuple(hi - lo for lo, hi in zip(self.min, self.max, strict=True))  # type: ignore[return-value]

    @property
    def center(self) -> Vec3:
        return tuple((lo + hi) / 2 for lo, hi in zip(self.min, self.max, strict=True))  # type: ignore[return-value]

    def extent(self, axis: Axis) -> float:
        return self.max[axis.ordinal] - self.min[axis.ordinal]

    def fits_in(self, volume: PrintVolume) -> bool:
        sx, sy, sz = self.size
        return sx <= volume.x and sy <= volume.y and sz <= volume.z


class PrintVolume(_Frozen):
    x: float = Field(gt=0)
    y: float = Field(gt=0)
    z: float = Field(gt=0)

    def component(self, axis: Axis) -> float:
        return (self.x, self.y, self.z)[axis.ordinal]


class CellLimits(_Frozen):
    """Per-axis maximum cell size the planner may emit, and the minimum spacing between cuts."""

    max_cell: Vec3
    min_cell: float = 1.0


class AxisCuts(_Frozen):
    """Interior cut positions per axis, in model coordinates."""

    x: list[float] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)
    z: list[float] = Field(default_factory=list)

    def for_axis(self, axis: Axis) -> list[float]:
        return (self.x, self.y, self.z)[axis.ordinal]


class CellIndex(_Frozen):
    i: int = Field(ge=0)
    j: int = Field(ge=0)
    k: int = Field(ge=0)

    @property
    def id(self) -> str:
        return f"x{self.i}_y{self.j}_z{self.k}"

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.i, self.j, self.k)

    def is_neighbour(self, other: CellIndex) -> bool:
        """True when the two cells touch (26-neighbourhood), including equality."""
        return all(abs(a - b) <= 1 for a, b in zip(self.as_tuple(), other.as_tuple(), strict=True))


class Cell(_Frozen):
    index: CellIndex
    bounds: Bounds

    @property
    def id(self) -> str:
        return self.index.id


class PlaneFrame(_Frozen):
    """An interface plane: origin on the plane, unit normal from the lower to the upper cell,
    and in-plane unit axes u, v (right-handed: u cross v = normal)."""

    origin: Vec3
    normal: Vec3
    u: Vec3
    v: Vec3


RectEdge = Literal["u_min", "u_max", "v_min", "v_max"]


class CutInterface(_Frozen):
    id: str
    axis: Axis
    position: float
    lower: CellIndex
    upper: CellIndex
    frame: PlaneFrame
    extent_u: float = Field(gt=0)
    extent_v: float = Field(gt=0)
    interior_edges: list[RectEdge] = Field(default_factory=list)

    @property
    def rect(self) -> tuple[float, float, float, float]:
        """(u_min, v_min, u_max, v_max) of the interface in its own frame."""
        return (-self.extent_u / 2, -self.extent_v / 2, self.extent_u / 2, self.extent_v / 2)


class WarningCode(StrEnum):
    CELL_OVERSIZE = "cell_oversize"
    PIECE_OVERSIZE = "piece_oversize"
    DISCONNECTED_PIECE = "disconnected_piece"
    NO_CONTACT_FOR_JOINT = "no_contact_for_joint"
    JOINT_CLIPPED = "joint_clipped"
    ASSEMBLY_CONFLICT = "assembly_conflict"
    VERTICES_MERGED = "vertices_merged"


class SliceWarning(_Frozen):
    code: WarningCode
    message: str
    subject: str | None = None


# --- joint specs: a discriminated union; adding a kind = adding a model + a generator -------------


class NoJointSpec(_Frozen):
    kind: Literal["none"] = "none"

    @property
    def depth(self) -> float:
        return 0.0

    @property
    def clearance(self) -> float:
        return 0.0


class DowelJointSpec(_Frozen):
    """A cylindrical registration pin straddling the cut plane."""

    kind: Literal["dowel"] = "dowel"
    auto: bool = False
    """When true the numeric fields are ignored and derived from the model and bed by
    `core.joints.auto.resolve_joint`; the resolved spec (auto=False) is what the pipeline runs."""
    diameter: float = Field(default=8.0, gt=0)
    depth: float = Field(default=6.0, gt=0)
    clearance: float = Field(default=0.15, gt=0)
    edge_margin: float = Field(default=3.0, ge=0)
    spacing: float = Field(default=40.0, gt=0)


class DovetailJointSpec(_Frozen):
    """A sliding dovetail: trapezoid in the (u, normal) plane extruded along v through the cell.

    Pieces interlock against pull-apart along the normal and assemble by sliding along v."""

    kind: Literal["dovetail"] = "dovetail"
    auto: bool = False
    """When true the numeric fields are ignored and derived from the model and bed by
    `core.joints.auto.resolve_joint`; the resolved spec (auto=False) is what the pipeline runs."""
    neck_width: float = Field(default=8.0, gt=0)
    head_width: float = Field(default=12.0, gt=0)
    depth: float = Field(default=6.0, gt=0)
    clearance: float = Field(default=0.15, gt=0)
    edge_margin: float = Field(default=3.0, ge=0)
    spacing: float = Field(default=60.0, gt=0)

    @model_validator(mode="after")
    def _flared(self) -> DovetailJointSpec:
        if self.auto:  # numbers are ignored and re-derived; do not reject them
            return self
        if self.head_width <= self.neck_width:
            raise ValueError("head_width must exceed neck_width for a dovetail to interlock")
        return self


class JigsawJointSpec(_Frozen):
    """A jigsaw-puzzle knob: a round head on a neck, drawn in the (u, normal) plane and extruded
    along v through the cell, like a dovetail but with the classic puzzle-piece silhouette.

    Pieces interlock against pull-apart along the normal and assemble by sliding along v (for cuts
    along X and Y that is Z: pieces drop in from above, exactly like a flat puzzle)."""

    kind: Literal["jigsaw"] = "jigsaw"
    auto: bool = False
    """When true the numeric fields are ignored and derived from the model and bed by
    `core.joints.auto.resolve_joint`; the resolved spec (auto=False) is what the pipeline runs."""
    neck_width: float = Field(default=8.0, gt=0)
    head_diameter: float = Field(default=14.0, gt=0)
    depth: float = Field(default=18.0, gt=0)
    clearance: float = Field(default=0.15, gt=0)
    edge_margin: float = Field(default=3.0, ge=0)
    spacing: float = Field(default=60.0, gt=0)

    @model_validator(mode="after")
    def _knob(self) -> JigsawJointSpec:
        if self.auto:  # numbers are ignored and re-derived; do not reject them
            return self
        if self.head_diameter <= self.neck_width:
            raise ValueError("head_diameter must exceed neck_width for a jigsaw knob to interlock")
        if self.depth < self.head_diameter:
            raise ValueError(
                "depth must be at least head_diameter so the whole head sits past the plane"
            )
        return self


JointSpec = Annotated[
    NoJointSpec | DowelJointSpec | DovetailJointSpec | JigsawJointSpec, Field(discriminator="kind")
]


class CutPlan(_Frozen):
    bounds: Bounds
    limits: CellLimits
    cuts: AxisCuts
    cells: list[Cell]
    interfaces: list[CutInterface]
    warnings: list[SliceWarning] = Field(default_factory=list)
    resolved_joint: JointSpec | None = None
    """The concrete joint spec this plan was sized for (auto sizing already applied)."""

    @property
    def cell_count(self) -> int:
        """Upper bound on the number of pieces (empty cells are dropped at slice time)."""
        return len(self.cells)

    @functools.cached_property
    def cells_by_id(self) -> dict[str, Cell]:
        """``{cell.id: cell}``, built once per instance (not a field: never serialised/compared)."""
        return {c.id: c for c in self.cells}

    def cell(self, index: CellIndex) -> Cell:
        """The cell at `index` (O(1)). Raises KeyError(index.id) if the plan has no such cell."""
        found = self.cells_by_id.get(index.id)
        if found is None:
            raise KeyError(index.id)
        return found


class MaleSide(StrEnum):
    LOWER = "lower"
    UPPER = "upper"


class PartitionSpec(_Frozen):
    cuts: AxisCuts | None = None
    bed_margin: float = Field(default=2.0, ge=0)
    axes: list[Axis] = Field(default_factory=lambda: [Axis.X, Axis.Y, Axis.Z])
    """Axes the planner may cut along. A model larger than the bed along an excluded axis yields
    a CELL_OVERSIZE warning rather than a cut."""


class SliceSpec(_Frozen):
    print_volume: PrintVolume
    partition: PartitionSpec = PartitionSpec()
    joint: JointSpec = NoJointSpec()
    male_side: MaleSide = MaleSide.LOWER


class Placement(_Frozen):
    u: float
    v: float
    rotation: float = 0.0


class JointInfo(_Frozen):
    interface_id: str
    kind: str
    male_piece: str
    female_piece: str
    placement: Placement


class MeshAsset(_Frozen):
    model_id: str
    filename: str
    scale: float = Field(gt=0)
    triangle_count: int
    bounds: Bounds
    volume: float
    warnings: list[SliceWarning] = Field(default_factory=list)


class PieceInfo(_Frozen):
    piece_id: str
    cell: CellIndex
    component: int = 0
    bounds: Bounds
    volume: float
    triangle_count: int
    component_count: int
    fits_bed: bool
    print_offset: Vec3


class SliceStats(_Frozen):
    piece_count: int
    input_volume: float
    output_volume: float
    max_overlap_volume: float
    duration_s: float

    @property
    def volume_ratio(self) -> float:
        return self.output_volume / self.input_volume if self.input_volume else math.nan


class SliceResult(_Frozen):
    job_id: str
    model_id: str
    spec: SliceSpec
    plan: CutPlan
    pieces: list[PieceInfo]
    joints: list[JointInfo]
    stats: SliceStats
    warnings: list[SliceWarning] = Field(default_factory=list)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    """Mutable: the runner updates progress in place (under its own lock)."""

    job_id: str
    model_id: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    step: str = "queued"
    result: SliceResult | None = None
    error: str | None = None


class PrinterPreset(_Frozen):
    name: str
    print_volume: PrintVolume
