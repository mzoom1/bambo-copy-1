#!/usr/bin/env python3
"""
Cut a flat-bottomed 3D topographic map into interlocking jigsaw pieces and export
the result as one multipart 3MF file.

Design choices:
- Use `trimesh` for mesh loading, scaling, slicing, and boolean operations.
- Use `shapely` to procedurally generate the 2D puzzle layout.
- Keep the mandatory -0.15 mm clearance on every 2D piece.
- Scale the source mesh before generating the puzzle grid.
- Trim the bottom of the map so only `--base-thickness` remains below the lowest
  terrain vertex above the base.
- Generate classic jigsaw tabs with a narrow neck and wider head.
- Place the final pieces in one large grid with safe gaps and flat Z=0.
- Export a single 3MF, optionally replacing the model file inside a template 3MF.

This script intentionally avoids explicit multi-plate authoring. Open the exported
3MF in Bambu Studio and press `A` for Auto Arrange if you want the slicer to pack
the pieces onto plates.
"""

from __future__ import annotations

import argparse
import copy
import io
import logging
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import trimesh
import trimesh.interfaces.blender as trimesh_blender
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import triangulate, unary_union


LOG = logging.getLogger("topo_jigsaw_exporter")

CORE_3MF_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("", CORE_3MF_NS)

MANDATORY_CLEARANCE_MM = 0.15
DEFAULT_ARRANGE_GAP_MM = 10.0
DEFAULT_CUTTER_PADDING_MM = 4.0
DEFAULT_MAX_SIZE_MM = 150.0
DEFAULT_BASE_THICKNESS_MM = 2.0
DEFAULT_BOOLEAN_ENGINE = "manifold"
DEFAULT_CHAMFER_HEIGHT_MM = 0.2
DEFAULT_CHAMFER_INSET_MM = 0.2
DEFAULT_TEXT_DEPTH_MM = 0.5
DEFAULT_TEXT_WIDTH_MM = 15.0
TEXT_LABEL_SCALE_FALLBACK_MM = 8.0

TAB_HEAD_FRACTION = 0.24
TAB_NECK_FRACTION = 0.66
TAB_DEPTH_FRACTION = 0.22
TAB_CENTER_MIN_RATIO = 0.35
TAB_CENTER_MAX_RATIO = 0.65
TAB_CORNER_MARGIN_FRACTION = 0.20
TAB_MIN_HEAD_MM = 2.0

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
    "-": ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
}


@dataclass(frozen=True)
class Piece2D:
    row: int
    col: int
    polygon: Polygon


@dataclass(frozen=True)
class Piece3D:
    row: int
    col: int
    polygon: Polygon
    mesh: trimesh.Trimesh

    @property
    def label(self) -> str:
        return f"R{self.row + 1}-C{self.col + 1}"


@dataclass(frozen=True)
class PuzzleConfig:
    rows: int
    columns: int
    max_size_mm: float = DEFAULT_MAX_SIZE_MM
    base_thickness_mm: float = DEFAULT_BASE_THICKNESS_MM
    cutter_padding_mm: float = DEFAULT_CUTTER_PADDING_MM
    arrange_gap_mm: float = DEFAULT_ARRANGE_GAP_MM
    tab_seed: int = 0
    boolean_engine: str = DEFAULT_BOOLEAN_ENGINE
    chamfer_height_mm: float = DEFAULT_CHAMFER_HEIGHT_MM
    chamfer_inset_mm: float = DEFAULT_CHAMFER_INSET_MM
    text_depth_mm: float = DEFAULT_TEXT_DEPTH_MM
    text_width_mm: float = DEFAULT_TEXT_WIDTH_MM

    def normalized_boolean_engine(self) -> str:
        engine = str(self.boolean_engine or "").strip().lower()
        if engine in {"", "auto", "default", "overlap"}:
            return DEFAULT_BOOLEAN_ENGINE
        return engine


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(levelname)s: %(message)s",
    )


def _largest_polygon(geom: BaseGeometry) -> Polygon:
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda g: g.area)
    raise TypeError(f"Expected Polygon or MultiPolygon, got {type(geom).__name__}")


def _normalize_boolean_output(result: Any) -> Optional[trimesh.Trimesh]:
    if result is None:
        return None
    if isinstance(result, trimesh.Trimesh):
        return result
    if isinstance(result, trimesh.Scene):
        if not result.geometry:
            return None
        return trimesh.util.concatenate(tuple(result.geometry.values()))
    if isinstance(result, (list, tuple)):
        meshes = [mesh for mesh in (_normalize_boolean_output(item) for item in result) if mesh is not None]
        if not meshes:
            return None
        return trimesh.util.concatenate(meshes)
    return None


def _clean_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    cleaned = mesh.copy()
    if hasattr(cleaned, "merge_vertices"):
        cleaned.merge_vertices()
    if hasattr(cleaned, "remove_duplicate_faces"):
        cleaned.remove_duplicate_faces()
    if hasattr(cleaned, "remove_degenerate_faces"):
        cleaned.remove_degenerate_faces()
    cleaned.remove_unreferenced_vertices()
    try:
        cleaned.fix_normals()
    except Exception:  # noqa: BLE001
        pass
    return cleaned


def _iter_scene_meshes(scene: trimesh.Scene) -> List[trimesh.Trimesh]:
    meshes: List[trimesh.Trimesh] = []
    for node_name in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph.get(node_name)
        geom = scene.geometry.get(geom_name)
        if geom is None or len(geom.faces) == 0:
            continue
        mesh = geom.copy()
        mesh.apply_transform(transform)
        meshes.append(mesh)
    if meshes:
        return meshes
    return [geom.copy() for geom in scene.geometry.values() if len(geom.faces) > 0]


def load_input_mesh(path: Path | str) -> trimesh.Trimesh:
    input_path = Path(path)
    if input_path.suffix.lower() not in {".stl", ".obj", ".3mf"}:
        raise ValueError("Input file must be .stl, .obj, or .3mf")

    loaded = trimesh.load(str(input_path), force="scene")
    if isinstance(loaded, trimesh.Scene):
        meshes = _iter_scene_meshes(loaded)
        if not meshes:
            raise RuntimeError(f"No mesh geometry found in {input_path}")
        if len(meshes) == 1:
            return _clean_mesh(meshes[0])
        try:
            merged = trimesh.boolean.union(meshes, engine=DEFAULT_BOOLEAN_ENGINE)
            merged_mesh = _normalize_boolean_output(merged)
            if merged_mesh is not None and len(merged_mesh.faces) > 0:
                return _clean_mesh(merged_mesh)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Scene union failed, falling back to concatenation: %s", exc)
        watertight_meshes = [(name, geom.copy()) for name, geom in loaded.geometry.items() if getattr(geom, "is_watertight", False)]
        if watertight_meshes:
            preferred = next((geom for name, geom in watertight_meshes if str(name).lower() == "terrain"), None)
            if preferred is None:
                preferred = max((geom for _, geom in watertight_meshes), key=lambda g: float(g.volume) if g.is_volume else float(g.extents.prod()))
            LOG.warning(
                "Using watertight scene geometry '%s' as puzzle source because the full scene is not a single solid.",
                "terrain" if any(str(name).lower() == "terrain" for name, _ in watertight_meshes) else "largest watertight part",
            )
            return _clean_mesh(preferred)
        return _clean_mesh(trimesh.util.concatenate(meshes))

    if isinstance(loaded, trimesh.Trimesh):
        return _clean_mesh(loaded)

    raise RuntimeError(f"Unsupported mesh type: {type(loaded).__name__}")


def scale_mesh_to_max_xy(mesh: trimesh.Trimesh, max_size_mm: float) -> trimesh.Trimesh:
    if max_size_mm <= 0.0:
        raise ValueError("--max-size must be > 0")
    largest_xy = float(max(mesh.extents[0], mesh.extents[1]))
    if largest_xy <= 0.0:
        raise RuntimeError("Cannot scale mesh with non-positive XY extents.")
    scaled = mesh.copy()
    scaled.apply_scale(float(max_size_mm) / largest_xy)
    return _clean_mesh(scaled)


def _slice_mesh_above_z(mesh: trimesh.Trimesh, cut_z: float) -> trimesh.Trimesh:
    try:
        if hasattr(mesh, "slice_plane"):
            sliced = mesh.slice_plane(plane_origin=[0.0, 0.0, float(cut_z)], plane_normal=[0.0, 0.0, 1.0], cap=True)
        else:
            sliced = trimesh.intersections.slice_mesh_plane(
                mesh,
                plane_normal=[0.0, 0.0, 1.0],
                plane_origin=[0.0, 0.0, float(cut_z)],
                cap=True,
            )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to slice mesh at Z={cut_z:.3f}: {exc}") from exc
    sliced_mesh = _normalize_boolean_output(sliced)
    if sliced_mesh is None or len(sliced_mesh.faces) == 0:
        raise RuntimeError(f"Slicing produced an empty mesh at Z={cut_z:.3f}")
    return _clean_mesh(sliced_mesh)


def trim_bottom_to_base_thickness(mesh: trimesh.Trimesh, base_thickness_mm: float) -> trimesh.Trimesh:
    if base_thickness_mm <= 0.0:
        return mesh.copy()

    z_values = np.asarray(mesh.vertices, dtype=np.float64)[:, 2]
    base_bottom_z = float(np.min(z_values))
    terrain_candidates = z_values[z_values > (base_bottom_z + 1e-6)]
    terrain_min_z = float(np.min(terrain_candidates)) if terrain_candidates.size else base_bottom_z
    cut_z = terrain_min_z - float(base_thickness_mm)

    if cut_z <= base_bottom_z + 1e-6:
        return mesh.copy()

    trimmed = _slice_mesh_above_z(mesh, cut_z)
    trimmed.apply_translation([0.0, 0.0, -float(trimmed.bounds[0][2])])
    return _clean_mesh(trimmed)


def _edge_rng(seed: int, row: int, col: int, salt: int) -> random.Random:
    return random.Random((int(seed) * 1_000_003) + (row * 100_003) + (col * 1_009) + salt)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _tab_geometry(edge_len: float, rng: random.Random) -> Tuple[float, float, float, float]:
    if edge_len <= 0.0:
        return 0.0, 0.0, 0.0, 0.5

    head_width = _clamp(edge_len * TAB_HEAD_FRACTION, TAB_MIN_HEAD_MM, edge_len * 0.30)
    neck_width = head_width * TAB_NECK_FRACTION
    depth = _clamp(edge_len * TAB_DEPTH_FRACTION, head_width * 0.95, edge_len * 0.34)
    center_ratio = _clamp(0.5 + rng.uniform(-0.10, 0.10), TAB_CENTER_MIN_RATIO, TAB_CENTER_MAX_RATIO)
    return head_width, neck_width, depth, center_ratio


def _clip_tab_to_safe_corridor(
    tab: Polygon,
    *,
    axis_start: float,
    axis_end: float,
    fixed_min: float,
    fixed_max: float,
    edge_len: float,
) -> Optional[Polygon]:
    margin = edge_len * TAB_CORNER_MARGIN_FRACTION
    clipped = tab.intersection(box(axis_start, fixed_min + margin, axis_end, fixed_max - margin)).buffer(0)
    if clipped.is_empty:
        return None
    return _largest_polygon(clipped)


def _vertical_tab_shape(
    x_edge: float,
    y0: float,
    y1: float,
    direction: int,
    seed: int,
) -> Optional[Polygon]:
    edge_len = y1 - y0
    rng = _edge_rng(seed, int(round(y0 * 1000)), int(round(x_edge * 1000)), 17)
    head_width, neck_width, depth, center_ratio = _tab_geometry(edge_len, rng)
    if head_width <= 0.0 or neck_width <= 0.0 or depth <= 0.0:
        return None

    sign = 1.0 if direction >= 0 else -1.0
    center_y = y0 + (center_ratio * edge_len)
    neck_depth = depth * 0.42
    head_center_x = x_edge + (sign * (neck_depth + (head_width * 0.18)))

    neck = box(
        min(x_edge, x_edge + sign * neck_depth),
        center_y - (neck_width * 0.5),
        max(x_edge, x_edge + sign * neck_depth),
        center_y + (neck_width * 0.5),
    )
    head = Point(head_center_x, center_y).buffer(head_width * 0.5, resolution=28)
    tab = unary_union([neck, head]).buffer(0)
    if tab.is_empty:
        return None

    tab = _clip_tab_to_safe_corridor(
        _largest_polygon(tab),
        axis_start=min(x_edge, x_edge + sign * depth) - 0.01,
        axis_end=max(x_edge, x_edge + sign * depth) + 0.01,
        fixed_min=y0,
        fixed_max=y1,
        edge_len=edge_len,
    )
    if tab is None:
        return None
    return orient(tab, sign=1.0)


def _horizontal_tab_shape(
    y_edge: float,
    x0: float,
    x1: float,
    direction: int,
    seed: int,
) -> Optional[Polygon]:
    edge_len = x1 - x0
    rng = _edge_rng(seed, int(round(y_edge * 1000)), int(round(x0 * 1000)), 29)
    head_width, neck_width, depth, center_ratio = _tab_geometry(edge_len, rng)
    if head_width <= 0.0 or neck_width <= 0.0 or depth <= 0.0:
        return None

    sign = 1.0 if direction >= 0 else -1.0
    center_x = x0 + (center_ratio * edge_len)
    neck_depth = depth * 0.42
    head_center_y = y_edge + (sign * (neck_depth + (head_width * 0.18)))

    neck = box(
        center_x - (neck_width * 0.5),
        min(y_edge, y_edge + sign * neck_depth),
        center_x + (neck_width * 0.5),
        max(y_edge, y_edge + sign * neck_depth),
    )
    head = Point(center_x, head_center_y).buffer(head_width * 0.5, resolution=28)
    tab = unary_union([neck, head]).buffer(0)
    if tab.is_empty:
        return None

    tab = _clip_tab_to_safe_corridor(
        _largest_polygon(tab),
        axis_start=min(y_edge, y_edge + sign * depth) - 0.01,
        axis_end=max(y_edge, y_edge + sign * depth) + 0.01,
        fixed_min=x0,
        fixed_max=x1,
        edge_len=edge_len,
    )
    if tab is None:
        return None
    return orient(tab, sign=1.0)


def generate_piece_polygons(bounds_xy: np.ndarray, rows: int, columns: int, seed: int = 0) -> List[Piece2D]:
    if rows <= 0 or columns <= 0:
        raise ValueError("--rows and --columns must be > 0")

    min_x = float(bounds_xy[0][0])
    min_y = float(bounds_xy[0][1])
    max_x = float(bounds_xy[1][0])
    max_y = float(bounds_xy[1][1])
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0.0 or height <= 0.0:
        raise RuntimeError("Mesh XY bounds are invalid for puzzle generation.")

    cell_w = width / float(columns)
    cell_h = height / float(rows)

    vertical_specs: Dict[Tuple[int, int], int] = {}
    horizontal_specs: Dict[Tuple[int, int], int] = {}

    for row in range(rows):
        for col in range(columns - 1):
            rng = _edge_rng(seed, row, col, 11)
            vertical_specs[(row, col)] = 1 if rng.random() >= 0.5 else -1

    for row in range(rows - 1):
        for col in range(columns):
            rng = _edge_rng(seed, row, col, 23)
            horizontal_specs[(row, col)] = 1 if rng.random() >= 0.5 else -1

    pieces: List[Piece2D] = []
    for row in range(rows):
        for col in range(columns):
            x0 = min_x + (col * cell_w)
            x1 = x0 + cell_w
            y0 = min_y + (row * cell_h)
            y1 = y0 + cell_h
            poly: Polygon = box(x0, y0, x1, y1)

            if col < columns - 1:
                sign = vertical_specs[(row, col)]
                tab = _vertical_tab_shape(x1, y0, y1, sign, seed)
                if tab is not None:
                    poly = poly.union(tab).buffer(0) if sign > 0 else poly.difference(tab).buffer(0)

            if col > 0:
                sign = vertical_specs[(row, col - 1)]
                tab = _vertical_tab_shape(x0, y0, y1, sign, seed)
                if tab is not None:
                    poly = poly.difference(tab).buffer(0) if sign > 0 else poly.union(tab).buffer(0)

            if row < rows - 1:
                sign = horizontal_specs[(row, col)]
                tab = _horizontal_tab_shape(y1, x0, x1, sign, seed)
                if tab is not None:
                    poly = poly.union(tab).buffer(0) if sign > 0 else poly.difference(tab).buffer(0)

            if row > 0:
                sign = horizontal_specs[(row - 1, col)]
                tab = _horizontal_tab_shape(y0, x0, x1, sign, seed)
                if tab is not None:
                    poly = poly.difference(tab).buffer(0) if sign > 0 else poly.union(tab).buffer(0)

            poly = poly.buffer(-MANDATORY_CLEARANCE_MM, join_style=1).buffer(0)
            if poly.is_empty:
                raise RuntimeError(f"Puzzle clearance collapsed tile ({row}, {col}).")
            poly = _largest_polygon(poly)
            pieces.append(Piece2D(row=row, col=col, polygon=orient(poly, sign=1.0)))

    return pieces


def _triangles_for_polygon(poly: Polygon) -> List[Polygon]:
    clean = orient(poly.buffer(0), sign=1.0)
    triangles: List[Polygon] = []
    for tri in triangulate(clean):
        if clean.covers(tri.representative_point()):
            triangles.append(tri)
    return triangles


def extrude_polygon_between(poly: Polygon, bottom_z: float, top_z: float) -> trimesh.Trimesh:
    clean = orient(poly.buffer(0), sign=1.0)
    if clean.is_empty or clean.area <= 1e-9 or top_z <= bottom_z:
        return trimesh.Trimesh()

    try:
        # Use trimesh's robust triangulation and extrusion which handles complex and concave polygons properly.
        # It leverages mapbox-earcut or other robust engines under the hood.
        mesh = trimesh.creation.extrude_polygon(clean, float(top_z - bottom_z))
        # trimesh extrudes starting from z=0 up to the specified height
        mesh.apply_translation([0.0, 0.0, float(bottom_z)])
        return _clean_mesh(mesh)
    except Exception as exc:
        LOG.warning("trimesh.creation.extrude_polygon failed, falling back to manual: %s", exc)

    # Fallback to manual triangulation if trimesh fails (less likely to handle all concave shapes correctly)
    vertices: List[List[float]] = []
    faces: List[List[int]] = []

    for tri in _triangles_for_polygon(clean):
        coords = list(tri.exterior.coords)[:-1]

        top_base = len(vertices)
        for x, y in coords:
            vertices.append([float(x), float(y), float(top_z)])
        faces.append([top_base, top_base + 1, top_base + 2])

        bottom_base = len(vertices)
        for x, y in coords:
            vertices.append([float(x), float(y), float(bottom_z)])
        faces.append([bottom_base, bottom_base + 2, bottom_base + 1])

    def add_ring(coords: Sequence[Tuple[float, float]]) -> None:
        ring = list(coords)
        if len(ring) < 2:
            return
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        for start, end in zip(ring, ring[1:]):
            x0, y0 = start
            x1, y1 = end
            base = len(vertices)
            vertices.extend(
                [
                    [float(x0), float(y0), float(bottom_z)],
                    [float(x1), float(y1), float(bottom_z)],
                    [float(x1), float(y1), float(top_z)],
                    [float(x0), float(y0), float(top_z)],
                ]
            )
            faces.append([base, base + 1, base + 2])
            faces.append([base, base + 2, base + 3])

    add_ring(list(clean.exterior.coords))
    for ring in clean.interiors:
        add_ring(list(ring.coords))

    return _clean_mesh(
        trimesh.Trimesh(
            vertices=np.asarray(vertices, dtype=np.float64),
            faces=np.asarray(faces, dtype=np.int64),
            process=False,
        )
    )


def _build_tile_cutter(piece_polygon: Polygon, mesh: trimesh.Trimesh, padding_mm: float) -> trimesh.Trimesh:
    z_min = float(mesh.bounds[0][2]) - float(padding_mm)
    z_max = float(mesh.bounds[1][2]) + float(padding_mm)
    cutter = extrude_polygon_between(piece_polygon, z_min, z_max)
    cutter = _clean_mesh(cutter)
    if len(cutter.faces) == 0 or not cutter.is_watertight:
        raise RuntimeError("Tile cutter mesh is not watertight.")
    return cutter


def _boolean_intersection(meshes: Sequence[trimesh.Trimesh], engine: str) -> Optional[trimesh.Trimesh]:
    try:
        result = trimesh.boolean.intersection(list(meshes), engine=engine, check_volume=False)
    except Exception as exc:  # noqa: BLE001
        if engine != "blender" and getattr(trimesh_blender, "exists", False):
            LOG.warning("Intersection with %s failed, retrying with blender: %s", engine, exc)
            result = trimesh.boolean.intersection(list(meshes), engine="blender", check_volume=False)
        else:
            raise RuntimeError(f"Boolean intersection failed: {exc}") from exc
    return _normalize_boolean_output(result)


def _boolean_difference(meshes: Sequence[trimesh.Trimesh], engine: str) -> Optional[trimesh.Trimesh]:
    try:
        result = trimesh.boolean.difference(list(meshes), engine=engine, check_volume=False)
    except Exception as exc:  # noqa: BLE001
        if engine != "blender" and getattr(trimesh_blender, "exists", False):
            LOG.warning("Difference with %s failed, retrying with blender: %s", engine, exc)
            result = trimesh.boolean.difference(list(meshes), engine="blender", check_volume=False)
        else:
            raise RuntimeError(f"Boolean difference failed: {exc}") from exc
    return _normalize_boolean_output(result)


def _boolean_union(meshes: Sequence[trimesh.Trimesh], engine: str) -> Optional[trimesh.Trimesh]:
    try:
        result = trimesh.boolean.union(list(meshes), engine=engine, check_volume=False)
    except Exception as exc:  # noqa: BLE001
        if engine != "blender" and getattr(trimesh_blender, "exists", False):
            LOG.warning("Union with %s failed, retrying with blender: %s", engine, exc)
            result = trimesh.boolean.union(list(meshes), engine="blender", check_volume=False)
        else:
            raise RuntimeError(f"Boolean union failed: {exc}") from exc
    return _normalize_boolean_output(result)


def _piece_label_mesh(label: str, target_width_mm: float, depth_mm: float) -> trimesh.Trimesh:
    def bitmap_character(ch: str, x_offset: float) -> List[Polygon]:
        glyph = BITMAP_GLYPHS.get(ch.upper())
        if glyph is None:
            glyph = BITMAP_GLYPHS["-"]
        cell = 1.0
        polys: List[Polygon] = []
        for row_idx, row in enumerate(glyph):
            for col_idx, bit in enumerate(row):
                if bit != "1":
                    continue
                x0 = x_offset + (col_idx * cell)
                y0 = -(row_idx * cell)
                polys.append(box(x0, y0 - cell, x0 + cell, y0))
        return polys

    try:
        text = getattr(trimesh.creation, "text_3d", None)
        if text is not None:
            mesh = text(text=label, depth=float(depth_mm))
            if mesh is not None and len(mesh.faces) > 0:
                mesh = _clean_mesh(mesh)
                width = float(mesh.extents[0])
                if width > 1e-6:
                    mesh.apply_scale(float(target_width_mm) / width)
                    return _clean_mesh(mesh)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("text_3d unavailable, using bitmap label fallback: %s", exc)

    cursor_x = 0.0
    glyph_spacing = 1.0
    char_gap = 1.0
    polys: List[Polygon] = []
    for ch in label:
        glyph = BITMAP_GLYPHS.get(ch.upper())
        if glyph is None:
            glyph = BITMAP_GLYPHS["-"]
        char_width = float(len(glyph[0]))
        polys.extend(bitmap_character(ch, cursor_x))
        cursor_x += char_width + char_gap

    if not polys:
        raise RuntimeError(f"Text mesh was empty for '{label}'")

    label_poly = unary_union(polys).buffer(0)
    if label_poly.is_empty:
        raise RuntimeError(f"Bitmap label polygon was empty for '{label}'")
    if isinstance(label_poly, MultiPolygon):
        label_poly = _largest_polygon(label_poly)

    label_mesh = extrude_polygon_between(orient(label_poly, sign=1.0), 0.0, float(depth_mm))
    width = float(label_mesh.extents[0])
    if width <= 1e-6:
        raise RuntimeError(f"Bitmap text mesh has invalid width for '{label}'")
    label_mesh.apply_scale(float(target_width_mm) / width)
    return _clean_mesh(label_mesh)


def apply_bottom_chamfer(piece: trimesh.Trimesh, footprint: Polygon, config: PuzzleConfig) -> trimesh.Trimesh:
    chamfer_height = max(0.0, float(config.chamfer_height_mm))
    chamfer_inset = max(0.0, float(config.chamfer_inset_mm))
    if chamfer_height <= 0.0 or chamfer_inset <= 0.0:
        return piece.copy()

    inset_poly = footprint.buffer(-chamfer_inset).buffer(0)
    if inset_poly.is_empty:
        return piece.copy()
    if isinstance(inset_poly, MultiPolygon):
        inset_poly = _largest_polygon(inset_poly)

    lower = extrude_polygon_between(inset_poly, 0.0, chamfer_height + 0.01)
    upper = _slice_mesh_above_z(piece, max(0.0, chamfer_height - 0.01))

    try:
        united = _boolean_union([lower, upper], config.normalized_boolean_engine())
        if united is None or len(united.faces) == 0:
            return piece.copy()
        return _clean_mesh(united)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Bottom chamfer failed, keeping original piece: %s", exc)
        return piece.copy()


def deboss_piece_label(piece: trimesh.Trimesh, label: str, config: PuzzleConfig) -> trimesh.Trimesh:
    piece = piece.copy()
    piece.apply_translation([0.0, 0.0, -float(piece.bounds[0][2])])

    piece_width = float(piece.extents[0])
    piece_height = float(piece.extents[1])
    target_width = min(
        float(config.text_width_mm),
        max(TEXT_LABEL_SCALE_FALLBACK_MM, min(piece_width, piece_height) * 0.72),
    )

    text_mesh = _piece_label_mesh(label, target_width_mm=target_width, depth_mm=float(config.text_depth_mm))
    text_bounds = text_mesh.bounds
    piece_bounds = piece.bounds
    piece_center_xy = (piece_bounds[0, :2] + piece_bounds[1, :2]) * 0.5
    text_center_xy = (text_bounds[0, :2] + text_bounds[1, :2]) * 0.5
    text_mesh.apply_translation(
        [
            float(piece_center_xy[0] - text_center_xy[0]),
            float(piece_center_xy[1] - text_center_xy[1]),
            float(-text_bounds[0][2]),
        ]
    )

    try:
        cut = _boolean_difference([piece, text_mesh], config.normalized_boolean_engine())
        if cut is None or len(cut.faces) == 0:
            return piece
        cut.apply_translation([0.0, 0.0, -float(cut.bounds[0][2])])
        return _clean_mesh(cut)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Deboss text failed for %s, keeping original piece: %s", label, exc)
        return piece


def cut_map_into_puzzle_pieces(map_mesh: trimesh.Trimesh, config: PuzzleConfig) -> List[Piece3D]:
    if len(map_mesh.faces) == 0:
        raise ValueError("map mesh is empty.")

    if not map_mesh.is_volume:
        if not getattr(trimesh_blender, "exists", False):
            raise RuntimeError(
                "Input mesh is not watertight and Blender boolean backend is unavailable. "
                "Install Blender or provide a watertight mesh."
            )

    bounds = np.asarray(map_mesh.bounds, dtype=np.float64)
    pieces_2d = generate_piece_polygons(bounds[:, :2], rows=config.rows, columns=config.columns, seed=config.tab_seed)
    engine = config.normalized_boolean_engine()
    pieces: List[Piece3D] = []

    for piece_2d in pieces_2d:
        cutter = _build_tile_cutter(piece_2d.polygon, map_mesh, config.cutter_padding_mm)
        result = _boolean_intersection([map_mesh, cutter], engine=engine)
        if result is None or len(result.faces) == 0:
            raise RuntimeError(f"Boolean cut returned an empty tile: R{piece_2d.row + 1}-C{piece_2d.col + 1}")

        result = _clean_mesh(result)
        result.apply_translation([0.0, 0.0, -float(result.bounds[0][2])])
        result = apply_bottom_chamfer(result, piece_2d.polygon, config)
        result = deboss_piece_label(result, f"R{piece_2d.row + 1}-C{piece_2d.col + 1}", config)
        result.apply_translation([0.0, 0.0, -float(result.bounds[0][2])])
        result = _clean_mesh(result)

        if len(result.faces) == 0:
            raise RuntimeError(f"Final piece mesh is empty: R{piece_2d.row + 1}-C{piece_2d.col + 1}")

        result.metadata["name"] = f"R{piece_2d.row + 1}-C{piece_2d.col + 1}"
        result.metadata["row"] = piece_2d.row
        result.metadata["col"] = piece_2d.col
        pieces.append(Piece3D(row=piece_2d.row, col=piece_2d.col, polygon=piece_2d.polygon, mesh=result))

    if len(pieces) != config.rows * config.columns:
        raise RuntimeError(
            f"Failed to generate all puzzle pieces (expected {config.rows * config.columns}, got {len(pieces)})."
        )

    return pieces


def arrange_pieces_for_printing(
    pieces: Sequence[Piece3D],
    rows: int,
    columns: int,
    gap_mm: float = DEFAULT_ARRANGE_GAP_MM,
) -> List[Piece3D]:
    if rows <= 0 or columns <= 0:
        raise ValueError("rows and columns must be positive")
    if len(pieces) != rows * columns:
        raise RuntimeError("Piece count mismatch during arrangement.")

    lookup: Dict[Tuple[int, int], Piece3D] = {(piece.row, piece.col): piece for piece in pieces}
    column_widths: List[float] = [0.0 for _ in range(columns)]
    row_heights: List[float] = [0.0 for _ in range(rows)]

    for piece in pieces:
        column_widths[piece.col] = max(column_widths[piece.col], float(piece.mesh.extents[0]))
        row_heights[piece.row] = max(row_heights[piece.row], float(piece.mesh.extents[1]))

    x_offsets: List[float] = [0.0]
    for col in range(1, columns):
        x_offsets.append(x_offsets[-1] + column_widths[col - 1] + float(gap_mm))

    y_offsets: List[float] = [0.0]
    for row in range(1, rows):
        y_offsets.append(y_offsets[-1] + row_heights[row - 1] + float(gap_mm))

    total_width = sum(column_widths) + (float(gap_mm) * (columns - 1))
    total_height = sum(row_heights) + (float(gap_mm) * (rows - 1))
    center_shift_x = -0.5 * total_width
    center_shift_y = -0.5 * total_height

    arranged: List[Piece3D] = []
    for row in range(rows):
        for col in range(columns):
            piece = lookup[(row, col)]
            mesh = piece.mesh.copy()
            bounds = mesh.bounds
            tx = center_shift_x + x_offsets[col] - float(bounds[0][0])
            ty = center_shift_y + y_offsets[row] - float(bounds[0][1])
            tz = -float(bounds[0][2])
            mesh.apply_translation([tx, ty, tz])
            mesh = _clean_mesh(mesh)
            arranged.append(Piece3D(row=piece.row, col=piece.col, polygon=piece.polygon, mesh=mesh))

    return arranged


def _mesh_to_xml(parent: ET.Element, mesh: trimesh.Trimesh) -> None:
    mesh_elem = ET.SubElement(parent, f"{{{CORE_3MF_NS}}}mesh")
    vertices_elem = ET.SubElement(mesh_elem, f"{{{CORE_3MF_NS}}}vertices")
    triangles_elem = ET.SubElement(mesh_elem, f"{{{CORE_3MF_NS}}}triangles")

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)

    for x, y, z in vertices:
        ET.SubElement(
            vertices_elem,
            f"{{{CORE_3MF_NS}}}vertex",
            {"x": f"{float(x):.4f}", "y": f"{float(y):.4f}", "z": f"{float(z):.4f}"},
        )

    for v1, v2, v3 in faces:
        ET.SubElement(
            triangles_elem,
            f"{{{CORE_3MF_NS}}}triangle",
            {"v1": str(int(v1)), "v2": str(int(v2)), "v3": str(int(v3))},
        )


def _build_model_xml(pieces: Sequence[Piece3D], template_model_xml: Optional[bytes] = None) -> bytes:
    if template_model_xml is None:
        root = ET.Element(f"{{{CORE_3MF_NS}}}model", {"unit": "millimeter"})
    else:
        template_root = ET.fromstring(template_model_xml)
        root = ET.Element(template_root.tag, dict(template_root.attrib))
        if "unit" not in root.attrib:
            root.attrib["unit"] = "millimeter"
        for child in list(template_root):
            local_name = child.tag.split("}")[-1]
            if local_name in {"resources", "build"}:
                continue
            root.append(copy.deepcopy(child))

    resources = ET.SubElement(root, f"{{{CORE_3MF_NS}}}resources")
    build = ET.SubElement(root, f"{{{CORE_3MF_NS}}}build")

    for object_id, piece in enumerate(pieces, start=1):
        obj = ET.SubElement(
            resources,
            f"{{{CORE_3MF_NS}}}object",
            {
                "id": str(object_id),
                "type": "model",
                "name": piece.label,
            },
        )
        _mesh_to_xml(obj, piece.mesh)
        ET.SubElement(build, f"{{{CORE_3MF_NS}}}item", {"objectid": str(object_id)})

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _find_template_model_target(template_zip: ZipFile) -> str:
    try:
        rels_xml = template_zip.read("_rels/.rels")
    except KeyError:
        return "3D/3dmodel.model"

    root = ET.fromstring(rels_xml)
    for rel in root.findall(f"{{{REL_NS}}}Relationship"):
        if rel.attrib.get("Type", "").endswith("/3dmodel"):
            return rel.attrib.get("Target", "3D/3dmodel.model").lstrip("/")
    return "3D/3dmodel.model"


def _extract_model_xml_from_3mf(payload_3mf: bytes) -> bytes:
    with ZipFile(io.BytesIO(payload_3mf), "r") as zf:
        model_candidates = [name for name in zf.namelist() if name.lower().startswith("3d/") and name.lower().endswith(".model")]
        if not model_candidates:
            raise RuntimeError("Generated 3MF contains no 3D model payload.")
        return zf.read(model_candidates[0])


def _read_template_model_xml(template_path: Path) -> Optional[bytes]:
    if not template_path.exists():
        return None
    with ZipFile(template_path, "r") as zf:
        target_model_path = _find_template_model_target(zf)
        try:
            return zf.read(target_model_path)
        except KeyError:
            return None


def _write_fresh_3mf_package(model_xml: bytes, output_path: Path) -> None:
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" Target="/3D/3dmodel.model"/>
</Relationships>""",
        )
        zf.writestr("3D/3dmodel.model", model_xml)


def _write_3mf_package_from_template(model_xml: bytes, output_path: Path, template_path: Optional[Path]) -> None:
    if template_path is None or not template_path.exists():
        _write_fresh_3mf_package(model_xml, output_path)
        return

    with ZipFile(template_path, "r") as src, ZipFile(output_path, "w", compression=ZIP_DEFLATED) as dst:
        target_model_path = _find_template_model_target(src)
        for name in src.namelist():
            if name.lower().startswith("3d/") and name.lower().endswith(".model"):
                continue
            dst.writestr(name, src.read(name))
        dst.writestr(target_model_path, model_xml)


def export_3mf(pieces: Sequence[Piece3D], output_path: Path | str, template_path: Optional[Path | str]) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    template_model_xml: Optional[bytes] = None
    template: Optional[Path] = None
    if template_path is not None:
        template = Path(template_path)
        template_model_xml = _read_template_model_xml(template)

    payload_model_xml = _build_model_xml(pieces, template_model_xml=template_model_xml)
    if template is None:
        _write_fresh_3mf_package(payload_model_xml, output)
        return

    if not template.exists():
        LOG.warning("Template not found at %s, exporting a fresh 3MF instead.", template)
        _write_fresh_3mf_package(payload_model_xml, output)
        return

    # Preserve the template package and replace only the model payload.
    _write_3mf_package_from_template(payload_model_xml, output, template)


def cut_input_mesh_file_to_puzzle_3mf(
    *,
    input_mesh_path: Path | str,
    output_path: Path | str,
    rows: int,
    columns: int,
    max_size_mm: float = DEFAULT_MAX_SIZE_MM,
    base_thickness_mm: float = DEFAULT_BASE_THICKNESS_MM,
    tab_seed: int = 0,
    boolean_engine: str = DEFAULT_BOOLEAN_ENGINE,
    cutter_padding_mm: float = DEFAULT_CUTTER_PADDING_MM,
    arrange_gap_mm: float = DEFAULT_ARRANGE_GAP_MM,
    template_path: Optional[Path | str] = "template.3mf",
    chamfer_height_mm: float = DEFAULT_CHAMFER_HEIGHT_MM,
    chamfer_inset_mm: float = DEFAULT_CHAMFER_INSET_MM,
    text_depth_mm: float = DEFAULT_TEXT_DEPTH_MM,
    text_width_mm: float = DEFAULT_TEXT_WIDTH_MM,
) -> Path:
    config = PuzzleConfig(
        rows=int(rows),
        columns=int(columns),
        max_size_mm=float(max_size_mm),
        base_thickness_mm=float(base_thickness_mm),
        cutter_padding_mm=float(cutter_padding_mm),
        arrange_gap_mm=float(arrange_gap_mm),
        tab_seed=int(tab_seed),
        boolean_engine=str(boolean_engine),
        chamfer_height_mm=float(chamfer_height_mm),
        chamfer_inset_mm=float(chamfer_inset_mm),
        text_depth_mm=float(text_depth_mm),
        text_width_mm=float(text_width_mm),
    )

    mesh = load_input_mesh(input_mesh_path)
    mesh = scale_mesh_to_max_xy(mesh, config.max_size_mm)
    mesh = trim_bottom_to_base_thickness(mesh, config.base_thickness_mm)

    pieces = cut_map_into_puzzle_pieces(mesh, config)
    arranged = arrange_pieces_for_printing(pieces, rows=config.rows, columns=config.columns, gap_mm=config.arrange_gap_mm)
    export_3mf(arranged, output_path=output_path, template_path=template_path)
    return Path(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cut a 3D topographic map into interlocking jigsaw pieces and export one 3MF."
    )
    parser.add_argument("input_mesh", help="Input mesh path (.stl, .obj, or .3mf)")
    parser.add_argument("--rows", type=int, required=True, help="Number of puzzle rows")
    parser.add_argument("--columns", type=int, required=True, help="Number of puzzle columns")
    parser.add_argument("--max-size", type=float, default=DEFAULT_MAX_SIZE_MM, help="Largest XY dimension in millimeters")
    parser.add_argument(
        "--base-thickness",
        type=float,
        default=DEFAULT_BASE_THICKNESS_MM,
        help="Keep this much solid base below the lowest terrain vertex",
    )
    parser.add_argument("--tab-seed", type=int, default=0, help="Deterministic seed for tab placement")
    parser.add_argument("--boolean-engine", default=DEFAULT_BOOLEAN_ENGINE, help="Boolean engine for trimesh")
    parser.add_argument("--cutter-padding", type=float, default=DEFAULT_CUTTER_PADDING_MM, help="Z padding for cutter extrusion")
    parser.add_argument("--arrange-gap", type=float, default=DEFAULT_ARRANGE_GAP_MM, help="Gap between arranged pieces")
    parser.add_argument("--template", type=str, default="template.3mf", help="Optional Bambu Studio template .3mf")
    parser.add_argument("--output", type=str, default="output_puzzle.3mf", help="Output 3MF path")
    parser.add_argument("--chamfer-height", type=float, default=DEFAULT_CHAMFER_HEIGHT_MM, help="Bottom chamfer height in mm")
    parser.add_argument("--chamfer-inset", type=float, default=DEFAULT_CHAMFER_INSET_MM, help="Bottom chamfer inset in mm")
    parser.add_argument("--text-depth", type=float, default=DEFAULT_TEXT_DEPTH_MM, help="Deboss text depth in mm")
    parser.add_argument("--text-width", type=float, default=DEFAULT_TEXT_WIDTH_MM, help="Approximate text width in mm")
    parser.add_argument("--log-level", type=str, default="INFO", help="DEBUG/INFO/WARNING/ERROR")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _configure_logging(args.log_level)

    input_path = Path(args.input_mesh).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    template_path = Path(args.template).expanduser().resolve() if args.template else None

    LOG.info("Loading mesh: %s", input_path)
    mesh = load_input_mesh(input_path)
    LOG.info("Scaling to max XY size %.3f mm", float(args.max_size))
    mesh = scale_mesh_to_max_xy(mesh, float(args.max_size))
    LOG.info("Trimming base to %.3f mm below the lowest terrain point", float(args.base_thickness))
    mesh = trim_bottom_to_base_thickness(mesh, float(args.base_thickness))

    config = PuzzleConfig(
        rows=int(args.rows),
        columns=int(args.columns),
        max_size_mm=float(args.max_size),
        base_thickness_mm=float(args.base_thickness),
        cutter_padding_mm=float(args.cutter_padding),
        arrange_gap_mm=float(args.arrange_gap),
        tab_seed=int(args.tab_seed),
        boolean_engine=str(args.boolean_engine),
        chamfer_height_mm=float(args.chamfer_height),
        chamfer_inset_mm=float(args.chamfer_inset),
        text_depth_mm=float(args.text_depth),
        text_width_mm=float(args.text_width),
    )

    LOG.info("Generating %dx%d jigsaw layout", config.rows, config.columns)
    pieces = cut_map_into_puzzle_pieces(mesh, config)

    LOG.info("Arranging pieces with %.1f mm gap", config.arrange_gap_mm)
    arranged = arrange_pieces_for_printing(pieces, rows=config.rows, columns=config.columns, gap_mm=config.arrange_gap_mm)

    LOG.info("Exporting 3MF: %s", output_path)
    export_3mf(arranged, output_path=output_path, template_path=template_path)
    LOG.info("Done. Exported %d puzzle pieces.", len(arranged))
    LOG.info("Open the 3MF in Bambu Studio and press 'A' to Auto Arrange if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
