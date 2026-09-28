# 03 — Four more joint kinds

v1 (2026-09-28). Extends `00_design.md` §4.2 / §4.6. Rulings here are final unless new evidence.

## What exists

| kind | base | extrudes along | interlocks | purpose |
|---|---|---|---|---|
| dowel | ProfileExtrusionJoint | normal | no | registration pin |
| dovetail | ProfileStripJoint | thin in-plane axis | yes (slide) | sliding interlock |
| jigsaw | ProfileStripJoint | thin in-plane axis | yes (slide) | puzzle knob |

## New kinds

| kind | base | spec fields (mm) | auto rule (`e` piece edge, `t` thickness, `ks`/`kd` scales) | purpose |
|---|---|---|---|---|
| **tab** | ProfileStripJoint, rectangle profile `[-w/2, w/2] × [0, depth]`; `interlocks = False` | width 10, depth 6, clearance 0.15, edge_margin 3, spacing 60 | width = clamp(0.10·e, 5, 30)·ks; depth = clamp(0.5·width, 3, 15)·kd; spacing = clamp(0.5·e, 25, 150); margin = min(clamp(0.5·width + 2, 3, 15), 0.25·t) | the plain rectangular registration tab (as in slicer "connector" tools); presses together along the normal |
| **hexpin** | ProfileExtrusionJoint, regular hexagon profile (across-flats = width) | width 8, depth 6, clearance 0.15, edge_margin 3, spacing 40 | as dowel with width in place of diameter | keyed peg: registration plus anti-rotation |
| **tongue** | ProfileStripJoint subclass with the slide rule INVERTED (`_slides_along_u = extent_u > extent_v`): the profile is drawn across the THIN axis and the rib runs along the LONG axis; one rib per interface, centred across the thin axis; `interlocks = False`; rib length = the placement region's extent along the rib (so it stops `depth + clearance` short of interior cut planes: the B1 corner rule for ribs) | width 5, depth 4, clearance 0.15, edge_margin 2 | width = clamp(t/3, 2, 12)·ks; depth = clamp(0.8·width, 3, 15)·kd; margin = min(clamp(0.5·width + 1, 2, 8), 0.25·t); spacing unused (single rib) | tongue and groove along the whole seam; strongest glue joint for panels; presses together along the normal |
| **magnet** | new `PocketJoint` behaviour: no male tab; a cylindrical pocket on BOTH faces (`has_male = False`, `Joint.male_pocket`) | diameter 6, height 3, clearance 0.1, edge_margin 3, spacing 50 | diameter = 6 if t < 12 else 8 if t < 25 else 10 (·ks, then snapped back to {4, 6, 8, 10, 12}); height = 3 if diameter ≥ 6 else 2 (·kd, rounded to 0.5); spacing = clamp(0.4·e, 20, 100); margin = min(clamp(0.5·diameter + 2, 3, 10), 0.25·t) | pockets for off-the-shelf disc magnets (6×3 etc.); pieces snap together and come apart |

`depth` (the protrusion the planner reserves) is 0 for magnet: the spec exposes `depth` as a property
returning 0 and `pocket_depth = height + clearance` for the pockets.

## Base-class changes (additive)

1. `JointGenerator.solid(..., region: Region2D)` gains the placement region (already inset by the
   caller) as a trailing parameter; existing generators ignore it. `tongue` reads its rib length
   from `region.bounds`.
2. `JointGenerator.has_male: ClassVar[bool] = True`. When False, `_verify` skips the male checks
   (male may be empty), and `call` fills `Joint.male_pocket` from a new hook
   `pocket(local, placement, spec, region) -> (female_pocket, male_pocket)` used instead of `solid`.
3. `Joint.male_pocket: Manifold | None = None` (world frame, on the MALE side of the plane).
   `slicing.joint_cells` clips it to the male cell and subtracts it there (union-then-subtract
   order unchanged). `Joint.clearance_volume` for pocket joints = female pocket volume + male
   pocket volume, so `check_pieces`'s lower volume bound stays valid.
4. `ProfileStripJoint.interlocks: ClassVar[bool] = True`; `tab` and `tongue` set False and
   `pipeline._assembly_conflicts` only considers generators with `interlocks` True.

## Frontend

Kind labels: "Rectangular tabs", "Hex pegs", "Tongue and groove", "Magnet pockets". Each gets a
fields component in the `JointForm` registry, an entry in `DEFAULT_JOINTS` (auto on, scales 1),
and a case in `formatJointSummary`. The joint summary for magnet reads
"magnet · Ø6 × 3 mm · spacing 50 mm".

## Tests

Conformance suite picks every kind up from the registry (pocket kinds get the pocket variant of
the base checks: female pocket on the female side, male pocket on the male side, both within
`pocket_depth` of the plane). Per kind: geometry test (tab rectangle widths; hexpin across-flats;
tongue rib spans the region and stops short of interior planes on a 2×2 slab with no overlap;
magnet pockets present on both pieces of a 2-piece slab with the right volumes) and an auto rule
test. Pipeline: 2×2 slab per kind → max_overlap 0, all fit, no warnings.
