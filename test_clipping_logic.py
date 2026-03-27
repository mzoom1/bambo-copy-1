import shapely.geometry as sg
from shapely.ops import triangulate

# test buffer and clearance
poly = sg.box(0, 0, 10, 10)
# adding a tab
tab = sg.Point(5, 10).buffer(2)
poly = poly.union(tab).buffer(0)
# clearance
poly = poly.buffer(-0.15, join_style=1).buffer(0)
print("After clearance area:", poly.area)

def _triangles_for_polygon(poly: sg.Polygon):
    tris = []
    for tri in triangulate(poly):
        if poly.covers(tri.representative_point()):
            tris.append(tri)
    return tris

tris = _triangles_for_polygon(poly)
import shapely.ops
tri_union = shapely.ops.unary_union(tris)
diff = poly.symmetric_difference(tri_union)
print("Difference Area:", diff.area)

