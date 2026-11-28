"""The shot plan format 2: the fixture passes, every rule has a failing fixture, and the example in the shot-plan skill passes.

    py -3 tools/tests/test_plan_schema.py          (plain Python; also collected by pytest)

Fixtures: tools/tests/fixtures/plan_new_format.json (a two-set story) with its script. Each failing case changes one thing in a copy of it and
expects a given message (a substring of the error or warning). The skill's worked example is the JSON block between the markers
<!-- plan-example:start --> and <!-- plan-example:end --> in .claude/skills/shot-plan/SKILL.md; its script is made from its own vo_text.
"""
from __future__ import annotations

import ast
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.dont_write_bytecode = True

import plan  # noqa: E402
import plan_v2  # noqa: E402

FIX = ROOT / "tools" / "tests" / "fixtures"
SKILL = ROOT / ".claude" / "skills" / "shot-plan" / "SKILL.md"


def load():
    return json.loads((FIX / "plan_new_format.json").read_text(encoding="utf-8")), json.loads((FIX / "plan_new_format_script.json").read_text(encoding="utf-8"))


def script_of(p: dict) -> dict:
    return {"title": p.get("title", "t"), "beats": [{"voiceover": s["vo_text"]} for s in p["shots"]]}


def run(p, s=None):
    return plan.check(p, s or script_of(p))


def has(msgs, text):
    return any(text in m for m in msgs)


def shot(p, sid):
    return next(s for s in p["shots"] if s["id"] == sid)


def view(p, sid, vid):
    return next(v for v in shot(p, sid)["views"] if v["id"] == vid)


def setof(p, sid):
    return next(s for s in p["sets"] if s["id"] == sid)


# ----------------------------------------------------------------------------- the good plans
def test_fixture_passes():
    p, s = load()
    e, w = plan.check(p, s)
    assert not e, e
    assert not [x for x in w if "draft" not in x], w          # the only warnings are the draft characters


def test_skill_example_passes():
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"<!-- plan-example:start -->\s*```json\s*(.*?)```\s*<!-- plan-example:end -->", text, re.S)
    assert m, "the shot-plan skill has no worked example between the plan-example markers"
    p = json.loads(m.group(1))
    e, w = run(p)
    assert not e, e
    assert not [x for x in w if "draft" not in x], w


# ----------------------------------------------------------------------------- one failing fixture per rule
def case(name, mutate, expect, level="error", fn=None):
    p, s = load()
    mutate(p)
    e, w = plan.check(p, s) if fn is None else fn(p, s)
    msgs = e if level == "error" else w
    assert has(msgs, expect), f"{name}: expected {level} containing {expect!r}; got errors={e} warnings={w}"


def test_set_rules():
    def no_arch(p): del setof(p, "office")["architecture"]
    case("no architecture", no_arch, "architecture is missing")

    def empty_beyond(p): setof(p, "office")["layers"]["beyond"] = []
    case("empty layer", empty_beyond, "layers.beyond is empty")

    def no_vista(p): del setof(p, "office")["architecture"]["walls"][0]["openings"][0]["vista"]
    case("opening without a vista", no_vista, "'vista' is missing")

    def no_ceiling(p): del setof(p, "office")["architecture"]["ceiling"]
    case("interior without a ceiling", no_ceiling, "ceiling is missing")

    def three_walls(p): setof(p, "office")["architecture"]["walls"].pop()
    case("interior with three walls", three_walls, "an interior needs all four")

    def poor(p):
        st = setof(p, "shop")
        st["dressing"] = st["dressing"][:2]
        st["layers"] = {k: v[:1] for k, v in st["layers"].items()}
    case("too few prop types", poor, "distinct things across layers and dressing")

    def wrong_era(p): setof(p, "office")["theme"] = "throne_room"
    case("theme of another era", wrong_era, "belongs to")

    def wrong_kind(p): setof(p, "office")["kind"] = "exterior"
    case("interior theme on an exterior", wrong_kind, "dresses an interior")

    def bad_theme(p): setof(p, "office")["theme"] = "spaceship"
    case("unknown theme", bad_theme, "theme must be 'custom' or one of")

    def few_practicals(p): setof(p, "office")["practicals"] = setof(p, "office")["practicals"][:2]
    case("two practicals in an interior", few_practicals, "practicals, need at least 3")

    def no_atmo(p): setof(p, "office")["atmosphere"] = []
    case("no atmosphere", no_atmo, "atmosphere, need at least 1")

    def few_details(p): setof(p, "office")["details"] = setof(p, "office")["details"][:1]
    case("one detail", few_details, "details, need at least 3")

    def no_marks(p): del setof(p, "shop")["marks"]
    case("no marks", no_marks, "marks is missing")

    def bad_mark(p): setof(p, "shop")["marks"]["counter"] = "centre"
    case("a mark without numbers", bad_mark, "must be [x, y]")

    def no_survive(p): del setof(p, "shop")["must_survive"]
    case("no must_survive", no_survive, "must_survive is missing")

    def bad_size(p): setof(p, "office")["size_m"] = [16, 11]
    case("interior without a height", bad_size, "size_m = [width, depth, height]")

    def old_dressing(p): setof(p, "shop")["dressing"] = ["barrels at the wall", "a rug"]
    case("old free-text dressing warns", old_dressing, "old free-text list", level="warn")

    def no_kind(p): del setof(p, "shop")["kind"]
    case("no kind", no_kind, "kind must be one of")


def test_camera_rules():
    def static_long(p): view(p, "sh01", "sam_stares")["move"] = {"type": "static"}
    case("a long static view", static_long, "A held frame feels dead")

    def static_ok(p):
        view(p, "sh01", "sam_stares")["move"] = {"type": "static"}
        view(p, "sh01", "sam_stares")["still_reason"] = "held on purpose"
    p, s = load()
    static_ok(p)
    e, _ = plan.check(p, s)
    assert not has(e, "A held frame feels dead"), e

    def unknown_move(p): view(p, "sh01", "sam_stares")["move"] = {"type": "zoomburst"}
    case("unknown move", unknown_move, "is not in the camera library")

    def no_move(p): del view(p, "sh01", "sam_stares")["move"]
    case("no move", no_move, "move is missing")

    def whip_no_target(p):
        view(p, "sh01", "sam_stares")["move"] = {"type": "whip"}
        view(p, "sh01", "busy_office")["enter"] = "whip"
    case("whip without a target", whip_no_target, "a whip needs a 'target'")

    def whip_mismatch(p): view(p, "sh01", "busy_office")["enter"] = "whip"
    case("enter whip after a view with another move", whip_mismatch, "enter is 'whip' but the view before")

    def whip_wrong_target(p):
        view(p, "sh01", "sam_stares")["move"] = {"type": "whip", "target": "tiny_note", "duration_s": 0.4}
        view(p, "sh01", "busy_office")["enter"] = "whip"
    case("whip aimed past the next view", whip_wrong_target, "is not the next view")

    def first_enter(p): view(p, "sh01", "sam_stares")["enter"] = "through"
    case("first view entered by a through", first_enter, "first view of a shot is reached by a 'cut'")

    def bad_ease(p): view(p, "sh01", "sam_stares")["move"]["ease"] = "bounce"
    case("unknown ease", bad_ease, "move.ease")

    def bad_framing(p): view(p, "sh01", "sam_stares")["framing"] = "selfie"
    case("unknown framing", bad_framing, "is not a camera helper")

    def bad_angle(p): del view(p, "sh01", "sam_stares")["angle"]
    case("no angle", bad_angle, "angle must be one of")

    def side_not_covered(p): view(p, "sh01", "sam_stares")["side"] = "left"
    case("side the set does not survive", side_not_covered, "must_survive")

    def line_cross(p):
        setof(p, "shop")["must_survive"].append("reverse")
        view(p, "sh02", "box_slides")["side"] = "reverse"
    case("crossing the line of action", line_cross, "line of action")

    def line_cross_ok(p):
        setof(p, "shop")["must_survive"].append("reverse")
        view(p, "sh02", "box_slides")["side"] = "reverse"
        view(p, "sh02", "box_slides")["cross_line"] = True
    p, s = load()
    line_cross_ok(p)
    e, _ = plan.check(p, s)
    assert not has(e, "line of action"), e

    def no_line(p): del shot(p, "sh02")["line_of_action"]
    case("two characters and no line", no_line, "line_of_action is missing")

    def bad_line(p): shot(p, "sh02")["line_of_action"]["between"] = ["sam", "nobody"]
    case("line names a stranger", bad_line, "neither in this shot's cast nor a mark")

    def never_wide(p):
        for v in shot(p, "sh02")["views"]:
            if v["size"] == "wide":
                v["size"] = "medium"
                v.pop("framing", None)
    case("a set never shown wide", never_wide, "is never shown in a wide or establishing view")

    def wide_late(p):
        view(p, "sh01", "busy_office")["size"] = "medium"
        view(p, "sh01", "busy_office").pop("framing", None)
        view(p, "sh03", "empty_office")["size"] = "wide"
    case("wide only in a later shot warns", wide_late, "never shows it wide", level="warn")

    def bad_lens(p): view(p, "sh01", "sam_stares")["lens_mm"] = 3
    case("lens out of range", bad_lens, "lens_mm")

    def whip_short(p):
        view(p, "sh01", "sam_stares")["move"] = {"type": "whip", "target": "busy_office", "duration_s": 1.5}
        view(p, "sh01", "busy_office")["enter"] = "whip"
    case("a slow whip warns", whip_short, "a whip lasts", level="warn")


def test_film_level_warnings():
    def one_type(p):
        for s in p["shots"]:
            for v in s["views"]:
                v["move"] = {"type": "dolly"}
    case("one move type", one_type, "different camera move type", level="warn")
    case("one move dominating", one_type, "no single move should be more than half", level="warn")

    def all_static(p):
        for s in p["shots"]:
            for v in s["views"]:
                v["move"] = {"type": "drift"}
    case("too much holding", all_static, "held views (static or drift) take", level="warn")

    def all_cuts(p):
        for s in p["shots"]:
            s.pop("transition_in", None)
            for v in s["views"][:1]:
                v["enter"] = "cut"
    case("every boundary a cut", all_cuts, "every shot boundary is a plain cut", level="warn")


def test_transition_rules():
    def bad_type(p): shot(p, "sh02")["transition_in"] = {"type": "swirl"}
    case("unknown transition", bad_type, "transition_in 'swirl'")

    def bad_dur(p): shot(p, "sh02")["transition_in"]["dur"] = 9
    case("transition too long", bad_dur, "transition_in.dur")

    def bad_dir(p): shot(p, "sh02")["transition_in"]["dir"] = "sideways"
    case("transition direction", bad_dir, "transition_in.dir")

    def on_first(p): shot(p, "sh01")["transition_in"] = "dissolve"
    case("transition on the first shot", on_first, "ignored", level="warn")

    def string_form(p): shot(p, "sh02")["transition_in"] = "whip"
    p, s = load()
    string_form(p)
    e, _ = plan.check(p, s)
    assert not e, e


def test_old_plans_keep_working():
    p, s = load()
    for st in p["sets"]:
        for k in ("kind", "theme", "size_m", "architecture", "layers", "practicals", "atmosphere", "details", "must_survive", "marks"):
            st.pop(k, None)
        st["dressing"] = ["barrels"]
    for sh in p["shots"]:
        sh.pop("transition_in", None)
        sh.pop("line_of_action", None)
        for v in sh["views"]:
            for k in ("move", "angle", "side", "enter", "framing", "still_reason"):
                v.pop(k, None)
    p.pop("plan_version")
    e, w = plan.check(p, s)
    assert not e, e
    assert has(w, "old format"), w


def test_light_rules():
    """shot.light {motivation, source}, view.hero, view.separate: plain words, checked against the set and the cast."""
    def bad_hero(p): view(p, "sh02", "box_slides")["hero"] = "queen"
    case("hero not in the cast", bad_hero, "hero 'queen' is not in this shot's cast")

    def bad_sep(p): view(p, "sh02", "box_slides")["separate"] = "nobody"
    case("separate not in the cast", bad_sep, "separate 'nobody' is not in this shot's cast")

    def bad_source(p): shot(p, "sh01")["light"]["source"] = "a chandelier"
    case("source the set does not list", bad_source, "is not something set 'office' lists")

    def no_motivation(p): shot(p, "sh01")["light"] = {"source": "window light"}
    case("light without a motivation", no_motivation, "light must be")

    p, s0 = load()                                                         # a mark of the set may be the hero (a prop the light is for)
    view(p, "sh01", "tiny_note")["hero"] = "worker_a"
    e, w = plan.check(p, s0)
    assert not [x for x in e if "hero" in x], e

    def partial(p): del shot(p, "sh03")["light"]
    case("a plan that uses light notes carries them everywhere", partial, "sh03: no light note", level="warn")

    def no_hero(p): del view(p, "sh02", "box_slides")["hero"]
    case("two people, no hero", no_hero, "box_slides: no hero", level="warn")

    def sep_hero(p): view(p, "sh02", "box_slides")["separate"] = "keeper"
    case("separate is the hero", sep_hero, "is the hero", level="warn")

    def long_note(p): shot(p, "sh01")["light"]["motivation"] = "word " * 31
    case("a motivation longer than a sentence", long_note, "light.motivation is", level="warn")

    for src in ("window light", "win_N-2", "the north windows", "sun", "desk lamps"):          # accepted ways to name a source of the office
        p, s = load()
        shot(p, "sh01")["light"]["source"] = src
        e, w = plan.check(p, s)
        assert not [x for x in e if "light.source" in x], (src, e)


def test_plans_without_light_stay_silent():
    p, s = load()
    for sh in p["shots"]:
        sh.pop("light", None)
        for v in sh["views"]:
            v.pop("hero", None)
            v.pop("separate", None)
    e, w = plan.check(p, s)
    assert not e, e
    assert not [x for x in w if "light" in x or "hero" in x], w          # no new warning for a plan that never used the fields


def test_planlink_hands_hero_and_separation_to_the_shot():
    sys.path.insert(0, str(ROOT / "tools" / "blender"))
    import planlink
    p, _ = load()
    assert planlink.viewlight_options(shot(p, "sh02")) == {"hero": {"box_slides": "keeper"}, "edge": {"box_slides": ["sam"]}}
    assert planlink.viewlight_options(shot(p, "sh03")) == {}
    assert planlink.viewlight_options(None) == {}
    v = view(p, "sh01", "tiny_note")
    v["hero"] = "worker_a"                                              # a mark is a prop: the key finds it, nothing is passed
    assert "tiny_note" not in planlink.viewlight_options(shot(p, "sh01")).get("hero", {})
    import inspect
    vl = (ROOT / "tools/blender/stagekit/viewlight.py").read_text(encoding="utf-8")
    assert '{"hero", "edge", "key_side", "scale"}' in vl, "viewlight.shape options changed: update planlink.viewlight_options and the stagekit skill"
    assert inspect.signature(planlink.viewlight_options)


# ----------------------------------------------------------------------------- the validator agrees with the code it describes
def _dict_keys(path: Path, name: str) -> list[str]:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == name for t in node.targets) and isinstance(node.value, ast.Dict):
            return [ast.literal_eval(k) for k in node.value.keys]
    raise AssertionError(f"{name} not found in {path}")


def _tuple(path: Path, name: str) -> list[str]:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == name for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise AssertionError(f"{name} not found in {path}")


def test_agrees_with_the_toolkit():
    assert list(plan.MOODS) == _dict_keys(ROOT / "tools/blender/stagekit/lights.py", "MOODS"), "plan.MOODS must equal stagekit.lights.MOODS"
    assert list(plan_v2.TRANSITIONS) == _tuple(ROOT / "tools/assemble.py", "TRANSITION_TYPES")
    assert list(plan_v2.DIRECTIONS) == _tuple(ROOT / "tools/assemble.py", "DIRECTIONS")
    cam_src = (ROOT / "tools/blender/stagekit/camera.py").read_text(encoding="utf-8")
    for mv in plan_v2.MOVES:
        if mv not in plan_v2.HOLDS:
            assert re.search(rf"def {mv}\(", cam_src), f"camera.py has no move '{mv}'"
    for fr in plan_v2.FRAMINGS:
        assert re.search(rf"def {fr}\(", cam_src), f"camera.py has no framing helper '{fr}'"
    assert "dolly_zoom" in plan_v2.MOVES and len(plan_v2.themes()) >= 13


def main():
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f()
            print(f"ok    {n}")
        except Exception as e:                                  # noqa: BLE001
            fails += 1
            print(f"FAIL  {n}: {type(e).__name__}: {e}")
    print(f"{len(tests) - fails}/{len(tests)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
