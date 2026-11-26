"""A generic set file for trying a dressing theme in a plain shell (not a worked example: see examples/sets/ for those).

    SK_THEME=tavern blender -b --factory-startup --python tools/blender/set_preview.py -- --set tools/tests/sets/set_theme_probe.py --out <dir>

The theme comes from the SK_THEME environment variable. Room themes get an enclosed room sized for the place with two windows
and a door; exterior themes get a flat stage. Used by tools/tests/sets/run_themes.py.
"""
import os

from stagekit import arch, build, dress, lights

THEME = os.environ.get("SK_THEME", "tavern")
ROOMS = {
    # theme: (size, floor, walls, ceiling, ceiling_kind, mood, wide camera (pos, aim, lens))
    "great_hall": ((11.0, 18.0, 7.0), "flagstone", "castle_stone", "dark_timber", "beams", "interior_day", ((0.0, -8.4, 1.8), (0.0, 5.0, 2.6), 17.0)),
    "castle_kitchen": ((9.0, 8.0, 4.4), "flagstone", "castle_stone", "dark_timber", "beams", "interior_warm", ((-3.0, -3.6, 1.8), (1.0, 3.0, 1.5), 16.0)),
    "tavern": ((9.0, 8.0, 3.4), "wood_floor", "plaster_warm", "dark_timber", "beams", "interior_warm", ((-3.2, -3.6, 1.7), (1.0, 3.0, 1.3), 16.0)),
    "peasant_cottage": ((6.0, 5.0, 2.6), "wood_floor", "plaster_white", "dark_timber", "beams", "interior_warm", ((-2.4, -2.2, 1.6), (0.5, 2.0, 1.1), 16.0)),
    "office_private": ((6.5, 5.5, 2.8), "carpet_grey", "painted_wall", "ceiling_tile", "flat", "office_day", ((-2.6, -2.4, 1.7), (0.5, 2.0, 1.1), 16.0)),
    "home_living_room": ((6.5, 5.2, 2.6), "parquet", "wallpaper", "plaster_clean", "flat", "interior_day", ((-2.6, -2.2, 1.7), (0.5, 2.0, 1.1), 16.0)),
    "home_kitchen": ((5.0, 4.4, 2.6), "floor_tile", "painted_wall", "plaster_clean", "flat", "interior_day", ((-2.0, -1.8, 1.7), (0.5, 1.6, 1.1), 15.0)),
    "shop_interior": ((7.5, 6.5, 3.2), "wood_floor", "plaster_warm", "dark_timber", "beams", "interior_warm", ((-2.8, -2.8, 1.7), (0.8, 2.4, 1.3), 16.0)),
}
EXT = {
    "market_street": ((-14, -5.5), (14, 5.5), "market", ((-12.0, -2.2, 2.2), (4.0, 3.0, 1.6), 20.0)),
    "village_square": ((-10, -8), (10, 6), "village", ((-6.0, -13.0, 2.4), (0.0, 3.0, 1.6), 20.0)),
    "army_camp": ((-14, -6), (14, 10), "camp", ((-8.0, -12.0, 2.6), (1.0, 5.0, 1.4), 20.0)),
    "battlefield": ((-16, -6), (16, 12), "battle", ((-6.0, -12.0, 2.4), (1.0, 6.0, 1.2), 20.0)),
    "city_street": ((-14, -6.5), (14, 6.5), "city", ((-13.0, -2.5, 2.3), (4.0, 3.0, 1.8), 20.0)),
}
MARK = {}
WIDE = (ROOMS[THEME][-1] if THEME in ROOMS else EXT[THEME][-1])
LIGHT = {ROOMS[THEME][-2] if THEME in ROOMS else "day_clear": {}}


def build_set(time=None):
    if THEME in ROOMS:
        size, floor, walls, ceil, ck, mood, _ = ROOMS[THEME]
        w, d, h = size
        ops = [dict(wall="S", kind="door", type="plank", w=1.1, h=2.1, at=w * 0.3, id="door", open=25),
               dict(wall="N", kind="window", type="sash", w=1.2, h=1.4, sill=1.0, at=-w * 0.28, id="w1"),
               dict(wall="N", kind="window", type="sash", w=1.2, h=1.4, sill=1.0, at=w * 0.3, id="w2"),
               dict(wall="E", kind="window", type="sash", w=1.2, h=1.4, sill=1.0, at=-d * 0.25, id="w3")]
        if h >= 6:
            ops = [dict(wall="S", kind="door", type="double", w=2.6, h=4.0, arched=True, id="gate", open=20)] + [dict(wall="E", kind="window", type="arched", w=1.3, h=3.6, sill=1.6, at=y, arched=True, id=f"w{i}") for i, y in enumerate((-4, 0, 4))]
        thick = 0.8 if "stone" in walls else 0.25
        R = arch.room(size, floor=floor, walls=walls, ceiling=ceil, ceiling_kind=ck, openings=ops, name="probe", thick=thick, floor_tint="#9A948A" if floor == "flagstone" else None)
        arch.vista(R, "N", "garden", distance=12)
        arch.vista(R, "E", "hills", distance=14)
        arch.vista(R, "S", "garden", distance=10)
        lights.rig(mood if mood != "interior_warm" else "candlelit", look=False, rim=0.0, ambient=0.08, strength=0.0)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window":
                lights.window_key(hd, power=700 if mood != "interior_warm" else 300, shaft=True, shaft_strength=0.08, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, h - 0.3), (w * 0.8, d * 0.8), power=60, color="#FFE9CC")
        inv = dress.room(R, THEME, marks={}, seed=2)
        return {"room": R, "mark": MARK, "inventory": inv}
    lo, hi, kind, _ = EXT[THEME]
    lights.rig("day_clear", sun_from=40)
    inv = dress.exterior(dict(lo=lo, hi=hi), THEME, marks={}, seed=2)
    return {"mark": MARK, "inventory": inv}
