# 01 — Design review ledger

v1 — review of `00_design.md` v1, 2026-09-28. Five lens agents (Opus), one lens each, on the
document plus the probe scripts. Pre-pass tools (complexity, import-linter) do not apply to a
markdown design; reviewers were given the probe measurements instead. Refutation was performed by
the orchestrator (not by separate refute agents): every blocking/major finding was accepted only if
it came with probe evidence or a concrete counter-example the orchestrator could reproduce by
reasoning about the cell algebra. Findings that were rejected are listed with the reason. Nothing
below is to be re-opened without new evidence.

## Per-lens tally

| lens | produced | survived | died because |
|---|---|---|---|
| contract | 8 | 8 | — |
| granularity | 8 | 7 | "polling split / store mix": store split accepted, polling location accepted; "plan/ folder" trivially folded |
| extensibility | 8 | 6 | polytope cells rejected (non-goal, see below); schema-driven forms rejected (over-engineering) |
| geometry semantics | 8 | 8 | — |
| API + frontend | 8 | 8 | — |

No lens was miscalibrated; the geometry-semantics lens (which ran its own probes) was the most valuable.

## Blocking (2, both confirmed by reviewer probes)

| id | finding | fix folded into v2 |
|---|---|---|
| B1 | Corner collision: on a 2×2 grid with `male_side=lower`, the Y-tab of cell (1,0) and the X-tab of cell (0,1) both protrude into cell (1,1) and overlap near the shared edge (probe: 42.8 mm³ overlap; the Σvolume check passes). | Placement regions are inset by `depth + clearance` from every rect edge that lies on an interior cut line, *before* the joint's own edge margin. A runtime 26-neighbourhood pairwise overlap check records `max_overlap_volume` in `SliceStats` and raises if > ε. |
| B2 | Thin cells: nothing forbids a cell thinner than `depth + clearance` along its axis; a ±depth male passes through the female cell into a third cell (probe: 100 mm³ overlap, through-hole). | Male solids extend only into the female side (`0..depth` along the normal); `joint_cells` clips every male/female to the female cell's bounds and emits `JOINT_CLIPPED`. Planner rejects explicit cuts closer than `depth + clearance + 1 mm`. |

## Major — accepted (all)

| id | finding (lens) | fix folded into v2 |
|---|---|---|
| M1 | `female_2d` returned by a hook; zero-clearance passes the `male ⊂ female` check (contract) | Extrusion mixin derives female = `male_2d.offset(clearance)` extruded to `depth + clearance`; base asserts `clearance > 0` and `female.volume() > male.volume()` |
| M2 | `2·depth` reservation wrong for fixed male side; NoJoint still pays depth; `margin` ambiguous (contract, semantics) | `max_cell = bed − sides·depth − 2·bed_margin`, `sides = 1` for fixed side; `depth = 0` for `none`; renamed `bed_margin` / `edge_margin` |
| M3 | CellOversize warning makes the tiling promise vacuous; no guard for `max_cell ≤ 0`, unsorted/duplicate cuts (contract) | Planner validates limits and positions (raises); oversize is only possible for explicit cuts and is a warning there |
| M4 | Centroid fallback can land outside a ring/C-shaped contact (contract, semantics) | Fallback = deepest interior point via iterative inset; if nothing fits → `[]` + `NO_CONTACT_FOR_JOINT` |
| M5 | `genus ≥ 0` contradicts keeping disconnected pieces; checks were test-only (contract) | Genus check dropped; disjointness and volume bounds checked at runtime by `check_pieces`, recorded in stats |
| M6 | Union-then-subtract order unstated (contract) | Stated invariant of `joint_cells` |
| M7 | `Joint` type undefined; no mapping to `JointInfo` (contract) | Defined in `core/geometry.py`; `JointInfo` = provenance fields of `Joint` |
| M8 | Slicer does three jobs (granularity) | Split into `contact_regions`, `joint_cells`, `carve`, `check_pieces` — pure functions composed by the pipeline |
| M9 | Placer registry without selector; overlapping variants (granularity, extensibility) | Placer registry dropped; `JointGenerator.placements()` hook with a default grid helper; a generator owns its placement rule |
| M10 | Explicit partitioner is a data source not a strategy (granularity) | One concrete planner: `plan_grid(bounds, limits, cuts: AxisCuts | None)` with `even_cuts()` helper |
| M11 | Flat `JointSpec`; two `margin`s (granularity) | Discriminated union of per-kind spec models; `edge_margin` vs `bed_margin` |
| M12 | No unit binds mesh + metadata on input (granularity) | `LoadedModel(asset, mesh)` mirrors `Piece(info, mesh)` |
| M13 | Dovetail impossible with a 2D-profile hook (extensibility) | Hook is `solid(local_frame, placement, params) -> (male, female)`; `ProfileExtrusionJoint` mixin covers pin-type joints |
| M14 | Closed `JointKind` enum forces leaf edits (extensibility) | Per-kind spec models in a discriminated union; registry keyed by the `kind` literal; frontend form registry keyed the same way |
| M15 | Axis alignment in every contract (extensibility) | `CutInterface` carries a `PlaneFrame(origin, normal, u, v)` + `extent_u/extent_v`; joints and slicing consume only the frame. Cells stay AABBs (see rejected) |
| M16 | piece id = cell id blocks splitting (extensibility) | `PieceInfo{piece_id, cell, component}`, `JointInfo` refers to piece ids |
| M17 | Persistence protocols mis-aimed (extensibility) | `ArtifactStore` Protocol owns piece meshes; `ProgressSink` Protocol; layering allows `service → io` |
| M18 | Coplanar faces make `slice(p)` overstate contact (semantics) | `contact = slice(p−ε) ∩ slice(p+ε)`; zero-volume components dropped |
| M19 | "Jigsaw" peg is not an interlock (semantics) | v1 kinds: `none`, `dowel` (registration pin), `dovetail` (sliding interlock = the puzzle cut). Keyed peg is LATER under an honest name |
| M20 | Non-watertight input yields 0 pieces silently (semantics) | Loader merges vertices, then checks `Manifold.status()`; non-`NoError` → HTTP 422 / CLI error |
| M21 | `scale` only in `SliceSpec`; viewer and plan frames diverge (API) | `scale` is an upload parameter applied at load; all coordinates are model space after scale |
| M22 | Piece GLB vs STL frame undefined (API) | GLB = model frame (explode works with cell offsets); STL = print frame (min z = 0, xy-centred); `PieceInfo.print_offset` records the translation |
| M23 | Input/Output schema split breaks TS round-trip (API) | `FastAPI(separate_input_output_schemas=False)`; covered by schema gate |
| M24 | No cancel/supersede on the single worker (API) | `DELETE /api/jobs/{id}`; a new slice for the same model cancels its predecessor; `CancelToken` checked between cuts |
| M25 | Unbounded memory, no delete, no 404 recovery (API) | LRU of 4 models; latest 2 jobs per model; `DELETE /api/models/{id}`; frontend resets on 404 |

## Minor — accepted

Single-scene `pieces.glb` with nodes named by piece id (per-piece STL kept); `AxisCuts` model
instead of `dict[Axis, ...]`; `Warning` → `SliceWarning`; `PrinterPreset` defined; enum values
listed; `CutPlan.limits` carried and the preview count labelled "cells (upper bound)"; `depth` hook
dropped (single source: spec); "package" stage removed from the diagram; `MaleSideRule` is a
function in `slicing.py`; `ViewerProps` is the only input to `viewer/` and the store is split into
data/view slices; polling lives in `useSliceJob` only.

## Rejected

| finding | why |
|---|---|
| Cells should be convex polytopes now, for non-axis cuts | Non-axis cuts are a stated non-goal. The `PlaneFrame` on `CutInterface` is accepted because joints need it anyway; changing `Cell.bounds` to a polytope is a model change that will be made when the feature is built, and is confined to `models.py`, `planning.py`, `joint_cells`. |
| Frontend should render joint forms from JSON schema | A kind-specific form is legitimate UI work; a form registry keyed by `kind` gives the same open/closed property with far less machinery. |
| Store split "polling split" (granularity minor, part) | Already folded; not a separate finding. |
