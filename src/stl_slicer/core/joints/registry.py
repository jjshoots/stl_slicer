"""Joint kind → generator lookup."""

from __future__ import annotations

from typing import Any

from stl_slicer.core.joints.base import JointGenerator
from stl_slicer.core.joints.dovetail import DovetailJoint
from stl_slicer.core.joints.dowel import DowelJoint
from stl_slicer.core.joints.none import NoJoint
from stl_slicer.core.models import DovetailJointSpec, DowelJointSpec, NoJointSpec

__all__ = ["REGISTRY", "get_generator", "spec_clearance", "spec_depth"]

REGISTRY: dict[str, type[JointGenerator[Any]]] = {
    "none": NoJoint,
    "dowel": DowelJoint,
    "dovetail": DovetailJoint,
}


def get_generator(kind: str) -> JointGenerator[Any]:
    """Instantiate the generator for `kind`; KeyError for an unknown kind."""
    try:
        cls = REGISTRY[kind]
    except KeyError:
        raise KeyError(f"unknown joint kind: {kind!r}") from None
    return cls()


def spec_depth(spec: NoJointSpec | DowelJointSpec | DovetailJointSpec) -> float:
    return float(spec.depth)


def spec_clearance(spec: NoJointSpec | DowelJointSpec | DovetailJointSpec) -> float:
    return float(spec.clearance)
