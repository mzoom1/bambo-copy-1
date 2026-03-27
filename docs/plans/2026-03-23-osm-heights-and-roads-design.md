# OSM Heights and Terrain-Following Roads Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make OSM buildings use real-world height tags and make roads follow the final puzzle-piece terrain surface as a dense ribbon.

**Architecture:** Keep the existing per-piece bake pipeline and manual multipart 3MF export. Update only the OSM geometry builders: buildings will derive per-feature heights from OSM tags and roads will be densified, sampled against the final piece surface, and extruded as a terrain-following ribbon. The final puzzle-piece export contract stays unchanged.

**Tech Stack:** Python 3.12, trimesh, shapely, requests, FastAPI, unittest.

---

### Task 1: Buildings use OSM heights

**Files:**
- Modify: `topomap_to_puzzle_3mf.py:671-820`
- Test: `tests/test_osm_buildings.py`

**Step 1: Write the failing test**

Add a test that feeds two building features with different tags into `build_buildings_mesh(...)` and asserts the resulting meshes have different heights when tags contain `height` vs `building:levels`, with the fallback default used only when both are missing.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_osm_buildings -v`
Expected: FAIL because the current builder still uses a fixed extrusion height.

**Step 3: Write minimal implementation**

Update `build_buildings_mesh(...)` so each item computes a real-world building height in meters from tags, converts it into model millimeters, and extrudes that item individually. Keep the existing downward penetration and clipping behavior.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_osm_buildings -v`
Expected: PASS.

**Step 5: Commit**

If this were a git checkout:
```bash
git add topomap_to_puzzle_3mf.py tests/test_osm_buildings.py
git commit -m "feat: use OSM heights for buildings"
```

### Task 2: Roads follow final piece terrain

**Files:**
- Modify: `topomap_to_puzzle_3mf.py:700-940, 2941-2998`
- Test: `tests/test_osm_roads.py`

**Step 1: Write the failing test**

Add a test that creates a simple sloped final piece mesh, passes its `surface_sampler` into `build_roads_mesh(...)`, and asserts the road mesh vertices vary in Z along the line and sit above the sampled terrain by the configured road offset.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_osm_roads -v`
Expected: FAIL because the current road builder still buffers and extrudes in flat 2D without terrain-following vertices.

**Step 3: Write minimal implementation**

Add road densification to ~1 mm segments, sample each densified vertex against the final piece surface, construct a 3D ribbon, and extrude it with deeper penetration while preserving the road offset above terrain.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_osm_roads -v`
Expected: PASS.

**Step 5: Commit**

If this were a git checkout:
```bash
git add topomap_to_puzzle_3mf.py tests/test_osm_roads.py
git commit -m "feat: terrain-follow OSM roads"
```

### Task 3: End-to-end verification

**Files:**
- Modify: none
- Test: `tests/test_osm_buildings.py`, `tests/test_osm_roads.py`, `tests/test_osm_merge.py`

**Step 1: Run the full test suite**

Run: `./.venv312/bin/python -m unittest discover -s tests -p 'test_*.py' -v`
Expected: PASS.

**Step 2: Run bytecode compilation**

Run: `./.venv312/bin/python -m py_compile topomap_to_puzzle_3mf.py server.py`
Expected: PASS.

**Step 3: Smoke test backend**

Run: `curl -sS http://127.0.0.1:8000/health`
Expected: `{"status":"ok"}`.
