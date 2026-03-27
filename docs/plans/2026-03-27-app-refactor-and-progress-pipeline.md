# App Refactor and Progress Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split the monolithic frontend into small typed modules and keep the generation flow, URL sync, and map selection behavior unchanged.

**Architecture:** Move shared domain types and parsing helpers into `types.ts` and `utils/`. Put URL syncing, bbox helpers, and generation job orchestration into hooks so the UI becomes a thin composition layer. Keep `App.tsx` as state wiring plus layout only, while preserving the current backend contract and download flow.

**Tech Stack:** React 19, TypeScript, Vite, Leaflet, FastAPI backend API

---

### Task 1: Shared Types and Utilities

**Files:**
- Create: `TopoPuzzle 3D/src/types.ts`
- Create: `TopoPuzzle 3D/src/utils/geo.ts`
- Create: `TopoPuzzle 3D/src/utils/api.ts`

**Step 1: Write the module shapes**

Export the shared map/job/grid types and the pure parsing/math helpers used by the current `App.tsx`.

**Step 2: Move parsing and HTTP helpers**

Keep the implementations functionally identical to the current app logic so the UI and API contract do not change.

**Step 3: Verify with TypeScript**

Run: `cd "TopoPuzzle 3D" && npm run lint`

Expected: pass without import or type errors.

### Task 2: Hooks

**Files:**
- Create: `TopoPuzzle 3D/src/hooks/useUrlState.ts`
- Create: `TopoPuzzle 3D/src/hooks/useBBox.ts`
- Create: `TopoPuzzle 3D/src/hooks/useGenerationJob.ts`

**Step 1: Extract URL syncing**

Keep query-param parsing and history updates in a hook that mirrors the current page state.

**Step 2: Extract bbox state**

Encapsulate selection bounds, center, area, and Leaflet event normalization.

**Step 3: Extract generation job flow**

Move submit, poll, download, and error normalization into a dedicated hook.

**Step 4: Verify with TypeScript**

Run: `cd "TopoPuzzle 3D" && npm run lint`

Expected: pass.

### Task 3: Components

**Files:**
- Create: `TopoPuzzle 3D/src/components/Navbar.tsx`
- Create: `TopoPuzzle 3D/src/components/MapView.tsx`
- Create: `TopoPuzzle 3D/src/components/ControlPanel.tsx`
- Create: `TopoPuzzle 3D/src/components/GenerationProgress.tsx`

**Step 1: Extract the navbar and map**

Keep Leaflet draw/edit behavior identical while moving all JSX out of `App.tsx`.

**Step 2: Extract the control panel**

Preserve the same controls, defaults, labels, and disabled states.

**Step 3: Extract generation overlays**

Render the progress and error overlays from props supplied by the hook.

**Step 4: Verify with TypeScript**

Run: `cd "TopoPuzzle 3D" && npm run lint`

Expected: pass.

### Task 4: Thin App Shell

**Files:**
- Modify: `TopoPuzzle 3D/src/App.tsx`

**Step 1: Replace monolith with composition**

Wire the hooks and components together without changing behavior.

**Step 2: Verify build**

Run: `cd "TopoPuzzle 3D" && npm run build`

Expected: production build succeeds.

