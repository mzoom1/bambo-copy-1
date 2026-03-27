import unittest
from unittest.mock import patch

import topomap_to_puzzle_3mf as m


class OsmBuildingsTests(unittest.TestCase):
    def test_fetch_osm_buildings_parses_way_geometry(self):
        payload = {
            "elements": [
                {
                    "type": "way",
                    "tags": {"building": "yes", "name": "Test House"},
                    "geometry": [
                        {"lat": 46.0, "lon": 7.0},
                        {"lat": 46.0, "lon": 7.0001},
                        {"lat": 46.0001, "lon": 7.0001},
                        {"lat": 46.0001, "lon": 7.0},
                        {"lat": 46.0, "lon": 7.0},
                    ],
                }
            ]
        }

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return payload

        with patch("requests.post", return_value=FakeResponse()):
            buildings = m.fetch_osm_buildings((7.0, 46.0, 7.0002, 46.0002))

        self.assertEqual(len(buildings), 1)
        self.assertEqual(buildings[0]["tags"]["name"], "Test House")

    def test_build_buildings_mesh_uses_overlap_extrusion(self):
        buildings = [
            {
                "geometry": [
                    {"lat": 46.0, "lon": 7.0},
                    {"lat": 46.0, "lon": 7.0001},
                    {"lat": 46.0001, "lon": 7.0001},
                    {"lat": 46.0001, "lon": 7.0},
                    {"lat": 46.0, "lon": 7.0},
                ],
                "tags": {"building": "yes", "height": "12"},
            }
        ]

        mesh = m.build_buildings_mesh(
            buildings,
            bbox=(7.0, 46.0, 7.0002, 46.0002),
            physical_size_mm=200.0,
            surface_sampler=lambda _x, _y: 10.0,
            model_mm_per_meter=1.0,
        )
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(float(mesh.bounds[0][2]), 7.0, delta=1e-6)
        self.assertAlmostEqual(float(mesh.bounds[1][2]), 22.0, delta=1e-6)


if __name__ == "__main__":
    unittest.main()
