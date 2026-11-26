"""A small set and three stand-in figures for testing the camera, with no characters and no downloaded textures.

The set: a flagstone yard on grass, a stone wall across it at y=5 with a doorway (x=0, 1.6 m wide, 2.3 m high), a pillar and
crates near the camera side, a far wall at y=15 and a lit prop beyond the doorway. Figures expose what stagekit expects of an
actor: .head.point(), .head_r, .scale, .height, .stage, .coll, .facing.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from stagekit import build, core, lights


class _Head:
    def __init__(self, ob):
        self.ob = ob

    def point(self) -> Vector:
        bpy.context.view_layer.update()
        return self.ob.matrix_world.translation.copy()


class StandIn:
    """A 1.75 m figure from primitives. face_deg: 0 faces -Y (the camera side), 90 faces +X, -90 faces -X, 180 faces +Y."""

    def __init__(self, shot, name: str, at, color: str, face_deg: float = 0.0):
        self.id = name
        self.name = name
        self.height, self.head_r, self.scale = 1.75, 0.14, 1.0
        self.coll = bpy.data.collections.new(f"CAST_{name}")
        bpy.context.scene.collection.children.link(self.coll)
        self.stage = bpy.data.objects.new(f"{name}.stage", None)
        self.coll.objects.link(self.stage)
        self.stage.location = (at[0], at[1], 0.0)
        self.stage.rotation_euler.z = math.radians(face_deg)
        body = build.cyl(f"{name}.body", 0.2, 1.5, (0, 0, 0), color, top_radius=0.17, coll=f"CAST_{name}")
        legs = build.box(f"{name}.legs", (0.26, 0.2, 0.5), (0, 0, 0), "#2A2D3A", bevel=0.0, coll=f"CAST_{name}")
        head = build.ball(f"{name}.head", self.head_r, (0, 0, 1.75 - 2 * self.head_r), "#E8C39E", coll=f"CAST_{name}")
        nose = build.box(f"{name}.nose", (0.04, 0.07, 0.04), (0, -self.head_r - 0.02, 1.57), "#C99572", bevel=0.0, coll=f"CAST_{name}")
        for o in (body, legs, head, nose):
            o.parent = self.stage
        self.head = _Head(head)
        self.facing = Vector((math.sin(math.radians(face_deg)), -math.cos(math.radians(face_deg)), 0.0))
        shot.actors[name] = self

    def _billboard(self, cam_ob):                       # flat characters turn to the camera; these are solid
        return None

    def walk(self, t0: float, t1: float, to, bob: float = 0.03):
        """Walk in a straight line from where it stands at t0 to `to`, with a small vertical bob (like a step)."""
        a = self.stage.location.copy()
        b = Vector((to[0], to[1], 0.0))
        core.key(self.stage, "location", t0, a, linear=True)
        n = max(2, int((t1 - t0) * 2.0))
        for i in range(1, n + 1):
            u = i / n
            p = a.lerp(b, u)
            p.z = bob * abs(math.sin(math.pi * u * n))
            core.key(self.stage, "location", t0 + (t1 - t0) * u, p, linear=True)
        d = b - a
        if d.length > 1e-4:
            self.stage.rotation_euler.z = math.atan2(d.x, -d.y)
            self.facing = Vector((d.x, d.y, 0)).normalized()
        return self


def build_world(shot) -> dict:
    """Returns {"A", "B", "W", "door", "pillar", "beyond", "wall", "marks"}."""
    lights.rig("day_clear", sun_from=40)
    build.ground("ground", 60, "grass_lawn", flat_radius=30)
    build.patch("flags", build.rect(0, 1.5, 14, 10), "flagstone", z=0.01)
    wall = build.stone_wall("wall", length=10, height=3.2, thickness=0.6, at=(0, 5, 0), crenels=False, gap=(0, 1.6, 2.3), surface="castle_stone")
    far = build.stone_wall("far_wall", length=24, height=4.0, thickness=0.8, at=(0, 15, 0), surface="castle_stone")
    build.box("pillar", (0.6, 0.6, 3.0), (3.2, -2.5, 0), "castle_stone")
    pillar = bpy.data.objects["pillar"]
    for i, (x, y) in enumerate(((-3.2, 0.2), (-3.5, 0.9), (3.6, 1.8), (-2.2, 3.6), (4.0, 3.9))):
        build.crate(f"crate{i}", (x, y, 0), 0.6 + 0.1 * (i % 3), rot_z=17 * i)
    build.barrel("barrel0", (2.4, 3.3, 0))
    build.barrel("barrel1", (-4.2, 3.0, 0))
    build.bench("bench", (0.0, -1.0, 0), 0, 1.6)
    build.tree("tree0", (-6.0, 7.0), height=5.0, crown=2.0)
    build.torch("torch0", (-1.4, 4.65, 1.9), 0)
    build.torch("torch1", (1.4, 4.65, 1.9), 0)
    beyond = build.crate("beyond_crate", (0.0, 9.5, 0), 0.9, rot_z=20)
    build.crate("beyond2", (-2.0, 12.0, 0), 0.8, rot_z=-10)
    build.barrel("beyond_barrel", (2.2, 8.0, 0))
    build.banner("banner", (0, 14.55, 2.2), 0)
    door = core.empty("mark_door", (0, 5, 1.3), "RIG", 0.2)
    A = StandIn(shot, "Ana", (-2.6, 2.0), "#C94A4A", face_deg=90)
    B = StandIn(shot, "Ben", (-1.0, 2.4), "#3F6FC9", face_deg=-90)
    W = StandIn(shot, "Walt", (-4.0, 0.4), "#4FA35A", face_deg=90)
    for name, p in (("mark_A", A.stage.location), ("mark_B", B.stage.location)):
        core.empty(name, tuple(p), "RIG", 0.15)
    return {"A": A, "B": B, "W": W, "door": door, "pillar": pillar, "beyond": beyond, "wall": wall, "far_wall": far,
            "marks": {"A": (-2.6, 2.0, 0.0), "B": (-1.0, 2.4, 0.0), "door": (0, 5, 1.3), "beyond": (0, 9.5, 0.4), "far": (0, 15, 0.5), "left": (-5, 0, 0), "right": (5, 0, 0)}}
