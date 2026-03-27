import trimesh
from shapely.geometry import LineString
from topomap_to_puzzle_3mf import extrude_polygon_between, _cleanup_mesh
import numpy as np

segment1 = LineString([(0,0), (1,0)])
segment2 = LineString([(1,0), (2,0)])

poly1 = segment1.buffer(0.3, cap_style=2, join_style=2).buffer(0)
poly2 = segment2.buffer(0.3, cap_style=2, join_style=2).buffer(0)

mesh1 = extrude_polygon_between(poly1, 0.0, 1.0)
mesh2 = extrude_polygon_between(poly2, 0.0, 1.0)

out = trimesh.util.concatenate([mesh1, mesh2])
print("Out faces:", len(out.faces))
print("Out watertight:", out.is_watertight)

comps = out.split(only_watertight=False)
print("Comps count:", len(comps))
for i, comp in enumerate(comps):
    print(f"Comp {i} watertight: {comp.is_watertight}")
