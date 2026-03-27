# Job-Based Generation API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the blocking `/generate` request with a job-based API so long-running 3MF generation runs in the background and the frontend can poll progress safely.

**Architecture:** Keep the existing geometry pipeline intact. Add a lightweight in-memory job registry in `server.py`, expose `POST /generate` as a job submit endpoint, add `GET /jobs/{job_id}` for status polling, and add `GET /jobs/{job_id}/download` for file delivery. The React frontend should submit a job, poll until the job is done or failed, then download the generated 3MF. This keeps the current single-process local workflow but removes the long-lived HTTP request.

**Tech Stack:** Python 3.12, FastAPI, Starlette `run_in_threadpool`, `asyncio`, `dataclasses`, `trimesh` pipeline, React/TypeScript, `fetch`, unittest.

---

### Task 1: Add a job registry and job model to the backend

**Files:**
- Modify: `server.py`
- Test: `tests/test_generation_jobs.py` (new)

**Step 1: Write the failing test**

Create a backend test that submits a simple payload and asserts that `POST /generate` returns `202 Accepted` with a `jobId`, not a file download. Add a second assertion that `GET /jobs/{jobId}` returns a queued/running status object.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_generation_jobs -v`
Expected: FAIL because `/generate` still returns `FileResponse`.

**Step 3: Write minimal implementation**

Add a small in-memory job store in `server.py` using a dataclass such as `GenerationJob`. The store should track `status`, `progress`, `output_path`, `error`, and timestamps. Add `POST /generate` job creation logic and `GET /jobs/{job_id}` status lookup.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_generation_jobs -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add server.py tests/test_generation_jobs.py
git commit -m "feat: add generation job registry"
```

### Task 2: Run generation in the background and expose download endpoint

**Files:**
- Modify: `server.py`
- Test: `tests/test_generation_jobs.py`

**Step 1: Write the failing test**

Add a backend test that marks a job as done, points it at a temp `.3mf` file, and asserts `GET /jobs/{job_id}/download` returns a `FileResponse` only when the job is complete. Add one failure-path assertion for `failed` or unknown jobs.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_generation_jobs -v`
Expected: FAIL because the download endpoint does not exist yet.

**Step 3: Write minimal implementation**

Refactor the current generation path into an internal async worker that calls the existing `generate_puzzle_from_map(...)` through `run_in_threadpool`. Update the job status as it moves from queued to running to done/failed. Add `GET /jobs/{job_id}/download` that returns the generated `.3mf` and attaches cleanup via `BackgroundTask`.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_generation_jobs -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add server.py tests/test_generation_jobs.py
git commit -m "feat: run 3mf generation as background jobs"
```

### Task 3: Add frontend polling and download flow

**Files:**
- Modify: `TopoPuzzle 3D/src/App.tsx`
- Test: `TopoPuzzle 3D/src/__tests__/generate-job-flow.test.ts` (new, if test harness exists)

**Step 1: Write the failing test**

Add a frontend test or minimal integration harness that stubs `POST /generate` to return a `jobId`, then stubs `GET /jobs/{jobId}` to progress from running to done, and asserts the UI eventually triggers a download from the download endpoint.

**Step 2: Run test to verify it fails**

Run: `npm test -- --runInBand generate-job-flow`
Expected: FAIL because the UI still waits for a direct blob response.

**Step 3: Write minimal implementation**

Change `simulateDownload()` so it submits the payload, receives a `jobId`, polls `/jobs/{jobId}` on a timer, and downloads the file from `/jobs/{jobId}/download` when ready. Preserve current error extraction and modal behavior for failed jobs.

**Step 4: Run test to verify it passes**

Run: `npm test -- --runInBand generate-job-flow`
Expected: PASS.

**Step 5: Commit**

```bash
git add 'TopoPuzzle 3D/src/App.tsx' 'TopoPuzzle 3D/src/__tests__/generate-job-flow.test.ts'
git commit -m "feat: poll generation jobs from the frontend"
```

### Task 4: Add cleanup and stale job retention rules

**Files:**
- Modify: `server.py`
- Test: `tests/test_generation_jobs.py`

**Step 1: Write the failing test**

Add a backend test that creates an old completed job and asserts the cleanup path removes temp output files and evicts stale job records according to a retention window.

**Step 2: Run test to verify it fails**

Run: `./.venv312/bin/python -m unittest tests.test_generation_jobs -v`
Expected: FAIL because the registry does not prune jobs yet.

**Step 3: Write minimal implementation**

Add a small pruning helper that removes finished jobs after a short retention period and deletes any associated temp files. Keep the cleanup conservative so in-flight jobs are never touched.

**Step 4: Run test to verify it passes**

Run: `./.venv312/bin/python -m unittest tests.test_generation_jobs -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add server.py tests/test_generation_jobs.py
git commit -m "feat: prune stale generation jobs"
```

### Task 5: End-to-end verification

**Files:**
- Modify: none
- Test: `tests/test_generation_jobs.py`, existing integration tests

**Step 1: Run the full Python test suite**

Run: `./.venv312/bin/python -m unittest discover -s tests -p 'test_*.py' -v`
Expected: PASS.

**Step 2: Compile backend**

Run: `./.venv312/bin/python -m py_compile server.py topomap_to_puzzle_3mf.py`
Expected: PASS.

**Step 3: Smoke-test the API**

Run: `curl -sS -X POST http://127.0.0.1:8000/generate -H 'Content-Type: application/json' -d '{"bbox":{"minLon":0,"minLat":0,"maxLon":0.01,"maxLat":0.01},"physicalSizeMm":200,"rows":5,"columns":5,"zScale":1,"smoothTerrain":true,"flattenSeaLevel":true}'`
Expected: `202` with `jobId`.

**Step 4: Poll job status**

Run: `curl -sS http://127.0.0.1:8000/jobs/<jobId>`
Expected: `queued|running|done|failed` with progress.

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: complete job-based generation api"
```
