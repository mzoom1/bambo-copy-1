import shapely.geometry as sg
from shapely.ops import triangulate
from shapely.geometry.polygon import orient
import numpy as np

def _triangles_for_polygon(poly: sg.Polygon):
    clean = orient(poly.buffer(0), sign=1.0)
    triangles = []
    for tri in triangulate(clean):
        if clean.covers(tri.representative_point()):
            triangles.append(tri)
    return triangles

# Create a shape with a tab
poly = sg.box(0, 0, 10, 10).union(sg.Point(5, 10).buffer(2, resolution=8)).difference(sg.Point(5, 0).buffer(2, resolution=8))

tris = _triangles_for_polygon(poly)
import shapely.ops
tri_union = shapely.ops.unary_union(tris)
diff = poly.symmetric_difference(tri_union)
print("Difference Area:", diff.area)
print("Original Area:", poly.area)
print("Triangulated Area:", tri_union.area)

