import unittest

import numpy as np

import topomap_to_puzzle_3mf as m


class TopomapGeometryTests(unittest.TestCase):
    def test_build_terrain_mesh_from_dem_is_watertight(self):
        dem = np.array(
            [
                [100.0, 110.0],
                [200.0, 210.0],
            ],
            dtype=float,
        )
        mesh = m.build_terrain_mesh_from_dem(
            dem=dem,
            bbox=(7.0, 46.0, 7.001, 46.001),
            physical_size_mm=100.0,
            vertical_exaggeration=1.0,
            base_thickness_mm=5.0,
            smooth_iterations=0,
            flatten_sea_level=False,
        )
        self.assertTrue(mesh.is_watertight)
        self.assertGreater(len(mesh.faces), 0)
        mins, maxs = mesh.bounds
        self.assertAlmostEqual(float(mins[0]), 0.0, delta=1e-6)
        self.assertAlmostEqual(float(mins[1]), 0.0, delta=1e-6)
        self.assertAlmostEqual(float(mins[2]), 0.0, delta=1e-6)
        self.assertGreater(float(maxs[2]), 5.0)

    def test_surface_sampler_uses_flipped_dem_orientation(self):
        dem = np.array(
            [
                [10.0, 20.0],
                [30.0, 40.0],
            ],
            dtype=float,
        )
        sampler = m._build_surface_sampler_from_dem(
            dem=dem,
            bbox=(7.0, 46.0, 7.001, 46.001),
            physical_size_mm=100.0,
            vertical_exaggeration=1.0,
            base_thickness_mm=5.0,
            smooth_iterations=0,
            flatten_sea_level=False,
        )
        width_mm, height_mm, _ = m.compute_model_size_mm((7.0, 46.0, 7.001, 46.001), 100.0)
        south_west = float(sampler(0.0, 0.0))
        north_west = float(sampler(0.0, height_mm))
        self.assertGreater(south_west, north_west)

    def test_surface_sampler_matches_terrain_formula_exactly(self):
        dem = np.array(
            [
                [10.0, 20.0],
                [30.0, 40.0],
            ],
            dtype=float,
        )
        sampler = m._build_surface_sampler_from_dem(
            dem=dem,
            bbox=(7.0, 46.0, 7.001, 46.001),
            physical_size_mm=100.0,
            vertical_exaggeration=2.0,
            base_thickness_mm=5.0,
            smooth_iterations=0,
            flatten_sea_level=False,
        )
        width_mm, height_mm, mm_per_meter = m.compute_model_size_mm((7.0, 46.0, 7.001, 46.001), 100.0)
        expected = (40.0 - 10.0) * 2.0 * mm_per_meter + 5.0
        self.assertAlmostEqual(float(sampler(width_mm, 0.0)), expected, places=6)

    def test_generate_puzzle_polygons_uses_round_tabs_for_multi_piece_grid(self):
        pieces = m.generate_puzzle_polygons(rows=1, columns=2, width_mm=100.0, height_mm=50.0)
        self.assertEqual(len(pieces), 2)
        _, _, left = pieces[0]
        _, _, right = pieces[1]
        self.assertGreater(len(list(left.exterior.coords)), 24)
        self.assertGreater(len(list(right.exterior.coords)), 24)
        self.assertGreater(left.bounds[2], 50.0)

    def test_generate_puzzle_polygons_delegates_to_stable_jigsaw_builder(self):
        calls = []

        def fake_build(bounds, config):
            calls.append((bounds.copy(), config.tiles_x, config.tiles_y))
            return [
                (0, 0, m.box(0.0, 0.0, 10.0, 10.0)),
                (0, 1, m.box(10.0, 0.0, 20.0, 10.0)),
            ]

        original = m.build_puzzle_tile_outlines
        try:
            m.build_puzzle_tile_outlines = fake_build
            pieces = m.generate_puzzle_polygons(rows=1, columns=2, width_mm=20.0, height_mm=10.0)
        finally:
            m.build_puzzle_tile_outlines = original

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1:], (2, 1))
        self.assertEqual(len(pieces), 2)


if __name__ == "__main__":
    unittest.main()
