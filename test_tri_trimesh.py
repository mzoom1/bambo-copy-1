import trimesh
import shapely.geometry as sg
poly = sg.box(0, 0, 10, 10)
vertices, faces = trimesh.creation.triangulate_polygon(poly)
print("Vertices:", vertices)
print("Faces:", faces)
