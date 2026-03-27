import numpy as np
import trimesh
import shapely.geometry as sg

poly = sg.Polygon([(0,0), (10,0), (10,10), (0,10)]).difference(sg.Point(5, 5).buffer(2, resolution=16))
# This is a polygon with a hole
mesh = trimesh.creation.extrude_polygon(poly, height=5.0)
print("Faces:", len(mesh.faces))
print("Is watertight:", mesh.is_watertight)
print("Volume:", mesh.volume)
