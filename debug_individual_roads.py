import logging
from topomap_to_puzzle_3mf import _cleanup_mesh, extrude_polygon_between
from shapely.geometry import Polygon, LineString

segment = LineString([(0,0), (10,0)])
# buffer creates rounded caps by default
road_poly = segment.buffer(0.3, cap_style=2, join_style=2).buffer(0)
mesh = extrude_polygon_between(road_poly, -3.0, 0.8)
mesh = _cleanup_mesh(mesh)
print(f"Watertight: {mesh.is_watertight}, Faces: {len(mesh.faces)}")

