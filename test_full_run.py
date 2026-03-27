import trimesh
from topomap_to_puzzle_3mf_clean import cut_input_mesh_file_to_puzzle_3mf

# Create a dummy box mesh
mesh = trimesh.creation.box((100, 100, 10))
mesh.apply_translation([50, 50, 5])
mesh.export("test_box.stl")

cut_input_mesh_file_to_puzzle_3mf(
    input_mesh_path="test_box.stl",
    output_path="test_gen_output_robust.3mf",
    tiles_x=2,
    tiles_y=2,
    size_mm=100.0,
    cutter_z_padding_mm=5.0
)
print("Success")
