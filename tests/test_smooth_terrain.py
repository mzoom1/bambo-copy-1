import unittest

import numpy as np

import topomap_to_puzzle_3mf as m


class SmoothTerrainTests(unittest.TestCase):
    def test_generate_smooth_terrain_returns_positive_space_mesh(self):
        dem = np.array(
            [
                [0.0, 1.0, 0.0],
                [1.0, 4.0, 1.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=float,
        )

        mesh = m.generate_smooth_terrain(
            dem,
            bbox=(7.0, 46.0, 7.002, 46.002),
            physical_size_mm=200.0,
            vertical_exaggeration=1.5,
            base_thickness_mm=5.0,
        )

        self.assertTrue(mesh.is_watertight)
        self.assertGreater(len(mesh.faces), 0)
        mins, maxs = mesh.bounds
        self.assertAlmostEqual(float(mins[0]), 0.0, delta=1e-6)
        self.assertAlmostEqual(float(mins[1]), 0.0, delta=1e-6)
        self.assertAlmostEqual(float(mins[2]), 0.0, delta=1e-6)
        self.assertGreater(float(maxs[0]), 0.0)
        self.assertGreater(float(maxs[1]), 0.0)
        self.assertGreater(float(maxs[2]), 5.0)


if __name__ == "__main__":
    unittest.main()
