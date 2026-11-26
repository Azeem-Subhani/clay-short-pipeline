# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/stage.py (Aj pack, 2026-11-26): fitreview and the fitters
# render through it. Unchanged.
"""Render stage helpers for the Aj hybrid costume work (run inside Blender)."""
import bpy, math
from mathutils import Vector

def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

def setup_stage(bg=(0.80, 0.84, 0.90)):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    try:
        sc.eevee.taa_render_samples = 32
    except Exception:
        pass
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.film_transparent = False
    if sc.world is None:
        sc.world = bpy.data.worlds.new("Stage_World")
    w = sc.world
    w.use_nodes = True
    bgn = w.node_tree.nodes.get("Background")
    bgn.inputs[0].default_value = (*bg, 1)
    bgn.inputs[1].default_value = 0.55
    col = bpy.data.collections.get("Stage")
    if col is None:
        col = bpy.data.collections.new("Stage")
        sc.collection.children.link(col)
    def light(name, loc, energy, size, color=(1, 1, 1)):
        ob = bpy.data.objects.get(name)
        if ob is None:
            ld = bpy.data.lights.new(name, "AREA")
            ob = bpy.data.objects.new(name, ld)
            col.objects.link(ob)
        ob.location = loc
        ob.data.energy = energy
        ob.data.size = size
        ob.data.color = color
        look_at(ob, (0, 0, 1.0))
        return ob
    light("Key", (-1.8, -2.6, 2.6), 220, 2.5, (1.0, 0.97, 0.92))
    light("Fill", (2.2, -2.0, 1.6), 80, 3.0, (0.9, 0.95, 1.0))
    light("Rim", (0.6, 2.4, 2.4), 160, 2.0)
    # floor
    fl = bpy.data.objects.get("Stage_Floor")
    if fl is None:
        me = bpy.data.meshes.new("Stage_Floor")
        me.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
        fl = bpy.data.objects.new("Stage_Floor", me)
        col.objects.link(fl)
        m = bpy.data.materials.new("Stage_Floor_MAT")
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.62, 0.64, 0.68, 1)
        m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
        fl.data.materials.append(m)
    cam = bpy.data.objects.get("Stage_Cam")
    if cam is None:
        cam = bpy.data.objects.new("Stage_Cam", bpy.data.cameras.new("Stage_Cam"))
        col.objects.link(cam)
    sc.camera = cam
    return cam

def frame(view="front", target_z=0.98, dist=4.6, lens=50, height=None, res=(1200, 1600)):
    sc = bpy.context.scene
    cam = sc.camera
    cam.data.lens = lens
    ang = {"front": 0, "three_quarter": 35, "side": 90, "back": 180, "three_quarter_r": -35}[view] if isinstance(view, str) else view
    a = math.radians(ang)
    h = target_z + 0.15 if height is None else height
    cam.location = (math.sin(a) * dist, -math.cos(a) * dist, h)
    look_at(cam, (0, 0, target_z))
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100

def hierarchy(root):
    out = [root]
    for c in root.children_recursive:
        out.append(c)
    return out

def world_bbox(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
    for o in objs:
        if o.type not in {"MESH", "CURVE"}:
            continue
        oe = o.evaluated_get(dg)
        for c in oe.bound_box:
            w = oe.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
    return mn, mx

def render_isolated(objs, path, angle=30, elev=15, res=600):
    """Render only `objs` with an orthographic camera fitted to them."""
    sc = bpy.context.scene
    keep = set(o.name for o in objs) | {"Key", "Fill", "Rim"}
    state = {}
    for o in sc.objects:
        state[o.name] = o.hide_render
        o.hide_render = o.name not in keep
    mn, mx = world_bbox(objs)
    ctr = (mn + mx) / 2; size = max((mx - mn).length, 0.01)
    cam = bpy.data.objects.get("Iso_Cam") or bpy.data.objects.new("Iso_Cam", bpy.data.cameras.new("Iso_Cam"))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"; cam.data.ortho_scale = size * 1.05
    a = math.radians(angle); e = math.radians(elev)
    cam.location = ctr + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * size * 3
    look_at(cam, ctr)
    cam.data.clip_end = size * 10
    old_cam = sc.camera; sc.camera = cam
    oldres = (sc.render.resolution_x, sc.render.resolution_y)
    sc.render.resolution_x = sc.render.resolution_y = res
    # lights follow
    for n in ("Key", "Fill", "Rim"):
        L = bpy.data.objects.get(n)
    render(path)
    sc.camera = old_cam
    sc.render.resolution_x, sc.render.resolution_y = oldres
    for n, h in state.items():
        if n in sc.objects:
            sc.objects[n].hide_render = h
    return [list(mn), list(mx)]

def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    return path
