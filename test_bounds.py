import trimesh
import shapely.geometry as sg
poly = sg.box(100, 100, 120, 120)
mesh = trimesh.creation.extrude_polygon(poly, 5.0)
print(mesh.bounds)
