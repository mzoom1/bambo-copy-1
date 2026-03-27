# Stable Manifold Penetration Geometry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace fragile surface-conformal overlays with a stable manifold-penetration geometry contract so buildings and roads boolean reliably, export cleanly, and stay AMS-safe in Bambu Studio.

**Architecture:** Keep the terrain pipeline centered and bilinear-sampled, but switch overlay generation to robust volumetric plugs: buildings become shallow solids with 3.0 m real-world penetration scaled into model space, and roads become thicker draped strips with 2.0 mm total thickness and 1.0 mm max segment subdivision before snapping. Preserve the existing piece slicing and 3MF multipart export, then enforce manifold checks before compression so each piece still exports as separate selectable parts.

**Tech Stack:** Python 3.12, trimesh, numpy, scipy, shapely, FastAPI, React/TypeScript, 3MF XML assembly.

---

### Task 1: Reintroduce stable overlay constants and remove fragile-conformal leftovers

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py`
- Test: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_buildings.py`
- Test: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_roads.py`

**Step 1: Write the failing test**

Add assertions that the active constants and geometry contract match the stable manifold design:
- terrain sampler remains bilinear and vertical exaggeration-aware
- buildings use 3.0 m penetration in model space
- roads use 2.0 mm thickness and 1.0 mm max segment length before snapping

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_osm_buildings tests.test_osm_roads -v`

Expected: FAIL on outdated overlap/conformal behavior.

**Step 3: Write minimal implementation**

- Remove legacy conformal/overlap constants that conflict with the new stability contract.
- Introduce or retain explicit constants for the stable manifold path.
- Keep comments explaining why the values were chosen for TerraPrinter-style robustness.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_osm_buildings tests.test_osm_roads -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add /Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py /Users/eugenetoporkov/Desktop/bambo/tests/test_osm_buildings.py /Users/eugenetoporkov/Desktop/bambo/tests/test_osm_roads.py
git commit -m "refactor: stabilize roads and buildings manifold contract"
```

### Task 2: Implement stable building plugs with 3.0 m penetration

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py:building helpers`
- Test: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_buildings.py`

**Step 1: Write the failing test**

Add a test that validates building meshes:
- sample terrain with bilinear interpolation
- compute average terrain height for the footprint
- create a closed manifold plug
- base sits at `average_terrain_z - scaled_3m_penetration`
- roof sits at `average_terrain_z + building_height_scaled`
- resulting mesh remains watertight/manifold

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_osm_buildings -v`

Expected: FAIL until the building builder matches the stable plug contract.

**Step 3: Write minimal implementation**

- Keep bilinear terrain sampling.
- Replace the fragile shallow/conformal bottom with the stable 3.0 m penetration plug.
- Ensure the mesh stays a closed 6-sided solid per building.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_osm_buildings -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add /Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py /Users/eugenetoporkov/Desktop/bambo/tests/test_osm_buildings.py
git commit -m "feat: make building overlays stable manifold plugs"
```

### Task 3: Implement stable road drape with 2.0 mm thickness and 1.0 mm subdivision

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py:road helpers`
- Test: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_roads.py`

**Step 1: Write the failing test**

Add a test that validates roads:
- centerlines are subdivided so no segment exceeds 1.0 mm in model space
- terrain snapping occurs after subdivision
- final road mesh thickness is 2.0 mm
- road is submerged by 1.0 mm into terrain and still stays watertight

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_osm_roads -v`

Expected: FAIL until the road pipeline is updated.

**Step 3: Write minimal implementation**

- Retain 2D union on road footprints.
- Densify line strings before snapping.
- Build a thick draped strip instead of a fragile surface-conformal shell.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_osm_roads -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add /Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py /Users/eugenetoporkov/Desktop/bambo/tests/test_osm_roads.py
git commit -m "feat: stabilize road drape geometry"
```

### Task 4: Enforce manifold export and final base trim at Z=0

**Files:**
- Modify: `/Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py`
- Test: `/Users/eugenetoporkov/Desktop/bambo/tests/test_topomap_geometry.py`
- Test: `/Users/eugenetoporkov/Desktop/bambo/tests/test_osm_merge.py`

**Step 1: Write the failing test**

Add checks that:
- `slice_piece_and_trim_base(...)` still caps and trims exactly at Z=0
- exported puzzle pieces are manifold/watertight before compression
- multipart 3MF keeps separate terrain/buildings/roads parts per piece

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_topomap_geometry tests.test_osm_merge -v`

Expected: FAIL if any part is non-manifold or base trim regresses.

**Step 3: Write minimal implementation**

- Preserve current trimming and capping logic.
- Add explicit manifold/watertight validation before export.
- Raise a clear generation error when validation fails.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_topomap_geometry tests.test_osm_merge -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add /Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py /Users/eugenetoporkov/Desktop/bambo/tests/test_topomap_geometry.py /Users/eugenetoporkov/Desktop/bambo/tests/test_osm_merge.py
git commit -m "feat: validate manifold export and base trim"
```

### Task 5: Final verification and service restart

**Files:**
- No code changes unless verification finds a regression.

**Step 1: Run the full suite**

Run: `./.venv312/bin/python -m unittest discover -s tests -p 'test_*.py' -v`

Expected: all tests pass.

**Step 2: Run backend compile check**

Run: `./.venv312/bin/python -m py_compile /Users/eugenetoporkov/Desktop/bambo/topomap_to_puzzle_3mf.py /Users/eugenetoporkov/Desktop/bambo/server.py`

Expected: no output.

**Step 3: Restart backend and verify health**

Run: `kill <old_backend_pid>` then start `uvicorn server:app --host 127.0.0.1 --port 8000` in the live session.

Expected: `GET http://127.0.0.1:8000/health` returns `{"status":"ok"}`.

**Step 4: Sanity-check the frontend**

Run: `curl -I -s http://127.0.0.1:4173 | head -n 1`

Expected: `HTTP/1.1 200 OK`
