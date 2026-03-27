# South-West Origin Geometry Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the centered/manifold-heavy map geometry pipeline with a south-west-origin DEM/OSM pipeline that builds terrain, buildings, roads, and 3MF components in one consistent model-space coordinate system.

**Architecture:** The rewrite keeps one model-space contract: `(0, 0)` is the south-west corner in millimeters, `+X` points east, and `+Y` points north. Terrain is built directly from a flipped DEM, overlays are clipped in 2D with Shapely and extruded as overlapping solids, and the 3MF exporter writes separate printable components without Python-side mesh unions.

**Tech Stack:** Python 3, NumPy, Shapely, trimesh, requests, zipfile, unittest, FastAPI.

---

### Task 1: Rewrite the tests around the new coordinate contract

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_model_space_helpers.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_topomap_geometry.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_full_map_pipeline.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_buildings.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_roads.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_puzzle_slicing_from_full_map.py`
- Modify: `/Users/eugenetoporkov/Desktop/bambo/tests/test_smooth_terrain.py`

**Step 1: Write the failing tests**

Write tests that assert:
- the projector maps the south-west bbox corner to `(0, 0)`
- terrain bounds start at non-negative XY and `z=0`
- DEM north/south orientation is corrected with `np.flipud`
- buildings extrude from `min_terrain_z - 3mm` to `min_terrain_z + height`
- roads densify to `1mm` segments and extrude from `terrain_z - 3mm` to `terrain_z + 0.8mm`
- full-map scenes and piece polygons stay in positive model space

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_model_space_helpers.py tests/test_topomap_geometry.py tests/test_full_map_pipeline.py tests/test_osm_buildings.py tests/test_osm_roads.py tests/test_puzzle_slicing_from_full_map.py tests/test_smooth_terrain.py -q`

Expected: FAIL because the current implementation still centers geometry and exposes legacy manifold behavior.

### Task 2: Replace `topomap_to_puzzle_3mf.py` with a clean pipeline

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py`

**Step 1: Write minimal implementation**

Implement:
- bbox/model-space helpers for south-west-origin projection
- DEM fetching/reading with immediate `np.flipud`
- terrain meshing from a scaled DEM with base thickness
- DEM bilinear sampler in model space
- 2D OSM cleanup, clipping, and polygon/line projection
- building and road overlap extrusion without unions
- rectangular puzzle grid generation and per-piece scene assembly
- simple multipart 3MF export with separate component objects

**Step 2: Run focused tests**

Run: `python3 -m pytest tests/test_model_space_helpers.py tests/test_topomap_geometry.py tests/test_full_map_pipeline.py tests/test_osm_buildings.py tests/test_osm_roads.py tests/test_puzzle_slicing_from_full_map.py tests/test_smooth_terrain.py -q`

Expected: PASS

### Task 3: Verify broader compatibility

**Files:**
- Modify if needed: `/Users/eugenetoporkov/Desktop/bambo/server.py`
- Modify if needed: `/Users/eugenetoporkov/Desktop/bambo/tests/test_quality_presets.py`
- Modify if needed: `/Users/eugenetoporkov/Desktop/bambo/tests/test_topomap_hard_fail.py`

**Step 1: Run broader regression checks**

Run: `python3 -m pytest tests/test_quality_presets.py tests/test_topomap_hard_fail.py tests/test_generation_jobs.py tests/test_frontend_terms.py -q`

Expected: PASS, or minimal follow-up fixes limited to public API compatibility.
