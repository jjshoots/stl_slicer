"""Miscellaneous routes: printer presets and health."""

from __future__ import annotations

from fastapi import APIRouter

from stl_slicer.core.models import PrinterPreset
from stl_slicer.service.presets import PRESETS

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/presets", response_model=list[PrinterPreset], operation_id="list_presets")
def list_presets() -> list[PrinterPreset]:
    """Return the built-in printer presets."""
    return list(PRESETS)


@router.get("/health", response_model=dict[str, str], operation_id="health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
