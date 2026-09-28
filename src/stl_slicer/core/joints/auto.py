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
- tab (docs/03_more_joints.md): ``width = clamp(0.10 e, 5, 30)``;
  ``depth = clamp(0.5 width, 3, 15)``; spacing and edge_margin as dovetail (using width);
  ``clearance = 0.15``.
- hexpin: as dowel with ``width`` (across flats) in place of ``diameter``.
- tongue: ``width = clamp(t / 3, 2, 12)``; ``depth = clamp(0.8 width, 3, 15)``;
  ``edge_margin = min(clamp(0.5 width + 1, 2, 8), 0.25 t)``; ``clearance = 0.15``; no spacing.
- magnet: ``diameter = 6 if t < 12 else 8 if t < 25 else 10``, times ``size_scale`` and snapped
  back to the nearest stock size in {4, 6, 8, 10, 12}; ``height = 3 if diameter >= 6 else 2``,
  times ``depth_scale`` and rounded to 0.5 mm; ``spacing = clamp(0.4 e, 20, 100)``;
  ``edge_margin = min(clamp(0.5 diameter + 2, 3, 10), 0.25 t)``; ``clearance = 0.1`` (the
  magnet spec's own default: a pocket fits a stock disc tighter than a printed tab). When the
  pocket ``diameter + 2 clearance`` does not fit across ``t - 2 edge_margin`` (the nominal 8 mm
  on a 12-16 mm thickness), the diameter steps down through the stock sizes until it does.

Two user coefficients, both default 1: ``size_scale`` multiplies the width quantity (head /
diameter) after its clamp, and the dependent neck / margin follow; ``depth_scale`` multiplies the
resulting depth. Validity is then re-established (jigsaw ``depth >= head``; dovetail
``depth >= 1``). The coefficients are echoed on the resolved spec.

A spec with ``auto=False`` or ``kind="none"`` is returned unchanged; otherwise the result is a spec
of the same kind with ``auto=False`` and the numeric fields replaced.
"""

from __future__ import annotations

from stl_slicer.core.models import (
    Bounds,
    DovetailJointSpec,
    DowelJointSpec,
    HexPinJointSpec,
    JigsawJointSpec,
    JointSpec,
    MagnetJointSpec,
    PrintVolume,
    TabJointSpec,
    TongueJointSpec,
)

__all__ = [
    "CLEARANCE",
    "MAGNET_CLEARANCE",
    "MAGNET_DIAMETERS",
    "clamp",
    "resolve_joint",
    "round_mm",
]

CLEARANCE = 0.15
MAGNET_CLEARANCE = 0.1
MAGNET_DIAMETERS = (4.0, 6.0, 8.0, 10.0, 12.0)
"""Stock disc-magnet diameters the auto rule snaps to."""


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

    ks, kd = spec.size_scale, spec.depth_scale
    scales = {"size_scale": ks, "depth_scale": kd}

    if isinstance(spec, JigsawJointSpec):
        head = round_mm(clamp(0.12 * e, 6, 40) * ks)
        depth = round_mm(1.3 * head * kd)
        return JigsawJointSpec(
            auto=False,
            head_diameter=head,
            neck_width=round_mm(0.55 * head),
            depth=max(depth, head),  # validator: the whole head sits past the plane
            spacing=round_mm(clamp(0.5 * e, 25, 150)),
            edge_margin=_edge_margin(clamp(0.5 * head + 2, 3, 15), t),
            clearance=CLEARANCE,
            **scales,
        )
    if isinstance(spec, DovetailJointSpec):
        head = round_mm(clamp(0.10 * e, 6, 30) * ks)
        return DovetailJointSpec(
            auto=False,
            head_width=head,
            neck_width=round_mm(0.65 * head),
            depth=max(round_mm(clamp(0.6 * head, 4, 20) * kd), 1.0),
            spacing=round_mm(clamp(0.5 * e, 25, 150)),
            edge_margin=_edge_margin(clamp(0.5 * head + 2, 3, 15), t),
            clearance=CLEARANCE,
            **scales,
        )
    if isinstance(spec, DowelJointSpec):
        diameter = round_mm(clamp(min(0.35 * t, 0.05 * e), 3, 12) * ks)
        return DowelJointSpec(
            auto=False,
            diameter=diameter,
            depth=round_mm(1.5 * diameter * kd),
            spacing=round_mm(clamp(0.4 * e, 20, 100)),
            edge_margin=_edge_margin(clamp(0.5 * diameter + 2, 3, 10), t),
            clearance=CLEARANCE,
            **scales,
        )
    if isinstance(spec, TabJointSpec):
        width = round_mm(clamp(0.10 * e, 5, 30) * ks)
        return TabJointSpec(
            auto=False,
            width=width,
            depth=round_mm(clamp(0.5 * width, 3, 15) * kd),
            spacing=round_mm(clamp(0.5 * e, 25, 150)),
            edge_margin=_edge_margin(clamp(0.5 * width + 2, 3, 15), t),
            clearance=CLEARANCE,
            **scales,
        )
    if isinstance(spec, HexPinJointSpec):
        width = round_mm(clamp(min(0.35 * t, 0.05 * e), 3, 12) * ks)
        return HexPinJointSpec(
            auto=False,
            width=width,
            depth=round_mm(1.5 * width * kd),
            spacing=round_mm(clamp(0.4 * e, 20, 100)),
            edge_margin=_edge_margin(clamp(0.5 * width + 2, 3, 10), t),
            clearance=CLEARANCE,
            **scales,
        )
    if isinstance(spec, TongueJointSpec):
        width = round_mm(clamp(t / 3, 2, 12) * ks)
        return TongueJointSpec(
            auto=False,
            width=width,
            depth=round_mm(clamp(0.8 * width, 3, 15) * kd),
            edge_margin=_edge_margin(clamp(0.5 * width + 1, 2, 8), t),
            clearance=CLEARANCE,
            **scales,
        )
    if isinstance(spec, MagnetJointSpec):
        nominal = 6.0 if t < 12 else 8.0 if t < 25 else 10.0
        diameter = min(MAGNET_DIAMETERS, key=lambda d: (abs(d - nominal * ks), d))
        margin = _edge_margin(clamp(0.5 * diameter + 2, 3, 10), t)
        # The pocket (diameter + 2 clearance) must fit across the thickness inside the margins;
        # on t in [12, 16.5) the nominal 8 mm does not, so step down through the stock sizes.
        while diameter + 2 * MAGNET_CLEARANCE > t - 2 * margin and diameter > MAGNET_DIAMETERS[0]:
            diameter = max(d for d in MAGNET_DIAMETERS if d < diameter)
            margin = _edge_margin(clamp(0.5 * diameter + 2, 3, 10), t)
        height = max(0.5, round((3.0 if diameter >= 6 else 2.0) * kd * 2) / 2)
        return MagnetJointSpec(
            auto=False,
            diameter=diameter,
            height=height,
            spacing=round_mm(clamp(0.4 * e, 20, 100)),
            edge_margin=margin,
            clearance=MAGNET_CLEARANCE,
            **scales,
        )
    raise TypeError(f"unsupported joint spec: {type(spec).__name__}")  # pragma: no cover
