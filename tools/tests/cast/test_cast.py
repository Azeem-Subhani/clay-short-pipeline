"""Tests for the casting side: cast_data rules, plan.check_cast, casting.py (standard library only).

    py -3 -I tools/tests/cast/test_cast.py

The rules are tested on a small synthetic registry (so they do not move when the real wardrobe grows), plus a few checks on the real
config/cast.json: every starter passes `cast_registry.check`.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import cast_data as cd  # noqa: E402
import casting  # noqa: E402
import plan as plan_mod  # noqa: E402

FACE = "Teen Classic"


def fit(status="pass", review="accept", file="library/wardrobe/fits/x.blend"):
    return {"status": status, "review": review, "file": file}


WARD = {
    "outfits": {
        "polo": {"era": ["modern"], "licence": "royalty_free", "tags": ["casual", "shirt"], "title": "Polo and jeans",
                 "pieces": {"D_jeans": {"slot": "bottom", "palette_slot": "secondary"}, "D_polo": {"slot": "top", "palette_slot": "primary"}},
                 "fits": {"Male_Teen": fit(), "Male_Senior": fit(), "Female_Adult": fit(review="reject"), "Male_Adult": fit("fail", "none", None)}},
        "tunic": {"era": ["medieval"], "licence": "cc0", "tags": ["tunic", "medieval"], "title": "Tunic",
                  "pieces": {"D_Tunic": {"slot": "top", "palette_slot": "primary"}, "D_Hose": {"slot": "bottom", "palette_slot": "secondary"}},
                  "fits": {"Female_Adult": fit()}},
        "stolen": {"era": ["modern"], "licence": "unknown", "pieces": {"D_x": {"slot": "top", "palette_slot": "primary"}}, "fits": {"Male_Teen": fit()}},
    },
    "addons": {
        "crown": {"era": ["medieval", "fantasy"], "licence": "royalty_free", "kind": "rigid", "bone": "Head", "tags": ["royal", "gold"], "palette_slot": "accent",
                  "fits": {"Female_Adult": fit(review="none")}},
        "apron": {"era": ["any"], "licence": "cc0", "kind": "skinned", "covers": ["top"], "palette_slot": "accent", "fits": {"Male_Teen": fit()}},
    },
}
REG = {
    "eras": {"modern": "", "medieval": "", "fantasy": ""},
    "bodies": {b: {} for b in ("Male_Kid", "Male_Teen", "Male_Adult", "Male_Senior", "Female_Kid", "Female_Teen", "Female_Adult", "Female_Senior")},
    "aliases": {"TeenBoy": "Tom"},
    "characters": {
        "Tom": {"family": "aj", "body": "Male_Teen", "face": FACE, "hair": {"style": "male_spiky", "color": "#222222"}, "facial_hair": None,
                "outfit": "polo", "addons": [], "palette": {"primary": "#C0392B"}, "era": ["modern"], "looks": "teenage boy, spiky hair, red polo", "status": "draft"},
    },
}
HAIR = {"hair": {s: {} for s in ("male_spiky", "male_short_tidy", "male_balding_ring", "female_long_straight", "female_bun_updo", "kid_bowl_cut")},
        "facial": {"facial_beard_short": {}, "facial_moustache_classic": {}}}


def patched(**over):
    """Make cast_data (and so plan and casting) read the synthetic registry."""
    reg = copy.deepcopy(over.get("reg", REG))
    ward = copy.deepcopy(over.get("ward", WARD))
    cd.cast, cd.wardrobe, cd.hair_index = (lambda: reg), (lambda: ward), (lambda: HAIR)
    plan_mod._registry = lambda: reg


class Rules(unittest.TestCase):
    def setUp(self):
        patched()

    def test_resolve(self):
        self.assertEqual(cd.resolve(REG, "TeenBoy")[0], "Tom")
        self.assertEqual(cd.resolve(REG, "Aj_Male_Teen")[2], "Male_Teen")
        self.assertEqual(cd.resolve(REG, "Male_Teen")[2], "Male_Teen")
        self.assertEqual(cd.resolve(REG, "Nobody")[1:], (None, None))

    def test_fit_rules(self):
        self.assertIsNone(cd.outfit_check(WARD, "polo", "Male_Teen"))
        self.assertIn("not fit-accepted", cd.outfit_check(WARD, "polo", "Female_Adult"))       # reviewer rejected
        self.assertIn("not fit-accepted", cd.outfit_check(WARD, "polo", "Male_Adult"))         # failed the check
        self.assertIn("licence", cd.outfit_check(WARD, "stolen", "Male_Teen"))
        self.assertIn("no outfit", cd.outfit_check(WARD, "nope", "Male_Teen"))
        self.assertIsNone(cd.addon_check(WARD, "crown", "Female_Adult"))                       # a rigid add-on may have review none
        self.assertIn("not fit-accepted", cd.addon_check(WARD, "crown", "Male_Teen"))
        self.assertNotIn("stolen", cd.accepted_outfits(WARD, "Male_Teen"))

    def test_costume_checks(self):
        ch = REG["characters"]["Tom"]
        ok = cd.check_costume(REG, WARD, ch, {"recolor": {"primary": "#fff", "hair": "#000", "skin": "#c58f63"}, "hide": ["hair"]}, "modern", "t", "Tom")
        self.assertEqual(ok, [])
        bad = cd.check_costume(REG, WARD, ch, {"recolor": {"collar": "#fff"}}, "modern", "t", "Tom")
        self.assertTrue(any("no colour slot 'collar'" in e for e in bad))
        bad = cd.check_costume(REG, WARD, ch, {"hide": ["cape"]}, "modern", "t", "Tom")
        self.assertTrue(any("matches nothing" in e for e in bad))
        era = cd.check_costume(REG, WARD, ch, None, "medieval", "t", "Tom")
        self.assertTrue(any("belongs to ['modern']" in e for e in era))

    def test_no_bare_body(self):
        ch = REG["characters"]["Tom"]
        e = cd.check_costume(REG, WARD, ch, {"hide": ["polo"]}, "modern", "t", "Tom")
        self.assertTrue(any("bare" in x and "'top'" in x for x in e), e)
        e = cd.check_costume(REG, WARD, ch, {"hide": ["jeans_shirt.jeans"]}, "modern", "t", "Tom")      # unknown outfit label: matches nothing
        self.assertTrue(any("matches nothing" in x for x in e))
        e = cd.check_costume(REG, WARD, ch, {"hide": ["polo.jeans"]}, "modern", "t", "Tom")           # '<outfit>.<piece>' is a real label
        self.assertTrue(any("bare" in x and "'bottom'" in x for x in e), e)
        e = cd.check_costume(REG, WARD, ch, {"wear": [{"item": "apron"}], "hide": ["polo"]}, "modern", "t", "Tom")   # the apron covers the top
        self.assertEqual(e, [])
        e = cd.check_costume(REG, WARD, ch, {"wear": [{"item": "apron"}], "hide": ["polo", "addon:apron"]}, "modern", "t", "Tom")
        self.assertTrue(any("bare" in x for x in e), e)
        e = cd.check_costume(REG, WARD, ch, {"wear": [{"item": "cape"}]}, "modern", "t", "Tom")
        self.assertTrue(any("no add-on 'cape'" in x for x in e))

    def test_character_check(self):
        ch = copy.deepcopy(REG["characters"]["Tom"])
        self.assertEqual(cd.check_character(REG, WARD, HAIR, "Tom", ch), [])
        ch["outfit"] = "tunic"
        self.assertTrue(cd.check_character(REG, WARD, HAIR, "Tom", ch))
        ch = copy.deepcopy(REG["characters"]["Tom"])
        ch["hair"]["style"] = "male_mohawk"
        ch["palette"] = {"tertiary": "#fff"}
        errs = cd.check_character(REG, WARD, HAIR, "Tom", ch)
        self.assertTrue(any("male_mohawk" in e for e in errs) and any("tertiary" in e for e in errs))


class PlanCast(unittest.TestCase):
    def setUp(self):
        patched()

    def run_check(self, cast, era="modern"):
        err, warn = [], []
        plan_mod.check_cast({"world": {"era": era}, "cast": cast}, err, warn)
        return err, warn

    def test_ok_with_draft_warning(self):
        err, warn = self.run_check([{"id": "a", "base": "Tom", "role": "boy", "reads_as": "red"}])
        self.assertEqual(err, [])
        self.assertTrue(any("draft" in w and "Gate A" in w for w in warn))

    def test_old_name_warns(self):
        err, warn = self.run_check([{"id": "a", "base": "TeenBoy", "role": "boy", "reads_as": "red"}])
        self.assertEqual(err, [])
        self.assertTrue(any("old name" in w for w in warn))

    def test_unknown_base_and_bare_body(self):
        err, _ = self.run_check([{"id": "a", "base": "KingActor", "role": "king", "reads_as": "x"}])
        self.assertTrue(any("not a registered character" in e and "casting" in e for e in err))
        err, warn = self.run_check([{"id": "a", "base": "Male_Teen", "role": "boy", "reads_as": "x"}])
        self.assertEqual(err, [])
        self.assertTrue(any("bare body" in w for w in warn))
        err, _ = self.run_check([{"id": "a", "base": "Male_Teen", "role": "boy", "reads_as": "x", "costume": {"hide": ["hair"]}}])
        self.assertTrue(any("bare body has no clothes" in e for e in err))

    def test_era_and_costume_errors(self):
        err, _ = self.run_check([{"id": "a", "base": "Tom", "role": "boy", "reads_as": "x"}], era="medieval")
        self.assertTrue(any("not to a medieval story" in e for e in err))
        err, _ = self.run_check([{"id": "a", "base": "Tom", "role": "boy", "reads_as": "x", "costume": {"recolor": {"bogus": "#fff"}}}])
        self.assertTrue(any("bogus" in e for e in err))

    def test_seat_limit_warns_on_sit_actions(self):
        reg = copy.deepcopy(REG)
        reg["characters"]["Tom"]["avoid"] = ["Seated seen from behind: the hem makes a bag over the seat.", "Keep feet out of close-ups."]
        patched(reg=reg)
        plan = {"world": {"era": "modern"}, "cast": [{"id": "a", "base": "Tom", "role": "boy", "reads_as": "x"}],
                "shots": [{"id": "s1", "do": [{"who": "a", "action": "sit_down"}, {"who": "a", "action": "wave"}]},
                          {"id": "s2", "do": [{"who": "a", "action": "sit_idle"}]}, {"id": "s3", "do": [{"who": "a", "action": "walk"}]}]}
        err, warn = [], []
        plan_mod.check_cast(plan, err, warn)
        seat = [w for w in warn if "reviewed limits" in w]
        self.assertEqual(err, [])
        self.assertEqual(len(seat), 2, warn)
        self.assertTrue(seat[0].startswith("s1:") and "sit_down" in seat[0] and "bag over the seat" in seat[0])
        self.assertTrue(seat[1].startswith("s2:") and "sit_idle" in seat[1])
        self.assertFalse(any("feet" in w for w in seat))                 # only the limits that mention seating are quoted
        reg["characters"]["Tom"]["avoid"] = ["Keep feet out of close-ups."]
        patched(reg=reg)
        err, warn = [], []
        plan_mod.check_cast(plan, err, warn)
        self.assertFalse(any("reviewed limits" in w for w in warn))

    def test_wants_shape(self):
        err, _ = self.run_check([{"id": "a", "base": "Tom", "role": "boy", "reads_as": "x", "wants": {"sex": "Boy", "age": "Old"}}])
        self.assertEqual(sum("wants." in e for e in err), 2)
        err, _ = self.run_check([{"id": "a", "base": "Tom", "reads_as": "x"}])
        self.assertTrue(any("missing 'role'" in e for e in err))


class Casting(unittest.TestCase):
    def setUp(self):
        patched()
        self.tmp = Path(tempfile.mkdtemp())

    def clip(self, cast, era="modern", script=True):
        d = Path(tempfile.mkdtemp())
        (d / "shotplan.json").write_text(json.dumps({"world": {"era": era}, "cast": cast, "shots": []}), encoding="utf-8")
        if script:
            (d / "script.json").write_text(json.dumps({"title": "t", "beats": []}), encoding="utf-8")
        return d

    def results(self, cast, era="modern"):
        casting.animations = lambda clip: {"checked": False, "note": "test"}
        out, code = casting.run(self.clip(cast, era))
        return {r["id"]: r for r in out["results"]}, code

    def test_existing(self):
        r, code = self.results([{"id": "a", "base": "Tom", "role": "a boy"}])
        self.assertEqual(r["a"]["status"], "EXISTING")
        self.assertEqual(code, 0)

    def test_avoid_is_copied(self):
        reg = copy.deepcopy(REG)
        reg["characters"]["Tom"]["avoid"] = ["Do not seat this character seen from behind."]
        ward = copy.deepcopy(WARD)
        ward["outfits"]["polo"]["fits"]["Male_Senior"]["avoid"] = ["Never seat close up."]
        ward["addons"]["apron"]["fits"]["Male_Teen"]["avoid"] = ["Apron strings fold when seated."]
        patched(reg=reg, ward=ward)
        r, _ = self.results([{"id": "a", "base": "Tom", "role": "a boy"}])
        self.assertEqual(r["a"]["avoid"], ["Do not seat this character seen from behind."])           # a registered character: its own list
        d = self.clip([{"id": "a", "base": "Tom", "role": "a boy"}])
        out, _ = casting.run(d)
        (d / "casting.json").write_text(json.dumps(out), encoding="utf-8")
        (d / "casting.md").write_text(casting.markdown(out), encoding="utf-8")
        self.assertIn("AVOID: Do not seat this character seen from behind.", (d / "casting.md").read_text(encoding="utf-8"))
        self.assertEqual(cd.avoid_union(ward, "Male_Teen", "polo", [{"item": "apron"}]), ["Apron strings fold when seated."])
        self.assertEqual(cd.avoid_union(ward, "Male_Senior", "polo", []), ["Never seat close up."])
        self.assertEqual(cd.seat_limits(["Never seat close up.", "Keep feet out.", "Seated at the back."]), ["Never seat close up.", "Seated at the back."])

    def test_inference_and_adapt(self):
        w = casting.effective_wants({"id": "gran", "role": "the old grandmother", "base": "x"}, REG, "modern")
        self.assertEqual((w["sex"], w["age"]), ("Female", "Senior"))
        w = casting.effective_wants({"id": "k", "role": "a little girl", "base": "x"}, REG, "modern")
        self.assertEqual((w["sex"], w["age"]), ("Female", "Kid"))
        w = casting.effective_wants({"id": "q", "role": "x", "base": "x", "wants": {"sex": "Female", "age": "Teen", "tags": ["Armor"]}}, REG, "modern")
        self.assertEqual(w["tags"], ["armour"])
        # Male_Senior can wear the polo: ADAPT with the exact delta
        r, code = self.results([{"id": "gramps", "base": "Nobody", "role": "the old grandfather", "wants": {"palette_hint": ["teal", "#112233"], "hair": "balding"}}])
        a = r["gramps"]["adapt"]
        self.assertEqual(r["gramps"]["status"], "ADAPT")
        self.assertEqual((a["body"], a["outfit"]), ("Male_Senior", "polo"))
        self.assertEqual(a["hair"]["style"], "male_balding_ring")
        self.assertEqual(a["palette"], {"primary": casting.COLOUR_NAMES["teal"], "secondary": "#112233"})
        self.assertEqual(code, 0)

    def test_missing_asks(self):
        r, code = self.results([{"id": "king", "base": "Nobody", "role": "the king, a man", "wants": {"sex": "Male", "age": "Adult", "era": "medieval", "tags": ["tunic", "crown"]}}])
        self.assertEqual(r["king"]["status"], "MISSING")
        self.assertEqual(code, 2)
        kinds = {m["kind"] for m in r["king"]["missing"]}
        self.assertEqual(kinds, {"outfit", "addon"})
        self.assertTrue(all("Male_Adult" in m["ask"] for m in r["king"]["missing"]))
        self.assertTrue(any("CC0 or Royalty Free" in m["ask"] for m in r["king"]["missing"]))
        # a queen CAN be dressed: the tunic is accepted on Female_Adult and so is the crown
        r, code = self.results([{"id": "queen", "base": "Nobody", "role": "the queen", "wants": {"era": "medieval", "tags": ["tunic", "crown"], "age": "Adult"}}])
        self.assertEqual(r["queen"]["status"], "ADAPT", r["queen"])
        self.assertEqual([x["item"] for x in r["queen"]["adapt"]["addons"]], ["crown"])
        self.assertEqual(r["queen"]["adapt"]["outfit"], "tunic")

    def test_unspecified_person_is_missing(self):
        r, code = self.results([{"id": "x", "base": "Nobody", "role": "a stranger"}])
        self.assertEqual(r["x"]["status"], "MISSING")
        self.assertEqual(r["x"]["missing"][0]["kind"], "spec")

    def test_unknown_hair_is_missing(self):
        r, _ = self.results([{"id": "m", "base": "Nobody", "role": "a man", "wants": {"sex": "Male", "age": "Senior", "hair": "mohawk"}}])
        self.assertEqual(r["m"]["status"], "MISSING")
        self.assertEqual(r["m"]["missing"][0]["kind"], "hair")

    def test_same_input_same_bytes(self):
        casting.animations = lambda clip: {"checked": False, "note": "test"}
        cast = [{"id": "a", "base": "Tom", "role": "a boy"}, {"id": "g", "base": "Nobody", "role": "the old grandfather"},
                {"id": "k", "base": "Nobody", "role": "the king, a man", "wants": {"sex": "Male", "age": "Adult", "era": "medieval", "tags": ["tunic"]}}]
        d = self.clip(cast)
        outs = []
        for _ in range(3):
            out, _c = casting.run(d)
            outs.append(json.dumps(out, sort_keys=True) + casting.markdown(out))
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(outs[1], outs[2])

    def test_apply_registers_and_rewrites(self):
        casting.animations = lambda clip: {"checked": False, "note": "test"}
        d = self.clip([{"id": "g", "base": "Nobody", "role": "the old grandfather"}])
        reg_file = Path(tempfile.mkdtemp()) / "cast.json"
        reg_file.write_text(json.dumps(REG), encoding="utf-8")
        real_root = casting.ROOT
        try:
            casting.ROOT = reg_file.parent.parent                    # apply_casting writes <ROOT>/config/cast.json
            (casting.ROOT / "config").mkdir(exist_ok=True)
            (casting.ROOT / "config" / "cast.json").write_text(json.dumps(REG), encoding="utf-8")
            out, code = casting.run(d, apply=True)
            reg2 = json.loads((casting.ROOT / "config" / "cast.json").read_text(encoding="utf-8"))
        finally:
            casting.ROOT = real_root
        name = out["results"][0]["character"]
        self.assertIn(name, reg2["characters"])
        self.assertEqual(reg2["characters"][name]["status"], "draft")
        self.assertEqual(json.loads((d / "shotplan.json").read_text(encoding="utf-8"))["cast"][0]["base"], name)


class RealRegistry(unittest.TestCase):
    def test_starters_pass_the_registry_check(self):
        import importlib
        importlib.reload(cd)
        reg, ward, hair = cd.cast(), cd.wardrobe(), cd.hair_index()
        self.assertGreaterEqual(len(reg["characters"]), 14)
        for name, ch in reg["characters"].items():
            self.assertEqual(cd.check_character(reg, ward, hair, name, ch), [], name)
            self.assertEqual(ch["status"], "draft")
            for e in ch["era"]:
                self.assertIn(e, reg["eras"])
        # a starter's own outfit is accepted on its body, and the old jumpers are not a starter's outfit
        for ch in reg["characters"].values():
            self.assertNotEqual(ch["outfit"], "casual_dressed_v0")


if __name__ == "__main__":
    unittest.main(verbosity=1)
