from shapely.geometry import Polygon, LineString
import trimesh

# Let's create a polygon that might cause spikes if extruded without cleaning
poly = Polygon([(0,0), (10,0), (10,10), (0,10), (5,0)]) # Self-intersecting or bad
try:
    poly = poly.buffer(0)
    print("Buffer 0 succeeded:", poly.is_valid)
except Exception as e:
    print("Buffer 0 failed:", e)

