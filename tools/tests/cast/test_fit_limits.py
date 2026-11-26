"""The fit check's limits must stay exactly the pack's (vendored into tools/blender/ajkit, never loosened).

    py -3 -I tools/tests/cast/test_fit_limits.py

Two guards:
- recorded digests: the LIMITS dict and every constant of the vendored fitcheck, grips, fit_rigged and fit_costume
  hash to the values recorded here when they were vendored (works without the pack);
- pack originals: when packs/aj_rebuild_v1 is present, the vendored constants equal the originals' and fitcheck's
  code (without docstrings) is identical. Only path names and the new `arm=None` / `body=None` arguments may differ.
"""
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS / "chars_aj"))
sys.path.insert(0, str(TOOLS / "blender"))
import fit  # noqa: E402
from ajkit import paths  # noqa: E402

AJKIT = TOOLS / "blender" / "ajkit"
# recorded 2026-11-27 from the vendored files, which then matched the pack originals
RECORDED = {
    "LIMITS": "5f676bc55dc2365cfc273d5439b051a7236931c50aec8e584b2af4789eb40379",
}
VENDORED = {
    "fitcheck": (AJKIT / "fitcheck.py", paths.PACK_SCRIPTS / "fitcheck.py"),
    "grips": (AJKIT / "grips.py", paths.PACK_SCRIPTS / "grips.py"),
    "contacts": (AJKIT / "contacts.py", paths.PACK_SCRIPTS / "contacts.py"),
    "fit_rigged": (AJKIT / "fit_rigged.py", paths.PACK_DRESS_TEST / "fit_rigged.py"),
    "fit_costume": (AJKIT / "fit_costume.py", paths.PACK_DRESS_TEST / "fit_costume.py"),
}


class TestFitLimits(unittest.TestCase):
    def test_limits_digest_recorded(self):
        self.assertEqual(fit.limits_digest(), RECORDED["LIMITS"],
                         "fitcheck.LIMITS changed: the fit limits may never be loosened or edited")

    def test_limits_present(self):
        lim = fit._consts(AJKIT / "fitcheck.py").get("LIMITS")
        self.assertIsInstance(lim, dict)
        self.assertGreater(len(lim), 5)

    def test_constants_match_pack(self):
        found = 0
        for name, (ours, theirs) in VENDORED.items():
            if not ours.exists() or not theirs.exists():
                continue
            found += 1
            with self.subTest(module=name):
                a, b = fit._limits_only(fit._consts(ours)), fit._limits_only(fit._consts(theirs))
                diff = sorted(n for n in set(a) | set(b) if n not in a or n not in b or a[n] != b[n])
                self.assertEqual(diff, [], f"{name}: constants differ from the pack: {diff}")
        if found == 0:
            self.skipTest("the pack (packs/aj_rebuild_v1) is not here: only the recorded digest was checked")

    def test_fitcheck_code_matches_pack(self):
        ours, theirs = VENDORED["fitcheck"]
        if not theirs.exists():
            self.skipTest("the pack is not here")
        self.assertEqual(fit._code(ours), fit._code(theirs), "fitcheck.py's code differs from the pack's")

    def test_limit_report_agrees(self):
        rep = fit.limit_report()
        for k, e in rep.items():
            if isinstance(e, dict) and "constants_match_pack" in e:
                with self.subTest(module=k):
                    self.assertTrue(e["constants_match_pack"], e.get("differences"))
                    self.assertEqual(e["differences"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
