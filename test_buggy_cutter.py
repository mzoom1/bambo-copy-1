import numpy as np
import trimesh
import shapely.geometry as sg
from shapely.geometry.polygon import orient

x0, y0 = 0, 0
x1, y1 = 10, 10
poly = sg.box(x0, y0, x1, y1)
tab = sg.Point(10, 5).buffer(2, resolution=16)
poly = poly.union(tab)
tab_hole = sg.Point(5, 0).buffer(2, resolution=16)
poly = poly.difference(tab_hole)
poly = poly.buffer(-0.15, join_style=1).buffer(0)
poly = orient(poly, sign=1.0)

# extrude
mesh = trimesh.creation.extrude_polygon(poly, 5.0)
mesh.export("buggy_cutter.stl")
