import numpy as np
import trimesh
import shapely.geometry as sg
from shapely.geometry.polygon import orient

# A simple polygon
poly = sg.Polygon([(0,0), (10,0), (10,10), (0,10)])
clean = orient(poly.buffer(0), sign=1.0)
mesh = trimesh.creation.extrude_polygon(clean, 5.0)

print("Is volume:", mesh.is_volume)
print("Volume:", mesh.volume)

# Let's write out a simple cutter to an STL and check it
mesh.export("cutter.stl")
