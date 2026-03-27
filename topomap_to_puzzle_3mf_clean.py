#!/usr/bin/env python3
"""
Clean stable topographic puzzle exporter.

This script keeps the original working contract:
- load a single watertight or scene-based 3D input
- generate a stable 2D jigsaw grid in shapely
- apply mandatory -0.15 mm clearance to every piece
- extrude cutters and boolean-intersect them against the source mesh
- arrange pieces with a 5.0 mm gap on a flat virtual build plate
- export a single multi-part 3MF, optionally injecting a Bambu template
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import trimesh
import trimesh.interfaces.blender as trimesh_blender
from shapely.affinity import translate as shapely_translate
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import triangulate, unary_union

logger = logging.getLogger(__name__)

CORE_3MF_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
ET.register_namespace("", CORE_3MF_NS)

PRINT_GAP_MM = 5.0
MANDATORY_CLEARANCE_MM = 0.15


def _maybe_enable_local_blender() -> None:
    if trimesh_blender.exists and getattr(trimesh_blender, "_blender_executable", None):
        return
    candidates = [
        Path("/Users/eugenetoporkov/Desktop/Blender.app/Contents/MacOS/blender"),
        Path("/Applications/Blender.app/Contents/MacOS/blender"),
        Path("/Applications/blender.app/Contents/MacOS/blender"),
    ]
    for candidate in candidates:
        if candidate.exists():
            trimesh_blender._blender_executable = str(candidate)
            trimesh_blender.exists = True
            logger.info("Enabled Blender boolean backend at %s", candidate)
            return


_maybe_enable_local_blender()


@dataclass(frozen=True)
class PuzzleConfig:
    tiles_x: int
    tiles_y: int
    tab_radius_mm: Optional[float] = None
    tab_depth_mm: Optional[float] = None
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

    def resolved_tab_geometry(self, cell_w: float, cell_h: float) -> Tuple[float, float, float]:
        tile_edge = max(0.0, min(float(cell_w), float(cell_h)))
        if tile_edge <= 0.0:
            return 0.0, 0.0, 0.0
        radius = 0.10 * tile_edge if self.tab_radius_mm is None else float(self.tab_radius_mm)
        radius = min(max(0.0, radius), (0.5 * tile_edge) - 1e-3)
        depth = radius * 1.3 if self.tab_depth_mm is None else float(self.tab_depth_mm)
        depth = min(max(0.0, depth), 0.49 * tile_edge)
        clearance = min(max(0.0, float(self.edge_clearance_mm)), (0.5 * tile_edge) - radius - 1e-3)
        return radius, depth, clearance


def _validate_config(config: PuzzleConfig) -> PuzzleConfig:
    if config.tiles_x <= 0 or config.tiles_y <= 0:
        raise ValueError("tiles_x and tiles_y must be positive.")
    if config.tab_radius_mm is not None and float(config.tab_radius_mm) < 0.0:
        raise ValueError("tab_radius_mm must be >= 0 when provided.")
    if config.tab_depth_mm is not None and float(config.tab_depth_mm) < 0.0:
        raise ValueError("tab_depth_mm must be >= 0 when provided.")
    if float(config.edge_clearance_mm) < 0.0:
        raise ValueError("edge_clearance_mm must be >= 0.")
    if float(config.cutter_z_padding_mm) <= 0.0:
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
        meshes = [mesh for mesh in (_normalize_boolean_result(item) for item in result) if mesh is not None]
        if not meshes:
            return None
        return trimesh.util.concatenate(meshes)
    return None


def _cleanup_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    mesh = mesh.copy()
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


def _split_mesh_components(mesh: trimesh.Trimesh) -> List[trimesh.Trimesh]:
    parts = mesh.split(only_watertight=False)
    return [part.copy() for part in parts if len(part.faces) > 0]


def _sanitize_export_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    cleaned = _cleanup_mesh(mesh)
    if cleaned.is_watertight:
        return cleaned
    parts = [part for part in _split_mesh_components(cleaned) if part.is_watertight]
    if not parts:
        raise RuntimeError("Non-watertight mesh detected in piece groups.")
    return _cleanup_mesh(trimesh.util.concatenate(parts))


def _mesh_xml(parent: ET.Element, mesh: trimesh.Trimesh) -> None:
    mesh_elem = ET.SubElement(parent, f"{{{CORE_3MF_NS}}}mesh")
    vertices_elem = ET.SubElement(mesh_elem, f"{{{CORE_3MF_NS}}}vertices")
    triangles_elem = ET.SubElement(mesh_elem, f"{{{CORE_3MF_NS}}}triangles")
    for x, y, z in np.asarray(mesh.vertices, dtype=np.float64):
        ET.SubElement(
            vertices_elem,
            f"{{{CORE_3MF_NS}}}vertex",
            {"x": f"{float(x):.4f}", "y": f"{float(y):.4f}", "z": f"{float(z):.4f}"},
        )
    for a, b, c in np.asarray(mesh.faces, dtype=np.int64):
        ET.SubElement(
            triangles_elem,
            f"{{{CORE_3MF_NS}}}triangle",
            {"v1": str(int(a)), "v2": str(int(b)), "v3": str(int(c))},
        )


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


def load_input_mesh(input_mesh_path: Path | str, boolean_engine: str = "manifold") -> trimesh.Trimesh:
    loaded = trimesh.load(str(input_mesh_path), force="scene")
    if isinstance(loaded, trimesh.Scene):
        meshes = [mesh for mesh in _iter_scene_meshes(loaded) if len(mesh.faces) > 0]
        if not meshes:
            raise ValueError(f"No mesh geometry found in {input_mesh_path!s}.")
        if len(meshes) == 1:
            return _cleanup_mesh(meshes[0])
        engine = PuzzleConfig(tiles_x=1, tiles_y=1, boolean_engine=boolean_engine).normalized_boolean_engine()
        try:
            result = trimesh.boolean.union(meshes, engine=engine)
        except ValueError as exc:
            logger.warning("Scene union failed, falling back to concatenation: %s", exc)
            return _cleanup_mesh(trimesh.util.concatenate(meshes))
        mesh = _normalize_boolean_result(result)
        if mesh is None or len(mesh.faces) == 0:
            raise RuntimeError("Failed to merge input scene into a single mesh.")
        return _cleanup_mesh(mesh)
    if isinstance(loaded, trimesh.Trimesh):
        return _cleanup_mesh(loaded)
    raise TypeError(f"Unsupported mesh type: {type(loaded).__name__}")


def scale_mesh_to_target_xy_size(mesh: trimesh.Trimesh, size_mm: float) -> trimesh.Trimesh:
    if size_mm <= 0.0:
        raise ValueError("size_mm must be > 0.")
    current_xy = max(float(mesh.extents[0]), float(mesh.extents[1]))
    if current_xy <= 0.0:
        raise ValueError("Cannot scale mesh with non-positive XY extent.")
    factor = float(size_mm) / current_xy
    scaled = mesh.copy()
    scaled.apply_scale(factor)
    return _cleanup_mesh(scaled)


def _prepare_boolean_input_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    return _cleanup_mesh(mesh)


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
    edge_clearance_mm: float,
    rng: random.Random,
) -> Optional[Polygon]:
    del rng
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
    edge_clearance_mm: float,
    rng: random.Random,
) -> Optional[Polygon]:
    del rng
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
    config = _validate_config(config)
    min_x = float(map_bounds[0][0])
    min_y = float(map_bounds[0][1])
    max_x = float(map_bounds[1][0])
    max_y = float(map_bounds[1][1])
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0.0 or height <= 0.0:
        raise ValueError("Map bounds must have positive XY size.")

    cell_w = width / config.tiles_x
    cell_h = height / config.tiles_y
    radius, depth, edge_clearance = config.resolved_tab_geometry(cell_w, cell_h)

    vertical_specs: Dict[Tuple[int, int], Tuple[int, Optional[Polygon]]] = {}
    horizontal_specs: Dict[Tuple[int, int], Tuple[int, Optional[Polygon]]] = {}

    for col in range(config.tiles_x - 1):
        for row in range(config.tiles_y):
            rng = random.Random((int(config.tab_noise_seed) * 1_000_003) + (row * 101) + (col * 1009) + 17)
            direction = 1 if rng.random() >= 0.5 else -1
            x = min_x + ((col + 1) * cell_w)
            y0 = min_y + (row * cell_h)
            y1 = y0 + cell_h
            shape = _vertical_tab_shape(x, y0, y1, direction, radius, depth, edge_clearance, rng)
            vertical_specs[(row, col)] = (direction, shape)

    for row in range(config.tiles_y - 1):
        for col in range(config.tiles_x):
            rng = random.Random((int(config.tab_noise_seed) * 1_000_033) + (row * 10007) + (col * 137) + 29)
            direction = 1 if rng.random() >= 0.5 else -1
            y = min_y + ((row + 1) * cell_h)
            x0 = min_x + (col * cell_w)
            x1 = x0 + cell_w
            shape = _horizontal_tab_shape(y, x0, x1, direction, radius, depth, edge_clearance, rng)
            horizontal_specs[(row, col)] = (direction, shape)

    pieces: List[Tuple[int, int, Polygon]] = []
    clearance = float(MANDATORY_CLEARANCE_MM)
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
            poly = poly.buffer(-clearance).buffer(0)
            if poly.is_empty:
                raise RuntimeError(f"Puzzle clearance collapsed tile ({row}, {col}).")
            if isinstance(poly, MultiPolygon):
                poly = max(poly.geoms, key=lambda geom: geom.area)
            pieces.append((row, col, orient(poly, sign=1.0)))
    return pieces


def _triangles_for_polygon(poly: Polygon) -> List[Polygon]:
    clean = orient(poly.buffer(0), sign=1.0)
    tris: List[Polygon] = []
    for tri in triangulate(clean):
        if clean.covers(tri.representative_point()):
            tris.append(tri)
    return tris


def extrude_polygon_between(poly: Polygon, bottom_z: float, top_z: float) -> trimesh.Trimesh:
    clean = orient(poly.buffer(0), sign=1.0)
    if clean.is_empty or clean.area <= 1e-9 or top_z <= bottom_z:
        return trimesh.Trimesh()

    try:
        # Use trimesh's robust triangulation (mapbox-earcut) to get 2D faces
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

    # Side walls
    rings = [list(clean.exterior.coords)[:-1]]
    for interior in clean.interiors:
        rings.append(list(interior.coords)[:-1])

    for ring in rings:
        ring_closed = ring + [ring[0]]
        for i in range(len(ring)):
            p0 = ring_closed[i]
            p1 = ring_closed[i+1]
            base = len(verts_3d)
            # Add vertices specifically for walls to avoid smoothing/normal issues
            verts_3d.extend([
                [float(p0[0]), float(p0[1]), bz],
                [float(p1[0]), float(p1[1]), bz],
                [float(p1[0]), float(p1[1]), tz],
                [float(p0[0]), float(p0[1]), tz],
            ])
            # CCW winding looking from the outside:
            # bottom right, bottom left, top left, top right
            # Which maps to: p0_bottom, p1_bottom, p1_top, p0_top
            faces_3d.extend([
                [base, base + 1, base + 2],
                [base, base + 2, base + 3]
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


def _build_tile_cutter(piece_polygon: Polygon, map_mesh: trimesh.Trimesh, config: PuzzleConfig) -> trimesh.Trimesh:
    min_z = float(map_mesh.bounds[0][2]) - float(config.cutter_z_padding_mm)
    max_z = float(map_mesh.bounds[1][2]) + float(config.cutter_z_padding_mm)
    cutter = extrude_polygon_between(piece_polygon, min_z, max_z)
    if not cutter.is_watertight:
        raise RuntimeError("Tile cutter mask is not watertight.")
    return cutter


def cut_map_into_puzzle_pieces(map_mesh: trimesh.Trimesh, config: PuzzleConfig) -> List[trimesh.Trimesh]:
    config = _validate_config(config)
    if len(map_mesh.faces) == 0:
        raise ValueError("map_mesh is empty.")
    cut_mesh = _prepare_boolean_input_mesh(map_mesh)

    outlines = build_puzzle_tile_outlines(np.asarray(cut_mesh.bounds, dtype=np.float64), config)
    pieces: List[trimesh.Trimesh] = []
    engine = config.normalized_boolean_engine()
    check_volume = True
    if not cut_mesh.is_volume:
        if not trimesh_blender.exists:
            raise RuntimeError(
                "Input mesh is not a volume and Blender boolean backend is unavailable. "
                "Install Blender or provide a watertight mesh."
            )
        engine = "blender"
        check_volume = False

    for row, col, outline in outlines:
        cutter = _build_tile_cutter(outline, cut_mesh, config)
        tile_name = f"tile_x{col}_y{row}"
        result = trimesh.boolean.intersection([cut_mesh, cutter], engine=engine, check_volume=check_volume)
        tile_mesh = _normalize_boolean_result(result)
        if tile_mesh is None or len(tile_mesh.faces) == 0:
            raise RuntimeError(f"Boolean cut returned an empty tile: {tile_name}")
        tile_mesh = _cleanup_mesh(tile_mesh)
        tile_mesh.metadata["name"] = tile_name
        tile_mesh.metadata["tile_x"] = col
        tile_mesh.metadata["tile_y"] = row
        pieces.append(tile_mesh)

    if len(pieces) != config.tiles_x * config.tiles_y:
        raise RuntimeError(
            f"Failed to generate all puzzle tiles (expected {config.tiles_x * config.tiles_y}, got {len(pieces)})."
        )
    return pieces


def arrange_tiles_for_printing(tiles: Sequence[trimesh.Trimesh], config: PuzzleConfig) -> List[trimesh.Trimesh]:
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


def export_tiles_3mf(
    tiles: Sequence[trimesh.Trimesh],
    *,
    output_path: Path | str,
    template_path: Optional[Path | str] = "template.3mf",
) -> None:
    sanitized = [_sanitize_export_mesh(tile) for tile in tiles]
    for tile in sanitized:
        if len(tile.faces) == 0:
            raise RuntimeError("Cannot export empty tile mesh.")
        if not tile.is_watertight:
            raise RuntimeError("Non-watertight mesh detected in tile export.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    model_xml = _build_flat_tile_model_xml(sanitized)
    _write_3mf_with_optional_template(model_xml=model_xml, output_path=output, template_path=template_path)


def cut_input_mesh_file_to_puzzle_3mf(
    *,
    input_mesh_path: Path | str,
    output_path: Path | str,
    tiles_x: int,
    tiles_y: int,
    size_mm: float,
    tab_radius_mm: Optional[float] = None,
    tab_depth_mm: Optional[float] = None,
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
        edge_clearance_mm=float(edge_clearance_mm),
        tab_noise_seed=int(tab_noise_seed),
        boolean_engine=str(boolean_engine),
        cutter_z_padding_mm=float(cutter_z_padding_mm),
        arrange_gap_mm=float(arrange_gap_mm),
    )
    mesh = load_input_mesh(input_mesh_path, boolean_engine=config.normalized_boolean_engine())
    mesh = scale_mesh_to_target_xy_size(mesh, float(size_mm))
    tiles = cut_map_into_puzzle_pieces(mesh, config)
    arranged = arrange_tiles_for_printing(tiles, config)
    export_tiles_3mf(arranged, output_path=output_path, template_path=template_path)
    return Path(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a topographic puzzle 3MF.")
    parser.add_argument("--input-mesh", required=True, help="Input STL/OBJ/3MF to cut into puzzle tiles.")
    parser.add_argument("--tiles-x", type=int, required=True, help="Tile count along X.")
    parser.add_argument("--tiles-y", type=int, required=True, help="Tile count along Y.")
    parser.add_argument("--size-mm", type=float, default=200.0, help="Target XY size in millimeters.")
    parser.add_argument("--tab-radius-mm", type=float, default=None, help="Tab radius in mm.")
    parser.add_argument("--tab-depth-mm", type=float, default=None, help="Tab depth in mm.")
    parser.add_argument("--edge-clearance-mm", type=float, default=0.0, help="Extra edge clearance.")
    parser.add_argument("--tab-noise-seed", type=int, default=0, help="Deterministic seed for tab placement.")
    parser.add_argument("--boolean-engine", default="manifold", help="Boolean engine for mesh cutting.")
    parser.add_argument("--cutter-z-padding", type=float, default=2.0, help="Z padding for cutter extrusion.")
    parser.add_argument("--arrange-gap-mm", type=float, default=PRINT_GAP_MM, help="Gap between arranged output tiles.")
    parser.add_argument("--template", default="template.3mf", help="Template 3MF project used for slicer settings.")
    parser.add_argument("--output", default="output_puzzle.3mf", help="Output 3MF path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cut_input_mesh_file_to_puzzle_3mf(
        input_mesh_path=args.input_mesh,
        output_path=args.output,
        tiles_x=int(args.tiles_x),
        tiles_y=int(args.tiles_y),
        size_mm=float(args.size_mm),
        tab_radius_mm=args.tab_radius_mm,
        tab_depth_mm=args.tab_depth_mm,
        edge_clearance_mm=float(args.edge_clearance_mm),
        tab_noise_seed=int(args.tab_noise_seed),
        boolean_engine=str(args.boolean_engine),
        cutter_z_padding_mm=float(args.cutter_z_padding),
        arrange_gap_mm=float(args.arrange_gap_mm),
        template_path=args.template,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
