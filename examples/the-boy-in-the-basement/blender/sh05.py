"""sh05 - the reversal, one take. Two small figures in a dark field -> police light (threat?) -> 'He had called them'
-> the first clear look at his face, next to the boy's, in warm light. The camera ends completely still for 'Papa'."""
import set_field_road
from stagekit import camera, cast, core, lights


def build_shot(shot):
    S = set_field_road.build_set()
    rig = S["rig"]
    man = cast.from_plan("man", at=(0.4, 13.5), facing=0)        # coming toward us: the first time we may see his face
    boy = cast.from_plan("boy")
    man.carry(boy, 0.0, turn_in=-20)                              # face a little toward us: the last word is his
    arrive = man.walk(0.0, to=(0.3, -3.2), speed=1.3, arms=False)   # hurrying; the arms keep hold of the child

    t_pol = shot.t("Police cars")
    t_called = shot.t("He had called them")
    t_five = shot.t("Five days ago")
    t_held = shot.t("held him tight")
    t_papa = shot.t("Papa")
    man.brows("stern", 0.0, blend=0.0)
    man.look(boy.head, t_held, blend=0.6)                        # he looks down at his son
    man.brows("concerned", t_held + 0.2, blend=0.5)
    boy.brows("worried", 0.0, blend=0.0)
    boy.look(man.head, t_held + 0.3, blend=0.5)                  # looks up at his father
    boy.brows("calm", t_papa, blend=0.4)
    man.idle()
    boy.idle()

    # police light reads as "caught" for one sentence. It starts as the narrator names the police cars.
    car = S["cars"][0].matrix_world.translation
    lights.flash("police", (car.x, car.y + 2.6, 2.7), power=2400, t0=max(0.0, t_pol - 0.5), period=0.9, radius=0.4)   # ahead of the car, so its own roof does not burn
    lights.practical("headlights", (car.x, car.y + 2.3, 0.65), "#FFF3D6", 700, kind="SPOT", aim=(0.3, 9.0, 1.2), size=0.25, rig_=rig)
    # the light opens up one beat after the truth: a warm soft key from the cars' side
    warm = lights.practical("relief_key", (2.4, -5.6, 2.3), "#FFD2A0", 0.0, kind="AREA", aim=(0.3, -3.2, 1.45), size=2.2, rig_=rig)
    lights.change(warm, t_five, t_five + 2.2, power=330)

    cam = camera.Camera(lens=35, blur="light")
    # behind the waiting car: its light bar sits low in the frame, the field and two small figures beyond it
    cam.at(0.0, pos=(1.05, -10.4, 1.95), aim=(0.4, 8.0, 1.2), focus=man.head)
    cam.follow(man.head, 0.0, t_called, aim=True, focus=True, lag=0.25)       # let them come to us
    cam.hold(t_called)
    cam.at((t_called + t_held) / 2 - 0.4, pos=(1.05, -8.3, 2.7))             # rise over the car on the way in
    core.bpy.context.scene.frame_set(shot.f(arrive + 0.5))
    two_faces = (man.head.point() + boy.head.point()) / 2          # where they will be standing: frame both faces
    cam.at(t_held - 0.2, pos=(1.0, -5.45, 1.42), aim=two_faces, lens=52, focus=boy.head, blur="medium")   # the truth arrives as we get close
    cam.follow(boy.head, t_called, t_held - 0.2, aim=False, focus=True)
    cam.hold(shot.seconds)                                                    # completely still for "Papa"

    shot.subject("boy", boy.head)
    shot.notes.append("Wide frames: the two figures are small and dark against the moonlit field on purpose; the police bar is the bright foreground.")
    shot.moment("far_figures", 1.2)
    shot.moment("police_light", t_pol + 1.0)
    shot.moment("closing_in", (t_called + t_held) / 2)
    shot.moment("papa", t_papa + 0.3)
