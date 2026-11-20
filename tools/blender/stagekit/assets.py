"""stagekit.assets - the reusable asset library and the three-step sourcing rule.

    1. library/assets/           assets.find("lamp")  ->  assets.use("prop_table_lamp", at=...)
    2. BlenderKit (paid plan)    tools/clip.py bk-search / bk-fetch, then assets.adopt(blend, ...) restyles and files it
    3. build it                  stagekit.build pieces or your own bpy code, then assets.save(...) so the next Short reuses it

Every asset that enters a shot ends up in the library with its source and licence, so the library grows with each Short.
An asset is one .blend holding one collection named like the asset id; its origin is the point it rests on.
"""
from __future__ import annotations

import datetime
import json
import math
import os
import re
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

from . import build, core

LIB = Path(os.environ.get("CLAY_LIBRARY", core.PROJECT / "library" / "assets"))
INDEX = LIB / "index.json"
KINDS = ("prop", "set_piece", "set", "character", "creature", "vehicle", "material")


def _load() -> dict:
    if INDEX.exists():
        return json.loads(INDEX.read_text(encoding="utf-8"))
    return {"version": 1, "assets": []}


def _store(idx: dict):
    LIB.mkdir(parents=True, exist_ok=True)
    idx["assets"].sort(key=lambda a: a["id"])
    INDEX.write_text(json.dumps(idx, indent=1), encoding="utf-8")


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 1}


def find(query: str, kind: str | None = None, limit: int = 8) -> list[dict]:
    """Search the project library by words. Returns the best matches first (each has id, name, kind, tags, size_m, notes)."""
    q = _tokens(query)
    scored = []
    for a in _load()["assets"]:
        if kind and a.get("kind") != kind:
            continue
        hay = _tokens(a["id"]) | _tokens(a.get("name", "")) | set(t.lower() for t in a.get("tags", []))
        s = len(q & hay) + 0.25 * sum(1 for t in q for h in hay if t in h and t != h)
        if s > 0:
            scored.append((s, a))
    return [a for _, a in sorted(scored, key=lambda x: -x[0])[:limit]]


def get(asset_id: str) -> dict:
    for a in _load()["assets"]:
        if a["id"] == asset_id:
            return a
    raise KeyError(f"asset {asset_id!r} is not in the library ({INDEX})")


def use(asset_id: str, name: str | None = None, at=(0, 0, 0), rot_z: float = 0.0, scale: float = 1.0, coll: str = "SET"):
    """Bring a library asset into the shot. Returns its root empty (move/animate that)."""
    a = get(asset_id)
    path = LIB / a["file"]
    cname = a.get("collection", asset_id)
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        if cname not in src.collections:
            raise KeyError(f"{path} has no collection {cname!r} (has {list(src.collections)})")
        dst.collections = [cname]
    c = dst.collections[0]
    objs = list(c.all_objects)
    root = core.empty(name or asset_id, coll=coll, size=0.2)    # a fresh handle: the asset keeps its own size and rest offset inside
    for o in objs:
        core.link(o, coll)
        if o.parent is None:
            o.parent = root
    bpy.data.collections.remove(c)
    root.location = at
    root.rotation_euler.z = math.radians(rot_z)
    root.scale = (scale,) * 3
    root["asset_id"] = asset_id
    return root


def _family(root):
    return [root, *root.children_recursive]


def measure(root) -> tuple[float, float, float]:
    lo, hi = core.world_bbox([o for o in _family(root) if o.type == "MESH"])
    return tuple(round(v, 3) for v in (hi - lo))


def save(root, asset_id: str, name: str, kind: str = "prop", tags=(), source: str = "built", source_id: str = "", author: str = "",
         license: str = "project", notes: str = "", preview: str | None = None) -> dict:
    """File an object tree (root + children) into the library as <kind>s/<asset_id>.blend and index it.
    Call it with the asset standing at the world origin, resting on z = 0, facing -Y."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,48}", asset_id):
        raise ValueError("asset_id: lowercase letters, digits and underscores, e.g. prop_wire_cutters")
    fam = _family(root)
    c = bpy.data.collections.new(asset_id)
    for o in fam:
        c.objects.link(o)
    rel = Path(f"{kind}s") / f"{asset_id}.blend"
    path = LIB / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    size = measure(root)
    bpy.data.libraries.write(str(path), {c}, fake_user=True, compress=True)
    for o in fam:
        c.objects.unlink(o)
    bpy.data.collections.remove(c)
    entry = {"id": asset_id, "name": name, "kind": kind, "tags": sorted(set(t.lower() for t in tags)), "file": rel.as_posix(),
             "collection": asset_id, "size_m": list(size), "source": source, "source_id": source_id, "author": author, "license": license,
             "notes": notes, "preview": preview or "", "added": datetime.date.today().isoformat()}
    idx = _load()
    idx["assets"] = [a for a in idx["assets"] if a["id"] != asset_id] + [entry]
    _store(idx)
    return entry


# ----------------------------------------------------------------------------- outside assets -> one clay world
def _mean_colour(mat):
    """Best guess of a material's flat colour: its Principled base colour, or the mean of its base-colour texture."""
    if not mat or not mat.use_nodes:
        return tuple(mat.diffuse_color[:3]) if mat else (0.6, 0.55, 0.5)
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return tuple(mat.diffuse_color[:3])
    inp = bsdf.inputs["Base Color"]
    node = inp.links[0].from_node if inp.is_linked else None
    hops = 0
    while node is not None and node.type != "TEX_IMAGE" and hops < 6:
        nxt = next((i.links[0].from_node for i in node.inputs if i.is_linked and i.type in ("RGBA", "VECTOR", "SHADER")), None)
        node, hops = nxt, hops + 1
    if node is not None and node.type == "TEX_IMAGE" and node.image and node.image.size[0] > 0:
        img = node.image
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        try:
            img.pixels.foreach_get(px)
            px = px.reshape(-1, 4)[:: max(1, (w * h) // 20000)]
            return tuple(float(v) for v in px[:, :3].mean(axis=0))
        except Exception:
            pass
    return tuple(inp.default_value[:3])


def clayify(root, recolor: dict | None = None, keep: tuple = (), bevel: bool = True, saturation: float = 0.9):
    """Restyle any imported asset into the channel's clay world: flat palette colours instead of photo textures,
    clay roughness and bump, bevelled edges. recolor: {"material-name substring": "#hex"} to pull colours to the story
    palette. keep: material-name substrings to leave untouched (glass, emissive screens, eyes)."""
    cl, _, _ = core.pack_modules()
    recolor = recolor or {}
    done = {}
    for o in _family(root):
        if o.type != "MESH":
            continue
        for slot in o.material_slots:
            m = slot.material
            if m is None or any(k.lower() in m.name.lower() for k in keep):
                continue
            if m.name in done:
                slot.material = done[m.name]
                continue
            hexcol = next((v for k, v in recolor.items() if k.lower() in m.name.lower()), None)
            if hexcol is None:
                r, g, b = _mean_colour(m)
                mx = (r + g + b) / 3
                r, g, b = (mx + (c - mx) * saturation for c in (r, g, b))
                srgb = [max(0.0, min(1.0, c)) ** (1 / 2.2) for c in (r, g, b)] if max(r, g, b) <= 1.0 else [0.6, 0.55, 0.5]
                hexcol = "#%02X%02X%02X" % tuple(int(c * 255) for c in srgb)
            done[m.name] = slot.material = build.clay(hexcol, name=f"{root.name}_{m.name}"[:60])
        if bevel and not any(md.type == "BEVEL" for md in o.modifiers) and len(o.data.polygons) < 20000:
            d = sorted(build._dims(o.data))
            if d[1] > 1e-5:
                b = o.modifiers.new("Bevel", "BEVEL")
                b.width = max(0.002, min(0.02, d[1] * 0.02))
                b.segments = 2
                b.limit_method = "ANGLE"
                b.angle_limit = math.radians(40)
    return root


def fit(root, height: float | None = None, longest: float | None = None, rest_on_floor: bool = True):
    """Scale an asset to a real-world size (a door is ~2.05 m, a chair seat 0.45 m, a cup 0.09 m) and stand it on z = 0."""
    sx, sy, sz = measure(root)
    if height:
        k = height / max(sz, 1e-6)
    elif longest:
        k = longest / max(sx, sy, sz, 1e-6)
    else:
        k = 1.0
    root.scale = tuple(s * k for s in root.scale)
    bpy.context.view_layer.update()
    if rest_on_floor:
        lo, hi = core.world_bbox([o for o in _family(root) if o.type == "MESH"])
        root.location.z -= lo.z
        root.location.x -= (lo.x + hi.x) / 2
        root.location.y -= (lo.y + hi.y) / 2
        bpy.context.view_layer.update()
    return root


def import_blend(path, name: str | None = None, coll: str = "SET"):
    """Append everything renderable from a downloaded .blend (a BlenderKit model) under one root empty."""
    path = Path(path)
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = list(src.objects)
    root = core.empty(name or path.stem, coll=coll, size=0.2)
    for o in dst.objects:
        if o is None:
            continue
        if o.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(o)
            continue
        core.link(o, coll)
        if o.parent is None:
            o.parent = root
    return root


def adopt(blend_path, asset_id: str, name: str, kind: str = "prop", tags=(), height: float | None = None, longest: float | None = None,
          recolor: dict | None = None, keep: tuple = (), source: str = "blenderkit", source_id: str = "", author: str = "",
          license: str = "royalty-free (BlenderKit)", notes: str = "") -> dict:
    """One call for step 2: import a downloaded .blend, restyle it to clay, size it, and file it in the library."""
    root = import_blend(blend_path, asset_id)
    fit(root, height, longest)
    clayify(root, recolor, keep)
    return save(root, asset_id, name, kind, tags, source, source_id, author, license, notes)


def blenderkit_downloads(query: str = "", data_dir: str | None = None) -> list[dict]:
    """Assets the BlenderKit add-on has already downloaded on this machine (its global directory), newest first.
    Anything you clicked in the add-on, or fetched with tools/clip.py bk-fetch, shows up here."""
    root = Path(data_dir or os.environ.get("BLENDERKIT_DATA_DIR") or Path.home() / "blenderkit_data")
    q = _tokens(query)
    out = []
    for sub in ("models", "scenes", "materials"):
        d = root / sub
        if not d.is_dir():
            continue
        for folder in d.iterdir():
            blends = sorted(folder.glob("*.blend"), key=lambda p: p.stat().st_size)
            if not blends:
                continue
            if q and not (q & _tokens(folder.name)):
                continue
            out.append({"name": folder.name, "type": sub[:-1], "blend": str(blends[-1]), "mtime": blends[-1].stat().st_mtime})
    return sorted(out, key=lambda a: -a["mtime"])
