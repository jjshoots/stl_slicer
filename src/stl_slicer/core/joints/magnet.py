"""Magnet pockets: a cylindrical pocket for a disc magnet on BOTH faces of the cut. Nothing
protrudes; the pieces snap together and come apart."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from stl_slicer.core.geometry import Region2D
from stl_slicer.core.joints.base import PocketJoint
from stl_slicer.core.models import MagnetJointSpec

__all__ = ["MagnetJoint"]

_SEGMENTS = 32


class MagnetJoint(PocketJoint[MagnetJointSpec]):
    kind: ClassVar[str] = "magnet"
    spec_type: ClassVar[type[BaseModel]] = MagnetJointSpec

    def profile(self, spec: MagnetJointSpec) -> Region2D:
        return Region2D.circle(spec.diameter / 2, _SEGMENTS)
