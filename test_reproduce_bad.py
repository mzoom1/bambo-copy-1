import numpy as np
import trimesh
import shapely.geometry as sg
from topomap_to_puzzle_3mf_clean import extrude_polygon_between

# simulate a puzzle piece
x0, y0 = 0, 0
x1, y1 = 10, 10
poly = sg.box(x0, y0, x1, y1)
tab = sg.Point(10, 5).buffer(2, resolution=16)
poly = poly.union(tab)
tab_hole = sg.Point(5, 0).buffer(2, resolution=16)
poly = poly.difference(tab_hole)
poly = poly.buffer(-0.15, join_style=1).buffer(0)

mesh = extrude_polygon_between(poly, 0, 5)
print("Mesh is watertight:", mesh.is_watertight)
print("Mesh volume:", mesh.volume)
print("Mesh faces:", len(mesh.faces))

# save for visual inspection
mesh.export("test_reproduce_bad.stl")
