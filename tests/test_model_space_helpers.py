import unittest

import topomap_to_puzzle_3mf as m


class ModelSpaceHelperTests(unittest.TestCase):
    def test_compute_scale_factor_xy(self):
        self.assertAlmostEqual(m.compute_scale_factor_xy(200.0, 5000.0), 0.04)
        self.assertAlmostEqual(m.compute_scale_factor_xy(150.0, 3750.0), 0.04)

    def test_bbox_projector_uses_south_west_origin(self):
        projector = m._bbox_to_model_projector((7.0, 46.0, 7.002, 46.001), 200.0)

        x0, y0 = projector(7.0, 46.0)
        x1, y1 = projector(7.002, 46.001)

        self.assertAlmostEqual(x0, 0.0, delta=1e-9)
        self.assertAlmostEqual(y0, 0.0, delta=1e-9)
        self.assertGreater(x1, 0.0)
        self.assertGreater(y1, 0.0)

    def test_model_dimensions_fit_within_requested_physical_size(self):
        width_mm, height_mm, mm_per_meter = m.compute_model_size_mm(
            bbox=(7.0, 46.0, 7.002, 46.001),
            physical_size_mm=200.0,
        )
        self.assertGreater(width_mm, 0.0)
        self.assertGreater(height_mm, 0.0)
        self.assertGreater(mm_per_meter, 0.0)
        self.assertLessEqual(max(width_mm, height_mm), 200.0)

    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            m.compute_scale_factor_xy(0.0, 10.0)
        with self.assertRaises(ValueError):
            m.compute_scale_factor_xy(10.0, 0.0)
        with self.assertRaises(ValueError):
            m.compute_model_size_mm((0.0, 0.0, 0.0, 1.0), 100.0)


if __name__ == "__main__":
    unittest.main()
