import numpy as np
import trimesh
import shapely.geometry as sg
from topomap_to_puzzle_3mf_clean import cut_input_mesh_file_to_puzzle_3mf

# Create a sample terrain using a box with some height variation
mesh = trimesh.creation.box((100, 100, 10))
mesh.apply_translation([50, 50, 5])
# add some noise to top z
vertices = np.array(mesh.vertices)
for i in range(len(vertices)):
    if vertices[i, 2] > 9:
        vertices[i, 2] += np.random.uniform(0, 2)
mesh = trimesh.Trimesh(vertices=vertices, faces=mesh.faces)
mesh.export("debug_terrain.stl")

cut_input_mesh_file_to_puzzle_3mf(
    input_mesh_path="debug_terrain.stl",
    output_path="debug_puzzle_out.3mf",
    tiles_x=3,
    tiles_y=3,
    size_mm=100.0,
    cutter_z_padding_mm=5.0
)
print("Saved debug_puzzle_out.3mf")
