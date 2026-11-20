"""Old door key standing upright as it sits in a lock: bow (ring) toward -Y (the viewer), shaft into +Y."""
import math

import bmesh
import bpy

from stagekit import build, core

ASSET = dict(id="prop_door_key", name="Old door key", kind="prop", tags=["key", "door", "lock", "brass", "metal"],
             notes="0.09 m long along Y, bow toward -Y (the viewer). Origin is at the lock face; rotate the root about Y to turn it. Use scale 1.5 for inserts.")


def build_asset():
    brass = build.clay("#C59A3A", rough=0.38, metallic=0.8, bump=0.004)
    # the bow is a flat ring in the plane of the shaft (YZ), so from the front it is a bar that visibly turns
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=28, radius1=0.017, radius2=0.017, depth=0.007)
    ring = build._new("key_bow", bm)
    ring.rotation_euler.y = math.radians(90)
    ring.location = (0, -0.052, 0.02)
    build.finish(ring, material=brass, bevel=0.002)
    hole = build.cyl("key_hole", 0.008, 0.03, (0, 0, 0), "#000000", segments=16, bevel=0, coll="HELPERS")
    hole.rotation_euler.y = math.radians(90)
    hole.location = (-0.015, -0.052, 0.02)
    hole.hide_render = hole.hide_viewport = True
    b = ring.modifiers.new("hole", "BOOLEAN")
    b.object = hole
    b.operation = "DIFFERENCE"
    ring.modifiers.move(len(ring.modifiers) - 1, 0)
    shaft = build.cyl("key_shaft", 0.0045, 0.075, (0, 0, 0), material=brass, segments=14, bevel=0)
    shaft.rotation_euler.x = math.radians(-90)
    shaft.location = (0, -0.036, 0.02)
    bit = build.box("key_bit", (0.004, 0.012, 0.014), (0, 0.022, 0.004), material=brass, bevel=0.001)
    return build.group("prop_door_key", [ring, shaft, bit, hole])
