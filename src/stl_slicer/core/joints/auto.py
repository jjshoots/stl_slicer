"""Auto joint sizing: derive concrete joint dimensions from the model and the bed.

Pure; imports only `core.models`. See docs/00_design.md §4.6.

Inputs: ``t`` = the model's smallest extent (its thickness); ``e`` = the typical piece edge =
``min(smallest bed dimension - 2 * bed_margin, largest model extent)``. Every length is rounded
to 0.1 mm; ``clamp(x, lo, hi)`` is the usual saturation. Placement regions are inset by
``edge_margin`` on every side (isotropically), so on a thin model the margin is additionally
capped at ``0.25 t``: a margin of ``t / 2`` or more would empty every contact region.

Rules (per kind):

- jigsaw: ``head_diameter = clamp(0.12 e, 6, 40)``; ``neck_width = 0.55 head``;
  ``depth = 1.3 head`` (the validator needs ``depth >= head``); ``spacing = clamp(0.5 e, 25, 150)``;
  ``edge_margin = min(clamp(0.5 head + 2, 3, 15), 0.25 t)``; ``clearance = 0.15``.
- dovetail: ``head_width = clamp(0.10 e, 6, 30)``; ``neck_width = 0.65 head``;
  ``depth = clamp(0.6 head, 4, 20)``; spacing and edge_margin as jigsaw (using head_width);
  ``clearance = 0.15``.
- dowel: ``diameter = clamp(min(0.35 t, 0.05 e), 3, 12)``; ``depth = 1.5 diameter``;
  ``spacing = clamp(0.4 e, 20, 100)``;
  ``edge_margin = min(clamp(0.5 diameter + 2, 3, 10), 0.25 t)``; ``clearance = 0.15``.

A spec with ``auto=False`` or ``kind="none"`` is returned unchanged; otherwise the result is a spec
of the same kind with ``auto=False`` and the numeric fields replaced.
"""

from __future__ import annotations

from stl_slicer.core.models import (
    Bounds,
    DovetailJointSpec,
    DowelJointSpec,
    JigsawJointSpec,
    JointSpec,
    PrintVolume,
)

__all__ = ["CLEARANCE", "clamp", "resolve_joint", "round_mm"]

CLEARANCE = 0.15


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def round_mm(x: float) -> float:
    """Round to 0.1 mm."""
    return round(x, 1)


def _typical_edge(bounds: Bounds, print_volume: PrintVolume, bed_margin: float) -> float:
    bed_min = min(print_volume.x, print_volume.y, print_volume.z)
    return min(bed_min - 2 * bed_margin, max(bounds.size))


def _edge_margin(nominal: float, t: float) -> float:
    """`nominal` capped at a quarter of the thickness so the isotropic inset cannot empty the
    contact region of a thin model."""
    return round_mm(min(nominal, 0.25 * t))


def resolve_joint(
    spec: JointSpec, bounds: Bounds, print_volume: PrintVolume, bed_margin: float
) -> JointSpec:
    """Return `spec` with its numeric fields derived from `bounds` and the bed when `spec.auto`
    is set; otherwise `spec` unchanged. The result always has ``auto=False``."""
    if spec.kind == "none" or not spec.auto:
        return spec
    e = _typical_edge(bounds, print_volume, bed_margin)
    t = min(bounds.size)

    if isinstance(spec, JigsawJointSpec):
        head = round_mm(clamp(0.12 * e, 6, 40))
        return JigsawJointSpec(
            auto=False,
            head_diameter=head,
            neck_width=round_mm(0.55 * head),
            depth=round_mm(1.3 * head),
            spacing=round_mm(clamp(0.5 * e, 25, 150)),
            edge_margin=_edge_margin(clamp(0.5 * head + 2, 3, 15), t),
            clearance=CLEARANCE,
        )
    if isinstance(spec, DovetailJointSpec):
        head = round_mm(clamp(0.10 * e, 6, 30))
        return DovetailJointSpec(
            auto=False,
            head_width=head,
            neck_width=round_mm(0.65 * head),
            depth=round_mm(clamp(0.6 * head, 4, 20)),
            spacing=round_mm(clamp(0.5 * e, 25, 150)),
            edge_margin=_edge_margin(clamp(0.5 * head + 2, 3, 15), t),
            clearance=CLEARANCE,
        )
    if isinstance(spec, DowelJointSpec):
        diameter = round_mm(clamp(min(0.35 * t, 0.05 * e), 3, 12))
        return DowelJointSpec(
            auto=False,
            diameter=diameter,
            depth=round_mm(1.5 * diameter),
            spacing=round_mm(clamp(0.4 * e, 20, 100)),
            edge_margin=_edge_margin(clamp(0.5 * diameter + 2, 3, 10), t),
            clearance=CLEARANCE,
        )
    raise TypeError(f"unsupported joint spec: {type(spec).__name__}")  # pragma: no cover
