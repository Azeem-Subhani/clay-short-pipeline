"""convert_pack.py - turn the dump of the 2D pack into 3D character sheets (config/cast3d.json). Stdlib only.

    py -3 convert_pack.py <pack_dump.json> <cast.json> <out cast3d.json> [--only Name,Name]

A sheet is: body (proportions), colors (+ the pack's colour names, so recolor() keeps working), face, and "parts": every
drawn costume part of the 2D character as a flat front outline. The 3D builder (stagekit/fig3d.py) decides how each
outline becomes 3D; OVERRIDES below corrects it where the automatic choice is wrong.
"""
import fnmatch
import json
import math
import sys
from pathlib import Path

SPECIAL = {"Ghost", "Mermaid", "Dragon", "Fairy", "Robot", "Alien", "Werewolf", "Mummy", "Genie", "Goblin", "Monster", "Devil", "Skeleton"}
STANDARD = ("Arm", "Arm_Lower", "Leg", "Leg_Lower", "Hand", "Hand_Grip", "Foot", "Torso", "Head", "Eye", "Brow", "Mouth", "Nose")

# what the automatic choice gets wrong, by part-name pattern (first match wins). {"as": how} or {"drop": True} or extra fields.
GLOBAL = [
    ("Collar_Ermine*", {"as": "collar_fur"}), ("Collar_Fur*", {"as": "collar_fur", "spots": False}),
    ("Collar_Spot*", {"drop": True}), ("Cape_Spot*", {"drop": True}), ("Cape_Ermine*", {"drop": True}), ("Cape_Fold*", {"drop": True}),
    ("Crown_Ball*", {"drop": True}), ("Crown_Gem*", {"drop": True}), ("Dress_Pleat*", {"drop": True}), ("Skirt_Pleat*", {"drop": True}),
    ("Trouser_Crotch*", {"drop": True}), ("Trouser_Seat*", {"drop": True}), ("Shorts_Seat*", {"drop": True}), ("Seat*", {"drop": True}),
    ("BodySide*", {"drop": True}), ("Helmet_Inside*", {"drop": True}), ("Hat_Under*", {"drop": True}), ("Belt_BuckleHole*", {"drop": True}),
    ("Neck", {"drop": True}), ("Neck.*", {"drop": True}), ("Knee*", {"drop": True}), ("Glasses_Arm*", {"drop": True}),
    ("Ear_Peek*", {"drop": True}), ("Boot_Highlight*", {"drop": True}), ("Helmet_Highlight*", {"drop": True}),
    ("Hair_Back*", {"as": "hair"}), ("Hair_Side*", {"as": "hair"}), ("Hood_Back*", {"as": "lathe"}),
    ("Tutu*", {"as": "band"}), ("Shorts", {"as": "limb"}), ("Hakama*", {"as": "limb"}),
]
OVERRIDES = {
    "Queen": {"parts": [("Dress_Waist", {"as": "band", "mat": "metal", "color": "#FFC83A", "z": [0.676, 0.704]})], "cape_lining": "#FFF8EA",
              "trim": {"hem": "#FFC83A", "cuffs": "#FFC83A", "front": "#F6E7C2"}, "face": {"lips": "#B23A42"},
              "hair": {"model": "female_layered_locks", "color": "#7E4526"},          # generated hair, approved 2026-11-23
              "looks": "queen, gold crown, layered chestnut hair, red dress, red cape lined with ermine"},
    "King": {"cape_lining": "#FFF8EA", "trim": {"hem": "#FFC83A", "cuffs": "#FFC83A"}},
    "Princess": {"trim": {"hem": "#F6E7C2", "cuffs": "#F6E7C2"}},
}

# generated hair and beards (library/hair): one list for the whole cast, shared with apply_generated.py
_GEN = Path(__file__).resolve().parents[2] / "config" / "cast3d_generated.json"
GENERATED = json.loads(_GEN.read_text(encoding="utf-8"))["characters"] if _GEN.exists() else {}


def bbox(pts):
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    return min(xs), min(zs), max(xs), max(zs)


def scan_x(pts, z):
    xs = []
    n = len(pts)
    for i in range(n):
        (x0, z0), (x1, z1) = pts[i], pts[(i + 1) % n]
        if (z0 <= z < z1) or (z1 <= z < z0):
            xs.append(x0 + (x1 - x0) * (z - z0) / (z1 - z0))
    return xs


def mix(a, b, k):
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{int(int(a[i:i + 2], 16) * (1 - k) + int(b[i:i + 2], 16) * k):02X}" for i in (0, 2, 4))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def convert(name, d, reg):
    P, B = d["parts"], d["bones"]
    ov = OVERRIDES.get(name, {})

    def blen(n):
        return math.hypot(B[n][2] - B[n][0], B[n][3] - B[n][1])

    hx0, hz0, hx1, hz1 = P["Head"]["box"]
    R = (hx1 - hx0) / 2
    head_z = (hz0 + hz1) / 2
    neck_z, hip_z = B["head"][1], B["body"][1]
    sh_x, sh_z = abs(B["arm_upper.L"][0]), B["arm_upper.L"][1]
    arm1, arm2 = blen("arm_upper.L"), blen("arm_lower.L")
    tilt = abs(B["arm_upper.L"][2] - B["arm_upper.L"][0]) / max(arm1, 1e-6)

    def limb_r(part, bone, lo, hi):
        if part not in P:
            return (lo + hi) / 2
        x0, z0, x1, z1 = P[part]["box"]
        return clamp(((x1 - x0) - blen(bone) * tilt * (1 if "arm" in bone else 0)) / 2, lo, hi)

    r_sh = limb_r("Arm.L", "arm_upper.L", 0.032, 0.062)
    r_wr = limb_r("Arm_Lower.L", "arm_lower.L", 0.028, 0.055) * 0.92
    r_hip = limb_r("Leg.L", "leg_upper.L", 0.036, 0.075)
    r_kn = limb_r("Leg_Lower.L", "leg_lower.L", 0.032, 0.070)
    hb = P.get("Hand.L", {}).get("box")
    hand_r = clamp((max(hb[2] - hb[0], hb[3] - hb[1]) / 2 * 0.9) if hb else 0.05, 0.036, 0.062)
    tp = P["Torso"]["pts"]
    tx0, tz0, tx1, tz1 = bbox(tp)
    prof = []
    n = 14
    for i in range(n + 1):
        z = tz1 - (tz1 - tz0) * i / n
        zq = clamp(z, tz0 + 0.004, tz1 - 0.004)
        xs = scan_x(tp, zq)
        prof.append([round(max((abs(x) for x in xs), default=0.05), 4), round(z, 4)])
    robe = bool(d.get("robe"))
    waist = hip_z
    if robe:
        cands = [p for p in prof if hip_z + 0.06 <= p[1] <= neck_z - 0.14]
        waist = min(cands, key=lambda p: p[0])[1] if cands else hip_z + 0.2
        waist = max(waist, hip_z + 0.12)
    fb = P.get("Foot.L", {}).get("box")
    foot = {"top": round(fb[3], 3) if fb else 0.0, "w": round(clamp((fb[2] - fb[0]) * 0.33, 0.036, 0.062), 3) if fb else 0.045,
            "len": round(0.105 * R / 0.27, 3)}
    height = max(p["box"][3] for p in P.values())
    body = dict(R=round(R, 4), head_z=round(head_z, 4), neck_z=neck_z, hip_z=hip_z, sh_x=round(sh_x, 4), sh_z=sh_z, arm1=round(arm1, 4), arm2=round(arm2, 4),
                hand_r=round(hand_r, 4), r_sh=round(r_sh, 4), r_el=round((r_sh + r_wr) / 2, 4), r_wr=round(r_wr, 4), hip_x=abs(B["leg_upper.L"][0]),
                leg_z=B["leg_upper.L"][1], knee_z=B["leg_lower.L"][1], ankle_z=B["foot.L"][1], r_hip=round(r_hip, 4), r_kn=round(r_kn, 4),
                r_an=round(r_kn * 0.86, 4), torso=prof, robe=robe, waist_z=round(waist, 4), foot=foot, ears=any(k.startswith("Ear") for k in P),
                height=round(height, 3))
    body.update(ov.get("body", {}))

    def hexof(part, default=None):
        return P[part]["hex"] if part in P else default

    def keyof(part):
        return P[part]["color"] if part in P else None

    skin = hexof("Head", "#F8D7B2")
    hand_part = "Glove.L" if "Glove.L" in P else "Hand.L"
    roles = {"skin": "Head", "torso": "Torso", "sleeve_u": "Arm.L", "sleeve_l": "Arm_Lower.L", "hand": hand_part, "leg_u": "Leg.L", "leg_l": "Leg_Lower.L",
             "shoe": "Foot.L"}
    colors = {r: hexof(p, skin) for r, p in roles.items()}
    keys = {r: keyof(p) for r, p in roles.items() if keyof(p)}
    # face
    face = {}
    if "Eye.L" in P:
        x0, z0, x1, z1 = P["Eye.L"]["box"]
        face.update(ex=round((x0 + x1) / 2 / R, 3), ez=round(((z0 + z1) / 2 - head_z) / R, 3), es=round(clamp((z1 - z0) / (0.25 * R), 0.75, 1.35), 3))
        if P["Eye.L"]["hex"].upper() != "#2B1B1B":
            face["eye"] = P["Eye.L"]["hex"]
    if "Brow.L" in P:
        x0, z0, x1, z1 = P["Brow.L"]["box"]
        face.update(bx=round((x0 + x1) / 2 / R, 3), bz=round(((z0 + z1) / 2 - head_z) / R, 3))
        face["brow"] = P["Brow.L"]["hex"] if P["Brow.L"]["hex"].upper() != "#2B1B1B" else "#3A2A22"
    if "Mouth" in P:
        x0, z0, x1, z1 = P["Mouth"]["box"]
        face.update(mz=round(((z0 + z1) / 2 - head_z) / R, 3), mw=round(clamp((x1 - x0) / (0.43 * R), 0.7, 1.25), 3))
    face["nz"] = round((face.get("ez", 0.03) + face.get("mz", -0.385)) / 2 + 0.02, 3)
    face["blush_color"] = mix(skin, "#EE6A62", 0.42)
    face["lips"] = mix(skin, "#5A1A1A", 0.78)
    face.update(ov.get("face", {}))
    # the drawn costume
    parts = []
    rules = list(ov.get("parts", [])) + GLOBAL
    for pn, p in P.items():
        base = pn.split(".")[0]
        if base in STANDARD or p.get("side") == "back":
            continue
        bone = p["bone"]
        if bone.split(".")[0] in ("foot", "hand", "palm", "root", "body"):
            continue
        q = {"name": pn, "on": bone, "pts": p["pts"], "color": p["hex"], "key": p["color"], "layer": p["layer"]}
        if p.get("wire"):
            q["wire"] = True
        if bone.split(".")[0] in ("arm_upper", "arm_lower", "leg_upper", "leg_lower"):
            q["bone2d"] = [[B[bone][0], B[bone][1]], [B[bone][2], B[bone][3]]]
        drop = False
        for pat, r in rules:
            if fnmatch.fnmatchcase(pn, pat) or fnmatch.fnmatchcase(base, pat):
                if r.get("drop"):
                    drop = True
                else:
                    q.update(r)
                break
        if drop:
            continue
        if base in ("Cape", "Cloak") and ov.get("cape_lining"):
            q["lining"] = ov["cape_lining"]
        parts.append(q)
    parts += ov.get("add", [])
    e = reg.get(name, {})
    sheet = {"label": d.get("label", name), "group": d.get("group", ""), "looks": e.get("looks", ""), "era": e.get("era", []),
             "stand_in": e.get("stand_in", []), "props": e.get("props", []), "from": "pack 0.4 (converted)", "order": d.get("order", 0),
             "body": body, "colors": colors, "keys": keys, "face": face, "parts": parts}
    if ov.get("trim"):
        sheet["trim"] = ov["trim"]
    if ov.get("hair"):
        sheet["hair"] = ov["hair"]
    if name in GENERATED:
        import apply_generated
        hair, beard = apply_generated.entries(name, sheet, GENERATED[name])
        if hair:
            sheet["hair"] = hair
        if beard:
            sheet["beard"] = beard
    if ov.get("looks"):
        sheet["looks"] = ov["looks"]
    return sheet


def main():
    a = sys.argv[1:]
    only = None
    if "--only" in a:
        i = a.index("--only")
        only = set(a[i + 1].split(","))
        del a[i:i + 2]
    dump = json.loads(Path(a[0]).read_text(encoding="utf-8"))
    reg = json.loads(Path(a[1]).read_text(encoding="utf-8"))["characters"]
    out = {}
    for name, d in sorted(dump.items(), key=lambda kv: kv[1].get("order", 0)):
        if name in SPECIAL or (only and name not in only):
            continue
        out[name] = convert(name, d, reg)
    doc = {"_comment": "3D character sheets. One entry per character: body proportions, colours, face, and its costume as flat front outlines "
                       "that stagekit/fig3d.py makes 3D. See docs/CHARACTERS_3D.md.",
           "left_out": sorted(SPECIAL), "characters": out}
    Path(a[2]).write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} sheets -> {a[2]} ({Path(a[2]).stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
