import numpy as np
import trimesh
import shapely.geometry as sg
from shapely.geometry.polygon import orient
import mapbox_earcut

poly = sg.Polygon([(0,0), (10,0), (10,10), (0,10)])
poly = orient(poly.buffer(0), sign=1.0)
mesh = trimesh.creation.extrude_polygon(poly, 5.0)
print("Is volume:", mesh.is_volume)
print("Is watertight:", mesh.is_watertight)
print("Volume:", mesh.volume)
print("Face normal 0:", mesh.face_normals[0])

# Let's check boolean intersection
box = trimesh.creation.box((10,10,10))
box.apply_translation([5,5,5])

try:
    res = trimesh.boolean.intersection([box, mesh], engine="manifold")
    print("Intersection volume:", res.volume)
except Exception as e:
    print("Intersection failed:", e)

