"""Tongue and groove: one rectangular rib per interface running along the LONG in-plane axis,
centred across the thin one, with a matching groove in the female piece.

The strip rule is inverted with respect to dovetail / jigsaw / tab: the profile is drawn across
the thin axis and the rib runs along the long axis for the length of the placement region, so it
stops `depth + clearance` (+ `edge_margin`) short of interior cut planes, which is what keeps two
ribs entering the same cell from an X and a Y interface apart (B1 for ribs). No undercut, so the
pieces press together along the normal and nothing interlocks.
"""

from __future__ import annotations

from typing import ClassVar

from manifold3d import Manifold
from pydantic import BaseModel

from stl_slicer.core.geometry import LocalFrame, Region2D
from stl_slicer.core.joints.base import ProfileStripJoint
from stl_slicer.core.models import Placement, TongueJointSpec

__all__ = ["TongueJoint"]

_EPS = 1e-9


class TongueJoint(ProfileStripJoint[TongueJointSpec]):
    kind: ClassVar[str] = "tongue"
    spec_type: ClassVar[type[BaseModel]] = TongueJointSpec
    interlocks: ClassVar[bool] = False

    @staticmethod
    def _slides_along_u(extent_u: float, extent_v: float) -> bool:
        # inverted: the rib runs along the LONGER in-plane axis (ties -> v, as for the others)
        return extent_u > extent_v

    def inset_region(
        self, region: Region2D, spec: TongueJointSpec, extent_u: float, extent_v: float
    ) -> Region2D:
        # Unlike the other strips the rib spans the placement REGION (not the interface rect)
        # along its axis, so the margin along the rib is what stops it short of the edges: keep
        # the isotropic inset rather than the across-only one of `ProfileStripJoint`.
        return region.inset(float(spec.edge_margin))

    def strip_profiles(self, spec: TongueJointSpec) -> tuple[Region2D, Region2D]:
        hw, c = spec.width / 2, spec.clearance
        male = Region2D.rect(-hw, 0.0, hw, spec.depth)
        female = Region2D.rect(-hw - c, -c, hw + c, spec.depth + c)
        return male, female

    def strip_half_width(self, spec: TongueJointSpec) -> float:
        return spec.width / 2

    def placements(
        self, region: Region2D, spec: TongueJointSpec, extent_u: float, extent_v: float
    ) -> list[Placement]:
        """A single rib at the centre of the region's bounds, provided the region is at least
        `width` wide across the rib."""
        if region.is_empty:
            return []
        u0, v0, u1, v1 = region.bounds
        across = (v1 - v0) if self._slides_along_u(extent_u, extent_v) else (u1 - u0)
        if across + _EPS < spec.width:
            return []
        return [Placement(u=(u0 + u1) / 2, v=(v0 + v1) / 2)]

    def solid(
        self,
        local: LocalFrame,
        placement: Placement,
        spec: TongueJointSpec,
        extent_u: float,
        extent_v: float,
        region: Region2D,
    ) -> tuple[Manifold, Manifold]:
        c = spec.clearance
        if not c > 0:
            raise ValueError(f"{self.kind} joint requires clearance > 0, got {c}")
        male_profile, female_profile = self.strip_profiles(spec)
        along_u = self._slides_along_u(extent_u, extent_v)
        u0, v0, u1, v1 = region.bounds
        # the rib spans the placement region along its axis, centred on the placement
        half_len = ((u1 - u0) if along_u else (v1 - v0)) / 2
        male = self._prism(local, male_profile, -half_len, half_len, along_u)
        female = self._prism(local, female_profile, -half_len - c, half_len + c, along_u)
        offset = [float(placement.u), float(placement.v), 0.0]
        return male.translate(offset), female.translate(offset)
