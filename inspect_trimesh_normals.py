import numpy as np
import trimesh
import shapely.geometry as sg
from shapely.geometry.polygon import orient

poly = sg.box(0, 0, 10, 10).union(sg.Point(5, 10).buffer(2, resolution=16)).difference(sg.Point(5, 0).buffer(2, resolution=16))
poly = poly.buffer(-0.15, join_style=1).buffer(0)
poly = orient(poly, sign=1.0)

mesh = trimesh.creation.extrude_polygon(poly, 5.0)

z_up_faces = []
z_down_faces = []
for i, normal in enumerate(mesh.face_normals):
    if normal[2] > 0.9:
        z_up_faces.append(i)
    elif normal[2] < -0.9:
        z_down_faces.append(i)

print("Faces with normal Z > 0:", len(z_up_faces))
print("Faces with normal Z < 0:", len(z_down_faces))

# Check winding order
print("Mesh is watertight:", mesh.is_watertight)
print("Mesh volume:", mesh.volume)
if mesh.volume < 0:
    print("WARNING: Mesh volume is negative! Inside-out normals!")
