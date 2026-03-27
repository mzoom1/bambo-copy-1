import logging
logging.basicConfig(level=logging.DEBUG)
from topomap_to_puzzle_3mf import generate_puzzle_from_map, build_roads_mesh, fetch_osm_roads, _bbox_to_model_projector, _project_line_to_model_xy
from shapely.geometry import Polygon

bbox = (15.2, 47.0, 15.21, 47.01)

# Just fetch roads and build mesh to see if it's watertight
roads = fetch_osm_roads(bbox)
print(f"Fetched {len(roads)} roads")

mesh = build_roads_mesh(
    roads=roads,
    bbox=bbox,
    physical_size_mm=100.0,
    road_width_mm=0.6,
    road_height_mm=0.8,
    surface_sampler=lambda x,y: 0.0,
    clip_polygon=Polygon([(0,0), (100,0), (100,100), (0,100)])
)

print(f"Roads mesh faces: {len(mesh.faces)}")
print(f"Roads mesh is watertight: {mesh.is_watertight}")
if not mesh.is_watertight:
    comps = mesh.split(only_watertight=False)
    bad_comps = [c for c in comps if not c.is_watertight]
    print(f"Total components: {len(comps)}, Bad components: {len(bad_comps)}")

