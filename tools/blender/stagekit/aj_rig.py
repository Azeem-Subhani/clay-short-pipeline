"""aj_rig - a hidden control rig with Aj's own joint layout, so the 3D actor API drives a real Mixamo skeleton.

fig3d's skeleton is a tree of empties that every actor method and every named action animates (J["sh.R"], J["kn.L"],
...). For an Aj actor the same tree is built with one empty per mapped Mixamo bone, placed at the bone head in a
"hanging arms" reference pose, under the SAME joint names, and the real pose bones follow the empties:

    rig = aj_rig.build(actor, arm, body, meas)      # J, W, targets, bound constraints
    aj_rig.binding_error(actor)                     # mm between every control pivot and its bone head (must stay < 0.5)

The reference pose exists in memory only: the arms are swung from the Mixamo T-pose to hang straight down with the
palms to the thighs, every other bone is at rest; the rest pose of the armature is never touched and nothing is saved.
In that pose every empty has the identity rotation (model space: front -Y, the figure's left +X, Z up), so an arm empty
at rest means "the arm hangs", its local X is the elbow hinge and local -Z runs down the bone: exactly fig3d's contract.
Each bone keeps the constant offset O_b between the empty's frame and its own frame in that pose (a child "target"
empty carries it) and copies the target's world rotation; the Hips also copy the hips empty's location.

Joint map: hips->Hips; spine, spine1, torso->Spine, Spine1, Spine2; neck, head->Neck, Head; cl.*->Shoulder (the collar,
derived from the arm at _finalize: shrug from elevation, protraction from forward reach); sh.*->Arm; el.*->ForeArm;
wr.*->Hand; hip.*, kn.*, an.*, toe.*->UpLeg, Leg, Foot, ToeBase. Fingers are keyed on their bones directly. skirt and
cape are empties that bind to nothing (old code keys them). The shoulder empty sh.* is a child of the torso (as in
fig3d) and its LOCATION follows the collar tip, keyed per frame by apply_collars(); so the arm angles keep meaning
"in the upper body's space" whatever the collar does.

The binding constraints are filed under named groups (legs, spine, arm.L, arm.R, head; actor._aj_groups) and
set_group() keys a group's influence, so a motion clip can later take one group over.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

P = "mixamorig:"
GROUPS = ("legs", "spine", "arm.L", "arm.R", "head")

# joint -> (bone, parent joint, group)
JOINTS = {
    "hips": ("Hips", "root", "legs"),
    "spine": ("Spine", "hips", "spine"),
    "spine1": ("Spine1", "spine", "spine"),
    "torso": ("Spine2", "spine1", "spine"),
    "neck": ("Neck", "torso", "head"),
    "head": ("Head", "neck", "head"),
}
for _s, _side in (("L", "Left"), ("R", "Right")):
    JOINTS.update({
        f"cl.{_s}": (f"{_side}Shoulder", "torso", f"arm.{_s}"),
        f"sh.{_s}": (f"{_side}Arm", "torso", f"arm.{_s}"),
        f"el.{_s}": (f"{_side}ForeArm", f"sh.{_s}", f"arm.{_s}"),
        f"wr.{_s}": (f"{_side}Hand", f"el.{_s}", f"arm.{_s}"),
        f"hip.{_s}": (f"{_side}UpLeg", "hips", "legs"),
        f"kn.{_s}": (f"{_side}Leg", f"hip.{_s}", "legs"),
        f"an.{_s}": (f"{_side}Foot", f"kn.{_s}", "legs"),
        f"toe.{_s}": (f"{_side}ToeBase", f"an.{_s}", "legs"),
    })
EXTRA = {"skirt": "hips", "cape": "torso"}          # unbound empties that existing code keys
QUAT = ("sh.", "el.", "wr.", "cl.")                  # these joints turn by quaternion (fig3d: sh., el.)

# collar: degrees of shrug at full elevation, protraction at full forward reach
COLLAR_SHRUG = 20.0
COLLAR_PROTRACT = 14.0
BREATH_SHRUG = 1.6


def _smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# ----------------------------------------------------------------------------------------------- reference pose
def _swing(a: Vector, b: Vector) -> Matrix:
    return a.normalized().rotation_difference(b.normalized()).to_matrix()


def reference_pose(arm):
    """Put the armature in the hanging-arms reference pose (pose only, in memory) and return
    {bone: (head, 3x3 rotation)} in the armature object's parent space (the figure's model space)."""
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
        for c in pb.constraints:
            c.mute = True
    bpy.context.view_layer.update()
    A = arm.matrix_basis.to_3x3().normalized()        # the FBX armature's own turn (X 90 deg); scale is applied below
    Ai = A.inverted()
    for side in ("Left", "Right"):
        for bn in ("Arm", "ForeArm"):
            pb = arm.pose.bones[P + side + bn]
            bpy.context.view_layer.update()
            M = pb.matrix.copy()                       # armature space
            d = A @ (M.to_3x3() @ Vector((0, 1, 0)))   # where the bone points in model space
            R = Ai @ _swing(d, Vector((0, 0, -1))) @ A  # the same swing written in armature space
            pb.matrix = Matrix.Translation(M.translation) @ (R @ M.to_3x3()).to_4x4()
            bpy.context.view_layer.update()
    S = arm.matrix_basis.to_scale()[0]
    out = {}
    for pb in arm.pose.bones:
        out[pb.name[len(P):]] = ((A @ pb.matrix.translation) * S, (A @ pb.matrix.to_3x3().normalized()))
    return out


# ------------------------------------------------------------------------------------------------- the rig
def _empty(actor, name, parent, loc, size=0.025):
    e = bpy.data.objects.new(f"{actor.id}.j.{name}", None)
    e.empty_display_size = size
    actor.coll.objects.link(e)
    if parent is not None:
        e.parent = parent
    e.location = loc
    e.hide_render = True
    return e


def _group(actor, con, group):
    """File a binding constraint under its group (influence 1). Drivers on these influences were tried first: in
    Blender 5.3 background runs they evaluated to 0 on the armature, so the groups are a table of constraints and
    set_group() keys their influence directly."""
    con.influence = 1.0
    actor._aj_groups.setdefault(group, []).append(con)


def set_group(actor, group: str, value: float, frame: int | None = None):
    """How much the control joints drive one group of bones (legs, spine, arm.L, arm.R, head): 1 = fully, 0 = the
    bones are free for something else (a motion clip). With a frame the change is keyed there."""
    for c in actor._aj_groups[group]:
        c.influence = float(value)
        if frame is not None:
            c.keyframe_insert("influence", frame=int(frame))


def build(actor, arm, body, k: float = 1.0):
    """Build the control empties for `actor` (which already has .id, .coll, .root, .ctrl) on the appended armature.
    k: the world scale of this figure (metres in the scene per native metre). Returns (J, W, ref)."""
    root = actor.root
    arm.parent = root
    arm.matrix_parent_inverse = Matrix.Identity(4)
    arm.location = (0, 0, 0)
    arm.rotation_mode = "XYZ"
    arm.rotation_euler = (math.radians(90.0), 0, 0)
    arm.scale = (0.01 * k,) * 3
    ref = reference_pose(arm)
    actor._aj_groups = {g: [] for g in GROUPS}
    J, W, T = {"root": root}, {"root": Vector((0, 0, 0))}, {}
    for jn, (bn, par, _g) in JOINTS.items():
        W[jn] = ref[bn][0].copy()
    for jn, par in EXTRA.items():
        W[jn] = W[par].copy()
    order = list(JOINTS) + list(EXTRA)
    for jn in order:
        par = JOINTS[jn][1] if jn in JOINTS else EXTRA[jn]
        e = _empty(actor, jn, J[par], W[jn] - W[par])
        e.rotation_mode = "QUATERNION" if jn.startswith(QUAT) else "XYZ"
        J[jn] = e
    for jn, (bn, par, g) in JOINTS.items():
        t = _empty(actor, jn + ".tgt", J[jn], (0, 0, 0), 0.01)
        t.rotation_mode = "QUATERNION"
        t.rotation_quaternion = ref[bn][1].to_quaternion()
        T[jn] = t
        pb = arm.pose.bones[P + bn]
        for c in list(pb.constraints):
            pb.constraints.remove(c)
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        c = pb.constraints.new("COPY_ROTATION")
        c.name = "aj_rot"
        c.target = t
        c.owner_space = c.target_space = "WORLD"
        c.mix_mode = "REPLACE"
        _group(actor, c, g)
        if jn == "hips":
            c = pb.constraints.new("COPY_LOCATION")
            c.name = "aj_loc"
            c.target = J["hips"]
            c.owner_space = c.target_space = "WORLD"
            _group(actor, c, g)
    # every other bone (fingers, extras) back at rest; fingers are keyed directly by aj_hands
    for pb in arm.pose.bones:
        if not pb.constraints:
            pb.rotation_mode = "XYZ" if "Hand" in pb.name and any(f in pb.name for f in ("Thumb", "Index", "Middle", "Ring", "Pinky")) else "QUATERNION"
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    actor._aj_targets = T
    actor._aj_ref = ref
    actor._collar_rest = {s: (W[f"cl.{s}"].copy(), W[f"sh.{s}"].copy()) for s in "LR"}
    return J, W, ref


# --------------------------------------------------------------------------------------------- the collar
def collar_rotation(side: str, u: Vector, breath: float = 0.0) -> Quaternion:
    """The collar bone's turn (torso space) for an upper arm pointing along u (torso space, unit): it shrugs as the arm
    rises above the shoulder and comes forward as the arm reaches ahead, like a real shoulder girdle."""
    s = 1.0 if side == "L" else -1.0
    up = u.z
    fwd = -u.y
    shrug = COLLAR_SHRUG * _smooth((up + 0.25) / 1.15) + BREATH_SHRUG * breath
    prot = COLLAR_PROTRACT * _smooth((fwd - 0.25) / 0.7) * (1.0 - 0.5 * _smooth(up))
    return (Quaternion((0, 0, 1), math.radians(-s * prot)) @ Quaternion((0, 1, 0), math.radians(-s * shrug)))


def shoulder_point(actor, side: str, q_cl: Quaternion) -> Vector:
    """Where the shoulder joint (the Arm bone head) is, in torso space, for a collar turn q_cl."""
    c, s0 = actor._collar_rest[side]
    return (c - actor.W["torso"]) + q_cl @ (s0 - c)


def arm_dir(q_sh: Quaternion) -> Vector:
    return (q_sh @ Vector((0, 0, -1))).normalized()


def _fc_map(ob):
    from . import core
    out = {}
    for fc in core.fcurves(ob):
        out[(fc.data_path, fc.array_index)] = fc
    return out


def _write_dense(ob, path, frames, values, n):
    """Replace a channel's keys with one key per frame (linear)."""
    from . import core
    for fc in list(core.fcurves(ob)):
        if fc.data_path == path:
            fc.keyframe_points.clear()
    ob.keyframe_insert(path, frame=frames[0])
    fcs = {fc.array_index: fc for fc in core.fcurves(ob) if fc.data_path == path}
    for i in range(n):
        fc = fcs[i]
        fc.keyframe_points.clear()
        fc.keyframe_points.add(len(frames))
        co = []
        for f, v in zip(frames, values):
            co += [float(f), float(v[i])]
        fc.keyframe_points.foreach_set("co", co)
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        fc.update()


def apply_collars(actor, frames):
    """Per frame: read the upper arm's keyed turn, work out the collar, key the collar empty and move the shoulder
    empty to the collar tip. Pure maths on the F-curves (no scene evaluation)."""
    ctrl_fc = _fc_map(actor.ctrl)
    bfc = ctrl_fc.get(('["breath"]', 0))
    for s in "LR":
        sh, cl = actor.J[f"sh.{s}"], actor.J[f"cl.{s}"]
        fcm = _fc_map(sh)
        qs, locs = [], []
        prev = None
        for f in frames:
            q = Quaternion([fcm[("rotation_quaternion", i)].evaluate(f) if ("rotation_quaternion", i) in fcm
                            else sh.rotation_quaternion[i] for i in range(4)]).normalized()
            br = bfc.evaluate(f) if bfc is not None else 0.0
            qc = collar_rotation(s, arm_dir(q), br)
            if prev is not None and qc.dot(prev) < 0:
                qc.negate()
            prev = qc
            qs.append(tuple(qc))
            locs.append(tuple(shoulder_point(actor, s, qc)))
        _write_dense(cl, "rotation_quaternion", frames, qs, 4)
        _write_dense(sh, "location", frames, locs, 3)


# ----------------------------------------------------------------------------------------------- checks
def binding_error(actor, frame=None) -> float:
    """Largest distance in mm between a control pivot and the head of the bone it drives (and the shoulder empty and
    the Arm head), at one frame. The rig's contract is that this stays under 0.5 mm."""
    if frame is not None:
        bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    arm = actor.rig.evaluated_get(dg)
    worst = 0.0
    for jn, (bn, _p, _g) in JOINTS.items():
        pb = arm.pose.bones[P + bn]
        hb = arm.matrix_world @ pb.head
        he = actor.J[jn].evaluated_get(dg).matrix_world.translation
        worst = max(worst, (hb - he).length)
    return worst * 1000.0


def rotation_error(actor) -> float:
    """Largest angle in degrees between a bone's world rotation and its target's (should be ~0)."""
    dg = bpy.context.evaluated_depsgraph_get()
    arm = actor.rig.evaluated_get(dg)
    worst = 0.0
    for jn, (bn, _p, _g) in JOINTS.items():
        pb = arm.pose.bones[P + bn]
        qb = (arm.matrix_world @ pb.matrix).to_quaternion()
        qt = actor._aj_targets[jn].evaluated_get(dg).matrix_world.to_quaternion()
        ang = qb.rotation_difference(qt).angle
        worst = max(worst, math.degrees(min(ang, math.tau - ang)))
    return worst
