import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh

import topomap_to_puzzle_3mf as m


class OsmMergeTests(unittest.TestCase):
    def test_export_piece_groups_3mf_writes_one_build_item_per_piece(self):
        base = trimesh.creation.box(extents=[10.0, 10.0, 2.0])
        base.metadata["name"] = "piece_r00_c00_terrain"
        base.metadata["piece_group"] = "piece_r00_c00"
        buildings = trimesh.creation.box(extents=[3.0, 3.0, 1.0])
        buildings.metadata["name"] = "piece_r00_c00_buildings"
        buildings.metadata["piece_group"] = "piece_r00_c00"
        roads = trimesh.creation.box(extents=[6.0, 1.0, 0.5])
        roads.metadata["name"] = "piece_r00_c00_roads"
        roads.metadata["piece_group"] = "piece_r00_c00"
        label = trimesh.creation.box(extents=[2.0, 1.0, 0.8])
        label.metadata["name"] = "piece_r00_c00_label"
        label.metadata["piece_group"] = "piece_r00_c00"
        label.metadata["part_role"] = "label"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.3mf"
            m.export_piece_groups_3mf([[base, buildings, roads, label]], output_path=output_path, template_path=None)

            with zipfile.ZipFile(output_path, "r") as zf:
                model_name = next(name for name in zf.namelist() if name.endswith(".model"))
                xml = zf.read(model_name).decode("utf-8")

        self.assertIn('name="piece_r00_c00"', xml)
        self.assertIn("<components>", xml)
        self.assertEqual(xml.count("<item"), 1)
        self.assertEqual(xml.count("<component "), 4)
        self.assertIn('name="label"', xml)

    def test_export_piece_groups_3mf_rejects_non_watertight_mesh(self):
        base = trimesh.creation.box(extents=[10.0, 10.0, 2.0])
        base.metadata["name"] = "piece_r00_c00_terrain"
        base.metadata["piece_group"] = "piece_r00_c00"
        # Break watertightness by removing one face.
        base.faces = base.faces[:-1]
        base.remove_unreferenced_vertices()
        self.assertFalse(base.is_watertight)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.3mf"
            with self.assertRaisesRegex(RuntimeError, "Non-watertight mesh detected"):
                m.export_piece_groups_3mf([[base]], output_path=output_path, template_path=None)

    def test_export_piece_groups_3mf_salvages_watertight_components_from_mixed_mesh(self):
        good = trimesh.creation.box(extents=[10.0, 10.0, 2.0])
        bad = trimesh.creation.box(extents=[4.0, 4.0, 2.0])
        bad.faces = bad.faces[:-1]
        bad.remove_unreferenced_vertices()
        bad.apply_translation([20.0, 0.0, 0.0])
        mixed = trimesh.util.concatenate([good, bad])
        mixed.metadata["piece_group"] = "piece_r00_c00"
        mixed.metadata["part_role"] = "roads"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.3mf"
            m.export_piece_groups_3mf([[mixed]], output_path=output_path, template_path=None)
            self.assertTrue(output_path.exists())

    def test_load_input_mesh_falls_back_to_concatenate_for_non_volume_scene(self):
        scene = trimesh.Scene()
        terrain = trimesh.creation.box(extents=[100.0, 100.0, 10.0])
        terrain.apply_translation([50.0, 50.0, 5.0])
        building = trimesh.creation.box(extents=[10.0, 10.0, 10.0])
        building.apply_translation([20.0, 20.0, 10.0])
        building.faces = building.faces[:-1]
        building.remove_unreferenced_vertices()
        scene.add_geometry(terrain, geom_name="terrain")
        scene.add_geometry(building, geom_name="building")

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "scene.3mf"
            trimesh.exchange.export.export_mesh(scene, file_obj=str(input_path), file_type="3mf")

            with patch.object(trimesh.boolean, "union", side_effect=ValueError("Not all meshes are volumes!")):
                mesh = m._load_input_mesh(input_path, boolean_engine="manifold")

        self.assertIsInstance(mesh, trimesh.Trimesh)
        self.assertGreater(len(mesh.faces), 0)
        self.assertGreater(mesh.extents[0], 0.0)
        self.assertGreater(mesh.extents[1], 0.0)


    def test_generate_puzzle_from_map_exports_flat_tile_meshes(self):
        terrain = trimesh.creation.box(extents=[100.0, 100.0, 20.0])
        terrain.apply_translation([50.0, 50.0, 10.0])
        building = trimesh.creation.box(extents=[20.0, 20.0, 10.0])
        building.apply_translation([35.0, 35.0, 25.0])
        scene = trimesh.Scene()
        scene.add_geometry(terrain, geom_name="terrain")
        scene.add_geometry(building, geom_name="building")

        with patch.object(m, "build_full_map_model", return_value=scene), \
             patch.object(m, "export_tiles_3mf") as export_tiles:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "out.3mf"
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
                    include_buildings=True,
                    include_roads=True,
                    dem_resolution=2.0,
                    engine="manifold",
                )

        self.assertTrue(export_tiles.called)
        exported_tiles = export_tiles.call_args.args[0]
        self.assertEqual(len(exported_tiles), 1)
        self.assertEqual(exported_tiles[0].metadata["name"], "tile_x0_y0")


if __name__ == "__main__":
    unittest.main()
