import numpy as np
import trimesh
import shapely.geometry as sg
from shapely.geometry.polygon import orient

# simulate a puzzle piece
x0, y0 = 0, 0
x1, y1 = 10, 10
poly = sg.box(x0, y0, x1, y1)
tab = sg.Point(10, 5).buffer(2, resolution=16)
poly = poly.union(tab)
tab_hole = sg.Point(5, 0).buffer(2, resolution=16)
poly = poly.difference(tab_hole)
poly = poly.buffer(-0.15, join_style=1).buffer(0)

mesh = trimesh.creation.extrude_polygon(poly, 5.0)

# area of poly
expected_area = poly.area

# area of top faces
top_area = 0.0
for i, normal in enumerate(mesh.face_normals):
    if normal[2] > 0.9:
        top_area += mesh.area_faces[i]

print("Expected Area:", expected_area)
print("Top Area:", top_area)
print("Difference:", expected_area - top_area)
