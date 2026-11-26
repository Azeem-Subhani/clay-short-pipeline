"""Writes the independent costume review files for the generated wardrobe outfits and records
them in library/wardrobe/index.json (fields review, reviewer, review_file, avoid only).
Also records where the nine pack-imported accepts came from. Verdicts come from looking at the
review sheets; this script only files them."""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
REG = os.path.join(ROOT, "library", "wardrobe", "index.json")
REVIEWER = "independent reviewer (sub-agent), 2026-11-27"

SIT_BACK = "Sit seen from behind: the back hem balloons into a rounded flap or bag over the seat."

# outfit -> dict(default verdict, notes, limits); per-body overrides in BODY
OUT = {
    "casual_tshirt_trousers": dict(
        verdict="accept_with_notes",
        notes=["Standing front, back, side, three-quarter: reads clearly as a plain tee and jeans-style trousers; collar, sleeves and hem are clean; cloth, not paint.",
               "Arms up and arms forward: tee rides up cleanly, no armpit tearing; a faint diagonal crease crosses the chest when the arms are forward.",
               "Stride and bend: trousers and shoes stay correct, no skin through cloth.",
               SIT_BACK + " Sit from the front and side is fine."],
        limits=["Do not seat this character seen from behind or from a low rear three-quarter.",
                "Shoes read as plain white socks or bootees; avoid full-body hero close-ups of the feet."]),
    "shirt_trousers": dict(
        verdict="accept_with_notes",
        notes=["Standing views: reads as a buttoned shirt with collar and long sleeves over dark trousers and shoes; the close-up front shows collar and button line cleanly.",
               "The shirt is worn untucked at hip length with a straight hem; it does not look tucked in, so the 'office' read is modest.",
               "Arms up, forward, stride and bend are presentable; hem lifts neatly.",
               SIT_BACK],
        limits=["Do not seat this character seen from behind.",
                "Medium and wide shots are safe; a tight rear close-up shows the plain back with no yoke or seam detail."]),
    "kid_tshirt_shorts": dict(
        verdict="accept_with_notes",
        notes=["Standing views: reads as a yellow tee, green shorts and blue shoes; edges and sleeves are clean.",
               "The blue shoes are blunt bootee shapes with no sole or opening; acceptable at medium distance only.",
               "Bare lower legs show a fine speckle texture in the close-up from behind (reads as down on the skin).",
               SIT_BACK + " The tee covers the shorts completely there."],
        limits=["Do not seat this character seen from behind.",
                "Keep feet out of close-ups."]),
    "blouse_skirt": dict(
        verdict="accept_with_notes",
        notes=["Standing views: white three-quarter-sleeve blouse with a small collar over a navy A-line skirt and black shoes; clean edges, reads as a blouse and skirt.",
               "Sit from the front: the skirt rises into a shallow bowl or disc around the thighs with the knees visible through it; looks odd but not indecent.",
               "Stride front: the skirt wraps and folds against the forward leg.",
               SIT_BACK + " The blouse hangs over a round skirt bubble."],
        limits=["Do not seat this character seen from behind or from a low front angle.",
                "Avoid wide strides and running close to camera."]),
    "dress_simple": dict(
        verdict="accept_with_notes",
        notes=["Reads as a two-piece pink top and skirt rather than one dress: the boxy top ends in a hard straight hem with a visible step onto the skirt at the waist, front and back.",
               "Standing, arms up and bend are otherwise clean; neckline and sleeves are tidy.",
               "Sit from the front: skirt becomes a wide disc around the knees. Stride: skirt folds against the leg.",
               "Sit seen from behind: a large pink balloon over the seat, the worst seat of any outfit."],
        limits=["Never seat this character seen from behind or from the front at close range.",
                "Medium shots standing or walking slowly only."]),
    "king_robes": dict(
        verdict="accept_with_notes",
        notes=["Reads as a king by the gold crown and white ermine yoke; purple tunic with brown belt is tidy and the colour is strong.",
               "It is a knee-length tunic over trousers, not floor-length robes, so the silhouette is more prince or page than king.",
               "Sit from the front: the tunic skirt becomes a wide purple disc over the knees. Stride: tunic skirt folds against the leg.",
               "Sit seen from behind: heavy balloon with a wavy belt line across it."],
        limits=["Do not seat this character seen from behind or at close range from the front.",
                "Best standing, on a throne seen from the side, or in medium shots."]),
    "queen_gown": dict(
        verdict="reject",
        notes=["Does not read as a gown: it is the same knee-length flared tunic as the king robe with trousers and boots visible beneath, so the 'queen' read rests on the crown alone.",
               "Standing views are clean (gold belt, ermine yoke) but the silhouette is a short blue tunic dress over trousers.",
               "Sit from the front: wide flared disc over the knees; stride: skirt folds against the leg.",
               "Sit seen from behind: a large blue balloon over the seat."],
        limits=["Do not use for a queen until the skirt is floor-length or reads as a gown."]),
    "guard_tabard": dict(
        verdict="accept_with_notes",
        notes=["Reads as a plain red sleeveless tunic with a brown belt over cream sleeves, grey trousers and boots; clean armholes and hem.",
               "There is no emblem, helmet or other guard marking, so the guard role has to come from props and context.",
               "Boots are tall stiff tubes with the trouser ends visible above them; they look like separate cylinders in the rear close-up.",
               "Sit seen from behind: tunic back curls over the seat in a rounded flap with a wavy belt line."],
        limits=["Do not seat this character seen from behind.",
                "Pair with a spear or helmet to sell the role; do not rely on the tabard alone."]),
    "knight_armour": dict(
        verdict="reject",
        notes=["Does not read as armour or a knight: the torso is a glossy silver sleeveless puffer-style vest over grey padded sleeves, grey trousers and silver boots.",
               "No helmet, shoulder plates, mail, gauntlets or tabard; looks like a space suit or padded jacket.",
               "The metal-look surface shows stretched, wrinkled highlights over the chest and back (arms forward, sit from behind).",
               "Sit seen from behind: rounded bag with a wavy belt line."],
        limits=["Do not use as a knight until it has visible armour pieces (helmet, pauldrons, mail skirt)."]),
    "kitchen_maid": dict(
        verdict="accept_with_notes",
        notes=["Re-rendered after the apron fix: a white apron panel now shows on the front over a blue skirt with a cord belt; reads as a maid or cook at a glance.",
               "The apron is a front-only panel: from the side the white meets the blue skirt in a hard vertical split.",
               "Sit from the front: skirt becomes a wide bowl over the knees. Stride: apron and skirt fold against the leg.",
               "Sit seen from behind: a big balloon with the blouse hem over it. Trousers show under the skirt."],
        limits=["Do not seat this character seen from behind or from the front at close range.",
                "Avoid wide strides toward camera; standing and slow walking are fine."]),
    "peasant_man": dict(
        verdict="accept_with_notes",
        notes=["Reads as a peasant: cream loose shirt with a rope belt, brown knee breeches and tall brown boots; edges clean, cloth not paint.",
               "Boots are tall straight tubes; the gap between breeches and boot top is clean.",
               "Arms up, forward, stride and bend are presentable.",
               "Sit seen from behind: the shirt hem forms a rounded flap over the seat with a wavy belt line."],
        limits=["Do not seat this character seen from behind."]),
    "peasant_woman": dict(
        verdict="accept_with_notes",
        notes=["Re-rendered after the apron fix: cream blouse, white apron panel over a brown skirt, trousers and boots beneath; reads as a village woman.",
               "The apron is a front-only panel: hard white-to-brown split seen from the side.",
               "Sit from the front: the skirt becomes a wide bowl and a dark hollow shows inside it. Stride: skirt and apron fold against the leg.",
               "Sit seen from behind: large balloon with the blouse hem over it."],
        limits=["Do not seat this character seen from behind or from the front at close range.",
                "Avoid wide strides toward camera; standing and slow walking are fine."]),
}

# per-body overrides: (outfit, body) -> dict(verdict=, extra_notes=[], limits=[], replace_notes=[])
BODY = {}
for b in ("Male_Kid", "Male_Teen", "Male_Adult", "Male_Senior"):
    BODY[("blouse_skirt", b)] = dict(
        verdict="reject",
        replace_notes=["A female-cut blouse and A-line skirt on a male body reads as a man or boy in a skirt: unintentionally comic, with no bust shaping and a masculine shoulder and leg line.",
                       "Standing views are technically clean (collar, hem, shoes) and the skirt behaves as on the female bodies, but the casting result is wrong for any story that does not call for it.",
                       "Sit from the front: skirt becomes a bowl around the thighs; sit seen from behind: blouse balloon over a skirt bubble."],
        limits=["Do not use for ordinary casting. Only for a deliberate costume gag."])
for b in ("Female_Adult", "Female_Senior"):
    BODY[("dress_simple", b)] = dict(
        verdict="reject",
        extra_notes=["Bodice is lumpy on this body: the top bunches over the bust and stomach, and a loose fold of cloth stands out at the side of the torso in three-quarter and close-up views."],
        limits=["Do not use until the top is fitted to the bust and waist and joined to the skirt."])
BODY[("blouse_skirt", "Female_Senior")] = dict(
    extra_notes=["Small white speckles at the blouse back hem in the sit-from-behind close-up (stray geometry or shading)."])
BODY[("blouse_skirt", "Female_Adult")] = dict(
    extra_notes=["Bust reads as a smooth, restrained shape under the blouse; no ragged edges."])
BODY[("casual_tshirt_trousers", "Female_Adult")] = dict(
    extra_notes=["Bust shows as a clear but restrained shape; the tee bunches slightly under the bust with arms forward."])
BODY[("casual_tshirt_trousers", "Female_Senior")] = dict(
    extra_notes=["Soft lumpy belly and bust shape under the tee; acceptable for a senior but slightly uneven in the front close-up."])
BODY[("shirt_trousers", "Female_Senior")] = dict(
    extra_notes=["Soft belly shape under the shirt front; the button line bends slightly in the close-up."])
BODY[("shirt_trousers", "Male_Kid")] = dict(
    extra_notes=["Sleeves end above the wrist with a puffed cuff and a rounded Peter Pan collar; reads as a boy's blouse rather than an office shirt."])
BODY[("shirt_trousers", "Female_Kid")] = dict(
    extra_notes=["Sleeves end above the wrist with a puffed cuff and a rounded Peter Pan collar; reads as a child's blouse rather than an office shirt."])
BODY[("kid_tshirt_shorts", "Male_Adult")] = dict(
    extra_notes=["On an adult the 'kid' set reads as casual summer wear; leg proportions are fine."])
BODY[("kid_tshirt_shorts", "Female_Senior")] = dict(
    extra_notes=["Soft belly and bust shape under the tee; acceptable."])
BODY[("peasant_woman", "Female_Senior")] = dict(
    extra_notes=["Soft belly under the blouse is visible in the front close-up; clean otherwise."])


def body_sex(body):
    return body.split("_")[0]


def main():
    with open(REG, encoding="utf-8") as f:
        reg = json.load(f)
    counts = {"accept": 0, "accept_with_notes": 0, "reject": 0}
    table = {}
    for oid, spec in OUT.items():
        fits = reg["outfits"][oid]["fits"]
        for body in fits:
            ov = BODY.get((oid, body), {})
            verdict = ov.get("verdict", spec["verdict"])
            notes = list(ov.get("replace_notes", spec["notes"])) + list(ov.get("extra_notes", []))
            limits = list(spec["limits"]) if "limits" not in ov else []
            limits += ov.get("limits", [])
            if verdict == "reject" and oid == "blouse_skirt":
                limits = ov["limits"]
            sheet = f"output/_staging/wardrobe/{oid}/{body}/{body}_{oid}_review.png"
            rel = f"library/wardrobe/reports/{oid}/{body}_review.json"
            data = {"outfit": oid, "body": body, "verdict": verdict, "reviewer": REVIEWER,
                    "sheet": sheet, "notes": notes, "limits": limits}
            path = os.path.join(ROOT, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            fit = fits[body]
            fit["review"] = "reject" if verdict == "reject" else "accept"
            fit["reviewer"] = REVIEWER
            fit["review_file"] = rel
            fit["avoid"] = limits
            counts[verdict] += 1
            table[(oid, body)] = verdict
    # pack-imported accepts
    pack_n = 0
    for oid in ("jeans_shirt", "pants_top"):
        for body, fit in reg["outfits"][oid]["fits"].items():
            if fit.get("review") != "accept":
                continue
            rel = f"packs/aj_rebuild_v1/04_Outfit_Fits/{oid}/Aj_{body}_{oid}_review.json"
            p = os.path.join(ROOT, rel)
            with open(p, encoding="utf-8") as f:
                v = json.load(f).get("verdict")
            if v != "accept":
                print("PACK REVIEW NOT ACCEPT", rel, v)
                sys.exit(1)
            fit["reviewer"] = "pack review 2026-11-26 (see review_file)"
            fit["review_file"] = rel
            pack_n += 1
    with open(REG, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(counts, "pack accepts annotated:", pack_n)
    json.dump({f"{k[0]}|{k[1]}": v for k, v in table.items()},
              open(os.path.join(ROOT, "output", "_staging", "wardrobe", "review_table.json"), "w"))


if __name__ == "__main__":
    main()
