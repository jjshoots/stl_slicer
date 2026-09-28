"""Tests for joint placement strategies."""

from __future__ import annotations

import pytest

from stl_slicer.core.geometry import Region2D
from stl_slicer.core.joints.placers import grid_placements, strip_placements

DOWEL = Region2D.circle(4.0)


def test_grid_centred_count() -> None:
    region = Region2D.rect(-47, -47, 47, 47)
    ps = grid_placements(region, DOWEL, 40)
    assert len(ps) == 9
    us = sorted({p.u for p in ps})
    assert us == pytest.approx([-40, 0, 40])
    assert sum(p.u for p in ps) == pytest.approx(0)
    assert sum(p.v for p in ps) == pytest.approx(0)


def test_grid_rejects_near_edge() -> None:
    # 0..82 wide: grid centred at 41 with spacing 40 → u in {1, 41, 81}; 1 and 81 are too close
    region = Region2D.rect(0, 0, 82, 10)
    ps = grid_placements(region, DOWEL, 40)
    assert [p.u for p in ps] == pytest.approx([41])
    assert all(region.contains(DOWEL.translate(p.u, p.v)) for p in ps)


def test_grid_fallback_deepest_point_in_ring() -> None:
    ring = Region2D.rect(-50, -50, 50, 50) - Region2D.rect(-30, -30, 30, 30)
    ps = grid_placements(ring, DOWEL, 200)  # only candidate is the centre, inside the hole
    assert len(ps) == 1
    p = ps[0]
    assert ring.contains_point(p.u, p.v)
    assert ring.contains(DOWEL.translate(p.u, p.v))
    assert max(abs(p.u), abs(p.v)) > 30


def test_grid_empty() -> None:
    assert grid_placements(Region2D.empty(), DOWEL, 40) == []
    assert grid_placements(Region2D.rect(0, 0, 3, 3), DOWEL, 40) == []


def test_strip_count_and_symmetry() -> None:
    region = Region2D.rect(-47, -47, 47, 47)
    ps = strip_placements(region, 6, 60)
    assert [p.u for p in ps] == pytest.approx([-30, 30])
    assert all(p.v == pytest.approx(0) for p in ps)

    ps = strip_placements(Region2D.rect(10, 0, 110, 20), 5, 20)
    us = [p.u for p in ps]
    assert len(us) == 5
    assert sum(us) / len(us) == pytest.approx(60)
    assert all(p.v == pytest.approx(10) for p in ps)


def test_strip_fallback_widest_run() -> None:
    # two components; the centred pattern (one candidate at u=50) falls in the gap
    region = Region2D.rect(0, 0, 30, 10) | Region2D.rect(55, 0, 100, 10)
    ps = strip_placements(region, 10, 200)
    assert len(ps) == 1
    assert ps[0].u == pytest.approx(77.5)


def test_strip_too_narrow() -> None:
    assert strip_placements(Region2D.rect(0, 0, 5, 50), 6, 60) == []
    assert strip_placements(Region2D.empty(), 6, 60) == []
