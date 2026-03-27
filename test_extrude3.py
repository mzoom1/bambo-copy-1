import shapely.geometry as sg
from topo_jigsaw_exporter import extrude_polygon_between
import trimesh

# typical jigsaw tab
poly = sg.box(0, 0, 10, 10)
tab = sg.Point(5, 10).buffer(2, resolution=16)
poly = poly.union(tab).buffer(0)
poly = poly.buffer(-0.15, join_style=1).buffer(0)

mesh = extrude_polygon_between(poly, 0, 5)
print("Manual Extrude:")
print("Watertight:", mesh.is_watertight)
print("Volume:", mesh.volume)
print("Faces:", len(mesh.faces))

mesh2 = trimesh.creation.extrude_polygon(poly, 5)
print("\nTrimesh Extrude:")
print("Watertight:", mesh2.is_watertight)
print("Volume:", mesh2.volume)
print("Faces:", len(mesh2.faces))
