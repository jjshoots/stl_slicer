"""Cylindrical dowel: a pin on the male piece, a clearance hole in the female piece."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from stl_slicer.core.geometry import Region2D
from stl_slicer.core.joints.base import ProfileExtrusionJoint
from stl_slicer.core.models import DowelJointSpec

__all__ = ["DowelJoint"]

_SEGMENTS = 32


class DowelJoint(ProfileExtrusionJoint[DowelJointSpec]):
    kind: ClassVar[str] = "dowel"
    spec_type: ClassVar[type[BaseModel]] = DowelJointSpec

    def profile(self, spec: DowelJointSpec) -> Region2D:
        return Region2D.circle(spec.diameter / 2, _SEGMENTS)
