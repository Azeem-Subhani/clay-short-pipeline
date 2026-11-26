"""Print what is inside a .blend without changing it (never saves).

    blender -b <file.blend> --python tools/chars_aj/inspect/inspect_blend.py [-- --json <out.json>]

Prints one line per object (type, parent / bone parent, vertex and face counts, materials, modifiers, armature
bones count and bone-name family) and a summary of armatures, images and custom properties. With --json the same data
is written to a file so other scripts can read it. Read-only: opens the file, prints, quits.
"""
import json
import sys

import bpy


def bone_family(arm):
    names = [b.name for b in arm.data.bones]
    if any(n.startswith("mixamorig:") for n in names):
        return "mixamo (mixamorig:)"
    if any(n.startswith("DEF-") or n.startswith("ORG-") or n.startswith("MCH-") for n in names):
        return "rigify (DEF-/ORG-/MCH-)"
    if any(n.endswith("_ref.x") or n.endswith(".x") for n in names) and any("c_" in n for n in names):
        return "auto-rig pro (c_*.x)"
    if any(n.lower().startswith("bip") for n in names):
        return "biped (Bip*)"
    return "other (first: " + ", ".join(names[:4]) + ")"


def tex_res(obj_list):
    best = 0
    seen = set()
    for o in obj_list:
        for s in o.material_slots:
            m = s.material
            if not m or not m.use_nodes:
                continue
            for n in m.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image and n.image.name not in seen:
                    seen.add(n.image.name)
                    best = max(best, max(n.image.size[0], n.image.size[1]))
    return best


def main():
    out = None
    if "--" in sys.argv:
        a = sys.argv[sys.argv.index("--") + 1:]
        if "--json" in a:
            out = a[a.index("--json") + 1]
    data = {"file": bpy.data.filepath, "objects": [], "armatures": [], "images": []}
    for o in bpy.data.objects:
        rec = {"name": o.name, "type": o.type, "parent": o.parent.name if o.parent else None,
               "parent_type": o.parent_type if o.parent else None,
               "parent_bone": o.parent_bone if o.parent_type == "BONE" else None,
               "hidden": bool(o.hide_viewport or o.hide_render),
               "dims": [round(x, 3) for x in o.dimensions],
               "materials": [s.material.name for s in o.material_slots if s.material],
               "modifiers": [f"{m.type}:{m.name}" for m in o.modifiers],
               "props": [k for k in o.keys() if not k.startswith("_")][:8]}
        if o.type == "MESH":
            me = o.data
            rec["verts"] = len(me.vertices)
            rec["faces"] = len(me.polygons)
            rec["vgroups"] = len(o.vertex_groups)
            rec["shape_keys"] = len(me.shape_keys.key_blocks) if me.shape_keys else 0
            rec["uv"] = len(me.uv_layers)
        data["objects"].append(rec)
    for o in bpy.data.objects:
        if o.type == "ARMATURE":
            data["armatures"].append({"name": o.name, "bones": len(o.data.bones), "family": bone_family(o)})
    for im in bpy.data.images:
        data["images"].append({"name": im.name, "size": list(im.size), "packed": bool(im.packed_file)})
    data["max_texture_px"] = tex_res(bpy.data.objects)
    data["collections"] = [c.name for c in bpy.data.collections]

    print("=== INSPECT", data["file"])
    for r in data["objects"]:
        extra = ""
        if r["type"] == "MESH":
            extra = f" v={r['verts']} f={r['faces']} vg={r['vgroups']} sk={r['shape_keys']}"
        print(f"  {r['type']:9s} {r['name']!r}{extra} parent={r['parent']}"
              f"{'/bone ' + r['parent_bone'] if r['parent_bone'] else ''} dims={r['dims']}"
              f" mats={r['materials']} mods={r['modifiers']}{' HIDDEN' if r['hidden'] else ''}")
    for a in data["armatures"]:
        print("  ARMATURE", a)
    print("  images:", len(data["images"]), "max texture px:", data["max_texture_px"])
    print("  collections:", data["collections"])
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        print("  json ->", out)


main()
