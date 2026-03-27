# Centered Model Space Terrain + Buildings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add centered model-space helpers for smooth terrain generation and OSM building extrusion with a strict coordinate contract suitable for FDM puzzle exports.

**Architecture:** Keep the geometry math explicit and centered around the bbox midpoint. Convert real-world coordinates into a local model space where `(0, 0)` is the bbox center, `+X` is east, `+Y` is north, and the final trimmed base plane is `Z = 0`. Terrain generation uses bilinear interpolation plus light Laplacian smoothing; building extrusion uses center-point ray-casting against the terrain mesh, flat roofs, vertical walls, and deep burial so the printed result is slicer-stable.

**Tech Stack:** Python 3.12, `numpy`, `scipy`, `shapely`, `trimesh`, `unittest`.

---

### Task 1: Add coordinate and scale helpers with tests

**Files:**
- Modify: `topomap_to_puzzle_3mf.py`
- Test: `tests/test_model_space_helpers.py` (new)

**Step 1: Write the failing test**

Add tests for:
- converting a bbox into a centered local origin transform
- computing `scale_factor_xy = physical_size_mm / real_world_size_m`
- mapping a real-world point into model space with `(0, 0)` at the bbox center

Example assertions:
```python
def test_centered_model_space_origin():
    bbox = (10.0, 20.0, 20.0, 30.0)
    transform = compute_model_space_transform(bbox, 200.0)
    assert transform.center_x == 0.0
    assert transform.center_y == 0.0
```

**Step 2: Run test to verify it fails**

Run:
```bash
./.venv312/bin/python -m unittest tests.test_model_space_helpers -v
```
Expected: FAIL because the helpers do not exist yet.

**Step 3: Write minimal implementation**

Add helpers in `topomap_to_puzzle_3mf.py`:
- `compute_scale_factor_xy(physical_size_mm: float, real_world_size_m: float) -> float`
- `center_bbox_to_model_space(bbox: tuple[float, float, float, float]) -> tuple[float, float]`
- `real_world_to_model_xy(x_m: float, y_m: float, bbox: tuple[float, float, float, float], scale_factor_xy: float) -> tuple[float, float]`

Keep the implementation explicit and document the contract:
- `(0, 0)` is the bbox center
- `+X` is east
- `+Y` is north
- model-space units are millimeters

**Step 4: Run test to verify it passes**

Run:
```bash
./.venv312/bin/python -m unittest tests.test_model_space_helpers -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add topomap_to_puzzle_3mf.py tests/test_model_space_helpers.py
git commit -m "feat: add centered model space helpers"
```

### Task 2: Implement smooth terrain generation

**Files:**
- Modify: `topomap_to_puzzle_3mf.py`
- Test: `tests/test_smooth_terrain.py` (new)

**Step 1: Write the failing test**

Add a test that builds a small synthetic DEM and asserts:
- the function returns a watertight `trimesh.Trimesh`
- the terrain is centered in model space
- bilinear interpolation is used instead of nearest-neighbor
- Laplacian smoothing reduces a sharp spike

Use a test DEM with one spike and compare the smoothed result against the unsmoothed one.

**Step 2: Run test to verify it fails**

Run:
```bash
./.venv312/bin/python -m unittest tests.test_smooth_terrain -v
```
Expected: FAIL because `generate_smooth_terrain(...)` does not exist yet.

**Step 3: Write minimal implementation**

Add:
- `generate_smooth_terrain(dem_matrix, scale_factor_xy, z_exaggeration)`

Implementation requirements:
- use `scipy.interpolate.RegularGridInterpolator` or equivalent bilinear interpolation
- optionally smooth the DEM with a small Laplacian kernel before meshing
- build a watertight terrain mesh with `trimesh`
- normalize geometry into the centered model-space contract
- preserve a flat trimmed base plane at `Z = 0` after any later trimming stage

**Step 4: Run test to verify it passes**

Run:
```bash
./.venv312/bin/python -m unittest tests.test_smooth_terrain -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add topomap_to_puzzle_3mf.py tests/test_smooth_terrain.py
git commit -m "feat: generate smooth terrain mesh"
```

### Task 3: Implement building extrusion with ray-cast anchoring

**Files:**
- Modify: `topomap_to_puzzle_3mf.py`
- Test: `tests/test_building_extrusion.py` (new)

**Step 1: Write the failing test**

Add a test that uses a synthetic terrain mesh plus a simple square building footprint and asserts:
- the roof is flat
- the base is deeply buried below the terrain
- the roof height equals `terrain_z_center + real_height * scale_factor_xy * z_exaggeration`
- the function returns a watertight `trimesh.Trimesh` per building

**Step 2: Run test to verify it fails**

Run:
```bash
./.venv312/bin/python -m unittest tests.test_building_extrusion -v
```
Expected: FAIL because `extrude_buildings(...)` does not exist yet.

**Step 3: Write minimal implementation**

Add:
- `extrude_buildings(building_polygons, terrain_mesh, scale_factor_xy, z_exaggeration)`

Implementation requirements:
- center each footprint in model space
- ray-cast straight down from the footprint center to find `Z_center`
- derive `model_z_height = real_height_m * scale_factor_xy * z_exaggeration`
- use a flat roof plane
- use vertical walls
- bury the bottom to a deep negative offset so the mesh becomes a closed manifold
- keep the output ready for downstream Boolean union / cut

**Step 4: Run test to verify it passes**

Run:
```bash
./.venv312/bin/python -m unittest tests.test_building_extrusion -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add topomap_to_puzzle_3mf.py tests/test_building_extrusion.py
git commit -m "feat: extrude buildings from centered terrain"
```

### Task 4: Regression check and backend compile

**Files:**
- Modify: none

**Step 1: Run the full Python geometry tests**

Run:
```bash
./.venv312/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```
Expected: PASS.

**Step 2: Compile the backend**

Run:
```bash
./.venv312/bin/python -m py_compile topomap_to_puzzle_3mf.py server.py
```
Expected: PASS.

**Step 3: Smoke-test the health endpoint**

Run:
```bash
curl -sS http://127.0.0.1:8000/health
```
Expected: `{"status":"ok"}`

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: centered model space geometry helpers"
```
