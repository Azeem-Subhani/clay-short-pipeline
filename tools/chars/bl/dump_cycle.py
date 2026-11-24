import bpy, sys
a = sys.argv[sys.argv.index("--") + 1:]
name, cyc = a[0], a[1]
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE" and f"{cyc}_action" in o.keys() and (a[3] if len(a) > 3 else "") in o.name)
act = rig.get(f"{cyc}_ref") or bpy.data.actions[rig[f"{cyc}_action"]]
n = rig[f"{cyc}_cycle_frames"]
print("CYCLE", act.name, "frames", n, "stride", rig[f"{cyc}_stride"], "range", tuple(act.frame_range))
fcs = []
for layer in act.layers:
    for strip in layer.strips:
        for bag in strip.channelbags:
            fcs.extend(bag.fcurves)
for fc in fcs:
    if "leg" in fc.data_path or "foot" in fc.data_path:
        ks = [(round(k.co.x, 1), round(k.co.y, 3)) for k in fc.keyframe_points]
        print("FC", fc.data_path, fc.array_index, "ext", fc.extrapolation, "mods", len(fc.modifiers), "e0", round(fc.evaluate(0), 3), "en", round(fc.evaluate(n), 3), ks[:4], "...", ks[-3:])
for fc in fcs:
    if ("leg" in fc.data_path or "foot" in fc.data_path) and len(a) > 2:
        ys = [k.co.y for k in fc.keyframe_points]
        j = [(i, round(ys[i] - ys[i - 1], 2)) for i in range(1, len(ys)) if abs(ys[i] - ys[i - 1]) > 0.5]
        print("JUMPS", rig.name, fc.data_path, j)
