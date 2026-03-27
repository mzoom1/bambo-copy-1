import numpy as np
import trimesh
import shapely.geometry as sg
from shapely.geometry.polygon import orient
import copy

# simulate a puzzle piece
x0, y0 = 0, 0
x1, y1 = 10, 10
poly = sg.box(x0, y0, x1, y1)
tab = sg.Point(10, 5).buffer(2, resolution=16)
poly = poly.union(tab)
tab_hole = sg.Point(5, 0).buffer(2, resolution=16)
poly = poly.difference(tab_hole)
poly = poly.buffer(-0.15, join_style=1).buffer(0)

# Create a sample block for intersection
terrain = trimesh.creation.box((15, 15, 10))
terrain.apply_translation([5, 5, 5])
terrain.export("debug_terrain_bool.stl")

# Using trimesh.creation.extrude_polygon
mesh = trimesh.creation.extrude_polygon(poly, 15.0)
mesh.apply_translation([0, 0, -2.5])

# check boolean
res = trimesh.boolean.intersection([terrain, mesh], engine="manifold")
res.export("debug_boolean_result.stl")

print("Trimesh extrude volume:", mesh.volume)
print("Trimesh intersect volume:", res.volume)
