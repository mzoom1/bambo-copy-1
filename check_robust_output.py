import trimesh
import zipfile
import tempfile
import os

with zipfile.ZipFile("test_gen_output_robust.3mf", "r") as z:
    with tempfile.TemporaryDirectory() as td:
        z.extractall(td)
        scene = trimesh.load(os.path.join(td, "3D", "3dmodel.model"))
        print("Exported scene meshes:")
        for name, geom in scene.geometry.items():
            print(f" - {name}: faces={len(geom.faces)}, watertight={geom.is_watertight}")
