"""Sliding dovetail: a trapezoid in the (u, n) plane extruded along v through the cell."""

from __future__ import annotations

from typing import ClassVar

from manifold3d import Manifold
from pydantic import BaseModel

from stl_slicer.core.geometry import LocalFrame, Region2D
from stl_slicer.core.joints.base import JointGenerator
from stl_slicer.core.joints.placers import strip_placements
from stl_slicer.core.models import DovetailJointSpec, Placement

__all__ = ["DovetailJoint"]

_OVERSHOOT = 0.0  # v-extent equals the interface rect; the female-cell clip bounds it anyway


def _prism(local: LocalFrame, points: list[tuple[float, float]], y0: float, y1: float) -> Manifold:
    """Extrude a polygon given in local (x, z) along local y over [y0, y1]."""
    # Extrude along local z over [-y1, -y0], then rotate +90 deg about x: (x, y, z) -> (x, -z, y),
    # so the polygon's 2nd coordinate becomes z and the extrusion covers y in [y0, y1].
    prism = local.extrude(Region2D.polygon(points), -y1, -y0)
    out: Manifold = prism.rotate([90.0, 0.0, 0.0])
    return out


class DovetailJoint(JointGenerator[DovetailJointSpec]):
    kind: ClassVar[str] = "dovetail"
    spec_type: ClassVar[type[BaseModel]] = DovetailJointSpec

    def solid(
        self,
        local: LocalFrame,
        placement: Placement,
        spec: DovetailJointSpec,
        extent_u: float,
        extent_v: float,
    ) -> tuple[Manifold, Manifold]:
        c = float(spec.clearance)
        if not c > 0:
            raise ValueError(f"dovetail joint requires clearance > 0, got {c}")
        neck, head, depth = spec.neck_width / 2, spec.head_width / 2, spec.depth
        half_len = extent_v / 2 + _OVERSHOOT
        male = _prism(
            local,
            [(-neck, 0.0), (neck, 0.0), (head, depth), (-head, depth)],
            -half_len,
            half_len,
        )
        female = _prism(
            local,
            [(-(neck + c), -c), (neck + c, -c), (head + c, depth + c), (-(head + c), depth + c)],
            -half_len - c,
            half_len + c,
        )
        offset = [float(placement.u), 0.0, 0.0]
        return male.translate(offset), female.translate(offset)

    def placements(
        self, region: Region2D, spec: DovetailJointSpec, extent_u: float, extent_v: float
    ) -> list[Placement]:
        return strip_placements(region, spec.head_width / 2, spec.spacing)
