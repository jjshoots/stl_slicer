"""Rectangular tab: a plain `width` x `depth` rectangle in the (across, normal) plane extruded
along the thin in-plane axis through the cell (the "connector" of slicer tools). No undercut, so
it does not interlock: pieces press together along the normal."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from stl_slicer.core.geometry import Region2D
from stl_slicer.core.joints.base import ProfileStripJoint
from stl_slicer.core.models import TabJointSpec

__all__ = ["TabJoint"]


class TabJoint(ProfileStripJoint[TabJointSpec]):
    kind: ClassVar[str] = "tab"
    spec_type: ClassVar[type[BaseModel]] = TabJointSpec
    interlocks: ClassVar[bool] = False

    def strip_profiles(self, spec: TabJointSpec) -> tuple[Region2D, Region2D]:
        hw, c = spec.width / 2, spec.clearance
        male = Region2D.rect(-hw, 0.0, hw, spec.depth)
        female = Region2D.rect(-hw - c, -c, hw + c, spec.depth + c)
        return male, female

    def strip_half_width(self, spec: TabJointSpec) -> float:
        return spec.width / 2
