"""A fairy wand: a slim pale stick with a chunky gold star on top (drawn thick enough to read on a phone)."""
import math

import bmesh

from stagekit import build

ASSET = dict(id="prop_fairy_wand", name="Fairy wand with a star", kind="prop", tags=["wand", "fairy", "magic", "star", "spell"],
             era=["fantasy"], source="built", license="project",
             notes="0.42 m tall, standing on the stick end; hold it 0.06 m up: fairy.hold(wand, 'R', t, offset=(0, 0, -0.06)); "
                   "the star faces -Y")


def build_asset():
    stick = build.cyl("wand.stick", 0.011, 0.30, (0, 0, 0), "#F4E3B0", seg=10)
    knob = build.ball("wand.knob", 0.018, (0, 0, 0.275), "gold")
    star = build.box("wand.star", (0.02, 0.03, 0.02), (0, 0, 0.345), "gold", bevel=0.0)     # replaced by a 5-point star below
    bm = bmesh.new()
    pts = [((0.075 if i % 2 == 0 else 0.032) * math.sin(math.pi * i / 5), (0.075 if i % 2 == 0 else 0.032) * math.cos(math.pi * i / 5))
           for i in range(10)]
    f1 = [bm.verts.new((x, -0.014, z)) for x, z in pts]
    f2 = [bm.verts.new((x, 0.014, z)) for x, z in pts]
    bm.faces.new(f1)
    bm.faces.new(f2[::-1])
    for i in range(10):
        j = (i + 1) % 10
        bm.faces.new((f1[i], f2[i], f2[j], f1[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(star.data)
    bm.free()
    star.modifiers.clear()
    return build.group("prop_fairy_wand", [stick, knob, star])
