import shapely.geometry as sg
from shapely.ops import triangulate

# creating a very difficult shape for simple triangulate
# thin spiral
coords = [(0,0), (10,0), (10,10), (2,10), (2,2), (8,2), (8,8), (4,8), (4,4), (6,4), (6,6), (5,6), (5,5), (7,5), (7,7), (3,7), (3,3), (9,3), (9,9), (1,9), (1,1), (0,1)]
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
