"""sh01 - the watcher. One long take: we stand behind him, lean in as he decides, and watch the house go dark."""
import set_house_night
from stagekit import camera, cast


def build_shot(shot):
    S = set_house_night.build_set(subject=(0.7, 0, 1.4))
    man = cast.from_plan("man", at=(0.7, 0.0), facing=180)            # back to us: his face stays hidden (plan: must_not_show)
    shot.subjects.pop("man", None)                           # ...so his head is not something the viewer must read
    shot.subject("house", (1.0, 11.45, 2.4))                 # a point on the front wall

    # light change, on the words: the two windows die one after the other
    off = shot.t("lights went out", edge="end")
    set_house_night.windows_off(S["windows"], [off - 0.25, off + 0.45])

    # action: he is still for the whole shot, then one step forward when the narrator is done
    step = shot.t("dogs slept", edge="end") + 0.15
    man.walk(step, distance=0.7, speed=0.6)
    man.idle(blinks=False)

    # camera: over his right shoulder; a very slow dolly while he decides, then hold for the light change
    house_pt = (0.0, 14.0, 2.3)
    cam = camera.Camera(lens=40, blur="medium")
    cam.at(0.0, pos=(1.12, -2.45, 1.70), aim=(-0.25, 14.0, 2.9), focus=house_pt)
    cam.at(shot.t("the boy inside", edge="end"), pos=(1.16, -1.75, 1.72))
    cam.hold(shot.seconds)
    # focus: house -> him ("Tonight, he would take the boy") -> house again (so we watch the windows)
    cam.rack(shot.t("Tonight") + 0.5, man.chest, duration=0.8)
    cam.rack(shot.t("He knew when the lights") + 0.3, house_pt, duration=0.8)

    shot.notes.append("He is a deliberate dark shape from behind (his face is hidden until sh05); at 'focus_on_him' the focus is on his back on purpose.")
    shot.notes.append("Night: the house front is deliberately dim (luma about 0.1). It reads through the lit windows, then as a shape against the sky.")
    shot.moment("watching", 1.5)
    shot.moment("focus_on_him", shot.t("Tonight") + 1.0)
    shot.moment("windows_lit", off - 0.5)
    shot.moment("windows_dark", off + 0.9)
