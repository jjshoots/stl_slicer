# stl-slicer

Partition an STL (or OBJ/3MF/GLB) mesh into pieces that each fit your print bed, with optional
joints so the printed parts register (dowel pins) or **interlock** (sliding dovetails). Runs as a
local web app with a 3D viewer for the model, the planned cut planes, and the exploded pieces.

- **Geometry kernel**: [manifold3d](https://github.com/elalish/manifold) (exact, robust booleans); trimesh only for file IO.
- **Backend**: FastAPI + pydantic v2; **frontend**: Vite + React + TypeScript + react-three-fiber.
- **Contracts first**: pydantic models → OpenAPI → generated TypeScript types (`web/src/api/schema.d.ts`).

## Quick start

```bash
uv sync                      # Python env
cd web && npm install && npm run build && cd ..
uv run stl-slicer serve      # http://127.0.0.1:8000
```

Development (hot reload on both sides):

```bash
uv run stl-slicer serve --dev          # API only, on :8000
cd web && npm run dev                  # Vite on :5173, proxies /api to :8000
```

CLI, no browser:

```bash
uv run stl-slicer slice model.stl --bed 220x220x250 --joint jigsaw -o out/   # add --manual to skip auto sizing
# out/: one STL per piece (print frame: min z = 0, xy-centred) + manifest.json (a SliceResult)
```

## How it works

1. **Plan** — the model's bounds are tiled into an even grid of cells no larger than
   `bed − joint depth − 2·bed_margin` per axis (or at explicit cut positions you supply).
2. **Contact regions** — for each interface between adjacent cells, the model's cross-section at
   the cut plane, inset so joints from different faces of a cell can never collide.
3. **Joints** — each joint is a `(male, female)` solid pair on the female side of the plane, with
   `female ⊇ male` by the clearance. The male cell becomes `cell ∪ male`, the female cell
   `cell − female`.
4. **Carve** — every piece is a single boolean `mesh ∩ cell′`, so tabs exist only where the model
   has material and pieces are pairwise disjoint by construction (verified at runtime).

Joint kinds (all auto-sized from the model and bed by default, with width/depth scale sliders):

| kind | shape | holds by |
|---|---|---|
| `dowel` | cylindrical pin along the cut normal | registration |
| `hexpin` | hexagonal peg | registration, anti-rotation |
| `tab` | rectangular tab along the cut (the classic slicer "connector") | registration |
| `tongue` | one tongue-and-groove rib along the whole seam | registration; strongest glue joint for panels |
| `dovetail` | flared strip through the thickness | interlocks; assemble by sliding |
| `jigsaw` | puzzle knob through the thickness | interlocks; flat models drop together like a puzzle |
| `magnet` | pockets on both faces for disc magnets (6×3 mm etc.) | snap together, separable |

Strip joints (dovetail, jigsaw, tab) run along the model's thinnest in-plane axis, so a flat model
cut in X and Y assembles by dropping pieces in along Z. A piece whose interlocking joints slide
along different axes gets an `assembly_conflict` warning. The "Cut along X / Y / Z" checkboxes
restrict which axes are cut.

## Layout

```
src/stl_slicer/
  core/       models (contracts), geometry (manifold3d wrapper), planning, joints/, slicing, pipeline
  io/         loaders (bytes → mesh), exporters (STL / GLB / zip)
  service/    in-memory stores, threaded job runner with cancel/supersede, printer presets
  api/        FastAPI routers (thin; never import the geometry kernel)
  cli.py      serve / slice / openapi
web/src/      api/ (typed client), store/, hooks/, components/{spec,viewer,pieces,layout}, lib/
docs/         00_design.md (architecture + rulings), 01_design_review.md, 02_build_brief.md
tests/        pytest mirrors the package; tests/conformance runs every registered joint kind
```

Import direction is enforced by import-linter: `cli → api → service → io → core`; `core.models`
imports nothing internal.

## Gates

```bash
uv run pytest -q && uv run ruff check src tests && uv run mypy && uv run lint-imports
cd web && npm run typecheck && npm test && npm run build
uv run stl-slicer openapi > openapi.json && (cd web && npm run gen) && git diff --exit-code   # schema drift
```

## Extending

- **New joint kind**: add a spec model to the `JointSpec` union in `core/models.py`, a generator in
  `core/joints/` registered in `registry.py` (the conformance suite picks it up automatically),
  and a form in `web/src/components/spec/JointForm.tsx`'s kind registry.
- **Persistence**: implement the `ModelStore` / `ArtifactStore` / `JobRunner` protocols in
  `service/` and inject them into `create_app`.
- Non-goals for v1 (recorded in `docs/00_design.md`): auto-orientation, non-axis cuts, mesh repair.
