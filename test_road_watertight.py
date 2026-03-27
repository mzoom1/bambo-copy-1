import trimesh
from shapely.geometry import LineString
from topomap_to_puzzle_3mf import extrude_polygon_between, _cleanup_mesh
import numpy as np

def build_test_road():
    segment = LineString([(0,0), (10,0)])
    road_poly = segment.buffer(0.3, cap_style=2, join_style=2).buffer(0)
    mesh1 = extrude_polygon_between(road_poly, 0.0, 1.0)
    print(f"Segment 1 watertight: {mesh1.is_watertight}")
    return mesh1

mesh = build_test_road()
