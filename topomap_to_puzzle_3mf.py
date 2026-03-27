#!/usr/bin/env python3
"""
South-west-origin topographic puzzle pipeline.

Core contract:
- Model space is millimeters.
- (0, 0) is the south-west corner of the full model.
- +X points east, +Y points north.
- DEM rows are flipped with np.flipud immediately so DEM and OSM share one frame.
- Terrain, buildings, and roads stay as separate overlapping solids in the 3MF.
"""

from __future__ import annotations

import argparse
import logging
import math
import random
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import trimesh
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon, box
from shapely.affinity import translate as shapely_affinity_translate
from shapely.geometry.polygon import orient
from shapely.ops import triangulate, unary_union


logger = logging.getLogger(__name__)

CORE_3MF_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
ET.register_namespace("", CORE_3MF_NS)

DEM_TIF_PATH = Path("dem_bbox.tif")
DEM_REQUEST_WIDTH = 300
DEM_REQUEST_HEIGHT = 300

QUALITY_PRESET_DEM_RESOLUTION = {
    "very low": 128,
    "very low (fastest)": 128,
    "low": 192,
    "average": 256,
    "high": 384,
    "very high": 512,
}

DEFAULT_BUILDING_HEIGHT_METERS = 5.0
ROAD_DEFAULT_WIDTH_MM = 0.6
ROAD_DEFAULT_HEIGHT_MM = 0.8
VERTICAL_EXAGGERATION = 2.0
BASE_THICKNESS_MM = 5.0
MIN_OVERPASS_BBOX_SPAN_DEG = 0.002
ROAD_MAX_SEGMENT_MM = 1.0
BUILDING_PENETRATION_MM = 3.0
ROAD_PENETRATION_MM = 3.0
ROAD_TOP_OFFSET_MM = 0.8
PRINT_GAP_MM = 5.0
LABEL_DEPTH_BELOW_MM = 0.4
LABEL_DEPTH_ABOVE_MM = 0.4
LABEL_MARGIN_MM = 2.0
LABEL_HEIGHT_MM = 4.0


BITMAP_GLYPHS: Dict[str, Tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10011", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
}


@dataclass(frozen=True)
class TerrainAdaptationResult:
    z_scale: float
    smooth_iterations: int


@dataclass(frozen=True)
class PieceAssembly:
    terrain: trimesh.Trimesh
    roads: Optional[trimesh.Trimesh]
    buildings: Optional[trimesh.Trimesh]
    piece_polygon: Polygon


@dataclass(frozen=True)
class HeightfieldModel:
    heights_mm: np.ndarray
    width_mm: float
    height_mm: float
    mm_per_meter: float
    min_elev: float
    vertical_exaggeration: float
    base_thickness_mm: float


@dataclass(frozen=True)
class PuzzleConfig:
    tiles_x: int
    tiles_y: int
    tab_radius_mm: Optional[float] = None
    tab_depth_mm: Optional[float] = None
    neck_ratio: float = 0.6
    neck_length_ratio: float = 0.3
    edge_clearance_mm: float = 0.0
    tab_noise_seed: int = 0
    boolean_engine: str = "manifold"
    cutter_z_padding_mm: float = 2.0
    arrange_gap_mm: float = PRINT_GAP_MM

    def normalized_boolean_engine(self) -> str:
        engine = str(self.boolean_engine or "manifold").strip().lower()
        if engine in {"", "auto", "default", "overlap"}:
            return "manifold"
        return engine

    def resolved_tab_geometry(self, cell_w: float, cell_h: float) -> Tuple[float, float, float, float, float]:
        tile_edge = max(0.0, min(float(cell_w), float(cell_h)))
        max_radius = max(0.0, (0.5 * tile_edge) - 1e-3)
        if self.tab_radius_mm is None:
            radius = 0.10 * tile_edge
        else:
            radius = float(self.tab_radius_mm)
        radius = min(max(0.0, radius), max_radius)

        neck_ratio = min(max(float(self.neck_ratio), 0.05), 0.95)
        neck_length_ratio = min(max(float(self.neck_length_ratio), 0.05), 1.0)
        derived_depth = radius * (1.0 + neck_length_ratio)
        if self.tab_depth_mm is None:
            depth = derived_depth
        else:
            depth = float(self.tab_depth_mm)
        depth = min(max(0.0, depth), max(0.0, (0.49 * tile_edge)))

        clearance = max(0.0, float(self.edge_clearance_mm))
        clearance = min(clearance, max(0.0, (0.5 * tile_edge) - radius - 1e-3))
        return radius, depth, clearance, neck_ratio, neck_length_ratio


def _normalize_bbox(bbox: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    west, south, east, north = bbox
    if west >= east or south >= north:
        raise ValueError("Invalid bbox ordering. Expected (west, south, east, north).")
    return float(west), float(south), float(east), float(north)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi * 0.5) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda * 0.5) ** 2
    return 2.0 * radius_m * math.asin(math.sqrt(max(0.0, a)))


def _bbox_width_height_m(bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    west, south, east, north = _normalize_bbox(bbox)
    mid_lat = 0.5 * (south + north)
    width_m = _haversine_m(mid_lat, west, mid_lat, east)
    height_m = _haversine_m(south, west, north, west)
    return width_m, height_m


def compute_scale_factor_xy(physical_size_mm: float, real_world_size_m: float) -> float:
    if physical_size_mm <= 0:
        raise ValueError("physical_size_mm must be > 0.")
    if real_world_size_m <= 0:
        raise ValueError("real_world_size_m must be > 0.")
    return float(physical_size_mm) / float(real_world_size_m)


def compute_model_size_mm(
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
) -> Tuple[float, float, float]:
    west, south, east, north = _normalize_bbox(bbox)
    if physical_size_mm <= 0:
        raise ValueError("physical_size_mm must be > 0.")
    width_m, height_m = _bbox_width_height_m((west, south, east, north))
    mm_per_meter = compute_scale_factor_xy(float(physical_size_mm), max(width_m, height_m))
    return width_m * mm_per_meter, height_m * mm_per_meter, mm_per_meter


def _bbox_to_model_projector(
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
) -> Callable[[float, float], Tuple[float, float]]:
    west, south, east, north = _normalize_bbox(bbox)
    width_mm, height_mm, _ = compute_model_size_mm(bbox, physical_size_mm)
    lon_span = max(1e-12, east - west)
    lat_span = max(1e-12, north - south)

    def project(lon: float, lat: float) -> Tuple[float, float]:
        x_mm = ((float(lon) - west) / lon_span) * width_mm
        y_mm = ((float(lat) - south) / lat_span) * height_mm
        return x_mm, y_mm

    return project


def _dem_request_size_from_resolution(
    bbox: Tuple[float, float, float, float],
    resolution: float,
) -> Tuple[int, int]:
    target_px = max(64, int(round(float(resolution))))
    width_m, height_m = _bbox_width_height_m(bbox)
    longest = max(width_m, height_m, 1e-9)
    scale = target_px / longest
    return max(2, int(round(width_m * scale))), max(2, int(round(height_m * scale)))


def fetch_dem_tiff(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    px_width: int = DEM_REQUEST_WIDTH,
    px_height: int = DEM_REQUEST_HEIGHT,
    out_path: Path | str = DEM_TIF_PATH,
) -> Path:
    import requests

    response = requests.get(
        "https://transitnetwork.ddns.net/geoserver/cc/wcs",
        params={
            "SERVICE": "WCS",
            "VERSION": "2.0.1",
            "REQUEST": "GetCoverage",
            "COVERAGEID": "cc:cop",
            "FORMAT": "image/tiff",
            "SUBSETTINGCRS": "EPSG:4326",
            "OUTPUTCRS": "EPSG:4326",
            "SUBSET": [f"Lat({min_lat},{max_lat})", f"Long({min_lon},{max_lon})"],
            "SCALETOSIZE": f"Long({px_width}),Lat({px_height})",
        },
        timeout=180,
    )
    response.raise_for_status()
    output = Path(out_path)
    output.write_bytes(response.content)
    return output


def read_dem_tiff_to_array(path: Path | str) -> np.ndarray:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DEM file not found: {path}")

    dem: Optional[np.ndarray] = None
    try:
        import rasterio

        with rasterio.open(path) as src:
            dem = np.asarray(src.read(1), dtype=np.float64)
    except Exception:
        import tifffile

        dem = np.asarray(tifffile.imread(str(path)), dtype=np.float64)
        if dem.ndim == 3:
            dem = dem[0] if dem.shape[0] <= dem.shape[-1] else dem[..., 0]

    if dem.ndim != 2:
        raise ValueError(f"Expected 2D DEM array, got {dem.shape}")
    return dem


def _prepare_dem_array(
    dem: np.ndarray,
    smooth_iterations: int,
    flatten_sea_level: bool,
) -> np.ndarray:
    working = np.flipud(np.asarray(dem, dtype=np.float64))
    if flatten_sea_level:
        working = np.where(working < 0.0, 0.0, working)
    for _ in range(max(0, int(smooth_iterations))):
        working = _bilinear_smooth_dem(working)
    return working


def fetch_dem(
    bbox: Tuple[float, float, float, float],
    resolution: float,
) -> np.ndarray:
    west, south, east, north = _normalize_bbox(bbox)
    px_width, px_height = _dem_request_size_from_resolution(bbox, resolution)
    with tempfile.NamedTemporaryFile(prefix="topopuzzle_dem_", suffix=".tif", delete=False) as tmp:
        dem_path = Path(tmp.name)
    try:
        fetch_dem_tiff(
            min_lat=south,
            min_lon=west,
            max_lat=north,
            max_lon=east,
            px_width=px_width,
            px_height=px_height,
            out_path=dem_path,
        )
        return np.flipud(read_dem_tiff_to_array(dem_path))
    finally:
        dem_path.unlink(missing_ok=True)


def compute_dem_stats(dem: np.ndarray) -> Tuple[float, float, float]:
    valid = np.asarray(dem, dtype=np.float64)
    valid = valid[np.isfinite(valid)]
    if valid.size == 0:
        raise ValueError("DEM contains no finite samples.")
    min_z = float(np.min(valid))
    max_z = float(np.max(valid))
    return min_z, max_z, max_z - min_z


def _bilinear_smooth_dem(dem: np.ndarray) -> np.ndarray:
    src = np.asarray(dem, dtype=np.float64)
    padded = np.pad(src, ((1, 1), (1, 1)), mode="edge")
    return (
        padded[:-2, :-2]
        + 2.0 * padded[:-2, 1:-1]
        + padded[:-2, 2:]
        + 2.0 * padded[1:-1, :-2]
        + 4.0 * padded[1:-1, 1:-1]
        + 2.0 * padded[1:-1, 2:]
        + padded[2:, :-2]
        + 2.0 * padded[2:, 1:-1]
        + padded[2:, 2:]
    ) / 16.0


def _build_heightfield_model(
    dem: np.ndarray,
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
    vertical_exaggeration: float,
    base_thickness_mm: float,
    smooth_iterations: int,
    flatten_sea_level: bool,
) -> HeightfieldModel:
    if vertical_exaggeration <= 0:
        raise ValueError("vertical_exaggeration must be > 0.")
    if base_thickness_mm < 0:
        raise ValueError("base_thickness_mm must be >= 0.")

    prepared = _prepare_dem_array(dem, smooth_iterations, flatten_sea_level)
    min_z, _, _ = compute_dem_stats(prepared)
    width_mm, height_mm, mm_per_meter = compute_model_size_mm(bbox, physical_size_mm)
    heights_mm = ((prepared - min_z) * mm_per_meter * float(vertical_exaggeration)) + float(base_thickness_mm)
    return HeightfieldModel(
        heights_mm=heights_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        mm_per_meter=mm_per_meter,
        min_elev=min_z,
        vertical_exaggeration=float(vertical_exaggeration),
        base_thickness_mm=float(base_thickness_mm),
    )


def _grid_vertices(width_mm: float, height_mm: float, heights_mm: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    rows, cols = heights_mm.shape
    xs = np.linspace(0.0, width_mm, cols, dtype=np.float64)
    ys = np.linspace(0.0, height_mm, rows, dtype=np.float64)
    vertices: List[List[float]] = []
    top_indices = np.zeros((rows, cols), dtype=np.int64)
    bottom_indices = np.zeros((rows, cols), dtype=np.int64)

    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            top_indices[row, col] = len(vertices)
            vertices.append([float(x), float(y), float(heights_mm[row, col])])
    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            bottom_indices[row, col] = len(vertices)
            vertices.append([float(x), float(y), 0.0])

    return np.asarray(vertices, dtype=np.float64), np.stack((top_indices, bottom_indices))


def _terrain_faces(indices: np.ndarray) -> np.ndarray:
    top_indices = indices[0]
    bottom_indices = indices[1]
    rows, cols = top_indices.shape
    faces: List[List[int]] = []

    for row in range(rows - 1):
        for col in range(cols - 1):
            a = int(top_indices[row, col])
            b = int(top_indices[row, col + 1])
            c = int(top_indices[row + 1, col + 1])
            d = int(top_indices[row + 1, col])
            faces.append([a, b, c])
            faces.append([a, c, d])

            ba = int(bottom_indices[row, col])
            bb = int(bottom_indices[row, col + 1])
            bc = int(bottom_indices[row + 1, col + 1])
            bd = int(bottom_indices[row + 1, col])
            faces.append([ba, bc, bb])
            faces.append([ba, bd, bc])

    def add_wall(top_a: int, top_b: int, bottom_a: int, bottom_b: int) -> None:
        faces.append([top_a, bottom_a, bottom_b])
        faces.append([top_a, bottom_b, top_b])

    for col in range(cols - 1):
        add_wall(
            int(top_indices[0, col]),
            int(top_indices[0, col + 1]),
            int(bottom_indices[0, col]),
            int(bottom_indices[0, col + 1]),
        )
        add_wall(
            int(top_indices[rows - 1, col + 1]),
            int(top_indices[rows - 1, col]),
            int(bottom_indices[rows - 1, col + 1]),
            int(bottom_indices[rows - 1, col]),
        )
    for row in range(rows - 1):
        add_wall(
            int(top_indices[row + 1, 0]),
            int(top_indices[row, 0]),
            int(bottom_indices[row + 1, 0]),
            int(bottom_indices[row, 0]),
        )
        add_wall(
            int(top_indices[row, cols - 1]),
            int(top_indices[row + 1, cols - 1]),
            int(bottom_indices[row, cols - 1]),
            int(bottom_indices[row + 1, cols - 1]),
        )

    return np.asarray(faces, dtype=np.int64)


def _cleanup_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    if hasattr(mesh, "merge_vertices"):
        mesh.merge_vertices()

    if hasattr(mesh, "remove_duplicate_faces"):
        mesh.remove_duplicate_faces()
    elif hasattr(mesh, "unique_faces"):
        mesh.update_faces(mesh.unique_faces())

    if hasattr(mesh, "remove_degenerate_faces"):
        mesh.remove_degenerate_faces()
    elif hasattr(mesh, "nondegenerate_faces"):
        mesh.update_faces(mesh.nondegenerate_faces())

    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    return mesh


def build_terrain_mesh_from_dem(
    dem: np.ndarray,
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
    vertical_exaggeration: float,
    base_thickness_mm: float,
    smooth_iterations: int = 0,
    flatten_sea_level: bool = True,
) -> trimesh.Trimesh:
    heightfield = _build_heightfield_model(
        dem=dem,
        bbox=bbox,
        physical_size_mm=physical_size_mm,
        vertical_exaggeration=vertical_exaggeration,
        base_thickness_mm=base_thickness_mm,
        smooth_iterations=smooth_iterations,
        flatten_sea_level=flatten_sea_level,
    )
    vertices, indices = _grid_vertices(heightfield.width_mm, heightfield.height_mm, heightfield.heights_mm)
    faces = _terrain_faces(indices)
    mesh = _cleanup_mesh(trimesh.Trimesh(vertices=vertices, faces=faces, process=False))
    if not mesh.is_watertight:
        raise RuntimeError("Terrain mesh is not watertight.")
    mesh.metadata["name"] = "terrain"
    mesh.metadata["part_role"] = "terrain"
    return mesh


def _bilinear_sample_grid(values: np.ndarray, x_frac: float, y_frac: float) -> float:
    rows, cols = values.shape
    gx = np.clip(float(x_frac) * max(1, cols - 1), 0.0, max(1, cols - 1))
    gy = np.clip(float(y_frac) * max(1, rows - 1), 0.0, max(1, rows - 1))
    x0 = int(math.floor(gx))
    x1 = min(cols - 1, x0 + 1)
    y0 = int(math.floor(gy))
    y1 = min(rows - 1, y0 + 1)
    tx = gx - x0
    ty = gy - y0
    v00 = float(values[y0, x0])
    v10 = float(values[y0, x1])
    v01 = float(values[y1, x0])
    v11 = float(values[y1, x1])
    top = v00 * (1.0 - tx) + v10 * tx
    bottom = v01 * (1.0 - tx) + v11 * tx
    return top * (1.0 - ty) + bottom * ty


def _build_surface_sampler_from_dem(
    dem: np.ndarray,
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
    vertical_exaggeration: float,
    base_thickness_mm: float,
    smooth_iterations: int,
    flatten_sea_level: bool,
) -> Callable[[float, float], float]:
    heightfield = _build_heightfield_model(
        dem=dem,
        bbox=bbox,
        physical_size_mm=physical_size_mm,
        vertical_exaggeration=vertical_exaggeration,
        base_thickness_mm=base_thickness_mm,
        smooth_iterations=smooth_iterations,
        flatten_sea_level=flatten_sea_level,
    )

    def sample(x_mm: float, y_mm: float) -> float:
        if heightfield.width_mm <= 0 or heightfield.height_mm <= 0:
            return float(base_thickness_mm)
        x_frac = np.clip(float(x_mm) / heightfield.width_mm, 0.0, 1.0)
        y_frac = np.clip(float(y_mm) / heightfield.height_mm, 0.0, 1.0)
        return _bilinear_sample_grid(heightfield.heights_mm, x_frac, y_frac)

    return sample


def generate_smooth_terrain(
    dem: np.ndarray,
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
    vertical_exaggeration: float,
    base_thickness_mm: float,
) -> trimesh.Trimesh:
    return build_terrain_mesh_from_dem(
        dem=dem,
        bbox=bbox,
        physical_size_mm=physical_size_mm,
        vertical_exaggeration=vertical_exaggeration,
        base_thickness_mm=base_thickness_mm,
        smooth_iterations=1,
        flatten_sea_level=True,
    )


def auto_adapt_terrain_params(
    dem: np.ndarray,
    base_z_scale: float,
    base_smooth_iterations: int,
) -> TerrainAdaptationResult:
    return TerrainAdaptationResult(z_scale=float(base_z_scale), smooth_iterations=int(base_smooth_iterations))


def _prepare_map_terrain(
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
    z_scale: float,
    smooth_terrain: bool,
    flatten_sea_level: bool,
    dem_resolution: float = float(DEM_REQUEST_WIDTH),
    base_thickness_mm: float = BASE_THICKNESS_MM,
) -> Tuple[trimesh.Trimesh, np.ndarray, Tuple[float, float, float], TerrainAdaptationResult]:
    raw_dem = fetch_dem(bbox=bbox, resolution=dem_resolution)
    adaptation = auto_adapt_terrain_params(
        dem=raw_dem,
        base_z_scale=z_scale,
        base_smooth_iterations=1 if smooth_terrain else 0,
    )
    terrain_mesh = build_terrain_mesh_from_dem(
        dem=raw_dem,
        bbox=bbox,
        physical_size_mm=physical_size_mm,
        vertical_exaggeration=adaptation.z_scale,
        base_thickness_mm=base_thickness_mm,
        smooth_iterations=adaptation.smooth_iterations,
        flatten_sea_level=flatten_sea_level,
    )
    return terrain_mesh, raw_dem, compute_dem_stats(raw_dem), adaptation


def resolve_quality_preset(preset: Optional[str]) -> Optional[int]:
    if preset is None:
        return None
    return QUALITY_PRESET_DEM_RESOLUTION.get(str(preset).strip().lower())


def _normalize_overpass_bbox(bbox: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    west, south, east, north = _normalize_bbox(bbox)
    if east - west < MIN_OVERPASS_BBOX_SPAN_DEG:
        pad = 0.5 * (MIN_OVERPASS_BBOX_SPAN_DEG - (east - west))
        west -= pad
        east += pad
    if north - south < MIN_OVERPASS_BBOX_SPAN_DEG:
        pad = 0.5 * (MIN_OVERPASS_BBOX_SPAN_DEG - (north - south))
        south -= pad
        north += pad
    return south, west, north, east


_OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]


def _run_overpass_query(query: str) -> List[Dict[str, Any]]:
    import requests

    last_exc: Optional[Exception] = None
    for mirror in _OVERPASS_MIRRORS:
        try:
            response = requests.post(mirror, data=query.encode("utf-8"), timeout=60)
            response.raise_for_status()
            payload = response.json()
            return list(payload.get("elements", []))
        except Exception as exc:
            logger.debug("Overpass mirror %s failed: %s", mirror, exc)
            last_exc = exc
    raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_exc}")


def fetch_osm_buildings(bbox: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    south, west, north, east = _normalize_overpass_bbox(bbox)
    query = f"""
    [out:json][timeout:30];
    way["building"]({south},{west},{north},{east});
    out body geom;
    """
    try:
        elements = _run_overpass_query(query)
    except Exception as exc:
        logger.warning("Building query skipped: %s", exc)
        return []
    return [
        {"geometry": el.get("geometry", []), "tags": dict(el.get("tags", {}) or {})}
        for el in elements
        if el.get("geometry")
    ]


def fetch_osm_roads(bbox: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    south, west, north, east = _normalize_overpass_bbox(bbox)
    # Include all meaningful road/path types
    query = f"""
    [out:json][timeout:30];
    way["highway"~"motorway|trunk|primary|secondary|tertiary|residential|service|living_street|pedestrian|track|path|cycleway|footway|steps|bridleway"]({south},{west},{north},{east});
    out body geom;
    """
    try:
        elements = _run_overpass_query(query)
    except Exception as exc:
        logger.warning("Road query skipped: %s", exc)
        return []
    return [
        {"geometry": el.get("geometry", []), "tags": dict(el.get("tags", {}) or {})}
        for el in elements
        if el.get("geometry")
    ]


def _coords_list_to_polygon(coords: Any) -> Optional[Polygon]:
    if not isinstance(coords, list) or len(coords) < 3:
        return None
    points = []
    for point in coords:
        try:
            points.append((float(point["lon"]), float(point["lat"])))
        except Exception:
            return None
    poly = Polygon(points)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty:
        return None
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda item: item.area)
    return poly if isinstance(poly, Polygon) else None


def _coords_list_to_line(coords: Any) -> Optional[LineString]:
    if not isinstance(coords, list) or len(coords) < 2:
        return None
    points = []
    for point in coords:
        try:
            points.append((float(point["lon"]), float(point["lat"])))
        except Exception:
            return None
    line = LineString(points)
    return None if line.is_empty else line


def _project_polygon_to_model_xy(poly: Polygon, projector: Callable[[float, float], Tuple[float, float]]) -> Optional[Polygon]:
    if poly.is_empty:
        return None
    exterior = [projector(lon, lat) for lon, lat in poly.exterior.coords]
    holes = [[projector(lon, lat) for lon, lat in ring.coords] for ring in poly.interiors]
    projected = Polygon(exterior, holes=holes).buffer(0)
    if projected.is_empty:
        return None
    if isinstance(projected, MultiPolygon):
        projected = max(projected.geoms, key=lambda item: item.area)
    return projected if isinstance(projected, Polygon) else None


def _project_line_to_model_xy(line: LineString, projector: Callable[[float, float], Tuple[float, float]]) -> Optional[LineString]:
    if line.is_empty:
        return None
    projected = LineString([projector(lon, lat) for lon, lat in line.coords])
    if projected.is_empty or projected.length <= 1e-9:
        return None
    return projected


def _iter_polygons(geometry: Any) -> Iterable[Polygon]:
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return [geom for geom in geometry.geoms if not geom.is_empty]
    if isinstance(geometry, GeometryCollection):
        items: List[Polygon] = []
        for geom in geometry.geoms:
            items.extend(_iter_polygons(geom))
        return items
    return []


def _iter_lines(geometry: Any) -> Iterable[LineString]:
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return [geom for geom in geometry.geoms if not geom.is_empty]
    if isinstance(geometry, GeometryCollection):
        items: List[LineString] = []
        for geom in geometry.geoms:
            items.extend(_iter_lines(geom))
        return items
    return []


def _polygon_sample_points(poly: Polygon) -> List[Tuple[float, float]]:
    points = [(float(x), float(y)) for x, y in list(poly.exterior.coords)[:-1]]
    centroid = poly.representative_point()
    points.append((float(centroid.x), float(centroid.y)))
    return points


def _parse_building_height_meters(tags: Dict[str, Any], default_height_m: float) -> float:
    raw_height = tags.get("height")
    if raw_height is not None:
        try:
            text = str(raw_height).strip().lower().replace("m", "")
            return max(0.1, float(text))
        except Exception:
            pass
    raw_levels = tags.get("building:levels")
    if raw_levels is not None:
        try:
            return max(0.1, float(raw_levels) * 3.0)
        except Exception:
            pass
    return float(default_height_m)


def _triangles_for_polygon(poly: Polygon) -> List[Polygon]:
    """Triangulate a (possibly non-convex) polygon using earcut.

    Uses trimesh.creation.triangulate_polygon which relies on earcut and
    handles concave shapes and holes correctly – unlike Shapely's Delaunay
    which produces triangles outside the boundary for jigsaw-shaped pieces.
    """
    clean = orient(poly.buffer(0), sign=1.0)
    if clean.is_empty or clean.area <= 1e-9:
        return []
    try:
        # trimesh.creation.triangulate_polygon returns (vertices_2d, faces)
        verts, faces = trimesh.creation.triangulate_polygon(clean, engine="earcut")
        triangles_out: List[Polygon] = []
        for i0, i1, i2 in faces:
            tri = Polygon([verts[i0], verts[i1], verts[i2]])
            if tri.area > 1e-12:
                triangles_out.append(tri)
        return triangles_out
    except Exception:
        # Fallback: Delaunay with containment filter
        triangles_out = []
        for tri in triangulate(clean):
            rep = tri.representative_point()
            if clean.covers(rep):
                triangles_out.append(tri)
        return triangles_out


def _sampled_vertex(
    x: float,
    y: float,
    z: float,
) -> List[float]:
    return [float(x), float(y), float(z)]


def _add_side_faces(
    vertices: List[List[float]],
    faces: List[List[int]],
    ring_coords: Sequence[Tuple[float, float]],
    bottom_z: float,
    top_z: float,
) -> None:
    ring = LineString(ring_coords)
    coords = list(ring.coords)
    if len(coords) < 2:
        return
    for idx in range(len(coords) - 1):
        x0, y0 = coords[idx]
        x1, y1 = coords[idx + 1]
        base = len(vertices)
        vertices.extend(
            [
                [x0, y0, bottom_z],
                [x1, y1, bottom_z],
                [x1, y1, top_z],
                [x0, y0, top_z],
            ]
        )
        faces.append([base, base + 1, base + 2])
        faces.append([base, base + 2, base + 3])


def _add_draped_side_faces(
    vertices: List[List[float]],
    faces: List[List[int]],
    ring_coords: Sequence[Tuple[float, float]],
    sample_bottom: Callable[[float, float], float],
    sample_top: Callable[[float, float], float],
) -> None:
    coords = list(LineString(ring_coords).coords)
    if len(coords) < 2:
        return
    for start, end in zip(coords, coords[1:]):
        x0, y0 = start
        x1, y1 = end
        z0b = float(sample_bottom(x0, y0))
        z1b = float(sample_bottom(x1, y1))
        z0t = float(sample_top(x0, y0))
        z1t = float(sample_top(x1, y1))
        base = len(vertices)
        vertices.extend(
            [
                _sampled_vertex(x0, y0, z0b),
                _sampled_vertex(x1, y1, z1b),
                _sampled_vertex(x1, y1, z1t),
                _sampled_vertex(x0, y0, z0t),
            ]
        )
        faces.append([base, base + 1, base + 2])
        faces.append([base, base + 2, base + 3])


def extrude_polygon_between(poly: Polygon, bottom_z: float, top_z: float) -> trimesh.Trimesh:
    if isinstance(poly, MultiPolygon):
        parts = [extrude_polygon_between(part, bottom_z, top_z) for part in poly.geoms if not part.is_empty]
        parts = [part for part in parts if len(part.faces) > 0]
        if not parts:
            return trimesh.Trimesh()
        return _cleanup_mesh(trimesh.util.concatenate(parts))

    clean = orient(poly.buffer(0), sign=1.0)
    if clean.is_empty or clean.area <= 1e-9 or top_z <= bottom_z:
        return trimesh.Trimesh()

    try:
        verts_2d, faces_2d = trimesh.creation.triangulate_polygon(clean)
    except Exception as exc:
        logger.warning("trimesh triangulate_polygon failed: %s", exc)
        return trimesh.Trimesh()

    verts_3d: List[List[float]] = []
    faces_3d: List[List[int]] = []
    bz = float(bottom_z)
    tz = float(top_z)

    # Bottom vertices (indices 0 to N-1)
    for v in verts_2d:
        verts_3d.append([float(v[0]), float(v[1]), bz])
        
    # Top vertices (indices N to 2N-1)
    n_verts = len(verts_2d)
    for v in verts_2d:
        verts_3d.append([float(v[0]), float(v[1]), tz])

    # Bottom faces (normals pointing down -> reverse winding)
    for f in faces_2d:
        faces_3d.append([int(f[0]), int(f[2]), int(f[1])])

    # Top faces (normals pointing up -> keep winding)
    for f in faces_2d:
        faces_3d.append([int(f[0] + n_verts), int(f[1] + n_verts), int(f[2] + n_verts)])

    # Exterior ring (CCW) -> outward normal is to the right
    ext_coords = list(clean.exterior.coords)[:-1]
    ext_closed = ext_coords + [ext_coords[0]]
    for i in range(len(ext_coords)):
        p0 = ext_closed[i]
        p1 = ext_closed[i+1]
        base = len(verts_3d)
        verts_3d.extend([
            [float(p0[0]), float(p0[1]), bz], # 0
            [float(p1[0]), float(p1[1]), bz], # 1
            [float(p1[0]), float(p1[1]), tz], # 2
            [float(p0[0]), float(p0[1]), tz], # 3
        ])
        faces_3d.extend([
            [base, base + 1, base + 2],
            [base, base + 2, base + 3]
        ])

    # Interior rings (CW) -> outward normal is to the left
    for interior in clean.interiors:
        int_coords = list(interior.coords)[:-1]
        int_closed = int_coords + [int_coords[0]]
        for i in range(len(int_coords)):
            p0 = int_closed[i]
            p1 = int_closed[i+1]
            base = len(verts_3d)
            verts_3d.extend([
                [float(p0[0]), float(p0[1]), bz], # 0
                [float(p1[0]), float(p1[1]), bz], # 1
                [float(p1[0]), float(p1[1]), tz], # 2
                [float(p0[0]), float(p0[1]), tz], # 3
            ])
            faces_3d.extend([
                [base, base + 2, base + 1],
                [base, base + 3, base + 2]
            ])

    mesh = trimesh.Trimesh(
        vertices=np.asarray(verts_3d, dtype=np.float64),
        faces=np.asarray(faces_3d, dtype=np.int64),
        process=False,
    )
    mesh.merge_vertices()
    try:
        mesh.fix_normals()
    except Exception:
        pass
    return _cleanup_mesh(mesh)


def drape_polygon_between(
    poly: Polygon,
    sample_bottom: Callable[[float, float], float],
    sample_top: Callable[[float, float], float],
) -> trimesh.Trimesh:
    clean = orient(poly.buffer(0), sign=1.0)
    if clean.is_empty or clean.area <= 1e-9:
        return trimesh.Trimesh()

    vertices: List[List[float]] = []
    faces: List[List[int]] = []
    for tri in _triangles_for_polygon(clean):
        coords = list(tri.exterior.coords)[:-1]
        top_base = len(vertices)
        for x, y in coords:
            vertices.append(_sampled_vertex(x, y, sample_top(x, y)))
        faces.append([top_base, top_base + 1, top_base + 2])

        bottom_base = len(vertices)
        for x, y in coords:
            vertices.append(_sampled_vertex(x, y, sample_bottom(x, y)))
        faces.append([bottom_base, bottom_base + 2, bottom_base + 1])

    _add_draped_side_faces(vertices, faces, list(clean.exterior.coords), sample_bottom, sample_top)
    for ring in clean.interiors:
        _add_draped_side_faces(vertices, faces, list(ring.coords), sample_bottom, sample_top)

    return _cleanup_mesh(
        trimesh.Trimesh(
            vertices=np.asarray(vertices, dtype=np.float64),
            faces=np.asarray(faces, dtype=np.int64),
            process=False,
        )
    )


def build_buildings_mesh(
    buildings: List[Dict[str, Any]],
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
    building_height_mm: float = DEFAULT_BUILDING_HEIGHT_METERS,
    surface_sampler: Optional[Callable[[float, float], float]] = None,
    clip_polygon: Optional[Polygon] = None,
    model_mm_per_meter: Optional[float] = None,
) -> trimesh.Trimesh:
    projector = _bbox_to_model_projector(bbox, physical_size_mm)
    if model_mm_per_meter is None:
        _, _, model_mm_per_meter = compute_model_size_mm(bbox, physical_size_mm)

    meshes: List[trimesh.Trimesh] = []
    for item in buildings:
        source_polygon = _coords_list_to_polygon(item.get("geometry"))
        if source_polygon is None:
            continue
        projected = _project_polygon_to_model_xy(source_polygon, projector)
        if projected is None:
            continue
        clipped = projected if clip_polygon is None else projected.intersection(clip_polygon)
        cleaned = clipped.buffer(0)
        for poly in _iter_polygons(cleaned):
            if poly.area <= 1e-6:
                continue
            min_terrain_z = 0.0
            if surface_sampler is not None:
                samples = [float(surface_sampler(x, y)) for x, y in _polygon_sample_points(poly)]
                if samples:
                    min_terrain_z = min(samples)
            height_m = _parse_building_height_meters(dict(item.get("tags", {}) or {}), default_height_m=float(building_height_mm))
            height_mm = float(height_m) * float(model_mm_per_meter)
            mesh = extrude_polygon_between(poly, min_terrain_z - BUILDING_PENETRATION_MM, min_terrain_z + height_mm)
            if len(mesh.faces) > 0:
                mesh.metadata["name"] = "buildings"
                mesh.metadata["part_role"] = "buildings"
                meshes.append(mesh)

    if not meshes:
        return trimesh.Trimesh()
    out = trimesh.util.concatenate(meshes)
    out.metadata["name"] = "buildings"
    out.metadata["part_role"] = "buildings"
    return _cleanup_mesh(out)


def _densify_line_string(line: LineString, max_segment_length: float) -> List[Tuple[float, float]]:
    if max_segment_length <= 0:
        raise ValueError("max_segment_length must be > 0.")
    coords = list(line.coords)
    if len(coords) < 2:
        return coords
    dense: List[Tuple[float, float]] = [coords[0]]
    for start, end in zip(coords, coords[1:]):
        segment = LineString([start, end])
        steps = max(1, int(math.ceil(segment.length / max_segment_length)))
        for step in range(1, steps + 1):
            point = segment.interpolate(step / steps, normalized=True)
            dense.append((float(point.x), float(point.y)))
    return dense


def build_roads_mesh(
    roads: List[Dict[str, Any]],
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
    road_width_mm: float = ROAD_DEFAULT_WIDTH_MM,
    road_height_mm: float = ROAD_DEFAULT_HEIGHT_MM,
    surface_sampler: Optional[Callable[[float, float], float]] = None,
    clip_polygon: Optional[Polygon] = None,
) -> trimesh.Trimesh:
    projector = _bbox_to_model_projector(bbox, physical_size_mm)
    meshes: List[trimesh.Trimesh] = []

    for item in roads:
        source_line = _coords_list_to_line(item.get("geometry"))
        if source_line is None:
            continue
        projected = _project_line_to_model_xy(source_line, projector)
        if projected is None:
            continue
        clipped = projected if clip_polygon is None else projected.intersection(clip_polygon)
        for line in _iter_lines(clipped):
            if line.length <= 1e-9:
                continue
            simplified = line.simplify(max(0.2, road_width_mm * 0.5), preserve_topology=False)
            dense_points = _densify_line_string(simplified, ROAD_MAX_SEGMENT_MM)
            if len(dense_points) < 2:
                continue
            for start, end in zip(dense_points, dense_points[1:]):
                segment = LineString([start, end])
                if segment.length <= 1e-9:
                    continue
                road_poly = segment.buffer(road_width_mm * 0.5, cap_style=2, join_style=2).buffer(0)
                if road_poly.is_empty:
                    continue
                def sample_surface(x: float, y: float) -> float:
                    if surface_sampler is None:
                        return 0.0
                    return float(surface_sampler(float(x), float(y)))
                sample_z = min(sample_surface(float(start[0]), float(start[1])), sample_surface(float(end[0]), float(end[1])))
                mesh = extrude_polygon_between(road_poly, sample_z - ROAD_PENETRATION_MM, sample_z + ROAD_TOP_OFFSET_MM)
                if len(mesh.faces) > 0:
                    mesh.metadata["name"] = "roads"
                    mesh.metadata["part_role"] = "roads"
                    meshes.append(mesh)

    if not meshes:
        return trimesh.Trimesh()
    out = trimesh.util.concatenate(meshes)
    out.metadata["name"] = "roads"
    out.metadata["part_role"] = "roads"
    return _cleanup_mesh(out)


def build_full_map_model(
    *,
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
    z_scale: float,
    smooth_terrain: bool,
    flatten_sea_level: bool,
    include_buildings: bool = False,
    include_roads: bool = False,
    quality_preset: Optional[str] = None,
    dem_resolution: float = float(DEM_REQUEST_WIDTH),
    vertical_exaggeration: Optional[float] = None,
    base_thickness_mm: float = BASE_THICKNESS_MM,
) -> trimesh.Scene:
    effective_z = float(vertical_exaggeration if vertical_exaggeration is not None else z_scale)
    preset_resolution = resolve_quality_preset(quality_preset)
    if preset_resolution is not None:
        dem_resolution = float(preset_resolution)

    terrain_mesh, dem, stats, adaptation = _prepare_map_terrain(
        bbox=bbox,
        physical_size_mm=physical_size_mm,
        z_scale=effective_z,
        smooth_terrain=smooth_terrain,
        flatten_sea_level=flatten_sea_level,
        dem_resolution=dem_resolution,
        base_thickness_mm=base_thickness_mm,
    )

    terrain_sampler = _build_surface_sampler_from_dem(
        dem=dem,
        bbox=bbox,
        physical_size_mm=physical_size_mm,
        vertical_exaggeration=adaptation.z_scale,
        base_thickness_mm=base_thickness_mm,
        smooth_iterations=adaptation.smooth_iterations,
        flatten_sea_level=flatten_sea_level,
    )

    scene = trimesh.Scene()
    scene.add_geometry(terrain_mesh.copy(), geom_name="terrain")

    buildings_raw: List[Dict[str, Any]] = []
    roads_raw: List[Dict[str, Any]] = []

    if include_buildings:
        buildings_raw = fetch_osm_buildings(bbox)
        buildings_mesh = build_buildings_mesh(
            buildings=buildings_raw,
            bbox=bbox,
            physical_size_mm=physical_size_mm,
            surface_sampler=terrain_sampler,
        )
        if len(buildings_mesh.faces) > 0:
            scene.add_geometry(buildings_mesh, geom_name="buildings")

    if include_roads:
        roads_raw = fetch_osm_roads(bbox)
        roads_mesh = build_roads_mesh(
            roads=roads_raw,
            bbox=bbox,
            physical_size_mm=physical_size_mm,
            surface_sampler=terrain_sampler,
        )
        if len(roads_mesh.faces) > 0:
            scene.add_geometry(roads_mesh, geom_name="roads")

    scene.metadata["terrain_stats"] = stats
    scene.metadata["terrain_adaptation"] = {
        "z_scale": adaptation.z_scale,
        "smooth_iterations": adaptation.smooth_iterations,
    }
    scene.metadata["dem_resolution"] = dem_resolution
    scene.metadata["pipeline"] = {
        "bbox": bbox,
        "physical_size_mm": physical_size_mm,
        "dem": dem,
        "vertical_exaggeration": adaptation.z_scale,
        "base_thickness_mm": base_thickness_mm,
        "flatten_sea_level": flatten_sea_level,
        "smooth_iterations": adaptation.smooth_iterations,
        "buildings": buildings_raw,
        "roads": roads_raw,
    }
    return scene


def _grid_label_text(row: int, col: int) -> str:
    return f"{chr(ord('A') + row)}{col + 1}"


def _glyph_polygon(char: str, scale: float) -> Polygon:
    rows = BITMAP_GLYPHS.get(char.upper())
    if rows is None:
        return box(0.0, 0.0, scale * 0.6, scale)
    pixel = scale / float(len(rows))
    blocks = []
    row_count = len(rows)
    col_count = len(rows[0])
    for row_idx, row_bits in enumerate(rows):
        for col_idx, bit in enumerate(row_bits):
            if bit != "1":
                continue
            min_x = col_idx * pixel
            max_x = min_x + pixel
            max_y = (row_count - row_idx) * pixel
            min_y = max_y - pixel
            blocks.append(box(min_x, min_y, max_x, max_y))
    if not blocks:
        return box(0.0, 0.0, pixel, pixel)
    merged = unary_union(blocks).buffer(0)
    if isinstance(merged, MultiPolygon):
        merged = max(merged.geoms, key=lambda geom: geom.area)
    return merged


def _label_polygon(text: str, char_height_mm: float = LABEL_HEIGHT_MM) -> Polygon:
    cursor_x = 0.0
    glyphs = []
    for char in text:
        glyph = _glyph_polygon(char, char_height_mm)
        glyph = shapely_affinity_translate(glyph, xoff=cursor_x, yoff=0.0)
        glyphs.append(glyph)
        cursor_x += char_height_mm * 0.9
    merged = unary_union(glyphs).buffer(0)
    if isinstance(merged, MultiPolygon):
        merged = unary_union([geom for geom in merged.geoms if not geom.is_empty]).buffer(0)
    return merged


def _build_label_mesh(piece_polygon: Polygon, row: int, col: int) -> trimesh.Trimesh:
    label_text = _grid_label_text(row, col)
    label_poly = _label_polygon(label_text, char_height_mm=LABEL_HEIGHT_MM)
    min_x, min_y, _, _ = piece_polygon.bounds
    placed = shapely_affinity_translate(
        label_poly,
        xoff=min_x + LABEL_MARGIN_MM,
        yoff=min_y + LABEL_MARGIN_MM,
    ).buffer(0)
    mesh = extrude_polygon_between(placed, -LABEL_DEPTH_BELOW_MM, LABEL_DEPTH_ABOVE_MM)
    mesh.metadata["name"] = "label"
    mesh.metadata["part_role"] = "label"
    mesh.metadata["label_text"] = label_text
    return mesh


def generate_puzzle_polygons(
    rows: int,
    columns: int,
    width_mm: float,
    height_mm: float,
) -> List[Tuple[int, int, Polygon]]:
    """
    Compatibility wrapper around the stable jigsaw builder.

    This preserves older callers while ensuring there is only one
    implementation for puzzle-outline generation.
    """
    if rows <= 0 or columns <= 0:
        raise ValueError("rows and columns must be positive integers.")
    map_bounds = np.array(
        [[0.0, 0.0, 0.0], [float(width_mm), float(height_mm), 0.0]],
        dtype=np.float64,
    )
    config = PuzzleConfig(
        tiles_x=int(columns),
        tiles_y=int(rows),
        tab_radius_mm=None,
        tab_depth_mm=None,
        edge_clearance_mm=0.0,
        tab_noise_seed=0,
    )
    return build_puzzle_tile_outlines(map_bounds, config)


def _validate_puzzle_config(config: PuzzleConfig) -> PuzzleConfig:
    if config.tiles_x <= 0 or config.tiles_y <= 0:
        raise ValueError("tiles_x and tiles_y must be positive.")
    if config.tab_radius_mm is not None and float(config.tab_radius_mm) < 0.0:
        raise ValueError("tab_radius_mm must be >= 0 when provided.")
    if config.tab_depth_mm is not None and float(config.tab_depth_mm) < 0.0:
        raise ValueError("tab_depth_mm must be >= 0 when provided.")
    if float(config.neck_ratio) <= 0.0:
        raise ValueError("neck_ratio must be > 0.")
    if float(config.neck_length_ratio) <= 0.0:
        raise ValueError("neck_length_ratio must be > 0.")
    if float(config.edge_clearance_mm) < 0.0:
        raise ValueError("edge_clearance_mm must be >= 0.")
    if config.cutter_z_padding_mm <= 0.0:
        raise ValueError("cutter_z_padding_mm must be > 0.")
    return config


def _normalize_boolean_result(result: Any) -> Optional[trimesh.Trimesh]:
    if result is None:
        return None
    if isinstance(result, trimesh.Trimesh):
        return result
    if isinstance(result, trimesh.Scene):
        if not result.geometry:
            return None
        return trimesh.util.concatenate(tuple(result.geometry.values()))
    if isinstance(result, (list, tuple)):
        meshes = [item for item in (_normalize_boolean_result(item) for item in result) if item is not None]
        if not meshes:
            return None
        return trimesh.util.concatenate(meshes)
    return None


def _cleanup_boolean_mesh(mesh: trimesh.Trimesh, name: str) -> trimesh.Trimesh:
    if mesh.is_watertight and abs(float(mesh.volume)) > 1e-6:
        direct = mesh.copy()
        direct.metadata.setdefault("name", name)
        return direct

    parts = _split_mesh_components(mesh.copy())
    good_parts: List[trimesh.Trimesh] = []
    for part in parts:
        if len(part.faces) == 0:
            continue
        if abs(float(part.volume)) <= 1e-6 and float(np.prod(np.maximum(part.extents, 0.0))) <= 1e-6:
            continue
        cleaned_part = _cleanup_mesh(part)
        if not cleaned_part.is_watertight:
            try:
                cleaned_part.fill_holes()
                cleaned_part = _cleanup_mesh(cleaned_part)
            except Exception:
                pass
        if cleaned_part.is_watertight and abs(float(cleaned_part.volume)) > 1e-6:
            good_parts.append(cleaned_part)

    if not good_parts:
        cleaned = _cleanup_mesh(mesh.copy())
        if cleaned.is_watertight:
            cleaned.metadata.setdefault("name", name)
            return cleaned
        raise RuntimeError(f"Boolean cut produced a non-watertight tile: {name}")

    merged = good_parts[0] if len(good_parts) == 1 else _cleanup_mesh(trimesh.util.concatenate(good_parts))
    merged.metadata.setdefault("name", name)
    return merged


def _snap_mesh_z_to_source_levels(
    mesh: trimesh.Trimesh,
    source_z_levels: np.ndarray,
    tolerance: float = 0.05,
) -> trimesh.Trimesh:
    levels = np.asarray(source_z_levels, dtype=np.float64).reshape(-1)
    if len(levels) == 0:
        return mesh
    levels = np.unique(levels)
    levels.sort()
    if len(levels) == 0:
        return mesh

    snapped = mesh.copy()
    vertices = np.asarray(snapped.vertices, dtype=np.float64).copy()
    z_vals = vertices[:, 2]
    idx = np.searchsorted(levels, z_vals, side="left")
    idx0 = np.clip(idx - 1, 0, len(levels) - 1)
    idx1 = np.clip(idx, 0, len(levels) - 1)
    cand0 = levels[idx0]
    cand1 = levels[idx1]
    use1 = np.abs(cand1 - z_vals) < np.abs(cand0 - z_vals)
    nearest = np.where(use1, cand1, cand0)
    diffs = np.abs(nearest - z_vals)
    vertices[:, 2] = np.where(diffs <= float(tolerance), nearest, z_vals)
    snapped.vertices = vertices
    snapped.metadata = dict(mesh.metadata or {})
    return _cleanup_mesh(snapped)


def _tile_grid_bounds(
    map_bounds: np.ndarray,
    config: PuzzleConfig,
) -> Tuple[float, float, float, float, float, float]:
    mins = np.asarray(map_bounds[0], dtype=float)
    maxs = np.asarray(map_bounds[1], dtype=float)
    return float(mins[0]), float(mins[1]), float(maxs[0]), float(maxs[1]), float(maxs[2] - mins[2]), float(max(mins[2], 0.0))


def _edge_span_limits(start: float, end: float, edge_clearance_mm: float) -> Tuple[float, float]:
    span = max(0.0, float(end) - float(start))
    margin = min(float(edge_clearance_mm), span * 0.45)
    return float(start) + margin, float(end) - margin


def _tab_center_limits(start: float, end: float) -> Tuple[float, float]:
    span = max(0.0, float(end) - float(start))
    return float(start) + (0.30 * span), float(start) + (0.70 * span)


def _safe_tab_half_width(start: float, end: float, requested_radius: float, edge_clearance_mm: float) -> float:
    span = max(0.0, float(end) - float(start))
    if span <= 0.0:
        return 0.0
    corner_cap = max(0.0, (0.20 * span) - max(0.0, float(edge_clearance_mm)))
    return min(max(0.0, float(requested_radius)), corner_cap)


def _vertical_tab_shape(
    boundary_x: float,
    y0: float,
    y1: float,
    direction: int,
    radius: float,
    depth: float,
    neck_ratio: float,
    neck_length_ratio: float,
    edge_clearance_mm: float,
    rng: random.Random,
) -> Optional[Polygon]:
    del neck_ratio, neck_length_ratio, rng
    half_width = _safe_tab_half_width(y0, y1, radius, edge_clearance_mm)
    if half_width <= 0.0 or depth <= 0.0:
        return None
    center_low, center_high = _tab_center_limits(y0, y1)
    center_y = 0.5 * (center_low + center_high)
    sign = 1.0 if direction >= 0 else -1.0
    centerline = LineString([(boundary_x, center_y), (boundary_x + (sign * depth), center_y)])
    shape = centerline.buffer(half_width, cap_style=1, join_style=1).buffer(0)
    if isinstance(shape, MultiPolygon):
        shape = max(shape.geoms, key=lambda geom: geom.area)
    return orient(shape, sign=1.0) if isinstance(shape, Polygon) else None


def _horizontal_tab_shape(
    boundary_y: float,
    x0: float,
    x1: float,
    direction: int,
    radius: float,
    depth: float,
    neck_ratio: float,
    neck_length_ratio: float,
    edge_clearance_mm: float,
    rng: random.Random,
) -> Optional[Polygon]:
    del neck_ratio, neck_length_ratio, rng
    half_width = _safe_tab_half_width(x0, x1, radius, edge_clearance_mm)
    if half_width <= 0.0 or depth <= 0.0:
        return None
    center_low, center_high = _tab_center_limits(x0, x1)
    center_x = 0.5 * (center_low + center_high)
    sign = 1.0 if direction >= 0 else -1.0
    centerline = LineString([(center_x, boundary_y), (center_x, boundary_y + (sign * depth))])
    shape = centerline.buffer(half_width, cap_style=1, join_style=1).buffer(0)
    if isinstance(shape, MultiPolygon):
        shape = max(shape.geoms, key=lambda geom: geom.area)
    return orient(shape, sign=1.0) if isinstance(shape, Polygon) else None


def build_puzzle_tile_outlines(
    map_bounds: np.ndarray,
    config: PuzzleConfig,
) -> List[Tuple[int, int, Polygon]]:
    config = _validate_puzzle_config(config)
    min_x = float(map_bounds[0][0])
    min_y = float(map_bounds[0][1])
    max_x = float(map_bounds[1][0])
    max_y = float(map_bounds[1][1])
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0.0 or height <= 0.0:
        raise ValueError("Map bounds must have positive XY size.")
    clearance_mm = 0.15

    cell_w = width / config.tiles_x
    cell_h = height / config.tiles_y
    radius, depth, edge_clearance, neck_ratio, neck_length_ratio = config.resolved_tab_geometry(cell_w, cell_h)

    vertical_specs: Dict[Tuple[int, int], Tuple[int, Optional[Polygon]]] = {}
    horizontal_specs: Dict[Tuple[int, int], Tuple[int, Optional[Polygon]]] = {}

    for col in range(config.tiles_x - 1):
        for row in range(config.tiles_y):
            rng = random.Random((int(config.tab_noise_seed) * 1_000_003) + (row * 101) + (col * 1009) + 17)
            direction = 1 if rng.random() >= 0.5 else -1
            x = min_x + ((col + 1) * cell_w)
            y0 = min_y + (row * cell_h)
            y1 = y0 + cell_h
            shape = _vertical_tab_shape(x, y0, y1, direction, radius, depth, neck_ratio, neck_length_ratio, edge_clearance, rng)
            vertical_specs[(row, col)] = (direction, shape)

    for row in range(config.tiles_y - 1):
        for col in range(config.tiles_x):
            rng = random.Random((int(config.tab_noise_seed) * 1_000_033) + (row * 10007) + (col * 137) + 29)
            direction = 1 if rng.random() >= 0.5 else -1
            y = min_y + ((row + 1) * cell_h)
            x0 = min_x + (col * cell_w)
            x1 = x0 + cell_w
            shape = _horizontal_tab_shape(y, x0, x1, direction, radius, depth, neck_ratio, neck_length_ratio, edge_clearance, rng)
            horizontal_specs[(row, col)] = (direction, shape)

    pieces: List[Tuple[int, int, Polygon]] = []
    for row in range(config.tiles_y):
        for col in range(config.tiles_x):
            x0 = min_x + (col * cell_w)
            y0 = min_y + (row * cell_h)
            poly: Polygon = box(x0, y0, x0 + cell_w, y0 + cell_h)

            if col < config.tiles_x - 1:
                direction, shape = vertical_specs[(row, col)]
                if shape is not None:
                    poly = poly.union(shape).buffer(0) if direction > 0 else poly.difference(shape).buffer(0)
            if col > 0:
                direction, shape = vertical_specs[(row, col - 1)]
                if shape is not None:
                    poly = poly.difference(shape).buffer(0) if direction > 0 else poly.union(shape).buffer(0)
            if row < config.tiles_y - 1:
                direction, shape = horizontal_specs[(row, col)]
                if shape is not None:
                    poly = poly.union(shape).buffer(0) if direction > 0 else poly.difference(shape).buffer(0)
            if row > 0:
                direction, shape = horizontal_specs[(row - 1, col)]
                if shape is not None:
                    poly = poly.difference(shape).buffer(0) if direction > 0 else poly.union(shape).buffer(0)

            if isinstance(poly, MultiPolygon):
                poly = max(poly.geoms, key=lambda geom: geom.area)
            poly = poly.buffer(-clearance_mm).buffer(0)
            if poly.is_empty:
                raise RuntimeError(f"Puzzle clearance collapsed tile ({row}, {col}).")
            if isinstance(poly, MultiPolygon):
                poly = max(poly.geoms, key=lambda geom: geom.area)
            pieces.append((row, col, orient(poly, sign=1.0)))
    return pieces


def _build_tile_cutter(piece_polygon: Polygon, map_mesh: trimesh.Trimesh, config: PuzzleConfig) -> trimesh.Trimesh:
    min_z = float(map_mesh.bounds[0][2]) - float(config.cutter_z_padding_mm)
    max_z = float(map_mesh.bounds[1][2]) + float(config.cutter_z_padding_mm)
    cutter = trimesh.creation.extrude_polygon(piece_polygon, max_z - min_z)
    cutter.apply_translation([0.0, 0.0, min_z])
    cutter = _cleanup_mesh(cutter)
    if not cutter.is_watertight:
        raise RuntimeError("Tile cutter mask is not watertight.")
    return cutter


def cut_map_into_puzzle_pieces(
    map_mesh: trimesh.Trimesh,
    config: PuzzleConfig,
) -> List[trimesh.Trimesh]:
    config = _validate_puzzle_config(config)
    if len(map_mesh.faces) == 0:
        raise ValueError("map_mesh is empty.")
    if not map_mesh.is_watertight:
        logger.warning("Puzzle map_mesh is not perfectly watertight. Manifold engine will attempt to process nonetheless.")

    outlines = build_puzzle_tile_outlines(map_mesh.bounds, config)
    pieces: List[trimesh.Trimesh] = []
    engine = config.normalized_boolean_engine()
    source_z_levels = np.asarray(map_mesh.vertices, dtype=np.float64)[:, 2]

    for row, col, outline in outlines:
        cutter = _build_tile_cutter(outline, map_mesh, config)
        tile_name = f"tile_x{col}_y{row}"
        
        try:
            result = trimesh.boolean.intersection([map_mesh, cutter], engine=engine)
            tile_mesh = _normalize_boolean_result(result)
        except Exception as exc:
            logger.error("Boolean intersection exception for %s: %s", tile_name, exc)
            tile_mesh = None

        if tile_mesh is None or len(tile_mesh.faces) == 0:
            logger.error("Boolean cut failed! Cutter bounds: %s", cutter.bounds)
            raise RuntimeError(f"Boolean cut returned an empty tile: {tile_name}")
            
        tile_mesh = _cleanup_boolean_mesh(tile_mesh, tile_name)
        tile_mesh = _snap_mesh_z_to_source_levels(tile_mesh, source_z_levels)
        tile_mesh.metadata["name"] = tile_name
        tile_mesh.metadata["tile_x"] = col
        tile_mesh.metadata["tile_y"] = row
        pieces.append(tile_mesh)

    if len(pieces) != config.tiles_x * config.tiles_y:
        raise RuntimeError(
            f"Failed to generate all puzzle tiles (expected {config.tiles_x * config.tiles_y}, got {len(pieces)})."
        )
    return pieces


def cut_input_mesh_file_to_puzzle_3mf(
    *,
    input_mesh_path: Path | str,
    output_path: Path | str,
    tiles_x: int,
    tiles_y: int,
    size_mm: float,
    tab_radius_mm: Optional[float] = None,
    tab_depth_mm: Optional[float] = None,
    neck_ratio: float = 0.6,
    neck_length_ratio: float = 0.3,
    edge_clearance_mm: float = 0.0,
    tab_noise_seed: int = 0,
    boolean_engine: str = "manifold",
    cutter_z_padding_mm: float = 2.0,
    arrange_gap_mm: float = PRINT_GAP_MM,
    template_path: Optional[Path | str] = "template.3mf",
) -> Path:
    config = PuzzleConfig(
        tiles_x=int(tiles_x),
        tiles_y=int(tiles_y),
        tab_radius_mm=None if tab_radius_mm is None else float(tab_radius_mm),
        tab_depth_mm=None if tab_depth_mm is None else float(tab_depth_mm),
        neck_ratio=float(neck_ratio),
        neck_length_ratio=float(neck_length_ratio),
        edge_clearance_mm=float(edge_clearance_mm),
        tab_noise_seed=int(tab_noise_seed),
        boolean_engine=str(boolean_engine),
        cutter_z_padding_mm=float(cutter_z_padding_mm),
        arrange_gap_mm=float(arrange_gap_mm),
    )
    mesh = _load_input_mesh(input_mesh_path, boolean_engine=config.normalized_boolean_engine())
    mesh = _scale_mesh_to_target_xy_size(mesh, float(size_mm))
    tiles = cut_map_into_puzzle_pieces(mesh, config)
    arranged = arrange_tiles_for_printing(tiles, config)
    export_tiles_3mf(arranged, output_path=output_path, template_path=template_path)
    return Path(output_path)


def _sample_piece_dem(
    sampler: Callable[[float, float], float],
    piece_polygon: Polygon,
    rows: int,
    cols: int,
) -> np.ndarray:
    min_x, min_y, max_x, max_y = piece_polygon.bounds
    xs = np.linspace(min_x, max_x, cols, dtype=np.float64)
    ys = np.linspace(min_y, max_y, rows, dtype=np.float64)
    out = np.zeros((rows, cols), dtype=np.float64)
    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            out[row, col] = sampler(float(x), float(y))
    return out


def _build_piece_terrain_mesh(
    piece_polygon: Polygon,
    sampler: Callable[[float, float], float],
) -> trimesh.Trimesh:
    mesh = drape_polygon_between(
        piece_polygon,
        sample_bottom=lambda _x, _y: 0.0,
        sample_top=lambda x, y: float(sampler(float(x), float(y))),
    )
    mesh.metadata["name"] = "terrain"
    mesh.metadata["part_role"] = "terrain"
    return mesh


def extract_watertight_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Filters out non-watertight fragments from a complex model."""
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate([g for g in mesh.geometry.values()])
    
    if mesh.is_watertight:
        return mesh

    logger.warning("Mesh is not completely watertight, filtering... preserving major components.")
    components = mesh.split(only_watertight=False)
    components.sort(key=lambda c: len(c.faces), reverse=True)
    
    kept_components = []
    if components:
        # Always keep the largest component (the main terrain) even if open
        kept_components.append(components[0])
        logger.info("Kept main geometry (Faces: %d, Watertight: %s)", len(components[0].faces), components[0].is_watertight)
        
    for c in components[1:]:
        # Keep remaining parts only if they are watertight or significantly large
        if c.is_watertight or len(c.faces) > 1000:
            kept_components.append(c)
    
    if kept_components:
        logger.info("Kept %d/%d components overall.", len(kept_components), len(components))
        return trimesh.util.concatenate(kept_components)
    
    return mesh


def _translate_group_to_piece_origin(group: List[trimesh.Trimesh], piece_polygon: Polygon) -> List[trimesh.Trimesh]:
    min_x, min_y, _, _ = piece_polygon.bounds
    translated: List[trimesh.Trimesh] = []
    for mesh in group:
        copy = mesh.copy()
        copy.apply_translation([-min_x, -min_y, 0.0])
        translated.append(copy)
    return translated


def _extract_scene_mesh(scene: trimesh.Scene, name: str) -> Optional[trimesh.Trimesh]:
    geom = scene.geometry.get(name)
    if geom is None:
        return None
    return geom.copy()


def _iter_scene_meshes(scene: trimesh.Scene) -> List[trimesh.Trimesh]:
    meshes: List[trimesh.Trimesh] = []
    for node_name in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph.get(node_name)
        geom = scene.geometry.get(geom_name)
        if geom is None:
            continue
        mesh = geom.copy()
        mesh.apply_transform(transform)
        meshes.append(mesh)
    if meshes:
        return meshes
    return [geom.copy() for geom in scene.geometry.values()]


def merge_scene_to_single_mesh(
    scene: trimesh.Scene,
    boolean_engine: str = "manifold",
) -> trimesh.Trimesh:
    valid_meshes = []
    dropped_count = 0
    
    for scene_mesh in _iter_scene_meshes(scene):
        if len(scene_mesh.faces) == 0:
            continue
            
        components = scene_mesh.split(only_watertight=False)
        for comp in components:
            if comp.is_watertight:
                valid_meshes.append(comp)
            else:
                dropped_count += 1
                
    if dropped_count > 0:
        logger.warning("Dropped %d non-watertight mesh components during scene setup.", dropped_count)

    if not valid_meshes:
        raise ValueError("Scene has no watertight geometry to merge.")
        
    if len(valid_meshes) == 1:
        merged = _cleanup_boolean_mesh(valid_meshes[0], "full_map_mesh")
        merged.metadata["name"] = "full_map_mesh"
        return merged

    engine = PuzzleConfig(tiles_x=1, tiles_y=1, boolean_engine=boolean_engine).normalized_boolean_engine()
    try:
        result = trimesh.boolean.union(valid_meshes, engine=engine)
    except Exception as exc:
        logger.warning("Scene union failed, falling back to concatenation: %s", exc)
        merged = trimesh.util.concatenate(valid_meshes)
        merged = _cleanup_boolean_mesh(merged, "full_map_mesh")
        merged.metadata["name"] = "full_map_mesh"
        return merged
        
    merged = _normalize_boolean_result(result)
    if merged is None or len(merged.faces) == 0:
        logger.warning("Union result empty, falling back to concatenation.")
        merged = trimesh.util.concatenate(valid_meshes)
        
    merged = _cleanup_boolean_mesh(merged, "full_map_mesh")
    merged.metadata["name"] = "full_map_mesh"
    return merged


def _load_input_mesh(input_mesh_path: Path | str, boolean_engine: str = "manifold") -> trimesh.Trimesh:
    loaded = trimesh.load(str(input_mesh_path), force="scene")
    if isinstance(loaded, trimesh.Scene):
        return merge_scene_to_single_mesh(loaded, boolean_engine=boolean_engine)
    if isinstance(loaded, trimesh.Trimesh):
        mesh = loaded.copy()
        mesh.metadata["name"] = "full_map_mesh"
        return _cleanup_boolean_mesh(mesh, "full_map_mesh")
    raise TypeError(f"Unsupported mesh type loaded from {input_mesh_path!s}: {type(loaded).__name__}")


def _scale_mesh_to_target_xy_size(mesh: trimesh.Trimesh, size_mm: float) -> trimesh.Trimesh:
    if size_mm <= 0.0:
        raise ValueError("size_mm must be > 0.")
    current_xy = max(float(mesh.extents[0]), float(mesh.extents[1]))
    if current_xy <= 0.0:
        raise ValueError("Cannot scale mesh with non-positive XY extent.")
    scale_factor = float(size_mm) / current_xy
    scaled = mesh.copy()
    scaled.apply_scale(scale_factor)
    scaled.metadata = dict(mesh.metadata or {})
    scaled.metadata["scale_factor"] = scale_factor
    return scaled


def slice_full_map_into_pieces(
    *,
    full_map_scene: trimesh.Scene,
    rows: int,
    columns: int,
    base_thickness_mm: float,
    seed: Optional[int] = None,
    engine: str = "overlap",
    z_padding: float = 2.0,
) -> List[trimesh.Trimesh]:
    del base_thickness_mm, seed
    mesh = merge_scene_to_single_mesh(full_map_scene, boolean_engine=engine)
    config = PuzzleConfig(
        tiles_x=int(columns),
        tiles_y=int(rows),
        tab_radius_mm=0.10 * min(mesh.extents[0] / max(1, columns), mesh.extents[1] / max(1, rows)),
        edge_clearance_mm=0.0,
        tab_noise_seed=0,
        boolean_engine=engine,
        cutter_z_padding_mm=float(z_padding),
    )
    return cut_map_into_puzzle_pieces(mesh, config)


def arrange_pieces_for_printing(
    pieces: Sequence[Sequence[trimesh.Trimesh]],
    rows: int,
    cols: int,
    bed_size: float,
    gap: float = PRINT_GAP_MM,
) -> Tuple[List[List[trimesh.Trimesh]], int]:
    del bed_size
    arranged: List[List[trimesh.Trimesh]] = []
    cursor_x = 0.0
    cursor_y = 0.0
    current_row = 0
    max_row_height = 0.0

    for index, group in enumerate(pieces):
        meshes = [mesh.copy() for mesh in group]
        if not meshes:
            continue
        group_bounds = np.array([mesh.bounds for mesh in meshes], dtype=np.float64)
        min_xyz = np.min(group_bounds[:, 0, :], axis=0)
        max_xyz = np.max(group_bounds[:, 1, :], axis=0)
        width = float(max_xyz[0] - min_xyz[0])
        height = float(max_xyz[1] - min_xyz[1])
        if index > 0 and index % cols == 0:
            cursor_x = 0.0
            cursor_y += max_row_height + gap
            max_row_height = 0.0
            current_row += 1
        terrain_mesh = next((mesh for mesh in meshes if str(mesh.metadata.get("part_role")) == "terrain"), meshes[0])
        terrain_min_z = float(terrain_mesh.bounds[0][2])
        tx = cursor_x - float(min_xyz[0])
        ty = cursor_y - float(min_xyz[1])
        tz = -terrain_min_z
        for mesh in meshes:
            mesh.apply_translation([tx, ty, tz])
        arranged.append(meshes)
        cursor_x += width + gap
        max_row_height = max(max_row_height, height)

    return arranged, max(1, math.ceil(len(arranged) / max(1, rows * cols)))


def arrange_tiles_for_printing(
    tiles: Sequence[trimesh.Trimesh],
    config: PuzzleConfig,
) -> List[trimesh.Trimesh]:
    arranged: List[trimesh.Trimesh] = []
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0

    for index, tile in enumerate(tiles):
        if index > 0 and index % config.tiles_x == 0:
            cursor_x = 0.0
            cursor_y += row_height + float(config.arrange_gap_mm)
            row_height = 0.0

        placed = tile.copy()
        mins, maxs = placed.bounds
        tx = cursor_x - float(mins[0])
        ty = cursor_y - float(mins[1])
        tz = -float(mins[2])
        placed.apply_translation([tx, ty, tz])
        arranged.append(placed)

        width = float(maxs[0] - mins[0])
        height = float(maxs[1] - mins[1])
        cursor_x += width + float(config.arrange_gap_mm)
        row_height = max(row_height, height)

    return arranged


def _format_3mf_float(value: float) -> str:
    return f"{float(value):.4f}"


def _mesh_xml(parent: ET.Element, mesh: trimesh.Trimesh) -> None:
    mesh_elem = ET.SubElement(parent, f"{{{CORE_3MF_NS}}}mesh")
    vertices_elem = ET.SubElement(mesh_elem, f"{{{CORE_3MF_NS}}}vertices")
    triangles_elem = ET.SubElement(mesh_elem, f"{{{CORE_3MF_NS}}}triangles")
    for vx, vy, vz in np.asarray(mesh.vertices, dtype=np.float64):
        ET.SubElement(
            vertices_elem,
            f"{{{CORE_3MF_NS}}}vertex",
            {"x": _format_3mf_float(vx), "y": _format_3mf_float(vy), "z": _format_3mf_float(vz)},
        )
    for i0, i1, i2 in np.asarray(mesh.faces, dtype=np.int64):
        ET.SubElement(
            triangles_elem,
            f"{{{CORE_3MF_NS}}}triangle",
            {"v1": str(int(i0)), "v2": str(int(i1)), "v3": str(int(i2))},
        )


# AMS/Bambu Studio color slots per part role
_AMS_COLORS: Dict[str, str] = {
    "terrain": "#C8A882",   # Sandy beige – ground/soil
    "buildings": "#FFFFFF", # White – buildings
    "roads": "#404040",     # Dark grey – asphalt
    "water": "#4A90D9",     # Blue – water
    "vegetation": "#5DA84E",# Green – grass/trees
}

_BAMBU_NS = "http://schemas.bambulab.com/package/2021"


def _build_manual_multipart_model_xml(piece_groups: Sequence[Sequence[trimesh.Trimesh]]) -> bytes:
    ET.register_namespace("p", _BAMBU_NS)
    model = ET.Element(f"{{{CORE_3MF_NS}}}model", {"unit": "millimeter"})
    resources = ET.SubElement(model, f"{{{CORE_3MF_NS}}}resources")
    build = ET.SubElement(model, f"{{{CORE_3MF_NS}}}build")

    # Build AMS color palette from all unique roles present
    all_roles: List[str] = []
    for group in piece_groups:
        for mesh in group:
            role = str(mesh.metadata.get("part_role", "terrain"))
            if role not in all_roles:
                all_roles.append(role)
    role_to_slot: Dict[str, int] = {role: idx + 1 for idx, role in enumerate(all_roles)}

    # Write Bambu color group extension
    color_group = ET.SubElement(
        resources,
        f"{{{_BAMBU_NS}}}colorgroup",
        {"id": "cg1"},
    )
    for role in all_roles:
        color_hex = _AMS_COLORS.get(role, "#AAAAAA")
        ET.SubElement(color_group, f"{{{_BAMBU_NS}}}color", {"color": color_hex})

    next_id = 2  # id=1 is the colorgroup
    for group_index, group in enumerate(piece_groups):
        child_ids: List[int] = []
        group_name = str(group[0].metadata.get("piece_group", f"piece_{group_index:03d}"))
        for mesh in group:
            object_id = next_id
            next_id += 1
            child_ids.append(object_id)
            role = str(mesh.metadata.get("part_role", "terrain"))
            slot = role_to_slot.get(role, 1)
            obj_attrs: Dict[str, str] = {
                "id": str(object_id),
                "type": "model",
                "name": role,
                f"{{{_BAMBU_NS}}}extruder": str(slot),
            }
            obj = ET.SubElement(resources, f"{{{CORE_3MF_NS}}}object", obj_attrs)
            _mesh_xml(obj, mesh)

        parent_id = next_id
        next_id += 1
        parent = ET.SubElement(
            resources,
            f"{{{CORE_3MF_NS}}}object",
            {"id": str(parent_id), "type": "model", "name": group_name},
        )
        components = ET.SubElement(parent, f"{{{CORE_3MF_NS}}}components")
        for child_id in child_ids:
            ET.SubElement(components, f"{{{CORE_3MF_NS}}}component", {"objectid": str(child_id)})
        ET.SubElement(build, f"{{{CORE_3MF_NS}}}item", {"objectid": str(parent_id)})

    return ET.tostring(model, encoding="utf-8", xml_declaration=True)


def _build_flat_tile_model_xml(tiles: Sequence[trimesh.Trimesh]) -> bytes:
    model = ET.Element(f"{{{CORE_3MF_NS}}}model", {"unit": "millimeter"})
    resources = ET.SubElement(model, f"{{{CORE_3MF_NS}}}resources")
    build = ET.SubElement(model, f"{{{CORE_3MF_NS}}}build")

    for object_id, tile in enumerate(tiles, start=1):
        obj = ET.SubElement(
            resources,
            f"{{{CORE_3MF_NS}}}object",
            {
                "id": str(object_id),
                "type": "model",
                "name": str(tile.metadata.get("name", f"tile_{object_id:03d}")),
            },
        )
        _mesh_xml(obj, tile)
        ET.SubElement(build, f"{{{CORE_3MF_NS}}}item", {"objectid": str(object_id)})

    return ET.tostring(model, encoding="utf-8", xml_declaration=True)


def _validate_piece_groups_for_export(piece_groups: Sequence[Sequence[trimesh.Trimesh]]) -> None:
    for group_index, group in enumerate(piece_groups):
        if not group:
            raise RuntimeError(f"Piece group {group_index} is empty.")
        for mesh in group:
            if len(mesh.faces) == 0:
                raise RuntimeError(f"Piece group {group_index} contains an empty mesh.")
            if not mesh.is_watertight:
                raise RuntimeError("Non-watertight mesh detected in piece groups.")


def _sanitize_export_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    cleaned = _cleanup_mesh(mesh.copy())
    if cleaned.is_watertight:
        return cleaned

    parts = _split_mesh_components(cleaned)
    good_parts = [part for part in parts if len(part.faces) > 0 and part.is_watertight]
    if not good_parts:
        raise RuntimeError("Non-watertight mesh detected in piece groups.")

    out = _cleanup_mesh(trimesh.util.concatenate(good_parts))
    out.metadata = dict(mesh.metadata or {})
    return out


def _sanitize_piece_groups_for_export(
    piece_groups: Sequence[Sequence[trimesh.Trimesh]],
) -> List[List[trimesh.Trimesh]]:
    sanitized: List[List[trimesh.Trimesh]] = []
    for group in piece_groups:
        sanitized.append([_sanitize_export_mesh(mesh) for mesh in group])
    return sanitized


def _sanitize_tile_meshes_for_export(tiles: Sequence[trimesh.Trimesh]) -> List[trimesh.Trimesh]:
    return [_sanitize_export_mesh(tile) for tile in tiles]


def _split_mesh_components(mesh: trimesh.Trimesh) -> List[trimesh.Trimesh]:
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if len(faces) == 0:
        return []

    parent = list(range(len(faces)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    edge_to_faces: Dict[Tuple[int, int], List[int]] = {}
    for face_index, (a, b, c) in enumerate(faces):
        for edge in ((a, b), (b, c), (c, a)):
            key = tuple(sorted((int(edge[0]), int(edge[1]))))
            edge_to_faces.setdefault(key, []).append(face_index)

    for attached_faces in edge_to_faces.values():
        head = attached_faces[0]
        for other in attached_faces[1:]:
            union(head, other)

    groups: Dict[int, List[int]] = {}
    for face_index in range(len(faces)):
        groups.setdefault(find(face_index), []).append(face_index)

    components: List[trimesh.Trimesh] = []
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    for face_indices in groups.values():
        sub_faces = faces[np.asarray(face_indices, dtype=np.int64)]
        unique_vertices, inverse = np.unique(sub_faces.reshape(-1), return_inverse=True)
        remapped_faces = inverse.reshape((-1, 3))
        sub_vertices = vertices[unique_vertices]
        component = _cleanup_mesh(trimesh.Trimesh(vertices=sub_vertices, faces=remapped_faces, process=False))
        component.metadata = dict(mesh.metadata or {})
        components.append(component)
    return components


def export_piece_groups_3mf(
    piece_groups: Sequence[Sequence[trimesh.Trimesh]],
    *,
    output_path: Path | str,
    template_path: Optional[Path | str] = None,
    plate_assignments: Optional[Sequence[int]] = None,
    object_materials_by_name: Optional[Dict[str, int]] = None,
) -> None:
    del plate_assignments, object_materials_by_name
    sanitized_piece_groups = _sanitize_piece_groups_for_export(piece_groups)
    _validate_piece_groups_for_export(sanitized_piece_groups)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    model_xml = _build_manual_multipart_model_xml(sanitized_piece_groups)
    _write_3mf_with_optional_template(model_xml=model_xml, output_path=output, template_path=template_path)

def _write_fresh_3mf_package(model_xml: bytes, output_path: Path) -> None:
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>""")
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>""",
        )
        zf.writestr("3D/3dmodel.model", model_xml)


def _write_3mf_with_optional_template(
    *,
    model_xml: bytes,
    output_path: Path,
    template_path: Optional[Path | str],
) -> None:
    template = Path(template_path) if template_path else None
    if template is None or not template.exists():
        _write_fresh_3mf_package(model_xml=model_xml, output_path=output_path)
        return

    with ZipFile(template, "r") as src, ZipFile(output_path, "w", compression=ZIP_DEFLATED) as dst:
        for name in src.namelist():
            # Preserve slicer metadata/settings from template and replace only the model payload.
            if name.startswith("3D/") and name.endswith(".model"):
                continue
            if name == "_rels/.rels":
                continue
            dst.writestr(name, src.read(name))
        dst.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>""",
        )
        dst.writestr("3D/3dmodel.model", model_xml)


def export_tiles_3mf(
    tiles: Sequence[trimesh.Trimesh],
    *,
    output_path: Path | str,
    template_path: Optional[Path | str] = "template.3mf",
) -> None:
    sanitized_tiles = _sanitize_tile_meshes_for_export(tiles)
    for tile in sanitized_tiles:
        if len(tile.faces) == 0:
            raise RuntimeError("Cannot export empty tile mesh.")
        if not tile.is_watertight:
            raise RuntimeError("Non-watertight mesh detected in tile export.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    model_xml = _build_flat_tile_model_xml(sanitized_tiles)
    _write_3mf_with_optional_template(model_xml=model_xml, output_path=output, template_path=template_path)


def _validate_piece_count(pieces_count: int, expected: int) -> None:
    if pieces_count < expected:
        raise RuntimeError(
            f"Failed to generate all puzzle pieces (expected {expected}, got {pieces_count}). Geometry intersection failed."
        )


def generate_puzzle_from_map(
    *,
    bbox: Tuple[float, float, float, float],
    physical_size_mm: float,
    rows: int,
    columns: int,
    z_scale: float,
    smooth_terrain: bool,
    flatten_sea_level: bool,
    base_thickness_mm: float,
    output_path: Path | str,
    template_path: Optional[Path | str] = "template.3mf",
    seed: Optional[int] = None,
    engine: str = "overlap",
    z_padding: float = 2.0,
    bed_size: float = 250.0,
    dem_resolution: float = float(DEM_REQUEST_WIDTH),
    include_buildings: bool = False,
    include_roads: bool = False,
    vertical_exaggeration: Optional[float] = None,
) -> Path:
    effective_z = float(vertical_exaggeration if vertical_exaggeration is not None else z_scale)

    _, dem, stats, adaptation = _prepare_map_terrain(
        bbox=bbox,
        physical_size_mm=physical_size_mm,
        z_scale=effective_z,
        smooth_terrain=smooth_terrain,
        flatten_sea_level=flatten_sea_level,
        dem_resolution=dem_resolution,
        base_thickness_mm=base_thickness_mm,
    )
    
    terrain_sampler = _build_surface_sampler_from_dem(
        dem=dem,
        bbox=bbox,
        physical_size_mm=physical_size_mm,
        vertical_exaggeration=adaptation.z_scale,
        base_thickness_mm=base_thickness_mm,
        smooth_iterations=adaptation.smooth_iterations,
        flatten_sea_level=flatten_sea_level,
    )

    buildings_raw = fetch_osm_buildings(bbox) if include_buildings else []
    roads_raw = fetch_osm_roads(bbox) if include_roads else []

    width_mm, height_mm, mm_per_meter = compute_model_size_mm(bbox, physical_size_mm)

    config = PuzzleConfig(
        tiles_x=int(columns),
        tiles_y=int(rows),
        tab_radius_mm=0.10 * min(width_mm / max(1, columns), height_mm / max(1, rows)),
        edge_clearance_mm=0.15,
        tab_noise_seed=0 if seed is None else int(seed),
        cutter_z_padding_mm=float(z_padding),
        arrange_gap_mm=PRINT_GAP_MM,
    )
    
    map_bounds = np.array([[0.0, 0.0, 0.0], [width_mm, height_mm, 0.0]], dtype=np.float64)
    piece_polys = build_puzzle_tile_outlines(map_bounds, config)

    all_piece_groups: List[List[trimesh.Trimesh]] = []
    
    for row, col, poly in piece_polys:
        tile_name = f"tile_x{col}_y{row}"
        components: List[trimesh.Trimesh] = []

        terrain_mesh = drape_polygon_between(
            poly,
            sample_bottom=lambda x, y: 0.0,
            sample_top=terrain_sampler,
        )
        if len(terrain_mesh.faces) == 0:
            logger.error("Failed to drape terrain for %s", tile_name)
            raise RuntimeError(f"Terrain generation failed for {tile_name}")
        terrain_mesh.metadata["name"] = f"{tile_name}_terrain"
        terrain_mesh.metadata["part_role"] = "terrain"
        terrain_mesh.metadata["piece_group"] = tile_name
        components.append(terrain_mesh)

        if include_buildings and buildings_raw:
            b_mesh = build_buildings_mesh(
                buildings=buildings_raw,
                bbox=bbox,
                physical_size_mm=physical_size_mm,
                surface_sampler=terrain_sampler,
                clip_polygon=poly,
                model_mm_per_meter=mm_per_meter,
            )
            if len(b_mesh.faces) > 0:
                b_mesh.metadata["name"] = f"{tile_name}_buildings"
                b_mesh.metadata["part_role"] = "buildings"
                components.append(b_mesh)

        if include_roads and roads_raw:
            r_mesh = build_roads_mesh(
                roads=roads_raw,
                bbox=bbox,
                physical_size_mm=physical_size_mm,
                surface_sampler=terrain_sampler,
                clip_polygon=poly,
            )
            if len(r_mesh.faces) > 0:
                r_mesh.metadata["name"] = f"{tile_name}_roads"
                r_mesh.metadata["part_role"] = "roads"
                components.append(r_mesh)
                
        all_piece_groups.append(components)

    if not all_piece_groups:
        raise RuntimeError("No puzzle pieces were generated.")

    arranged, _ = arrange_pieces_for_printing(all_piece_groups, rows, columns, bed_size, gap=PRINT_GAP_MM)
    export_piece_groups_3mf(arranged, output_path=output_path, template_path=template_path)
    return Path(output_path)


def _parse_grid_size(grid_size: str) -> Tuple[int, int]:
    normalized = str(grid_size).lower().replace(" ", "")
    if "x" not in normalized:
        raise ValueError("grid_size must look like '5x5'.")
    rows, cols = normalized.split("x", 1)
    return int(rows), int(cols)


def generate_3mf_from_params(
    *,
    bbox: Tuple[float, float, float, float],
    physical_size: int,
    grid_size: str,
    z_scale: float,
    smooth_terrain: bool,
    flatten_sea_level: bool,
    include_buildings: bool = False,
    include_roads: bool = False,
    output_path: Path | str,
    template_path: Optional[Path | str] = "template.3mf",
    seed: Optional[int] = None,
    engine: str = "overlap",
    z_padding: float = 2.0,
    base_thickness: float = BASE_THICKNESS_MM,
    bed_size: float = 250.0,
    dem_px_width: int = DEM_REQUEST_WIDTH,
    dem_px_height: int = DEM_REQUEST_HEIGHT,
) -> Path:
    rows, cols = _parse_grid_size(grid_size)
    min_lat, min_lon, max_lat, max_lon = bbox
    return generate_puzzle_from_map(
        bbox=(min_lon, min_lat, max_lon, max_lat),
        physical_size_mm=float(physical_size),
        rows=rows,
        columns=cols,
        z_scale=z_scale,
        smooth_terrain=smooth_terrain,
        flatten_sea_level=flatten_sea_level,
        base_thickness_mm=base_thickness,
        output_path=output_path,
        template_path=template_path,
        seed=seed,
        engine=engine,
        z_padding=z_padding,
        bed_size=bed_size,
        dem_resolution=float(max(dem_px_width, dem_px_height)),
        include_buildings=include_buildings,
        include_roads=include_roads,
        vertical_exaggeration=z_scale,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a topographic puzzle 3MF.")
    parser.add_argument("--input-mesh", default=None, help="Existing merged 3MF/STL/OBJ mesh to cut into tiles.")
    parser.add_argument("--tiles-x", type=int, default=None, help="Tile count along X for input-mesh mode.")
    parser.add_argument("--tiles-y", type=int, default=None, help="Tile count along Y for input-mesh mode.")
    parser.add_argument("--size-mm", type=float, default=None, help="Overall XY size for input-mesh mode.")
    parser.add_argument("--tab-radius-mm", "--tab-radius", dest="tab_radius_mm", type=float, default=None, help="Jigsaw tab radius in mm. Defaults to 10% of tile edge.")
    parser.add_argument("--tab-depth-mm", "--tab-depth", dest="tab_depth_mm", type=float, default=None, help="Optional depth override. Defaults to R + (neck_length_ratio * R).")
    parser.add_argument("--neck-ratio", type=float, default=0.6, help="Neck width ratio relative to head diameter.")
    parser.add_argument("--neck-length-ratio", type=float, default=0.3, help="Neck length ratio relative to tab radius.")
    parser.add_argument("--edge-clearance-mm", type=float, default=0.0, help="Inset from tile corners before tabs can start.")
    parser.add_argument("--tab-noise-seed", type=int, default=0, help="Deterministic seed for tab placement.")
    parser.add_argument("--outer-margin-mm", type=float, default=None, help="Deprecated alias for edge-clearance-mm.")
    parser.add_argument("--boolean-engine", default="manifold", help="Boolean engine for mesh cutting.")
    parser.add_argument("--cutter-z-padding", type=float, default=2.0, help="Z padding for cutter extrusion.")
    parser.add_argument("--arrange-gap-mm", type=float, default=PRINT_GAP_MM, help="Gap between arranged output tiles.")
    parser.add_argument("--template", default="template.3mf", help="Template 3MF project used for slicer settings.")
    parser.add_argument("--bbox", required=False)
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--cols", type=int, default=None)
    parser.add_argument("--output", default="output_puzzle.3mf")
    parser.add_argument("--max-size", type=float, default=150.0)
    parser.add_argument("--base-thickness", type=float, default=BASE_THICKNESS_MM)
    parser.add_argument("--z-scale", type=float, default=VERTICAL_EXAGGERATION)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.input_mesh:
        tiles_x = args.tiles_x
        tiles_y = args.tiles_y
        if tiles_x is None or tiles_y is None:
            raise SystemExit("Pass --tiles-x and --tiles-y with --input-mesh.")
        size_mm = args.size_mm if args.size_mm is not None else float(args.max_size)
        cut_input_mesh_file_to_puzzle_3mf(
            input_mesh_path=args.input_mesh,
            output_path=args.output,
            tiles_x=int(tiles_x),
            tiles_y=int(tiles_y),
            size_mm=float(size_mm),
            tab_radius_mm=None if args.tab_radius_mm is None else float(args.tab_radius_mm),
            tab_depth_mm=None if args.tab_depth_mm is None else float(args.tab_depth_mm),
            neck_ratio=float(args.neck_ratio),
            neck_length_ratio=float(args.neck_length_ratio),
            edge_clearance_mm=float(args.edge_clearance_mm if args.outer_margin_mm is None else args.outer_margin_mm),
            tab_noise_seed=int(args.tab_noise_seed),
            boolean_engine=str(args.boolean_engine),
            cutter_z_padding_mm=float(args.cutter_z_padding),
            arrange_gap_mm=float(args.arrange_gap_mm),
            template_path=args.template,
        )
        return 0

    if not args.bbox:
        raise SystemExit("Pass --bbox west,south,east,north")
    west, south, east, north = [float(part) for part in str(args.bbox).split(",")]
    if args.rows is None or args.cols is None:
        raise SystemExit("Pass --rows and --cols for bbox generation mode.")
    generate_puzzle_from_map(
        bbox=(west, south, east, north),
        physical_size_mm=float(args.max_size),
        rows=int(args.rows),
        columns=int(args.cols),
        z_scale=float(args.z_scale),
        smooth_terrain=True,
        flatten_sea_level=True,
        base_thickness_mm=float(args.base_thickness),
        output_path=args.output,
        template_path=args.template,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
