"""The lobby of the NORTHLINE office building: 14 x 9 m, 4.6 m to the ceiling, a glass front with double glass doors on the south wall (the street is -Y).

A worked example of a modern interior with a street outside it, for the story "Two Seconds at the Office Door":

    marks first       MARK = the door (inside and at the card reader outside), where someone holds it, the speed gate, the lifts, the front desk,
                      the receptionist's place, the way to the open-plan office, and the north-east corner where the security camera hangs
    then the place    dress.office_lobby_room: stone floor, painted walls, a dark stone feature wall on the north, a 12.6 m gap in the south wall and a 2.4 m
                      opening in the west wall; dress.room(R, "office_lobby") fills it: glass front, doors, reception desk, three speed gates, two lifts,
                      seating on a rug, plants, wall logo, clock, screen, vending machine, recycling bins, umbrella stand, wet-floor sign, mat, nine ceiling
                      lights, security cameras, a lit open-plan office through the west opening, and outside the glass the forecourt, kerb, road, parked
                      cars, planters, bike rack, bus stop, the card reader post, the buildings across the road and the skyline
    then the light    day: a bright window key through the glass and the lamps on; rain: a cool grey key and rain falling outside, rain beads on the
                      glass, wet pavement; night: lit ceiling panels against a dark street and lit street lamps
    the story's gear  returned in the dict: the doors (animate with furnish.swing_door), the card reader's status lamp (furnish.lamp_state), the lift
                      core (furnish.open_lift), the speed gate, the reception desk and the security camera's position and aim for a CCTV cut

Camera side is -Y. WIDE is from the south-east corner by the glass, across the gates and the desk to the lifts and the opening to the office. Times: "office_day", "rain_day", "office_night".
"""
import math

from mathutils import Vector

from stagekit import arch, core, dress, furnish, fx, lights

THEME = "office_lobby"
SIZE = (14.0, 9.0, 4.6)
MARK = {
    "door_in": (0.0, 1.6, 0.0),            # just inside the glass doors
    "reader": (1.45, -1.45, 0.0),          # outside, in front of the card reader post
    "hold_door": (1.35, 0.7, 0.0),         # inside, beside the right-hand leaf, holding it open
    "lift_wait": (-3.2, 5.9, 0.0),         # in front of the lifts
    "desk": (3.8, 2.3, 0.0),               # visitor's place at the front desk counter
    "receptionist": (3.9, 4.6, 0.0),       # behind the counter
    "gate": (0.0, 3.0, 0.0),               # in front of the middle speed-gate lane
    "to_office": (-6.2, 5.5, 0.0),         # at the west opening to the open-plan office
    "cam_corner": (6.35, 8.75, 3.65),      # where the security dome hangs (the CCTV point of view): high in the north-east corner, with the doors and the gates in view
}
WIDE = ((6.2, 0.7, 1.9), (-2.2, 6.4, 1.25), 17.0)
LIGHT = {"office_day": {}, "rain_day": {}, "office_night": {}}
# the angles the film really uses, rendered by set_preview.py next to the derived six (and audited with them): (position, aim, lens in mm)
PREVIEWS = {
    "cctv": ((6.23, 8.35, 3.43), (0.0, 1.7, 1.0), 24.0),               # the security dome's view: down across the gates to the doors
    "door_in": ((0.4, 5.2, 1.55), (0.0, 0.0, 1.3), 24.0),            # from the gates back at the doors and the street
    "street_in": ((0.9, -4.2, 1.6), (0.0, 3.0, 1.4), 22.0),          # from the pavement through the glass into the lobby
}


def build_set(time: str = "office_day"):
    night = time == "office_night"
    rain = time == "rain_day"
    R = dress.office_lobby_room("lobby", office=True)
    # ---- the light: a rig, a key through the glass front, a cool or warm tone to suit the hour
    lights.rig(time, sun_from=-20, sun_elevation=50, look=False, rim=0.0, ambient=0.06 if night else (0.55 if rain else 0.45)) if time in lights.MOODS else lights.rig("office_day", look=False, rim=0.0)
    front = R.openings["front"]
    if night:
        lights.window_key(front, color="#8FA6FF", power=110, shaft=False, pitch=14, shadow=False, name="KEY_front")
    elif rain:
        lights.window_key(front, color="#CFE0F2", power=900, shaft=False, pitch=16, shadow=False, name="KEY_front")
    else:
        lights.window_key(front, color="#FFF2DC", power=1500, shaft=True, shaft_strength=0.03, pitch=18, shadow=False, name="KEY_front")
        lights.window_sun(R, "S", elevation=38.0, yaw=-25.0, power=1.6)
    inv = dress.room(R, "office_lobby", marks=MARK, density=1.0, seed=7, keep_clear=0.6, night=night, wet=rain, office=True, outside=True)
    refs = R.refs
    # ---- rain outside the glass, on the glass, and off the canopy
    wx = (0.14, 0.0)
    if rain:
        fx.rain(dict(lo=(-16.0, -18.0), hi=(16.0, -0.3)), intensity=1.7, wind=wx, ground=0.0, near=(0.5, -3.5, 7.5),
                exclude=[(-3.55, -2.9, 3.55, -0.25, 3.3), (-14.1, -5.3, -10.9, -2.1, 2.6)])
        fx.window_rain(refs["front"], density=1.0)
        fx.drips_edge((-3.4, -2.86, 3.28), (3.4, -2.86, 3.28), n=22, fall=3.25)
        fx.rain_splashes((-14.0, -14.4, 14.0, -5.7), count=170, ground=-0.14, seed=21)
    reader_lamp = furnish.part(refs["reader"], "lamp") if refs.get("reader") is not None else None
    cam = refs.get("camera")
    cam_pos = Vector((MARK["cam_corner"][0] - 0.12, MARK["cam_corner"][1] - 0.4, MARK["cam_corner"][2] - 0.22))   # just below and in front of the dome, not inside it
    cctv = (tuple(cam_pos), (0.0, 1.7, 1.0))                        # a camera position and aim for the lobby-camera cut: from the dome, down across the gates to the doors
    return {"room": R, "mark": MARK, "inventory": inv, "time": time, "wide": WIDE, "refs": refs, "doors": refs.get("doors"), "front": refs.get("front"),
            "reader_post": refs.get("reader"), "reader_lamp": reader_lamp, "lifts": refs.get("lifts"), "gate": refs.get("gate"), "reception": refs.get("reception"),
            "security_camera": cam, "cctv": cctv, "canopy": refs.get("canopy")}
