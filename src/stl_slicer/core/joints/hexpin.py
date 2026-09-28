"""Hexagonal peg: a regular hexagon (`width` across flats) on the male piece, a clearance
socket in the female piece. Registers like a dowel and also resists rotation about its axis."""

from __future__ import annotations

import math
from typing import ClassVar

from pydantic import BaseModel

from stl_slicer.core.geometry import Region2D
from stl_slicer.core.joints.base import ProfileExtrusionJoint
from stl_slicer.core.models import HexPinJointSpec

__all__ = ["HexPinJoint", "hexagon"]


def hexagon(across_flats: float) -> Region2D:
    """A regular hexagon centred at the origin with vertices on the u axis, so the across-flats
    distance is measured along v and the across-corners distance (2 / sqrt(3) larger) along u."""
    r = across_flats / math.sqrt(3.0)  # circumradius: across flats = r * sqrt(3)
    return Region2D.polygon(
        [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    )


class HexPinJoint(ProfileExtrusionJoint[HexPinJointSpec]):
    kind: ClassVar[str] = "hexpin"
    spec_type: ClassVar[type[BaseModel]] = HexPinJointSpec

    def profile(self, spec: HexPinJointSpec) -> Region2D:
        return hexagon(spec.width)
