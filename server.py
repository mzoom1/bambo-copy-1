from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from topomap_to_puzzle_3mf import (
    BASE_THICKNESS_MM,
    DEM_REQUEST_WIDTH,
    VERTICAL_EXAGGERATION,
    generate_puzzle_from_map,
    resolve_quality_preset,
)


app = FastAPI(title="TopoPuzzle Local Generator API")
logger = logging.getLogger("topopuzzle.api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:4174",
        "http://127.0.0.1:4174",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


JOB_RETENTION = timedelta(minutes=30)


@dataclass
class GenerationJob:
    job_id: str
    status: str
    progress: int
    created_at: str
    updated_at: str
    output_path: str | None = None
    error: str | None = None
    filename: str | None = None


_JOBS: dict[str, GenerationJob] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utcnow().isoformat()


def _cleanup_file(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def _cleanup_job_file(job_id: str, path: Path) -> None:
    _cleanup_file(path)
    job = _JOBS.get(job_id)
    if job is not None and job.output_path == str(path):
        job.output_path = None
        job.updated_at = _iso_now()


def _pick(d: dict, *keys: str):
    for key in keys:
        if key in d:
            return d[key]
    return None


def _parse_bool(v, default: bool) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_float(v, field_name: str) -> float:
    try:
        return float(v)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Field '{field_name}' must be a number.") from exc


def _parse_int(v, field_name: str) -> int:
    try:
        return int(v)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Field '{field_name}' must be an integer.") from exc


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _ensure_min_span(lo: float, hi: float, min_span: float, min_limit: float, max_limit: float) -> tuple[float, float]:
    span = hi - lo
    if span >= min_span:
        return lo, hi
    center = (lo + hi) * 0.5
    half = min_span * 0.5
    lo2 = center - half
    hi2 = center + half
    if lo2 < min_limit:
        hi2 += (min_limit - lo2)
        lo2 = min_limit
    if hi2 > max_limit:
        lo2 -= (hi2 - max_limit)
        hi2 = max_limit
    lo2 = _clamp(lo2, min_limit, max_limit)
    hi2 = _clamp(hi2, min_limit, max_limit)
    return lo2, hi2


def _serialize_job(job: GenerationJob) -> dict:
    return asdict(job)


def _prune_jobs() -> None:
    cutoff = _utcnow() - JOB_RETENTION
    stale_ids: list[str] = []
    for job_id, job in list(_JOBS.items()):
        try:
            updated = datetime.fromisoformat(job.updated_at)
        except Exception:
            updated = _utcnow()
        if job.status in {"done", "failed"} and updated < cutoff:
            if job.output_path:
                _cleanup_file(Path(job.output_path))
            stale_ids.append(job_id)
    for job_id in stale_ids:
        _JOBS.pop(job_id, None)


def _get_job_or_404(job_id: str) -> GenerationJob:
    _prune_jobs()
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def _parse_generation_request(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object.")

    bbox_payload = _pick(payload, "bbox")
    if bbox_payload is None:
        raise HTTPException(status_code=400, detail="Missing 'bbox' object.")
    if not isinstance(bbox_payload, dict):
        raise HTTPException(status_code=400, detail="'bbox' must be an object with south/west/north/east.")

    raw_west = _parse_float(_pick(bbox_payload, "minLon", "min_lon", "west"), "bbox.minLon")
    raw_south = _parse_float(_pick(bbox_payload, "minLat", "min_lat", "south"), "bbox.minLat")
    raw_east = _parse_float(_pick(bbox_payload, "maxLon", "max_lon", "east"), "bbox.maxLon")
    raw_north = _parse_float(_pick(bbox_payload, "maxLat", "max_lat", "north"), "bbox.maxLat")

    west = min(raw_west, raw_east)
    east = max(raw_west, raw_east)
    south = min(raw_south, raw_north)
    north = max(raw_south, raw_north)

    eps = 1e-6
    if south == north:
        south -= eps
        north += eps
    if west == east:
        west -= eps
        east += eps

    south, north = _ensure_min_span(south, north, min_span=0.002, min_limit=-89.999, max_limit=89.999)
    west, east = _ensure_min_span(west, east, min_span=0.002, min_limit=-179.999, max_limit=179.999)

    physical_size_mm = _parse_float(
        _pick(payload, "physicalSizeMm", "physical_size", "physicalSize", "size"),
        "physicalSizeMm",
    )
    if not (50 <= physical_size_mm <= 3000):
        raise HTTPException(status_code=400, detail="physicalSizeMm must be between 50 and 3000.")

    raw_rows = _pick(payload, "rows")
    raw_columns = _pick(payload, "columns")
    if raw_rows is not None and raw_columns is not None:
        rows = _parse_int(raw_rows, "rows")
        columns = _parse_int(raw_columns, "columns")
    else:
        raw_grid_size = _pick(payload, "grid_size", "gridSize", "grid")
        if raw_grid_size is None:
            raise HTTPException(status_code=400, detail="Missing 'rows'/'columns' or 'grid_size'.")
        grid_size = str(raw_grid_size).strip().lower()
        if "x" not in grid_size:
            raise HTTPException(status_code=400, detail="grid_size must look like '5x5'.")
        parts = grid_size.split("x", 1)
        rows = _parse_int(parts[0], "rows")
        columns = _parse_int(parts[1], "columns")

    raw_vertical_exaggeration = _pick(
        payload,
        "vertical_exaggeration",
        "verticalExaggeration",
        "zScale",
        "z_scale",
        "z",
    )
    vertical_exaggeration = _parse_float(
        raw_vertical_exaggeration if raw_vertical_exaggeration is not None else VERTICAL_EXAGGERATION,
        "vertical_exaggeration",
    )
    if not (0.0 < vertical_exaggeration <= 20.0):
        raise HTTPException(status_code=400, detail="vertical_exaggeration must be > 0 and <= 20.")

    raw_base_thickness_mm = _pick(payload, "base_thickness_mm", "baseThicknessMm", "baseThickness", "base_thickness")
    base_thickness_mm = _parse_float(
        raw_base_thickness_mm if raw_base_thickness_mm is not None else BASE_THICKNESS_MM,
        "base_thickness_mm",
    )
    if base_thickness_mm < 0:
        raise HTTPException(status_code=400, detail="base_thickness_mm must be >= 0.")

    smooth_terrain = _parse_bool(_pick(payload, "smoothTerrain", "smooth_terrain", "smooth"), True)
    flatten_sea_level = _parse_bool(_pick(payload, "flattenSeaLevel", "flatten_sea_level", "sea"), True)
    include_buildings = _parse_bool(_pick(payload, "include_buildings", "includeBuildings"), False)
    include_roads = _parse_bool(_pick(payload, "include_roads", "includeRoads"), False)
    quality_preset = _pick(payload, "qualityPreset", "quality_preset", "quality")
    quality_resolution = resolve_quality_preset(quality_preset)

    tmp_dir = Path(gettempdir()) / "topopuzzle-api"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    timestamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"topopuzzle_{rows}x{columns}_{int(round(physical_size_mm))}mm_{timestamp}_{uuid4().hex[:8]}.3mf"
    output_path = tmp_dir / filename
    project_root = Path(__file__).resolve().parent
    template_candidate = project_root / "template.3mf"
    template_path = template_candidate if template_candidate.exists() else None

    return {
        "bbox": (west, south, east, north),
        "physical_size_mm": physical_size_mm,
        "rows": rows,
        "columns": columns,
        "vertical_exaggeration": vertical_exaggeration,
        "z_scale": vertical_exaggeration,
        "base_thickness_mm": base_thickness_mm,
        "smooth_terrain": smooth_terrain,
        "flatten_sea_level": flatten_sea_level,
        "include_buildings": include_buildings,
        "include_roads": include_roads,
        "dem_resolution": float(quality_resolution) if quality_resolution is not None else float(DEM_REQUEST_WIDTH),
        "output_path": output_path,
        "template_path": template_path,
        "filename": filename,
    }


def _run_generation_with_fallback(*, params: dict) -> Path:
    output_path = Path(params["output_path"])
    try:
        generated_path = generate_puzzle_from_map(
            bbox=params["bbox"],
            physical_size_mm=params["physical_size_mm"],
            rows=params["rows"],
            columns=params["columns"],
            z_scale=params["vertical_exaggeration"],
            vertical_exaggeration=params["vertical_exaggeration"],
            smooth_terrain=params["smooth_terrain"],
            flatten_sea_level=params["flatten_sea_level"],
            base_thickness_mm=params["base_thickness_mm"],
            include_buildings=params["include_buildings"],
            include_roads=params["include_roads"],
            dem_resolution=params["dem_resolution"],
            output_path=output_path,
            template_path=params["template_path"],
        )
    except ValueError as exc:
        if output_path.exists():
            _cleanup_file(output_path)
        raise ValueError(str(exc)) from exc
    except FileNotFoundError as exc:
        if output_path.exists():
            _cleanup_file(output_path)
        raise FileNotFoundError(str(exc)) from exc
    except Exception as exc:
        if output_path.exists():
            _cleanup_file(output_path)
        logger.exception("Generation failed: %s", exc)
        raise RuntimeError(f"3MF generation failed: {exc}") from exc

    generated_path = Path(generated_path)
    if not generated_path.exists():
        raise FileNotFoundError("Generation finished, but output file was not found.")
    return generated_path


async def _run_generation_job(job_id: str, params: dict) -> None:
    job = _JOBS.get(job_id)
    if job is None:
        return
    job.status = "running"
    job.progress = 10
    job.updated_at = _iso_now()
    try:
        generated_path = await run_in_threadpool(_run_generation_with_fallback, params=params)
        job.output_path = str(generated_path)
        job.filename = generated_path.name
        job.status = "done"
        job.progress = 100
        job.updated_at = _iso_now()
    except Exception as exc:
        output_path = params.get("output_path")
        if output_path:
            _cleanup_file(Path(output_path))
        job.status = "failed"
        job.progress = 100
        job.error = str(exc)
        job.output_path = None
        job.updated_at = _iso_now()
        logger.exception("Generation job %s failed: %s", job_id, exc)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", status_code=202)
async def generate(payload: dict) -> JSONResponse:
    params = _parse_generation_request(payload)
    _prune_jobs()
    job_id = uuid4().hex
    job = GenerationJob(
        job_id=job_id,
        status="queued",
        progress=0,
        created_at=_iso_now(),
        updated_at=_iso_now(),
        filename=params["filename"],
    )
    _JOBS[job_id] = job
    asyncio.create_task(_run_generation_job(job_id, params))
    return JSONResponse(status_code=202, content={"jobId": job_id, "status": job.status})


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    job = _get_job_or_404(job_id)
    return JSONResponse(content=_serialize_job(job))


@app.get("/jobs/{job_id}/download")
async def download_job(job_id: str) -> FileResponse:
    job = _get_job_or_404(job_id)
    if job.status != "done" or not job.output_path:
        raise HTTPException(status_code=409, detail="Job is not ready for download.")
    generated_path = Path(job.output_path)
    if not generated_path.exists():
        job.output_path = None
        job.updated_at = _iso_now()
        raise HTTPException(status_code=500, detail="Generation finished, but output file was not found.")
    return FileResponse(
        path=str(generated_path),
        filename=job.filename or generated_path.name,
        media_type="application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        background=BackgroundTask(_cleanup_job_file, job_id, generated_path),
    )
