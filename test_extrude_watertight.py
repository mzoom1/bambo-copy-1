import trimesh
from shapely.geometry import Polygon
from topomap_to_puzzle_3mf import extrude_polygon_between, _cleanup_mesh

poly = Polygon([(0,0), (1,0), (1,1), (0,1)])
mesh = extrude_polygon_between(poly, 0.0, 5.0)
print(f"Faces: {len(mesh.faces)}, Watertight: {mesh.is_watertight}")
