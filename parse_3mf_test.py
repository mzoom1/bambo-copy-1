import zipfile
import tempfile
import os
import xml.etree.ElementTree as ET

CORE_3MF_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"

with zipfile.ZipFile("test_gen_output_robust.3mf", "r") as z:
    with tempfile.TemporaryDirectory() as td:
        z.extractall(td)
        model_path = os.path.join(td, "3D", "3dmodel.model")
        tree = ET.parse(model_path)
        root = tree.getroot()
        resources = root.find(f"{{{CORE_3MF_NS}}}resources")
        objects = resources.findall(f"{{{CORE_3MF_NS}}}object")
        print(f"Found {len(objects)} objects")
        for obj in objects:
            mesh = obj.find(f"{{{CORE_3MF_NS}}}mesh")
            vertices = mesh.find(f"{{{CORE_3MF_NS}}}vertices")
            triangles = mesh.find(f"{{{CORE_3MF_NS}}}triangles")
            print(f"Object {obj.attrib.get('name')}: {len(vertices)} vertices, {len(triangles)} triangles")
