# Stage 2 Tabs Labels And Draped Roads Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add tabbed puzzle outlines, grid labels, shared-heightfield overlay placement, and draped unioned road meshes to the south-west-origin terrain pipeline.

**Architecture:** Keep one authoritative terrain heightfield derived from the flipped DEM and the exact formula `Z = (elev - min_elev) * exaggeration * mm_per_meter + base_thickness`. Build tabbed piece polygons in 2D first, then reuse those exact polygons for terrain cropping, building clipping, road clipping, and label placement so geometry, sampler, and exported parts stay synchronized.

**Tech Stack:** Python 3, NumPy, Shapely, trimesh, unittest.

---

### Task 1: Add failing tests for the Stage 2 integration contract

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_topomap_geometry.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_roads.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_puzzle_slicing_from_full_map.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_merge.py`

**Step 1: Write the failing test**

Add tests that assert:
- piece polygons contain tab protrusions / sockets and are not plain rectangles,
- a 1x1 piece export includes a label mesh named `label`,
- piece labels use grid IDs like `A1`,
- buildings and roads use the same authoritative heightfield as the terrain formula,
- roads are emitted as one draped mesh per piece after 2D union instead of a chain of boxes.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_topomap_geometry tests.test_osm_roads tests.test_puzzle_slicing_from_full_map tests.test_osm_merge`
Expected: FAIL until tabs, labels, and draped roads are implemented.

### Task 2: Implement shared heightfield + tabbed piece polygons

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py`

**Step 1: Write minimal implementation**

Implement:
- a reusable authoritative heightfield object or helper set,
- tabbed 2D jigsaw polygon generation in model space,
- piece terrain generation clipped to those polygons,
- terrain-relative building bottoms using the same heightfield sampler.

**Step 2: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_topomap_geometry tests.test_puzzle_slicing_from_full_map`
Expected: PASS

### Task 3: Implement draped unioned roads and grid labels

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_roads.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_merge.py`

**Step 1: Write minimal implementation**

Implement:
- 2D unary-unioned road outlines with `buffer(0)` cleanup,
- triangulated draped top/bottom road surfaces with stitched side walls and consistent winding,
- grid label meshes (`A1`, `A2`, `B1`) anchored near negative-X / negative-Y piece edges,
- export metadata so label meshes survive as separate components.

**Step 2: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_osm_roads tests.test_puzzle_slicing_from_full_map tests.test_osm_merge`
Expected: PASS

### Task 4: Verify focused regression coverage

**Files:**
- Modify if needed: `/Users/eugenetoporkov/Desktop/bambo/tests/test_full_map_pipeline.py`
- Modify if needed: `/Users/eugenetoporkov/Desktop/bambo/tests/test_quality_presets.py`

**Step 1: Run verification**

Run: `.venv/bin/python -m unittest tests.test_model_space_helpers tests.test_topomap_geometry tests.test_full_map_pipeline tests.test_osm_buildings tests.test_osm_roads tests.test_puzzle_slicing_from_full_map tests.test_osm_merge tests.test_smooth_terrain tests.test_quality_presets tests.test_topomap_hard_fail`
Expected: PASS
