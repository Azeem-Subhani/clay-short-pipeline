"""The manager's office: 7 x 5.8 m, 2.8 m to a tiled ceiling, a big desk against the city, bookcases, a sofa corner, a glass door onto the floor.

A worked example of the set-file contract for a modern private room:

    marks first       MARK = the manager behind the desk, a visitor in front of it, an assistant at the door, someone on the sofa
    then the place    arch.room: carpet, painted walls, suspended ceiling; two wide windows in the north wall onto the city, a glass door in
                      the south wall onto the open-plan floor, a side window; arch.vista: the city by day or night
    then the light    day: soft window light and a sun patch, ceiling panels; night: the city glow through the windows, the desk and floor lamps
    then the dressing dress.room(R, "office_private", marks=MARK): executive desk with screen, lamp, globe and framed photos; three bookcases;
                      credenza with trophies and flowers; sofa, coffee table and armchair; plants; whiteboard; pictures; filing cabinet,
                      water cooler, coat stand; a rug; ceiling panels

Camera side is -Y. WIDE is from the south-west corner across the desk to the windows. Times: "office_day", "office_night".
"""
from stagekit import arch, core, dress, lights

SIZE = (7.8, 6.2, 2.8)
MARK = {
    "manager": (0.0, 1.95, 0.0),        # behind the desk
    "visitor": (-1.2, -0.5, 0.0),       # in front of it
    "assistant": (2.6, -2.4, 0.0),      # by the glass door
    "sofa": (-2.55, -0.2, 0.0),         # on the sofa
}
WIDE = ((-3.5, -2.9, 2.0), (0.8, 2.6, 1.0), 12.0)
LIGHT = {"office_day": {}, "office_night": {}}


def build_set(time: str = "office_day"):
    night = time == "office_night"
    ops = [dict(wall="N", kind="window", type="office", w=2.6, h=1.7, sill=0.9, at=-1.7, id="win_N1"),
           dict(wall="N", kind="window", type="office", w=2.6, h=1.7, sill=0.9, at=1.7, id="win_N2"),
           dict(wall="S", kind="door", type="glass", w=1.0, h=2.2, at=2.6, id="glass_door", open=35),
           dict(wall="E", kind="window", type="office", w=1.4, h=1.5, sill=1.0, at=0.2, id="win_E")]
    R = arch.room(SIZE, at=(0, 0), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile", openings=ops, name="office_private", thick=0.25,
                  skirting="brushed_metal", cornice="plaster_clean")
    arch.vista(R, "N", "night_city" if night else "city_day", distance=16, seed=4, night=night)
    arch.vista(R, "E", "rooftops", distance=12, seed=6, night=night)
    arch.vista(R, "S", "street", distance=8, seed=8, night=night)
    arch.vista(R, "W", "rooftops", distance=12, seed=9, night=night)
    mood = "office_night" if night else "office_day"
    lights.rig(mood, look=False, rim=0.0, ambient=0.05 if night else 0.18)
    for oid, hd in R.openings.items():
        if hd["kind"] != "window":
            continue
        lights.window_key(hd, color="#9FB4FF" if night else "#EAF2FF", power=90 if night else 330, shaft=(not night) and hd["wall"] == "N", shaft_strength=0.04, pitch=16, shadow=False, name=f"KEY_{oid}")
    lights.ambient_fill((0, 0, 2.5), (7, 5.6), power=48 if night else 28, color="#FFD8A8" if night else "#EAF0FF")
    if not night:
        lights.window_sun(R, "N", elevation=30, yaw=20, power=6.0, color="#FFF1DC")
    lights.rim_light(MARK["manager"], from_deg=20 if night else 0, distance=3.0, power=240, color="#FFC890" if night else "#CFE0FF")
    inv = dress.room(R, "office_private", marks=MARK, density=2.8, seed=2, keep_clear=0.4)
    lights.limit_shadows()
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
