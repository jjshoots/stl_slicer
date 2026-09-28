"""Joint generator base classes (docs/00_design.md §4.2, docs/02_build_brief.md §2.3,
docs/03_more_joints.md)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, Protocol, TypeVar, cast

from manifold3d import Manifold
from pydantic import BaseModel

from stl_slicer.core.errors import SliceInvariantError
from stl_slicer.core.geometry import Joint, LocalFrame, Region2D
from stl_slicer.core.joints.placers import grid_placements, strip_placements
from stl_slicer.core.models import Axis, CellIndex, CutInterface, Placement, Vec3

__all__ = ["JointGenerator", "PocketJoint", "ProfileExtrusionJoint", "ProfileStripJoint"]

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


class _SpacedSpec(_SizedSpec, Protocol):
    """A sized spec whose placements repeat with `spacing` (every kind but `tongue`)."""

    @property
    def spacing(self) -> float: ...


class _PocketSpec(_SizedSpec, Protocol):
    """A sized spec for a pocket joint (no male tab; `depth` is 0)."""

    @property
    def pocket_depth(self) -> float: ...


def _sized(spec: BaseModel) -> _SizedSpec:
    return cast(_SizedSpec, spec)


def _spaced(spec: BaseModel) -> _SpacedSpec:
    return cast(_SpacedSpec, spec)


def _pocketed(spec: BaseModel) -> _PocketSpec:
    return cast(_PocketSpec, spec)


class JointGenerator(ABC, Generic[SpecT]):  # noqa: UP046 - signature fixed by the build brief
    kind: ClassVar[str]
    spec_type: ClassVar[type[BaseModel]]
    has_male: ClassVar[bool] = True
    """False for pocket joints: `call` uses `pocket` instead of `solid`, the male solid is empty
    and `Joint.male_pocket` carries the pocket on the male side."""

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
        flip = [0.0, 0.0, 1.0]
        joints: list[Joint] = []
        for p in unique:
            pocket_world: Manifold | None = None
            if self.has_male:
                m_local, f_local = self.solid(
                    frame, p, spec, interface.extent_u, interface.extent_v, region_inset
                )
                self._verify(m_local, f_local, depth, p)
                if mirror:
                    m_local, f_local = m_local.mirror(flip), f_local.mirror(flip)
                m_world = frame.to_world(m_local)
                f_world = frame.to_world(f_local)
                clearance_volume = float(f_world.volume()) - float(m_world.volume())
            else:
                f_local, p_local = self.pocket(frame, p, spec, region_inset)
                self._verify_pockets(f_local, p_local, float(_pocketed(spec).pocket_depth), p)
                if mirror:
                    f_local, p_local = f_local.mirror(flip), p_local.mirror(flip)
                m_world = Manifold()
                f_world = frame.to_world(f_local)
                pocket_world = frame.to_world(p_local)
                clearance_volume = float(f_world.volume()) + float(pocket_world.volume())
            joints.append(
                Joint(
                    interface_id=interface.id,
                    kind=self.kind,
                    male_cell=male,
                    female_cell=female,
                    placement=p,
                    male=m_world,
                    female=f_world,
                    clearance_volume=clearance_volume,
                    male_pocket=pocket_world,
                )
            )
        return joints

    def _where(self, p: Placement) -> str:
        return f"{self.kind} joint at (u={p.u:.3f}, v={p.v:.3f})"

    def _verify(self, male: Manifold, female: Manifold, depth: float, p: Placement) -> None:
        where = self._where(p)
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

    def _verify_pockets(
        self, female: Manifold, male_pocket: Manifold, pocket_depth: float, p: Placement
    ) -> None:
        where = self._where(p)
        for name, solid, lo, hi in (
            ("female pocket", female, 0.0, pocket_depth),
            ("male pocket", male_pocket, -pocket_depth, 0.0),
        ):
            if not float(solid.volume()) > 0:
                raise SliceInvariantError(f"{where}: {name} has no volume")
            bb = [float(x) for x in solid.bounding_box()]
            if bb[2] < lo - _Z_TOL or bb[5] > hi + _Z_TOL:
                raise SliceInvariantError(
                    f"{where}: {name} z-extent [{bb[2]:.6f}, {bb[5]:.6f}] outside [{lo}, {hi}]"
                )

    @abstractmethod
    def solid(
        self,
        local: LocalFrame,
        placement: Placement,
        spec: SpecT,
        extent_u: float,
        extent_v: float,
        region: Region2D,
    ) -> tuple[Manifold, Manifold]:
        """(male, female) in the LOCAL frame: x=u, y=v, z=normal into the female side. `region`
        is the placement region (already inset by the edge margin); most kinds ignore it."""

    def pocket(
        self, local: LocalFrame, placement: Placement, spec: SpecT, region: Region2D
    ) -> tuple[Manifold, Manifold]:
        """Pocket joints (`has_male` False): (female pocket, male pocket) in the LOCAL frame, the
        female pocket spanning z in [0, pocket_depth] and the male pocket [-pocket_depth, 0]."""
        raise NotImplementedError(f"{type(self).__name__} defines no pocket")

    def placements(
        self, region: Region2D, spec: SpecT, extent_u: float, extent_v: float
    ) -> list[Placement]:
        return grid_placements(region, self.footprint(spec), float(_spaced(spec).spacing))

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
        region: Region2D,
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


class PocketJoint(JointGenerator[SpecT]):
    """No male tab: a 2D profile (grown by the clearance) sunk `pocket_depth` into BOTH faces
    of the cut (magnet). The spec's `depth` is 0, so the planner reserves no protrusion."""

    has_male: ClassVar[bool] = False

    @abstractmethod
    def profile(self, spec: SpecT) -> Region2D:
        """The pocket cross-section WITHOUT clearance, centred at (0, 0)."""

    def footprint(self, spec: SpecT) -> Region2D:
        return self.profile(spec).offset(float(_sized(spec).clearance))

    def solid(
        self,
        local: LocalFrame,
        placement: Placement,
        spec: SpecT,
        extent_u: float,
        extent_v: float,
        region: Region2D,
    ) -> tuple[Manifold, Manifold]:
        raise NotImplementedError(f"{self.kind} is a pocket joint and has no male solid")

    def pocket(
        self, local: LocalFrame, placement: Placement, spec: SpecT, region: Region2D
    ) -> tuple[Manifold, Manifold]:
        clearance = float(_sized(spec).clearance)
        if not clearance > 0:
            raise ValueError(f"{self.kind} joint requires clearance > 0, got {clearance}")
        pocket_depth = float(_pocketed(spec).pocket_depth)
        footprint = self.footprint(spec).translate(placement.u, placement.v)
        female = local.extrude(footprint, 0.0, pocket_depth)
        male_pocket = local.extrude(footprint, -pocket_depth, 0.0)
        return female, male_pocket


def _axis_of(vec: Vec3) -> Axis:
    """The coordinate axis a (unit, axis-aligned) frame vector points along."""
    mags = [abs(c) for c in vec]
    return (Axis.X, Axis.Y, Axis.Z)[mags.index(max(mags))]


class ProfileStripJoint(JointGenerator[SpecT]):
    """A 2D profile drawn in the (in-plane, normal) plane and extruded along the other in-plane
    axis over the full extent of the interface, so the joint slides in along that axis
    (dovetail, jigsaw, tab).

    Slide-axis rule: the strip runs along the in-plane axis with the SMALLER extent (the model's
    thickness) and the profile is drawn across the larger one; ties go to `v`. A flat model
    therefore slides along Z for both X and Y cuts and assembles like a flat puzzle.

    Subclasses provide `strip_profiles(spec) -> (male, female)` in the (across, normal) plane,
    with the male spanning z in [0, depth] and the female = male grown by the clearance (z from
    -clearance), plus `strip_half_width(spec)` for `strip_placements`.

    `interlocks` says whether the profile is undercut (wider past the plane than at it), so the
    pieces can only be assembled by sliding: the pipeline's ASSEMBLY_CONFLICT check only
    considers interlocking strips."""

    interlocks: ClassVar[bool] = True

    @abstractmethod
    def strip_profiles(self, spec: SpecT) -> tuple[Region2D, Region2D]:
        """(male, female) cross-sections in the (x=across, z=normal) plane, centred on x = 0."""

    @abstractmethod
    def strip_half_width(self, spec: SpecT) -> float:
        """Half the footprint a strip needs across the region, perpendicular to the slide."""

    @staticmethod
    def _slides_along_u(extent_u: float, extent_v: float) -> bool:
        return extent_u < extent_v

    def slide_axis(self, interface: CutInterface) -> Axis:
        """World axis this joint slides along on `interface` (the smaller in-plane extent)."""
        frame = interface.frame
        if self._slides_along_u(interface.extent_u, interface.extent_v):
            return _axis_of(frame.u)
        return _axis_of(frame.v)

    @staticmethod
    def _prism(
        local: LocalFrame, profile: Region2D, y0: float, y1: float, along_u: bool
    ) -> Manifold:
        """Extrude a profile given in (across, z) along the slide axis over [y0, y1] (symmetric
        ranges only when `along_u`)."""
        # Extrude along local z over [-y1, -y0], then rotate +90 deg about x:
        # (x, y, z) -> (x, -z, y), so the profile's 2nd coordinate becomes z and the extrusion
        # covers local y in [y0, y1] with the profile drawn along local x (= u).
        out: Manifold = local.extrude(profile, -y1, -y0).rotate([90.0, 0.0, 0.0])
        if along_u:
            # Rotate +90 deg about z: (x, y) -> (-y, x). The profile now runs along local y (= v)
            # and the extrusion covers local x in [-y1, -y0] (the callers pass symmetric ranges).
            out = out.rotate([0.0, 0.0, 90.0])
        return out

    def solid(
        self,
        local: LocalFrame,
        placement: Placement,
        spec: SpecT,
        extent_u: float,
        extent_v: float,
        region: Region2D,
    ) -> tuple[Manifold, Manifold]:
        c = float(_sized(spec).clearance)
        if not c > 0:
            raise ValueError(f"{self.kind} joint requires clearance > 0, got {c}")
        male_profile, female_profile = self.strip_profiles(spec)
        along_u = self._slides_along_u(extent_u, extent_v)
        # the strip spans exactly the interface rect along the slide; the cell clip bounds it
        half_len = (extent_u if along_u else extent_v) / 2
        male = self._prism(local, male_profile, -half_len, half_len, along_u)
        female = self._prism(local, female_profile, -half_len - c, half_len + c, along_u)
        offset = [0.0, float(placement.v), 0.0] if along_u else [float(placement.u), 0.0, 0.0]
        return male.translate(offset), female.translate(offset)

    def placements(
        self, region: Region2D, spec: SpecT, extent_u: float, extent_v: float
    ) -> list[Placement]:
        hw, spacing = self.strip_half_width(spec), float(_spaced(spec).spacing)
        if not self._slides_along_u(extent_u, extent_v):
            return strip_placements(region, hw, spacing)
        # strips run along u: place across v by transposing the region, then map back
        return [Placement(u=p.v, v=p.u) for p in strip_placements(region.transpose(), hw, spacing)]
