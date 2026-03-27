import trimesh

b1 = trimesh.creation.box(extents=(1, 1, 1))
b1.apply_translation([0, 0, 0])

b2 = trimesh.creation.box(extents=(1, 1, 1))
b2.apply_translation([0.5, 0, 0])

out = trimesh.util.concatenate([b1, b2])
print("Watertight:", out.is_watertight)
