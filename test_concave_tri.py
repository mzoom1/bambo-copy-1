import shapely.geometry as sg
from shapely.ops import triangulate

# An L-shape polygon with extra points to make Delaunay fail
coords = [(0,0), (10,0), (10,10), (8,10)]
for i in range(7, 2, -1):
    coords.append((i, 3))
coords.extend([(2,10), (0,10)])
poly = sg.Polygon(coords)

tris = []
for tri in triangulate(poly):
    if poly.covers(tri.representative_point()):
        tris.append(tri)

import shapely.ops
tri_union = shapely.ops.unary_union(tris)
print("Original Area:", poly.area)
print("Triangulated Area:", tri_union.area)
print("Difference Area:", poly.symmetric_difference(tri_union).area)
