"""Plain-Python checks of the Mixamo clip registry and its CLI (no Blender):  py -3 tools/chars_aj/test_clips.py

- every registry entry names a file, a Mixamo title and how to download it, and is analysed
- the ask text gives the search, the settings and the target path
- scan() finds the clips a clip folder needs from shot code (.do, walk(cycle=), play_clip) and a plan's do lists
- --need exits 2 and lists the ask when a needed clip is not on disk, 0 when everything is there
The registry is copied to a temporary project so nothing under config/ or library/ is touched."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]


def load_mod(project: Path):
    os.environ["SHORTS_PROJECT"] = str(project)
    import importlib.util
    spec = importlib.util.spec_from_file_location("clips_under_test", HERE.parent / "clips.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Registry(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ajclips_"))
        (self.tmp / "config").mkdir()
        shutil.copy(ROOT / "config" / "mixamo_clips.json", self.tmp / "config" / "mixamo_clips.json")
        self.reg = json.loads((self.tmp / "config" / "mixamo_clips.json").read_text(encoding="utf-8"))
        self.clipdir = self.tmp / self.reg.get("dir", "library/characters/aj/mixamo")
        self.clipdir.mkdir(parents=True)
        self.m = load_mod(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ["SHORTS_PROJECT"] = str(ROOT)

    def test_entries_complete(self):
        for name, c in self.reg["clips"].items():
            for k in ("file", "mixamo_title", "kind", "in_place", "loop", "actions"):
                self.assertIn(k, c, f"{name} has no {k}")
            self.assertTrue(c.get("analysis"), f"{name} is not analysed (run clips.py --register)")
            self.assertTrue(c.get("sha256"), f"{name} has no sha256")

    def test_ask(self):
        t = self.m.ask("Standard_Walk", self.reg)
        self.assertIn(self.reg["clips"]["Standard_Walk"]["mixamo_title"], t)
        self.assertIn("Without Skin", t)
        self.assertIn("30", t)
        self.assertIn("Standard_Walk", t)
        self.assertIn("--register", t)

    def make_clip_folder(self, code: str, plan=None) -> Path:
        d = self.tmp / "output" / "clips" / "demo"
        (d / "blender").mkdir(parents=True)
        (d / "blender" / "sh01.py").write_text(code, encoding="utf-8")
        if plan:
            (d / "shotplan.json").write_text(json.dumps(plan), encoding="utf-8")
        return d

    def test_scan_and_report(self):
        d = self.make_clip_folder('a.do("sit_down", t=1)\nb.walk(2, (1, 0), cycle="run")\nc.play_clip("Salute", 3)\n',
                                  {"shots": [{"id": "sh02", "do": [{"action": "kneel"}]}]})
        r = self.m.scan(d, self.reg)
        for c in ("Stand_To_Sit", "Standard_Run", "Standing_Idle", "Salute", "Kneeling_Down"):
            self.assertIn(c, r["required"], c)
        self.assertEqual(set(r["missing"]), set(r["required"]))          # nothing is on disk in the temp project
        md = self.m.missing_report(d, "Stand_To_Sit", None, self.reg)
        self.assertIn("## Stand_To_Sit", md)
        self.assertIn("Needed by: sh01.py", md)

    def test_need_exit_codes(self):
        d = self.make_clip_folder('a.do("salute", t=1)\n')
        env = dict(os.environ, SHORTS_PROJECT=str(self.tmp))
        r = subprocess.run([sys.executable, str(HERE.parent / "clips.py"), "--need", str(d)], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("MISSING", r.stdout)
        (self.clipdir / self.reg["clips"]["Salute"]["file"]).write_bytes(b"x")
        r = subprocess.run([sys.executable, str(HERE.parent / "clips.py"), "--need", str(d)], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
