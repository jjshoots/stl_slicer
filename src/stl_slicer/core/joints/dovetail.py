"""Sliding dovetail: a trapezoid in the (u, n) plane extruded along v through the cell."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from stl_slicer.core.geometry import Region2D
from stl_slicer.core.joints.base import ProfileStripJoint
from stl_slicer.core.models import DovetailJointSpec

__all__ = ["DovetailJoint"]


class DovetailJoint(ProfileStripJoint[DovetailJointSpec]):
    kind: ClassVar[str] = "dovetail"
    spec_type: ClassVar[type[BaseModel]] = DovetailJointSpec

    def strip_profiles(self, spec: DovetailJointSpec) -> tuple[Region2D, Region2D]:
        c = spec.clearance
        neck, head, depth = spec.neck_width / 2, spec.head_width / 2, spec.depth
        male = Region2D.polygon([(-neck, 0.0), (neck, 0.0), (head, depth), (-head, depth)])
        # grown by `clearance` on all sides: half-widths + c, z from -c to depth + c
        female = Region2D.polygon(
            [(-(neck + c), -c), (neck + c, -c), (head + c, depth + c), (-(head + c), depth + c)]
        )
        return male, female

    def strip_half_width(self, spec: DovetailJointSpec) -> float:
        return spec.head_width / 2
