import unittest
from unittest.mock import patch

import numpy as np

import topomap_to_puzzle_3mf as m


class OsmRoadsTests(unittest.TestCase):
    def test_fetch_osm_roads_returns_empty_list_on_failure(self):
        with patch("requests.post", side_effect=TimeoutError("boom")):
            roads = m.fetch_osm_roads((7.0, 46.0, 7.0003, 46.0003))
        self.assertEqual(roads, [])

    def test_build_roads_mesh_densifies_and_uses_overlap_extrusion(self):
        roads = [
            {
                "geometry": [
                    {"lat": 46.0, "lon": 7.0},
                    {"lat": 46.0, "lon": 7.0003},
                ],
                "tags": {"highway": "residential"},
            }
        ]

        mesh = m.build_roads_mesh(
            roads,
            bbox=(7.0, 46.0, 7.0003, 46.0003),
            physical_size_mm=200.0,
            surface_sampler=lambda x, _y: 10.0 + x * 0.05,
        )
        self.assertTrue(mesh.is_watertight)
        self.assertLessEqual(float(mesh.bounds[0][2]), 7.0)
        self.assertGreater(float(mesh.bounds[1][2]), 10.8)

    def test_build_roads_mesh_returns_visible_overlap_boxes_after_simplify(self):
        roads = [
            {
                "geometry": [
                    {"lat": 46.0, "lon": 7.0},
                    {"lat": 46.0, "lon": 7.0003},
                ],
                "tags": {"highway": "residential"},
            },
            {
                "geometry": [
                    {"lat": 46.0, "lon": 7.00015},
                    {"lat": 46.0003, "lon": 7.00015},
                ],
                "tags": {"highway": "residential"},
            },
        ]
        mesh = m.build_roads_mesh(
            roads,
            bbox=(7.0, 46.0, 7.0003, 46.0003),
            physical_size_mm=200.0,
            surface_sampler=lambda x, y: 5.0 + (x * 0.05) + (y * 0.02),
        )
        self.assertTrue(mesh.is_watertight)
        self.assertGreaterEqual(len(mesh.split(only_watertight=False)), 1)
        self.assertGreater(float(np.ptp(np.asarray(mesh.vertices)[:, 2])), 3.2)


if __name__ == "__main__":
    unittest.main()
