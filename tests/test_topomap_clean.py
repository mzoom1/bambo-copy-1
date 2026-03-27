import tempfile
import zipfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import trimesh
from shapely.geometry import box

import topomap_to_puzzle_3mf_clean as m


class TopomapCleanTests(unittest.TestCase):
    def test_build_puzzle_tile_outlines_applies_clearance(self):
        bounds = np.array([[0.0, 0.0, 0.0], [100.0, 50.0, 0.0]], dtype=np.float64)
        config = m.PuzzleConfig(tiles_x=2, tiles_y=1, tab_noise_seed=0)

        outlines = m.build_puzzle_tile_outlines(bounds, config)

        self.assertEqual(len(outlines), 2)
        left = next(poly for row, col, poly in outlines if row == 0 and col == 0)
        right = next(poly for row, col, poly in outlines if row == 0 and col == 1)
        self.assertGreaterEqual(float(left.bounds[2]), 49.85)
        self.assertLessEqual(float(right.bounds[0]), 50.15)

    def test_arrange_tiles_for_printing_uses_five_mm_gap(self):
        config = m.PuzzleConfig(tiles_x=2, tiles_y=1, arrange_gap_mm=5.0)
        left = trimesh.creation.box(extents=[10.0, 10.0, 2.0])
        right = trimesh.creation.box(extents=[8.0, 10.0, 2.0])

        arranged = m.arrange_tiles_for_printing([left, right], config)

        self.assertEqual(len(arranged), 2)
        left_max = float(arranged[0].bounds[1][0])
        right_min = float(arranged[1].bounds[0][0])
        self.assertGreaterEqual(right_min - left_max, 5.0 - 1e-6)
        self.assertAlmostEqual(float(arranged[0].bounds[0][2]), 0.0, places=6)
        self.assertAlmostEqual(float(arranged[1].bounds[0][2]), 0.0, places=6)

    def test_export_tiles_3mf_with_template_injection(self):
        tile = trimesh.creation.box(extents=[10.0, 10.0, 2.0])
        tile.metadata["name"] = "tile_x0_y0"
        tile.metadata["tile_x"] = 0
        tile.metadata["tile_y"] = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.3mf"
            m.export_tiles_3mf([tile], output_path=output_path, template_path=Path("template.3mf"))
            self.assertTrue(output_path.exists())
            with zipfile.ZipFile(output_path, "r") as zf:
                names = zf.namelist()
                self.assertTrue(any(name.endswith(".model") for name in names))
                self.assertTrue(any("project_settings" in name for name in names))

    def test_non_volume_input_uses_blender_boolean_without_repair(self):
        mesh = trimesh.creation.box(extents=[20.0, 20.0, 5.0])
        mesh.faces = mesh.faces[:-1]
        mesh.remove_unreferenced_vertices()
        self.assertFalse(mesh.is_volume)

        config = m.PuzzleConfig(tiles_x=1, tiles_y=1, tab_noise_seed=0)

        def fake_outlines(bounds, cfg):
            self.assertEqual(cfg.tiles_x, 1)
            self.assertEqual(cfg.tiles_y, 1)
            return [(0, 0, box(0.0, 0.0, 20.0, 20.0))]

        with patch.object(m, "build_puzzle_tile_outlines", side_effect=fake_outlines), \
             patch.object(m.trimesh.boolean, "intersection") as fake_intersection:
            m.trimesh_blender.exists = True
            m.trimesh_blender._blender_executable = "/tmp/blender"
            fake_intersection.return_value = trimesh.creation.box(extents=[10.0, 10.0, 2.0])
            m.cut_map_into_puzzle_pieces(mesh, config)

        kwargs = fake_intersection.call_args.kwargs
        self.assertEqual(kwargs["engine"], "blender")
        self.assertFalse(kwargs["check_volume"])


if __name__ == "__main__":
    unittest.main()
