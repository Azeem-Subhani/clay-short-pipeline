"""The castle garden: a deep stone-rimmed pond with a wooden sluice gate at its far end, an oak leaning over the water,
the curtain wall and a round tower behind. One place, three times of day (shotplan.json > sets > pond_garden).

The set is built around what the story does here:
  - the QUEEN stands on the east rim (screen right) and looks west over the water
  - the HOPEFULS wait on the south-west bank (screen left) and look east
  - the GATE is in the middle of the far edge, so every wide view from the camera side has it in frame
  - the OAK BRANCH reaches over the west half of the water
  - the RING goes under about a metre from the east rim and lies there on the mud at the end
The camera always stays south of the line between queen and hopefuls, so screen directions never flip.
"""
from stagekit import build, cast, core, lights

POND_AT, POND_SIZE, DEPTH = (0.0, 2.2), (4.4, 6.6), 1.15   # longer than wide: a 9:16 frame has depth to spare, not width
RIM_Z = 0.2                                   # standing height on the rim stones
MARK = {
    "queen": (2.4, 0.6, RIM_Z),               # east rim, facing left
    "soldier": (-2.95, -0.7, 0.0),             # west bank, facing right; on a diagonal so a camera from the south-east
    "rich_man": (-2.8, 0.8, 0.0),             # sees three separate figures stacked up the tall frame
    "gardener": (-2.8, 2.4, 0.0),
    "ring_in": (1.65, 0.6),                   # where the ring meets the water
    "ring_rest": (1.35, 0.7, -DEPTH + 0.05),  # where it lies on the mud
    "fisher": (2.4, 1.5, RIM_Z),              # the rich man's fishing spot on the east rim
    "onlooker_a": (1.75, 6.25, 0.0),          # by the channel, east of the gate: where the losers watch the water leave
    "onlooker_b": (2.75, 5.75, 0.0),
}
WIDE = ((1.71, -7.79, 3.33), (-0.59, 2.72, -0.24), 24)      # the one wide of the pond: every shot that needs it uses this, so changes show
LIGHT = {"day_clear": dict(sun_from=42), "sunset": dict(sun_from=-62, sun_elevation=13), "morning": dict(sun_from=58, sun_elevation=26)}


def build_set(time: str = "day_clear"):
    P = build.pond("pond", at=POND_AT, size=POND_SIZE, depth=DEPTH, sluice="north", channel=6.0, lilies=7, seed=3)
    build.ground("lawn", 90, "grass_lawn", holes=P["holes"], relief=1.4, flat_radius=15)
    build.patch("terrace", build.rounded_rect(0.4, -3.3, 10.5, 3.4, 0.9), "cobblestone")
    build.patch("path", [(-6.6, 11.6), (-4.4, 11.6), (-3.4, 6.8), (-4.6, 4.4), (-6.2, 4.6), (-5.4, 7.2)], "earth_path")
    # the castle behind: it fills the top of the tall frame with stone instead of empty sky
    build.stone_wall("curtain", length=34, height=5.6, at=(0, 12.6, 0), gap=(0.0, 1.5, 0.95))
    build.box("drain_dark", (1.5, 0.5, 0.95), (0, 12.75, 0), "#0E0C0B", bevel=0)
    build.tower("tower", radius=2.6, height=10.5, at=(8.6, 13.0, 0))
    build.tower("tower_far", radius=2.2, height=8.6, at=(-13.5, 13.4, 0), roof="roof_slate")
    build.arch_door("door", at=(-5.5, 12.1, 0))
    build.banner("banner", at=(8.6, 10.34, 8.4), size=(1.0, 2.5))
    build.banner("banner2", at=(3.4, 12.1, 4.9), size=(0.8, 1.9), emblem="sun")
    build.ivy("ivy", at=(-5.5, 12.12, 0), width=7.0, height=5.0, density=420, seed=2)
    build.ivy("ivy2", at=(5.2, 12.12, 0), width=3.0, height=2.6, density=120, seed=5)
    build.torch("torch", at=(-3.9, 12.1, 2.3), lit=False)
    # the oak and its branch over the water
    T = build.tree("oak", at=(-4.0, 3.5), height=6.4, crown=2.7, lean=0.55, branch=(1.0, 0.0, 2.75, 3.3), seed=4)
    build.tree("far_tree", at=(-11.0, 9.5), height=7.5, crown=3.0, lean=-0.3, tint="#8FBF7A", seed=9)
    build.tree("right_tree", at=(9.8, 5.6), height=6.6, crown=2.5, lean=-0.4, seed=11)
    # dressing: edges and background only; the banks where people stand stay clear
    keep_clear = [(MARK[k][0], MARK[k][1], 0.9) for k in ("queen", "soldier", "rich_man", "gardener", "fisher", "onlooker_a", "onlooker_b")] + [(0, 5.6, 1.6), (0.4, -3.3, 5.0)]
    build.grass_tufts("tufts", area=(-9, 9, -2.2, 11.8), count=520, height=0.2, inside=P["outline"], avoid=keep_clear, seed=1)
    build.grass_tufts("tufts_tall", area=(-9, 9, 9.8, 11.9), count=160, height=0.42, tint="#547F38", seed=2)
    build.flowers("wall_flowers", area=(-9, 9, 10.9, 11.9), count=80, seed=3)
    build.flowers("bank_flowers", area=(-6.2, -3.9, -1.6, 5.5), count=34, colors=("#F6F1E4", "#F2C94C"), avoid=keep_clear, seed=4)
    build.flowers("east_flowers", area=(3.9, 6.5, -1.2, 6.0), count=40, colors=("#F6F1E4", "#D9534F", "#B58BD6"), avoid=keep_clear, seed=5)
    build.bush("bush_e", at=(4.9, 5.2), size=1.25, flowers="#F6F1E4", seed=1)
    build.bush("bush_ne", at=(3.3, 8.2), size=1.0, seed=2)
    build.bush("bush_w", at=(-6.4, 0.6), size=1.1, flowers="#F3D9E4", seed=3)
    build.bush("bush_nw", at=(-2.9, 8.6), size=0.9, seed=4)
    build.reeds("reeds_ne", at=(1.85, 4.9, 0), count=16, seed=1)
    build.reeds("reeds_nw", at=(-1.85, 5.0, 0), count=10, seed=2)
    # foreground for the wide views: something low and near at the bottom corners of the tall frame
    build.barrel("barrel", at=(2.15, -4.2), seed=1)
    build.bucket("bucket", at=(1.72, -4.6))
    build.crate("crate", at=(2.5, -3.55), size=0.55, seed=2)
    build.bush("bush_fg", at=(-0.8, -4.55), size=0.85, flowers="#F2C94C", seed=6)
    build.flowers("fg_flowers", area=(-1.7, -0.1, -5.3, -4.1), count=22, colors=("#F6F1E4", "#D9534F"), seed=7)
    for i, (x, y, s) in enumerate(((-2.1, -2.0, 0.34), (1.9, -1.9, 0.26), (-5.3, 3.0, 0.5), (4.4, 2.9, 0.3))):
        build.rock(f"stone{i}", at=(x, y), size=s, surface="fieldstone", seed=i)
    R = lights.rig(time, **LIGHT.get(time, {}))
    return {"pond": P, "tree": T, "rig": R, "mark": MARK, "time": time,
            "water_z": P["surface_z"], "mud_z": -DEPTH + 0.02, "gate": P["gate"], "branch": T["branch"]}
