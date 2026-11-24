"""stagekit.actions - named, timed performances for the 2D cast.

    queen.do("gasp", t)                              # starts at t, returns the time it ends
    boy.do("pick_up", ring, hit=shot.t("picked up")) # the hand CLOSES on the ring on that word
    guard.do("point", gate, t)                       # at a point, an object, an anchor or another actor
    a.do("hand_over", key, to=b, t=shot.t("gave"))   # two people
    t1 = thief.do("sneak", t, to=(3, 1))             # moving actions return the arrival time

An action is a short performance, not a pose: anticipation, the main motion, a settle. `t` is when it starts; `hit` is
when its key moment lands (the grab, the finger arriving, the jump leaving the ground): use `hit=shot.t("word")` so the
action lands on the narrator's word. speed=1.3 plays it faster. Every action works in the three views and both facings
because it is built from the view-aware poses, reach(), hold() and the walk cycles of stagekit.cast.

Characters without legs (ghost), with a tail (mermaid) and the like still answer every action: the registry entry of the
character (config/cast.json > characters > <Name> > body) says what replaces walking, sitting and so on.

The catalogue (names, what each needs, lead times) is ACTIONS below; `python tools/clip.py actions` prints it from
config/actions.json. To add an action see docs/ADDING_NEW_ACTIONS.md.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import core

ACTIONS: dict = {}


def action(name: str, group: str, lead: float = 0.3, dur: float = 1.0, needs: tuple = (), summary: str = "", loops: bool = False):
    """Register an action. lead: seconds from its start to its key moment; dur: its usual length at speed 1;
    needs: what the caller must pass ("target", "prop", "to", "other"); loops: runs until `until=`."""

    def deco(fn):
        ACTIONS[name] = {"fn": fn, "group": group, "lead": lead, "dur": dur, "needs": tuple(needs), "summary": summary or (fn.__doc__ or "").strip(),
                         "loops": loops}
        return fn

    return deco


def catalog() -> list:
    """The action list as plain data (written to config/actions.json by tools/blender/list_actions.py)."""
    return [{"name": n, "group": d["group"], "lead": d["lead"], "duration": d["dur"], "needs": list(d["needs"]), "loops": d["loops"],
             "summary": d["summary"]} for n, d in ACTIONS.items()]


def run(actor, name: str, *args, t=None, hit=None, speed: float = 1.0, **kw) -> float:
    if name not in ACTIONS:
        raise KeyError(f"unknown action {name!r}. Actions: {', '.join(sorted(ACTIONS))}")
    spec = ACTIONS[name]
    target = kw.pop("target", None)
    for x in args:                                    # do("pick_up", ring, 2.4): a number is the time, anything else the target
        if isinstance(x, (int, float)) and not isinstance(x, bool) and t is None and hit is None:
            t = float(x)
        elif target is None:
            target = x
    k = max(0.2, float(speed))
    if t is None:
        t = (float(hit) - spec["lead"] / k) if hit is not None else 0.0
    t = max(0.0, t)
    for need in spec["needs"]:
        have = target if need in ("target", "prop", "other") else kw.get(need)
        if have is None:
            raise TypeError(f'action "{name}" needs {need}: {spec["summary"]}')
    A = _Perf(actor, k)
    end = spec["fn"](A, t, target=target, **kw) if "target" in spec["fn"].__code__.co_varnames else spec["fn"](A, t, **kw)
    actor.shot.actions.append({"actor": actor.id, "action": name, "t0": round(t, 3), "t1": round(float(end if end is not None else t), 3)}) \
        if hasattr(actor.shot, "actions") else None
    return float(end if end is not None else t + spec["dur"] / k)


# ----------------------------------------------------------------------------- the performer: an actor plus tempo and helpers
class _Perf:
    def __init__(self, actor, k: float):
        self.a = actor
        self.k = k
        self.body = getattr(actor, "body", None) or {}

    def d(self, seconds: float) -> float:
        """A duration at this performance's tempo."""
        return seconds / self.k

    # -- where things are on screen
    def side_of(self, target) -> str:
        p = core.point_of(target.chest if hasattr(target, "chest") else target)
        cam = bpy.context.scene.camera
        right = (cam.matrix_world.to_3x3() @ Vector((1, 0, 0))) if cam else Vector((1, 0, 0))
        return "right" if (p - self.a.position()).dot(right) >= 0 else "left"

    def face(self, target, t):
        """Turn to the side of the screen the target is on (no-op if already there)."""
        if target is None:
            return
        s = self.side_of(target)
        if (s == "right") != (self.a._face > 0):
            self.a.face(s, t)

    def look(self, target, t, blend=0.1):
        """Eyes to a target (they lead the action)."""
        if target is None:
            return
        p = core.point_of(target.head if hasattr(target, "head") else target)
        hz = self.a.head.point().z
        dz = max(-1.0, min(1.0, (p.z - hz) / 0.7))
        dx = 1.0 if (self.side_of(target) == "right") == (self.a._face > 0) else -0.8
        self.a.eyes(dx, dz, t, blend)

    def rest(self, t, blend=0.3, legs=True):
        a = self.a
        a.pose("rest", t, blend)
        a.lean(0, t, blend)
        a.tilt_head(0, t, blend)
        if legs and getattr(a, "_sink", None) and any(a._sink):
            a.legs(0, 0, t, blend)

    def has_legs(self) -> bool:
        return bool(self.body.get("legs", True))

    def gait(self) -> str:
        return self.body.get("gait", "walk")

    def chest_height(self) -> float:
        return self.a.chest.point().z

    def arm_len(self) -> float:
        if hasattr(self.a, "arm_length"):                       # the 3D cast knows its own arm
            return self.a.arm_length()
        c = self.a._calib[self.a._view_key()]
        return (c["arm_upper.R"][3] + c["arm_lower.R"][3] + 0.5 * c["hand.R"][3]) * self.a.scale

    def shoulder_z(self) -> float:
        if hasattr(self.a, "shoulder_height"):
            return self.a.shoulder_height()
        v = self.a._view_key()
        return self.a.position().z + float(self.a.rigs[v].data.bones["arm_upper.R"].head_local.z) * self.a.scale

    def glide(self, t0, to, speed_mps=1.1, bob=0.05, period=0.7):
        """Travel without legs: a float with a slow bob (ghost, genie) or a swim (mermaid)."""
        a = self.a
        p0 = a.position()
        p1 = Vector((to[0], to[1], to[2] if len(to) > 2 else p0.z))
        dist = (p1 - p0).length
        if dist < 1e-3:
            return t0
        self.face(p1, t0)
        t1 = t0 + dist / max(0.05, speed_mps * self.k)
        n = max(2, int((t1 - t0) / (period / 2)))
        for i in range(n + 1):
            u = i / n
            q = p0.lerp(p1, u)
            q.z += bob * math.sin(math.pi * i) if False else (bob if i % 2 else 0.0) * (0 if i in (0, n) else 1)
            a.stage.location = q
            core.key_frame(a.stage, "location", a._f(t0 + (t1 - t0) * u))
        a._pos = p1.copy()
        a.lean(8, t0 + 0.15, 0.2)
        a.lean(0, t1, 0.25)
        return t1

    def go(self, t0, to, cycle="walk", speed=None, arms=True):
        """Get somewhere the way this body does it. Returns the arrival time."""
        g = self.gait()
        a = self.a
        if g != "walk":
            base = {"walk": 1.1, "run": 2.6, "sneak": 0.55}[cycle]
            return self.glide(t0, to, base, bob=0.06 if g == "float" else 0.03)
        sp = (speed if speed is not None else {"walk": 2.0, "run": 1.0, "sneak": 1.0}[cycle]) * self.k
        return a.walk(t0, to, speed=sp, cycle=cycle, arms=arms)

    def crouch_for(self, z_world, t, blend):
        """Lean and bend the knees just enough for the hand to get down to a height. Returns True if it had to crouch."""
        a = self.a
        drop = self.shoulder_z() - z_world
        reach = self.arm_len()
        if drop <= reach * 0.85:
            a.lean(max(0.0, min(18.0, (drop / max(reach, 1e-3)) * 14)), t, blend)
            return False
        need = drop - reach * 0.75
        torso = max(0.2, (self.shoulder_z() - a.position().z) * 0.5)
        lean = max(20.0, min(62.0, math.degrees(math.asin(max(-1.0, min(1.0, need / torso))))))
        a.lean(lean, t, blend)
        a.tilt_head(-min(14.0, lean * 0.3), t, blend)
        if need > torso * 0.75 and self.has_legs():
            a.legs(46, 86, t, blend)
            return True
        return False

    def pulse(self, fn, t0, t1, every=0.3):
        """Call fn(i, t) on a beat between two times."""
        n = max(1, int(round((t1 - t0) / self.d(every))))
        for i in range(n + 1):
            fn(i, t0 + (t1 - t0) * i / n)
        return n


def _both(A, raise_a, bend_a, t, blend, plane="fwd", dl=0.0):
    A.a.arm("R", raise_a, bend_a, t, blend, plane=plane)
    A.a.arm("L", raise_a + dl, bend_a, t, blend, plane=plane)


# ============================================================================= MOVING
@action("walk", "moving", lead=0.0, dur=2.0, needs=("to",), summary="walk to a place on the walk cycle, feet planted (ghost: floats, mermaid: swims)")
def walk(A, t, to=None, speed=None, arms=True):
    return A.go(t, to, "walk", speed, arms)


@action("run", "moving", lead=0.0, dur=1.2, needs=("to",), summary="run to a place: long strides, body forward, elbows pumping")
def run_(A, t, to=None, speed=None, arms=True):
    A.a.squash(t, 0.06, 0.04, 0.1)                        # a dip before the start
    return A.go(t + A.d(0.08), to, "run", speed, arms)


@action("sneak", "moving", lead=0.0, dur=3.0, needs=("to",), summary="creep to a place: knees bent, careful high steps, hands held up (also tiptoe)")
def sneak(A, t, to=None, speed=None):
    A.a.expr("worried", t, 0.15, amount=0.6)
    return A.go(t, to, "sneak", speed, True)


@action("tiptoe", "moving", lead=0.0, dur=3.0, needs=("to",), summary="tiptoe: the sneak cycle, upright and a little faster")
def tiptoe(A, t, to=None):
    return A.go(t, to, "sneak", 1.3, True)


@action("step_forward", "moving", lead=0.35, dur=0.7, summary="one decisive step toward the facing side")
def step_forward(A, t, dist=0.5):
    a = A.a
    p = a.position()
    cam = bpy.context.scene.camera
    right = (cam.matrix_world.to_3x3() @ Vector((1, 0, 0))) if cam else Vector((1, 0, 0))
    q = p + right * dist * a._face * a.scale
    return A.go(t, (q.x, q.y, p.z), "walk", 2.2)


@action("pace", "moving", lead=0.0, dur=4.0, summary="walk up and down in agitation (three legs)", loops=True)
def pace(A, t, width=1.2, turns=3):
    a = A.a
    p = a.position()
    cam = bpy.context.scene.camera
    right = (cam.matrix_world.to_3x3() @ Vector((1, 0, 0))) if cam else Vector((1, 0, 0))
    pts = [p + right * width * 0.5, p - right * width * 0.5]
    a.pose("hips", t, 0.25)
    for i in range(turns):
        q = pts[i % 2]
        t = A.go(t, (q.x, q.y, p.z), "walk", 2.4, arms=False)
    t = A.go(t, (p.x, p.y, p.z), "walk", 2.4, arms=False)
    A.rest(t + A.d(0.25))
    return t + A.d(0.25)


@action("stomp", "moving", lead=0.3, dur=1.2, summary="angry stomp on the spot: fists down, one foot slammed twice")
def stomp(A, t, times=2):
    a = A.a
    a.expr("angry", t, 0.1)
    a.pose({"L": (18, 38, "out"), "R": (18, 38, "out"), "hands": "fist", "lean": 6}, t + A.d(0.15), A.d(0.15))
    tt = t + A.d(0.15)
    for i in range(times):
        if A.has_legs():
            a.legs(52, 70, tt + A.d(0.16), A.d(0.14), side="R", ground=False)
            a.legs(0, 0, tt + A.d(0.26), A.d(0.08), side="R", ground=False)
        a.squash(tt + A.d(0.27), 0.08, 0.04, 0.12)
        tt += A.d(0.42)
    A.rest(tt + A.d(0.3), A.d(0.3))
    return tt + A.d(0.3)


@action("sit_down", "moving", lead=0.45, dur=0.8, summary="sit: a small lean forward, then down onto a seat at knee height (mermaid: settles on her tail)")
def sit_down(A, t):
    a = A.a
    a.lean(14, t + A.d(0.2), A.d(0.2))
    a.pose("sit", t + A.d(0.6), A.d(0.4))
    a.lean(0, t + A.d(0.75), A.d(0.25))
    a.squash(t + A.d(0.62), 0.05, 0.04, 0.14)
    return t + A.d(0.8)


@action("sit_idle", "moving", lead=0.0, dur=2.0, summary="stay seated: small shifts of weight and a look around", loops=True)
def sit_idle(A, t, until=None):
    a = A.a
    t1 = until if until is not None else t + A.d(2.0)
    if not getattr(a, "_sink", None) or not any(a._sink):
        a.pose("sit", t, 0.0)
    A.pulse(lambda i, tt: a.lean(3 if i % 2 else -2, tt, A.d(0.5)), t + A.d(0.4), t1, every=1.1)
    return t1


@action("stand_up", "moving", lead=0.35, dur=0.7, summary="rise from sitting, kneeling or crouching")
def stand_up(A, t):
    a = A.a
    a.lean(18, t + A.d(0.2), A.d(0.2))
    if A.has_legs():
        a.legs(0, 0, t + A.d(0.55), A.d(0.35))
    a.pose("rest", t + A.d(0.6), A.d(0.4))
    a.lean(0, t + A.d(0.7), A.d(0.3))
    a.squash(t + A.d(0.5), -0.05, 0.04, 0.16)
    return t + A.d(0.7)


@action("kneel", "moving", lead=0.4, dur=0.7, summary="drop to the knees")
def kneel(A, t):
    a = A.a
    a.lean(10, t + A.d(0.2), A.d(0.2))
    a.pose("kneel", t + A.d(0.55), A.d(0.35))
    a.squash(t + A.d(0.56), 0.05, 0.04, 0.12)
    return t + A.d(0.7)


@action("crouch", "moving", lead=0.35, dur=0.6, summary="squat low on the spot (hide, lurk, look at something on the ground)")
def crouch(A, t):
    a = A.a
    a.pose("crouch", t + A.d(0.45), A.d(0.35))
    a.squash(t + A.d(0.46), 0.04, 0.04, 0.12)
    return t + A.d(0.6)


@action("hide", "moving", lead=0.4, dur=1.4, summary="duck down behind cover, then peek over it")
def hide(A, t, peek=True):
    a = A.a
    a.expr("worried", t, 0.1)
    a.pose("crouch", t + A.d(0.4), A.d(0.3))
    if peek:
        a.tilt_head(-16, t + A.d(1.0), A.d(0.3))
        a.eyes(1.0, 0.4, t + A.d(0.9), 0.1)
    return t + A.d(1.3)


@action("peek", "moving", lead=0.4, dur=1.0, summary="lean the head and shoulders out from behind something, look, pull back")
def peek(A, t, back=True):
    a = A.a
    a.eyes(1.0, 0.0, t, 0.1)
    a.lean(22, t + A.d(0.35), A.d(0.3))
    a.tilt_head(-10, t + A.d(0.4), A.d(0.25))
    a.pose({"R": (58, 52), "hands": {"R": "open"}}, t + A.d(0.35), A.d(0.3))
    if back:
        A.rest(t + A.d(1.1), A.d(0.25), legs=False)
        return t + A.d(1.1)
    return t + A.d(0.5)


@action("lie_down", "moving", lead=0.6, dur=1.0, summary="lie flat on the back on the ground")
def lie_down(A, t):
    a = A.a
    a.pose("rest", t, A.d(0.2))
    if A.has_legs():
        a.legs(40, 70, t + A.d(0.3), A.d(0.3))
        a.legs(0, 0, t + A.d(0.9), A.d(0.4))
    a.rock(-88, t + A.d(0.9), A.d(0.6), pivot=0.0)
    p = a.position()
    a.move(t + A.d(0.3), t + A.d(0.9), (p.x, p.y, p.z + 0.16 * a.scale), linear=False, land=False)
    a.floating = True
    return t + A.d(1.0)


@action("sleep", "moving", lead=0.0, dur=3.0, summary="asleep: eyes shut, slow deep breathing (lying if lie_down came first, else nodding off upright)", loops=True)
def sleep(A, t, until=None):
    a = A.a
    t1 = until if until is not None else t + A.d(3.0)
    a.expr("neutral", t, 0.2)
    a.eyes_closed(t, t1)
    if abs(a.tilt.rotation_euler.y) < 0.5:
        a.pose("sleep", t + 0.3, 0.3)
    A.pulse(lambda i, tt: a.squash(tt, -0.03, 0.5, 0.6), t + 0.4, t1, every=1.9)
    return t1


@action("wake_up", "moving", lead=0.3, dur=0.9, summary="wake with a start and sit / stand up")
def wake_up(A, t):
    a = A.a
    a.expr("surprised", t + A.d(0.1), 0.06)
    a.squash(t + A.d(0.12), -0.08, 0.04, 0.14)
    if abs(a.tilt.rotation_euler.y) > 0.5:
        a.rock(0, t + A.d(0.7), A.d(0.5), pivot=0.0)
        p = a.position()
        a.move(t + A.d(0.2), t + A.d(0.7), (p.x, p.y, p.z - 0.16 * a.scale), land=False)
        a.floating = False
    a.pose("rest", t + A.d(0.6), A.d(0.3))
    a.tilt_head(0, t + A.d(0.5), A.d(0.2))
    a.expr("neutral", t + A.d(0.9), 0.2)
    return t + A.d(0.9)


@action("fall", "moving", lead=0.35, dur=0.9, summary="fall over: arms fly up, the figure tips and lands flat (to=(x, y, z) to fall down to a place)")
def fall(A, t, to=None, forward=True):
    a = A.a
    a.expr("surprised", t, 0.06)
    a.pose("hands_up", t + A.d(0.2), A.d(0.18))
    a.squash(t + A.d(0.1), -0.08, 0.04, 0.1)
    p = a.position()
    dest = to if to is not None else (p.x, p.y, p.z + 0.12 * a.scale)
    a.rock(84 if forward else -84, t + A.d(0.75), A.d(0.55), pivot=0.0 if to is None else a.height * 0.5)
    a.move(t + A.d(0.25), t + A.d(0.75), dest, arc=0.0 if to is None else 0.05, land=False)
    a.squash(t + A.d(0.76), 0.14, 0.05, 0.2)
    a.floating = True
    return t + A.d(0.95)


@action("get_up", "moving", lead=0.5, dur=0.9, summary="get back on the feet after a fall or lying down")
def get_up(A, t):
    a = A.a
    p = a.position()
    a.rock(0, t + A.d(0.7), A.d(0.55), pivot=0.0)
    a.move(t + A.d(0.1), t + A.d(0.7), (p.x, p.y, max(0.0, p.z - 0.14 * a.scale)), land=False)
    a.floating = False
    A.rest(t + A.d(0.8), A.d(0.4))
    a.expr("neutral", t + A.d(0.8), 0.2)
    return t + A.d(0.9)


@action("slip", "moving", lead=0.25, dur=1.0, summary="a foot shoots out, arms windmill, down on the back")
def slip(A, t):
    a = A.a
    a.expr("surprised", t, 0.05)
    if A.has_legs():
        a.legs(70, 10, t + A.d(0.18), A.d(0.14), side="R", ground=False)
    a.pose({"L": (150, 20, "out"), "R": (120, -30, "out"), "hands": "open"}, t + A.d(0.2), A.d(0.16))
    a.pose({"L": (60, 60, "out"), "R": (165, 10, "out")}, t + A.d(0.4), A.d(0.18))
    p = a.position()
    a.rock(-86, t + A.d(0.7), A.d(0.45), pivot=0.0)
    a.move(t + A.d(0.2), t + A.d(0.7), (p.x, p.y, p.z + 0.14 * a.scale), arc=0.22, land=False)
    if A.has_legs():
        a.legs(20, 30, t + A.d(0.75), A.d(0.2), ground=False)
    a.squash(t + A.d(0.72), 0.16, 0.05, 0.22)
    a.floating = True
    return t + A.d(1.0)


@action("jump", "moving", lead=0.3, dur=0.8, summary="jump on the spot or to a place (to=): crouch, leave the ground, land with a squash")
def jump(A, t, to=None, height=0.35):
    a = A.a
    a.squash(t + A.d(0.16), 0.12, 0.06, 0.06)
    a.pose({"L": (-30, 20), "R": (-30, 20), "views": {"front": {"L": (20, 10, "out"), "R": (20, 10, "out")}}}, t + A.d(0.18), A.d(0.16))
    a.pose("hands_up", t + A.d(0.42), A.d(0.2))
    p = a.position()
    dest = to if to is not None else (p.x, p.y, p.z)
    t1 = a.move(t + A.d(0.28), t + A.d(0.28) + A.d(0.42), dest, arc=height * a.scale)
    A.rest(t1 + A.d(0.28), A.d(0.25), legs=False)
    return t1 + A.d(0.28)


@action("climb", "moving", lead=0.2, dur=2.0, needs=("to",), summary="climb up or down to a place (ladder, rope, wall): hands reach one after the other")
def climb(A, t, to=None, rate=0.55):
    a = A.a
    p = a.position()
    dest = Vector((to[0], to[1], to[2] if len(to) > 2 else p.z))
    a.view("front", t)
    secs = max(A.d(0.6), (dest - p).length / (rate * A.k))
    t1 = a.move(t + A.d(0.15), t + A.d(0.15) + secs, tuple(dest), linear=True, land=False)
    a.floating = True

    def step(i, tt):
        hi, lo = (168, 6, "out"), (120, 46, "out")
        a.pose({"L": hi if i % 2 else lo, "R": lo if i % 2 else hi, "hands": "fist"}, tt, A.d(0.2))
        if A.has_legs():
            a.legs(46, 70, tt, A.d(0.2), side="L" if i % 2 else "R", ground=False)
            a.legs(6, 10, tt, A.d(0.2), side="R" if i % 2 else "L", ground=False)

    A.pulse(step, t + A.d(0.15), t1, every=0.3)
    if A.has_legs():
        a.legs(0, 0, t1 + A.d(0.2), A.d(0.2), ground=False)
    a.pose("rest", t1 + A.d(0.25), A.d(0.25))
    a.floating = False
    return t1 + A.d(0.25)


@action("hang", "moving", lead=0.3, dur=2.0, summary="hang from the hands (a branch, a rope, a ledge) and swing a little", loops=True)
def hang(A, t, until=None, swing=7.0):
    a = A.a
    t1 = until if until is not None else t + A.d(2.0)
    a.view("front", t)
    a.pose("hang", t + A.d(0.25), A.d(0.25))
    a.floating = True
    A.pulse(lambda i, tt: a.rock((swing if i % 2 else -swing) * (0 if tt >= t1 - 1e-3 else 1), tt, A.d(0.55), pivot=a.height), t + A.d(0.3), t1, every=0.6)
    if A.has_legs():
        A.pulse(lambda i, tt: a.legs(10 if i % 2 else -8, 14, tt, A.d(0.5), ground=False), t + A.d(0.3), t1, every=0.6)
    return t1


@action("swim", "moving", lead=0.0, dur=3.0, summary="tread water or swim to a place (to=): body low, arms sweeping (mermaid: tail strokes)", loops=True)
def swim(A, t, to=None, until=None):
    a = A.a
    t1 = until if until is not None else t + A.d(3.0)
    a.floating = True
    if to is not None:
        t1 = A.glide(t, to, 0.8, bob=0.04, period=0.6)
    A.pulse(lambda i, tt: a.pose({"L": (70 if i % 2 else 110, 30, "out"), "R": (110 if i % 2 else 70, 30, "out"), "hands": "open"}, tt, A.d(0.4)),
            t, t1, every=0.45)
    return t1


@action("crawl", "moving", lead=0.4, dur=2.5, needs=("to",), summary="down on the belly and pull forward with the arms to a place")
def crawl(A, t, to=None):
    a = A.a
    p = a.position()
    A.face(Vector((to[0], to[1], p.z)), t)
    a.view("side", t)
    a.rock(82, t + A.d(0.4), A.d(0.4), pivot=0.0)
    a.move(t, t + A.d(0.4), (p.x, p.y, p.z + 0.14 * a.scale), land=False)
    dest = Vector((to[0], to[1], p.z + 0.14 * a.scale))
    secs = max(A.d(0.8), (dest - p).length / (0.45 * A.k))
    t1 = a.move(t + A.d(0.45), t + A.d(0.45) + secs, tuple(dest), linear=True, land=False)
    a.floating = True
    A.pulse(lambda i, tt: a.pose({"R": (150 if i % 2 else 100, 30), "L": (100 if i % 2 else 150, 30), "hands": "fist"}, tt, A.d(0.3)),
            t + A.d(0.45), t1, every=0.4)
    return t1


@action("roll", "moving", lead=0.2, dur=1.2, needs=("to",), summary="roll along the ground to a place like a log")
def roll(A, t, to=None, turns=2):
    a = A.a
    p = a.position()
    a.pose({"L": (20, 110), "R": (20, 110), "hands": "fist"}, t + A.d(0.15), A.d(0.15))
    t1 = t + A.d(1.1)
    a.tilt.location.z = a.height * 0.5
    a.root.location.z = -a.height * 0.5
    f0, f1 = a._f(t + A.d(0.1)), a._f(t1)
    a.tilt.keyframe_insert("rotation_euler", index=1, frame=f0)
    a.tilt.rotation_euler.y = math.radians(90 + 360 * turns) * a._face
    a.tilt.keyframe_insert("rotation_euler", index=1, frame=f1)
    a.move(t + A.d(0.1), t1, (to[0], to[1], (to[2] if len(to) > 2 else p.z) - a.height * 0.5 + 0.16 * a.scale), linear=True, land=False)
    a.floating = True
    return t1


@action("struggle", "moving", lead=0.2, dur=2.0, summary="stuck fast (mud, a trap, a grip): strain upward, twist, strain again", loops=True)
def struggle(A, t, until=None):
    a = A.a
    t1 = until if until is not None else t + A.d(2.0)
    a.expr("worried", t, 0.1)

    def pull_(i, tt):
        a.pose({"L": (130 if i % 2 else 60, 40, "out"), "R": (60 if i % 2 else 130, 40, "out"), "hands": "fist", "lean": -10 if i % 2 else 12}, tt, A.d(0.28))
        a.squash(tt, -0.07 if i % 2 else 0.06, 0.05, 0.12)

    A.pulse(pull_, t + A.d(0.2), t1, every=0.38)
    a.shake(t, t1, 1.6, 10)
    return t1


@action("lean_on", "moving", lead=0.4, dur=0.7, summary="lean the weight forward onto something (a counter, a staff, a wall)")
def lean_on(A, t, target=None, deg=18):
    a = A.a
    if target is not None:
        A.face(target, t)
        a.lean(deg * 0.6, t + A.d(0.3), A.d(0.3))
        a.reach("R", target, t + A.d(0.5), A.d(0.3))
        a.hand("R", "open", t + A.d(0.45), 0.1)
    else:
        a.pose({"R": (50, 40), "L": (40, 50), "hands": "open"}, t + A.d(0.45), A.d(0.3))
    a.lean(deg, t + A.d(0.6), A.d(0.3))
    return t + A.d(0.7)


@action("turn_around", "moving", lead=0.2, dur=0.45, summary="turn sharply to face the other way")
def turn_around(A, t):
    a = A.a
    a.squash(t + A.d(0.12), 0.07, 0.03, 0.1)
    a.face("left" if a._face > 0 else "right", t + A.d(0.2))
    a.eyes(1.0, 0.0, t + A.d(0.2), 0.0)
    return t + A.d(0.45)


@action("freeze", "moving", lead=0.1, dur=1.5, summary="stop dead mid-movement and hold perfectly still, wide-eyed", loops=True)
def freeze(A, t, until=None):
    a = A.a
    a.expr("surprised", t, 0.05, amount=0.8)
    a.squash(t + A.d(0.06), -0.06, 0.04, 0.08)
    a.pose({"L": (34, 46, "out"), "R": (34, 46, "out"), "hands": "open", "lean": -3}, t + A.d(0.12), A.d(0.1))
    return until if until is not None else t + A.d(1.5)


@action("recoil", "moving", lead=0.15, dur=0.7, summary="jerk back from something: hands up in front, body back, a half step away")
def recoil(A, t, target=None):
    a = A.a
    if target is not None:
        A.face(target, t)
    a.expr("surprised", t, 0.05)
    a.pose({"L": (78, 60), "R": (70, 70), "hands": "open", "lean": -16, "tilt": -8}, t + A.d(0.16), A.d(0.14))
    a.squash(t + A.d(0.1), -0.08, 0.04, 0.12)
    p = a.position()
    cam = bpy.context.scene.camera
    right = (cam.matrix_world.to_3x3() @ Vector((1, 0, 0))) if cam else Vector((1, 0, 0))
    q = p - right * 0.22 * a._face * a.scale
    a.move(t + A.d(0.08), t + A.d(0.3), (q.x, q.y, p.z), arc=0.05, land=False)
    a.lean(-6, t + A.d(0.6), A.d(0.3))
    return t + A.d(0.7)


@action("ride", "moving", lead=0.3, dur=2.0, summary="seated holding reins or a wheel (horse, cart, car): hands forward, a steady bob", loops=True)
def ride(A, t, until=None, bob=True):
    a = A.a
    t1 = until if until is not None else t + A.d(2.0)
    a.pose({"L": (52, 40), "R": (58, 34), "hands": "fist", "legs": (70, 60)}, t + A.d(0.3), A.d(0.3))
    a.floating = True
    if bob:
        A.pulse(lambda i, tt: a.squash(tt, 0.035, 0.03, 0.14), t + A.d(0.3), t1, every=0.34)
    return t1


# ============================================================================= HANDS AND PROPS
@action("pick_up", "hands", lead=0.55, dur=1.2, needs=("prop",), summary="look at a thing, bend to it, close the hand on it and bring it up (both=True: with two hands)")
def pick_up(A, t, target=None, side="R", both=False, lift_to=None):
    a = A.a
    prop = target
    A.face(prop, t)
    A.look(prop, t, 0.12)                                     # eyes lead
    a.lean(-4, t + A.d(0.12), A.d(0.12))                      # a small breath back
    z = core.point_of(prop).z
    low = A.crouch_for(z, t + A.d(0.45), A.d(0.3))
    a.hand(side, "open", t + A.d(0.3), 0.1)
    tg = t + A.d(0.55)
    a.reach(side, prop, tg, A.d(0.3))
    if both:
        a.hand("L", "open", t + A.d(0.3), 0.1)
        a.reach("L", prop, tg, A.d(0.3))
    a.hold(prop, side, tg)
    a.squash(tg + A.d(0.04), 0.04, 0.03, 0.1)
    up = tg + A.d(0.5)
    a.lean(0, up, A.d(0.4))
    a.tilt_head(0, up, A.d(0.3))
    if low:
        a.legs(0, 0, up, A.d(0.4))
    spec = lift_to or ((48, 62) if both else (52, 66))
    a.arm(side, spec[0], spec[1], up, A.d(0.42))
    if both:
        a.arm("L", spec[0] + 6, spec[1], up, A.d(0.42))
        a.hand("L", "fist", up, 0.1)
    A.look(prop, up - A.d(0.1))
    return up + A.d(0.1)


@action("put_down", "hands", lead=0.5, dur=1.0, needs=("prop", "to"), summary="set a held thing down on a place and take the hand away")
def put_down(A, t, target=None, to=None, side="R"):
    a = A.a
    prop = target
    dest = Vector((to[0], to[1], to[2] if len(to) > 2 else 0.0))
    A.face(dest, t)
    A.look(dest, t, 0.12)
    low = A.crouch_for(dest.z, t + A.d(0.4), A.d(0.3))
    tr = t + A.d(0.5)
    a.reach(side, dest, tr, A.d(0.32))
    a.release(prop, tr + A.d(0.04))
    core.key(prop, "location", tr + A.d(0.12), tuple(dest))
    up = tr + A.d(0.45)
    a.lean(0, up, A.d(0.35))
    a.tilt_head(0, up, A.d(0.3))
    if low:
        a.legs(0, 0, up, A.d(0.35))
    a.pose("rest", up, A.d(0.35))
    return up


@action("carry", "hands", lead=0.3, dur=0.6, needs=("prop",), summary="take a thing in both arms in front of the chest and keep it there (then walk with arms=False)")
def carry(A, t, target=None, side="R", offset=(0.06, 0.0, 0.02)):
    a = A.a
    a.pose("carry", t + A.d(0.3), A.d(0.3))
    a.hold(target, side, t + A.d(0.3), offset=offset)
    a.hand("L", "fist", t + A.d(0.3), 0.1)
    a.lean(-3, t + A.d(0.4), A.d(0.2))
    return t + A.d(0.5)


@action("haul", "hands", lead=0.4, dur=2.0, needs=("prop", "to"), summary="drag a heavy thing to a place: both hands on it, body thrown against the weight")
def haul(A, t, target=None, to=None):
    a = A.a
    prop = target
    A.face(prop, t)
    A.crouch_for(core.point_of(prop).z + 0.2, t + A.d(0.3), A.d(0.25))
    a.reach("R", prop, t + A.d(0.4), A.d(0.3))
    a.reach("L", prop, t + A.d(0.4), A.d(0.3))
    off = core.point_of(prop) - a.position()
    a.hold(prop, "R", t + A.d(0.4))
    a.hand("L", "fist", t + A.d(0.4), 0.1)
    a.lean(-18, t + A.d(0.6), A.d(0.2))
    if A.has_legs():
        a.legs(0, 0, t + A.d(0.74), A.d(0.32))                    # up out of the crouch before the first step, not in one frame
    a.expr("angry", t + A.d(0.4), 0.1, amount=0.5)
    t1 = A.go(t + A.d(0.74), to, "walk", 1.1, arms=False)
    a.shake(t + A.d(0.74), t1, 1.2, 7)
    return t1


@action("throw", "hands", lead=0.45, dur=0.9, needs=("prop",), summary="wind up and throw a held thing to a place (to=) or just ahead")
def throw(A, t, target=None, to=None, side="R", arc=0.7):
    a = A.a
    prop = target
    if to is not None:
        A.face(Vector((to[0], to[1], 0)), t)
        A.look(Vector((to[0], to[1], to[2] if len(to) > 2 else 1.0)), t, 0.1)
    if prop.name not in a._held:
        a.hold(prop, side, t)
    a.pose("throw_back", t + A.d(0.28), A.d(0.26))
    a.squash(t + A.d(0.3), 0.05, 0.03, 0.08)
    tr = t + A.d(0.45)
    a.pose("throw_fwd", tr + A.d(0.06), A.d(0.16))
    start = a.release(prop, tr)
    cam = bpy.context.scene.camera
    right = (cam.matrix_world.to_3x3() @ Vector((1, 0, 0))) if cam else Vector((1, 0, 0))
    dest = Vector((to[0], to[1], to[2] if len(to) > 2 else 0.0)) if to is not None else start + right * 2.2 * a._face - Vector((0, 0, start.z))
    f0, f1 = a._f(tr), a._f(tr + A.d(0.5))
    mid = (start + dest) / 2
    mid.z = max(start.z, dest.z) + arc
    prop.location = mid
    core.key_frame(prop, "location", (f0 + f1) // 2)
    prop.location = dest
    core.key_frame(prop, "location", f1)
    A.rest(tr + A.d(0.55), A.d(0.3), legs=False)
    return tr + A.d(0.55)


@action("drop", "hands", lead=0.2, dur=0.7, needs=("prop",), summary="the hand opens and the held thing falls to the ground")
def drop(A, t, target=None, ground_z=None):
    a = A.a
    prop = target
    tr = t + A.d(0.2)
    start = a.release(prop, tr)
    gz = ground_z if ground_z is not None else a.position().z + 0.03
    f0, f1 = a._f(tr), a._f(tr + A.d(0.32))
    prop.location = (start.x, start.y, gz)
    core.key_frame(prop, "location", f1)
    for fc in core.fcurves(prop):
        if fc.data_path == "location":
            for kp in fc.keyframe_points:
                if abs(kp.co.x - f0) < 0.5:
                    kp.interpolation, kp.easing = "QUAD", "EASE_IN"
    return tr + A.d(0.5)


@action("hold_up", "hands", lead=0.4, dur=0.8, summary="raise the hand (and whatever it holds) high to show it")
def hold_up(A, t, target=None, side="R", high=True):
    a = A.a
    if target is not None and target.name not in a._held:
        a.hold(target, side, t)
    a.lean(3, t + A.d(0.14), A.d(0.14))
    a.arm(side, 132 if high else 96, 22, t + A.d(0.45), A.d(0.32))
    a.lean(-5, t + A.d(0.5), A.d(0.25))
    a.tilt_head(-8, t + A.d(0.5), A.d(0.25))
    a.eyes(0.7, 0.8, t + A.d(0.3), 0.1)
    return t + A.d(0.8)


@action("show", "hands", lead=0.35, dur=0.7, summary="hold a thing out in front for someone to see (chest height)")
def show(A, t, target=None, side="R", to=None):
    a = A.a
    if to is not None:
        A.face(to, t)
        A.look(to, t + A.d(0.3))
    if target is not None and target.name not in a._held:
        a.hold(target, side, t)
    a.arm(side, 74, 24, t + A.d(0.4), A.d(0.34))
    a.lean(4, t + A.d(0.45), A.d(0.25))
    return t + A.d(0.7)


@action("point", "hands", lead=0.3, dur=0.6, needs=("target",), summary="turn to a thing and point straight at it with one finger")
def point(A, t, target=None, side="R", hold=0.0):
    a = A.a
    A.face(target, t)
    A.look(target, t, 0.1)
    a.lean(-3, t + A.d(0.1), A.d(0.1))
    a.hand(side, "point", t + A.d(0.16), 0.08)
    a.aim(side, target, t + A.d(0.3), A.d(0.22))
    a.lean(5, t + A.d(0.34), A.d(0.16))
    return t + A.d(0.6) + hold


@action("hold_up_finger", "hands", lead=0.3, dur=0.6, summary='one finger raised: "one rule", a warning, an idea')
def hold_up_finger(A, t, side="R"):
    a = A.a
    a.pose("point_up", t + A.d(0.3), A.d(0.24), side=side)
    a.squash(t + A.d(0.3), -0.04, 0.03, 0.1)
    a.tilt_head(-4, t + A.d(0.3), A.d(0.2))
    return t + A.d(0.6)


@action("wave", "hands", lead=0.35, dur=1.3, summary="raise an open hand and wave it (greeting, goodbye, waving someone on)")
def wave(A, t, target=None, side="R", times=3):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.look(target, t)
    a.expr("happy", t, 0.12)
    a.pose("wave", t + A.d(0.32), A.d(0.28), side=side)
    tt = t + A.d(0.32)
    for i in range(times * 2):
        tt += A.d(0.14)
        for s_ in "LR":                                           # whichever arm is up in the view that shows
            a._wag(s_, 18 if i % 2 == 0 else -18, tt, A.d(0.14))
    for s_ in "LR":
        a._wag(s_, 0, tt + A.d(0.1), A.d(0.1))
    A.rest(tt + A.d(0.4), A.d(0.3), legs=False)
    return tt + A.d(0.4)


@action("beckon", "hands", lead=0.35, dur=1.1, summary="palm up, curl the hand toward the body twice: come here")
def beckon(A, t, target=None, side="R", times=2):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.look(target, t)
    a.hand(side, "open", t + A.d(0.2), 0.1)
    a.arm(side, 70, 20, t + A.d(0.3), A.d(0.26))
    tt = t + A.d(0.3)
    for i in range(times):
        a.arm(side, 62, 86, tt + A.d(0.18), A.d(0.16))
        a.hand(side, "mitten", tt + A.d(0.18), 0.08)
        a.arm(side, 70, 20, tt + A.d(0.36), A.d(0.16))
        a.hand(side, "open", tt + A.d(0.36), 0.08)
        tt += A.d(0.36)
    A.rest(tt + A.d(0.3), A.d(0.28), legs=False)
    return tt + A.d(0.3)


@action("push", "hands", lead=0.45, dur=1.0, needs=("target",), summary="both hands on a thing and shove (by=(dx, dy) also moves the thing)")
def push(A, t, target=None, by=None):
    a = A.a
    A.face(target, t)
    A.look(target, t)
    a.lean(-6, t + A.d(0.15), A.d(0.15))
    a.hand("R", "open", t + A.d(0.2), 0.1)
    a.hand("L", "open", t + A.d(0.2), 0.1)
    a.reach("R", target, t + A.d(0.4), A.d(0.25))
    a.reach("L", target, t + A.d(0.4), A.d(0.25))
    th = t + A.d(0.45)
    a.lean(16, th + A.d(0.2), A.d(0.2))
    a.squash(th, 0.05, 0.03, 0.1)
    if by is not None and hasattr(target, "location"):
        q = Vector(target.location) + Vector((by[0], by[1], by[2] if len(by) > 2 else 0.0))
        core.move(target, th, th + A.d(0.35), location=q)
        core.at_frame(a._f(th + A.d(0.35)))
        a.reach("R", target, th + A.d(0.35), A.d(0.33))
        a.reach("L", target, th + A.d(0.35), A.d(0.33))
    return th + A.d(0.55)


@action("pull", "hands", lead=0.45, dur=1.0, needs=("target",), summary="grab a thing with both hands and heave back (by=(dx, dy) also moves the thing)")
def pull(A, t, target=None, by=None):
    a = A.a
    A.face(target, t)
    A.look(target, t)
    a.lean(10, t + A.d(0.3), A.d(0.25))
    a.reach("R", target, t + A.d(0.4), A.d(0.25))
    a.reach("L", target, t + A.d(0.4), A.d(0.25))
    a.hand("R", "fist", t + A.d(0.4), 0.06)
    a.hand("L", "fist", t + A.d(0.4), 0.06)
    th = t + A.d(0.45)
    a.squash(th, 0.05, 0.03, 0.08)
    a.lean(-14, th + A.d(0.3), A.d(0.28))
    a.expr("angry", th, 0.1, amount=0.4)
    if by is not None and hasattr(target, "location"):
        q = Vector(target.location) + Vector((by[0], by[1], by[2] if len(by) > 2 else 0.0))
        core.move(target, th, th + A.d(0.35), location=q)
        core.at_frame(a._f(th + A.d(0.35)))
        a.reach("R", target, th + A.d(0.35), A.d(0.33))
        a.reach("L", target, th + A.d(0.35), A.d(0.33))
    else:
        a.pose("pull", th + A.d(0.3), A.d(0.28))
    return th + A.d(0.55)


@action("lift", "hands", lead=0.5, dur=1.2, needs=("prop",), summary="take a thing in both hands and lift it overhead (by= metres up: the hands stay on a thing that slides, like a gate)")
def lift(A, t, target=None, by=None):
    a = A.a
    prop = target
    A.face(prop, t)
    A.look(prop, t)
    A.crouch_for(core.point_of(prop).z, t + A.d(0.4), A.d(0.3))
    tg = t + A.d(0.5)
    a.reach("R", prop, tg, A.d(0.3))
    a.reach("L", prop, tg, A.d(0.3))
    a.hand("L", "fist", tg, 0.06)
    a.squash(tg + A.d(0.05), 0.07, 0.04, 0.1)
    up = tg + A.d(0.55)
    if by is not None:
        a.hand("R", "fist", tg, 0.06)
        q = Vector(prop.location) + Vector((0, 0, by))
        core.move(prop, tg + A.d(0.1), up, location=q)
        core.at_frame(a._f(up))
        a.reach("R", prop, up, A.d(0.42))
        a.reach("L", prop, up, A.d(0.42))
        a.lean(-9, up, A.d(0.4))
    else:
        a.hold(prop, "R", tg)
        a.pose("lift", up, A.d(0.45))
        if getattr(a, "_sink", None) and any(a._sink):
            a.legs(0, 0, up, A.d(0.4))
    a.expr("angry", tg, 0.1, amount=0.35)
    return up + A.d(0.15)


@action("open_door", "hands", lead=0.4, dur=0.9, needs=("target",), summary="hand on the handle and swing it (door= the leaf object, deg= how far): also close_door with a negative deg")
def open_door(A, t, target=None, door=None, deg=80.0, side="R"):
    a = A.a
    A.face(target, t)
    A.look(target, t)
    a.reach(side, target, t + A.d(0.35), A.d(0.28))
    a.hand(side, "fist", t + A.d(0.35), 0.06)
    th = t + A.d(0.4)
    if door is not None:
        r = door.rotation_euler
        core.move(door, th, th + A.d(0.4), rotation_deg=(math.degrees(r.x), math.degrees(r.y), math.degrees(r.z) + deg))
        core.at_frame(a._f(th + A.d(0.4)))
        a.reach(side, target, th + A.d(0.4), A.d(0.38))
    a.lean(-8 if deg > 0 else 8, th + A.d(0.3), A.d(0.3))
    A.rest(th + A.d(0.75), A.d(0.3), legs=False)
    return th + A.d(0.75)


@action("turn_key", "hands", lead=0.4, dur=0.9, needs=("target",), summary="hand to a lock, a handle or a dial and twist the wrist (lock, unlock, turn a knob)")
def turn_key(A, t, target=None, side="R", prop=None):
    a = A.a
    A.face(target, t)
    A.look(target, t)
    if prop is not None and prop.name not in a._held:
        a.hold(prop, side, t, turn=True)
    a.reach(side, target, t + A.d(0.4), A.d(0.3))
    a.hand(side, "pinch" if prop is None else "grip", t + A.d(0.36), 0.06)
    a.wrist(side, -70, t + A.d(0.62), A.d(0.16))
    a.wrist(side, 0, t + A.d(0.82), A.d(0.14))
    return t + A.d(0.9)


@action("press", "hands", lead=0.35, dur=0.6, needs=("target",), summary="jab a button, a switch or a bell with one finger (palm=True: slap it with the flat hand)")
def press(A, t, target=None, side="R", palm=False):
    a = A.a
    A.face(target, t)
    A.look(target, t)
    a.hand(side, "open" if palm else "point", t + A.d(0.12), 0.08)
    a.arm(side, 60, 70, t + A.d(0.2), A.d(0.18))
    a.reach(side, target, t + A.d(0.35), A.d(0.12))
    a.squash(t + A.d(0.36), 0.03, 0.02, 0.08)
    a.arm(side, 56, 60, t + A.d(0.55), A.d(0.16))
    return t + A.d(0.6)


@action("tap", "hands", lead=0.3, dur=1.2, summary="tap things one by one with a finger (counting): targets=[...] or the air in front")
def tap(A, t, targets=None, side="R", times=3):
    a = A.a
    a.hand(side, "point", t + A.d(0.1), 0.08)
    tt = t + A.d(0.1)
    items = list(targets) if targets else [None] * times
    for i, it in enumerate(items):
        if it is not None:
            A.look(it, tt)
            a.reach(side, it, tt + A.d(0.22), A.d(0.16))
        else:
            a.arm(side, 62 + 8 * i, 30, tt + A.d(0.22), A.d(0.16))
        a.arm(side, a._arm[side][0] + 10, a._arm[side][1] + 16, tt + A.d(0.34), A.d(0.1), plane=a._arm[side][2])
        tt += A.d(0.36)
    return tt


@action("knock", "hands", lead=0.35, dur=1.0, summary="rap on a door with the knuckles three times")
def knock(A, t, target=None, side="R", times=3):
    a = A.a
    if target is not None:
        A.face(target, t)
    a.hand(side, "fist", t + A.d(0.15), 0.08)
    a.arm(side, 80, 78, t + A.d(0.3), A.d(0.26))
    tt = t + A.d(0.3)
    for _ in range(times):
        a.arm(side, 86, 52, tt + A.d(0.09), A.d(0.08))
        a.arm(side, 80, 78, tt + A.d(0.2), A.d(0.1))
        tt += A.d(0.2)
    A.rest(tt + A.d(0.3), A.d(0.28), legs=False)
    return tt + A.d(0.3)


@action("take_out", "hands", lead=0.45, dur=0.9, summary="hand into a pocket or bag and out again holding a thing (prop appears in the hand)")
def take_out(A, t, target=None, side="R", spot="pocket"):
    a = A.a
    a.eyes(0.2, -0.8, t, 0.1)
    a.pose({side: ("to", spot), "hands": {side: "mitten"}}, t + A.d(0.3), A.d(0.28))
    tg = t + A.d(0.45)
    if target is not None:
        core.show(target, tg, True)
        a.hold(target, side, tg)
    a.arm(side, 62, 58, tg + A.d(0.35), A.d(0.3))
    a.eyes(0.6, -0.2, tg + A.d(0.2), 0.1)
    return tg + A.d(0.45)


@action("stash", "hands", lead=0.4, dur=0.8, summary="tuck a held thing away into a pocket, a bag or under the coat (it disappears)")
def stash(A, t, target=None, side="R", spot="pocket"):
    a = A.a
    a.eyes(-0.6, 0.0, t, 0.1)                                # a glance over the shoulder first
    a.pose({side: ("to", spot)}, t + A.d(0.4), A.d(0.3))
    if target is not None:
        a.release(target, t + A.d(0.42), hand=None)
        core.show(target, t + A.d(0.42), False)
    a.hand(side, "mitten", t + A.d(0.45), 0.08)
    A.rest(t + A.d(0.8), A.d(0.3), legs=False)
    return t + A.d(0.8)


@action("use_tool", "hands", lead=0.4, dur=2.0, summary="work a held tool in strokes: kind = dig | sweep | mop | hammer | saw | stir | cut | paint | scrub | chop", loops=True)
def use_tool(A, t, target=None, kind="sweep", until=None, strokes=None, side="R"):
    a = A.a
    two = kind in ("dig", "sweep", "mop", "chop")
    A_, B_ = {  # two arm states per kind: (R, L) at the back of the stroke and at the front
        "dig": (((70, 40), (40, 70), 20), ((40, 30), (26, 60), 34)), "sweep": (((84, 22), (62, 58), 8), ((52, 30), (34, 62), 14)),
        "mop": (((84, 22), (62, 58), 8), ((56, 22), (36, 58), 16)), "chop": (((150, 30), (140, 40), -12), ((50, 20), (44, 30), 22)),
        "hammer": (((96, 70), None, 0), ((62, 40), None, 6)), "saw": (((54, 78), None, 10), ((70, 34), None, 14)),
        "stir": (((58, 60), None, 8), ((66, 44), None, 8)), "cut": (((58, 66), None, 10), ((62, 58), None, 10)),
        "paint": (((100, 30), None, -2), ((72, 44), None, 2)), "scrub": (((44, 48), None, 34), ((58, 30), None, 34)),
    }[kind]
    if target is not None and target.name not in a._held:
        a.hold(target, side, t, turn=True)
    t0 = t + A.d(0.3)
    t1 = until if until is not None else t0 + A.d(0.44) * (strokes or 4)
    other = "L" if side == "R" else "R"

    def stroke(i, tt):
        st = A_ if i % 2 == 0 else B_
        a.arm(side, st[0][0], st[0][1], tt, A.d(0.2))
        if two and st[1]:
            a.arm(other, st[1][0], st[1][1], tt, A.d(0.2))
            a.hand(other, "fist", tt, 0.1)
        a.lean(st[2], tt, A.d(0.2))
        if kind in ("hammer", "chop") and i % 2 == 1:
            a.squash(tt, 0.04, 0.02, 0.08)

    A.pulse(stroke, t0, t1, every=0.22)
    return t1


@action("pour", "hands", lead=0.5, dur=1.3, summary="tip a held jug, bottle or bucket so it pours (over to= if given)")
def pour(A, t, target=None, to=None, side="R"):
    a = A.a
    if to is not None:
        A.face(to, t)
        A.look(to, t)
    if target is not None and target.name not in a._held:
        a.hold(target, side, t, turn=True)
    a.arm(side, 78, 34, t + A.d(0.35), A.d(0.3))
    a.wrist(side, 78, t + A.d(0.6), A.d(0.24))
    a.lean(6, t + A.d(0.6), A.d(0.25))
    a.wrist(side, 78, t + A.d(1.0), 0.0)
    a.wrist(side, 0, t + A.d(1.25), A.d(0.22))
    return t + A.d(1.3)


@action("drink", "hands", lead=0.5, dur=1.4, summary="lift a held cup to the mouth, tip it, lower it")
def drink(A, t, target=None, side="R"):
    a = A.a
    if target is not None and target.name not in a._held:
        a.hold(target, side, t, turn=True)
    a.pose("drink", t + A.d(0.45), A.d(0.4), side=side)
    a.wrist(side, -40, t + A.d(0.6), A.d(0.18))
    a.eyes_closed(t + A.d(0.55), t + A.d(1.0))
    a.wrist(side, 0, t + A.d(1.1), A.d(0.16))
    a.arm(side, 54, 62, t + A.d(1.35), A.d(0.3))
    a.tilt_head(0, t + A.d(1.3), A.d(0.25))
    return t + A.d(1.4)


@action("eat", "hands", lead=0.45, dur=1.6, summary="bring a held bite to the mouth and chew")
def eat(A, t, target=None, side="R", bites=1):
    a = A.a
    if target is not None and target.name not in a._held:
        a.hold(target, side, t)
    tt = t
    for _ in range(bites):
        a.pose({side: ("to", "mouth"), "hands": {}}, tt + A.d(0.4), A.d(0.36))
        a.ctrl_pulse("viseme_A", tt + A.d(0.34), tt + A.d(0.5))
        a.arm(side, 50, 70, tt + A.d(0.75), A.d(0.28))
        a.chew(tt + A.d(0.55), tt + A.d(1.5))
        tt += A.d(1.5)
    return tt


@action("read", "hands", lead=0.4, dur=2.0, summary="hold a paper or book up in both hands and read it, eyes moving along the lines", loops=True)
def read(A, t, target=None, until=None, side="R"):
    a = A.a
    if target is not None and target.name not in a._held:
        a.hold(target, side, t, offset=(0.08, 0.0, 0.03))
    a.pose("read", t + A.d(0.4), A.d(0.35))
    t1 = until if until is not None else t + A.d(2.0)
    A.pulse(lambda i, tt: a.eyes(0.9 if i % 2 else 0.3, -0.5, tt, A.d(0.3)), t + A.d(0.4), t1, every=0.45)
    return t1


@action("write", "hands", lead=0.4, dur=2.0, summary="bend over a page and write, the hand making small quick strokes", loops=True)
def write(A, t, target=None, until=None, side="R", on=None):
    a = A.a
    if target is not None and target.name not in a._held:
        a.hold(target, side, t, turn=True)
    a.pose("write", t + A.d(0.4), A.d(0.35))
    if on is not None:
        a.reach(side, on, t + A.d(0.4), A.d(0.3))
    t1 = until if until is not None else t + A.d(2.0)
    a.eyes(0.5, -0.9, t + A.d(0.3))
    A.pulse(lambda i, tt: a._wag(side, 7 if i % 2 else -7, tt, A.d(0.1)), t + A.d(0.45), t1, every=0.13)
    a._wag(side, 0, t1 + A.d(0.1), A.d(0.1))
    return t1


@action("tie", "hands", lead=0.4, dur=1.6, summary="both hands busy together in front (tie a knot, fasten, button, unwrap)", loops=True)
def tie(A, t, target=None, until=None, low=False):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.crouch_for(core.point_of(target).z, t + A.d(0.3), A.d(0.25))
        a.reach("R", target, t + A.d(0.4), A.d(0.3))
        a.reach("L", target, t + A.d(0.4), A.d(0.3))
    else:
        a.pose({"L": ("to", "belly" if low else "chest"), "R": ("to", "belly" if low else "chest", 0.03, 0.03), "hands": "pinch", "tilt": 14}, t + A.d(0.4), A.d(0.3))
    t1 = until if until is not None else t + A.d(1.6)
    A.pulse(lambda i, tt: (a._wag("R", 9 if i % 2 else -9, tt, A.d(0.12)), a._wag("L", -9 if i % 2 else 9, tt, A.d(0.12))), t + A.d(0.45), t1, every=0.16)
    a._wag("R", 0, t1 + A.d(0.1), A.d(0.1))
    a._wag("L", 0, t1 + A.d(0.1), A.d(0.1))
    return t1


@action("light", "hands", lead=0.5, dur=1.0, summary="strike a match / touch a flame to a thing held in the other hand or at a place")
def light(A, t, target=None, side="R"):
    a = A.a
    a.pose({"L": (52, 66), "R": (44, 80), "hands": "pinch", "tilt": 10}, t + A.d(0.3), A.d(0.28))
    a.arm(side, 60, 40, t + A.d(0.45), A.d(0.08))            # the strike
    if target is not None:
        A.look(target, t + A.d(0.5))
        a.reach(side, target, t + A.d(0.8), A.d(0.25))
    return t + A.d(1.0)


@action("blow", "hands", lead=0.35, dur=0.7, summary="lean in and blow (out a candle, on hot soup, dust off a book)")
def blow(A, t, target=None):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.look(target, t)
    a.lean(14, t + A.d(0.3), A.d(0.26))
    a.squash(t + A.d(0.2), -0.05, 0.04, 0.08)
    a.ctrl_pulse("viseme_U", t + A.d(0.3), t + A.d(0.6))
    a.lean(4, t + A.d(0.7), A.d(0.2))
    return t + A.d(0.7)


@action("phone", "hands", lead=0.4, dur=2.0, summary="hold a phone or a radio to the ear and talk (screen=True: hold it in front and look at it)", loops=True)
def phone(A, t, target=None, until=None, side="R", screen=False):
    a = A.a
    if target is not None and target.name not in a._held:
        a.hold(target, side, t)
    if screen:
        a.arm(side, 62, 76, t + A.d(0.4), A.d(0.34))
        a.eyes(0.6, -0.5, t + A.d(0.3))
        a.tilt_head(8, t + A.d(0.4), A.d(0.3))
    else:
        a.pose("phone", t + A.d(0.4), A.d(0.34), side=side)
    return until if until is not None else t + A.d(2.0)


@action("aim", "hands", lead=0.35, dur=0.7, needs=("target",), summary="level a held thing at a target and keep it there (flashlight, pistol, sword, wand)")
def aim(A, t, target=None, side="R", prop=None):
    a = A.a
    A.face(target, t)
    A.look(target, t)
    if prop is not None and prop.name not in a._held:
        a.hold(prop, side, t, turn=True)
    a.lean(-4, t + A.d(0.12), A.d(0.12))
    a.aim(side, target, t + A.d(0.35), A.d(0.24))
    a.lean(6, t + A.d(0.4), A.d(0.16))
    return t + A.d(0.7)


@action("hands_up", "hands", lead=0.25, dur=0.5, summary="both empty hands thrown up (surrender, not mine)")
def hands_up(A, t):
    a = A.a
    a.expr("worried", t, 0.08)
    a.squash(t + A.d(0.1), -0.05, 0.03, 0.1)
    a.pose("hands_up", t + A.d(0.26), A.d(0.2))
    return t + A.d(0.5)


@action("tip_hat", "hands", lead=0.35, dur=0.9, summary="touch the hat brim and dip the head")
def tip_hat(A, t, side="R"):
    a = A.a
    a.pose({side: ("to", "brow", 0.0, 0.12), "hands": {side: "pinch"}}, t + A.d(0.32), A.d(0.28))
    a.tilt_head(12, t + A.d(0.5), A.d(0.16))
    a.tilt_head(0, t + A.d(0.72), A.d(0.18))
    A.rest(t + A.d(0.95), A.d(0.25), legs=False)
    return t + A.d(0.95)


@action("dust_off", "hands", lead=0.3, dur=1.1, summary="brush the clothes down with both hands")
def dust_off(A, t):
    a = A.a
    a.tilt_head(12, t + A.d(0.2), A.d(0.2))

    def brush(i, tt):
        a.pose({"R": ("to", "chest" if i % 2 else "belly"), "L": ("to", "belly" if i % 2 else "chest"), "hands": "open"}, tt, A.d(0.14))

    A.pulse(brush, t + A.d(0.25), t + A.d(0.95), every=0.16)
    A.rest(t + A.d(1.2), A.d(0.25), legs=False)
    return t + A.d(1.2)


@action("clap", "hands", lead=0.3, dur=1.1, summary="clap the hands together in front of the chest")
def clap(A, t, times=4):
    a = A.a
    a.expr("happy", t, 0.1)
    tt = t + A.d(0.2)
    for _ in range(times):
        a.pose({"L": (52, 96), "R": (52, 96), "views": {"front": {"L": (40, -128, "out"), "R": (40, -128, "out")}}, "hands": "open"}, tt + A.d(0.08), A.d(0.07))
        a.pose({"L": (44, 78), "R": (44, 78), "views": {"front": {"L": (46, -100, "out"), "R": (46, -100, "out")}}}, tt + A.d(0.19), A.d(0.1))
        tt += A.d(0.2)
    A.rest(tt + A.d(0.3), A.d(0.28), legs=False)
    return tt + A.d(0.3)


@action("slam", "hands", lead=0.3, dur=0.6, summary="bring the fist (or a held thing) down hard on a surface")
def slam(A, t, target=None, side="R"):
    a = A.a
    a.expr("angry", t, 0.08)
    a.hand(side, "fist", t + A.d(0.1), 0.06)
    a.arm(side, 128, 40, t + A.d(0.2), A.d(0.18))
    if target is not None:
        A.face(target, t)
        a.reach(side, target, t + A.d(0.3), A.d(0.08))
    else:
        a.arm(side, 46, 34, t + A.d(0.3), A.d(0.08))
    a.squash(t + A.d(0.31), 0.08, 0.03, 0.12)
    a.lean(10, t + A.d(0.32), A.d(0.1))
    return t + A.d(0.6)


# ============================================================================= REACTIONS
@action("gasp", "reactions", lead=0.2, dur=0.7, summary="shock: the face first, a jolt up, both hands fly up beside the face")
def gasp(A, t, target=None):
    a = A.a
    if target is not None:
        A.look(target, t)
    a.expr("surprised", t, 0.06)
    a.squash(t + A.d(0.1), -0.1, 0.04, 0.14)
    a.pose("gasp", t + A.d(0.24), A.d(0.16))
    a.ctrl_pulse("viseme_O", t + A.d(0.1), t + A.d(0.5))
    return t + A.d(0.7)


@action("laugh", "reactions", lead=0.3, dur=1.6, summary="head back, one hand on the belly, shoulders shaking", loops=True)
def laugh(A, t, until=None):
    a = A.a
    t1 = until if until is not None else t + A.d(1.6)
    a.expr("happy", t, 0.1)
    a.pose("laugh", t + A.d(0.3), A.d(0.26))
    a.shake(t + A.d(0.3), t1, 2.2, 8)
    A.pulse(lambda i, tt: a.ctrl_pulse("viseme_A", tt, tt + A.d(0.16)), t + A.d(0.3), t1, every=0.24)
    return t1


@action("smile", "reactions", lead=0.15, dur=0.5, summary="a smile or grin with a small lift of the head (smug=True: chin up, hands on hips)")
def smile(A, t, smug=False):
    a = A.a
    a.expr("happy", t + A.d(0.12), 0.12)
    a.tilt_head(-4, t + A.d(0.3), A.d(0.2))
    if smug:
        a.pose("proud", t + A.d(0.4), A.d(0.3))
    return t + A.d(0.5)


@action("cry", "reactions", lead=0.4, dur=1.8, summary="face in the hands, shoulders shaking", loops=True)
def cry(A, t, until=None):
    a = A.a
    t1 = until if until is not None else t + A.d(1.8)
    a.expr("sad", t, 0.12)
    a.pose({"L": ("to", "brow"), "R": ("to", "brow"), "hands": "open", "tilt": 18, "lean": 10}, t + A.d(0.4), A.d(0.34))
    a.shake(t + A.d(0.45), t1, 1.6, 6)
    return t1


@action("sigh", "reactions", lead=0.35, dur=1.0, summary="a breath in, then shoulders and head drop (also: sad slump)")
def sigh(A, t):
    a = A.a
    a.expr("sad", t, 0.2, amount=0.7)
    a.squash(t + A.d(0.3), -0.05, 0.12, 0.3)
    a.ctrl_pulse("viseme_U", t + A.d(0.4), t + A.d(0.8))
    a.pose("slump", t + A.d(0.8), A.d(0.45))
    return t + A.d(1.0)


@action("shrug", "reactions", lead=0.25, dur=0.9, summary="shoulders up, palms out, head to one side, and down again")
def shrug(A, t, hold=0.25):
    a = A.a
    a.expr("worried", t, 0.1, amount=0.4)
    a.squash(t + A.d(0.22), -0.04, hold, 0.2)
    a.pose("shrug", t + A.d(0.25), A.d(0.2))
    A.rest(t + A.d(0.5) + hold + A.d(0.25), A.d(0.3), legs=False)
    return t + A.d(0.75) + hold


@action("think", "reactions", lead=0.35, dur=1.5, summary="hand to the chin, eyes up and away", loops=True)
def think(A, t, until=None):
    a = A.a
    a.eyes(0.5, 0.8, t, 0.15)
    a.pose("think", t + A.d(0.35), A.d(0.3))
    return until if until is not None else t + A.d(1.5)


@action("nod", "reactions", lead=0.15, dur=0.7, summary="nod the head twice")
def nod(A, t, times=2):
    a = A.a
    tt = t
    for _ in range(times):
        a.tilt_head(14, tt + A.d(0.14), A.d(0.12))
        a.tilt_head(-2, tt + A.d(0.3), A.d(0.14))
        tt += A.d(0.3)
    a.tilt_head(0, tt + A.d(0.1), A.d(0.1))
    return tt + A.d(0.1)


@action("shake_head", "reactions", lead=0.15, dur=0.8, summary="shake the head: no")
def shake_head(A, t, times=3):
    a = A.a
    tt = t
    for i in range(times * 2):
        a.head_turn(1.0 if i % 2 == 0 else -1.0, tt + A.d(0.12), A.d(0.11))
        tt += A.d(0.12)
    a.head_turn(0.0, tt + A.d(0.1), A.d(0.1))
    return tt + A.d(0.1)


@action("cheer", "reactions", lead=0.3, dur=1.2, summary="jump with both arms thrown up")
def cheer(A, t, hops=2):
    a = A.a
    a.expr("happy", t, 0.08)
    a.squash(t + A.d(0.14), 0.08, 0.04, 0.06)
    a.pose("cheer", t + A.d(0.3), A.d(0.18))
    tt = t + A.d(0.2)
    for _ in range(hops):
        a.hop(tt, 0.2 * a.scale, A.d(0.32))
        tt += A.d(0.42)
    return tt + A.d(0.15)


@action("jeer", "reactions", lead=0.3, dur=1.2, summary="shake a raised fist and shout (a crowd booing)", loops=True)
def jeer(A, t, until=None, side="R"):
    a = A.a
    t1 = until if until is not None else t + A.d(1.2)
    a.expr("angry", t, 0.1)
    a.hand(side, "fist", t + A.d(0.1), 0.08)
    A.pulse(lambda i, tt: a.arm(side, 150 if i % 2 else 128, 30 if i % 2 else 60, tt, A.d(0.14), plane="out" if a._view == "front" else "fwd"),
            t + A.d(0.2), t1, every=0.18)
    A.pulse(lambda i, tt: a.ctrl_pulse("viseme_A", tt, tt + A.d(0.2)), t + A.d(0.2), t1, every=0.36)
    return t1


@action("panic", "reactions", lead=0.2, dur=1.6, summary="arms flailing overhead, looking one way then the other, shaking", loops=True)
def panic(A, t, until=None):
    a = A.a
    t1 = until if until is not None else t + A.d(1.6)
    a.expr("surprised", t, 0.06)

    def flail(i, tt):
        a.pose({"L": (150 if i % 2 else 110, 20, "out"), "R": (110 if i % 2 else 150, 20, "out"), "hands": "open"}, tt, A.d(0.14))

    A.pulse(flail, t + A.d(0.15), t1, every=0.16)
    a.shake(t + A.d(0.15), t1, 2.4, 11)
    A.pulse(lambda i, tt: a.eyes(1.0 if i % 2 else -1.0, 0.0, tt, 0.05), t, t1, every=0.4)
    return t1


@action("cower", "reactions", lead=0.3, dur=1.4, summary="shrink down small behind raised arms, trembling", loops=True)
def cower(A, t, until=None, target=None):
    a = A.a
    t1 = until if until is not None else t + A.d(1.4)
    if target is not None:
        A.face(target, t)
    a.expr("worried", t, 0.08)
    a.pose("cower", t + A.d(0.3), A.d(0.24))
    a.shake(t + A.d(0.3), t1, 1.4, 12)
    return t1


@action("tremble", "reactions", lead=0.1, dur=1.4, summary="the whole body shakes (cold, fear, rage held in)", loops=True)
def tremble(A, t, until=None, amount=1.3):
    a = A.a
    t1 = until if until is not None else t + A.d(1.4)
    a.pose({"L": (24, 70, "out"), "R": (24, 70, "out"), "hands": "fist", "lean": 4}, t + A.d(0.2), A.d(0.2))
    a.shake(t, t1, amount, 13)
    return t1


@action("angry", "reactions", lead=0.25, dur=0.9, summary="fury: face first, fists clenched at the sides, body forward")
def angry(A, t, target=None):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.look(target, t)
    a.expr("angry", t, 0.08)
    a.pose({"L": (16, 30, "out"), "R": (16, 30, "out"), "hands": "fist", "lean": 9, "tilt": 6}, t + A.d(0.28), A.d(0.2))
    a.shake(t + A.d(0.3), t + A.d(0.9), 1.0, 12)
    return t + A.d(0.9)


@action("suspicious", "reactions", lead=0.3, dur=1.0, summary="arms crossed, a slight lean in, narrowed look")
def suspicious(A, t, target=None):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.look(target, t)
    a.expr("angry", t, 0.15, amount=0.45)
    a.pose("cross_arms", t + A.d(0.4), A.d(0.32))
    a.lean(7, t + A.d(0.6), A.d(0.3))
    a.tilt_head(8, t + A.d(0.6), A.d(0.3))
    return t + A.d(1.0)


@action("dread", "reactions", lead=0.3, dur=1.2, summary="the smile goes, the body stiffens, a hand comes up to the collar")
def dread(A, t):
    a = A.a
    a.expr("worried", t, 0.25)
    a.squash(t + A.d(0.2), -0.04, 0.3, 0.3)
    a.pose({"R": ("to", "chest", 0.0, 0.1), "hands": {"R": "pinch"}, "lean": -4}, t + A.d(0.6), A.d(0.4))
    a.shake(t + A.d(0.5), t + A.d(1.2), 0.7, 12)
    return t + A.d(1.2)


@action("yawn", "reactions", lead=0.4, dur=1.4, summary="a big yawn behind the hand, with a stretch")
def yawn(A, t, side="R"):
    a = A.a
    a.pose("cover_mouth", t + A.d(0.4), A.d(0.34), side=side)
    a.arm("L" if side == "R" else "R", 150, 20, t + A.d(0.5), A.d(0.4), plane="out")
    a.ctrl_pulse("viseme_O", t + A.d(0.3), t + A.d(1.1))
    a.eyes_closed(t + A.d(0.4), t + A.d(1.1))
    a.tilt_head(-10, t + A.d(0.6), A.d(0.3))
    A.rest(t + A.d(1.45), A.d(0.3), legs=False)
    return t + A.d(1.45)


@action("sneeze", "reactions", lead=0.6, dur=1.0, summary="the head goes back, back... and snaps forward")
def sneeze(A, t):
    a = A.a
    a.expr("worried", t, 0.1)
    a.tilt_head(-16, t + A.d(0.5), A.d(0.45))
    a.lean(-8, t + A.d(0.5), A.d(0.45))
    a.eyes_closed(t + A.d(0.45), t + A.d(0.85))
    a.tilt_head(18, t + A.d(0.62), A.d(0.08))
    a.lean(16, t + A.d(0.62), A.d(0.08))
    a.squash(t + A.d(0.62), 0.08, 0.03, 0.14)
    a.ctrl_pulse("viseme_O", t + A.d(0.58), t + A.d(0.78))
    A.rest(t + A.d(1.0), A.d(0.3), legs=False)
    return t + A.d(1.0)


@action("whistle", "reactions", lead=0.2, dur=1.5, summary="lips pursed, head bobbing to a tune", loops=True)
def whistle(A, t, until=None):
    a = A.a
    t1 = until if until is not None else t + A.d(1.5)
    a.expr("happy", t, 0.2, amount=0.4)
    A.pulse(lambda i, tt: (a.ctrl_pulse("viseme_U", tt, tt + A.d(0.22)), a.tilt_head(5 if i % 2 else -5, tt, A.d(0.2))), t + A.d(0.2), t1, every=0.3)
    a.tilt_head(0, t1 + A.d(0.1), A.d(0.1))
    return t1


@action("sniff", "reactions", lead=0.2, dur=0.9, summary="nose up, two short sniffs")
def sniff(A, t):
    a = A.a
    a.tilt_head(-10, t + A.d(0.2), A.d(0.18))
    for i in range(2):
        a.squash(t + A.d(0.3 + 0.24 * i), -0.035, 0.03, 0.1)
    a.eyes(0.6, 0.5, t + A.d(0.2))
    a.tilt_head(0, t + A.d(0.9), A.d(0.2))
    return t + A.d(0.9)


@action("listen", "reactions", lead=0.3, dur=1.2, summary="stop, tilt the head, a hand cupped at the ear", loops=True)
def listen(A, t, until=None, target=None):
    a = A.a
    if target is not None:
        A.face(target, t)
    a.pose({"R": ("to", "ear", 0.0, 0.02), "hands": {"R": "open"}, "tilt": -8, "lean": 6}, t + A.d(0.3), A.d(0.26))
    a.eyes(0.8, 0.2, t + A.d(0.1))
    return until if until is not None else t + A.d(1.2)


@action("look_around", "reactions", lead=0.2, dur=1.4, summary="look one way, then the other, then back")
def look_around(A, t, times=2):
    a = A.a
    start = "right" if a._face > 0 else "left"
    other = "left" if a._face > 0 else "right"
    tt = t
    a.eyes(1.0, 0.0, tt, 0.08)
    for i in range(times):
        tt += A.d(0.35)
        a.squash(tt - A.d(0.04), 0.03, 0.02, 0.06)
        a.face(other if i % 2 == 0 else start, tt)
        a.eyes(1.0, 0.0, tt, 0.0)
    if times % 2 == 1:
        tt += A.d(0.35)
        a.face(start, tt)
    return tt + A.d(0.3)


@action("watch", "reactions", lead=0.2, dur=1.5, needs=("target",), summary="turn to a thing and keep the eyes on it (also: lock eyes with a person)", loops=True)
def watch(A, t, target=None, until=None):
    A.face(target, t)
    A.look(target, t + A.d(0.1), 0.15)
    A.a.tilt_head(-2, t + A.d(0.3), A.d(0.25))
    return until if until is not None else t + A.d(1.5)


@action("inspect", "reactions", lead=0.4, dur=1.2, needs=("target",), summary="lean right in to examine a thing closely")
def inspect(A, t, target=None):
    a = A.a
    A.face(target, t)
    A.look(target, t)
    A.crouch_for(core.point_of(target).z + 0.25, t + A.d(0.4), A.d(0.34))
    a.expr("angry", t + A.d(0.3), 0.2, amount=0.25)
    a.pose({"R": ("to", "chin"), "hands": {"R": "pinch"}}, t + A.d(0.6), A.d(0.3))
    return t + A.d(1.2)


@action("look_away", "reactions", lead=0.2, dur=0.7, summary="eyes and head turned away on purpose (avoiding someone's eye)")
def look_away(A, t):
    a = A.a
    a.eyes(-1.0, -0.3, t + A.d(0.1), 0.1)
    a.tilt_head(8, t + A.d(0.4), A.d(0.3))
    a.lean(-3, t + A.d(0.4), A.d(0.3))
    return t + A.d(0.7)


@action("facepalm", "reactions", lead=0.35, dur=1.0, summary="palm to the forehead, head down")
def facepalm(A, t):
    a = A.a
    a.expr("sad", t, 0.12, amount=0.6)
    a.pose("facepalm", t + A.d(0.35), A.d(0.28))
    a.squash(t + A.d(0.36), 0.04, 0.03, 0.12)
    return t + A.d(1.0)


@action("proud", "reactions", lead=0.3, dur=0.8, summary="chest out, chin up, fists on the hips")
def proud(A, t):
    a = A.a
    a.expr("happy", t, 0.12)
    a.squash(t + A.d(0.2), -0.06, 0.05, 0.16)
    a.pose("proud", t + A.d(0.3), A.d(0.24))
    return t + A.d(0.8)


# ============================================================================= TWO PEOPLE
def _between(a, b, height=0.92):
    pa, pb = a.chest.point(), b.chest.point()
    m = (pa + pb) / 2
    m.z = min(pa.z, pb.z) * height + 0.02
    return m


@action("hand_over", "two_person", lead=0.45, dur=1.1, needs=("prop", "to"), summary="hold a thing out to another character, who takes it (a.do('hand_over', prop, to=b))")
def hand_over(A, t, target=None, to=None, side="R"):
    a, b, prop = A.a, to, target
    B = _Perf(b, A.k)
    A.face(b, t)
    B.face(a, t)
    A.look(b, t)
    if prop.name not in a._held:
        a.hold(prop, side, t)
    meet = _between(a, b)
    tg = t + A.d(0.45)
    a.lean(6, tg, A.d(0.3))
    a.reach(side, meet, tg, A.d(0.34))
    B.look(prop, t + A.d(0.15))
    b.hand(side, "open", t + A.d(0.3), 0.1)
    b.lean(5, tg + A.d(0.12), A.d(0.25))
    b.reach(side, meet, tg + A.d(0.14), A.d(0.3))
    a.release(prop, tg + A.d(0.16))
    b.hold(prop, side, tg + A.d(0.16))
    end = tg + A.d(0.6)
    a.pose("rest", end, A.d(0.35))
    a.lean(0, end, A.d(0.3))
    b.arm(side, 52, 66, end, A.d(0.36))
    b.lean(0, end, A.d(0.3))
    B.look(prop, end)
    return end


@action("receive", "two_person", lead=0.4, dur=0.9, needs=("prop",), summary="hold out an open hand and close it on a thing that is given or lying there")
def receive(A, t, target=None, side="R"):
    a = A.a
    A.face(target, t)
    A.look(target, t)
    a.hand(side, "open", t + A.d(0.1), 0.1)
    a.reach(side, target, t + A.d(0.4), A.d(0.34))
    a.hold(target, side, t + A.d(0.42))
    a.arm(side, 52, 66, t + A.d(0.85), A.d(0.36))
    return t + A.d(0.9)


@action("handshake", "two_person", lead=0.45, dur=1.3, needs=("other",), summary="two characters clasp right hands between them and shake")
def handshake(A, t, target=None, pumps=3):
    a, b = A.a, target
    B = _Perf(b, A.k)
    A.face(b, t)
    B.face(a, t)
    A.look(b, t)
    B.look(a, t)
    meet = _between(a, b, 0.86)
    tg = t + A.d(0.45)
    for x in (a, b):
        x.hand("R", "open", t + A.d(0.2), 0.1)
        x.lean(5, tg, A.d(0.3))
        x.reach("R", meet, tg, A.d(0.34))
        x.hand("R", "fist", tg, 0.06)
    tt = tg
    for i in range(pumps * 2):
        tt += A.d(0.1)
        dz = 0.05 if i % 2 == 0 else -0.04
        for x in (a, b):
            x.reach("R", meet + Vector((0, 0, dz)), tt, A.d(0.1))
    for x in (a, b):
        x.pose("rest", tt + A.d(0.4), A.d(0.34))
        x.lean(0, tt + A.d(0.4), A.d(0.3))
    return tt + A.d(0.4)


@action("hug", "two_person", lead=0.5, dur=1.4, needs=("other",), summary="two characters close in and put their arms round each other")
def hug(A, t, target=None, hold=0.6):
    a, b = A.a, target
    B = _Perf(b, A.k)
    A.face(b, t)
    B.face(a, t)
    for x in (a, b):
        x.expr("happy", t, 0.15)
        x.pose({"L": (60, 20, "out"), "R": (70, 16), "hands": "open"}, t + A.d(0.25), A.d(0.22))
    pa, pb = a.position(), b.position()
    mid = (pa + pb) / 2
    gap = 0.2 * (a.scale + b.scale) / 2
    d = (pb - pa)
    d.z = 0
    if d.length > 1e-4:
        d.normalize()
        ta = A.go(t + A.d(0.2), tuple(mid - d * gap), "walk", 2.6, arms=False) if (pa - (mid - d * gap)).length > 0.05 else t + A.d(0.3)
        tb = B.go(t + A.d(0.2), tuple(mid + d * gap), "walk", 2.6, arms=False) if (pb - (mid + d * gap)).length > 0.05 else t + A.d(0.3)
    else:
        ta = tb = t + A.d(0.3)
    th = max(ta, tb) + A.d(0.1)
    a.pose("hug", th + A.d(0.2), A.d(0.24))
    b.pose("hug", th + A.d(0.2), A.d(0.24))
    for x in (a, b):
        x.eyes_closed(th + A.d(0.2), th + A.d(0.2) + hold)
        x.squash(th + A.d(0.22), 0.04, 0.04, 0.14)
    return th + A.d(0.2) + hold


@action("whisper", "two_person", lead=0.4, dur=1.6, summary="lean in to another character with a hand beside the mouth and speak low (other=)", loops=True)
def whisper(A, t, target=None, until=None, first=None, last=None):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.look(target, t)
    a.pose({"R": ("to", "cheek", 0.0, -0.04), "hands": {"R": "open"}, "lean": 14, "tilt": -4}, t + A.d(0.4), A.d(0.34))
    t1 = until if until is not None else t + A.d(1.6)
    if first is not None:
        t1 = a.speak(first, last, strength=0.55)
    else:
        a.speak(t + A.d(0.45), t1, strength=0.55)
    if target is not None and hasattr(target, "tilt_head"):
        target.lean(8, t + A.d(0.5), A.d(0.3))
        target.tilt_head(-6, t + A.d(0.5), A.d(0.3))
    return t1


@action("argue", "two_person", lead=0.3, dur=2.4, needs=("other",), summary="two characters go at each other: jabbing fingers and thrown-up hands by turns", loops=True)
def argue(A, t, target=None, until=None):
    a, b = A.a, target
    B = _Perf(b, A.k)
    A.face(b, t)
    B.face(a, t)
    t1 = until if until is not None else t + A.d(2.4)
    for x in (a, b):
        x.expr("angry", t, 0.1)
    moves = [{"R": (84, 10), "hands": {"R": "point"}, "lean": 10}, {"L": (60, 60, "out"), "R": (60, 60, "out"), "hands": "open", "lean": -4},
             {"R": (100, 40), "hands": {"R": "fist"}, "lean": 8}, {"L": ("to", "hip"), "R": (70, 30), "hands": {"R": "open"}, "lean": 4}]

    def turn(i, tt):
        who, other = (a, b) if i % 2 == 0 else (b, a)
        who.pose(moves[i % len(moves)], tt + A.d(0.2), A.d(0.18))
        who.speak(tt + A.d(0.1), tt + A.d(0.55), strength=1.0)
        who.squash(tt + A.d(0.2), -0.04, 0.03, 0.1)
        other.lean(-5, tt + A.d(0.3), A.d(0.2))

    A.pulse(turn, t + A.d(0.1), t1 - A.d(0.3), every=0.6)
    return t1


@action("chase", "two_person", lead=0.0, dur=2.0, needs=("other", "to"), summary="one runs for it to a place and the other runs after, a stride behind")
def chase(A, t, target=None, to=None, gap=0.9):
    a, b = A.a, target
    B = _Perf(b, A.k)
    b.expr("worried", t, 0.08)
    a.expr("angry", t, 0.08)
    tb = B.go(t, to, "run")
    pa = a.position()
    dest = Vector((to[0], to[1], to[2] if len(to) > 2 else pa.z))
    d = dest - pa
    d.z = 0
    stop = dest - d.normalized() * gap if d.length > gap else pa
    a.pose({"R": (86, 16), "hands": {"R": "open"}}, t + A.d(0.3), A.d(0.2))
    ta = A.go(t + A.d(0.25), (stop.x, stop.y, pa.z), "run", arms=False)
    return max(ta, tb)


@action("bow", "two_person", lead=0.45, dur=1.3, summary="bow from the waist, one hand on the chest, and straighten")
def bow(A, t, target=None, deep=False):
    a = A.a
    if target is not None:
        A.face(target, t)
    a.pose({"R": ("to", "chest"), "L": (16, 10, "out"), "hands": {"R": "open"}}, t + A.d(0.3), A.d(0.26))
    a.lean(48 if deep else 34, t + A.d(0.6), A.d(0.3))
    a.tilt_head(16, t + A.d(0.6), A.d(0.3))
    a.eyes_closed(t + A.d(0.5), t + A.d(0.95))
    a.lean(0, t + A.d(1.2), A.d(0.34))
    a.tilt_head(0, t + A.d(1.2), A.d(0.3))
    a.pose("rest", t + A.d(1.3), A.d(0.3))
    return t + A.d(1.3)


@action("curtsy", "two_person", lead=0.45, dur=1.3, summary="curtsy: skirt held out, knees dip, head bows")
def curtsy(A, t, target=None):
    a = A.a
    if target is not None:
        A.face(target, t)
    a.pose({"L": (34, 30, "out"), "R": (34, 30, "out"), "hands": "pinch"}, t + A.d(0.3), A.d(0.26))
    if A.has_legs():
        a.legs(26, 52, t + A.d(0.62), A.d(0.3))
    a.lean(10, t + A.d(0.62), A.d(0.3))
    a.tilt_head(14, t + A.d(0.62), A.d(0.3))
    if A.has_legs():
        a.legs(0, 0, t + A.d(1.15), A.d(0.34))
    A.rest(t + A.d(1.3), A.d(0.34), legs=False)
    return t + A.d(1.3)


@action("salute", "two_person", lead=0.3, dur=1.0, summary="snap the flat hand to the brow, hold, drop it")
def salute(A, t, target=None, hold=0.4):
    a = A.a
    if target is not None:
        A.face(target, t)
    a.squash(t + A.d(0.22), -0.05, 0.04, 0.12)
    a.pose("salute", t + A.d(0.28), A.d(0.18))
    A.rest(t + A.d(0.55) + hold + A.d(0.2), A.d(0.2), legs=False)
    return t + A.d(0.75) + hold


@action("plead", "two_person", lead=0.4, dur=1.4, summary="hands clasped out in front, body bent toward the other (knees=True: on the knees)", loops=True)
def plead(A, t, target=None, until=None, knees=False):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.look(target, t)
    a.expr("worried", t, 0.1)
    if knees and A.has_legs():
        a.legs(8, 98, t + A.d(0.4), A.d(0.34))
    a.pose("beg", t + A.d(0.4), A.d(0.32))
    t1 = until if until is not None else t + A.d(1.4)
    a.shake(t + A.d(0.45), t1, 0.9, 7)
    return t1


@action("push_person", "two_person", lead=0.35, dur=0.9, needs=("other",), summary="shove another character, who staggers back")
def push_person(A, t, target=None):
    a, b = A.a, target
    A.face(b, t)
    a.expr("angry", t, 0.08)
    a.lean(-6, t + A.d(0.14), A.d(0.12))
    a.hand("R", "open", t + A.d(0.2), 0.08)
    a.hand("L", "open", t + A.d(0.2), 0.08)
    a.reach("R", b.chest, t + A.d(0.35), A.d(0.18))
    a.reach("L", b.chest, t + A.d(0.35), A.d(0.18))
    a.lean(14, t + A.d(0.4), A.d(0.14))
    run(b, "recoil", a, t=t + A.d(0.33), speed=A.k)
    A.rest(t + A.d(0.9), A.d(0.34), legs=False)
    return t + A.d(0.9)


@action("grab_person", "two_person", lead=0.35, dur=0.8, needs=("other",), summary="seize another character by the arm or collar and hold on")
def grab_person(A, t, target=None, where="chest"):
    a, b = A.a, target
    A.face(b, t)
    A.look(b, t)
    a.lean(8, t + A.d(0.3), A.d(0.24))
    a.hand("R", "open", t + A.d(0.15), 0.08)
    a.reach("R", getattr(b, where, b.chest), t + A.d(0.35), A.d(0.22))
    a.hand("R", "fist", t + A.d(0.36), 0.05)
    b.expr("surprised", t + A.d(0.38), 0.06)
    b.squash(t + A.d(0.4), -0.06, 0.03, 0.12)
    b.pose({"L": (40, 50, "out"), "R": (40, 50, "out"), "hands": "open", "lean": -6}, t + A.d(0.5), A.d(0.16))
    return t + A.d(0.8)


@action("pat_back", "two_person", lead=0.35, dur=1.0, needs=("other",), summary="friendly slaps on another character's shoulder")
def pat_back(A, t, target=None, times=2):
    a, b = A.a, target
    A.face(b, t)
    a.expr("happy", t, 0.1)
    a.hand("R", "open", t + A.d(0.15), 0.08)
    tt = t + A.d(0.3)
    spot = b.chest.point() + Vector((0, 0, 0.16 * b.scale))
    for _ in range(times):
        a.reach("R", spot, tt + A.d(0.06), A.d(0.1))
        b.squash(tt + A.d(0.07), 0.04, 0.02, 0.08)
        a.arm("R", 84, 40, tt + A.d(0.24), A.d(0.14))
        tt += A.d(0.26)
    A.rest(tt + A.d(0.3), A.d(0.28), legs=False)
    return tt + A.d(0.3)


@action("cover_mouth", "two_person", lead=0.3, dur=0.8, summary="clap a hand over the mouth: the character's own, or another's (other=)")
def cover_mouth(A, t, target=None):
    a = A.a
    if target is None or not hasattr(target, "head"):
        a.expr("surprised", t, 0.06)
        a.pose("cover_mouth", t + A.d(0.3), A.d(0.2))
        return t + A.d(0.8)
    b = target
    A.face(b, t)
    a.hand("R", "open", t + A.d(0.1), 0.08)
    a.lean(8, t + A.d(0.3), A.d(0.2))
    a.reach("R", b.head.point() - Vector((0, 0, 0.5 * b.head_r * b.scale)), t + A.d(0.3), A.d(0.2))
    b.expr("surprised", t + A.d(0.32), 0.05)
    return t + A.d(0.8)


@action("slap_away", "two_person", lead=0.25, dur=0.6, needs=("other",), summary="knock another character's reaching hand aside")
def slap_away(A, t, target=None):
    a, b = A.a, target
    A.face(b, t)
    a.expr("angry", t, 0.06)
    a.hand("R", "open", t + A.d(0.05), 0.05)
    a.arm("R", 96, 50, t + A.d(0.14), A.d(0.12))
    a.arm("R", 60, 14, t + A.d(0.25), A.d(0.08))
    b.squash(t + A.d(0.26), -0.05, 0.03, 0.1)
    b.pose({"R": (40, 80), "hands": {"R": "open"}, "lean": -6}, t + A.d(0.36), A.d(0.1))
    b.expr("surprised", t + A.d(0.26), 0.05)
    return t + A.d(0.6)


# ============================================================================= TALKING
_GESTURES = [{"R": (64, 34), "hands": {"R": "open"}}, {"R": (50, 70), "hands": {"R": "open"}}, {"R": (76, 104), "hands": {"R": "point"}},
             {"L": (32, 60, "out"), "R": (32, 60, "out"), "hands": "open"}, {"R": (58, 50), "L": (30, 40), "hands": "open"}]


@action("talk", "talking", lead=0.0, dur=2.0, summary='speak a line with lip sync and hand gestures: do("talk", first="Bring it back", last="is yours") or t0/t1', loops=True)
def talk(A, t, target=None, first=None, last=None, until=None, strength=1.0, gestures=True):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.look(target, t)
    if first is not None:
        t0 = a.shot.t(first) if isinstance(first, str) else float(first)
        t1 = a.speak(first, last, strength=strength)
    else:
        t0 = t
        t1 = until if until is not None else t + A.d(2.0)
        a.speak(t0, t1, strength=strength)
    if gestures:
        seed = sum(ord(c) for c in a.id)

        def g(i, tt):
            a.pose(_GESTURES[(seed + i) % len(_GESTURES)], tt + A.d(0.24), A.d(0.24))
            a.tilt_head(-3 if i % 2 else 3, tt + A.d(0.24), A.d(0.24))

        A.pulse(g, t0, max(t0, t1 - A.d(0.5)), every=0.95)
        A.rest(t1 + A.d(0.3), A.d(0.3), legs=False)
    return t1 + (A.d(0.3) if gestures else 0.0)


@action("shout", "talking", lead=0.2, dur=1.4, summary="shout or call out: body forward, mouth wide, a hand cupped at the mouth or a fist up", loops=True)
def shout(A, t, target=None, first=None, last=None, until=None, fist=False):
    a = A.a
    if target is not None:
        A.face(target, t)
        A.look(target, t)
    a.squash(t + A.d(0.12), -0.07, 0.04, 0.12)
    if fist:
        a.pose({"R": (140, 30, "out"), "hands": {"R": "fist"}, "lean": 8, "views": {"3q": {"R": (128, 30)}, "side": {"R": (128, 30)}}}, t + A.d(0.22), A.d(0.18))
    else:
        a.pose({"R": ("to", "cheek", 0.0, -0.06), "hands": {"R": "open"}, "lean": 12, "tilt": -8}, t + A.d(0.22), A.d(0.18))
    if first is not None:
        t1 = a.speak(first, last, strength=1.25)
    else:
        t1 = until if until is not None else t + A.d(1.4)
        a.speak(t + A.d(0.2), t1, strength=1.25)
    a.shake(t + A.d(0.2), t1, 0.8, 9)
    return t1


# ============================================================================= added by following docs/ADDING_NEW_ACTIONS.md
@action("juggle", "hands", lead=0.45, dur=2.4, needs=("props",), loops=True,
        summary="keep two or three small things in the air: hands alternate low in front, eyes follow the top of the arc")
def juggle(A, t, props=None, until=None, height=None):
    a = A.a
    props = list(props)
    t1 = until if until is not None else t + A.d(2.4)
    h = (height if height is not None else 0.34 * a.height)
    a.expr("happy", t, 0.12)
    if A.has_legs():                                          # anticipation: a small dip, eyes up
        a.squash(t + A.d(0.2), 0.05, 0.04, 0.1)
    a.eyes(0.4, 0.9, t + A.d(0.15), 0.1)
    low = {"L": (36, 78), "R": (36, 78), "hands": "open", "views": {"front": {"L": (24, -70, "out"), "R": (24, -70, "out")}}}
    a.pose(low, t + A.d(0.35), A.d(0.3))
    core.at_frame(a._f(t + A.d(0.36)))
    v = a._view_key()
    if getattr(a, "is3d", False):
        hands = {s: a.hand_point(s) for s in "LR"}
    else:
        rig = a.rigs[v].evaluated_get(bpy.context.evaluated_depsgraph_get())
        hands = {s: rig.matrix_world @ rig.pose.bones[f"palm.{s}" if a.v4 else f"hand.{s}"].head for s in "LR"}
    depth = a.stage.matrix_world.to_3x3() @ Vector((0, -0.075, 0))          # just in front of the figure
    beat = A.d(0.22)
    n = max(2, int((t1 - A.d(0.4) - (t + A.d(0.45))) / beat))
    for i, pr in enumerate(props):                              # every prop starts in a hand
        pr.location = hands["R" if i % 2 == 0 else "L"] + depth
        core.key_frame(pr, "location", a._f(t + A.d(0.4)), interp="CONSTANT")
    for k in range(n):
        tt = t + A.d(0.45) + k * beat
        pr = props[k % len(props)]
        src = "R" if k % 2 == 0 else "L"
        dst = "L" if src == "R" else "R"
        air = beat * max(1.0, len(props) - 0.5)
        p0, p1 = hands[src] + depth, hands[dst] + depth
        f0, f1 = a._f(tt), a._f(tt + air)
        pr.location = p0
        core.key_frame(pr, "location", f0)
        mid = (p0 + p1) / 2
        mid.z += h
        pr.location = mid
        core.key_frame(pr, "location", (f0 + f1) // 2)
        pr.location = p1
        core.key_frame(pr, "location", f1)
        a._wag(src, 16, tt, beat * 0.45)                        # the throwing hand flicks up ...
        a._wag(src, 0, tt + beat * 0.9, beat * 0.45)            # ... and drops to catch
        a.eyes(0.3 if k % 2 else -0.3, 0.9, tt, beat * 0.5)
    end = t + A.d(0.45) + n * beat + beat * max(1.0, len(props) - 0.5)
    a.pose({"L": ("to", "belly"), "R": ("to", "belly", 0.04, 0.0), "hands": "fist"}, end + A.d(0.2), A.d(0.2))   # settle: all caught
    for i, pr in enumerate(props):
        core.at_frame(a._f(end + A.d(0.2)))
        if getattr(a, "is3d", False):
            pr.location = a.hand_point("R") + depth + Vector((0, 0, 0.03 * i))
        else:
            rig = a.rigs[v].evaluated_get(bpy.context.evaluated_depsgraph_get())
            pr.location = rig.matrix_world @ rig.pose.bones[f"palm.R" if a.v4 else "hand.R"].head + depth + Vector((0, 0, 0.03 * i))
        core.key_frame(pr, "location", a._f(end + A.d(0.2)))
    a.tilt_head(8, end + A.d(0.45), A.d(0.2))
    a.eyes(1.0, 0.0, end + A.d(0.3), 0.1)
    return end + A.d(0.5)


@action("slip_banana", "moving", lead=0.75, dur=1.5, needs=("prop",),
        summary="step on a peel without looking: the foot shoots out, the peel flies off, the figure hangs level in the air and lands flat on its back")
def slip_banana(A, t, target=None):
    a = A.a
    peel = target
    pp = core.point_of(peel)
    p = a.position()
    A.face(pp, t)
    a.eyes(0.9, 0.5, t, 0.1)                                   # anticipation: carefree, looking anywhere but down
    a.expr("happy", t, 0.1, amount=0.6)
    stand = Vector((pp.x, pp.y, p.z))
    back = (p - stand)
    back.z = 0
    if back.length > 0.3:
        stand = stand + back.normalized() * 0.12 * a.scale
        ts = A.go(t, (stand.x, stand.y, p.z), "walk", 2.2)
    else:
        ts = t + A.d(0.2)
    cam = bpy.context.scene.camera
    right = (cam.matrix_world.to_3x3() @ Vector((1, 0, 0))) if cam else Vector((1, 0, 0))
    fwd = right * a._face
    a.expr("surprised", ts + A.d(0.04), 0.04)                  # the face knows first
    if A.has_legs():
        a.legs(78, 8, ts + A.d(0.14), A.d(0.1), side="R", ground=False)     # the foot shoots forward
    core.move(peel, ts + A.d(0.06), ts + A.d(0.4), location=tuple(pp + fwd * 1.3 + Vector((0, 0, 0.0))))      # the peel flies off
    core.key(peel, "rotation_euler", ts + A.d(0.06))
    core.key(peel, "rotation_euler", ts + A.d(0.4), (0.0, 0.0, 9.0))
    a.pose({"L": (150, 20, "out"), "R": (110, -30, "out"), "hands": "open"}, ts + A.d(0.16), A.d(0.12))       # windmill
    a.pose({"L": (70, 50, "out"), "R": (165, 10, "out")}, ts + A.d(0.32), A.d(0.14))
    q = a.position()
    lie = 0.15 * a.scale
    a.rock(-88, ts + A.d(0.4), A.d(0.3), pivot=a.height * 0.5)                # level in the air ...
    a.move(ts + A.d(0.12), ts + A.d(0.55), (q.x, q.y, q.z + lie - a.height * 0.5), arc=0.38 * a.scale, land=False)
    if A.has_legs():
        a.legs(40, 20, ts + A.d(0.36), A.d(0.2), ground=False)
        a.legs(12, 16, ts + A.d(0.7), A.d(0.14), ground=False)
    a.squash(ts + A.d(0.56), 0.16, 0.05, 0.22)                                # ... and down flat
    a.pose({"L": (80, 10, "out"), "R": (80, 10, "out"), "hands": "open"}, ts + A.d(0.62), A.d(0.1))
    a.floating = True
    a.expr("worried", ts + A.d(1.0), 0.2)                                     # settle: a dazed look up
    a.tilt_head(10, ts + A.d(1.15), A.d(0.3))
    a.eyes(0.0, 0.8, ts + A.d(1.0), 0.15)
    return ts + A.d(1.3)
