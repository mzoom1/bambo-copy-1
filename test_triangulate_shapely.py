import shapely.geometry as sg
from shapely.ops import triangulate
from shapely.geometry.polygon import orient

poly = sg.Polygon([(0,0), (10,0), (10,10), (5,5), (0,10)])
clean = orient(poly.buffer(0), sign=1.0)
tris = []
for tri in triangulate(clean):
    if clean.covers(tri.representative_point()):
        tris.append(tri)
print(len(tris))
for t in tris:
    print(t.wkt)

