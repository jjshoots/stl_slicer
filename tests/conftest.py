"""Shared fixtures. Synthetic geometry only; see docs/02_build_brief.md §4."""

import pytest

from stl_slicer.core.models import Bounds, PrintVolume


@pytest.fixture
def bed() -> PrintVolume:
    return PrintVolume(x=100, y=100, z=100)


@pytest.fixture
def unit_bounds() -> Bounds:
    return Bounds(min=(0, 0, 0), max=(1, 1, 1))
