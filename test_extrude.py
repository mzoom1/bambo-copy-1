import numpy as np
import trimesh
import shapely.geometry as sg
from shapely.ops import unary_union
from shapely.geometry.polygon import orient

tab_poly = sg.box(0, 0, 10, 10).union(sg.Point(5, 10).buffer(2)).difference(sg.Point(5, 0).buffer(2))
# Trimesh extrusion
mesh = trimesh.creation.extrude_polygon(tab_poly, 5.0)
mesh.apply_translation([0, 0, -2.5])
print("Is watertight:", mesh.is_watertight)
print("Is volume:", mesh.is_volume)
print("Faces:", len(mesh.faces))
