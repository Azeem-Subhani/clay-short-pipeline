"""A village well: a round fieldstone wall, two oak posts, a little shingle roof, a windlass with a crank and a bucket on a rope.
An example of a built asset in the 2D-cast / 3D-world look: real surfaces by name, chunky shapes, moving parts as children.

    python tools/clip.py asset examples/assets/set_stone_well.py --no-save     preview only
    python tools/clip.py asset examples/assets/set_stone_well.py               preview + file it in the library
"""
import math

from stagekit import build, core

ASSET = dict(id="set_stone_well", name="Stone well with roof and bucket", kind="set", tags=["well", "water", "village", "stone", "bucket", "medieval"],
             era=["medieval", "fairytale", "old_west"],
             notes="1.5 m across, 2.6 m tall, front toward -Y. Children a shot can animate: 'well.crank' (rotate about X to wind), "
                   "'well.bucket' (move in Z, 0.95 = at the rim, -3 = down the shaft).")


def build_asset():
    parts = []
    # the wall: a ring of stone with a dark shaft inside
    wall = build.cyl("well.wall", 0.75, 0.8, (0, 0, 0), "fieldstone", seg=28)
    shaft = build.cyl("well.shaft", 0.56, 0.06, (0, 0, 0.78), "#0B0D10", seg=28)
    cap = build.cyl("well.cap", 0.8, 0.09, (0, 0, 0.8), "castle_stone", top_radius=0.78, seg=28)
    hole = build.cyl("well.hole", 0.57, 0.1, (0, 0, 0.8), "#0B0D10", seg=28)
    parts += [wall, shaft, cap, hole]
    # two posts and the beam the roof sits on
    for sx in (-1, 1):
        parts.append(build.box(f"well.post{sx}", (0.13, 0.13, 2.05), (sx * 0.68, 0, 0), "oak_planks"))
    parts.append(build.box("well.beam", (1.7, 0.12, 0.12), (0, 0, 2.0), "dark_timber"))
    # the roof: two pitched slabs
    for sy in (-1, 1):
        slab = build.box(f"well.roof{sy}", (1.9, 0.86, 0.06), (0, sy * 0.33, 2.2), "roof_slate")
        slab.rotation_euler.x = math.radians(-34 * sy)
        parts.append(slab)
    # the windlass: an axle between the posts, a crank outside the right post
    axle = build.cyl("well.axle", 0.07, 1.36, (0, 0, 0), "oak_planks", seg=14)
    axle.rotation_euler.y = math.radians(90)
    axle.location = (-0.68, 0, 1.45)
    crank = core.empty("well.crank", (0.76, 0, 1.45), "SET", 0.1)
    arm = build.box("well.crank.arm", (0.05, 0.05, 0.3), (0, 0, 0), "iron_dark")
    grip = build.box("well.crank.grip", (0.22, 0.05, 0.05), (0.1, 0, 0.28), "oak_planks")
    arm.parent = crank
    grip.parent = crank
    # rope and bucket
    rope = build.cyl("well.rope", 0.02, 0.36, (0, 0, 1.13), "rope", seg=8)
    bucket = build.bucket("well.bucket", at=(0, 0, 0.95))
    parts += [axle, crank, rope, bucket]
    return build.group("set_stone_well", parts)
