# 02 — Build brief: stl-slicer v1

v1 (2026-09-28). For a session with no conversation history. Read `00_design.md` (v2) first; this
brief is DRY against it and only adds what a builder needs to type the code. Every `§N` here is a
literal anchor.

## §0 Rulings you must not re-litigate

| ruling | source | consequence in code |
|---|---|---|
| R1 React + r3f | 00 §10 | `web/` is Vite+React+TS; no Streamlit anywhere |
| R2 manifold3d kernel, trimesh IO only | 00 §1 | no `trimesh.boolean`, no `trimesh.intersections` for cutting; trimesh only in `io/` |
| R3/R11 cell-volume joints, union→subtract, clip to female cell, inset interior edges, runtime `check_pieces` | 00 §3, 01 B1/B2 | `core/slicing.py` owns rules 1–3; `SliceInvariantError` on overlap |
| R4 scale at upload; one coordinate frame | 00 §6 | `SliceSpec` has no `scale`; `MeshAsset.scale` records it |
| R5 single-worker job runner, cancel/supersede | 00 §6 | `ThreadJobRunner`, `CancelToken`, `DELETE /api/jobs/{id}` |
| R6 GLB view / STL print frames | 00 §6 | `pieces.glb` model frame; `.stl` translated by `PieceInfo.print_offset` |
| R7 planner concrete; joints registry | 00 §4.1/4.2 | `plan_grid` function; `joints/registry.py` maps `kind` literal → generator class |
| R9 kinds none/dowel/dovetail | 00 §4.2 | no jigsaw/keyed peg |
| R10 non-manifold = error | 00 §4.4 | `MeshLoadError` → HTTP 422 |
| Layering | 00 §8 | `uv run lint-imports` must pass |

## §1 Files you will touch (all NEW; the repo is empty apart from tooling)

Already present (READ, do not rewrite): `pyproject.toml` (deps, ruff, mypy strict, import-linter
contracts), `.gitignore`, `web/package.json` (+ installed deps), `docs/*`.
Written by the lead before builders start: `src/stl_slicer/core/models.py`, `src/stl_slicer/core/errors.py`,
all `__init__.py`.

Baseline commands (expected before any edit): `uv run python -c "import stl_slicer.core.models"` → no
output; `uv run pytest` → "no tests ran"; `cd web && npm run build` → succeeds with the Vite template.

## §2 Exact specifications

### §2.1 `core/geometry.py`

```python
class Mesh:
    """Immutable wrapper over manifold3d.Manifold. All lengths in mm, model frame."""
    def __init__(self, manifold: manifold3d.Manifold) -> None
    @classmethod
    def from_arrays(cls, vertices: NDArray[np.float64], faces: NDArray[np.int64]) -> Mesh   # raises MeshLoadError if status != NoError
    @classmethod
    def box(cls, size: Vec3, center: Vec3 = (0,0,0)) -> Mesh
    @classmethod
    def sphere(cls, radius: float, segments: int = 64) -> Mesh
    def to_arrays(self) -> tuple[NDArray[np.float64], NDArray[np.int64]]
    @property
    def manifold(self) -> manifold3d.Manifold
    @property
    def volume(self) -> float
    @property
    def bounds(self) -> Bounds
    @property
    def triangle_count(self) -> int
    @property
    def is_empty(self) -> bool
    def translate(self, offset: Vec3) -> Mesh
    def scale(self, factor: float) -> Mesh
    def components(self) -> list[Mesh]                 # decompose(); zero-volume components dropped
    def cross_section(self, frame: PlaneFrame, offset: float = 0.0) -> Region2D
        # rotate world so frame.normal→+z, frame.u→+x, frame.v→+y, frame.origin→0; slice at z=offset
    def __and__(self, o: Mesh) -> Mesh; def __or__(self, o: Mesh) -> Mesh; def __sub__(self, o: Mesh) -> Mesh

class Region2D:
    """Wrapper over manifold3d.CrossSection in an interface's (u, v) frame."""
    def __init__(self, cs: manifold3d.CrossSection) -> None
    @classmethod
    def rect(cls, u_min, v_min, u_max, v_max) -> Region2D
    @classmethod
    def circle(cls, radius: float, segments: int = 32) -> Region2D
    @classmethod
    def polygon(cls, points: Sequence[tuple[float,float]]) -> Region2D
    @property
    def cs(self) -> manifold3d.CrossSection
    @property
    def area(self) -> float
    @property
    def is_empty(self) -> bool
    @property
    def bounds(self) -> tuple[float,float,float,float]      # u_min, v_min, u_max, v_max
    def inset(self, d: float) -> Region2D                    # offset(-d, Round); d<=0 → self
    def inset_edges(self, d: float, edges: Iterable[str], rect: tuple[float,float,float,float]) -> Region2D
        # intersect with the rect shrunk by d on the named edges only ("u_min","u_max","v_min","v_max")
    def offset(self, d: float) -> Region2D
    def translate(self, u: float, v: float) -> Region2D
    def contains(self, other: Region2D, tol: float = 1e-9) -> bool   # (other − self).area <= tol
    def components(self) -> list[Region2D]
    def deepest_point(self, step: float | None = None) -> tuple[float,float] | None   # O3 in 00 §10
    def __and__/__or__/__sub__

class LocalFrame:
    """Transforms between an interface's local frame (x=u, y=v, z=normal, origin on plane) and world."""
    def __init__(self, frame: PlaneFrame) -> None
    @property
    def matrix(self) -> NDArray[np.float64]              # 4x4 local→world (rotation+translation)
    def to_world(self, m: manifold3d.Manifold) -> manifold3d.Manifold
    def extrude(self, region: Region2D, z0: float, z1: float) -> manifold3d.Manifold   # local; z0<z1

@dataclass(frozen=True)
class Joint:
    interface_id: str; kind: str; male_cell: CellIndex; female_cell: CellIndex; placement: Placement
    male: manifold3d.Manifold; female: manifold3d.Manifold      # WORLD frame, both on female side
    clearance_volume: float                                     # female.volume − male.volume

@dataclass(frozen=True)
class Piece:      info: PieceInfo; mesh: Mesh
@dataclass(frozen=True)
class LoadedModel: asset: MeshAsset; mesh: Mesh
@dataclass(frozen=True)
class SliceOutput: result: SliceResult; pieces: list[Piece]
```

### §2.2 `core/planning.py`

```python
def even_cuts(lo: float, hi: float, max_cell: float) -> list[float]      # n=ceil((hi-lo)/max_cell); n-1 interior cuts; [] if n<=1; raises PlanError if max_cell<=0
def plan_grid(bounds: Bounds, limits: CellLimits, cuts: AxisCuts | None = None) -> CutPlan
def make_frame(axis: Axis, position: float, rect_center: Vec3) -> PlaneFrame
    # normal = +axis; (u, v) = cyclic next two axes: X→(Y,Z), Y→(Z,X), Z→(X,Y)
```
Contract items 00 §4.1.1–6 are tests. Interface id: `f"{axis}{cut_index}_{lower.id}"`.

### §2.3 `core/joints/`

`base.py`:
```python
class JointGenerator(ABC, Generic[SpecT]):
    kind: ClassVar[str]
    spec_type: ClassVar[type[BaseModel]]
    def call(self, interface: CutInterface, region: Region2D, spec: SpecT, male: CellIndex, female: CellIndex) -> list[Joint]
        # 00 §4.2.1–4 enforced here; region is ALREADY inset per rule 3 by slicing.contact_regions
    @abstractmethod def solid(self, local: LocalFrame, placement: Placement, spec: SpecT, extent_u: float, extent_v: float) -> tuple[Manifold, Manifold]
    def placements(self, region: Region2D, spec: SpecT, extent_u: float, extent_v: float) -> list[Placement]   # default: grid_placements(region, self.footprint(spec), spec.spacing)
    def footprint(self, spec: SpecT) -> Region2D          # default: raise NotImplementedError (grid default needs it)

class ProfileExtrusionJoint(JointGenerator[SpecT]):
    @abstractmethod def profile(self, spec: SpecT) -> Region2D          # centred at (0,0)
    def footprint(self, spec) -> Region2D: return self.profile(spec)
    def solid(...): male = local.extrude(profile.translate(u,v), 0, depth); female = local.extrude(profile.offset(clearance).translate(u,v), -clearance, depth+clearance)
```
`placers.py`: `grid_placements(region, footprint, spacing) -> list[Placement]` (grid from region bounds
with `spacing`, aligned so the pattern is centred; keep if `region.contains(footprint.translate(u,v))`;
fallback `region.deepest_point()` if it passes containment, else `[]`) and
`strip_placements(region, half_width, spacing) -> list[Placement]` (positions along u whose
`[u−hw, u+hw]` lies within the u-projection of `region`; v = centre of region bounds; centred pattern;
fallback to the u-midpoint of the widest run).
`none.py` `NoJoint` (`kind="none"`, `call` returns `[]`). `dowel.py` `DowelJoint(ProfileExtrusionJoint)`
(`profile` = circle of diameter). `dovetail.py` `DovetailJoint`: `solid` builds the trapezoid in
local (x=u, z=n): half-widths `neck/2` at z=0 and `head/2` at z=depth, as a `CrossSection` in the
xz-plane extruded along y over `[-extent_v/2 - 1, extent_v/2 + 1]` (rotate accordingly); female =
trapezoid grown by `clearance` on all sides (neck/head half-widths + clearance, z from −clearance to
depth + clearance), same y-extent + 2·clearance. `placements` = `strip_placements(region, head/2, spacing)`.
`registry.py`: `REGISTRY: dict[str, type[JointGenerator]]`, `get_generator(kind) -> JointGenerator`,
`spec_depth(spec) -> float`, `spec_clearance(spec) -> float` (0 for none).

### §2.4 `core/slicing.py`

```python
def male_female(interface: CutInterface, rule: MaleSide) -> tuple[CellIndex, CellIndex]
def contact_regions(mesh: Mesh, plan: CutPlan, edge_inset: float, eps: float = 1e-3) -> dict[str, Region2D]
    # slice(−eps) ∩ slice(+eps) ∩ rect(extent) then inset_edges(edge_inset, interface.interior_edges)
def joint_cells(plan: CutPlan, joints: Sequence[Joint]) -> tuple[dict[str, Manifold], list[SliceWarning]]
    # for each joint: clip male/female to female Cell.bounds (cube manifold); JOINT_CLIPPED if male volume shrank > 1e-9
    # cell' = (cube(cell) ∪ males_out) − females_in   (batch_boolean)
def carve(mesh: Mesh, cells: dict[str, Manifold], plan: CutPlan) -> list[Piece]
    # piece_id = f"p_{cell.id}"; skip empty; component_count from Mesh.components(); fits_bed/print_offset left for pipeline (fill False/(0,0,0) here)
def check_pieces(pieces: Sequence[Piece], plan: CutPlan, input_volume: float, clearance_volume: float, duration_s: float) -> SliceStats
    # neighbours: cells whose indices differ by ≤1 on every axis; raise SliceInvariantError if any overlap > 1e-6*input_volume
```

### §2.5 `core/pipeline.py`

```python
class ProgressSink(Protocol):  def __call__(self, fraction: float, step: str) -> None
class CancelToken:             def cancel(self) -> None; @property is_cancelled -> bool; def raise_if_cancelled(self) -> None
def cell_limits(spec: SliceSpec) -> CellLimits          # 00 §3 formula; min_cell = depth + clearance + 1
def slice_model(model: LoadedModel, spec: SliceSpec, progress: ProgressSink | None = None, cancel: CancelToken | None = None, job_id: str = "") -> SliceOutput
```
Warnings emitted here: `PIECE_OVERSIZE`, `DISCONNECTED_PIECE`, `NO_CONTACT_FOR_JOINT`,
`ASSEMBLY_CONFLICT` (dovetail slide axes differ within a piece), plus pass-through from plan/joint_cells.
`print_offset = (−cx, −cy, −min_z)` of the piece bounds.

### §2.6 `io/`

`loaders.py`: `load_mesh(data: bytes, filename: str, scale: float = 1.0) -> LoadedModel` (trimesh
`load(file_obj=BytesIO, file_type=ext)`; merge vertices; `VERTICES_MERGED` warning if count changed;
`Mesh.from_arrays` raises `MeshLoadError` for non-manifold; `model_id = uuid4().hex[:12]`).
`exporters.py`: `mesh_to_stl(mesh) -> bytes`, `mesh_to_glb(mesh) -> bytes`,
`pieces_to_glb(pieces: Sequence[Piece]) -> bytes` (trimesh `Scene`, `geometry` keyed by `piece_id`,
node name = piece_id), `pieces_to_zip(pieces, result: SliceResult) -> bytes` (`{piece_id}.stl` in print
frame + `manifest.json`).

### §2.7 `service/`

`stores.py`: `ModelStore` Protocol + `InMemoryModelStore(capacity=4)` (OrderedDict LRU);
`ArtifactStore` Protocol + `InMemoryArtifactStore(jobs_per_model=2)` storing `SliceOutput` by job id.
`jobs.py`: `JobRunner` Protocol; `ThreadJobRunner(models, artifacts, executor=ThreadPoolExecutor(1))`
with `submit(model_id, spec) -> Job` (cancels any QUEUED/RUNNING job of the same model), `get(job_id)`,
`cancel(job_id)`, `shutdown()`. Progress updates mutate a per-job `Job` under a lock; `Cancelled` →
`CANCELLED`, other exceptions → `FAILED` with `error=str(e)`.
`presets.py`: `PRESETS: list[PrinterPreset]` (Bambu A1 mini 180³, Bambu P1S/X1C 256³, Prusa MK4
250×210×220, Ender 3 220×220×250, Voron 2.4 300³).

### §2.8 `api/`

`app.py`: `create_app(models=None, artifacts=None, runner=None, serve_web: bool = True) -> FastAPI` with
`separate_input_output_schemas=False`; exception handlers: `MeshLoadError`→422, `PlanError`→422,
`KeyError`/not found→404. `deps.py`: app.state accessors. Routes per 00 §6. Multipart field names:
`file`, `scale`. `web/dist` mounted at `/` only if it exists.
`cli.py` (typer): `serve --host 127.0.0.1 --port 8000 --dev` (dev = no static mount + reload),
`slice FILE --bed 220x220x250 --joint none|dowel|dovetail --scale 1.0 -o out/` (writes STLs + manifest),
`openapi` (prints JSON).

### §2.9 `web/`

`vite.config.ts`: proxy `/api` → `http://127.0.0.1:8000`; vitest `environment: jsdom`. Scripts:
`gen` = `openapi-typescript ../openapi.json -o src/api/schema.d.ts`, `typecheck` = `tsc -b`, `test` =
`vitest run`. Components per 00 §7; `ViewerProps { modelUrl?: string; piecesUrl?: string; plan?: CutPlan;
bed: PrintVolume; explode: number; showPlanes: boolean; hidden: Set<string>; selected?: string;
onSelect(id) }`. `lib/explode.ts`: `explodeOffset(cell: CellIndex, plan: CutPlan, factor: number): Vec3`
= (cell centre − plan centre) × factor. Poll interval 400 ms. Styling: plain CSS modules, dark theme,
sidebar 360 px + viewer; no UI framework.

## §3 Build order and gates

| step | owner | files | gate | expected |
|---|---|---|---|---|
| 0 | lead | `core/models.py`, `core/errors.py`, `__init__.py`s, `tests/conftest.py` | `uv run pytest tests/test_models.py` | pass |
| 1 | Lead A | `core/geometry.py`, `core/planning.py`, tests | `uv run pytest tests/core -q` | pass, ≥ 25 tests |
| 2 | Lead A | `core/joints/*`, `core/slicing.py`, `core/pipeline.py`, `tests/conformance/*`, tests | `uv run pytest -q` | pass; B1/B2/M18 regressions present |
| 3 | Lead B (parallel with 2) | `io/*`, `service/*`, `api/*`, `cli.py`, tests | `uv run pytest tests/api tests/service tests/io -q` | pass |
| 4 | Lead C (parallel with 1–3) | `web/src/**`, `vite.config.ts`, tests | `npm run typecheck && npm test && npm run build` | pass |
| 5 | lead | `openapi.json`, `web/src/api/schema.d.ts` | `uv run stl-slicer openapi > openapi.json && cd web && npm run gen && git diff --exit-code` | clean |
| 6 | lead | — | `uv run ruff check . && uv run mypy && uv run lint-imports && uv run pytest -q` | all pass |
| 7 | lead | — | end-to-end: `uv run stl-slicer slice tests/fixtures/sphere.stl --bed 100x100x100 --joint dovetail -o out/` | N STLs + manifest; browser smoke of the UI |
| 8 | lead | — | `/code-review` report-only; triage | findings triaged |

## §4 Guardrails

- $0 everywhere; no network calls at runtime except localhost.
- Never hand-edit `web/src/api/schema.d.ts` or `openapi.json` (generated).
- `api/` and `service/` must not import `manifold3d`/`trimesh` (import-linter).
- Formatting: `uv run ruff format <files>` scoped to touched files; `npx prettier` is not installed — keep TS tidy by hand.
- Tests use synthetic meshes only (`Mesh.box`, `Mesh.sphere`); one committed fixture `tests/fixtures/sphere.stl` (< 200 KB) generated by a test helper.
- Every builder returns: files written, `pytest`/`vitest` output (untruncated), open questions. Builders never edit files outside their step.

## §5 Build-time judgement calls

| item | decision |
|---|---|
| Manifold precision | keep float32 vert_properties (manifold3d default); volumes compared with rel tol 1e-6 |
| `Region2D.deepest_point` step | start `min(bounds extent)/8`, halve until 0.05 mm |
| Dovetail default sizes | neck 8, head 12, depth 6, clearance 0.15, spacing 60 |
| Grid placer alignment | centre the grid on region bounds centre |
| Vite proxy target | 127.0.0.1:8000 |
| Colours | pieces coloured by index from a 12-hue palette; selected = white outline; hidden = not rendered |

## §6 Done looks like

1. `uv run pytest -q` ≥ 120 tests pass; `ruff`, `mypy --strict`, `lint-imports` clean.
2. `cd web && npm run typecheck && npm test && npm run build` pass; schema drift gate clean.
3. `uv run stl-slicer slice sphere.stl --bed 100x100x100 --joint dovetail` produces disjoint pieces whose STL manifest validates as `SliceResult`, with `max_overlap_volume == 0`.
4. `uv run stl-slicer serve` then uploading an STL in the browser shows the model, live cut planes as the bed size changes, and after slicing an exploded, selectable set of pieces with a download zip.
5. README written; `docs/` updated with a v3 note if anything in 00 changed during the build.
