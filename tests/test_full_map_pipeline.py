import unittest
from unittest.mock import patch

import numpy as np
import trimesh

import topomap_to_puzzle_3mf as m


class FullMapPipelineTests(unittest.TestCase):
    def test_build_full_map_model_returns_positive_scene(self):
        dem = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=float)
        terrain = m.build_terrain_mesh_from_dem(
            dem=dem,
            bbox=(7.0, 46.0, 7.001, 46.001),
            physical_size_mm=200.0,
            vertical_exaggeration=1.0,
            base_thickness_mm=5.0,
            smooth_iterations=0,
            flatten_sea_level=False,
        )

        with (
            patch.object(m, "fetch_dem", return_value=np.flipud(dem)),
            patch.object(m, "fetch_osm_buildings", return_value=[]),
            patch.object(m, "fetch_osm_roads", return_value=[]),
        ):
            scene = m.build_full_map_model(
                bbox=(7.0, 46.0, 7.001, 46.001),
                physical_size_mm=200.0,
                z_scale=1.0,
                smooth_terrain=False,
                flatten_sea_level=False,
            )

        self.assertIsInstance(scene, trimesh.Scene)
        self.assertIn("terrain", scene.geometry)
        mins, maxs = scene.bounds
        self.assertAlmostEqual(float(mins[0]), 0.0, delta=1e-6)
        self.assertAlmostEqual(float(mins[1]), 0.0, delta=1e-6)
        self.assertGreater(float(maxs[0]), 0.0)
        self.assertGreater(float(maxs[1]), 0.0)
        self.assertGreater(float(maxs[2]), 0.0)

    def test_prepare_map_terrain_returns_flipped_dem(self):
        dem = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float)
        with patch.object(m, "fetch_dem", return_value=np.flipud(dem)):
            terrain_mesh, prepared_dem, stats, adaptation = m._prepare_map_terrain(
                bbox=(7.0, 46.0, 7.001, 46.001),
                physical_size_mm=200.0,
                z_scale=1.0,
                smooth_terrain=False,
                flatten_sea_level=False,
                dem_resolution=2.0,
            )
        self.assertTrue(terrain_mesh.is_watertight)
        self.assertEqual(prepared_dem[0, 0], 3.0)
        self.assertEqual(stats, (1.0, 4.0, 3.0))
        self.assertEqual(adaptation.z_scale, 1.0)


if __name__ == "__main__":
    unittest.main()
