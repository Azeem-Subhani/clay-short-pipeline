"""Tests for the review rule (tools/reviewgate.py): a shot reaches the final render only in the form its reviewer passed.

    py -3 -I tools/tests/test_reviewgate.py

Everything runs in a temporary folder with small fake plan, set and shot files; nothing under output/ is touched.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import reviewgate as rg  # noqa: E402

PLAN = {"world": {"era": "modern"}, "cast": [{"id": "maya", "base": "Aj_F"}, {"id": "guard", "base": "Aj_M"}],
        "shots": [{"id": "sh01", "set": "lobby"}, {"id": "sh02", "set": "lobby"}]}
TIMING = {"shots": {"sh01": {"seconds": 4.0, "frames": 96, "start_s": 0.0}, "sh02": {"seconds": 3.0, "frames": 72, "start_s": 4.0}},
          "words": [{"text": "hello", "start": 0.2, "end": 0.5, "shot": "sh01"}, {"text": "there", "start": 4.3, "end": 4.6, "shot": "sh02"}]}


def w(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.clip = Path(self._tmp.name) / "demo"
        w(self.clip / "shotplan.json", json.dumps(PLAN))
        w(self.clip / "timing.json", json.dumps(TIMING))
        w(self.clip / "blender" / "set_lobby.py", "# set\n")
        w(self.clip / "blender" / "set_office.py", "# another set\n")
        w(self.clip / "blender" / "sh01.py", 'HOLD = (1, 2)\nIMG = "cctv.png"\nmaya = cast.from_plan("maya")\n')
        w(self.clip / "blender" / "sh02.py", 'src = (HERE / "sh01.py").read_text()   # reads HOLD from the shot before\n')
        w(self.clip / "assets" / "cctv.png", "picture")
        w(self.clip / "assets" / "poster.png", "a poster no shot names")

    def tearDown(self):
        self._tmp.cleanup()

    def stills(self, sid, blocking=0, build=None):
        items = [{"level": "block", "code": "x", "text": "x"}] * blocking
        w(self.clip / "review" / sid / "checks.json", json.dumps({"build": build or rg.build_id(self.clip, sid), "items": items}))

    def verdict(self, sid, v="pass", build=None, issues=()):
        w(self.clip / "review" / sid / "verdict.json", json.dumps({"verdict": v, "reviewed_build": build or rg.build_id(self.clip, sid),
                                                                   "issues": [{"problem": i} for i in issues]}))

    def status(self, sid):
        return rg.state(self.clip, sid)["status"]


class TestStates(Base):
    def test_order_of_states(self):
        self.assertEqual(self.status("sh01"), "no_stills")
        self.stills("sh01")
        self.assertEqual(self.status("sh01"), "no_verdict")
        self.verdict("sh01", "fix", issues=["hand off the handle"])
        self.assertEqual(self.status("sh01"), "not_passed")
        self.verdict("sh01", "pass")
        self.assertEqual(self.status("sh01"), "pass")
        self.assertTrue(rg.state(self.clip, "sh01")["ok"])

    def test_blocking_checks_stop_a_passed_shot(self):
        self.stills("sh01", blocking=2)
        self.verdict("sh01", "pass")
        self.assertEqual(self.status("sh01"), "blocked")

    def test_stills_without_a_build_stamp_are_stale(self):
        w(self.clip / "review" / "sh01" / "checks.json", json.dumps({"items": []}))
        self.verdict("sh01", "pass")
        self.assertEqual(self.status("sh01"), "stale_stills")

    def test_verdict_without_reviewed_build_is_stale(self):
        self.stills("sh01")
        w(self.clip / "review" / "sh01" / "verdict.json", json.dumps({"verdict": "pass"}))
        self.assertEqual(self.status("sh01"), "stale_verdict")

    def test_check_lists_only_the_shots_that_may_not_render(self):
        for sid in ("sh01", "sh02"):
            self.stills(sid)
        self.verdict("sh01", "pass")
        ok, bad = rg.check(self.clip, ["sh01", "sh02"])
        self.assertFalse(ok)
        self.assertEqual([b["shot"] for b in bad], ["sh02"])


class TestStaleness(Base):
    def passed(self, sid):
        self.stills(sid)
        self.verdict(sid, "pass")
        self.assertEqual(self.status(sid), "pass")

    def test_editing_the_shot_after_the_review_reopens_it(self):
        self.passed("sh01")
        w(self.clip / "blender" / "sh01.py", "HOLD = (1, 3)\n")
        self.assertEqual(self.status("sh01"), "stale_stills")
        self.stills("sh01")                                   # new stills alone are not a review
        self.assertEqual(self.status("sh01"), "stale_verdict")

    def test_an_imported_shot_module_counts(self):
        self.passed("sh02")
        w(self.clip / "blender" / "sh01.py", "HOLD = (9, 9)\n")
        self.assertEqual(self.status("sh02"), "stale_stills")

    def test_set_asset_timing_and_plan_count(self):
        for change in (lambda: w(self.clip / "blender" / "set_lobby.py", "# set, moved the door\n"),
                       lambda: w(self.clip / "assets" / "cctv.png", "another picture"),
                       lambda: w(self.clip / "timing.json", json.dumps(TIMING | {"shots": TIMING["shots"] | {"sh01": {"seconds": 5.0, "frames": 120}}})),
                       lambda: w(self.clip / "shotplan.json", json.dumps(PLAN | {"cast": [{"id": "maya", "base": "Aj_F2"}]}))):
            self.passed("sh01")
            change()
            self.assertEqual(self.status("sh01"), "stale_stills")

    def test_what_the_shot_does_not_use_does_not_reopen_it(self):
        later = {"shots": {"sh01": TIMING["shots"]["sh01"] | {"seconds": 6.0, "frames": 144}, "sh02": TIMING["shots"]["sh02"] | {"start_s": 6.0}},
                 "words": [TIMING["words"][0], TIMING["words"][1] | {"start": 6.3, "end": 6.6}]}
        for change, shot in ((lambda: w(self.clip / "timing.json", json.dumps(later)), "sh02"),              # a retake of sh01 moves sh02 in the film, not in itself
                             (lambda: w(self.clip / "blender" / "set_office.py", "# another set, changed\n"), "sh01"),
                             (lambda: w(self.clip / "assets" / "poster.png", "a new poster"), "sh01"),
                             (lambda: w(self.clip / "shotplan.json", json.dumps(PLAN | {"cast": [PLAN["cast"][0], {"id": "guard", "base": "Aj_M2"}]})), "sh01")):
            self.passed(shot)
            change()
            self.assertEqual(self.status(shot), "pass")

    def test_a_module_read_as_text_counts(self):
        self.assertIn("blender/sh01.py", rg.inputs(self.clip, "sh02"))
        self.assertNotIn("blender/sh02.py", rg.inputs(self.clip, "sh01"))


class TestFramesAndStamp(Base):
    def test_stamp_writes_build_and_kit(self):
        w(self.clip / "review" / "sh01" / "checks.json", json.dumps({"items": []}))
        self.assertEqual(rg.stamp_stills(self.clip, "sh01"), rg.build_id(self.clip, "sh01"))
        data = json.loads((self.clip / "review" / "sh01" / "checks.json").read_text(encoding="utf-8"))
        self.assertEqual(data["kit"], rg.kit_id())
        self.assertIsNone(rg.stamp_stills(self.clip, "sh02"))

    def test_frames_from_an_older_build_are_stale(self):
        out = self.clip / "render" / "sh01" / "final"
        self.assertEqual(rg.frames_state(self.clip, "sh01")["status"], "none")
        w(out / "0001.png", "frame")
        self.assertEqual(rg.frames_state(self.clip, "sh01")["status"], "stale")          # no build stamp
        w(out / "render.json", json.dumps({"build": rg.build_id(self.clip, "sh01")}))
        self.assertEqual(rg.frames_state(self.clip, "sh01")["status"], "current")
        w(self.clip / "blender" / "sh01.py", "HOLD = (7, 7)\n")
        self.assertEqual(rg.frames_state(self.clip, "sh01")["status"], "stale")


class TestAcceptance(Base):
    def test_accept_needs_a_reason_and_a_current_verdict(self):
        self.stills("sh01")
        with self.assertRaises(ValueError):                   # never reviewed
            rg.accept(self.clip, "sh01", "the owner likes it as it is")
        self.verdict("sh01", "fix", issues=["tie too large"])
        with self.assertRaises(ValueError):                   # no reason
            rg.accept(self.clip, "sh01", " ")
        st = rg.accept(self.clip, "sh01", "the owner likes the tie as it is", by="user in chat")
        self.assertEqual(st["status"], "accepted")
        self.assertTrue(st["ok"])
        rec = json.loads((self.clip / "review" / "sh01" / "accepted.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["open_issues"], ["tie too large"])

    def test_an_acceptance_dies_with_the_build(self):
        self.stills("sh01")
        self.verdict("sh01", "fix")
        rg.accept(self.clip, "sh01", "the owner accepts the open issue")
        w(self.clip / "blender" / "sh01.py", "HOLD = (4, 4)\n")
        self.stills("sh01")
        self.verdict("sh01", "fix")
        self.assertEqual(self.status("sh01"), "not_passed")

    def test_a_stale_verdict_cannot_be_accepted(self):
        self.stills("sh01")
        self.verdict("sh01", "restage")
        w(self.clip / "blender" / "sh01.py", "HOLD = (4, 4)\n")
        self.stills("sh01")
        with self.assertRaises(ValueError):
            rg.accept(self.clip, "sh01", "the owner accepts the open issue")


if __name__ == "__main__":
    unittest.main(verbosity=1)
