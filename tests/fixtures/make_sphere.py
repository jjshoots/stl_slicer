"""Generate tests/fixtures/sphere.stl: an icosphere of radius 30 mm (1280 faces, binary STL).

Run with `uv run python tests/fixtures/make_sphere.py`.
"""

from __future__ import annotations

from pathlib import Path

import trimesh

OUT = Path(__file__).resolve().parent / "sphere.stl"


def main() -> None:
    """Write the sphere fixture next to this script."""
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=30.0)
    data = sphere.export(file_type="stl")
    OUT.write_bytes(data if isinstance(data, bytes) else data.encode())
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(sphere.faces)} faces)")


if __name__ == "__main__":
    main()
