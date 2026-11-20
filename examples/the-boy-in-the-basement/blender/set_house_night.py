"""Set: the lonely house at night, seen from the tree line. Camera side is -Y; the house stands at y = 14.
The set owns its ONE light rig: every shot that calls build_set() gets identical light."""
from stagekit import build, core, lights

WALL = "#C7B49A"


def build_set(subject=(0.7, 0, 1.4)):
    build.ground("ground", 120, "#232F2B", relief=1.2, seed=4, keep_flat_radius=16)
    build.backdrop("sky", "#24337A", "#0D1640", strength=0.75, radius=55, height=40)
    house = build.house("house", at=(0, 14, 0), wall_color=WALL, roof_color="#4A2E2B", windows=2, lit=("#FFC477",), lit_strength=6.0)
    build.slab("path", (1.1, 7.5), (0, 8.0, 0.012), "#3A3A34", thickness=0.03)
    build.fence("fence_l", 7, 1.0, (-5.0, 7.0, 0), color="#7D776C")
    build.fence("fence_r", 7, 1.0, (5.0, 7.0, 0), color="#7D776C")
    # the tree line the watcher hides in: trunks near him, pines falling away into the dark, more behind the house for a skyline
    build.tree("tree_near_l", "bare", 6.5, (-0.9, 0.5, 0), trunk_color="#2B211C", seed=3)
    build.tree("tree_near_r", "bare", 7.0, (2.3, 1.2, 0), trunk_color="#2B211C", seed=8)
    build.scatter(build.tree, 9, (-14, 14, -3, 6), seed=5, avoid=[(0.7, 0, 3.2), (0, 6, 2.5)], min_gap=2.5, kind="pine", height=6.0, color="#1F3A33", trunk_color="#2B211C")
    build.scatter(build.tree, 10, (-22, 22, 16, 30), seed=9, avoid=[(0, 14, 6)], min_gap=3.0, kind="pine", height=8.0, color="#1A302C", trunk_color="#2B211C")
    build.scatter(build.bush, 8, (-9, 9, 2, 6.5), seed=2, avoid=[(0, 5, 1.6), (0.7, 0, 2.2)], color="#22382F", size=0.9)
    rig = lights.rig("night_moon", subject=subject, key_azimuth=140, key_elevation=42)   # moon behind-right: he is a rim-lit shape
    wins = []
    for i, x in enumerate((-1.9, 1.9)):                      # practicals: what each lit window throws on the ground
        pane = core.bpy.data.objects[f"house_win{i}_pane"]
        lamp = lights.practical(f"window_spill{i}", (x, 11.2, 1.5), "#FFC477", 120, kind="AREA", aim=(x, 7.5, 0), size=1.4, rig_=rig)
        wins.append((pane, lamp))
    return {"house": house, "rig": rig, "windows": wins}


def windows_off(wins, times):
    """Switch the house windows off one after the other (pane glow and its spill together)."""
    for (pane, lamp), t in zip(wins, times):
        build.set_glow(pane, 6.0, max(0.0, t - 0.08))
        build.set_glow(pane, 0.05, t)
        lights.switch(lamp, t, on=False)


def wall_detail(tip):
    """The same house wall seen from 1 m: wire, clips, junction box, and the same moon, raking the wall from screen-right.
    Built around `tip`, the point where the cutter jaws end up, so the tool and the wire really meet."""
    wire_x, wall_y, cut_z = tip.x, tip.y + 0.03, tip.z
    build.wall("house_wall", 5.0, 4.5, (wire_x, wall_y + 0.08, -0.5), color=WALL)
    black = build.clay("#15161A", rough=0.5, bump=0.0)
    build.cyl("wire_upper", 0.006, 2.4, (wire_x, wall_y - 0.02, cut_z + 0.004), material=black, segments=10, bevel=0)
    pivot = core.empty("wire_pivot", (wire_x, wall_y - 0.02, cut_z - 0.62))
    lower = build.cyl("wire_lower", 0.006, 0.626, (0, 0, 0), material=black, segments=10, bevel=0)
    lower.parent = pivot
    build.box("junction_box", (0.16, 0.07, 0.2), (wire_x, wall_y - 0.035, cut_z - 0.8), "#6E6A62", bevel=0.012)
    for i in range(3):
        build.box(f"clip{i}", (0.03, 0.02, 0.014), (wire_x, wall_y - 0.01, cut_z + 0.35 + i * 0.6), "#3A3D44", bevel=0.003)
    cut_pt = (wire_x, wall_y - 0.02, cut_z)
    rig = lights.rig("night_moon", subject=cut_pt, key_azimuth=70, key_elevation=40, fill=1.4, rim=0.4)
    return {"wire_pivot": pivot, "cut_point": cut_pt, "rig": rig}
