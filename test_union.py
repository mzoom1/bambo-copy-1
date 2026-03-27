import logging
logging.basicConfig(level=logging.INFO)
from topomap_to_puzzle_3mf import generate_puzzle_from_map

bbox = (15.2, 47.0, 15.21, 47.01)
generate_puzzle_from_map(
    bbox=bbox, 
    physical_size_mm=50.0, 
    rows=1, 
    columns=1, 
    z_scale=2.0,
    smooth_terrain=True, 
    flatten_sea_level=True, 
    base_thickness_mm=5.0,
    output_path="test_union.3mf", 
    include_buildings=True, 
    include_roads=True,
    dem_resolution=128
)
