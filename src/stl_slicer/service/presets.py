"""Built-in printer presets (build volumes in millimetres)."""

from __future__ import annotations

from stl_slicer.core.models import PrinterPreset, PrintVolume


def _preset(name: str, x: float, y: float, z: float) -> PrinterPreset:
    return PrinterPreset(name=name, print_volume=PrintVolume(x=x, y=y, z=z))


PRESETS: list[PrinterPreset] = [
    _preset("Bambu Lab A1 mini", 180, 180, 180),
    _preset("Bambu Lab P1S / X1C", 256, 256, 256),
    _preset("Prusa MK4", 250, 210, 220),
    _preset("Creality Ender 3", 220, 220, 250),
    _preset("Voron 2.4 (300)", 300, 300, 300),
]
