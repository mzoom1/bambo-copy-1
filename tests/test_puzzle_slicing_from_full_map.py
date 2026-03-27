import unittest

import trimesh

import topomap_to_puzzle_3mf as m


def _translated_box(extents, min_corner):
    mesh = trimesh.creation.box(extents=extents)
    center = [min_corner[i] + (extents[i] * 0.5) for i in range(3)]
    mesh.apply_translation(center)
    return mesh


class FullMapSlicingTests(unittest.TestCase):
    def test_slice_full_map_into_pieces_returns_merged_tiles(self):
        terrain = _translated_box([120.0, 120.0, 8.0], [0.0, 0.0, 0.0])
        tower = _translated_box([30.0, 30.0, 12.0], [15.0, 15.0, 8.0])
        scene = trimesh.Scene()
        scene.add_geometry(terrain, geom_name="terrain")
        scene.add_geometry(tower, geom_name="tower")

        tiles = m.slice_full_map_into_pieces(
            full_map_scene=scene,
            rows=2,
            columns=2,
            base_thickness_mm=5.0,
            engine="manifold",
        )

        self.assertEqual(len(tiles), 4)
        self.assertEqual([tile.metadata["name"] for tile in tiles], [
            "tile_x0_y0",
            "tile_x1_y0",
            "tile_x0_y1",
            "tile_x1_y1",
        ])
        for tile in tiles:
            self.assertTrue(tile.is_watertight)
            self.assertGreater(len(tile.faces), 0)


if __name__ == "__main__":
    unittest.main()
