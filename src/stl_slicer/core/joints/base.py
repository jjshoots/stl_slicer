"""Joint generator base classes (docs/00_design.md §4.2, docs/02_build_brief.md §2.3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, Protocol, TypeVar, cast

from manifold3d import Manifold
from pydantic import BaseModel

from stl_slicer.core.errors import SliceInvariantError
from stl_slicer.core.geometry import Joint, LocalFrame, Region2D
from stl_slicer.core.joints.placers import grid_placements
from stl_slicer.core.models import CellIndex, CutInterface, Placement

__all__ = ["JointGenerator", "ProfileExtrusionJoint"]

SpecT = TypeVar("SpecT", bound=BaseModel)

_Z_TOL = 1e-6
_VOL_TOL = 1e-9


class _SizedSpec(Protocol):
    """Attributes every real (non-`none`) joint spec carries."""

    @property
    def depth(self) -> float: ...
    @property
    def clearance(self) -> float: ...
    @property
    def edge_margin(self) -> float: ...
    @property
    def spacing(self) -> float: ...


def _sized(spec: BaseModel) -> _SizedSpec:
    return cast(_SizedSpec, spec)


class JointGenerator(ABC, Generic[SpecT]):  # noqa: UP046 - signature fixed by the build brief
    kind: ClassVar[str]
    spec_type: ClassVar[type[BaseModel]]

    def call(
        self,
        interface: CutInterface,
        region: Region2D,
        spec: SpecT,
        male: CellIndex,
        female: CellIndex,
    ) -> list[Joint]:
        """Place joints on `region` (the interface contact region, already inset from interior
        rect edges by the caller) and return them in world coordinates on the female side."""
        if not isinstance(spec, self.spec_type):
            raise TypeError(
                f"{type(self).__name__} expects {self.spec_type.__name__}, "
                f"got {type(spec).__name__}"
            )
        if female == interface.upper and male == interface.lower:
            mirror = False
        elif female == interface.lower and male == interface.upper:
            mirror = True
        else:
            raise ValueError(
                f"male/female must be the two cells of interface {interface.id}, "
                f"got {male.id}/{female.id}"
            )
        sized = _sized(spec)
        depth = float(sized.depth)
        region_inset = region.inset(float(sized.edge_margin))
        if region_inset.is_empty:
            return []

        placements = sorted(
            self.placements(region_inset, spec, interface.extent_u, interface.extent_v),
            key=lambda p: (p.u, p.v),
        )
        unique: list[Placement] = []
        for p in placements:
            if unique and (unique[-1].u, unique[-1].v) == (p.u, p.v):
                continue
            unique.append(p)

        frame = LocalFrame(interface.frame)
        joints: list[Joint] = []
        for p in unique:
            m_local, f_local = self.solid(frame, p, spec, interface.extent_u, interface.extent_v)
            self._verify(m_local, f_local, depth, p)
            if mirror:
                m_local = m_local.mirror([0.0, 0.0, 1.0])
                f_local = f_local.mirror([0.0, 0.0, 1.0])
            m_world = frame.to_world(m_local)
            f_world = frame.to_world(f_local)
            joints.append(
                Joint(
                    interface_id=interface.id,
                    kind=self.kind,
                    male_cell=male,
                    female_cell=female,
                    placement=p,
                    male=m_world,
                    female=f_world,
                    clearance_volume=float(f_world.volume()) - float(m_world.volume()),
                )
            )
        return joints

    def _verify(self, male: Manifold, female: Manifold, depth: float, p: Placement) -> None:
        where = f"{self.kind} joint at (u={p.u:.3f}, v={p.v:.3f})"
        male_vol = float(male.volume())
        if not male_vol > 0:
            raise SliceInvariantError(f"{where}: male solid has no volume")
        if float((male - female).volume()) > _VOL_TOL:
            raise SliceInvariantError(f"{where}: male solid is not contained in the female")
        if not float(female.volume()) > male_vol:
            raise SliceInvariantError(f"{where}: female volume does not exceed male volume")
        bb = [float(x) for x in male.bounding_box()]
        if bb[2] < -_Z_TOL or bb[5] > depth + _Z_TOL:
            raise SliceInvariantError(
                f"{where}: male z-extent [{bb[2]:.6f}, {bb[5]:.6f}] outside [0, {depth}]"
            )

    @abstractmethod
    def solid(
        self,
        local: LocalFrame,
        placement: Placement,
        spec: SpecT,
        extent_u: float,
        extent_v: float,
    ) -> tuple[Manifold, Manifold]:
        """(male, female) in the LOCAL frame: x=u, y=v, z=normal into the female side."""

    def placements(
        self, region: Region2D, spec: SpecT, extent_u: float, extent_v: float
    ) -> list[Placement]:
        return grid_placements(region, self.footprint(spec), float(_sized(spec).spacing))

    def footprint(self, spec: SpecT) -> Region2D:
        raise NotImplementedError(f"{type(self).__name__} defines no footprint")


class ProfileExtrusionJoint(JointGenerator[SpecT]):
    """A 2D profile extruded along the normal: male from 0 to depth, female grown by clearance."""

    @abstractmethod
    def profile(self, spec: SpecT) -> Region2D:
        """The joint cross-section, centred at (0, 0)."""

    def footprint(self, spec: SpecT) -> Region2D:
        return self.profile(spec)

    def solid(
        self,
        local: LocalFrame,
        placement: Placement,
        spec: SpecT,
        extent_u: float,
        extent_v: float,
    ) -> tuple[Manifold, Manifold]:
        sized = _sized(spec)
        depth, clearance = float(sized.depth), float(sized.clearance)
        if not clearance > 0:
            raise ValueError(f"{self.kind} joint requires clearance > 0, got {clearance}")
        profile = self.profile(spec)
        u, v = placement.u, placement.v
        male = local.extrude(profile.translate(u, v), 0.0, depth)
        female = local.extrude(
            profile.offset(clearance).translate(u, v), -clearance, depth + clearance
        )
        return male, female
