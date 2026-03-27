import trimesh
import shapely.geometry as sg
import numpy as np
poly = sg.box(0, 0, 10, 10)
mesh = trimesh.creation.extrude_polygon(poly, 5.0)
print("Bounds:", mesh.bounds)
print("Watertight:", mesh.is_watertight)
print("Volume:", mesh.volume)
print("Faces normal [0]:", mesh.face_normals[0])
