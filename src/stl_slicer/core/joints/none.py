"""The `none` joint: plain cuts, no registration features."""

from __future__ import annotations

from typing import ClassVar

from manifold3d import Manifold
from pydantic import BaseModel

from stl_slicer.core.geometry import Joint, LocalFrame, Region2D
from stl_slicer.core.joints.base import JointGenerator
from stl_slicer.core.models import CellIndex, CutInterface, NoJointSpec, Placement

__all__ = ["NoJoint"]


class NoJoint(JointGenerator[NoJointSpec]):
    kind: ClassVar[str] = "none"
    spec_type: ClassVar[type[BaseModel]] = NoJointSpec

    def call(
        self,
        interface: CutInterface,
        region: Region2D,
        spec: NoJointSpec,
        male: CellIndex,
        female: CellIndex,
    ) -> list[Joint]:
        if not isinstance(spec, self.spec_type):
            raise TypeError(f"NoJoint expects NoJointSpec, got {type(spec).__name__}")
        return []

    def solid(
        self,
        local: LocalFrame,
        placement: Placement,
        spec: NoJointSpec,
        extent_u: float,
        extent_v: float,
        region: Region2D,
    ) -> tuple[Manifold, Manifold]:
        raise NotImplementedError("the none joint has no solid")

    def placements(
        self, region: Region2D, spec: NoJointSpec, extent_u: float, extent_v: float
    ) -> list[Placement]:
        return []
