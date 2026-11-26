"""The throne room: a royal hall 12 m wide, 20 m long and 8 m to the eaves, with a barrel vault rising 2.2 m above them.

A worked example of the set-file contract with the architecture kit (stagekit.arch / furnish / dress / lights):

    marks first       MARK = where people stand: the throne on its dais at the north end, a petitioner on the carpet, guards
                      in pairs down the nave and either side of the big doors at the south end
    then the place    arch.room: stone walls 0.9 m thick with real openings (tall arched windows between the column bays, big
                      double doors at the south, a plank side door), a timber-ribbed vault; arch.vista for what the windows see
    then the light    a low sun through the east windows (real window light and shadows), practicals: chandeliers, braziers,
                      sconces, torches, candelabra; a rim light for the figure on the carpet
    then the dressing dress.room(R, "throne_room", marks=MARK): dais and throne, long red runner, two rows of fluted columns with
                      pilasters, banners, tapestries, shields, weapon racks, armour, benches, tables with goblets and candles,
                      straw on the floor, dust in the window light

Camera side is -Y. build_set(time) returns {"room", "mark", "inventory", ...}; WIDE is the one wide every shot of this set uses.
Times: "interior_day" (sun through the east windows) and "candlelit" (night: moonlight, the practicals do the work).
"""
from stagekit import arch, core, dress, lights

THEME = "throne_room"                       # the plan's sets[].theme: the build-time agreement check compares it
SIZE = (12.0, 20.0, 8.0)
DAIS_Y = 10.0
MARK = {
    "throne": (0.0, 8.7, 0.45),            # the king, seated on the dais
    "petitioner": (0.0, 1.0, 0.0),         # kneels on the carpet, half way down the nave
    "guard_nl": (-2.1, 4.6, 0.0),          # guards flank the runner in pairs
    "guard_nr": (2.1, 4.6, 0.0),
    "guard_ml": (-2.1, -1.8, 0.0),
    "guard_mr": (2.1, -1.8, 0.0),
    "door_l": (-2.8, -7.4, 0.0),           # either side of the big doors
    "door_r": (2.8, -7.4, 0.0),
}
WIDE = ((0.6, -9.35, 1.9), (-0.3, 6.0, 2.9), 17.0)      # from the doors, down the nave to the dais: columns, banners, vault, windows
LIGHT = {"interior_day": dict(sun_from=90, sun_elevation=32), "candlelit": dict()}


def _openings():
    ys = dress.hall_bays(SIZE)
    mids = [(a + b) / 2 for a, b in zip(ys, ys[1:])]
    ops = [dict(wall="S", kind="door", type="double", w=3.4, h=4.6, arched=True, id="gate", open=28),
           dict(wall="W", kind="door", type="plank", w=1.3, h=2.7, arched=True, at=-7.6, id="side", open=0)]
    for i, y in enumerate(mids):
        for W in ("E", "W"):
            ops.append(dict(wall=W, kind="window", type="arched", w=1.5, h=4.4, sill=1.9, at=y, arched=True, id=f"win_{W}{i}", surround="castle_stone"))
    return ops


def build_set(time: str = "interior_day"):
    R = arch.room(SIZE, at=(0, 0), floor="flagstone", floor_tint="#9A948A", walls="castle_stone", ceiling="plaster_warm", openings=_openings(), name="throne", thick=0.9,
                  ceiling_kind="vault", rise=2.2, vault_axis="Y", cornice="castle_stone", skirting="castle_stone", beams="dark_timber")
    # the layer beyond: hills with a far castle through the east windows, a walled garden to the west, the courtyard past the doors
    arch.vista(R, "E", "hills", distance=20, seed=2)
    arch.vista(R, "W", "garden", distance=16, seed=5)
    arch.vista(R, "S", "garden", distance=14, seed=7)
    night = time == "candlelit"
    # ---- light
    if night:
        lights.rig("candlelit", look=False, rim=0.0, ambient=0.06)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window" and hd["wall"] == "E":
                lights.window_key(hd, color="#9FB4FF", power=420, shaft=True, shaft_strength=0.03, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 6.5), (9, 16), power=420, color="#FFD2A0")           # the bounce of a hall full of candles: lifts the vault and the walls into the readable range
    else:
        lights.rig("interior_day", sun_from=90, sun_elevation=32, look=False, rim=0.0, strength=0.0, ambient=0.1)
        for oid, hd in R.openings.items():
            if hd["kind"] == "window" and hd["wall"] == "E":
                lights.window_key(hd, color="#FFEBCB", power=380, shaft=True, shaft_strength=0.13, shadow=False, name=f"KEY_{oid}")
            elif hd["kind"] == "window":
                lights.window_key(hd, color="#E6EEFF", power=220, shaft=False, shadow=False, name=f"KEY_{oid}")
        lights.ambient_fill((0, 0, 6.5), (9, 16), power=95, color="#FFF2E0")
        lights.window_sun(R, "E", elevation=34, yaw=0, power=9.0, color="#FFE8C4")           # the sun patches on the floor and the west wall
    lights.rim_light(MARK["petitioner"], from_deg=160, distance=5.0, power=900)
    # ---- the dressing
    inv = dress.room(R, "throne_room", marks=MARK, density=1.0, seed=3, keep_clear=0.9)
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
