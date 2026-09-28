"""Tests for the built-in printer presets."""

from __future__ import annotations

from stl_slicer.core.models import PrinterPreset, PrintVolume
from stl_slicer.service.presets import PRESETS


def test_presets_exact_names_and_volumes_in_order() -> None:
    expected = [
        ("Bambu Lab A1 mini", (180, 180, 180)),
        ("Bambu Lab A1", (256, 256, 256)),
        ("Bambu Lab P1P", (256, 256, 256)),
        ("Bambu Lab P1S", (256, 256, 256)),
        ("Bambu Lab X1C", (256, 256, 256)),
        ("Bambu Lab X1E", (256, 256, 256)),
        ("Bambu Lab H2S", (340, 320, 340)),
        ("Bambu Lab H2D", (350, 320, 325)),
        ("Prusa MK4", (250, 210, 220)),
        ("Creality Ender 3", (220, 220, 250)),
        ("Voron 2.4 (300)", (300, 300, 300)),
    ]
    assert len(PRESETS) == 11
    got = [(p.name, (p.print_volume.x, p.print_volume.y, p.print_volume.z)) for p in PRESETS]
    assert got == expected


def test_preset_names_unique_and_types() -> None:
    assert len({p.name for p in PRESETS}) == len(PRESETS)
    for p in PRESETS:
        assert isinstance(p, PrinterPreset)
        assert isinstance(p.print_volume, PrintVolume)


def test_presets_serialise() -> None:
    dumped = [p.model_dump() for p in PRESETS]
    assert dumped[8] == {"name": "Prusa MK4", "print_volume": {"x": 250, "y": 210, "z": 220}}
