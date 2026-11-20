"""sh03 - target and strike in one take. Window -> the boy alone -> a dark shape crosses behind him -> a hand reaches in.
Not shown, on purpose: the climb ('he climbed through a window' plays on the window itself) and the lift (sh04 covers it).
His face never enters the frame: he crosses with his head above the frame line and ends outside frame-left."""
import set_basement
from stagekit import camera, cast


def build_shot(shot):
    S = set_basement.build_set()
    boy = cast.from_plan("boy")
    boy.lie(at=(-0.35, -0.3), head_toward=-90, z=S["mattress_top"])          # head on the pillow at the left end
    boy.pose([("upper_arm_fk.L", "Y", 12), ("upper_arm_fk.R", "Y", -12), ("forearm_fk.L", "X", 14), ("forearm_fk.R", "X", 14)], 0.0, blend=0.0)  # arms by his sides
    man = cast.from_plan("man", at=(2.45, 0.95), facing=-80)                 # already inside, out of frame by the window wall
    shot.subjects.pop("man", None)                                          # his face must stay unreadable until sh05
    shot.subject("hand", man.hand_R, moments=["reach", "end"])              # ...but his hand is the clue, so it is checked where it acts
    shot.subject("window", (1.3, 2.2, 2.5), moments=["start", "window"])

    t_cross = shot.t("He crossed")
    t_mouth = shot.t("mouth")
    man.appear(shot.t("a small boy") + 0.3)                                   # not in the window frames; he is outside the crane-down frame by then
    arrive = man.walk(t_cross, to=(-1.75, 0.2), speed=0.55)                 # slow and careful: "without a sound"
    man.face(boy.head, arrive + 0.45, duration=0.45)
    reach = cast.POSES["crouch"] + [("upper_arm_fk.R", "X", -50), ("forearm_fk.R", "X", -14)]   # down and forward, toward his face
    man.pose(reach, max(arrive + 1.0, t_mouth + 0.1), blend=0.75)            # crouch and reach; the hand arrives on "mouth"
    man.idle(blinks=False)

    boy.look((0, -10), 0.0, blend=0.0)                                      # staring at the ceiling
    boy.brows("worried", 0.0, blend=0.0)
    boy.look((0, -32), t_mouth, blend=0.25)                                  # his head tips back toward the hand above him
    boy.brows("shocked", t_mouth - 0.05, blend=0.12)
    boy.idle()

    cam = camera.Camera(lens=35, blur="medium")
    window = (1.3, 2.25, 2.5)
    cam.at(0.0, pos=(-0.2, -3.3, 0.55), aim=window, focus=window)            # "he climbed through a window": stay on the window
    cam.hold(shot.t("Two men"))
    t_boy = shot.t("a small boy")
    cam.at(t_boy + 0.2, pos=(-1.25, -2.5, 0.62), aim=(-0.75, -0.3, 0.30), focus=boy.head, lens=50)   # crane down with the narrator: upstairs -> basement
    cam.hold(t_cross)
    cam.at(shot.seconds - 0.4, pos=(-0.95, -2.15, 0.40), aim=(-1.02, -0.25, 0.20), lens=45)   # the room closes in on him; the hand enters from frame-left, his head stays above the frame line
    cam.hold(shot.seconds)

    shot.notes.append("The man is a deliberate dark shape: head above the frame while he crosses, body outside frame-left at the end. Only his hand may read.")
    shot.notes.append("The hand enters at the frame-left edge and stays dim on purpose: it is a threat arriving, not a subject to study.")
    shot.moment("window", 1.0)
    shot.moment("boy_alone", t_boy + 1.2)
    shot.moment("shape_behind", (t_cross + arrive) / 2)
    shot.moment("reach", t_mouth + 0.35)
