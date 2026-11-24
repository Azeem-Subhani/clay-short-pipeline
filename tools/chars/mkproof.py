"""mkproof.py - queue every proof render that is not an action test (for jobrun.py). Stdlib only.

    py -3 mkproof.py <queue.jsonl>

Jobs (each writes its own files under work/out/proof/):
  ink        outline consistency: 12 characters on 0.4 (3 scales), 6 characters on the 0.3 pack for comparison
  poses      pose x view x facing frames for 8 representative characters (all named poses)
  trans      transition frame strips between poses (every 2nd frame), 3 views x 2 facings, 4 characters
  compare    every new character next to its reference crop
  wardrobe   all 17 wardrobe pieces on 4 old and 6 new characters
  walkticks  the front walk frames of Senior Man and Office Woman (0.3's known tick)
  pond       the 21 logged moments of the pond clip, re-rendered with the final code
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charpaths as P  # noqa: E402
import mkqueue  # noqa: E402

OUT = P.OUT / "proof"
BL = P.BL
OLD = P.TOOLS.parent.parent / "characters_beta_0.3" / "character-library_v3d.blend"
NEW_CAST = [n for n in mkqueue.all_names() if not (P.PACK / "character_refs" / "crops_v3c" / f"{n}.png").exists()
            and (P.PACK / "character_refs" / "crops_v4" / f"{n}.png").exists()]


def bl(script, *args):
    return [BL, "-b", "--factory-startup", "--threads", "2", "--python", str(script), "--", *[str(x) for x in args]]


jobs = []
INK_NEW = ["Soldier", "Queen", "Boy", "Baby", "SeniorMan", "OfficeAssistant", "Witch", "Knight", "Princess", "Mummy", "Dragon", "Ghost"]
for n in INK_NEW:
    jobs.append({"id": f"ink:v4:{n}", "kind": "ink", "outputs": [str(OUT / "ink_v4" / n / "ink.json")], "min_bytes": 200,
                 "fail_if": ["Traceback (most recent call last)"],
                 "cmd": bl(P.TOOLS / "bl" / "ink_test.py", "--char", n, "--pack", P.CHARS / f"{n}.blend", "--out", OUT / "ink_v4", "--pipeline", P.PIPELINE)})
for n in ["Soldier", "Queen", "Boy", "OfficeAssistant", "Witch", "SeniorMan"]:
    jobs.append({"id": f"ink:v3d:{n}", "kind": "ink", "outputs": [str(OUT / "ink_v3d" / n / "ink.json")], "min_bytes": 200,
                 "fail_if": ["Traceback (most recent call last)"],
                 "cmd": bl(P.TOOLS / "bl" / "ink_test.py", "--char", n, "--pack", OLD, "--out", OUT / "ink_v3d", "--scales", "1.0", "--pipeline", P.PIPELINE)})
for n in ["AdultMan", "Soldier", "Queen", "Boy", "Baby", "SeniorMan", "Knight", "Ghost", "Dragon"]:
    jobs.append({"id": f"poses:{n}", "kind": "strip", "outputs": [str(OUT / "poses" / n / "rest__front_right.png")], "min_bytes": 2000,
                 "fail_if": ["Traceback (most recent call last)"],
                 "cmd": bl(P.TOOLS / "bl" / "pose_sheet.py", "--char", n, "--pack", P.CHARS / f"{n}.blend", "--out", OUT / "poses", "--px", "300",
                           "--zoom", "2.2", "--pipeline", P.PIPELINE)})
TRANS = "rest>cheer,hips>cheer,gasp>point,carry>hands_up,think>wave,rest>cross_arms,point>facepalm,sit>rest"
for n in ["Soldier", "Queen", "Boy", "Mermaid"]:
    jobs.append({"id": f"trans:{n}", "kind": "strip", "outputs": [str(OUT / "trans" / n / "T_rest-cheer__front_right__00.png")], "min_bytes": 2000,
                 "fail_if": ["Traceback (most recent call last)"],
                 "cmd": bl(P.TOOLS / "bl" / "pose_sheet.py", "--char", n, "--pack", P.CHARS / f"{n}.blend", "--out", OUT / "trans", "--px", "260",
                           "--zoom", "2.2", "--trans", TRANS, "--pipeline", P.PIPELINE)})
for n in NEW_CAST:
    jobs.append({"id": f"compare:{n}", "kind": "compare", "outputs": [str(OUT / "compare_ref" / f"{n}.png")], "min_bytes": 5000,
                 "fail_if": ["Traceback (most recent call last)"],
                 "cmd": [BL, "-b", str(P.CHARS / f"{n}.blend"), "--threads", "2", "--python", str(P.SCRIPTS / "compare_ref_v4.py"), "--", "--name", n,
                         "--out", str(OUT / "compare_ref" / f"{n}.png"), "--refdir", str(P.PACK / "character_refs" / "crops_v4"), "--h", "700"]})
for n in ["AdultMan", "Queen", "Boy", "Skeleton", "Farmer", "Housemaid", "Knight", "ElderlyWoman", "Ghost", "Robot"]:
    jobs.append({"id": f"wardrobe:{n}", "kind": "strip", "outputs": [str(OUT / "wardrobe" / n / "straw_hat__3q.png")], "min_bytes": 2000,
                 "fail_if": ["Traceback (most recent call last)"],
                 "cmd": bl(P.TOOLS / "bl" / "wardrobe_sheet.py", "--char", n, "--pack", P.CHARS / f"{n}.blend", "--out", OUT / "wardrobe", "--pipeline", P.PIPELINE)})
for n in ["SeniorMan", "OfficeWoman"]:
    for fr in (0, 4, 8, 12, 16, 20):
        jobs.append({"id": f"walktick:{n}:{fr}", "kind": "compare", "outputs": [str(OUT / "walk_ticks" / f"{n}_front_walk_{fr:02d}.png")], "min_bytes": 5000,
                     "fail_if": ["Traceback (most recent call last)"],
                     "cmd": [BL, "-b", str(P.CHARS / f"{n}.blend"), "--threads", "2", "--python", str(P.SCRIPTS / "render_closeup_v4.py"), "--", "--name", n,
                             "--view", "0", "--frame", str(fr), "--region", "-0.45", "0.30", "0.45", "1.15", "--px", "900",
                             "--out", str(OUT / "walk_ticks" / f"{n}_front_walk_{fr:02d}.png")]})
CL = P.PIPELINE / "output" / "clips" / "the-ring-in-the-pond"
for shot, frames in (("sh01", "9,41,209,217,241,277"), ("sh02", "15,71,143,167"), ("sh03", "12,36,84,204"), ("sh04", "17,89,101,201,213,265,317")):
    first = int(frames.split(",")[0])
    jobs.append({"id": f"pond:{shot}", "kind": "pond", "outputs": [str(OUT / "pond_after" / f"{shot}_{first:04d}.png")], "min_bytes": 50000,
                 "fail_if": ["Traceback (most recent call last)"],
                 "cmd": bl(P.TOOLS / "bl" / "pond_frames.py", "--clip", CL, "--shot", shot, "--frames", frames, "--out", OUT / "pond_after", "--pipeline", P.PIPELINE)})
q = Path(sys.argv[1])
q.parent.mkdir(parents=True, exist_ok=True)
q.write_text("\n".join(json.dumps(j) for j in jobs) + "\n", encoding="utf-8")
print(f"{len(jobs)} proof jobs -> {q}  ({len(NEW_CAST)} new characters to compare)")
