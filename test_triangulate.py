import shapely.geometry as sg
from shapely.ops import triangulate

# Create a polygon where Delaunay triangulation of its vertices does NOT contain its boundary edges.
# A simple example: a very thin "C" shape or a polygon with a "hole" that has points arranged such that Delaunay edges cross the boundary.
poly = sg.Polygon([(0,0), (10,0), (10,10), (8,10), (8,2), (2,2), (2,10), (0,10)])

# Let's add many points along the boundary to make Delaunay fail on boundary edges
boundary_points = []
for i in range(100):
    boundary_points.append((i/10.0, 0.0))
    
poly = sg.Polygon([(0,0), (10,0), (5, 0.1), (0,0)])

tris = []
for tri in triangulate(poly):
    if poly.covers(tri.representative_point()):
        tris.append(tri)

import shapely.ops
tri_union = shapely.ops.unary_union(tris)
diff = poly.symmetric_difference(tri_union)
print("Difference Area:", diff.area)

