"""Round 2 of the independent costume review (2026-11-27): files the verdicts for the rebuilt outfits (shirt_trousers,
casual_tshirt_trousers, kid_tshirt_shorts, blouse_skirt on the four female bodies, blouse_trousers) and the seven add-ons, and records them in
library/wardrobe/index.json (fields review, reviewer, review_file, avoid only). Verdicts come from looking at the review sheets
(output/_staging/wardrobe/<outfit>/<Body>/<Body>_<outfit>_review.png) and the add-on look sheets (.../<item>/<Body>/<Body>_<item>_look.png);
this script only files them.

    py -3 tools/chars_aj/inspect/write_costume_review_round2.py
"""
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
REG = os.path.join(ROOT, "library", "wardrobe", "index.json")
REVIEWER = "independent reviewer (sub-agent), 2026-11-27, round 2"
BODIES = ["Male_Kid", "Male_Teen", "Male_Adult", "Male_Senior", "Female_Kid", "Female_Teen", "Female_Adult", "Female_Senior"]
FEMALE = [b for b in BODIES if b.startswith("Female")]

FIXED = ("Round-1 faults checked: the seat balloon, blob shoes and untucked hem are gone or much reduced as described below; "
         "shoes now have a sole, an opening and a lace strap.")
CHEST = "In pipeline-style renders (the add-on look sheets) a speckled noise patch sits at the collar and upper chest."

# outfit -> notes, limits, per-body extra notes, per-body extra limits
OUT = {
    "shirt_trousers": dict(
        verdict="accept_with_notes",
        notes=["Reads as an office shirt: collar, button placket and long sleeves, tucked into dark trousers with the hem ending at the waistband; real lace-up shoes with a sole, a toe cap and a lace strap.",
               "Round-1 faults: untucked hem GONE (it reads tucked); blob shoes GONE; seat balloon GONE (seated from behind the back is clean, only a small hem crinkle at the waist).",
               "Stride, bend, arms up and arms forward are presentable; no skin through cloth; sit from front and side is clean.",
               "NEW: " + CHEST + " The review-sheet lighting does not show it; the pipeline lighting (add-on look sheets, Gate A sheets) does. Medium and wide shots in any action, seated included, are safe."],
        limits=["Avoid tight close-ups of the collar and upper chest (speckled shading in pipeline renders)."],
        extra={"Male_Kid": ["Peter Pan collar and three-quarter puffed sleeves: reads as a child's blouse, not an office shirt."],
               "Female_Kid": ["Peter Pan collar and three-quarter puffed sleeves: reads as a child's blouse, not an office shirt."],
               "Female_Teen": ["Rounded collar; sleeves end above the wrist."],
               "Female_Adult": ["Bust shape is clear but restrained; seated from the front the waistband shows a faintly crinkled speckled line."],
               "Female_Senior": ["Soft belly and bust shape; seated from the front the waistband shows a crinkled speckled line at the waist."],
               "Male_Senior": ["Slight crumple at the back hem seated from behind."]}),
    "casual_tshirt_trousers": dict(
        verdict="accept_with_notes",
        notes=["Reads as a plain coral tee with a round neck and short sleeves over blue jeans-style trousers; white lace-up trainers with a grey sole and laces (round-1 'sock shoes' GONE).",
               "Stride, bend, arms up and forward are clean; no skin through cloth.",
               "Round-1 seat balloon: MUCH REDUCED, not gone. Seated from behind the untucked tee hem forms a rounded lip over the seat and the back sags a little; seated front and side are fine.",
               "NEW: a faint crease across the chest with the arms forward; soft shapes under the tee on adult and senior bodies."],
        limits=["Seated seen from behind: the tee hem forms a rounded lip over the seat; keep rear seated shots at medium distance."],
        extra={"Male_Kid": ["Tee is long on a child and reads like a short dress from behind when seated."],
               "Female_Kid": ["Tee is long on a child and reads like a short dress from behind when seated."],
               "Female_Adult": ["Bust and a soft belly show under the tee; restrained."],
               "Female_Senior": ["Soft belly and bust shape under the tee; the hem lumps over the belly seated."],
               "Male_Senior": ["Soft belly under the tee seated from the front."]}),
    "kid_tshirt_shorts": dict(
        verdict="accept_with_notes",
        notes=["Reads as a yellow tee, olive shorts and blue laced high-top trainers; shoes now have a sole, an opening and laces (round-1 blobs GONE), though the toe edge of the sole is slightly jagged in the close-up.",
               "Bare lower legs show a fine speckle in the view from behind (reads as down on the skin).",
               "Round-1 seat balloon: REDUCED but still there. Seated from behind the tee hangs over the shorts in a rounded bag; seated front shows the shorts crumpled under the hem.",
               "Standing, arms up, stride and bend are clean; no skin through cloth."],
        limits=["Seated seen from behind: the tee hangs over the shorts in a rounded bag; keep rear seated shots at medium distance.",
                "Keep feet out of extreme close-ups (jagged toe edge of the sole)."],
        extra={"Male_Teen": ["On a teenager the 'kid' set reads as casual summer wear."],
               "Male_Adult": ["On an adult the 'kid' set reads as casual summer wear; leg proportions are fine."],
               "Male_Senior": ["On an elderly man the shorts set reads as holiday wear."],
               "Female_Teen": ["On a teenager the 'kid' set reads as casual summer wear."],
               "Female_Adult": ["On an adult the 'kid' set reads as casual summer wear; bust shape under the tee is restrained."],
               "Female_Senior": ["The tee bunches into a wrinkled lump over the belly and the shorts crumple when seated: the least tidy fit of the set; acceptable standing."]}),
    "blouse_skirt": dict(
        verdict="accept_with_notes",
        notes=["Reads as a white three-quarter-sleeve blouse tucked into a navy straight knee-length skirt with a hem that follows the legs, and brown shoes with soles and lace straps.",
               "Round-1 faults: skirt BOWL/DISC when seated GONE (the skirt now rides up the thighs as a narrow band); seat balloon MUCH REDUCED (seated from behind the skirt makes a rounded bag below the blouse hem); blob shoes GONE.",
               "NEW: seated from the front a small patch of skin shows between the thighs under the front hem of the skirt; it reads as a pale triangle at sheet size, not indecent but not clean either.",
               "NEW: bare legs show a fine speckle seen from behind (down on the skin). Stride: the skirt folds against the forward leg but stays a clean tube."],
        limits=["Seated seen from the front at close or low angle: skin shows between the thighs under the skirt's front hem; keep seated front shots at a medium distance or from the side.",
                "Seated seen from behind: the skirt forms a rounded bag under the blouse hem."],
        extra={"Female_Kid": ["On a child the skirt is very short and reads as shorts; fine for a schoolgirl."],
               "Female_Teen": ["The skirt hem is above the knee when seated; legs bare."],
               "Female_Adult": ["Bust is restrained; the hem sits just above the knee."],
               "Female_Senior": ["Soft belly under the blouse; the hem sits above the knee."]}),
    "blouse_trousers": dict(
        verdict="accept_with_notes",
        notes=["Reads as an office blouse: white three-quarter sleeves, small collar, tucked into navy tailored trousers, with brown shoes that have a sole and a lace strap.",
               "Clean in stride, bend, arms up and arms forward; no skin through cloth. Seated from behind there is no balloon, only a small crinkle at the waist hem.",
               "NEW (minor): sleeves end above the wrist; seated from the front the waistband shows a crinkled speckled line on the adult and senior bodies."],
        limits=["Avoid tight close-ups of the collar and upper chest (speckled shading seen on the same shirt cut in pipeline renders)."],
        extra={"Female_Kid": ["Rounded collar and puffed sleeves read as a child's blouse."],
               "Female_Adult": ["Bust is restrained."],
               "Female_Senior": ["Soft belly and bust shape; a white line at the waist when seated from the front."]}),
}

SKIN_FIX = ("Skinned add-on: its look sheets were shredded into thin arcs before the aj_wardrobe loader fix of this round "
            "(matrix_parent_inverse was taken from an unsynchronised matrix). With the fix it sits correctly; this verdict is on the fixed render.")
ADD = {
    "tie": dict(
        verdict="accept_with_notes",
        notes=["Reads as a necktie: a red flat strip hanging from the collar down the placket with a pointed tip, centred on the buttons, ending just above the waistband.",
               "It follows the chest shape on the female bodies (a gentle wave over the bust) and sits flat; arms up, sitting and stride keep it on the placket.",
               "No knot or collar wrap: it is a plain strip, so it reads at medium distance but not in an extreme close-up. Shirt collar stays visible around it.",
               SKIN_FIX],
        limits=["Plain strip with no knot: keep close-ups of the neck loose.",
                "Not for use over a tee or blouse; it was built over shirt_trousers."], extra={}),
    "belt": dict(
        verdict="accept_with_notes",
        notes=["Reads as a brown belt with a small gold buckle at the front and a sewn edge, sitting on the trouser waistband under the shirt hem; visible front, side and back.",
               "Seated it bends into a wavy ribbon around the seat and thigh and floats slightly off the trousers at the back.",
               SKIN_FIX],
        limits=["Seated seen from behind or from the side at close range: the belt bends into a wavy ribbon over the seat."], extra={}),
    "blazer": dict(
        verdict="accept_with_notes",
        notes=["Reads as a navy open jacket worn over the shirt: wide three-quarter sleeves, soft shoulders and a hem at the hip; the shirt and tie line show in the opening.",
               "No crisp lapels: the collar is soft, and at the back of the neck it stands up in a short funnel that reads like a turtleneck behind the head.",
               "Seated from behind and from the side the jacket balloons into a large rounded bag over the seat and thighs; it is the bulkiest of the add-ons.",
               "Sleeves are wide and short of the wrist, so on a child it reads like an oversize cardigan. Arms up and forward are clean.",
               SKIN_FIX],
        limits=["Seated seen from behind or the side: the jacket balloons into a bag over the seat.",
                "Back-of-neck close-ups show a standing funnel collar."], extra={}),
    "cardigan": dict(
        verdict="accept_with_notes",
        notes=["Reads as a sage-green open cardigan over the shirt: wide three-quarter sleeves, soft knit surface and a hip-length hem.",
               "Same boxy cut as the blazer: a short standing collar at the back of the neck, and seated it balloons into a rounded bag over the seat.",
               "On the senior and adult women it drapes over the bust with a visible shape; a slight fuzz at the shoulder edge.",
               SKIN_FIX],
        limits=["Seated seen from behind or the side: the cardigan balloons into a bag over the seat.",
                "Back-of-neck close-ups show a standing collar."], extra={}),
    "lanyard_badge": dict(
        verdict="accept_with_notes",
        notes=["Reads as an ID badge: a blue strap in a V at the collar and a white rectangular card on the chest at the third button; it stays on the placket in sit, arms up and stride.",
               "There is no strap behind the neck: from behind and from the side the strap does not go round the nape, so the card seems to float from a V at the collar.",
               "The card is a plain white slab with no print or photo.",
               SKIN_FIX],
        limits=["Back-of-neck and side close-ups show no strap behind the neck; keep those shots wide."], extra={}),
    "glasses": dict(
        verdict="accept_with_notes",
        notes=["Reads as spectacles: dark round-square frames with two lenses and temples that reach the ears; they sit on the nose bridge at eye level in front, three-quarter and profile.",
               "The frames are large and thick, covering a wide share of the face on the adult and senior heads (a retro look), and the lenses show a noisy frosted speckle in draft light.",
               "Measured on Male_Adult: the glasses' bridge sits 4.6 cm in front of the nose-bridge surface in native metres (a frame standoff), the same whether worn from the list or after placing.",
               "Rigid on the Head bone: they follow head turns; round-1 loader bug (floating when worn after placing) is fixed this round."],
        limits=["Lenses speckle in draft stills: do not rely on seeing the eyes through the lens in a close-up."], extra={}),
    "wrist_watch": dict(
        verdict="accept_with_notes",
        notes=["Reads as a small dark watch with a light face on the left wrist, under the cuff, at the forearm; it follows the arm in arms up, sit and stride.",
               "It is very small: visible only in a close-up of the hand; at medium shot it is a dot.",
               "Rigid on the LeftForeArm bone: the round-1 loader bug (it floated 0.5 m from the wrist when worn after the arm had moved) is fixed this round."],
        limits=["Left wrist only; keep the left hand in view if the watch matters to the story."], extra={}),
}


def write(rel, data):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def main():
    with open(REG, encoding="utf-8") as f:
        reg = json.load(f)
    counts = {"accept": 0, "accept_with_notes": 0, "reject": 0}
    table = {}
    for oid, spec in OUT.items():
        fits = reg["outfits"][oid]["fits"]
        for body, fit in fits.items():
            if oid == "blouse_skirt" and body not in FEMALE:
                continue                                              # the male pairs keep their round-1 reject
            notes = list(spec["notes"]) + list(spec["extra"].get(body, []))
            limits = list(spec["limits"])
            sheet = f"output/_staging/wardrobe/{oid}/{body}/{body}_{oid}_review.png"
            rel = f"library/wardrobe/reports/{oid}/{body}_review.json"
            write(rel, {"outfit": oid, "body": body, "verdict": spec["verdict"], "reviewer": REVIEWER, "sheet": sheet,
                        "notes": notes, "limits": limits})
            fit.update(review="accept" if spec["verdict"] != "reject" else "reject", reviewer=REVIEWER, review_file=rel, avoid=limits)
            counts[spec["verdict"]] += 1
            table[f"{oid}|{body}"] = spec["verdict"]
    for item, spec in ADD.items():
        fits = reg["addons"][item]["fits"]
        for body, fit in fits.items():
            sheet = f"output/_staging/wardrobe/{item}/{body}/{body}_{item}_look.png"
            rel = f"library/wardrobe/reports/{item}/{body}_review.json"
            write(rel, {"item": item, "body": body, "verdict": spec["verdict"], "reviewer": REVIEWER, "sheet": sheet,
                        "notes": list(spec["notes"]), "limits": list(spec["extra"].get(body, [])) + list(spec["limits"])})
            fit.update(review="accept", reviewer=REVIEWER, review_file=rel, avoid=list(spec["limits"]))
            counts[spec["verdict"]] += 1
            table[f"{item}|{body}"] = spec["verdict"]
    with open(REG, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(counts)
    with open(os.path.join(ROOT, "output", "_staging", "wardrobe", "review_table_round2.json"), "w") as f:
        json.dump(table, f)


if __name__ == "__main__":
    main()
