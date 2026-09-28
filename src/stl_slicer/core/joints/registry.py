"""Joint kind → generator lookup."""

from __future__ import annotations

from typing import Any

from stl_slicer.core.joints.base import JointGenerator
from stl_slicer.core.joints.dovetail import DovetailJoint
from stl_slicer.core.joints.dowel import DowelJoint
from stl_slicer.core.joints.hexpin import HexPinJoint
from stl_slicer.core.joints.jigsaw import JigsawJoint
from stl_slicer.core.joints.magnet import MagnetJoint
from stl_slicer.core.joints.none import NoJoint
from stl_slicer.core.joints.tab import TabJoint
from stl_slicer.core.joints.tongue import TongueJoint
from stl_slicer.core.models import (
    DovetailJointSpec,
    DowelJointSpec,
    HexPinJointSpec,
    JigsawJointSpec,
    MagnetJointSpec,
    NoJointSpec,
    TabJointSpec,
    TongueJointSpec,
)

__all__ = ["REGISTRY", "get_generator", "spec_clearance", "spec_depth"]

_AnySpec = (
    NoJointSpec
    | DowelJointSpec
    | DovetailJointSpec
    | JigsawJointSpec
    | TabJointSpec
    | HexPinJointSpec
    | TongueJointSpec
    | MagnetJointSpec
)

REGISTRY: dict[str, type[JointGenerator[Any]]] = {
    "none": NoJoint,
    "dowel": DowelJoint,
    "dovetail": DovetailJoint,
    "jigsaw": JigsawJoint,
    "tab": TabJoint,
    "hexpin": HexPinJoint,
    "tongue": TongueJoint,
    "magnet": MagnetJoint,
}


def get_generator(kind: str) -> JointGenerator[Any]:
    """Instantiate the generator for `kind`; KeyError for an unknown kind."""
    try:
        cls = REGISTRY[kind]
    except KeyError:
        raise KeyError(f"unknown joint kind: {kind!r}") from None
    return cls()


def spec_depth(spec: _AnySpec) -> float:
    """Protrusion past the cut plane the planner must reserve (0 for `none` and pocket kinds)."""
    return float(spec.depth)


def spec_clearance(spec: _AnySpec) -> float:
    return float(spec.clearance)
