import numpy as np
import trimesh
import shapely.geometry as sg

# thin spiral
coords = [(0,0), (10,0), (10,10), (2,10), (2,2), (8,2), (8,8), (4,8), (4,4), (6,4), (6,6), (5,6), (5,5), (7,5), (7,7), (3,7), (3,3), (9,3), (9,9), (1,9), (1,1), (0,1)]
poly = sg.Polygon(coords)
try:
    mesh = trimesh.creation.extrude_polygon(poly, 5.0)
    print("Is watertight:", mesh.is_watertight)
    print("Volume:", mesh.volume)
except Exception as e:
    print("Failed trimesh extrude:", e)
