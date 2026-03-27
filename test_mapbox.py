import mapbox_earcut
import numpy as np

# simple test
verts = np.array([[0,0], [10,0], [10,10], [0,10]], dtype=np.float64).flatten()
rings = np.array([], dtype=np.uint32)
faces = mapbox_earcut.triangulate_float64(verts, rings)
print("Faces:", faces)
