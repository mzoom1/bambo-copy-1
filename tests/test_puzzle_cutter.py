import itertools
import tempfile
import zipfile
from pathlib import Path
import unittest

import numpy as np
import trimesh
from shapely.geometry import LineString, MultiPolygon, Polygon, box

import topomap_to_puzzle_3mf as m


def _translated_box(extents, min_corner):
    mesh = trimesh.creation.box(extents=extents)
    extents = np.asarray(extents, dtype=float)
    min_corner = np.asarray(min_corner, dtype=float)
    center = min_corner + (extents * 0.5)
    mesh.apply_translation(center)
    return mesh


def _boolean_union(meshes):
    result = trimesh.boolean.union(list(meshes), engine="manifold")
    if isinstance(result, trimesh.Scene):
        result = trimesh.util.concatenate(tuple(result.geometry.values()))
    return result


class PuzzleCutterTests(unittest.TestCase):
    def test_print_gap_default_is_five_mm(self):
        self.assertEqual(m.PRINT_GAP_MM, 5.0)

    def test_cut_map_into_puzzle_pieces_returns_named_tiles(self):
        map_mesh = _translated_box([120.0, 90.0, 12.0], [10.0, 20.0, 0.0])
        config = m.PuzzleConfig(tiles_x=3, tiles_y=2, tab_radius_mm=8.0, tab_depth_mm=4.8, tab_noise_seed=11)

        tiles = m.cut_map_into_puzzle_pieces(map_mesh, config)

        self.assertEqual(len(tiles), 6)
        self.assertEqual([tile.metadata["name"] for tile in tiles], [
            "tile_x0_y0",
            "tile_x1_y0",
            "tile_x2_y0",
            "tile_x0_y1",
            "tile_x1_y1",
            "tile_x2_y1",
        ])

    def test_tiles_reconstruct_source_volume_without_meaningful_overlap(self):
        map_mesh = _translated_box([140.0, 140.0, 18.0], [3.0, 7.0, 0.0])
        config = m.PuzzleConfig(tiles_x=2, tiles_y=2, tab_radius_mm=10.0, tab_depth_mm=6.0, tab_noise_seed=3)

        tiles = m.cut_map_into_puzzle_pieces(map_mesh, config)
        reconstructed = _boolean_union(tiles)

        self.assertLess(float(reconstructed.volume), float(map_mesh.volume))
        self.assertGreater(float(reconstructed.volume), float(map_mesh.volume) * 0.97)
        self.assertGreaterEqual(float(reconstructed.bounds[0][0]), float(map_mesh.bounds[0][0]) - 1e-3)
        self.assertLessEqual(float(reconstructed.bounds[1][0]), float(map_mesh.bounds[1][0]) + 1e-3)
        self.assertGreaterEqual(float(reconstructed.bounds[0][1]), float(map_mesh.bounds[0][1]) - 1e-3)
        self.assertLessEqual(float(reconstructed.bounds[1][1]), float(map_mesh.bounds[1][1]) + 1e-3)

        for left, right in itertools.combinations(tiles, 2):
            overlap = trimesh.boolean.intersection([left, right], engine="manifold")
            if overlap is None:
                continue
            if isinstance(overlap, trimesh.Scene):
                overlap = trimesh.util.concatenate(tuple(overlap.geometry.values()))
            if len(overlap.faces) == 0:
                continue
            self.assertLess(float(overlap.volume), 1e-4)

    def test_tile_bounds_stay_within_expected_xy_cell_plus_tab_allowance(self):
        map_mesh = _translated_box([160.0, 100.0, 10.0], [5.0, 8.0, 0.0])
        config = m.PuzzleConfig(tiles_x=4, tiles_y=2, tab_radius_mm=8.0, tab_depth_mm=4.8, tab_noise_seed=19)
        tiles = m.cut_map_into_puzzle_pieces(map_mesh, config)

        min_x, min_y, _, max_x, max_y, _ = map_mesh.bounds.reshape(-1)
        cell_w = (max_x - min_x) / config.tiles_x
        cell_h = (max_y - min_y) / config.tiles_y
        expected_radius, expected_depth, _, _, _ = config.resolved_tab_geometry(cell_w, cell_h)
        expected_allowance = expected_depth + expected_radius
        eps = 1e-3

        for tile in tiles:
            col = int(tile.metadata["tile_x"])
            row = int(tile.metadata["tile_y"])
            tile_min, tile_max = tile.bounds
            cell_min_x = min_x + (col * cell_w)
            cell_max_x = cell_min_x + cell_w
            cell_min_y = min_y + (row * cell_h)
            cell_max_y = cell_min_y + cell_h

            self.assertGreaterEqual(float(tile_min[0]), float(min_x) - eps)
            self.assertLessEqual(float(tile_max[0]), float(max_x) + eps)
            self.assertGreaterEqual(float(tile_min[1]), float(min_y) - eps)
            self.assertLessEqual(float(tile_max[1]), float(max_y) + eps)
            self.assertGreaterEqual(float(tile_min[0]), cell_min_x - expected_allowance - eps)
            self.assertLessEqual(float(tile_max[0]), cell_max_x + expected_allowance + eps)
            self.assertGreaterEqual(float(tile_min[1]), cell_min_y - expected_allowance - eps)
            self.assertLessEqual(float(tile_max[1]), cell_max_y + expected_allowance + eps)

    def test_rectangular_cutting_preserves_original_z_levels(self):
        base = _translated_box([100.0, 60.0, 4.0], [0.0, 0.0, 0.0])
        tower = _translated_box([40.0, 30.0, 8.0], [10.0, 15.0, 4.0])
        map_mesh = _boolean_union([base, tower])
        config = m.PuzzleConfig(tiles_x=2, tiles_y=1, tab_radius_mm=0.0, tab_depth_mm=0.0, tab_noise_seed=0)

        tiles = m.cut_map_into_puzzle_pieces(map_mesh, config)
        source_z_values = {round(float(z), 6) for z in np.asarray(map_mesh.vertices)[:, 2]}

        for tile in tiles:
            tile_z_values = {round(float(z), 6) for z in np.asarray(tile.vertices)[:, 2]}
            self.assertTrue(tile_z_values.issubset(source_z_values))

    def test_cut_input_mesh_file_to_puzzle_3mf_exports_tiles(self):
        source_scene = trimesh.Scene()
        source_scene.add_geometry(_translated_box([40.0, 40.0, 10.0], [0.0, 0.0, 0.0]), geom_name="map")

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "source.3mf"
            output_path = Path(tmpdir) / "out.3mf"
            source_scene.export(file_obj=str(input_path), file_type="3mf")

            result = m.cut_input_mesh_file_to_puzzle_3mf(
                input_mesh_path=input_path,
                output_path=output_path,
                tiles_x=2,
                tiles_y=2,
                size_mm=80.0,
                tab_radius_mm=4.0,
                tab_depth_mm=2.4,
                tab_noise_seed=7,
                edge_clearance_mm=0.0,
                boolean_engine="manifold",
            )

            self.assertEqual(result, output_path)
            self.assertTrue(output_path.exists())
            with zipfile.ZipFile(output_path, "r") as zf:
                model_name = next(name for name in zf.namelist() if name.endswith(".model"))
                xml = zf.read(model_name).decode("utf-8")

            self.assertEqual(xml.count("<item"), 4)
            self.assertIn('name="tile_x0_y0"', xml)
            self.assertIn('name="tile_x1_y1"', xml)

    def test_piece_outlines_apply_negative_clearance_before_cutting(self):
        map_bounds = np.array([[0.0, 0.0, 0.0], [100.0, 50.0, 12.0]], dtype=np.float64)
        config = m.PuzzleConfig(tiles_x=2, tiles_y=1, tab_radius_mm=0.0, tab_depth_mm=0.0, tab_noise_seed=0)

        outlines = m.build_puzzle_tile_outlines(map_bounds, config)

        self.assertEqual(len(outlines), 2)
        left = next(poly for row, col, poly in outlines if row == 0 and col == 0)
        right = next(poly for row, col, poly in outlines if row == 0 and col == 1)
        self.assertAlmostEqual(float(left.bounds[2]), 49.85, places=2)
        self.assertAlmostEqual(float(right.bounds[0]), 50.15, places=2)

    def test_tabs_stay_in_middle_forty_percent_of_edge(self):
        map_bounds = np.array([[0.0, 0.0, 0.0], [150.0, 150.0, 12.0]], dtype=np.float64)
        config = m.PuzzleConfig(
            tiles_x=3,
            tiles_y=3,
            tab_radius_mm=5.0,
            tab_depth_mm=None,
            edge_clearance_mm=2.0,
            tab_noise_seed=13,
        )
        outlines = m.build_puzzle_tile_outlines(map_bounds, config)
        by_rc = {(row, col): poly for row, col, poly in outlines}

        cell_w = 50.0
        cell_h = 50.0
        middle_min_x = 0.30 * cell_w
        middle_max_x = 0.70 * cell_w
        middle_min_y = 0.30 * cell_h
        middle_max_y = 0.70 * cell_h

        for row in range(3):
            boundary_x = 50.0
            left = by_rc[(row, 0)]
            cell_rect = box(0.0, row * cell_h, cell_w, (row + 1) * cell_h)
            protrusion = left.difference(cell_rect).intersection(
                box(boundary_x - 20.0, row * cell_h, boundary_x + 20.0, (row + 1) * cell_h)
            ).buffer(0)
            if protrusion.is_empty:
                continue
            bounds = protrusion.bounds
            self.assertGreaterEqual(float(bounds[1]) - (row * cell_h), middle_min_y - 0.25)
            self.assertLessEqual(float(bounds[3]) - (row * cell_h), middle_max_y + 0.25)
            self.assertGreater(float(bounds[0]), boundary_x - 0.25)

        for col in range(3):
            boundary_y = 50.0
            bottom = by_rc[(0, col)]
            cell_rect = box(col * cell_w, 0.0, (col + 1) * cell_w, cell_h)
            protrusion = bottom.difference(cell_rect).intersection(
                box(col * cell_w, boundary_y - 20.0, (col + 1) * cell_w, boundary_y + 20.0)
            ).buffer(0)
            if protrusion.is_empty:
                continue
            bounds = protrusion.bounds
            self.assertGreaterEqual(float(bounds[0]) - (col * cell_w), middle_min_x - 0.25)
            self.assertLessEqual(float(bounds[2]) - (col * cell_w), middle_max_x + 0.25)
            self.assertGreater(float(bounds[1]), boundary_y - 0.25)

    def test_tabs_do_not_intrude_into_four_way_junction_corner_boxes(self):
        map_bounds = np.array([[0.0, 0.0, 0.0], [150.0, 150.0, 10.0]], dtype=np.float64)
        config = m.PuzzleConfig(tiles_x=3, tiles_y=3, tab_radius_mm=5.0, tab_depth_mm=None, tab_noise_seed=3)
        outlines = m.build_puzzle_tile_outlines(map_bounds, config)

        junction_guard = box(45.0, 45.0, 55.0, 55.0)
        cell_w = 50.0
        cell_h = 50.0
        for row, col, poly in outlines:
            cell_rect = box(col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h).buffer(-0.15).buffer(0)
            intrusion = poly.symmetric_difference(cell_rect).intersection(junction_guard)
            self.assertTrue(intrusion.is_empty)


if __name__ == "__main__":
    unittest.main()
