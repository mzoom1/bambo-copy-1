import numpy as np
import trimesh
import shapely.geometry as sg
from shapely.ops import unary_union

# typical jigsaw tab
poly = sg.box(0, 0, 10, 10)
tab = sg.Point(5, 10).buffer(2, resolution=16)
poly = poly.union(tab).buffer(0)
poly = poly.buffer(-0.15, join_style=1).buffer(0)

mesh = trimesh.creation.extrude_polygon(poly, height=5.0)
print("Is watertight:", mesh.is_watertight)
print("Volume:", mesh.volume)
print("Faces:", len(mesh.faces))
mesh.apply_translation([0, 0, -2.5])
print("Is watertight after trans:", mesh.is_watertight)
