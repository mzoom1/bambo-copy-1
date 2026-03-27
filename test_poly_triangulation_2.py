import numpy as np
import trimesh
import shapely.geometry as sg
from shapely.geometry.polygon import orient
import mapbox_earcut

x0, y0 = 0, 0
x1, y1 = 10, 10
poly = sg.box(x0, y0, x1, y1)
tab = sg.Point(10, 5).buffer(2, resolution=16)
poly = poly.union(tab)
tab_hole = sg.Point(5, 0).buffer(2, resolution=16)
poly = poly.difference(tab_hole)
poly = poly.buffer(-0.15, join_style=1).buffer(0)
poly = orient(poly, sign=1.0)

# the default trimesh triangulator works like this:
vertices, faces = trimesh.creation.triangulate_polygon(poly)
print("Faces shape:", faces.shape)

# wait, trimesh.creation.extrude_polygon creates bad cutters.
# let's try our own strict extrusion logic that creates simple vertical walls perfectly matching shapely vertices

def strict_extrude(poly: sg.Polygon, bottom_z: float, top_z: float):
    # Triangulate top and bottom using trimesh.creation.triangulate_polygon which uses mapbox_earcut
    verts_2d, faces_2d = trimesh.creation.triangulate_polygimport numpy as np
import trimesh
import s3dimport trimesh
imAdimport shapelicfrom shapely.geometry.polygov import mapbox_earcut

x0, y0 = 0, 0
x1, y1, 
x0, y0 = 0, 0
x1,   
    # Add top poly = sg.box(x N to 2N-1)
    n_verts = len(vpoly = poly.union(tab)
tab_hole = sg.Point(5,_3tab_hole = sg.Point(5 tpoly = poly.difference(tabbottom faces (flipped norpoly = poly.buffer(-0.15, joi    poly = orient(poly, sign=1.0)

# the default tri  
# the defa faces
    for f in vertices, faces = trimesh.creation.triangulate_pol fprint("Faces shape:", faces.shape)

# wait, trimesh.creatioom
# wait, trimesh.creation.extrudeeri# let's try our own strict extrusion logic that creates simp r
def strict_extrude(poly: sg.Polygon, bottom_z: float, top_z: float):
    # Triangulate top and bottom using tri       # Triangulate top and bottom using trimesh.creat_closed[i]
          verts_2d, faces_2d = trimesh.creation.triangulate_polygimport vertices for the wall to avoid normimport trimesh
import s3dimport trimesh
imAdimport shapelicfrom shapely.geomteimport s3dimp  imAdimport shapelicfromtt
x0, y0 = 0, 0
x1, y1, 
x0, y0 = 0, 0
x1,   
    # Add top poly = sg[0]x1, y1, 
x0,_zx0, y0   x1,   
    #0[    #0[    n_verts = len(vpoly = poly.union(ta ctab_hole = sg.Point(5,_3tab_hole = sg.Po  
# the default tri  
# the defa faces
    for f in vertices, faces = trimesh.creation.triangulate_pol fprint("Faces shape:", faces.shape)

# wait, trimesh.crea # # the defa faces
 .     for normal is
# wait, trimesh.creatioom
# wait, trimesh.creation.extrudeeri# let's try our own strict extrusion   # wait, trimesh.creation  def strict_extrude(poly: sg.Polygon, bottom_z: float, top_z: float):
    # Triangulate top and bal    # Triangulate top and bottom using tri       # Triangulate top s(          verts_2

mesh = strict_extrude(poly, 0, 5.0)
mesh.export("strict_cutter.stl")
print("Watertight:", mesh.is_watertight)
print("Volume:", mesh.volume)

