"""aj_wardrobe - how an Aj character is put together from the project's wardrobe, and changed per shot.

A cast entry (config/cast.json, family "aj") is
    {body: "Male_Teen", face: "Teen Classic", hair: {style, color}, facial_hair: {style, color} | null,
     outfit: "jeans_shirt", addons: [{item, color?}], palette: {primary: "#hex", secondary: "#hex"}, skin: "#hex" | "tan",
     era: [...], looks, height_m, status, approved}
and load() builds it: the outfit's fit file (library/wardrobe/fits/<body>/<outfit>.blend: this body's armature, the body mesh
with its hide-under-clothes mask, the garments skinned to the armature) is APPENDED, the face preset is set, the hair and
beard are built from library/characters/aj/hair and bone-parented to the Head (ajkit.hairkit), add-ons are worn, the
palette and the skin tone are applied on this actor's own copies of the materials. A body may only wear an outfit or
add-on whose fit is `pass` and review `accept` (rigid add-ons: review `none` is fine) in library/wardrobe/index.json.

Per shot, from the plan's cast[].costume {recolor, hide, wear}, the actor calls:
    recolor(**slots)   palette slots (primary, secondary, ... as the outfit lists them), hair, facial_hair, skin, or a
                       piece's own name ('polo'); a '#rrggbb' each. A textured garment keeps its texture detail and takes the
                       new average colour (the texture is multiplied by new / old average colour); a plain one is set.
    hide(*patterns)    hair, facial_hair, <outfit>.<piece> (or just <piece>), addon:<item>; wildcards allowed. Hiding an
                       outfit piece is refused (ValueError) unless another worn piece covers its slot: no accidental bare bodies.
    wear(item, **o)    an add-on from library/wardrobe/addons/<item>.blend (apron, cloak, crown, hat, belt, glasses, bag...);
                       color= tints it. The registry entry (index.json > addons.<item>) says: file, kind 'rigid' (bone-parented
                       to `bone`, default Head; authored for the base body, moved with the body's head matrix when the bone
                       is the Head) or 'skinned' (binds to the actor's rig), covers [slots], palette_slot, and per-body fits.

Old characters (no `outfit`, e.g. bare bodies or the pack's own dressed variants) keep the part-name behaviour.

The look of the cloth (style/style.json > look.cloth) is put on at load, so no garment file is rebuilt: a matte, slightly sheened
response on every cloth material (cloth_response) and a thin Solidify shell on every garment that shows in renders only
(cloth_thickness). Colour, recolouring and palette tints are not touched by either.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re

import bpy
from mathutils import Vector

from . import aj_rig, core

SKIN_TONES = {"porcelain": "#F6D9C5", "light": "#EBC3A0", "fair": "#E3B48E", "tan": "#C58F63", "olive": "#B98A5E",
              "brown": "#8F5D3B", "deep": "#684128", "dark": "#4B2E1D"}
_INDEX = None

# The garment factory (ajkit.templates.fabric) names every material F_<slot>_<kind> and stamps it with custom property
# "fabric_kind". Cloth is what is woven or knitted; leather, fur, rubber and the metals keep the response their scans were built with.
CLOTH_KINDS = {"cotton", "linen", "woven", "velvet", "felt"}
CLOTH = os.environ.get("AJ_CLOTH", "1") != "0"     # switch for A/B tests: AJ_CLOTH=0 (or CLOTH = False) loads characters without the cloth look
THICK_NAME = "aj_cloth_thickness"
FLOOR_NAME = "aj_cloth_floor"
NO_THICKNESS = {"shoes", "addon:tie", "addon:lanyard_badge"}     # shoes are not cloth; a tie and a lanyard are already thin straps


# ----------------------------------------------------------------------------------------------- the registry
def index() -> dict:
    global _INDEX
    if _INDEX is None:
        _INDEX = json.loads((core.PROJECT / "library" / "wardrobe" / "index.json").read_text(encoding="utf-8"))
    return _INDEX


def reload_index():
    global _INDEX
    _INDEX = None
    return index()


def fit_ok(entry_fit: dict | None, rigid: bool = False) -> bool:
    return bool(entry_fit) and entry_fit.get("status") == "pass" and (entry_fit.get("review") == "accept" or (rigid and entry_fit.get("review") == "none"))


def outfit_fit(outfit: str, body_id: str) -> dict:
    o = index()["outfits"].get(outfit)
    if o is None:
        raise KeyError(f"the wardrobe has no outfit '{outfit}' (it has {', '.join(index()['outfits'])})")
    f = (o.get("fits") or {}).get(body_id)
    if not fit_ok(f):
        have = [b for b, x in (o.get("fits") or {}).items() if fit_ok(x)]
        raise ValueError(f"outfit '{outfit}' is not fit-accepted on {body_id} (status {f and f.get('status')}, review {f and f.get('review')}); accepted on: {', '.join(have) or 'no body'}")
    if not f.get("file"):
        raise ValueError(f"outfit '{outfit}' on {body_id} has no file in the registry")
    return f


def addon_entry(item: str, body_id: str) -> tuple[dict, dict]:
    a = (index().get("addons") or {}).get(item)
    if a is None:
        raise KeyError(f"the wardrobe has no add-on '{item}' (it has {', '.join(index().get('addons') or {}) or 'none yet'})")
    f = (a.get("fits") or {}).get(body_id)
    if not fit_ok(f, rigid=(a.get("kind") == "rigid")):
        raise ValueError(f"add-on '{item}' is not fit-accepted on {body_id}")
    return a, f


# ----------------------------------------------------------------------------------------------- images
def _img_key(im):
    k = im.get("aj_key")
    if k is None:
        h = hashlib.md5(bytes(im.packed_file.data)).hexdigest() if im.packed_file else "-"
        stem = re.sub(r"(\.\d{3})+$", "", im.name)
        k = f"{stem}|{im.size[0]}x{im.size[1]}|{h}"
        im["aj_key"] = k
    return k


def share_images(before: set):
    """Images an append brought in that an earlier append already brought (same file name, size and bytes) are replaced
    by the earlier one: four characters in one outfit hold one copy of its textures, not four."""
    have = {}
    for im in bpy.data.images:
        if im.name in before and im.type == "IMAGE":
            have.setdefault(_img_key(im), im)
    merged = 0
    for im in [i for i in bpy.data.images if i.name not in before and i.type == "IMAGE"]:
        twin = have.get(_img_key(im))
        if twin is not None and twin is not im:
            im.user_remap(twin)
            bpy.data.images.remove(im)
            merged += 1
        else:
            have[_img_key(im)] = im
    return merged


def _srgb_to_linear(c):
    import numpy as np
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def image_average(im):
    """Average linear colour of an image, leaving out near-black pixels (atlas padding). Cached on the image."""
    v = im.get("aj_avg")
    if v is not None:
        return tuple(v)
    import numpy as np
    w, h = im.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(buf)
    px = buf.reshape(-1, 4)[::5, :3]
    px = px[px.max(axis=1) > 0.03]
    if len(px) == 0:
        px = np.full((1, 3), 0.5, dtype=np.float32)
    if im.colorspace_settings.name.lower().startswith("srgb"):
        px = _srgb_to_linear(px)
    v = tuple(float(x) for x in px.mean(axis=0))
    im["aj_avg"] = v
    return v


def _source_image(socket, hops: int = 8):
    """The image texture behind a colour link, looking up through plain nodes (mix, mapping, colour ramps)."""
    node = socket.links[0].from_node if socket.is_linked else None
    for _ in range(hops):
        if node is None:
            return None
        if node.type == "TEX_IMAGE":
            return node.image
        nxt = None
        for i in node.inputs:
            if i.is_linked and i.type == "RGBA":
                nxt = i.links[0].from_node
                break
        node = nxt
    return None


# ----------------------------------------------------------------------------------------------- colour
def _principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if mat and mat.use_nodes else None


def tint_material(mat, hexc) -> bool:
    """Give a material the colour `hexc`. Plain base colour: set. Textured: multiply the texture by new / old average colour
    (the texture's folds and wear stay). False when the material has no Principled shader (e.g. an invisible patch)."""
    b = _principled(mat)
    if b is None:
        return False
    target = core.hex_rgba(hexc)
    inp = b.inputs["Base Color"]
    if not inp.is_linked:
        inp.default_value = target
        return True
    nt = mat.node_tree
    node = nt.nodes.get("aj_tint")
    if node is None:
        # colour = new colour x (the texture's brightness / its average brightness), softened and limited: the folds and
        # wear of the texture stay, whatever colour it had (a dark navy polo can become a bright pink one)
        src = inp.links[0].from_socket
        im = _source_image(inp)
        avg = image_average(im) if im is not None else (0.5, 0.5, 0.5)
        mat["aj_avg"] = list(avg)
        lum = max(0.02, 0.2126 * avg[0] + 0.7152 * avg[1] + 0.0722 * avg[2])
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        rel = nt.nodes.new("ShaderNodeMath")
        rel.operation = "MULTIPLY"
        rel.inputs[1].default_value = 1.0 / lum
        soft = nt.nodes.new("ShaderNodeMath")
        soft.operation = "MULTIPLY_ADD"
        soft.inputs[1].default_value = 0.75
        soft.inputs[2].default_value = 0.25
        lim = nt.nodes.new("ShaderNodeClamp")
        lim.inputs[1].default_value = 0.25
        lim.inputs[2].default_value = 1.8
        node = nt.nodes.new("ShaderNodeVectorMath")
        node.name = "aj_tint"
        node.operation = "SCALE"
        nt.links.new(src, bw.inputs[0])
        nt.links.new(bw.outputs[0], rel.inputs[0])
        nt.links.new(rel.outputs[0], soft.inputs[0])
        nt.links.new(soft.outputs[0], lim.inputs[0])
        nt.links.new(lim.outputs[0], node.inputs[3])
        nt.links.new(node.outputs[0], inp)
    node.inputs[0].default_value = target[:3]
    return True


def tint_skin(mat, tone) -> bool:
    """Skin tone: multiply what the skin material shows (the head texture and the mouth) by tone / the texture's average."""
    hexc = SKIN_TONES.get(tone, tone)
    b = _principled(mat)
    if b is None:
        return False
    nt = mat.node_tree
    inp = b.inputs["Base Color"]
    node = nt.nodes.get("aj_skin_tone")
    if node is None:
        src = inp.links[0].from_socket
        im = None
        grp = inp.links[0].from_node
        if grp.type == "GROUP" and grp.node_tree:
            im = next((n.image for n in grp.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and "Head" in n.image.name), None)
        node = nt.nodes.new("ShaderNodeMix")
        node.name = "aj_skin_tone"
        node.data_type = "RGBA"
        node.blend_type = "MULTIPLY"
        node.inputs[0].default_value = 1.0
        nt.links.new(src, node.inputs[6])
        nt.links.new(node.outputs[2], inp)
        mat["aj_avg"] = list(image_average(im)) if im is not None else [0.8, 0.5, 0.4]
    avg = mat["aj_avg"]
    t = core.hex_rgba(hexc)
    node.inputs[7].default_value = (*[max(0.0, min(2.0, t[i] / max(0.02, avg[i]))) for i in range(3)], 1.0)
    return True


# ----------------------------------------------------------------------------------------------- the look of the cloth
def is_cloth(mat, outfit_piece: bool = False) -> bool:
    """True for a material that is cloth. The factory's own materials say their kind (fabric_kind): cotton, linen, woven, velvet and
    felt are cloth, leather, fur, rubber and metals are not. A material with no kind is the pack's own (jeans_shirt, pants_top):
    it is cloth only on a worn outfit piece (outfit_piece=True), if it is a Principled shader and not metal."""
    b = _principled(mat)
    if b is None:
        return False
    kind = mat.get("fabric_kind")
    if kind is not None:
        return kind in CLOTH_KINDS
    return bool(outfit_piece) and b.inputs["Metallic"].default_value < 0.5


def cloth_response(mat) -> bool:
    """Matte cloth with a soft edge: specular, sheen and a roughness floor from style.json look.cloth. The floor sits after the
    roughness texture (a Maximum node), so the scan's variation above the floor stays. Colour is not touched. Idempotent."""
    b = _principled(mat)
    if b is None or mat.get("aj_cloth"):
        return False
    b.inputs["Specular IOR Level"].default_value = float(core.look("cloth.specular", 0.15))
    b.inputs["Sheen Weight"].default_value = float(core.look("cloth.sheen", 0.7))
    b.inputs["Sheen Roughness"].default_value = float(core.look("cloth.sheen_roughness", 0.5))
    floor = float(core.look("cloth.roughness_floor", 0.8))
    r = b.inputs["Roughness"]
    if r.is_linked:
        nt = mat.node_tree
        mx = nt.nodes.new("ShaderNodeMath")
        mx.name = FLOOR_NAME
        mx.operation = "MAXIMUM"
        mx.inputs[1].default_value = floor
        nt.links.new(r.links[0].from_socket, mx.inputs[0])
        nt.links.new(mx.outputs[0], r)
    else:
        r.default_value = max(floor, r.default_value)
    mat["aj_cloth"] = True
    return True


def cloth_thickness(ob) -> bool:
    """A Solidify of look.cloth.thickness_mm after the Armature, pushed outward (offset +1: the fitted surface stays where the fit
    check measured it, the new shell lies outside). It shows in renders only: the viewport evaluation, which the physical sweep,
    the character QA and every other geometry check read, does not include it. Idempotent."""
    mm = float(core.look("cloth.thickness_mm", 2.5))
    if mm <= 0 or ob.modifiers.get(THICK_NAME) is not None:
        return False
    md = ob.modifiers.new(THICK_NAME, "SOLIDIFY")
    md.thickness = mm / 1000.0
    md.offset = 1.0
    md.use_even_offset = False
    md.use_rim = True
    md.show_viewport = False
    md.show_render = True
    return True


def apply_cloth(objs, roles: dict | None = None, outfit_pieces=()) -> dict:
    """Give the garments among `objs` the cloth look. `roles` maps an object to its role name (to leave shoes, a tie and a lanyard
    without thickness); `outfit_pieces` are the worn outfit pieces (their pack-made materials count as cloth)."""
    done = {"materials": 0, "thick": 0}
    if not CLOTH:
        return done
    roles = roles or {}
    for o in objs:
        if o.type != "MESH":
            continue
        piece = o in outfit_pieces
        has_cloth = False
        for s in o.material_slots:
            if s.material is not None and is_cloth(s.material, piece):
                has_cloth = True
                done["materials"] += cloth_response(s.material)
        if has_cloth and any(m.type == "ARMATURE" for m in o.modifiers) and roles.get(o) not in NO_THICKNESS:
            done["thick"] += cloth_thickness(o)
    return done


# ----------------------------------------------------------------------------------------------- loading
def _append_objects(path, coll, keep=None):
    """Append the objects of a .blend (all, or those `keep(name)` accepts) into coll. Never links; the file is only read."""
    before = {im.name for im in bpy.data.images}
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if keep is None or keep(n)]
    obs = [o for o in dst.objects if o is not None]
    for o in obs:
        coll.objects.link(o)
    share_images(before)
    return obs


def measured_marks(body_id: str) -> dict:
    """The measured landmarks of the dressed body (ear, chin, ...) in native metres: library/characters/aj/bodies/<body>.json."""
    m = json.loads((core.PROJECT / "library" / "characters" / "aj" / "bodies" / f"{body_id}.json").read_text(encoding="utf-8"))
    return m["landmarks"].get("dressed") or m["landmarks"]["bare"]


def _own_materials(ob):
    for slot in ob.material_slots:
        if slot.material is not None and slot.material.users > 1:
            slot.material = slot.material.copy()


def load(actor, ent: dict) -> list:
    """Append and dress the character `ent` for `actor`. Returns the objects (armature, body, garments, hair, add-ons);
    actor._wd holds what was built; actor._roles maps each object to its role name (body, polo, hair, ...)."""
    from ajkit import faces, hairkit
    cid, coll = actor.id, actor.coll
    body_id, outfit = ent["body"], ent["outfit"]
    fit = outfit_fit(outfit, body_id)
    pieces = index()["outfits"][outfit]["pieces"]
    obs = _append_objects(core.PROJECT / fit["file"], coll)
    arm = next(o for o in obs if o.type == "ARMATURE")
    body = next(o for o in obs if o.name.startswith("Aj_Base_Body"))
    roles = {body: "body"}
    wd = {"outfit": outfit, "body_id": body_id, "pieces": {}, "addons": {}, "hair": None, "facial_hair": None, "palette": {},
          "face": ent.get("face"), "skin": ent.get("skin"), "hidden": set(), "pending": [], "arm0": arm.matrix_basis.copy()}
    for o in obs:
        base = re.sub(r"\.\d{3}$", "", o.name)
        if base in pieces:
            role = base[2:].lower() if base.startswith("D_") else base.lower()
            roles[o] = role
            wd["pieces"][role] = {"kind": "outfit", "outfit": outfit, "slot": pieces[base]["slot"], "palette_slot": pieces[base]["palette_slot"], "obj": o}
            if o.parent is None:
                bpy.context.view_layer.update()
                o.parent = arm
                o.matrix_parent_inverse = arm.matrix_world.inverted()
            _own_materials(o)
    for o in obs:                                     # anything else the file carried is not worn
        if o not in roles and o is not arm:
            bpy.data.objects.remove(o, do_unlink=True)
    obs = [o for o in obs if o in roles or o is arm]
    for o in obs:
        if o is not arm:
            o.name = f"{cid}.{roles[o]}"
    arm.name = arm.data.name = f"{cid}.rig"
    if ent.get("face"):
        if ent["face"] not in faces.PRESETS:
            raise ValueError(f"unknown face preset '{ent['face']}' (use one of {', '.join(faces.PRESETS)})")
        faces.apply_preset(ent["face"], body)
    actor._wd = wd
    actor._roles = roles
    # hair and beard
    hc = (ent.get("hair") or {}).get("color", "#3a2a1c")
    for kind, spec, dflt in (("hair", ent.get("hair"), hc), ("facial_hair", ent.get("facial_hair"), hc)):
        if not spec:
            continue
        ob = hairkit.build(spec["style"], coll, f"{cid}.{kind}", decimate=float(spec.get("decimate", 0.35)))
        mat = hairkit.material(f"{cid}.{kind}", spec.get("color", dflt))
        hb = _principled(mat)                                 # a little more matte than the hair kit's glossy helmet (close-ups only)
        if CLOTH and hb is not None:
            hb.inputs["Roughness"].default_value = float(core.look("hair.roughness", 0.45))
            hb.inputs["Specular IOR Level"].default_value = float(core.look("hair.specular", 0.5))
        ob.data.materials.append(mat)
        wd["pending"].append(kind)                        # skinned to the body once the figure stands in its rest pose (finish)
        roles[ob] = kind
        obs.append(ob)
        wd[kind] = {"style": spec["style"], "color": spec.get("color", dflt), "obj": ob, "mat": mat}
    # add-ons
    for ad in ent.get("addons") or []:
        ad = dict(ad)
        obs += _wear(actor, arm, body, coll, ad.pop("item"), **ad)
    for slot, hexc in (ent.get("palette") or {}).items():
        _recolor_one(actor, slot, hexc)
    if ent.get("skin"):
        _recolor_one(actor, "skin", ent["skin"], body=body)
    wd["cloth"] = apply_cloth([o for o in obs if o is not body and o.type == "MESH" and roles.get(o) not in ("hair", "facial_hair")], roles,
                              outfit_pieces={p["obj"] for p in wd["pieces"].values()})
    return obs


def finish(actor):
    """The end of the actor's build: skin the hair and beard to the body in the pose it stands in (hairkit.attach). Lifts hair that
    would sit in the skin of the neck and shoulders and gives low locks the weights of the skin under them."""
    wd = getattr(actor, "_wd", None)
    if not wd or not wd["pending"]:
        return
    from ajkit import hairkit
    marks = measured_marks(wd["body_id"])
    ear = marks.get("ear", {}).get("at", (0.17, -0.04, 1.59))
    chin = marks.get("chin", {}).get("at")
    bpy.context.view_layer.update()
    T = actor.rig.matrix_world @ wd["arm0"].inverted()             # native frame -> the world as the figure stands now
    for kind in wd["pending"]:
        h = wd[kind]
        h["fit"] = hairkit.attach(h["obj"], actor.rig, actor.mesh, [Vector((s * ear[0], ear[1], ear[2])) for s in (1, -1)],
                                  below_z=(chin[2] - 0.01) if chin else None, T=T)
    wd["pending"] = []


# ----------------------------------------------------------------------------------------------- add-ons
def _wear(actor, arm, body, coll, item: str, **opts) -> list:
    wd = actor._wd
    if item in wd["addons"]:
        return []
    a, fit = addon_entry(item, wd["body_id"])
    path = core.PROJECT / (fit.get("file") or a["file"])
    own_space = bool(fit.get("file"))
    obs = [o for o in _append_objects(path, coll) if o.type != "ARMATURE"]
    bone = a.get("bone", "Head")
    skinned = a.get("kind") == "skinned"
    made = []
    from ajkit import hairkit
    # The add-on's geometry is in the native frame (the pack's metres, the rig at its own rest matrix arm0). The actor may already
    # stand elsewhere, scaled and turned (actor.wear after placing; a plan's costume.wear): T takes the native frame to where
    # the figure stands now. T is the identity while the figure is still being loaded.
    # A rigid piece is bone-parented keeping where it stands, so it must stand where the bone's REST pose says (the figure may
    # already have its arms down or a clip running when it is worn): the rig is put in REST for the parenting and back after.
    pose0 = arm.data.pose_position
    if not skinned:
        arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    T = arm.matrix_world @ wd["arm0"].inverted()
    for o in obs:
        base = re.sub(r"\.\d{3}$", "", o.name)
        o.name = f"{actor.id}.addon.{item}.{base}"
        if o.type != "MESH":
            made.append(o)
            continue
        _own_materials(o)
        if skinned:
            md = next((m for m in o.modifiers if m.type == "ARMATURE"), None) or o.modifiers.new("Armature", "ARMATURE")
            md.object = arm
            o.parent = arm
            o.matrix_parent_inverse = wd["arm0"].inverted()          # what the outfit pieces carry (arm.matrix_world is not valid yet here)
        else:
            o.parent = None
            native = hairkit.head_matrix(arm) @ o.matrix_world if bone == "Head" and not own_space else o.matrix_world.copy()
            o.matrix_world = T @ native
            hairkit.bone_parent(o, arm, bone)
        made.append(o)
    arm.data.pose_position = pose0
    bpy.context.view_layer.update()
    apply_cloth(made, {o: f"addon:{item}" for o in made})
    wd["addons"][item] = {"kind": "addon", "item": item, "covers": list(a.get("covers", [])), "palette_slot": a.get("palette_slot", "accent"),
                          "objs": made}
    for o in made:
        actor._roles[o] = f"addon:{item}"
    if opts.get("color"):
        wd["palette"][wd["addons"][item]["palette_slot"]] = opts["color"]
        for o in made:
            for s in o.material_slots:
                tint_material(s.material, opts["color"])
    return made


def wear(actor, item: str, **opts):
    """actor.wear(): put an add-on on the actor."""
    if getattr(actor, "_wd", None) is None:
        raise NotImplementedError(f"{actor.id}: {actor.base} is not a wardrobe character; add-ons need an `outfit` in config/cast.json")
    made = _wear(actor, actor.rig, actor.mesh, actor.coll, item, **opts)
    for o in made:
        actor.parts[f"addon:{item}"] = o
    return actor


# ----------------------------------------------------------------------------------------------- per shot: recolor, hide
def _objs_for_slot(actor, slot):
    wd = actor._wd
    out = [p["obj"] for p in wd["pieces"].values() if p["palette_slot"] == slot or p["obj"].name.endswith("." + slot)]
    for ad in wd["addons"].values():
        if ad["palette_slot"] == slot:
            out += [o for o in ad["objs"] if o.type == "MESH"]
    return out


def _recolor_one(actor, slot: str, hexc: str, body=None):
    wd = actor._wd
    if slot == "skin":
        tint_skin(actor._skin_mat if getattr(actor, "_skin_mat", None) else (body or actor.mesh).material_slots[0].material, hexc)
        wd["skin"] = hexc
        return True
    if slot in ("hair", "facial_hair"):
        h = wd.get(slot)
        if not h:
            return False
        from ajkit import hairkit
        hairkit.set_color(h["mat"], hexc)
        h["color"] = hexc
        return True
    if slot in wd["pieces"]:                          # a piece by its own name
        objs = [wd["pieces"][slot]["obj"]]
    else:
        objs = _objs_for_slot(actor, slot)
    if not objs:
        return False
    for o in objs:
        for s in o.material_slots:
            tint_material(s.material, hexc)
    wd["palette"][slot] = hexc
    return True


def palette_slots(actor) -> list[str]:
    wd = actor._wd
    s = {p["palette_slot"] for p in wd["pieces"].values()} | {a["palette_slot"] for a in wd["addons"].values()} | set(wd["pieces"])
    return sorted(s | {"hair", "facial_hair", "skin"})


def recolor(actor, **colors):
    for slot, hexc in colors.items():
        if getattr(actor, "_wd", None) is None:
            _recolor_legacy(actor, slot, hexc)
        elif not _recolor_one(actor, slot, hexc):
            actor.shot.notes.append(f"{actor.id}: recolor {slot}: {actor.base} has no such palette slot (it has {', '.join(palette_slots(actor))})")
    return actor


def _labels(actor, role: str) -> list[str]:
    wd = actor._wd
    if role in wd["pieces"]:
        return [role, f"{wd['outfit']}.{role}"]
    if role.startswith("addon:"):
        return [role, role[6:]]
    return [role]


def hide(actor, *patterns):
    if getattr(actor, "_wd", None) is None:
        return _hide_legacy(actor, *patterns)
    wd = actor._wd
    hit, targets = False, []
    for role, ob in actor.parts.items():
        if role == "body":
            continue
        if any(fnmatch.fnmatchcase(lb, p) for p in patterns for lb in _labels(actor, role)):
            targets.append(role)
            hit = True
    if not hit:
        actor.shot.notes.append(f"{actor.id}: hide{patterns} matched no part of {actor.base} (parts: {', '.join(sorted(r for r in actor.parts if r != 'body'))})")
        return actor
    for role in targets:
        if role in wd["pieces"]:                       # an outfit piece: another worn piece must cover the slot
            slot = wd["pieces"][role]["slot"]
            covered = any(r != role and r not in wd["hidden"] and p["slot"] == slot for r, p in wd["pieces"].items()) or \
                any(slot in a["covers"] and f"addon:{k}" not in wd["hidden"] for k, a in wd["addons"].items())
            if not covered:
                raise ValueError(f"{actor.id}: hide '{role}' would leave the body bare at the '{slot}' slot: no other worn piece covers it. "
                                 f"Wear something that covers {slot} first, or leave it on.")
    for role in targets:
        objs = [wd["pieces"][role]["obj"]] if role in wd["pieces"] else \
            ([wd[role]["obj"]] if role in ("hair", "facial_hair") and wd.get(role) else
             (wd["addons"][role[6:]]["objs"] if role.startswith("addon:") else [actor.parts[role]]))
        for o in objs:
            o.hide_render = o.hide_viewport = True
        wd["hidden"].add(role)
    return actor


# ----------------------------------------------------------------------------------------------- old characters
def _recolor_legacy(actor, role, hexc):
    ob = actor.parts.get(role)
    if ob is None:
        actor.shot.notes.append(f"{actor.id}: recolor {role}: {actor.base} has no part '{role}' (it has {', '.join(sorted(actor.parts))})")
        return
    for slot in ob.material_slots:
        tint_material(slot.material, hexc)


def _hide_legacy(actor, *patterns):
    hit = False
    for role, ob in actor.parts.items():
        if role == "body":
            continue
        if any(fnmatch.fnmatchcase(role, p) or fnmatch.fnmatchcase(ob.name, p) for p in patterns):
            ob.hide_render = ob.hide_viewport = True
            hit = True
    if not hit:
        actor.shot.notes.append(f"{actor.id}: hide{patterns} matched no part of {actor.base} (parts: {', '.join(sorted(actor.parts))})")
    return actor


def describe(actor) -> dict:
    """What the actor wears, for labels and QA."""
    wd = getattr(actor, "_wd", None)
    if wd is None:
        return {"outfit": None, "addons": [], "hair": None, "facial_hair": None}
    return {"outfit": wd["outfit"], "addons": sorted(wd["addons"]), "hair": wd["hair"] and f"{wd['hair']['style']} {wd['hair']['color']}",
            "facial_hair": wd["facial_hair"] and f"{wd['facial_hair']['style']} {wd['facial_hair']['color']}", "face": wd["face"],
            "palette": dict(wd["palette"]), "skin": wd["skin"], "body": wd["body_id"]}
