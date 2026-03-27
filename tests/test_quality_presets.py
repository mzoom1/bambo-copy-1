import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh

import server
import topomap_to_puzzle_3mf as m


class QualityPresetTests(unittest.TestCase):
    def test_resolve_quality_preset_mapping(self):
        self.assertEqual(m.resolve_quality_preset("Very Low"), 128)
        self.assertEqual(m.resolve_quality_preset("Low"), 192)
        self.assertEqual(m.resolve_quality_preset("Average"), 256)
        self.assertEqual(m.resolve_quality_preset("High"), 384)
        self.assertEqual(m.resolve_quality_preset("Very High"), 512)
        self.assertIsNone(m.resolve_quality_preset("Unknown"))

    def test_generate_puzzle_from_map_uses_dem_resolution_directly(self):
        terrain = trimesh.creation.box(extents=[100.0, 100.0, 20.0])
        dem = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=float)
        stats = (0.0, 1.0, 1.0)
        adaptation = m.TerrainAdaptationResult(z_scale=1.0, smooth_iterations=0)
        scene = trimesh.Scene()
        scene.add_geometry(terrain, geom_name="terrain")
        scene.metadata["pipeline"] = {
            "bbox": (7.0, 46.0, 7.001, 46.001),
            "physical_size_mm": 200.0,
            "dem": dem,
            "vertical_exaggeration": 1.0,
            "base_thickness_mm": 5.0,
            "flatten_sea_level": False,
            "smooth_iterations": 0,
            "buildings": [],
            "roads": [],
        }
        scene.metadata["terrain_stats"] = stats
        scene.metadata["terrain_adaptation"] = {"z_scale": 1.0, "smooth_iterations": 0}

        captured = {}

        def fake_prepare_map_terrain(**kwargs):
            captured["dem_resolution"] = kwargs.get("dem_resolution")
            return terrain, dem, stats, adaptation

        def fake_build_full_map_model(**kwargs):
            fake_prepare_map_terrain(
                bbox=kwargs["bbox"],
                physical_size_mm=kwargs["physical_size_mm"],
                z_scale=kwargs["z_scale"],
                smooth_terrain=kwargs["smooth_terrain"],
                flatten_sea_level=kwargs["flatten_sea_level"],
                dem_resolution=kwargs["dem_resolution"],
            )
            return scene

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.3mf"
            with (
                patch.object(m, "_prepare_map_terrain", side_effect=fake_prepare_map_terrain),
                patch.object(m, "build_full_map_model", side_effect=fake_build_full_map_model),
                patch.object(m, "export_piece_groups_3mf"),
            ):
                m.generate_puzzle_from_map(
                    bbox=(7.0, 46.0, 7.001, 46.001),
                    physical_size_mm=200.0,
                    rows=1,
                    columns=1,
                    z_scale=1.0,
                    smooth_terrain=False,
                    flatten_sea_level=False,
                    base_thickness_mm=m.BASE_THICKNESS_MM,
                    output_path=output_path,
                    template_path=None,
                    include_buildings=False,
                    include_roads=False,
                    dem_resolution=128,
                )

        self.assertEqual(captured["dem_resolution"], 128)
        self.assertLess(captured["dem_resolution"], m.DEM_REQUEST_WIDTH)

    def test_generate_endpoint_maps_quality_preset(self):
        payload = {
            "bbox": {"minLon": 0.0, "minLat": 0.0, "maxLon": 1.0, "maxLat": 1.0},
            "physicalSizeMm": 150,
            "rows": 2,
            "columns": 2,
            "vertical_exaggeration": 2.0,
            "base_thickness_mm": 5.0,
            "smoothTerrain": True,
            "flattenSeaLevel": True,
            "includeBuildings": False,
            "includeRoads": False,
            "qualityPreset": "Very Low",
        }

        async def invoke():
            with tempfile.TemporaryDirectory() as tmpdir:
                output = Path(tmpdir) / "out.3mf"
                output.write_bytes(b"3mf")
                with patch.object(server, "generate_puzzle_from_map", return_value=output) as call:
                    response = await server.generate(payload)
                    self.assertEqual(response.status_code, 202)
                    await asyncio.sleep(0.05)
                    return call

        call = asyncio.run(invoke())
        self.assertTrue(call.called)
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs.get("dem_resolution"), 128)


if __name__ == "__main__":
    unittest.main()
