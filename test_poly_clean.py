import shapely.geometry as sg
from shapely.validation import make_valid
from shapely.geometry.polygon import orient
import trimesh

poly = sg.Polygon([(0,0), (10,0), (5,5), (10,10), (0,10)]) # A bow-tie? No this is valid.
# self intersecting:
poly = sg.Polygon([(0,0), (10,10), (10,0), (0,10)])
print("Before:", poly.is_valid)
clean = make_valid(poly)
print("After make_valid:", clean.is_valid, type(clean))
clean_buf = poly.buffer(0)
print("After buffer(0):", clean_buf.is_valid, type(clean_buf))
