import unittest
from pathlib import Path


class FrontendTermsTests(unittest.TestCase):
    def test_vertical_exaggeration_label_replaces_z_scale_label(self) -> None:
        app_path = Path("/Users/eugenetoporkov/Desktop/bambo/TopoPuzzle 3D/src/App.tsx")
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("Vertical Exaggeration", source)
        self.assertNotIn("Z-Scale Exaggeration", source)
        self.assertNotIn('>Elevation<', source)

    def test_payload_uses_vertical_exaggeration_primary_field(self) -> None:
        app_path = Path("/Users/eugenetoporkov/Desktop/bambo/TopoPuzzle 3D/src/App.tsx")
        source = app_path.read_text(encoding="utf-8")

        self.assertIn("vertical_exaggeration: zScale", source)
        self.assertIn("zScale,", source)


if __name__ == "__main__":
    unittest.main()
