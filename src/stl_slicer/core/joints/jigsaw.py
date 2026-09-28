"""Jigsaw knob: a round head on a neck in the (u, n) plane, extruded along v through the cell.

Like a dovetail it slides in along v (world Z for X/Y cuts, so flat models assemble by dropping
pieces in from above, exactly like a flat puzzle), and the head being wider than the neck makes
it interlock against pull-apart along the normal.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from stl_slicer.core.geometry import Region2D
from stl_slicer.core.joints.base import ProfileStripJoint
from stl_slicer.core.models import JigsawJointSpec

__all__ = ["JigsawJoint"]

_HEAD_SEGMENTS = 48


class JigsawJoint(ProfileStripJoint[JigsawJointSpec]):
    kind: ClassVar[str] = "jigsaw"
    spec_type: ClassVar[type[BaseModel]] = JigsawJointSpec

    def strip_profiles(self, spec: JigsawJointSpec) -> tuple[Region2D, Region2D]:
        radius, depth = spec.head_diameter / 2, spec.depth
        head_z = depth - radius  # the head's far edge sits exactly at z = depth
        neck = Region2D.rect(-spec.neck_width / 2, 0.0, spec.neck_width / 2, head_z)
        head = Region2D.circle(radius, _HEAD_SEGMENTS).translate(0.0, head_z)
        # the spec guarantees depth >= head_diameter; the clip is a safeguard on the contract
        clip = Region2D.rect(-depth - radius, 0.0, depth + radius, depth)
        male = (neck | head) & clip
        return male, male.offset(spec.clearance)

    def strip_half_width(self, spec: JigsawJointSpec) -> float:
        return spec.head_diameter / 2
