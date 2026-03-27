# TerraPrinter-Style Full-Map Puzzle Pipeline Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a TerraPrinter-like generation flow that first produces a clean full-map mesh with quality presets, then slices that mesh into puzzle pieces for export.

**Architecture:** Split the current pipeline into two explicit stages. Stage 1 builds a single full-map terrain model from DEM + OSM using low/very-low quality presets, deterministic centering, and separate preview/export behavior. Stage 2 reuses that already-built full-map geometry, slices it into puzzle pieces, applies the existing puzzle/tab/chamfer/export logic, and emits the final multipart 3MF.

**Tech Stack:** Python 3.12, trimesh, shapely, requests, FastAPI, FastAPI background file responses, unittest, Vite + React for the UI.

---

## Current Problem

The current implementation generates puzzle geometry per piece while also fetching and baking OSM overlays repeatedly inside the piece loop. That keeps the printable output correct, but it makes the visual style diverge from TerraPrinter and makes generation slower than needed. TerraPrinter’s logs and reference files show a simpler top-level scene: terrain, buildings, roads, and water are generated once, centered/scaled, and previewed as a single map before export.

## Target Result

The user should be able to:
1. Select a region.
2. Choose a quality preset, with `Very Low (Fastest)` as the default for puzzle generation.
3. Generate a TerraPrinter-like full-map mesh that is visually clean and fast to compute.
4. Slice that full-map mesh into puzzle pieces.
5. Export a print-ready 3MF with the existing puzzle layout and Bambu metadata.

## Proposed Flow

### Stage 1: Full-map generation
- Fetch DEM once for the selected bbox.
- Fetch OSM features once for the same bbox and cache by bbox + quality + toggles.
- Build terrain, buildings, roads, and optional water/text/trails into a single full-map scene.
- Normalize the model:
  - center on the map footprint,
  - scale to `physicalSizeMm`,
  - apply the chosen quality preset.
- Emit a preview mesh/GLB path for the viewer.

### Stage 2: Puzzle slicing and export
- Slice the already-built full-map geometry into puzzle pieces.
- Preserve the existing interlocking tab geometry, clearance, chamfer, and piece ID debossing.
- Keep manual multipart 3MF export and Bambu template support.
- Avoid re-fetching or re-baking OSM inside each piece unless it is strictly necessary for the final puzzle slice.

## UI Changes

- Add a visible quality selector with presets similar to TerraPrinter:
  - Very Low (Fastest)
  - Low
  - Average
  - High
  - Very High
- Default puzzle mode to `Very Low` so the workflow is fast by default.
- Keep the current bbox selection and generation flow.
- Keep buildings/roads toggles, but they should feed the stage-1 full-map builder rather than drive per-piece OSM work directly.

## Backend Changes

- Introduce a full-map build function that returns a normalized mesh or scene for the selected bbox and quality preset.
- Introduce a slicing function that takes the full-map geometry and produces puzzle pieces.
- Cache DEM and OSM fetches by bbox + preset.
- Keep the current 3MF export contract, but route it through the new stage-2 data.
- Preserve current error handling and 500 responses for generation failures.

## Risks and Constraints

- Stage 1 must stay lightweight enough for a fast preview path.
- Stage 2 must not lose the current puzzle-specific features.
- The full-map builder should not rely on expensive boolean work per piece.
- We should not reintroduce the old broken per-piece OSM baking path as the main flow.

## Success Criteria

- A full-map export visually matches TerraPrinter much more closely.
- The same bbox on repeated runs is faster because DEM/OSM work is cached.
- Puzzle export still produces valid multipart 3MF with the existing Bambu template behavior.
- The new quality presets visibly change processing cost and mesh density.
