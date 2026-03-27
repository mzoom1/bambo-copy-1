# TerraPrinter-Style Full-Map Puzzle Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the generator build a TerraPrinter-like full-map model first, then slice that model into puzzle pieces for export.

**Architecture:** Split the current path into stage 1 and stage 2. Stage 1 builds a single normalized map mesh/scene from DEM + OSM using a quality preset and cached fetches. Stage 2 consumes that full-map geometry, generates puzzle cuts, and exports the existing multipart 3MF without reintroducing the old per-piece OSM generation as the primary path.

**Tech Stack:** Python 3.12, trimesh, shapely, requests, FastAPI, FastAPI background responses, unittest, Vite + React.

---

### Task 1: Add quality presets and wire them through the API payload

**Files:**
- Modify: `TopoPuzzle 3D/src/App.tsx`
- Modify: `server.py`
- Modify: `topomap_to_puzzle_3mf.py`
- Test: `tests/test_quality_presets.py` (new)

**Step 1: Write the failing test**

Create a backend test that calls the map generation entry point with a preset-like parameter and asserts it maps to a smaller DEM resolution than the current default puzzle path. Add a lightweight frontend unit-style assertion if a test harness exists; otherwise focus on backend behavior and URL/payload parsing in `server.py`.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_quality_presets -v`
Expected: FAIL because there is no explicit quality preset plumbing yet.

**Step 3: Write minimal implementation**

Add a preset enum or mapping table in Python that turns `Very Low`, `Low`, `Average`, `High`, `Very High` into concrete DEM/OSM quality parameters. Expose the preset in the `/generate` payload and in the React UI as a visible selector. Default puzzle mode to `Very Low`.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_quality_presets -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add server.py topomap_to_puzzle_3mf.py 'TopoPuzzle 3D/src/App.tsx' tests/test_quality_presets.py
git commit -m "feat: add terrain quality presets"
```

### Task 2: Build a full-map stage-1 pipeline

**Files:**
- Modify: `topomap_to_puzzle_3mf.py`
- Test: `tests/test_full_map_pipeline.py` (new)

**Step 1: Write the failing test**

Add a test that exercises a new full-map builder function. The test should assert that the stage-1 output is a single normalized mesh/scene, centered and scaled to the requested physical size, and that it can be built without slicing into puzzle pieces.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_full_map_pipeline -v`
Expected: FAIL because the current generator only has the puzzle path.

**Step 3: Write minimal implementation**

Create a `build_full_map_model(...)` helper that:
- fetches DEM once,
- fetches OSM once,
- builds terrain/buildings/roads (and optional layers) into one scene or mesh,
- centers/scales it,
- returns the full-map geometry for preview and later slicing.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_full_map_pipeline -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add topomap_to_puzzle_3mf.py tests/test_full_map_pipeline.py
git commit -m "feat: add full map build stage"
```

### Task 3: Slice the full map into puzzle pieces

**Files:**
- Modify: `topomap_to_puzzle_3mf.py`
- Test: `tests/test_puzzle_slicing_from_full_map.py` (new)

**Step 1: Write the failing test**

Add a test that passes a simple full-map mesh into a new slicing helper and asserts the helper returns the expected number of puzzle piece groups with the current tab/clearance behavior.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_puzzle_slicing_from_full_map -v`
Expected: FAIL because the slicing helper does not exist yet.

**Step 3: Write minimal implementation**

Create a `slice_full_map_into_pieces(...)` helper that reuses the current puzzle polygon generation, cutter construction, base trim, chamfer, and piece-ID logic. Keep the current multipart 3MF export contract intact.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_puzzle_slicing_from_full_map -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add topomap_to_puzzle_3mf.py tests/test_puzzle_slicing_from_full_map.py
git commit -m "feat: slice full map into puzzle pieces"
```

### Task 4: Cache DEM/OSM fetches by bbox and preset

**Files:**
- Modify: `topomap_to_puzzle_3mf.py`
- Test: `tests/test_generation_cache.py` (new)

**Step 1: Write the failing test**

Add a test that calls the full-map builder twice with the same bbox/preset and asserts the second call uses cached fetch results instead of repeating the expensive network/data load path.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_generation_cache -v`
Expected: FAIL because there is no explicit cache layer yet.

**Step 3: Write minimal implementation**

Add a small cache key based on bbox + quality preset + toggles. Cache DEM and OSM fetch results separately so repeated generation of the same region is faster.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_generation_cache -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add topomap_to_puzzle_3mf.py tests/test_generation_cache.py
git commit -m "feat: cache map fetches by bbox and preset"
```

### Task 5: Update backend generation flow to use the new two-stage pipeline

**Files:**
- Modify: `server.py`
- Modify: `topomap_to_puzzle_3mf.py`
- Test: `tests/test_server_generate_flow.py` (new)

**Step 1: Write the failing test**

Add a backend test that submits the generate payload and asserts the backend calls the new stage-1 full-map builder before the slicing/export stage.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_server_generate_flow -v`
Expected: FAIL because the server still calls the legacy monolithic map-mode path.

**Step 3: Write minimal implementation**

Refactor `generate_puzzle_from_map(...)` into explicit stage-1 and stage-2 helpers. Keep the `/generate` endpoint signature stable, but route it through the new two-stage flow.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_server_generate_flow -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add server.py topomap_to_puzzle_3mf.py tests/test_server_generate_flow.py
git commit -m "feat: route generation through full map pipeline"
```

### Task 6: End-to-end regression and performance sanity check

**Files:**
- Modify: none
- Test: `tests/test_quality_presets.py`, `tests/test_full_map_pipeline.py`, `tests/test_puzzle_slicing_from_full_map.py`, `tests/test_generation_cache.py`, `tests/test_server_generate_flow.py`

**Step 1: Run the full Python test suite**

Run: `./.venv312/bin/python -m unittest discover -s tests -p 'test_*.py' -v`
Expected: PASS.

**Step 2: Compile the backend**

Run: `./.venv312/bin/python -m py_compile topomap_to_puzzle_3mf.py server.py`
Expected: PASS.

**Step 3: Smoke test the API**

Run: `curl -sS http://127.0.0.1:8000/health`
Expected: `{"status":"ok"}`.

**Step 4: Manual UI check**

Open the site and verify the quality selector defaults to `Very Low`, bbox selection still works, and generation returns a valid 3MF.

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: complete terraprinter style map pipeline"
```
