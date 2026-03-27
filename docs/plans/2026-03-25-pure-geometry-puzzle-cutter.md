# Pure Geometry Puzzle Cutter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore the puzzle stage as a pure geometry post-processor that cuts one merged watertight map mesh into deterministic jigsaw tiles without rebuilding terrain, buildings, or roads.

**Architecture:** Add a dedicated `PuzzleConfig` and a new cutter pipeline that works only from mesh bounds plus boolean intersections against extruded 2D puzzle masks. Keep map generation unchanged, and adapt the existing map-generation entrypoint to merge the final scene into one mesh before invoking the cutter.

**Tech Stack:** Python, `trimesh`, `manifold3d`, `shapely`, `unittest`

---

### Task 1: Add regression tests for pure mesh cutting

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_puzzle_slicing_from_full_map.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_merge.py`
- Create: `/Users/eugenetoporkov/Desktop/bambo/tests/test_puzzle_cutter.py`

**Step 1: Write the failing tests**

- Add tests for:
  - returning `tiles_x * tiles_y` merged tile meshes
  - deterministic tile names `tile_x{n}_y{m}`
  - union of tiles reconstructs source map volume within tolerance
  - no meaningful overlap between neighboring tiles
  - tile XY bounds stay within their cell bounds plus tab allowance
  - interior Z values are preserved by the cutter

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_puzzle_cutter.py -q`

Expected: FAIL because the new cutter API and behavior do not exist yet.

### Task 2: Implement a dedicated puzzle cutter

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py`
- Test: `/Users/eugenetoporkov/Desktop/bambo/tests/test_puzzle_cutter.py`

**Step 1: Add the new configuration and polygon generation**

- Introduce `PuzzleConfig`
- Add deterministic tab-boundary generation from mesh bounds
- Add flat XY puzzle outline generation independent from DEM/OSM metadata

**Step 2: Implement boolean slicing**

- Add `cut_map_into_puzzle_pieces(map_mesh, config)`
- Extrude each tile mask across mesh Z with padding
- Intersect source mesh with each cutter using `trimesh.boolean`
- Clean and validate each tile mesh

**Step 3: Add tile arrangement/export helpers**

- Add layout helper for arranging one mesh per tile on the virtual plate
- Add flat 3MF export helper for separate tile objects

**Step 4: Run tests**

Run: `python -m pytest tests/test_puzzle_cutter.py -q`

Expected: PASS

### Task 3: Rewire existing map-generation entrypoints

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_puzzle_slicing_from_full_map.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_merge.py`

**Step 1: Replace rebuild-based slicing**

- Remove the current behavior that re-samples DEM / rebuilds buildings / rebuilds roads inside `slice_full_map_into_pieces`
- Make the pipeline operate on a merged mesh only

**Step 2: Keep high-level API working**

- Adapt `generate_puzzle_from_map(...)` so it:
  - builds the scene as before
  - merges scene geometry into a single watertight mesh
  - calls the new cutter
  - exports one object per tile

**Step 3: Run focused regression tests**

Run: `python -m pytest tests/test_puzzle_slicing_from_full_map.py tests/test_osm_merge.py -q`

Expected: PASS

### Task 4: Final verification

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_puzzle_cutter.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_puzzle_slicing_from_full_map.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_merge.py`

**Step 1: Run verification**

Run: `python -m pytest tests/test_puzzle_cutter.py tests/test_puzzle_slicing_from_full_map.py tests/test_osm_merge.py -q`

Expected: PASS

**Step 2: Run syntax check**

Run: `python -m py_compile topomap_to_puzzle_3mf.py`

Expected: PASS
