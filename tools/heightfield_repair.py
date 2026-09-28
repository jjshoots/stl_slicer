"""Rebuild a relief-style mesh (a textured panel, a lithophane, a field of overlapping shells)
as one closed solid: the visible top surface sampled on a grid, over a flat base.

Usage: uv run python tools/heightfield_repair.py IN.stl OUT.stl [--cell 1.0] [--base 0.0]
       [--crop xmin,ymin,xmax,ymax]

The top surface is max z per grid cell (vertices and face centroids), holes are filled from
neighbours; the base sits `--base` mm below the lowest sampled z. Output is a watertight
heightfield: top grid, flat bottom, vertical walls."""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np
import trimesh


def sample_top(
    v: np.ndarray, f: np.ndarray, cell: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pts = np.vstack(
        [v, v[f].mean(1), v[f][:, [0, 1]].mean(1), v[f][:, [1, 2]].mean(1), v[f][:, [0, 2]].mean(1)]
    )
    lo = pts.min(0)
    nx, ny = int((pts[:, 0].max() - lo[0]) // cell) + 2, int((pts[:, 1].max() - lo[1]) // cell) + 2
    ix = ((pts[:, 0] - lo[0]) / cell).astype(int)
    iy = ((pts[:, 1] - lo[1]) / cell).astype(int)
    z = np.full((nx, ny), -np.inf)
    np.maximum.at(z, (ix, iy), pts[:, 2])
    has = np.isfinite(z)
    # fill small holes from the max of the 8-neighbourhood, a few passes
    for _ in range(4):
        miss = ~np.isfinite(z)
        if not miss.any():
            break
        pad = np.pad(z, 1, constant_values=-np.inf)
        neigh = np.max(
            np.stack(
                [
                    pad[i : i + nx, j : j + ny]
                    for i in range(3)
                    for j in range(3)
                    if (i, j) != (1, 1)
                ]
            ),
            0,
        )
        z = np.where(miss, neigh, z)
    return z, has, lo


def _manifold_mask(z: np.ndarray) -> np.ndarray:
    """Drop isolated cells and bridge diagonal-only contacts (two cells sharing just a corner
    would give their walls a vertical edge shared by four faces)."""
    z = z.copy()
    for _ in range(8):
        inside = np.isfinite(z)
        p = np.pad(inside, 1)
        n4 = p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
        z[inside & ~n4] = -np.inf
        inside = np.isfinite(z)
        a, b = inside[:-1, :-1], inside[1:, 1:]  # cell and its +x+y diagonal
        c, d = inside[1:, :-1], inside[:-1, 1:]  # the two cells between them
        diag = a & b & ~c & ~d
        anti = c & d & ~a & ~b
        if not diag.any() and not anti.any():
            return z
        i, j = np.nonzero(diag)
        z[i + 1, j] = np.maximum(z[i, j], z[i + 1, j + 1])
        i, j = np.nonzero(anti)
        z[i, j] = np.maximum(z[i + 1, j], z[i, j + 1])
    return z


def heightfield_mesh(z: np.ndarray, lo: np.ndarray, cell: float, base_z: float) -> trimesh.Trimesh:
    """Closed solid under the height map `z` (cells with -inf are outside)."""
    z = _manifold_mask(z)
    inside = np.isfinite(z)
    nx, ny = z.shape
    # vertex grid at cell corners: corner height = max of adjacent inside cells
    pad = np.pad(np.where(inside, z, -np.inf), 1, constant_values=-np.inf)
    corner = np.max(
        np.stack([pad[:-1, :-1], pad[1:, :-1], pad[:-1, 1:], pad[1:, 1:]]), 0
    )  # (nx+1, ny+1)
    cx, cy = np.meshgrid(
        np.arange(nx + 1) * cell + lo[0], np.arange(ny + 1) * cell + lo[1], indexing="ij"
    )
    top = np.stack([cx, cy, np.where(np.isfinite(corner), corner, base_z)], -1).reshape(-1, 3)
    bot = top.copy()
    bot[:, 2] = base_z
    verts = np.vstack([top, bot])
    nb = len(top)
    idx = lambda i, j: i * (ny + 1) + j  # noqa: E731
    ci, cj = np.nonzero(inside)
    a, b, c, d = idx(ci, cj), idx(ci + 1, cj), idx(ci + 1, cj + 1), idx(ci, cj + 1)
    faces = [
        np.stack([a, b, c], 1),
        np.stack([a, c, d], 1),
        np.stack([a + nb, c + nb, b + nb], 1),
        np.stack([a + nb, d + nb, c + nb], 1),
    ]

    # walls where an inside cell borders an outside cell
    def wall(p, q):  # edge p->q on the top, outward normal to the right of p->q
        faces.append(np.stack([p, p + nb, q + nb], 1))
        faces.append(np.stack([p, q + nb, q], 1))

    padi = np.pad(inside, 1)
    m = inside & ~padi[:-2, 1:-1]
    i, j = np.nonzero(m)
    wall(idx(i, j + 1), idx(i, j))  # -x side
    m = inside & ~padi[2:, 1:-1]
    i, j = np.nonzero(m)
    wall(idx(i + 1, j), idx(i + 1, j + 1))  # +x side
    m = inside & ~padi[1:-1, :-2]
    i, j = np.nonzero(m)
    wall(idx(i, j), idx(i + 1, j))  # -y side
    m = inside & ~padi[1:-1, 2:]
    i, j = np.nonzero(m)
    wall(idx(i + 1, j + 1), idx(i, j + 1))  # +y side
    mesh = trimesh.Trimesh(verts, np.vstack(faces), process=True)
    mesh.remove_unreferenced_vertices()
    return mesh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--cell", type=float, default=1.0)
    ap.add_argument(
        "--base", type=float, default=0.0, help="extra base thickness below the lowest z"
    )
    ap.add_argument(
        "--crop",
        type=str,
        default=None,
        help="xmin,ymin,xmax,ymax[,zmin,zmax] to keep (whole triangles)",
    )
    ap.add_argument(
        "--min-thickness",
        type=float,
        default=0.0,
        help="drop cells thinner than this above the base",
    )
    args = ap.parse_args()
    t0 = time.time()
    m = trimesh.load(args.src, force="mesh", process=False)
    v, f = np.asarray(m.vertices), np.asarray(m.faces)
    if args.crop:
        parts = list(map(float, args.crop.split(",")))
        x0, y0, x1, y1 = parts[:4]
        z0, z1 = (parts[4], parts[5]) if len(parts) == 6 else (-np.inf, np.inf)
        t = v[f]  # keep triangles whose every vertex lies inside the crop box
        keep = (t[:, :, 0] >= x0) & (t[:, :, 0] <= x1) & (t[:, :, 1] >= y0) & (t[:, :, 1] <= y1)
        keep &= (t[:, :, 2] >= z0) & (t[:, :, 2] <= z1)
        f = f[keep.all(1)]
    used = np.unique(f)
    remap = np.full(len(v), -1)
    remap[used] = np.arange(len(used))
    v, f = v[used], remap[f]
    z, has, lo = sample_top(v, f, args.cell)
    base_z = float(v[:, 2].min()) - args.base
    z = np.where(z - base_z >= args.min_thickness, z, -np.inf)
    mesh = heightfield_mesh(z, lo, args.cell, base_z)
    print(
        f"cells {has.sum()} inside; faces {len(mesh.faces)}; watertight {mesh.is_watertight}; "
        f"volume {mesh.volume:.0f} mm3; bounds {mesh.bounds.round(1).tolist()}; "
        f"{time.time() - t0:.1f}s"
    )
    if not mesh.is_watertight:
        sys.exit("result is not watertight")
    mesh.export(args.out)


if __name__ == "__main__":
    main()
