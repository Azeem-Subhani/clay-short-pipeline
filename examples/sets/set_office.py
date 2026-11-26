"""The open-plan office: 16 x 11 m, 2.8 m to a tiled ceiling, a city outside the windows, a glass-walled meeting room in the corner.

A worked example of the set-file contract for a modern interior built with the architecture kit:

    marks first       MARK = the aisles people walk in, the kitchenette, the meeting-room table and the glass door
    then the place    arch.room: carpet floor, painted walls, a suspended ceiling; four office windows in the north wall and three
                      shop-front style windows in the south wall; a door in the west wall; arch.vista gives each wall its view
                      (north: the city, south: the street, west: rooftops)
                      arch.glass_partition x2 make the meeting room (L-shaped glass wall, one glass door standing open)
    then the light    a soft window key through each north window (real window light), a weaker one from the south, eight
                      ceiling light panels with real lights, desk lamps; no sun, no flat world light
    then the dressing dress.room(R, "office_open_plan", marks=MARK, reserve=[meeting room]): four rows of workstations (desk,
                      chair, monitor and keyboard, phone, mug, papers), filing cabinets, printer, water cooler, bookcases, plants,
                      whiteboard, notice boards, posters, wall clock, coat stand, bins and a kitchenette; then the meeting room

Camera side is -Y. WIDE is from the south-west corner across the floor to the north-east. Times: "office_day" and "office_night".
"""
import math

from stagekit import arch, core, dress, furnish, lights

SIZE = (16.0, 11.0, 2.8)
MEETING = (2.5, 0.5, 8.0, 5.5)             # x0, y0, x1, y1 of the glass meeting room (north-east corner)
MARK = {
    "worker_a": (-5.0, -2.55, 0.0),        # in the aisle behind the first row
    "worker_b": (-1.6, 0.25, 0.0),         # in the middle aisle
    "visitor": (-4.7, -4.45, 0.0),         # by the entrance end
    "kitchen": (6.6, -2.6, 0.0),           # at the kitchenette counter
    "manager": (5.2, 2.2, 0.0),            # in the meeting room, by the table
    "glass_door": (3.4, -0.3, 0.0),        # just outside the meeting room door
}
WIDE = ((-7.5, -5.2, 2.15), (2.2, 2.3, 0.15), 16.0)
LIGHT = {"office_day": {}, "office_night": {}}


def build_set(time: str = "office_day"):
    night = time == "office_night"
    ops = []
    for x in (-5.6, -1.9, 1.9, 5.6):
        ops.append(dict(wall="N", kind="window", type="office", w=3.0, h=1.6, sill=0.9, at=x, id=f"win_N{x:+.0f}"))
    for x in (-5.0, 0.0, 5.0):
        ops.append(dict(wall="S", kind="window", type="shop", w=3.2, h=1.7, sill=0.8, at=x, id=f"win_S{x:+.0f}"))
    ops.append(dict(wall="W", kind="door", type="glass", w=1.1, h=2.2, at=-1.9, id="entrance", open=35))
    R = arch.room(SIZE, at=(0, 0), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile", openings=ops, name="office", thick=0.25,
                  skirting="brushed_metal", cornice="plaster_clean")
    arch.vista(R, "N", "night_city" if night else "city_day", distance=18, seed=4, night=night)
    arch.vista(R, "S", "street", distance=10, seed=6, night=night)
    arch.vista(R, "W", "rooftops", distance=14, seed=8, night=night)
    # the glass meeting room: two glass walls meet in the corner; the north and east walls are the office's own
    x0, y0, x1, y1 = MEETING
    arch.glass_partition(x1 - x0 - 0.08, 2.7, at=((x0 + x1) / 2 + 0.04, y0, 0), rot_z=0, door=(-1.4, 1.0), opaque_band=0.5, name="meet_front", open_deg=45)
    arch.glass_partition(y1 - y0, 2.7, at=(x0, (y0 + y1) / 2, 0), rot_z=-90, opaque_band=0.5, name="meet_side")
    # ---- light
    mood = "office_night" if night else "office_day"
    lights.rig(mood, look=False, rim=0.0, ambient=0.05 if night else 0.18)
    for oid, hd in R.openings.items():
        if hd["kind"] != "window":
            continue
        if hd["wall"] == "N":
            lights.window_key(hd, color="#9FB4FF" if night else "#EAF2FF", power=120 if night else 430, shaft=not night, shaft_strength=0.04, pitch=18, name=f"KEY_{oid}")
        else:
            lights.window_key(hd, color="#FFD9A8" if night else "#FFF1DC", power=90 if night else 240, shaft=False, pitch=12, shadow=False, name=f"KEY_{oid}")
    lights.ambient_fill((0, 0, 2.5), (14, 9), power=10 if night else 18, color="#EAF0FF")
    lights.rim_light(MARK["worker_b"], from_deg=170, distance=4.0, power=260, color="#CFE0FF")
    # ---- the dressing, then the meeting room
    inv = dress.room(R, "office_open_plan", marks=MARK, density=1.0, seed=7, keep_clear=0.5, reserve=[(x0 - 0.15, y0 - 0.15, x1, y1)])
    mt = furnish.meeting_table(at=(5.3, 3.55, 0.0), rot_z=0)            # origin is the back-centre: the table spans y 2.45 to 3.55... centred on y = 3.0
    mt["sk_layer"] = "mid"
    for k, sx in enumerate((-0.8, 0.0, 0.8)):
        for side in (-1, 1):
            c = furnish.chair_office(at=(5.3 + sx, 3.0 + side * 1.27, 0.0), rot_z=0 if side > 0 else 180, color="#3A4A5A")
            c["sk_layer"] = "mid"
    tl = furnish.tops(mt)[0]
    for k, nm in enumerate(("laptop", "papers_stack", "mugs", "book_stack", "office_phone", "laptop")):
        o = furnish.make(nm, at=(tl[0].x - 1.0 + 0.4 * k, tl[0].y + (0.28 if k % 2 else -0.28), tl[1]), rot_z=0 if k % 2 else 180)
        o["sk_on"] = mt.name
        o["sk_layer"] = "mid"
    wb = furnish.whiteboard(at=(x1, 3.0, 0.9), rot_z=-90, width=2.4, height=1.15, seed=5)
    arch.tag_wall(wb, R.name, "E")
    wb["sk_layer"] = "background"
    pl = furnish.potted_plant(at=(7.3, 4.8, 0.0), height=1.6, seed=9)
    pl["sk_layer"] = "background"
    tv = furnish.tv(at=(5.3, 5.45, 0.0), rot_z=0, diag=1.3, stand=True)
    tv["sk_layer"] = "background"
    for i in range(2):
        pn = furnish.ceiling_light_panel(at=(4.2 + i * 2.4, 3.3 - 0.0 + 0.3, 2.8), size=(1.2, 0.6), power=45.0)
        arch.tag_wall(pn, R.name, "C")
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE}
