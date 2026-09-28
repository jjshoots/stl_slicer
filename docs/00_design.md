# 00 — Design: stl-slicer

v4 — slide-axis rule (2026-09-28): strip joints (dovetail, jigsaw) extrude along the in-plane
axis with the smaller extent and draw their profile across the larger one (ties → v), so flat
models assemble like a flat puzzle and `ASSEMBLY_CONFLICT` asks the generator for the slide axis.

v3 — build-time revisions (2026-09-28): dovetail strips span exactly the interface rect (no 1 mm
overshoot; `JOINT_CLIPPED` now only fires when a tab would enter a third cell); `JOINT_CLIPPED`
volume is measured against the plan's outer bounds; `check_pieces` treats overlaps ≤ 1e-9·input as
kernel noise; the hollow-box fixture in §9 uses a 4 mm dowel (a 10 mm wall cannot host the default
8 mm pin, which correctly yields `NO_CONTACT_FOR_JOINT`); deleting a model cancels its live jobs;
planner enforces `min_cell` only for explicit cuts. v1/v2 history below is unchanged.

v2 — post-review revision (2026-09-28): joints clipped to the female cell and placement regions
inset from interior edges (B1/B2); dovetail replaces the misnamed jigsaw; discriminated joint specs;
slicing split into pure functions; scale moved to upload; frames, stores, cancel, memory caps
defined. v1 (2026-09-28) was the initial design; see `01_design_review.md` for what changed and why.

## 0. Problem

Take a watertight STL, partition it into pieces that each fit a user's print bed, and optionally
give adjacent pieces joints so the printed parts register (dowel pins) or **interlock** (sliding
dovetails — the "puzzle cut"). Run as a local web app with a 3D viewer for the input model, the
planned cut planes, and the resulting pieces (exploded view, per-piece selection).

Non-goals for v1: auto-orientation, non-axis-aligned cuts, mesh repair beyond vertex merging,
supports, G-code, multi-user, persistence across restarts, keyed (anti-rotation) pegs.

## 1. Evidence (probes, 2026-09-28; trimesh 5.1.0, manifold3d 3.5.4, numpy 2.5.3, py3.12)

| claim | measurement |
|---|---|
| Box-intersection chunking conserves volume exactly | 8 pieces of a 60 mm icosphere: Σvol == original |
| Pin joints via boolean stay watertight | both pieces watertight, genus 0 |
| Cell-modification joints give disjoint pieces **for one interface pair** | `(A ^ B).volume() == 0.0` |
| …but NOT across a corner or a thin cell without extra rules | reviewer probes: 42.8 mm³ diagonal overlap; 100 mm³ through a 4 mm cell |
| Cross-section clip + inset + containment work | `Manifold.slice`, `^ rect`, `.offset(-6)` |
| `slice(p)` overstates contact at a coplanar face | area 400 vs true 200 → use `slice(p−ε) ∩ slice(p+ε)` |
| Non-watertight input → empty Manifold, no exception | `status == Error.NotManifold`, volume 0 |
| Performance is not a v1 concern | 27 cuts of a 327,680-face mesh: 0.14 s |
| GLB is the viewer transfer format | STL 16.0 MB vs GLB 5.8 MB for the same mesh |

**manifold3d is the geometry kernel; trimesh is the IO adapter only** (no trimesh booleans).

## 2. Stack (rulings R1, R2, R6)

| layer | pick | why |
|---|---|---|
| geometry | manifold3d + numpy | exact robust booleans, 2D CrossSection algebra, fast |
| mesh IO | trimesh | STL/OBJ/3MF/GLB, scene export with named nodes |
| contracts | pydantic v2 | JSON schema → OpenAPI → generated TS types |
| backend | FastAPI + uvicorn, `separate_input_output_schemas=False` | typed, OpenAPI, one TS type per model |
| CLI | typer | shares the pipeline; cheapest end-to-end test |
| frontend | Vite + React 19 + TypeScript + react-three-fiber + drei + zustand | interactive client-side 3D state; Streamlit rejected (reruns, no per-piece selection) |
| API types | `openapi-typescript` → committed `web/src/api/schema.d.ts`, drift-gated | one source of truth |
| tests | pytest + hypothesis; vitest + testing-library | — |
| packaging | uv; npm; `stl-slicer serve` mounts `web/dist` | one command launches everything |

## 3. Domain shape

```
bytes ─load──▶ LoadedModel ─plan_grid──▶ CutPlan ─contact_regions──▶ regions
             (io.loaders)  (core.planning)          (core.slicing)
   regions ─JointGenerator.call──▶ joints ─joint_cells──▶ cells′ ─carve──▶ pieces ─check_pieces──▶ stats
           (core.joints)                  (core.slicing)         (core.slicing)   (core.slicing)
   pipeline.slice_model composes all of the above into SliceOutput(result: SliceResult, pieces)
```

All stages are pure functions or template-method classes over value types. Only `pipeline` knows
the order; only `service` knows about threads, ids and storage.

### Key insight (R3, hardened): joints are cell-volume modifications

Each joint yields a `(male, female)` solid pair in **world coordinates**, both lying on the female
side of the interface plane, with `male ⊂ female` (female = male grown by the clearance, including
at the tip). The plan's cell for the male side becomes `cell ∪ male`; the female side's cell
becomes `cell − female`. Every piece is then **one** intersection `mesh ∩ cell′`. Tabs exist only
where the model has material, so a tab near a thin wall is trimmed rather than floating.

Three rules, all owned by `core/slicing.py`, make pieces **pairwise disjoint by construction**:

1. **Union before subtract**: `cell′ = (cell ∪ ⋃males_out) − ⋃females_in`, in that order.
2. **Clip to the female cell**: every male and female solid is intersected with the female cell's
   AABB before use, so nothing reaches a third cell (B2). If clipping removed volume, warn `JOINT_CLIPPED`.
3. **Inset from interior edges**: the placement region for an interface is the contact region inset
   by `depth + clearance` along every rect edge that lies on another cut plane, then by the joint's
   own `edge_margin`. Two tabs entering the same cell from different faces therefore cannot meet (B1).

`check_pieces` verifies at runtime: pairwise intersection volume over the 26-neighbourhood of every
cell ≤ ε, and `mesh.volume − Σclearance_shells − ε ≤ Σpieces ≤ mesh.volume + ε`. Results land in
`SliceStats`; a disjointness violation raises `SliceInvariantError` (a bug, not a warning).

### Bed-fit reservation (M2)

A piece protrudes past its cell by `depth` on the side(s) where it is male. With a fixed
`male_side`, that is one side per axis:
`max_cell = bed − sides·depth − 2·bed_margin`, `sides = 1` (`lower`/`upper`), `depth = 0` for `none`.
The pipeline derives `CellLimits`; the planner never sees the joint spec. `fits_bed` is computed
from the **final** piece bounds against the bed.

## 4. Contracts

`base` = enforced by the base `call` whatever the hook returns; `hook` = subclass responsibility,
verified by the conformance suite every registered variant runs through.

### 4.1 `plan_grid(bounds: Bounds, limits: CellLimits, cuts: AxisCuts | None = None) -> CutPlan` (concrete; M10)

1. Raises `PlanError` if any `limits.max_cell` component ≤ 0, or if given cuts are unsorted,
   duplicated, outside `(min, max)` open interval, or closer together than `limits.min_cell`.
2. When `cuts is None`, positions per axis are `even_cuts(lo, hi, max_cell)`: `n = ceil(extent/max_cell)`
   cells, `n−1` equally spaced interior cuts. Then every cell ≤ `max_cell` (by construction).
3. When `cuts` are given, a cell wider than `max_cell` yields `CELL_OVERSIZE` (axis named) — this is
   the only path that can produce it.
4. Cells tile `bounds` exactly along each axis; indexed `(i, j, k)` ascending; `Cell.id = "x{i}_y{j}_z{k}"`.
5. `interfaces` = one `CutInterface` per axis-adjacent cell pair, carrying a `PlaneFrame` whose
   normal points from `lower` to `upper`, `u`/`v` the two other axes in cyclic order, `origin` at the
   rect centre, `extent_u/extent_v`, and `interior_edges` = which of the four rect edges lie on
   another interior cut plane (needed by rule 3).
6. Pure and deterministic; never touches a mesh.

### 4.2 `JointGenerator.call(interface: CutInterface, region: Region2D, spec: <KindSpec>) -> list[Joint]`

1. `base` Returns `[]` if `region` is empty after `inset(spec.edge_margin)`.
2. `base` Placements come from `self.placements(region_inset, spec)`; the base sorts them by `(u, v)`
   and rejects duplicates.
3. `base` For each placement, `self.solid(local, placement, spec)` returns `(male, female)` in the
   **local frame** (z = normal into the female side, x = u, y = v, origin on the plane). The base
   verifies `male.volume() > 0`, `(male − female).volume() == 0`, `female.volume() > male.volume()`,
   `male.bounds.z ∈ [0, depth]`, then transforms both to world via the interface frame.
4. `base` Each `Joint` carries provenance: `interface_id, kind, male_cell, female_cell, placement`.
5. `hook` `placements(region, spec) -> list[Placement]`; default = `grid_placements(region, footprint, spacing)`
   from `placers.py` (grid over region bounds, keep points whose footprint ⊂ region; fallback to the
   deepest interior point via iterative inset; `[]` if none). Dovetail overrides with `strip_placements`.
6. `hook` `solid(local: LocalFrame, placement, spec) -> (Manifold, Manifold)`. `ProfileExtrusionJoint`
   (mixin) implements it from a `profile(spec) -> CrossSection` hook: male = extrude(profile, depth),
   female = extrude(profile.offset(clearance), depth + clearance). Requires `clearance > 0`.
7. `hook` `footprint(spec) -> CrossSection` (for the default placer's containment test).

Variants (v1): `NoJoint` (`kind="none"`, returns `[]`), `DowelJoint` (`kind="dowel"`, circle profile,
ProfileExtrusion), `DovetailJoint` (`kind="dovetail"`): trapezoid in the (u, n) plane — neck width at
n = 0, head width at n = depth — extruded along the *full* v-extent of the rect (through the cell,
so assembly is a slide along v); female = trapezoid offset by clearance, same length + 2·clearance;
placements = `strip_placements` along u with `spacing`, each strip's u-interval inside the
region's projection perpendicular to the slide. Slide axis (dovetail and jigsaw alike) = the
in-plane axis with the **smaller** extent (the model's thickness); ties → `v`. The profile is drawn
across the larger extent. A flat model therefore slides along Z for both X and Y cuts (a flat
puzzle); a tall bar cut along Z slides along the shorter of X/Y (ties → Y).
Pieces whose dovetails have different slide axes get `ASSEMBLY_CONFLICT` (a warning; assembly
order is the user's problem, but they are told).

### 4.3 `core/slicing.py` (pure functions; M8)

- `contact_regions(mesh, plan, eps=1e-3) -> dict[str, Region2D]`: per interface,
  `slice(p−eps) ∩ slice(p+eps) ∩ rect`, then inset by `depth + clearance` along `interior_edges`.
  The inset amount is a parameter; the pipeline passes it from the spec.
- `male_side(interface, rule) -> tuple[CellIndex, CellIndex]` (male, female).
- `joint_cells(plan, joints) -> dict[str, Manifold]`: rules 1–2 of §3; returns `cell′` per cell id and
  the list of `JOINT_CLIPPED` warnings.
- `carve(mesh, cells′, plan) -> list[Piece]`: `mesh ∩ cell′`; drops empty results; drops zero-volume
  components; `component_count` recorded; `piece_id = f"p_{cell.id}"` (component suffix reserved).
- `check_pieces(pieces, plan, mesh_volume, clearance_volume) -> SliceStats`.

### 4.4 `pipeline.slice_model(model: LoadedModel, spec: SliceSpec, progress: ProgressSink, cancel: CancelToken) -> SliceOutput`

Derives `CellLimits`; calls the above in order; checks `cancel` between cuts (raises `Cancelled`);
reports `planning → contacts → joints → cutting i/n → checking`; collects warnings; computes
`fits_bed`, `print_offset` per piece.

## 5. Models (`core/models.py`, pydantic v2, leaf module)

```python
Vec3 = tuple[float, float, float]
class Axis(StrEnum): X="x"; Y="y"; Z="z"
class Bounds(BaseModel):       min: Vec3; max: Vec3                         # size, center, extent(axis)
class PrintVolume(BaseModel):  x: float; y: float; z: float                 # gt=0
class CellLimits(BaseModel):   max_cell: Vec3; min_cell: float = 1.0
class AxisCuts(BaseModel):     x: list[float] = []; y: list[float] = []; z: list[float] = []
class CellIndex(BaseModel):    i: int; j: int; k: int                       # .id -> "x{i}_y{j}_z{k}"
class Cell(BaseModel):         index: CellIndex; bounds: Bounds            # .id
class PlaneFrame(BaseModel):   origin: Vec3; normal: Vec3; u: Vec3; v: Vec3
class CutInterface(BaseModel): id: str; axis: Axis; position: float; lower: CellIndex; upper: CellIndex
                               frame: PlaneFrame; extent_u: float; extent_v: float
                               interior_edges: list[Literal["u_min","u_max","v_min","v_max"]]
class WarningCode(StrEnum):    CELL_OVERSIZE, PIECE_OVERSIZE, DISCONNECTED_PIECE, NO_CONTACT_FOR_JOINT,
                               JOINT_CLIPPED, ASSEMBLY_CONFLICT, VERTICES_MERGED
class SliceWarning(BaseModel): code: WarningCode; message: str; subject: str | None = None
class CutPlan(BaseModel):      bounds: Bounds; limits: CellLimits; cuts: AxisCuts; cells: list[Cell]
                               interfaces: list[CutInterface]; warnings: list[SliceWarning]
                               # cell_count property: "cells (upper bound on pieces)"

class NoJointSpec(BaseModel):       kind: Literal["none"] = "none"
class DowelJointSpec(BaseModel):    kind: Literal["dowel"] = "dowel"; diameter: float = 8; depth: float = 6
                                    clearance: float = 0.15; edge_margin: float = 3; spacing: float = 40
class DovetailJointSpec(BaseModel): kind: Literal["dovetail"] = "dovetail"; neck_width: float = 8; head_width: float = 12
                                    depth: float = 6; clearance: float = 0.15; edge_margin: float = 3; spacing: float = 60
JointSpec = Annotated[NoJointSpec | DowelJointSpec | DovetailJointSpec, Field(discriminator="kind")]
# every spec exposes .depth (0 for none) and .clearance (0 for none) via a shared protocol/property

class MaleSide(StrEnum):       LOWER="lower"; UPPER="upper"
class PartitionSpec(BaseModel): cuts: AxisCuts | None = None; bed_margin: float = 2.0
class SliceSpec(BaseModel):    print_volume: PrintVolume; partition: PartitionSpec = PartitionSpec()
                               joint: JointSpec = NoJointSpec(); male_side: MaleSide = MaleSide.LOWER

class Placement(BaseModel):    u: float; v: float; rotation: float = 0
class JointInfo(BaseModel):    interface_id: str; kind: str; male_piece: str; female_piece: str; placement: Placement

class MeshAsset(BaseModel):    model_id: str; filename: str; scale: float; triangle_count: int; bounds: Bounds
                               volume: float; warnings: list[SliceWarning]
class PieceInfo(BaseModel):    piece_id: str; cell: CellIndex; component: int = 0; bounds: Bounds; volume: float
                               triangle_count: int; component_count: int; fits_bed: bool; print_offset: Vec3
class SliceStats(BaseModel):   piece_count: int; input_volume: float; output_volume: float
                               max_overlap_volume: float; duration_s: float
class SliceResult(BaseModel):  job_id: str; model_id: str; spec: SliceSpec; plan: CutPlan; pieces: list[PieceInfo]
                               joints: list[JointInfo]; stats: SliceStats; warnings: list[SliceWarning]
class JobStatus(StrEnum):      QUEUED, RUNNING, DONE, FAILED, CANCELLED
class Job(BaseModel):          job_id: str; model_id: str; status: JobStatus; progress: float; step: str
                               result: SliceResult | None = None; error: str | None = None
class PrinterPreset(BaseModel): name: str; print_volume: PrintVolume
```

Errors (`core/errors.py`): `SlicerError` ← `PlanError`, `MeshLoadError` (non-manifold etc.),
`SliceInvariantError`, `Cancelled`.

Non-model geometry (`core/geometry.py`, plain classes over manifold3d; never serialised):
`Mesh` (wraps `Manifold`: `from_arrays`, `to_arrays`, `volume`, `bounds`, `is_empty`,
`cross_section(frame, offset) -> Region2D`, `components()`, `__and__/__or__/__sub__`, `translate`),
`Region2D` (wraps `CrossSection`: `inset`, `inset_edges`, `area`, `contains(cs)`, `components`,
`bounds`, `deepest_point`), `LocalFrame` (to-world 4×4 from a `PlaneFrame`), `Joint` (`male`, `female`
Manifolds in world + provenance fields), `Piece(info: PieceInfo, mesh: Mesh)`,
`LoadedModel(asset: MeshAsset, mesh: Mesh)`, `SliceOutput(result, pieces)`.

## 6. Service and API

```
POST   /api/models                      multipart file + scale=1.0 → MeshAsset          (422 on non-manifold)
GET    /api/models/{id}                 MeshAsset
DELETE /api/models/{id}
GET    /api/models/{id}/mesh.glb        model frame
POST   /api/models/{id}/plan            SliceSpec → CutPlan     (sync, < 10 ms; live preview)
POST   /api/models/{id}/slice           SliceSpec → Job         (cancels a live job for the same model)
GET    /api/jobs/{id}                   Job
DELETE /api/jobs/{id}                   cancel
GET    /api/jobs/{id}/pieces.glb        one scene, node name = piece_id, model frame
GET    /api/jobs/{id}/pieces/{pid}.stl  print frame (min z = 0, xy-centred)
GET    /api/jobs/{id}/download.zip      STLs + manifest.json (= SliceResult)
GET    /api/presets                     list[PrinterPreset]
GET    /api/health
```

`service/` Protocols: `ModelStore` (LRU, cap 4; `put/get/delete`), `ArtifactStore` (piece meshes by
`(job_id, piece_id)`; keeps latest 2 jobs per model), `JobRunner` (`submit(model, spec) -> Job`,
`get`, `cancel`; `ThreadJobRunner` = single worker + `CancelToken`, publishes through `ProgressSink`).
`api/` routers are thin and never import manifold3d/trimesh (import-linter enforced); mesh bytes come
from `io.exporters` through the stores. Production mounts `web/dist`; dev proxies `/api` to :8000.

CLI: `stl-slicer serve [--dev] [--port]`, `stl-slicer slice FILE --bed 220x220x250 [--joint dowel|dovetail]
[--scale] -o out/`, `stl-slicer openapi`.

## 7. Frontend (`web/src`)

```
api/        client.ts (typed fetch; 404 → resets model), schema.d.ts (generated)
store/      data.ts (model, spec, plan, job, result), view.ts (explode, showPlanes, hidden, selected)
hooks/      useModelUpload, usePlanPreview (debounced), useSliceJob (submit + poll + cancel)
components/ layout/AppShell · spec/{PrintVolumeForm, PartitionForm, JointForm (kind registry), PlanSummary}
            viewer/{Viewer (ViewerProps only; no store imports), ModelMesh, CutPlanes, CellBoxes, PiecesScene (useGLTF nodes), BedOutline}
            pieces/{PiecesList, DownloadBar}
lib/        explode.ts (piece cell → offset), frames.ts, format.ts   (pure, unit-tested)
```

Rules: components never `fetch`; `viewer/` consumes `ViewerProps` and nothing from the store;
`JointForm` maps `kind → form component` (adding a joint kind = one entry).

## 8. Layout and import direction (import-linter, `pyproject.toml`)

```
src/stl_slicer/
  core/models.py, core/errors.py       leaf
  core/geometry.py                     ← models, errors
  core/planning.py                     ← models, errors
  core/joints/{base,none,dowel,dovetail,placers,registry}.py   ← models, geometry
  core/slicing.py                      ← models, geometry, joints
  core/pipeline.py                     ← all core
  io/loaders.py, io/exporters.py       ← core
  service/{stores,jobs,presets}.py     ← core, io
  api/{app,deps,routes_models,routes_jobs,routes_misc}.py      ← service, core.models, core.errors
  cli.py                               ← api, service, io, core
tests/  mirrors the package; tests/conformance/ holds the variant suites
web/    §7
docs/   00_design, 01_design_review, 02_build_brief
```

Layers: `cli → api → service → io → core`; `core.models`/`core.errors` import nothing internal;
`api`/`service` never import `manifold3d`/`trimesh`.

## 9. Tests

- Unit per module with synthetic meshes (`Mesh.box`, `Mesh.sphere` test factories).
- Conformance suite `tests/conformance/test_joints.py` parametrised over the registry: base items
  4.2.1–4.2.4 for every kind; adding a kind = registering it.
- Hypothesis on `even_cuts`/`plan_grid`: tiling, ≤ max_cell, count = Πceil, interfaces = Σ(n−1)·Π(others).
- Slicing invariants on a sphere, a hollow box (ring contact → deepest-point fallback), a 2×2 grid
  with dowels (B1 regression: overlap == 0), a thin explicit cell (B2 regression: `PlanError`), a
  coplanar step (M18 regression).
- Pipeline end-to-end with dowel and dovetail; volume bounds; `fits_bed` true for every piece when
  the bed is the reservation.
- API: upload → plan → slice → poll → pieces.glb → zip; non-manifold → 422; cancel; 404 after delete.
- Frontend: vitest on `lib/`, stores, `client.ts` mapping; render smoke of `SpecPanel` and `PiecesList`.
- Gates: `uv run pytest`, `uv run ruff check`, `uv run mypy`, `uv run lint-imports`, `npm run
  typecheck`, `npm test`, `npm run build`, schema drift (`npm run gen && git diff --exit-code`).

## 10. Decisions

### Rulings (dated 2026-09-28; do not re-open)

| # | ruling | why |
|---|---|---|
| R1 | React + r3f, not Streamlit | client-side interactive 3D state |
| R2 | manifold3d kernel, trimesh IO only | probes §1 |
| R3 | cell-volume joints + rules 1–3 + runtime `check_pieces` | disjoint by construction; B1/B2 |
| R4 | mm; `scale` applied at upload; all coordinates model-space-after-scale | one frame for viewer, plan, pieces |
| R5 | async job + poll, single worker, cancel/supersede | seconds-long jobs; simple |
| R6 | GLB for viewing (single scene per job), STL for printing (print frame) | size; explode needs one frame |
| R7 | planner concrete; joints a registry keyed by discriminated `kind` | sibling counts 1 vs 3 |
| R8 | disconnected pieces kept as one piece + warning; ids reserve a component slot | identity stability |
| R9 | v1 joint kinds: none, dowel (registration), dovetail (interlock). No "jigsaw" peg | a normal-extruded peg does not interlock |
| R10 | non-manifold input is a hard error after vertex merge | silently empty output otherwise |
| R11 | placement regions inset by depth+clearance on interior edges; solids clipped to female cell | B1, B2 |

### Build-time calls (decide as noted; not rulings)

| # | item | decision |
|---|---|---|
| O1 | dovetail slide axis | frame `v` (Z for X/Y interfaces, Y for Z); warn `ASSEMBLY_CONFLICT` on mixed axes per piece |
| O2 | ε for contact slices and overlap tolerance | 1e-3 mm slice offset; overlap ε = 1e-6·mesh volume |
| O3 | deepest interior point | iterative `offset(-step)` halving until empty; centroid of last non-empty largest component |
| O4 | LRU sizes | 4 models, 2 jobs per model |
