# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/joints.py (Aj pack, 2026-11-26).
# Changes against the pack copy, nothing else: the armature is a function argument (arm=) instead of the fixed object
# name "Armature" (two Aj in one scene), and `import grips` reads the vendored ajkit.grips. Without arm= the old name
# is used. No algorithm or limit constant is changed.
"""Plain-language joint control, IK reach, and keyframing for the Aj Mixamo rig.

Quick start (inside Blender):

    import joints, grips
    joints.relaxed()                                            # natural standing pose (arms down, relaxed fingers)
    joints.set("head", turn_left=15, nod_down=8)                # plain-language angles in degrees, clamped to limits
    joints.set("right_arm", out=22, forward=35)                 # zero gimbal lock from the hanging-arm pose
    joints.set("right_elbow", flex=85, pronate=55)
    print(joints.summary())                                     # read the current pose back in the same words

    # Hold a pen and touch its tip to a point on a desk/paper:
    grips.hold("Pen", "Right", "pen")
    joints.reach("Right", target=(-0.18, -0.36, 0.88), obj="Pen", point="tip")

    # Keyframe with smooth easing:
    joints.key(1, ease="SMOOTH")
    joints.set("head", turn_right=20)
    joints.key(25, ease="SMOOTH")

All bone axes and signs were measured directly on Aj_Base.blend (Mixamo rig, world front = -Y,
character Left = +X, character Right = -X, Up = +Z). Rest pose and bone names are never altered.
"""
import math
import bpy
from mathutils import Vector, Matrix, Euler, Quaternion

_builtin_set = set
P = "mixamorig:"
RAD = math.radians
DEG = math.degrees

# ----------------------------------------------------------------------------------- joint catalog
# Each standard joint maps plain-language motion names to (axis_index, sign, lo_deg, hi_deg).
# Positive value rotates bone local axis `axis_index` (0=X, 1=Y, 2=Z) by `sign * angle`.
# Right/LeftArm uses a gimbal-free spherical parameterization (out, forward, twist) defined below.

def _side_spec(side):
    s = 1.0 if side == "Right" else -1.0
    return {
        f"{side}Shoulder": {
            "order": "XYZ",
            "motions": {
                "shrug":   (0, -1.0, -12.0,  35.0),     # lift shoulder up (+Z)
                "forward": (2, -s,   -20.0,  28.0),     # protract shoulder forward (-Y)
                "twist":   (1,  s,   -15.0,  15.0),
            },
        },
        f"{side}ForeArm": {
            "order": "XYZ",
            "motions": {
                "flex":    (2, -s,     0.0, 145.0),     # bend elbow (0 = straight, 90 = right angle)
                "pronate": (1, -s,   -85.0,  90.0),     # + turns palm down, - turns palm up (supinate)
                "carry":   (0,  1.0,  -8.0,   8.0),     # tiny natural carry angle
            },
        },
        f"{side}Hand": {
            "order": "XYZ",
            "motions": {
                "flex":    (0,  1.0, -70.0,  75.0),     # + bends palm inward, - extends back
                "ulnar":   (2,  s,   -28.0,  38.0),     # + tilts toward pinky, - tilts toward thumb (radial)
                "twist":   (1, -s,   -18.0,  18.0),
            },
        },
        f"{side}UpLeg": {
            "order": "XYZ",
            "motions": {
                "forward":  (0,  1.0, -35.0, 120.0),    # + swings thigh forward/up, - extends leg back
                "out":      (2, -s,   -25.0,  65.0),    # + abducts leg outward, - crosses inward
                "turn_out": (1,  s,   -40.0,  50.0),    # + rotates toes outward, - pigeon-toes inward
            },
        },
        f"{side}Leg": {
            "order": "XYZ",
            "motions": {
                "flex":    (0, -1.0,   0.0, 140.0),     # bend knee backward (0 = straight)
                "twist":   (1,  s,   -15.0,  15.0),
                "side":    (2, -s,    -5.0,   5.0),
            },
        },
        f"{side}Foot": {
            "order": "XYZ",
            "motions": {
                "up":       (0,  1.0, -50.0,  35.0),    # + lifts toes (dorsiflex), - points toes (plantarflex)
                "turn_out": (1,  s,   -25.0,  25.0),
                "roll_in":  (2,  s,   -25.0,  25.0),    # + turns sole inward (inversion)
            },
        },
        f"{side}ToeBase": {
            "order": "XYZ",
            "motions": {
                "up":      (0,  1.0, -35.0,  50.0),
                "side":    (2,  s,   -10.0,  10.0),
                "twist":   (1,  s,   -10.0,  10.0),
            },
        },
    }


JOINTS = {
    "Hips": {
        "order": "YXZ",
        "motions": {
            "forward":    (0,  1.0, -40.0,  65.0),      # + pitches pelvis/torso forward
            "turn_left":  (1,  1.0, -180.0, 180.0),     # + turns facing toward character's left
            "tilt_right": (2,  1.0, -35.0,  35.0),      # + leans toward character's right
        },
    },
    "Spine": {
        "order": "YXZ",
        "motions": {
            "forward":    (0,  1.0, -25.0,  40.0),
            "turn_left":  (1,  1.0, -35.0,  35.0),
            "tilt_right": (2,  1.0, -25.0,  25.0),
        },
    },
    "Spine1": {
        "order": "YXZ",
        "motions": {
            "forward":    (0,  1.0, -25.0,  40.0),
            "turn_left":  (1,  1.0, -35.0,  35.0),
            "tilt_right": (2,  1.0, -25.0,  25.0),
        },
    },
    "Spine2": {
        "order": "YXZ",
        "motions": {
            "forward":    (0,  1.0, -25.0,  35.0),
            "turn_left":  (1,  1.0, -35.0,  35.0),
            "tilt_right": (2,  1.0, -25.0,  25.0),
        },
    },
    "Neck": {
        "order": "YXZ",
        "motions": {
            "nod_down":   (0,  1.0, -30.0,  35.0),
            "turn_left":  (1,  1.0, -40.0,  40.0),
            "tilt_right": (2,  1.0, -25.0,  25.0),
        },
    },
    "Head": {
        "order": "YXZ",
        "motions": {
            "nod_down":   (0,  1.0, -35.0,  42.0),
            "turn_left":  (1,  1.0, -55.0,  55.0),
            "tilt_right": (2,  1.0, -30.0,  30.0),
        },
    },
}
JOINTS.update(_side_spec("Right"))
JOINTS.update(_side_spec("Left"))

# Spherical arm joints (measured from hanging straight down at the side):
#   out     = abduction off the torso (0 = straight down, 22 = relaxed hanging, 90 = T-pose, 165 = overhead)
#   forward = flexion in front of the torso (0 = at side, 90 = pointing straight ahead, -45 = reaching behind)
#   twist   = axial roll about the upper arm (+ = external/thumb-out, - = internal/thumb-in)
ARM_LIMITS = {
    "out":     (-25.0, 170.0),
    "forward": (-55.0, 155.0),
    "twist":   (-85.0,  85.0),
}
ARM_BONES = {"RightArm": "Right", "LeftArm": "Left"}

# Friendly joint aliases (case-insensitive)
JOINT_ALIASES = {
    "hips": "Hips", "pelvis": "Hips", "root": "Hips",
    "spine": "Spine", "waist": "Spine", "lower_back": "Spine",
    "spine1": "Spine1", "mid_back": "Spine1", "torso": "Spine1",
    "spine2": "Spine2", "chest": "Spine2", "upper_back": "Spine2",
    "neck": "Neck", "head": "Head",
}
for _side in ("Right", "Left"):
    _s = _side.lower()
    JOINT_ALIASES.update({
        f"{_s}_clavicle": f"{_side}Shoulder", f"{_s}_collar": f"{_side}Shoulder",
        f"{_s}_shoulder": f"{_side}Arm",      f"{_s}_arm": f"{_side}Arm", f"{_s}_upper_arm": f"{_side}Arm",
        f"{_s}_elbow": f"{_side}ForeArm",     f"{_s}_forearm": f"{_side}ForeArm",
        f"{_s}_wrist": f"{_side}Hand",        f"{_s}_hand": f"{_side}Hand",
        f"{_s}_hip": f"{_side}UpLeg",         f"{_s}_thigh": f"{_side}UpLeg", f"{_s}_upleg": f"{_side}UpLeg",
        f"{_s}_knee": f"{_side}Leg",          f"{_s}_shin": f"{_side}Leg", f"{_s}_leg": f"{_side}Leg",
        f"{_s}_ankle": f"{_side}Foot",        f"{_s}_foot": f"{_side}Foot",
        f"{_s}_toes": f"{_side}ToeBase",      f"{_s}_toe": f"{_side}ToeBase",
    })
    for _b in ("Shoulder", "Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "ToeBase"):
        JOINT_ALIASES[(_side + _b).lower()] = _side + _b

# Friendly motion synonyms -> (canonical_motion, sign_multiplier)
MOTION_ALIASES = {
    "back": ("forward", -1.0), "lean_back": ("forward", -1.0), "bend_forward": ("forward", 1.0),
    "turn_right": ("turn_left", -1.0), "look_left": ("turn_left", 1.0), "look_right": ("turn_left", -1.0),
    "tilt_left": ("tilt_right", -1.0),
    "look_down": ("nod_down", 1.0), "look_up": ("nod_down", -1.0), "nod_up": ("nod_down", -1.0),
    "pitch": ("nod_down", 1.0),
    "raise": ("out", 1.0), "abduct": ("out", 1.0), "in": ("out", -1.0),
    "drop": ("shrug", -1.0),
    "bend": ("flex", 1.0), "extend": ("flex", -1.0),
    "supinate": ("pronate", -1.0), "palm_down": ("pronate", 1.0), "palm_up": ("pronate", -1.0),
    "radial": ("ulnar", -1.0), "thumb_side": ("ulnar", -1.0), "pinky_side": ("ulnar", 1.0),
    "turn_in": ("turn_out", -1.0),
    "point": ("up", -1.0), "dorsiflex": ("up", 1.0), "plantarflex": ("up", -1.0),
    "roll_out": ("roll_in", -1.0),
}


def _arm(arm=None):
    return arm if arm is not None else bpy.data.objects["Armature"]


def _resolve_joint(name):
    if name in JOINTS or name in ARM_BONES:
        return name
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    if key in JOINT_ALIASES:
        return JOINT_ALIASES[key]
    raise KeyError(f"unknown joint {name!r}; valid names include: {', '.join(sorted(_builtin_set(JOINTS) | _builtin_set(ARM_BONES)))}")


def _resolve_motion(joint, motion):
    m = motion.strip().lower().replace(" ", "_").replace("-", "_")
    valid = ARM_LIMITS if joint in ARM_BONES else JOINTS[joint]["motions"]
    if m in valid:
        return m, 1.0
    if m in MOTION_ALIASES:
        canon, mult = MOTION_ALIASES[m]
        if canon in valid:
            return canon, mult
        # e.g. "forward" alias on Neck/Head -> nod_down
        if m == "forward" and "nod_down" in valid:
            return "nod_down", 1.0
        if m in ("back", "lean_back") and "nod_down" in valid:
            return "nod_down", -1.0
    if m == "forward" and "nod_down" in valid:
        return "nod_down", 1.0
    if m in ("nod_down", "look_down") and "forward" in valid:
        return "forward", 1.0
    if m in ("nod_up", "look_up") and "forward" in valid:
        return "forward", -1.0
    raise KeyError(f"joint {joint!r} has no motion {motion!r}; expected one of {list(valid)}")


def _clamp(val, lo, hi, do_clamp):
    return max(lo, min(hi, float(val))) if do_clamp else float(val)


# --------------------------------------------------------------------------------- arm kinematics

def _arm_matrix(side, out_deg, forward_deg, twist_deg):
    """Local basis 3x3 rotation matrix for RightArm/LeftArm from anatomical (out, forward, twist).

    Conventions (0 deg = arm hanging straight down at the side):
      out=90, forward=0, twist=0 -> exact Mixamo T-pose (identity).
      out=22, forward=0, twist=0 -> relaxed arm at side (equivalent to X=+68 deg).
      out=0, forward=90, twist=0 -> arm pointing straight ahead (-Y), palm facing inward.
    """
    sgn = 1.0 if side == "Right" else -1.0
    # In rest pose (T-pose): RightArm X=(0,-1,0) [fwd], Y=(-1,0,0) [out], Z=(0,0,-1) [down]
    #                        LeftArm  X=(0,+1,0) [back], Y=(+1,0,0) [out], Z=(0,0,-1) [down]
    # 1. Start from T-pose and lower to `out` degrees off vertical: rotate about local X by (90 - out).
    R_out = Matrix.Rotation(RAD(90.0 - out_deg), 3, "X")
    # 2. Swing forward around the torso left-right axis (which is local -Y on Right, +Y on Left in rest space!):
    #    Check: on RightArm, local +Y = (-1,0,0) = -X_world; rotating hanging (-Z_world = +Z_local) by +forward
    #    about local +Y moves +Z_local toward +X_local = (0,-1,0) = FORWARD (-Y_world)!
    #    On LeftArm, local +Y = (+1,0,0) = +X_world; rotating +Z_local by -forward about local +Y moves
    #    +Z_local toward -X_local = (0,-1,0) = FORWARD (-Y_world)!
    R_fwd = Matrix.Rotation(RAD(forward_deg * sgn), 3, "Y")
    # 3. Axial twist about the posed arm shaft (local Y, applied innermost):
    #    From probe: +Y on RightArm rolls thumb up/out (external rotation), -Y on LeftArm does the same.
    R_tw = Matrix.Rotation(RAD(twist_deg * sgn), 3, "Y")
    return R_fwd @ R_out @ R_tw


def _arm_decompose(side, R):
    """Inverse of _arm_matrix: recover (out_deg, forward_deg, twist_deg) from a bone basis 3x3 matrix."""
    sgn = 1.0 if side == "Right" else -1.0
    # Where did local +Y (the arm shaft) go?
    # Under R_fwd(f*s) @ R_out(90-o):
    #   R_out(90-o) @ (0,1,0) = (0, sin(o), cos(o))
    #   R_fwd(f*s) @ (0, sin(o), cos(o)) = (sin(f*s)*cos(o), sin(o), cos(f*s)*cos(o))
    y = R.col[1]
    out = math.asin(max(-1.0, min(1.0, float(y.y))))
    # Handle overhead (out > 90 deg) vs normal range using Z/X quadrant if needed; default [-90, 90] unless cos(f) < 0
    fwd_s = math.atan2(float(y.x), float(y.z))
    if abs(fwd_s) > math.pi * 0.75 and out > 0:
        # Arm raised past horizontal toward overhead: flip into out in (90, 180]
        out = math.pi - out
        fwd_s = math.atan2(float(-y.x), float(-y.z))
    out_deg = DEG(out)
    fwd_deg = DEG(fwd_s) * sgn
    # Residual twist about bone local Y
    R_no_tw = _arm_matrix(side, out_deg, fwd_deg, 0.0)
    R_res = R_no_tw.transposed() @ R
    tw_s = math.atan2(float(R_res[0][2]), float(R_res[0][0]))
    tw_deg = DEG(tw_s) * sgn
    return {"out": round(out_deg, 1), "forward": round(fwd_deg, 1), "twist": round(tw_deg, 1)}


def _get_basis_3x3(pb):
    return pb.matrix_basis.to_3x3()


def _write_rotation(pb, mat3, order="XYZ"):
    if pb.rotation_mode == "QUATERNION":
        pb.rotation_quaternion = mat3.to_quaternion()
    else:
        pb.rotation_mode = order
        pb.rotation_euler = mat3.to_euler(order)


# --------------------------------------------------------------------------------- core pose API

def limits(joint=None):
    """Return anatomical limits in degrees: {motion: (min, max)} for one joint, or all joints."""
    if joint is not None:
        j = _resolve_joint(joint)
        if j in ARM_BONES:
            return dict(ARM_LIMITS)
        return {m: (lo, hi) for m, (_, _, lo, hi) in JOINTS[j]["motions"].items()}
    out = {b: dict(ARM_LIMITS) for b in ARM_BONES}
    for j, spec in JOINTS.items():
        out[j] = {m: (lo, hi) for m, (_, _, lo, hi) in spec["motions"].items()}
    return out


def get(joint, arm=None):
    """Read one joint's current plain-language angles (degrees)."""
    j = _resolve_joint(joint)
    pb = _arm(arm).pose.bones[P + j]
    R = _get_basis_3x3(pb)
    if j in ARM_BONES:
        return _arm_decompose(ARM_BONES[j], R)
    spec = JOINTS[j]
    e = R.to_euler(spec["order"])
    return {m: round(DEG(e[ax]) * sgn, 1) + 0.0 for m, (ax, sgn, _, _) in spec["motions"].items()}


def set(joint, clamp=True, update=True, arm=None, **motions):
    """Set one joint using plain-language motion angles in degrees (preserves unspecified axes).

    Example: joints.set("right_elbow", flex=85, pronate=45)
             joints.set("head", turn_left=15, nod_down=8)
             joints.set("right_arm", out=22, forward=35)
    """
    j = _resolve_joint(joint)
    pb = _arm(arm).pose.bones[P + j]
    if j in ARM_BONES:
        side = ARM_BONES[j]
        cur = _arm_decompose(side, _get_basis_3x3(pb))
        for k, v in motions.items():
            cm, mult = _resolve_motion(j, k)
            lo, hi = ARM_LIMITS[cm]
            cur[cm] = _clamp(v * mult, lo, hi, clamp)
        mat3 = _arm_matrix(side, cur["out"], cur["forward"], cur["twist"])
        _write_rotation(pb, mat3, order="XYZ")
        if update:
            bpy.context.view_layer.update()
        return {k: round(v, 1) + 0.0 for k, v in cur.items()}
    spec = JOINTS[j]
    order = spec["order"]
    e = _get_basis_3x3(pb).to_euler(order)
    vals = [e[0], e[1], e[2]]
    for k, v in motions.items():
        cm, mult = _resolve_motion(j, k)
        ax, sgn, lo, hi = spec["motions"][cm]
        deg = _clamp(v * mult, lo, hi, clamp)
        vals[ax] = RAD(deg * sgn)
    mat3 = Euler(vals, order).to_matrix()
    _write_rotation(pb, mat3, order=order)
    if update:
        bpy.context.view_layer.update()
    return get(j, arm)


def pose(spec, reset_first=False, clamp=True, update=True, arm=None, body=None):
    """Apply a dict of {joint_name: {motion: deg}} in one call.

    Special keys supported:
      "right_hand_pose" / "left_hand_pose": "open", "relaxed", "fist", or float 0..1 fist amount.
    """
    if reset_first:
        reset(update=False, arm=arm)
    out = {}
    for jname, cfg in spec.items():
        key = jname.strip().lower().replace(" ", "_").replace("-", "_")
        if key in ("right_hand_pose", "left_hand_pose"):
            from . import grips
            side = "Right" if key.startswith("right") else "Left"
            if cfg == "open":
                grips.open_hand(side, flex=(4, 5, 3), arm=arm, body=body)
            elif cfg == "relaxed":
                grips.open_hand(side, flex=(14, 18, 10), arm=arm, body=body)
            elif cfg == "fist":
                grips.fist(side, 1.0, arm=arm, body=body)
            elif isinstance(cfg, (int, float)):
                grips.fist(side, float(cfg), arm=arm, body=body)
            out[jname] = cfg
            continue
        out[_resolve_joint(jname)] = set(jname, clamp=clamp, update=False, arm=arm, **cfg)
    if update:
        bpy.context.view_layer.update()
    return out


def reset(update=True, arm=None):
    """Reset the entire armature to T-pose rest."""
    a = _arm(arm)
    for pb in a.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    if update:
        bpy.context.view_layer.update()


def relaxed(arm_out=22.0, elbow_flex=8.0, update=True, arm=None, body=None):
    """Natural standing pose: arms down by the sides with slight elbow bend and relaxed hands."""
    from . import grips
    reset(update=False, arm=arm)
    for side in ("Right", "Left"):
        set(f"{side}Arm", out=arm_out, forward=2.0, twist=0.0, update=False, arm=arm)
        set(f"{side}ForeArm", flex=elbow_flex, pronate=0.0, update=False, arm=arm)
        grips.open_hand(side, flex=(16, 20, 12), arm=arm, body=body)
    if update:
        bpy.context.view_layer.update()
    return describe(arm=arm)


def describe(threshold=1.0, include_all=False, arm=None):
    """Report the current pose in the same plain-language motion words and degrees.

    Motions within `threshold` degrees of neutral (0 deg, or out=90 for T-pose arms unless include_all)
    are omitted for conciseness. Also includes simple finger curl averages per hand."""
    out = {}
    order = (
        "Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
        "RightShoulder", "RightArm", "RightForeArm", "RightHand",
        "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
        "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
        "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
    )
    for j in order:
        vals = get(j, arm)
        if include_all:
            out[j] = vals
        else:
            if j in ARM_BONES:
                # always report arm if not in T-pose (out != 90 or forward/twist != 0)
                if abs(vals["out"] - 90.0) >= threshold or abs(vals["forward"]) >= threshold or abs(vals["twist"]) >= threshold:
                    out[j] = {k: v for k, v in vals.items() if k == "out" or abs(v) >= threshold}
            else:
                nz = {k: v for k, v in vals.items() if abs(v) >= threshold}
                if nz:
                    out[j] = nz
    # summarize finger flexion per hand
    a = _arm(arm)
    for side in ("Right", "Left"):
        curls = []
        for F in ("Index", "Middle", "Ring", "Pinky"):
            pb = a.pose.bones.get(f"{P}{side}Hand{F}2")
            if pb:
                curls.append(DEG(_get_basis_3x3(pb).to_euler("XYZ")[0]))
        avg = round(sum(curls) / len(curls), 1) if curls else 0.0
        if include_all or abs(avg) >= threshold:
            out[f"{side}Fingers"] = {"avg_pip_flex": avg}
    return out


def summary(threshold=1.0, arm=None):
    """One-line-per-joint plain-English description of the current pose."""
    d = describe(threshold=threshold, arm=arm)
    if not d:
        return "T-pose (all joints at rest)"
    lines = []
    for j, m in d.items():
        parts = ", ".join(f"{k}={v:+.1f}deg" if k != "out" else f"out={v:.1f}deg" for k, v in m.items())
        lines.append(f"{j}: {parts}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------- head look-at

def look_at(target, neck_share=0.35, clamp=True, update=True, arm=None):
    """Turn Neck and Head naturally toward world point `target` (or Blender object)."""
    if isinstance(target, str):
        target = bpy.data.objects[target].matrix_world.translation.copy()
    elif hasattr(target, "matrix_world"):
        target = target.matrix_world.translation.copy()
    else:
        target = Vector(target)
    a = _arm(arm)
    # reset Neck & Head first so Spine2's frame gives the un-turned forward reference
    set("Neck", nod_down=0, turn_left=0, tilt_right=0, update=False, arm=arm)
    set("Head", nod_down=0, turn_left=0, tilt_right=0, update=True, arm=arm)
    pb_h = a.pose.bones[P + "Head"]
    head_w = a.matrix_world @ pb_h.matrix
    eye_pos = head_w @ Vector((0.0, 0.16 / a.matrix_world.to_scale()[0], 0.0))  # rough eye height
    to_tgt = target - eye_pos
    if to_tgt.length < 1e-4:
        return {"Neck": get("Neck", arm), "Head": get("Head", arm)}
    # Express target vector in Head rest-orientation frame:
    #   local +X = character Left (+X_w), +Y = Up (+Z_w), +Z = Forward (-Y_w)
    m3 = head_w.to_3x3().normalized()
    loc = m3.inverted() @ to_tgt.normalized()
    yaw_left = DEG(math.atan2(loc.x, loc.z))       # +X is left, +Z is forward
    horiz = math.hypot(loc.x, loc.z)
    pitch_down = DEG(math.atan2(-loc.y, horiz))    # +Y is up -> looking down is positive nod_down
    r_n = set("Neck", turn_left=yaw_left * neck_share, nod_down=pitch_down * neck_share, clamp=clamp, update=False, arm=arm)
    r_h = set("Head", turn_left=yaw_left * (1.0 - neck_share), nod_down=pitch_down * (1.0 - neck_share),
              clamp=clamp, update=update, arm=arm)
    return {"Neck": r_n, "Head": r_h}


# ----------------------------------------------------------------------------- analytic arm IK reach

def _obj_tip_world(obj, point="tip"):
    """Find the world-space reach point on a held object (e.g. 'tip' of a pen, or explicit local/world Vector)."""
    from . import grips
    ob = bpy.data.objects[obj] if isinstance(obj, str) else obj
    if isinstance(point, str):
        if point == "tip":
            sh = grips.shaft(ob, at=0.02)
            # shaft's s[0] is the lower end (the writing tip on a pen, or pommel on a rod)
            # Find the actual extreme vertex at the s[0] end along sh["d"]
            dg = bpy.context.evaluated_depsgraph_get()
            best_p, best_s = None, 1e18
            d = Vector(sh["d"]).normalized()
            for o in grips._meshes(ob):
                e = o.evaluated_get(dg); me = e.to_mesh()
                mw = o.matrix_world
                for v in me.vertices:
                    w = mw @ v.co
                    s = w.dot(d)
                    if s < best_s:
                        best_s, best_p = s, w
                e.to_mesh_clear()
            return best_p if best_p is not None else sh["g"]
        if point == "top":
            sh = grips.shaft(ob, at=0.98)
            dg = bpy.context.evaluated_depsgraph_get()
            best_p, best_s = None, -1e18
            d = Vector(sh["d"]).normalized()
            for o in grips._meshes(ob):
                e = o.evaluated_get(dg); me = e.to_mesh()
                mw = o.matrix_world
                for v in me.vertices:
                    w = mw @ v.co
                    s = w.dot(d)
                    if s > best_s:
                        best_s, best_p = s, w
                e.to_mesh_clear()
            return best_p if best_p is not None else sh["g"]
        if point == "center":
            sh = grips.shaft(ob, at=0.5)
            return sh["g"]
        raise ValueError(f"unknown point selector {point!r} (expected 'tip', 'top', 'center', or 3D vector)")
    return Vector(point)


def reach(side, target, obj=None, point=None, pole=None, keep_hand_rot=True,
          shoulder_follow=0.25, update=True, arm=None):
    """Analytic two-bone IK for the arm: move the wrist (or a held object's tip) to world `target`.

    Parameters:
      side: "Right" or "Left".
      target: world (x, y, z) position (or Blender object).
      obj: optional held object (bone-parented to `{side}Hand`); if given, its `point` (default "tip")
           is placed on `target` while keeping the grip intact.
      point: "tip", "top", "center", or a current world-space 3D point rigidly moving with the hand
             (for example a fingertip pad or pen tip).
      pole: optional world elbow-hint direction (default: natural outward-down-back elbow bend).
      keep_hand_rot: if True (default), keep the hand's current world orientation (so held objects
                     and pen angle stay steady as the arm moves).
      shoulder_follow: 0..0.5; gentle clavicle shrug/protraction toward far targets for natural reach.

    Returns {"reached", "error_mm", "shortfall_mm", "elbow_flex_deg", "point_world", "wrist_world"}.
    """
    side = "Right" if side.strip().lower().startswith("r") else "Left"
    sgn = 1.0 if side == "Right" else -1.0
    if isinstance(target, str):
        target = bpy.data.objects[target].matrix_world.translation.copy()
    elif hasattr(target, "matrix_world"):
        target = target.matrix_world.translation.copy()
    else:
        target = Vector(target)

    a = _arm(arm)
    bpy.context.view_layer.update()
    A = a.matrix_world
    Ai = A.inverted()
    scale = A.to_scale()[0]
    chain = [f"{side}Arm", f"{side}ForeArm", f"{side}Hand"]
    pbs = {b: a.pose.bones[P + b] for b in chain}

    # Determine the active end-effector point in world space (before IK) and its rigid offset from wrist
    W_cur_w = A @ pbs[chain[2]].matrix.translation
    if obj is not None:
        P_cur_w = _obj_tip_world(obj, "tip" if point is None else point)
    elif point is not None:
        P_cur_w = Vector(point)
    else:
        P_cur_w = W_cur_w.copy()
    # rigid world offset from wrist to effector point (preserved when keep_hand_rot=True)
    eff_offset_w = P_cur_w - W_cur_w
    W_tgt_w = target - eff_offset_w

    # Optional gentle clavicle follow toward the target before solving the 2-bone arm
    if shoulder_follow > 0.0:
        S_w = A @ pbs[chain[0]].matrix.translation
        arm_len = (pbs[chain[1]].head - pbs[chain[0]].head).length * scale + \
                  (pbs[chain[2]].head - pbs[chain[1]].head).length * scale
        rel = W_tgt_w - S_w
        if rel.length > arm_len * 0.65:
            frac = min(1.0, (rel.length - arm_len * 0.65) / max(arm_len * 0.45, 1e-4)) * shoulder_follow
            shrug = max(-10.0, min(28.0, (rel.z / max(rel.length, 1e-4)) * 35.0 * frac))
            protract = max(-15.0, min(25.0, (-rel.y / max(rel.length, 1e-4)) * 32.0 * frac))
            set(f"{side}Shoulder", shrug=shrug, forward=protract, update=True, arm=arm)
            # Recompute effector offset AFTER clavicle rotation so hand orientation & offset match exactly
            W_cur_w = A @ pbs[chain[2]].matrix.translation
            if obj is not None:
                P_cur_w = _obj_tip_world(obj, "tip" if point is None else point)
                eff_offset_w = P_cur_w - W_cur_w
                W_tgt_w = target - eff_offset_w

    # Refresh armature-space matrices after any clavicle motion
    Mu, Mf, Mh = pbs[chain[0]].matrix.copy(), pbs[chain[1]].matrix.copy(), pbs[chain[2]].matrix.copy()
    par_name = pbs[chain[0]].parent.name
    Tp_sh = a.pose.bones[par_name].matrix.copy()
    Rl = {b: a.data.bones[P + b].matrix_local.copy() for b in chain}
    Rl["parent"] = a.data.bones[par_name].matrix_local.copy()

    S, E, W = Mu.translation.copy(), Mf.translation.copy(), Mh.translation.copy()
    Wn = Ai @ W_tgt_w
    L1 = (E - S).length
    L2 = (W - E).length
    Lv = Wn - S
    L = Lv.length
    max_reach = (L1 + L2) * 0.998
    min_reach = abs(L1 - L2) + 0.02 * (L1 + L2)
    shortfall = 0.0
    if L > max_reach:
        shortfall = (L - max_reach) * scale
        L = max_reach
        Wn = S + Lv.normalized() * L
    elif L < min_reach:
        L = min_reach
        Wn = S + (Lv.normalized() if Lv.length > 1e-6 else Vector((0, 0, -1))) * L

    u = (Wn - S).normalized()
    # Natural elbow pole in armature space:
    # if user gave `pole`, use it; otherwise blend current elbow bend with natural outward-back-down hint
    if pole is not None:
        pole_a = (Ai.to_3x3() @ Vector(pole)).normalized()
    else:
        cur_pole = (E - S) - u * (E - S).dot(u)
        # world hint: outward (-X right / +X left), backward (+Y), downward (-Z)
        hint_w = Vector((-0.55 * sgn, 0.55, -0.65)).normalized()
        hint_a = (Ai.to_3x3() @ hint_w).normalized()
        if cur_pole.length > 0.15 * L1:
            pole_a = (cur_pole.normalized() * 0.6 + hint_a * 0.4).normalized()
        else:
            pole_a = hint_a
    v = pole_a - u * pole_a.dot(u)
    if v.length < 1e-6:
        v = u.orthogonal()
    v.normalize()

    ca = max(-1.0, min(1.0, (L1 * L1 + L * L - L2 * L2) / (2.0 * L1 * L)))
    sa = math.sqrt(max(0.0, 1.0 - ca * ca))
    En = S + L1 * (ca * u + sa * v)
    Wn = En + (Wn - En).normalized() * L2

    # Construct anatomically clean Arm & ForeArm frames:
    # On Aj's Mixamo rig, elbow flexion rotates ForeArm about local (-Z on Right, +Z on Left),
    # meaning the elbow bends in the plane spanned by (+Y_upper, -X_upper*sgn) — i.e., local +Z
    # is perpendicular to the arm-forearm plane (pointing along -(u_arm x u_fore)*sgn)!
    u1 = (En - S).normalized()
    u2 = (Wn - En).normalized()
    bend_n = u1.cross(u2)
    if bend_n.length > 1e-5:
        bend_n.normalize()
        # Verify sign: in rest pose, RightForeArm -Z moves +Y=(-1,0,0) toward -Y_world=(0,-1,0),
        # so u1 x u2 = (-1,0,0) x (0,-1,0) = (0,0,+1) = -Z_local (since Z_local=(0,0,-1)).
        # On LeftForeArm, +Z moves +Y=(+1,0,0) toward -Y_world=(0,-1,0),
        # so u1 x u2 = (+1,0,0) x (0,-1,0) = (0,0,-1) = +Z_local!
        z_arm = (-bend_n * sgn).normalized()
        x_arm = u1.cross(z_arm).normalized()
        Ru = Matrix((x_arm, u1, z_arm)).transposed()
        # ForeArm shares the hinge axis z_arm (pure flexion) plus preserves the original forearm pronation!
        # Compute existing pronation of ForeArm relative to Arm before IK
        R_rel0 = (Rl[chain[1]].inverted() @ Rl[chain[0]] @ Mu.inverted() @ Mf).to_3x3()
        pron_rad = R_rel0.to_euler("XYZ")[1]
        x_fa = u2.cross(z_arm).normalized()
        Rf_no_pron = Matrix((x_fa, u2, z_arm)).transposed()
        Rf = Rf_no_pron @ Matrix.Rotation(pron_rad, 3, "Y")
    else:
        # Straight arm fallback: minimal swing from current pose
        R1 = (E - S).rotation_difference(u1).to_matrix()
        Ru = R1 @ Mu.to_3x3()
        Rf = R1 @ Mf.to_3x3()

    Mu2 = Matrix.Translation(S) @ Ru.to_4x4()
    Mf2 = Matrix.Translation(En) @ Rf.to_4x4()
    Rh = Mh.to_3x3() if keep_hand_rot else (Rf @ (Mf.to_3x3().transposed() @ Mh.to_3x3()))
    Mh2 = Matrix.Translation(Wn) @ Rh.to_4x4()

    new_m = {chain[0]: Mu2, chain[1]: Mf2, chain[2]: Mh2}
    par_m = {
        chain[0]: (Rl["parent"], Tp_sh),
        chain[1]: (Rl[chain[0]], Mu2),
        chain[2]: (Rl[chain[1]], Mf2),
    }
    for bn in chain:
        Rp, Tp = par_m[bn]
        basis = (Rl[bn].inverted() @ Rp @ Tp.inverted()) @ new_m[bn]
        _write_rotation(pbs[bn], basis.to_3x3(), order="XYZ")

    if update:
        bpy.context.view_layer.update()

    # Measure actual achieved point error
    W_after = A @ pbs[chain[2]].matrix.translation
    if obj is not None:
        P_after = _obj_tip_world(obj, "tip" if point is None else point)
    elif point is not None:
        P_after = W_after + (A.to_3x3() @ (Mh2.to_3x3() @ Mh.to_3x3().transposed() @ (Ai.to_3x3() @ eff_offset_w)))
    else:
        P_after = W_after
    err_mm = (P_after - target).length * 1000.0
    elbow_flex = get(f"{side}ForeArm", arm)["flex"]
    return {
        "reached": err_mm < 2.0,
        "error_mm": round(err_mm, 2),
        "shortfall_mm": round(shortfall * 1000.0, 1),
        "elbow_flex_deg": round(elbow_flex, 1),
        "point_world": [round(x, 4) for x in P_after],
        "wrist_world": [round(x, 4) for x in W_after],
    }


# --------------------------------------------------------------------------- keyframing & easing

def ease(t, kind="smooth"):
    """Scalar easing curve for t in [0, 1]: 'linear', 'smooth' (smoothstep), 'smoother',
    'ease_in', 'ease_out', 'overshoot' (gentle back-ease)."""
    t = max(0.0, min(1.0, float(t)))
    k = kind.strip().lower()
    if k == "linear":
        return t
    if k in ("smooth", "smoothstep", "ease_in_out"):
        return t * t * (3.0 - 2.0 * t)
    if k == "smoother":
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
    if k == "ease_in":
        return t * t * t
    if k == "ease_out":
        u = 1.0 - t
        return 1.0 - u * u * u
    if k in ("overshoot", "back"):
        c1 = 1.35; c3 = c1 + 1.0
        u = t - 1.0
        return 1.0 + c3 * u * u * u + c1 * u * u
    raise ValueError(f"unknown ease kind {kind!r}")


def _ensure_action(name="AgentAnim", arm=None):
    a = _arm(arm)
    ad = a.animation_data or a.animation_data_create()
    if ad.action is None:
        act = bpy.data.actions.get(name) or bpy.data.actions.new(name)
        ad.action = act
        if hasattr(act, "slots"):
            slot = next((s for s in act.slots if s.target_id_type == "OBJECT"), None)
            if slot is None:
                slot = act.slots.new(id_type="OBJECT", name=a.name)
            ad.action_slot = slot
    return ad.action


def _action_fcurves(act):
    if hasattr(act, "layers") and act.layers:
        out = []
        for lay in act.layers:
            for st in lay.strips:
                for cb in st.channelbags:
                    out.extend(cb.fcurves)
        return out
    return list(getattr(act, "fcurves", ()))


def key(frame, bones=None, ease_mode="SMOOTH", action_name="AgentAnim", include_location=False, arm=None):
    """Insert keyframes at `frame` for `bones` (None = all pose bones) with clean easing.

    ease_mode: "SMOOTH" (auto-clamped Bezier ease-in-out), "EASE_IN", "EASE_OUT",
               "LINEAR", "HOLD" (constant), or "OVERSHOOT" (BACK easing).
    """
    a = _arm(arm)
    act = _ensure_action(action_name, arm)
    if bones is None:
        pbs = list(a.pose.bones)
    else:
        pbs = []
        for b in bones:
            bn = P + _resolve_joint(b) if b in JOINTS or b in ARM_BONES or b.lower() in JOINT_ALIASES else (
                b if b.startswith(P) else P + b
            )
            if bn in a.pose.bones:
                pbs.append(a.pose.bones[bn])
    fr = int(round(frame))
    paths = _builtin_set()
    for pb in pbs:
        prop = "rotation_quaternion" if pb.rotation_mode == "QUATERNION" else "rotation_euler"
        pb.keyframe_insert(data_path=prop, frame=fr)
        paths.add(f'pose.bones["{pb.name}"].{prop}')
        if include_location or pb.name == P + "Hips":
            pb.keyframe_insert(data_path="location", frame=fr)
            paths.add(f'pose.bones["{pb.name}"].location')
    mode = ease_mode.strip().upper()
    for fc in _action_fcurves(act):
        if fc.data_path not in paths:
            continue
        for kp in fc.keyframe_points:
            if int(round(kp.co.x)) != fr:
                continue
            if mode == "LINEAR":
                kp.interpolation = "LINEAR"
            elif mode in ("HOLD", "CONSTANT"):
                kp.interpolation = "CONSTANT"
            elif mode in ("EASE_IN", "EASE_OUT"):
                kp.interpolation = "CUBIC"
                kp.easing = "EASE_IN" if mode == "EASE_IN" else "EASE_OUT"
            elif mode in ("OVERSHOOT", "BACK"):
                kp.interpolation = "BACK"
                kp.easing = "EASE_OUT"
                kp.back = 1.2
            else:
                kp.interpolation = "BEZIER"
                kp.handle_left_type = "AUTO_CLAMPED"
                kp.handle_right_type = "AUTO_CLAMPED"
        fc.update()
    return {"action": act.name, "frame": fr, "bones_keyed": len(pbs), "ease": mode}


def animate_poses(keyframes, ease_mode="SMOOTH", action_name="AgentAnim", fps=30, clear_old=True, arm=None):
    """Build a multi-keyframe animation from [(frame, spec_or_callable), ...].

    Each entry is (frame, pose_dict) or (frame, callable_taking_no_args).
    Example:
        joints.animate_poses([
            (1,  lambda: joints.relaxed()),
            (25, {"right_arm": {"out": 30, "forward": 70}, "right_elbow": {"flex": 95}, "head": {"turn_right": 15}}),
            (50, lambda: joints.relaxed()),
        ])
    """
    a = _arm(arm)
    if clear_old:
        old = bpy.data.actions.get(action_name)
        if old:
            bpy.data.actions.remove(old)
        if a.animation_data:
            a.animation_data.action = None
    sc = bpy.context.scene
    sc.render.fps = fps
    frames = []
    for item in keyframes:
        fr = item[0]
        spec = item[1]
        em = item[2] if len(item) > 2 else ease_mode
        if callable(spec):
            spec()
        else:
            pose(spec, arm=arm)
        key(fr, ease_mode=em, action_name=action_name, arm=arm)
        frames.append(int(round(fr)))
    if frames:
        sc.frame_start, sc.frame_end = min(frames), max(frames)
        sc.frame_set(frames[0])
    return {"action": action_name, "frames": frames, "fps": fps}
