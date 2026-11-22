"""stagekit.assets - the reusable asset library and the sourcing order for models.

    1. library/assets/           assets.find("barrel")  ->  assets.use("prop_barrel_oak", at=...)
    2. BlenderKit (full plan)    tools/clip.py bk-search / bk-fetch, then assets.adopt(blend, ..., era=[...]) sizes and files it
    3. build it                  stagekit.build pieces or your own bpy code, then assets.save(...) so the next Short reuses it

(Surfaces - stone, wood, ground - come from ambientCG through stagekit.mat, not from here.)

Every asset that enters a shot ends up in the library with its source, licence and the periods it belongs to (`era`),
so the library grows with each Short and a medieval set never borrows a plastic chair by accident.
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

from . import core

LIB = Path(os.environ.get("SHORTS_LIBRARY") or os.environ.get("CLAY_LIBRARY") or core.PROJECT / "library" / "assets")
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
    try:                                                   # a prop from the wrong century is the fastest way to break a world
        shot = core.current()
        want = (shot.world or {}).get("era")
        have = a.get("era") or ["any"]
        if want and "any" not in have and want not in have:
            shot.notes.append(f"WORLD: asset '{asset_id}' is tagged {have} but this story is set in '{want}'. Replace it or re-tag it if the tag is wrong.")
    except RuntimeError:
        pass
    return root


def _family(root):
    return [root, *root.children_recursive]


def measure(root) -> tuple[float, float, float]:
    lo, hi = core.world_bbox([o for o in _family(root) if o.type == "MESH"])
    return tuple(round(v, 3) for v in (hi - lo))


def save(root, asset_id: str, name: str, kind: str = "prop", tags=(), source: str = "built", source_id: str = "", author: str = "",
         license: str = "project", notes: str = "", preview: str | None = None, era=("any",)) -> dict:
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
             "collection": asset_id, "size_m": list(size), "era": list(era), "source": source, "source_id": source_id, "author": author, "license": license,
             "notes": notes, "preview": preview or "", "added": datetime.date.today().isoformat()}
    idx = _load()
    idx["assets"] = [a for a in idx["assets"] if a["id"] != asset_id] + [entry]
    _store(idx)
    return entry


# ----------------------------------------------------------------------------- outside assets -> this world
def tone(root, saturation: float = 0.9, value: float = 1.0, tint: str | None = None, keep: tuple = ()):
    """Pull an imported asset toward the story palette without flattening it: scale saturation and brightness of every
    base colour, and optionally multiply by a tint. keep: material-name substrings to leave alone (glass, flames)."""
    done = set()
    for o in _family(root):
        if o.type != "MESH":
            continue
        for slot in o.material_slots:
            m = slot.material
            if m is None or m.name in done or not m.use_nodes or any(k.lower() in m.name.lower() for k in keep):
                continue
            done.add(m.name)
            bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                continue
            inp = bsdf.inputs["Base Color"]
            hs = m.node_tree.nodes.new("ShaderNodeHueSaturation")
            hs.inputs["Saturation"].default_value = saturation
            hs.inputs["Value"].default_value = value
            if inp.is_linked:
                m.node_tree.links.new(inp.links[0].from_socket, hs.inputs["Color"])
            else:
                hs.inputs["Color"].default_value = inp.default_value
            src = hs.outputs["Color"]
            if tint:
                mx = m.node_tree.nodes.new("ShaderNodeMix")
                mx.data_type = "RGBA"
                mx.blend_type = "MULTIPLY"
                mx.inputs["Factor"].default_value = 1.0
                mx.inputs["B"].default_value = core.hex_rgba(tint)
                m.node_tree.links.new(src, mx.inputs["A"])
                src = mx.outputs["Result"]
            m.node_tree.links.new(src, inp)
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
          era=("any",), saturation: float | None = None, tint: str | None = None, keep: tuple = (), source: str = "blenderkit", source_id: str = "",
          author: str = "", license: str = "royalty-free (BlenderKit)", notes: str = "") -> dict:
    """One call for step 2: import a downloaded .blend, size it to real scale, optionally tone it, and file it in the
    library with the periods it belongs to. era: names from config/cast.json > eras, or ("any",)."""
    root = import_blend(blend_path, asset_id)
    fit(root, height, longest)
    if saturation is not None or tint:
        tone(root, 1.0 if saturation is None else saturation, 1.0, tint, keep)
    return save(root, asset_id, name, kind, tags, source, source_id, author, license, notes, era=era)


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
