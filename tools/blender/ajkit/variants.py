# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/variants.py (Aj pack, 2026-11-26).
# Changes against the pack copy, nothing else: the folder paths come from ajkit.paths (pack at packs/aj_rebuild_v1, clips at
# library/characters/aj/mixamo) and `import faces` reads the vendored ajkit.faces. The armature and body were already
# arguments here. No algorithm or limit constant is changed.
"""Body size & age variants of Aj: Kid, Teen, Adult, Senior for the male and the female base (run inside Blender).

    import variants
    variants.apply("Female", "Senior")       # on an open base file (Aj_Base.blend or Aj_Female_Base.blend)
    variants.measure()                       # height, head height, heads tall, limb lengths ...
    act = variants.load_clip("Standing_Idle")    # a Mixamo clip, root motion scaled to this body
    variants.play(act)                       # put it on the armature
    variants.write_all()                     # rebuild costumes_hybrid/variants/Aj_<Sex>_<Age>.blend

How it works
------------
The current Aj is the Teen (Teen Male = Aj_Base.blend unchanged). Every other variant is made from a base copy by
re-proportioning the skeleton and the skin together:

* Each deform bone gets a scale in its own frame (length along the bone, width and depth across it) and, for the
  senior's posture, an extra rest rotation. From those, every bone gets one affine map T_b (rest space -> new rest
  space); a child's head goes where its parent's map sends it, so the joints stay connected.
* The skin follows with the same maps, blended by the skin weights (M_v = sum w_b T_b). Every shape key (sizing,
  chest, face, expression and gaze keys) is mapped the same way, so all of them keep working on the variant.
* The armature's rest pose is rewritten (edit bones: new heads, lengths, rest rotations; bone names, rolls of
  unrotated bones and the hierarchy unchanged). Mixamo clips key only bone rotations plus the Hips location, so they
  play on the new skeleton unchanged; `load_clip` / `retarget` scale the Hips location by the leg-length ratio.
* The head is never reshaped: Head and Neck get no scale and no relative rotation, so everything weighted to them
  (the whole head, eyes and brows) moves as one rigid piece. `head_matrix()` gives that rigid map, to move
  head-fitted assets (hair, beards, hats) onto a variant. The mouth is untouched (it is a 2D layer).
* The feet are kept and put on the floor (z = 0) after the change.

Faces come from faces.PRESETS, the chest from the Female_Chest key, and limb bulk partly from the existing
Arms_/Legs_Thicker/Thinner keys. Proportions are in SPECS; edit them there.

Works on any copy of the Aj body (vertex order does not matter: everything is driven by the skin weights and bone
positions). Apply variants to a body at base proportions only; the body is marked (custom property `aj_variant`).
Run base.add_chest_key / faces.add_face_keys BEFORE apply (they compute from base rest-pose positions).
"""
import os, math
import bpy
from . import paths as _paths
import numpy as np
from mathutils import Matrix, Vector

BODY = "Aj_Base_Body"
ARM = "Armature"
P = "mixamorig:"
PROP = "aj_variant"
ROOT = _paths.ROOT
BASE_FILE = _paths.BASE_FILE
FEMALE_FILE = _paths.FEMALE_FILE
OUT_DIR = _paths.OUT_DIR
ANIM_DIR = _paths.ANIM_DIR

SEXES = ("Male", "Female")
AGES = ("Kid", "Teen", "Adult", "Senior")

# ------------------------------------------------------------------------------------------------ specs
# Factors relative to the base (Teen) body. Lengths scale along the bone, *_w / *_d across it (width = the axis
# nearest world X, depth = front-back), *_r both across directions (limb thickness).
#   torso: Hips/Spine/Spine1/Spine2 length    leg: thigh+shin length    foot/hand: uniform (fingers/toes included)
#   arm: upper arm + forearm length            shoulder: collar-bone length (shoulder width)
#   hip_w/hip_d (Hips), belly_w/belly_d (Spine), waist_w/waist_d (Spine1), chest_w/chest_d (Spine2)
#   arm_r, leg_r: limb thickness              posture: {bone: (x, y, z) degrees} extra rest rotation about world
#   axes, relative to the parent (x = pitch, + bends an upward bone forward); "level" = back to the base
#   orientation; ("level", (x, y, z)) = the base orientation turned by (x, y, z), ignoring the parent.
#   keys: shape-key values       face: faces.PRESETS name
NEUTRAL = dict(torso=1.0, leg=1.0, foot=1.0, arm=1.0, hand=1.0, shoulder=1.0,
               hip_w=1.0, hip_d=1.0, belly_w=1.0, belly_d=1.0, waist_w=1.0, waist_d=1.0,
               chest_w=1.0, chest_d=1.0, arm_r=1.0, leg_r=1.0, posture={}, keys={}, face="Teen Classic")

# Senior posture. Rule learnt from the renders: neighbouring bones whose skin blends (Spine2 / Shoulder / Neck)
# must not differ by much more than ~15-18 deg, or the blend folds the skin (a lump at the base of the throat).
_STOOP = {   # rounded back spread over the spine, head carried forward, shoulders rounded forward, soft knees
    "Spine": (5.0, 0, 0), "Spine1": (9.0, 0, 0), "Spine2": (10.0, 0, 0),
    "Neck": (-18.0, 0, 0), "Head": (0, 0, 0),           # head rigid with the neck: faces 6 deg down
    "LeftShoulder": (0, 6.0, -6.0), "RightShoulder": (0, -6.0, 6.0),     # collarbones follow the chest, rounded
    "LeftArm": "level", "RightArm": "level",             # arm frames as on the base, so clips hang the arms
    # beside the body as on the base (a forward-tilted frame put the hands into the thighs)
    "LeftUpLeg": (-6.0, 0, 0), "RightUpLeg": (-6.0, 0, 0),
    "LeftLeg": (12.0, 0, 0), "RightLeg": (12.0, 0, 0),
    "LeftFoot": "level", "RightFoot": "level",          # feet flat
}
_STOOP_F = dict(_STOOP, Spine=(4.0, 0, 0), Spine1=(8.0, 0, 0), Spine2=(9.0, 0, 0), Neck=(-16.0, 0, 0),
                LeftUpLeg=(-5.0, 0, 0), RightUpLeg=(-5.0, 0, 0), LeftLeg=(10.0, 0, 0), RightLeg=(10.0, 0, 0))

SPECS = {
    ("Male", "Kid"): dict(torso=0.80, leg=0.68, foot=0.82, arm=0.72, hand=0.84, shoulder=0.86,
                          hip_w=0.85, belly_d=1.08, belly_w=0.97, waist_w=0.93, chest_w=0.90, chest_d=0.95,
                          arm_r=1.0, leg_r=1.0, face="Kid Round"),
    ("Female", "Kid"): dict(torso=0.80, leg=0.68, foot=0.80, arm=0.72, hand=0.82, shoulder=0.84,
                            hip_w=0.87, belly_d=1.06, belly_w=0.96, waist_w=0.92, chest_w=0.89, chest_d=0.95,
                            arm_r=0.98, leg_r=1.0, keys={"Female_Chest": 0.0}, face="Kid Bright"),
    ("Male", "Teen"): dict(),        # the base Aj, unchanged
    ("Female", "Teen"): dict(hip_w=1.05, waist_w=0.96, shoulder=0.95, keys={"Female_Chest": 0.7}),
    ("Male", "Adult"): dict(torso=1.10, leg=1.15, foot=1.12, arm=1.12, hand=1.12, shoulder=1.40,
                            hip_w=1.04, belly_w=1.06, waist_w=1.06, waist_d=1.04, chest_w=1.15, chest_d=1.12,
                            arm_r=1.15, leg_r=1.10, keys={"Arms_Thicker": 0.5, "Legs_Thicker": 0.3},
                            face="Adult Broad"),
    ("Female", "Adult"): dict(torso=1.07, leg=1.13, foot=1.04, arm=1.08, hand=1.03, shoulder=1.05,
                              hip_w=1.16, hip_d=1.08, belly_w=1.02, waist_w=0.94, chest_w=1.02,
                              arm_r=1.02, leg_r=1.06, keys={"Female_Chest": 1.0, "Legs_Thicker": 0.3},
                              face="Adult Sculpted"),
    ("Male", "Senior"): dict(torso=1.0, leg=1.10, foot=1.12, arm=1.10, hand=1.12, shoulder=1.28,
                             hip_w=1.06, belly_w=1.14, belly_d=1.22, waist_w=1.14, waist_d=1.16,
                             chest_w=1.10, chest_d=1.08, arm_r=1.04, leg_r=1.0,
                             keys={"Arms_Thinner": 0.2, "Legs_Thinner": 0.3},
                             posture=_STOOP, face="Senior Strong"),
    ("Female", "Senior"): dict(torso=0.98, leg=1.09, foot=1.04, arm=1.06, hand=1.03, shoulder=1.04,
                               hip_w=1.11, hip_d=1.06, belly_w=1.06, belly_d=1.10, waist_w=1.04, waist_d=1.06,
                               chest_w=1.02, arm_r=0.98, leg_r=1.02,
                               keys={"Female_Chest": 0.9, "Arms_Thinner": 0.3},
                               posture=_STOOP_F, face="Senior Soft"),
}


def spec(sex, age):
    if (sex, age) not in SPECS:
        raise KeyError(f"unknown variant {sex} {age}; sexes {SEXES}, ages {AGES}")
    s = dict(NEUTRAL)
    s.update(SPECS[(sex, age)])
    if sex == "Female" and "Female_Chest" not in s["keys"]:
        s["keys"] = dict(s["keys"], Female_Chest=1.0)
    return s


def file_name(sex, age):
    return os.path.join(OUT_DIR, f"Aj_{sex}_{age}.blend")


# ------------------------------------------------------------------------------------------- bone plan

def _short(n):
    return n.replace(P, "")


def _scale_for(name, s):
    """(width, length, depth) factors for one bone."""
    n = _short(name)
    if n == "Hips":
        return (s["hip_w"], s["torso"], s["hip_d"])
    if n == "Spine":
        return (s["belly_w"], s["torso"], s["belly_d"])
    if n == "Spine1":
        return (s["waist_w"], s["torso"], s["waist_d"])
    if n == "Spine2":
        return (s["chest_w"], s["torso"], s["chest_d"])
    if n.endswith("Shoulder"):
        return (1.0, s["shoulder"], 1.0)
    if n.endswith("ForeArm"):
        r = s["arm_r"]
        return (r, s["arm"], r)
    if n.endswith("Arm"):
        r = s["arm_r"]
        return (r, s["arm"], r)
    if "Hand" in n:
        h = s["hand"]
        return (h, h, h)
    if n.endswith("UpLeg"):
        r = s["leg_r"]
        return (r, s["leg"], r)
    if n.endswith("Leg"):
        r = 1.0 + 0.7 * (s["leg_r"] - 1.0)
        return (r, s["leg"], r)
    if "Foot" in n or "Toe" in n:
        f = s["foot"]
        return (f, f, f)
    return (1.0, 1.0, 1.0)    # Neck, Head (the head is never reshaped) and the non-deform extras


def _euler(d):
    from mathutils import Euler
    return Euler([math.radians(a) for a in d], "XYZ").to_matrix()


def plan(arm, s):
    """Per bone: old head (world), new head, 3x3 linear map L, new rest rotation, length factor.
    Returns (order, info) with info[name] = dict(h0, h1, L, R0, R1, sy)."""
    mw = arm.matrix_world
    bones = arm.data.bones
    order = []

    def walk(b):
        order.append(b)
        for c in b.children:
            walk(c)
    for b in bones:
        if b.parent is None:
            walk(b)
    info = {}
    I3 = Matrix.Identity(3)
    for b in order:
        M = mw @ b.matrix_local
        R0 = M.to_3x3().normalized()
        h0 = M.to_translation()
        w, l, d = _scale_for(b.name, s)
        # local axis carrying the width: the one (X or Z) more aligned with world X
        ax, az = R0.col[0], R0.col[2]
        sx, sz = (w, d) if abs(ax.x) >= abs(az.x) else (d, w)
        S = Matrix.Diagonal((sx, l, sz))
        par = info.get(b.parent.name) if b.parent else None
        Qp = par["Q"] if par else I3.copy()
        pose_d = s["posture"].get(_short(b.name))
        if pose_d == "level":
            Q = I3.copy()
        elif isinstance(pose_d, tuple) and pose_d and pose_d[0] == "level":
            Q = _euler(pose_d[1])
        elif pose_d is not None:
            Q = Qp @ _euler(pose_d)
        else:
            Q = Qp.copy()
        L = Q @ R0 @ S @ R0.transposed()
        h1 = par["T"](h0) if par else h0.copy()

        def T(x, h0=h0, h1=h1, L=L):
            return h1 + L @ (Vector(x) - h0)
        info[b.name] = dict(h0=h0, h1=h1, L=L, Q=Q, R0=R0, R1=(Q @ R0), sy=l, T=T, deform=b.use_deform)
    return order, info


def _affine(i, shift):
    """3x4 numpy affine of a bone's map, with a final world translation."""
    L = np.array(i["L"], dtype=np.float64)
    t = np.array(i["h1"], dtype=np.float64) - L @ np.array(i["h0"], dtype=np.float64) + shift
    return np.hstack([L, t[:, None]])


def _weights(body, names):
    """Dense (n_verts, n_bones) normalized weights over the deform bones in `names`."""
    idx = {n: k for k, n in enumerate(names)}
    gmap = {g.index: idx.get(g.name) for g in body.vertex_groups}
    nv = len(body.data.vertices)
    W = np.zeros((nv, len(names)), dtype=np.float64)
    for v in body.data.vertices:
        for g in v.groups:
            k = gmap.get(g.group)
            if k is not None and g.weight > 0:
                W[v.index, k] += g.weight
    tot = W.sum(1)
    if (tot <= 0).any():
        hips = idx[P + "Hips"]
        W[tot <= 0, hips] = 1.0
        tot = W.sum(1)
    return W / tot[:, None]


def _key_coords(kb):
    a = np.empty(len(kb.data) * 3, dtype=np.float64)
    kb.data.foreach_get("co", a)
    return a.reshape(-1, 3)


def _is_neutral(s):
    keys = ("torso", "leg", "foot", "arm", "hand", "shoulder", "hip_w", "hip_d", "belly_w", "belly_d",
            "waist_w", "waist_d", "chest_w", "chest_d", "arm_r", "leg_r")
    return all(abs(s[k] - 1.0) < 1e-9 for k in keys) and not s["posture"]


# --------------------------------------------------------------------------------------------- apply

def apply(sex, age, arm=None, body=None, face=True):
    """Turn the base body (and its armature) in the open file into the given variant, in place.

    Returns measure() of the result. Teen Male leaves the geometry untouched (it is the base)."""
    arm = arm or bpy.data.objects[ARM]
    body = body or bpy.data.objects[BODY]
    if body.get(PROP) or arm.get(PROP):
        raise RuntimeError(f"already a variant ({body.get(PROP) or arm.get(PROP)}): start from a base file")
    s = spec(sex, age)
    if not _is_neutral(s):
        _reshape(arm, body, s)
    keys = body.data.shape_keys.key_blocks
    for k, v in s["keys"].items():
        keys[k].value = v
    if sex == "Male" and "Female_Chest" in keys and "Female_Chest" not in s["keys"]:
        keys["Female_Chest"].value = 0.0
    if face:
        from . import faces
        faces.apply_preset(s["face"], body)
    body[PROP] = arm[PROP] = f"{sex} {age}"
    if s["posture"]:
        arm["aj_ground"] = True
    body.data.update()
    bpy.context.view_layer.update()
    return measure(arm, body)


def _reshape(arm, body, s):
    order, info = plan(arm, s)
    deform = [b.name for b in order if b.use_deform]
    order = [b.name for b in order]   # Bone references die when edit mode rebuilds the bones
    Wt = _weights(body, deform)
    me = body.data
    Bw = np.array(body.matrix_world, dtype=np.float64)
    Bi = np.linalg.inv(Bw)
    keys = me.shape_keys.key_blocks if me.shape_keys else None
    basis = _key_coords(keys[0]) if keys else np.array([v.co[:] for v in me.vertices])

    def to_world(c):
        return c @ Bw[:3, :3].T + Bw[:3, 3]

    def blend(shift):
        A = np.stack([_affine(info[n], shift) for n in deform])          # (nb,3,4)
        return np.einsum("vb,bij->vij", Wt, A)                           # (nv,3,4)

    def deform_pts(Mv, c):
        pw = to_world(c)
        out = np.einsum("vij,vj->vi", Mv[:, :, :3], pw) + Mv[:, :, 3]
        return out @ Bi[:3, :3].T + Bi[:3, 3]

    zero = np.zeros(3)
    Mv = blend(zero)
    floor = to_world(deform_pts(Mv, basis))[:, 2].min()
    shift = np.array((0.0, 0.0, -floor))
    Mv = blend(shift)
    # skin: every key block mapped by the same per-vertex affine
    if keys:
        for kb in keys:
            c = deform_pts(Mv, _key_coords(kb))
            kb.data.foreach_set("co", c.astype(np.float32).ravel())
        me.vertices.foreach_set("co", _key_coords(keys[0]).astype(np.float32).ravel())
    else:
        me.vertices.foreach_set("co", deform_pts(Mv, basis).astype(np.float32).ravel())
    me.update()
    # skeleton: new rest pose
    sh = Vector(shift)
    Aw = arm.matrix_world
    Ai = Aw.inverted()
    Arot = Aw.to_3x3().normalized()
    ascale = Aw.to_scale()[0]
    prev_active = bpy.context.view_layer.objects.active
    lengths = {b.name: b.length for b in arm.data.bones}
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    for nm in order:
        i = info[nm]
        e = eb[nm]
        length = lengths[nm] * i["sy"]
        head = Ai @ (i["h1"] + sh)
        rot = Arot.inverted() @ i["R1"]
        mat = rot.to_4x4()
        mat.translation = head
        e.matrix = mat
        e.length = length
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = prev_active
    # check the skeleton landed where the skin went
    err = 0.0
    for nm in order:
        i = info[nm]
        err = max(err, ((Aw @ arm.data.bones[nm].head_local) - (i["h1"] + sh)).length)
    if err > 1e-4:
        raise RuntimeError(f"rest skeleton off by {err*1000:.2f} mm")
    hip0 = info[P + "LeftUpLeg"]["h0"].z
    hip1 = info[P + "LeftUpLeg"]["h1"].z + shift[2]
    arm["aj_root_scale"] = hip1 / hip0
    head = info[P + "Head"]
    H = Matrix.Translation(head["h1"] + sh) @ head["L"].to_4x4() @ Matrix.Translation(-head["h0"])
    arm["aj_head_matrix"] = [x for row in H for x in row]
    body["aj_head_rigid_mm"] = _head_rigidity(Wt, deform, Mv, H, basis, Bw) * 1000.0


def _head_rigidity(Wt, deform, Mv, H, basis, Bw):
    """Largest distance (m) between where the skin went and where the rigid head map sends it, over every vertex
    weighted mostly (>= 0.5) to the Head bone. 0 = the head kept its shape exactly."""
    k = deform.index(P + "Head")
    sel = Wt[:, k] >= 0.5
    Hn = np.array(H, dtype=np.float64)[:3]
    pw = basis[sel] @ Bw[:3, :3].T + Bw[:3, 3]
    a = np.einsum("vij,vj->vi", Mv[sel, :, :3], pw) + Mv[sel, :, 3]
    b = pw @ Hn[:, :3].T + Hn[:, 3]
    return float(np.linalg.norm(a - b, axis=1).max()) if sel.any() else 0.0


def head_matrix(arm=None):
    """World 4x4 taking base rest-pose head space to this variant's rest-pose head (rigid, no scale).
    Use it to move a head-fitted asset built for the base: obj.matrix_world = head_matrix() @ obj.matrix_world."""
    arm = arm or bpy.data.objects[ARM]
    v = arm.get("aj_head_matrix")
    if not v:
        return Matrix.Identity(4)
    v = list(v)
    return Matrix([v[0:4], v[4:8], v[8:12], v[12:16]])


# ------------------------------------------------------------------------------------------- measure

def measure(arm=None, body=None):
    """Rest-pose measurements in metres (shape keys as currently set, via the evaluated mesh at rest)."""
    arm = arm or bpy.data.objects[ARM]
    body = body or bpy.data.objects[BODY]
    old = arm.data.pose_position
    arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    ev.to_mesh_clear()
    arm.data.pose_position = old
    bpy.context.view_layer.update()
    Bw = np.array(body.matrix_world); co = co @ Bw[:3, :3].T + Bw[:3, 3]
    mw = arm.matrix_world
    J = {b.name.replace(P, ""): (mw @ b.head_local) for b in arm.data.bones}
    T = {b.name.replace(P, ""): (mw @ b.tail_local) for b in arm.data.bones}
    c0 = Vector((J["Hips"].x, J["Head"].y, 0.0))        # measure about the figure's own centre line
    co = co - np.array(c0)
    J = {k: v - c0 for k, v in J.items()}
    T = {k: v - c0 for k, v in T.items()}
    names = {g.index: g.name for g in body.vertex_groups}
    hk = next(i for i, nm in names.items() if nm == P + "Head")
    headw = np.zeros(n)
    for v in body.data.vertices:
        for g in v.groups:
            if g.group == hk:
                headw[v.index] = g.weight
    front = (headw > 0.95) & (np.abs(co[:, 0]) < 0.02)
    front &= co[:, 1] < -0.08
    chin = float(co[front, 2].min())
    top = float(co[:, 2].max())
    foot_len = float(np.ptp(co[co[:, 2] < 0.03, 1])) if (co[:, 2] < 0.03).any() else 0.0
    r = dict(
        variant=body.get(PROP, "base"),
        height=round(top, 3), chin=round(chin, 3), head_height=round(top - chin, 3),
        heads_tall=round(top / (top - chin), 2),
        leg_length=round(J["LeftUpLeg"].z, 3),                       # hip joint above the floor
        leg_ratio=round(J["LeftUpLeg"].z / top, 3),
        torso_length=round(J["Neck"].z - J["LeftUpLeg"].z, 3),       # hip joint to neck base
        arm_length=round((J["LeftArm"] - J["LeftHand"]).length, 3),   # shoulder joint to wrist
        hand_length=round((J["LeftHand"] - T["LeftHandMiddle4"]).length, 3),
        shoulder_span=round((J["LeftArm"] - J["RightArm"]).length, 3),
        hip_span=round(float(np.ptp(co[np.abs(co[:, 2] - J["LeftUpLeg"].z) < 0.02, 0])), 3),
        chest_width=round(float(np.ptp(co[(np.abs(co[:, 2] - (J["Spine2"].z + 0.06)) < 0.01)
                                           & (np.abs(co[:, 0]) < J["LeftArm"].x - 0.01), 0])), 3),
        foot_length=round(foot_len, 3),
        head_rigid_mm=round(float(body.get("aj_head_rigid_mm", 0.0)), 4),
    )
    return r


# ----------------------------------------------------------------------------------------- animation

def _channelbag(act):
    return act.layers[0].strips[0].channelbags[0]


def load_clip(stem, arm=None):
    """Import work/mixamo/anims/<stem>.fbx as an action and retarget it to this variant (Hips location scaled)."""
    arm = arm or bpy.data.objects[ARM]
    name = "MX_" + stem
    act = bpy.data.actions.get(name)
    if act is None:
        before_o, before_a = set(bpy.data.objects), set(bpy.data.actions)
        bpy.ops.import_scene.fbx(filepath=os.path.join(ANIM_DIR, stem + ".fbx"), ignore_leaf_bones=False)
        new_o = [o for o in bpy.data.objects if o not in before_o]
        ia = next(o for o in new_o if o.type == "ARMATURE")
        act = ia.animation_data.action
        act.name = name
        act.use_fake_user = True
        for a in [a for a in bpy.data.actions if a not in before_a and a != act]:
            bpy.data.actions.remove(a)
        for o in new_o:
            bpy.data.objects.remove(o, do_unlink=True)
    return retarget(act, arm)


def retarget(act, arm=None, body=None, ground=True):
    """Copy of a clip for this variant: Hips location keys times the leg-length ratio (aj_root_scale), so a crouch
    or a hip sway is as deep relative to the legs as on the base. Bone rotations need nothing.

    ground: then shift the Hips by a constant so the lower foot's lowest skin point sits on the floor (median over
    the clip). Needed for the bent-knee seniors (the clip's leg bends add to the rest bend, lifting the feet by
    5-13 mm); a constant shift keeps jumps and crouches as they are."""
    arm = arm or bpy.data.objects[ARM]
    body = body or next((o for o in arm.children if o.type == "MESH" and o.name.startswith(BODY)), None)
    k = float(arm.get("aj_root_scale", 1.0))
    if abs(k - 1.0) < 1e-6 and not (ground and arm.get("aj_ground")):
        return act
    name = f"{act.name}@{arm.get(PROP, 'variant')}"
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    new = act.copy()
    new.name = name
    hips = [fc for fc in _channelbag(new).fcurves if fc.data_path == f'pose.bones["{P}Hips"].location']
    for fc in hips:
        for kp in fc.keyframe_points:
            kp.co[1] *= k
            kp.handle_left[1] *= k
            kp.handle_right[1] *= k
    if ground and body is not None and arm.get("aj_ground") and hips:
        dz = _clip_floor(new, arm, body)
        if abs(dz) > 0.001:
            b = arm.data.bones[P + "Hips"]
            R = (arm.matrix_world.to_3x3().normalized() @ b.matrix_local.to_3x3()).normalized()
            v = R.inverted() @ Vector((0.0, 0.0, -dz)) / arm.matrix_world.to_scale()[0]
            for fc in hips:
                for kp in fc.keyframe_points:
                    for attr in ("co", "handle_left", "handle_right"):
                        getattr(kp, attr)[1] += v[fc.array_index]
        new["aj_ground_mm"] = dz * 1000.0
    return new


def _clip_floor(act, arm, body, samples=16):
    """Median over the clip of the lowest skin point (world z) when `act` plays on this armature."""
    ad = arm.animation_data or arm.animation_data_create()
    keep = (ad.action, ad.action_slot if ad.action else None)
    sc = bpy.context.scene
    keep_f = sc.frame_current
    ad.action = act
    if act.slots:
        ad.action_slot = act.slots[0]
    f0, f1 = act.frame_range
    lows = []
    for j in range(samples):
        sc.frame_set(int(round(f0 + (f1 - f0) * j / max(1, samples - 1))))
        dg = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(dg)
        m = ev.to_mesh()
        c = np.empty(len(m.vertices) * 3); m.vertices.foreach_get("co", c)
        ev.to_mesh_clear()
        c = c.reshape(-1, 3) @ np.array(body.matrix_world)[:3, :3].T + np.array(body.matrix_world)[:3, 3]
        lows.append(c[:, 2].min())
    ad.action = keep[0]
    if keep[0]:
        ad.action_slot = keep[1]
    sc.frame_set(keep_f)
    return float(np.median(lows))


def play(act, arm=None):
    arm = arm or bpy.data.objects[ARM]
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if act.slots:
        ad.action_slot = act.slots[0]
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = (int(round(x)) for x in act.frame_range)
    return act


def stand(arm=None, down=68.0):
    """Still pose for line-ups: arms lowered from the T-pose (pose only, the rest pose is untouched)."""
    arm = arm or bpy.data.objects[ARM]
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    from mathutils import Euler
    for side in ("Left", "Right"):
        pb = arm.pose.bones[P + side + "Arm"]
        pb.rotation_quaternion = Euler((math.radians(down), 0, 0)).to_quaternion()


# --------------------------------------------------------------------------------------------- files

def write_variant(sex, age, path=None):
    """Open the matching base file, apply the variant, save it as variants/Aj_<Sex>_<Age>.blend."""
    path = path or file_name(sex, age)
    src = FEMALE_FILE if sex == "Female" else BASE_FILE
    bpy.ops.wm.open_mainfile(filepath=src)
    r = apply(sex, age)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        import shutil, time
        bak = os.path.join(os.path.dirname(path), "backups")
        os.makedirs(bak, exist_ok=True)
        shutil.copy2(path, os.path.join(bak, time.strftime("%Y%m%d_%H%M%S_") + os.path.basename(path)))
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, compress=True)
    r["file"] = path
    return r


def write_all():
    return [write_variant(sx, ag) for sx in SEXES for ag in AGES]
