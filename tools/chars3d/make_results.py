"""make_results.py - write docs/ACTIONS_3D_RESULTS.md from the per-character action test results. Stdlib only.

    py -3 make_results.py <results dir> <out.md>
"""
import json
import sys
from pathlib import Path

d, out = Path(sys.argv[1]), Path(sys.argv[2])
chars = {}
for f in sorted(d.glob("*.json")):
    if f.name == "summary.json":
        continue
    j = json.loads(f.read_text(encoding="utf-8"))
    chars[j["char"]] = j["results"]
acts = sorted({a for r in chars.values() for a in r})
tot = sum(len(r) for r in chars.values())
ok = sum(1 for r in chars.values() for v in r.values() if v["pass"])
L = ["# Action tests on the 3D cast", "",
     f"**{ok} of {tot}** action x character combinations pass: {len(acts)} actions on {len(chars)} characters, each performed once in a plain test scene "
     "(three-quarter view, facing right) and measured on every frame.", "",
     "| Check | Passes when |", "|---|---|",
     "| held prop | a prop that is being held is within 3 cm of the palm on every frame |",
     "| planted feet | a foot on the ground moves less than 3.5 cm in one frame while walking (6 cm in other actions); a figure turning on the spot is exempt |",
     "| floor | no foot is more than 4 cm below the ground (lying, kneeling, climbing and swimming actions are exempt) |",
     "| touch | for pick_up, press, knock, turn_key, push, pull, lift, receive, open_door: the palm comes close to the thing |", "",
     "Not measured: whether a pose reads, whether a hand passes through a costume, timing. Those are judged from pictures.", ""]
bad = [(c, a, v) for c, r in chars.items() for a, v in r.items() if not v["pass"]]
if bad:
    L += [f"## Failing: {len(bad)}", "", "| Character | Action | Why |", "|---|---|---|"]
    for c, a, v in bad:
        L.append(f"| {c} | `{a}` | {'; '.join(v['fails'])[:200]} |")
    L.append("")
else:
    L += ["## Failing: none", ""]
L += ["## Per character", "", "| Character | Pass | Fail |", "|---|---|---|"]
for c, r in chars.items():
    p = sum(1 for v in r.values() if v["pass"])
    L.append(f"| {c} | {p} | {len(r) - p} |")
L += ["", "## Worst measured values per action (over all characters)", "", "| Action | Characters | Held prop gap (cm) | Foot slide (cm) | Below floor (cm) |", "|---|---|---|---|---|"]
for a in acts:
    vs = [r[a] for r in chars.values() if a in r and "frames" in r[a]]
    if not vs:
        continue
    L.append(f"| `{a}` | {len(vs)} | {max(v['held_gap'] for v in vs) * 100:.1f} | {max(v['foot_slide'] for v in vs) * 100:.1f} | {max(v['sunk'] for v in vs) * 100:.1f} |")
out.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"{ok}/{tot} pass, {len(chars)} characters, {len(bad)} failing -> {out}")
