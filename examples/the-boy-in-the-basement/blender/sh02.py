"""sh02 - the phone line. An insert: the clue is the only thing in the frame. A hand, a tool, one wire.
The set module builds this corner of the house close-up (same wall colour, same moon) around where the reach ends."""
import set_house_night
from mathutils import Vector

from stagekit import assets, camera, cast, core


def build_shot(shot):
    cut_t = shot.t("cut")
    man = cast.from_plan("man", at=(0.0, 0.0), facing=180)                 # facing the wall (+Y); we only ever see his forearm
    shot.subjects.pop("man", None)
    man.pose("hand_up_R", 0.0, blend=0.0)
    man.pose("reach_R", cut_t, blend=0.55)                        # the reach ends exactly on "cut"
    core.bpy.context.scene.frame_set(shot.f(cut_t))
    cutters = assets.use("prop_wire_cutters", scale=1.7)          # a little oversized: a hero prop has to read on a phone
    man.hold(cutters, "R", offset=(0.0, 0.13, 0.03), rotation_deg=(0, 0, 90))   # jaws point at the wall
    tip = cutters.matrix_world @ Vector((0.05, 0.0, 0.004))       # between the jaws, where the reach ends

    D = set_house_night.wall_detail(tip)                          # the wall, wire and light of this corner of the set
    pivot, cut_pt = D["wire_pivot"], D["cut_point"]
    wire_x, wall_y, cut_z = cut_pt[0], cut_pt[1] + 0.02, cut_pt[2]
    # the cut wire lets go: the loose half swings away from the wall and settles
    core.key(pivot, "rotation_euler", cut_t + 0.06)
    core.key(pivot, "rotation_euler", cut_t + 0.34, (0.0, 0.42, 0.0))
    core.key(pivot, "rotation_euler", cut_t + 0.62, (0.0, 0.30, 0.0))
    core.key(pivot, "rotation_euler", cut_t + 0.90, (0.0, 0.36, 0.0))

    shot.subject("wire_cut", cut_pt)

    cam = camera.Camera(lens=85, blur="strong")
    # from his right side, along the wall: only the forearm and the tool come into frame, never his face
    cam.at(0.0, pos=(wire_x + 0.66, wall_y - 0.80, cut_z + 0.07), aim=(wire_x - 0.03, wall_y, cut_z - 0.03), focus=cut_pt)
    cam.push(0.0, cut_t + 0.1, 0.06)                              # tightens as the jaws close, then still for the fall
    cam.hold(shot.seconds)

    shot.moment("reaching", max(0.0, cut_t - 0.35))
    shot.moment("cut", cut_t + 0.02)
    shot.moment("wire_falls", cut_t + 0.45)
