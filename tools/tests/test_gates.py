"""Tests for the approval gates (tools/gates.py and the clip.py commands that use them).

    py -3 -I tools/tests/test_gates.py

Everything runs in a temporary folder with small fake plan, set and shot files; nothing under output/ is touched.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import gates  # noqa: E402

PLAN = {
    "world": {"era": "modern", "place": "laundromat"},
    "cast": [{"id": "worker", "base": "Aj_Male_Adult", "costume": {"wear": ["apron"]}}],
    "sets": [{"id": "laundromat", "description": "a long room"}],
    "shots": [{"id": "sh01", "set": "laundromat"}],
}


def w(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old_root = gates.ROOT
        gates.ROOT = self.root
        w(self.root / "config" / "cast.json", json.dumps({"characters": {"Aj_Male_Adult": {"looks": "tall"}}}))
        w(self.root / "library" / "wardrobe" / "index.json", json.dumps({"items": {"apron": {"colour": "red"}}}))
        self.clip = self.root / "output" / "clips" / "demo"
        w(self.clip / "shotplan.json", json.dumps(PLAN))
        w(self.clip / "timing.json", json.dumps({"total_frames": 10, "total_seconds": 0.4, "source": "mock", "shots": {}}))
        w(self.clip / "blender" / "set_laundromat.py", "# set\n")
        w(self.clip / "blender" / "sh01.py", "# shot\n")

    def tearDown(self):
        gates.ROOT = self._old_root
        self._tmp.cleanup()

    def fps(self):
        return {g: gates.fingerprint(self.clip, g) for g in gates.GATES}

    def show_and_approve(self, g):
        gates.mark_ready(self.clip, g, [f"{g}.png"])
        gates.approve(self.clip, g, by="user in chat")

    def approve_all(self):
        for g in gates.GATES:
            self.show_and_approve(g)


class Fingerprints(Base):
    def test_only_the_changed_gate_moves(self):
        base = self.fps()
        w(self.clip / "blender" / "sh01.py", "# shot v2\n")
        now = self.fps()
        self.assertEqual((now["A"], now["B"]), (base["A"], base["B"]))
        self.assertNotEqual(now["C"], base["C"])
        base = now
        w(self.clip / "blender" / "set_laundromat.py", "# set v2\n")
        now = self.fps()
        self.assertNotEqual(now["B"], base["B"])
        self.assertEqual((now["A"], now["C"]), (base["A"], base["C"]))
        base = now
        plan = dict(PLAN, cast=[dict(PLAN["cast"][0], costume={"wear": ["apron"], "recolor": {"x": "#fff"}})])
        w(self.clip / "shotplan.json", json.dumps(plan))
        now = self.fps()
        self.assertNotEqual(now["A"], base["A"])
        self.assertEqual((now["B"], now["C"]), (base["B"], base["C"]))

    def test_plan_shot_edit_touches_nothing(self):
        base = self.fps()
        w(self.clip / "shotplan.json", json.dumps(dict(PLAN, shots=[{"id": "sh01", "set": "laundromat", "views": []}])))
        self.assertEqual(self.fps(), base)

    def test_sets_section_moves_only_b(self):
        base = self.fps()
        w(self.clip / "shotplan.json", json.dumps(dict(PLAN, sets=[{"id": "laundromat", "description": "bigger"}])))
        now = self.fps()
        self.assertNotEqual(now["B"], base["B"])
        self.assertEqual((now["A"], now["C"]), (base["A"], base["C"]))

    def test_registry_and_wardrobe_entries_move_a_only(self):
        base = self.fps()
        w(self.root / "library" / "wardrobe" / "index.json", json.dumps({"items": {"apron": {"colour": "blue"}, "hat": {}}}))
        now = self.fps()
        self.assertNotEqual(now["A"], base["A"])
        self.assertEqual((now["B"], now["C"]), (base["B"], base["C"]))
        base = now
        w(self.root / "config" / "cast.json", json.dumps({"characters": {"Aj_Male_Adult": {"looks": "short"}, "Other": {}}}))
        self.assertNotEqual(self.fps()["A"], base["A"])

    def test_missing_registries_and_casting_are_fine(self):
        (self.root / "config" / "cast.json").unlink()
        (self.root / "library" / "wardrobe" / "index.json").unlink()
        a = gates.fingerprint(self.clip, "A")
        w(self.clip / "casting.json", "{}")
        self.assertNotEqual(gates.fingerprint(self.clip, "A"), a)

    def test_timing_is_camera(self):
        base = self.fps()
        w(self.clip / "timing.json", json.dumps({"total_frames": 11, "total_seconds": 0.5, "source": "mock", "shots": {}}))
        self.assertNotEqual(self.fps()["C"], base["C"])


class Decisions(Base):
    def test_approve_needs_previews(self):
        with self.assertRaises(gates.GateError):
            gates.approve(self.clip, "A")
        gates.approve(self.clip, "A", no_previews=True)
        self.assertEqual(gates.status(self.clip)["gates"]["A"]["status"], "approved")

    def test_approve_refused_when_previews_are_for_older_inputs(self):
        gates.mark_ready(self.clip, "C", ["c.mp4"])
        w(self.clip / "blender" / "sh01.py", "# changed\n")
        with self.assertRaises(gates.GateError):
            gates.approve(self.clip, "C")

    def test_edit_makes_only_that_gate_stale(self):
        self.approve_all()
        self.assertIsNone(gates.next_decision(self.clip))
        w(self.clip / "blender" / "sh01.py", "# shot v2\n")
        s = gates.status(self.clip)["gates"]
        self.assertTrue(s["C"]["stale"])
        self.assertFalse(s["A"]["stale"] or s["B"]["stale"])
        self.assertEqual((s["A"]["status"], s["B"]["status"]), ("approved", "approved"))
        self.assertEqual(s["C"]["changed"], ["blender/sh01.py"])
        self.assertEqual(gates.next_decision(self.clip), "C")

    def test_revise_stores_notes_and_counts_rounds(self):
        gates.request_changes(self.clip, "A", ["hair darker", "longer coat"])
        g = gates.status(self.clip)["gates"]["A"]
        self.assertEqual((g["status"], g["notes"], g["round"]), ("changes_requested", ["hair darker", "longer coat"], 1))
        gates.request_changes(self.clip, "A", "no hat")
        self.assertEqual(gates.status(self.clip)["gates"]["A"]["round"], 2)
        self.assertEqual(gates.next_decision(self.clip), "A")

    def test_history_is_append_only(self):
        gates.mark_ready(self.clip, "A", ["a.png"])
        gates.request_changes(self.clip, "A", "x")
        h1 = gates.load(self.clip)["history"]
        gates.mark_ready(self.clip, "A", ["a2.png"])
        gates.approve(self.clip, "A")
        h2 = gates.load(self.clip)["history"]
        self.assertEqual(h2[:len(h1)], h1)
        self.assertEqual([e["action"] for e in h2], ["ready", "changes_requested", "ready", "approved"])
        self.assertTrue(all(e["time"] for e in h2))

    def test_file_shape(self):
        gates.mark_ready(self.clip, "A", ["a.png"])
        doc = json.loads((self.clip / "approvals.json").read_text(encoding="utf-8"))
        self.assertEqual((doc["version"], doc["mode"]), (1, "interactive"))
        self.assertEqual(set(doc["gates"]), {"A", "B", "C"})
        for k in ("status", "fingerprint", "decided_at", "decided_by", "notes", "previews", "round"):
            self.assertIn(k, doc["gates"]["A"])
        self.assertEqual([p.name for p in self.clip.glob("approvals.json*")], ["approvals.json"])


class Requirements(unittest.TestCase):
    def test_table(self):
        r = gates.requirements
        self.assertEqual(r("stills"), {"A", "B"})
        self.assertEqual(r("render", "draft"), {"A", "B"})
        self.assertEqual(r("render", "preview"), {"A", "B"})
        self.assertEqual(r("render", "final"), {"A", "B", "C"})
        self.assertEqual(r("assemble"), {"A", "B", "C"})
        self.assertEqual(r("assemble", tag="animatic"), {"A", "B"})
        self.assertEqual(r("assemble", quality="draft"), {"A", "B"})
        self.assertEqual(r("voice"), set())


class Enforcement(Base):
    def test_interactive_blocks_then_passes(self):
        ok, problems = gates.check(self.clip, "stills", "draft")
        self.assertFalse(ok)
        self.assertEqual(len(problems), 2)
        self.assertIn("Gate A", problems[0])
        self.assertIn("clip.py gate demo A", problems[0])
        self.show_and_approve("A")
        self.show_and_approve("B")
        self.assertEqual(gates.check(self.clip, "stills", "draft"), (True, []))
        ok, problems = gates.check(self.clip, "render", "final")
        self.assertFalse(ok)
        self.assertIn("Gate C", problems[0])
        self.show_and_approve("C")
        self.assertTrue(gates.check(self.clip, "render", "final")[0])
        self.assertTrue(gates.check(self.clip, "assemble")[0])

    def test_stale_blocks_with_changed_path(self):
        self.approve_all()
        w(self.clip / "blender" / "set_laundromat.py", "# edited\n")
        ok, problems = gates.check(self.clip, "stills")
        self.assertFalse(ok)
        self.assertIn("STALE", problems[0])
        self.assertIn("set_laundromat.py", problems[0])

    def test_animatic_assemble_needs_only_a_and_b(self):
        self.show_and_approve("A")
        self.show_and_approve("B")
        self.assertTrue(gates.check(self.clip, "assemble", tag="animatic")[0])
        self.assertTrue(gates.check(self.clip, "assemble", quality="draft")[0])
        self.assertFalse(gates.check(self.clip, "assemble")[0])

    def test_changes_requested_blocks_and_says_what(self):
        gates.request_changes(self.clip, "A", "make the hair darker")
        ok, problems = gates.check(self.clip, "stills")
        self.assertFalse(ok)
        self.assertIn("make the hair darker", problems[0])

    def test_autonomous_never_blocks_and_never_approves(self):
        self.assertRaises(gates.GateError, gates.set_mode, self.clip, "autonomous", "")
        gates.set_mode(self.clip, "autonomous", "owner asked for an unattended run")
        ok, problems = gates.check(self.clip, "render", "final")
        self.assertEqual((ok, problems), (True, []))
        s = gates.status(self.clip)["gates"]
        for g in gates.GATES:
            self.assertEqual(s[g]["status"], "bypassed")
            self.assertFalse(s[g]["approved"])
            self.assertEqual(s[g]["notes"], "owner asked for an unattended run")
        self.assertNotIn("approved", [e["action"] for e in gates.load(self.clip)["history"]])
        self.assertIsNone(gates.next_decision(self.clip))
        n = len(gates.load(self.clip)["history"])
        gates.check(self.clip, "render", "final")                     # nothing changed: no new records
        self.assertEqual(len(gates.load(self.clip)["history"]), n)
        fp = gates.load(self.clip)["gates"]["C"]["fingerprint"]
        w(self.clip / "blender" / "sh01.py", "# changed\n")           # inputs changed: recorded again
        self.assertTrue(gates.check(self.clip, "render", "final")[0])
        c = gates.load(self.clip)["gates"]["C"]
        self.assertEqual(c["status"], "bypassed")
        self.assertNotEqual(c["fingerprint"], fp)
        self.assertEqual(c["fingerprint"], gates.fingerprint(self.clip, "C"))
        self.assertGreater(len(gates.load(self.clip)["history"]), n)

    def test_autonomous_keeps_a_real_approval(self):
        self.show_and_approve("A")
        gates.set_mode(self.clip, "autonomous", "unattended")
        gates.check(self.clip, "stills")
        s = gates.status(self.clip)["gates"]
        self.assertEqual((s["A"]["status"], s["B"]["status"]), ("approved", "bypassed"))

    def test_back_to_interactive_blocks_bypassed(self):
        gates.set_mode(self.clip, "autonomous", "unattended")
        gates.check(self.clip, "render", "final")
        gates.set_mode(self.clip, "interactive")
        ok, problems = gates.check(self.clip, "stills")
        self.assertFalse(ok)
        self.assertEqual(len(problems), 2)
        self.assertEqual(gates.next_decision(self.clip), "A")
        self.assertEqual(gates.load(self.clip)["mode_reason"], None)


class Cli(Base):
    """clip.py commands, run in-process against the temporary clip."""

    def setUp(self):
        super().setUp()
        import clip
        self.clip_mod = clip
        w(self.clip / "script.json", "{}")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        old = sys.argv
        sys.argv = ["clip.py", *argv]
        code = 0
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = self.clip_mod.main() or 0
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 1
        finally:
            sys.argv = old
        return code, out.getvalue(), err.getvalue()

    def test_stills_and_render_exit_4(self):
        for argv in (("stills", str(self.clip)), ("render", str(self.clip)), ("render", str(self.clip), "--quality", "draft")):
            code, _, err = self.run_cli(*argv)
            self.assertEqual(code, 4, argv)
            self.assertIn("Gate A", err)
            self.assertIn("clip.py gate demo A", err)

    def test_assemble_exit_4_and_animatic_gate_set(self):
        code, _, err = self.run_cli("assemble", str(self.clip))
        self.assertEqual(code, 4)
        self.assertIn("Gate C", err)
        code, _, err = self.run_cli("assemble", str(self.clip), "--tag", "animatic")
        self.assertEqual(code, 4)
        self.assertNotIn("Gate C", err)

    def test_gate_commands(self):
        c = str(self.clip)
        code, out, _ = self.run_cli("gate", c, "A", "--approve")
        self.assertEqual(code, 2)                                      # nothing shown yet
        code, out, _ = self.run_cli("gate", c, "A", "--ready", "--previews", "a.png", "b.png")
        self.assertEqual(code, 0)
        self.assertIn("preview: a.png", out)
        code, out, _ = self.run_cli("gate", c, "A", "--approve", "--by", "user in chat", "--notes", "looks good")
        self.assertIn("approved", out)
        code, out, _ = self.run_cli("gate", c, "B", "--revise", "more props", "--revise", "warmer light")
        self.assertIn("more props; warmer light", out)
        code, out, _ = self.run_cli("gate", c, "--json")
        doc = json.loads(out)
        self.assertEqual(doc["gates"]["A"]["status"], "approved")
        self.assertEqual(doc["gates"]["B"]["round"], 1)
        self.assertEqual(doc["next_decision"], "B")
        code, _, err = self.run_cli("gate", c, "--autonomous")
        self.assertEqual(code, 2)
        code, out, _ = self.run_cli("gate", c, "--autonomous", "--reason", "owner asked")
        self.assertEqual(code, 0)

    def test_preview_tools_not_installed_message(self):
        for name in ("cast-sheets", "setpreview", "preview"):
            script = self.clip_mod.GATE_TOOLS[{"cast-sheets": "A", "setpreview": "B", "preview": "C"}[name]][1]
            if script.exists():
                continue                                               # another agent has installed it: not testable here
            code, _, err = self.run_cli(name, str(self.clip))
            self.assertEqual(code, 5)
            self.assertIn("not installed yet", err)

    def test_status_without_script_json(self):
        (self.clip / "script.json").unlink()
        code, out, _ = self.run_cli("status", str(self.clip))
        self.assertEqual(code, 0)
        self.assertIn("gate A", out)
        self.assertIn("script.json is missing", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
