"""Print what each body can wear, as a markdown table, from library/wardrobe/index.json (the single source of truth).

    py -3 tools/chars_aj/inspect/wardrobe_table.py            print the table and the counts
    py -3 tools/chars_aj/inspect/wardrobe_table.py --write    put them between the markers in library/wardrobe/README.md

A cell says what the registry holds for that outfit or add-on on that body: accept (fit passed the measured check and the independent
review accepted it; a star means the review left limits in `avoid`), reject, fail (the fit check failed), pass (passed, never reviewed),
not built (no fit made). Standard library only; needs no Blender.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INDEX = ROOT / "library" / "wardrobe" / "index.json"
README = ROOT / "library" / "wardrobe" / "README.md"
BODIES = ["Male_Kid", "Male_Teen", "Male_Adult", "Male_Senior", "Female_Kid", "Female_Teen", "Female_Adult", "Female_Senior"]
SHORT = ["M kid", "M teen", "M adult", "M senior", "F kid", "F teen", "F adult", "F senior"]
START, END = "<!-- wardrobe-table:start -->", "<!-- wardrobe-table:end -->"


def cell(entry: dict, body: str) -> str:
    fit = (entry.get("fits") or {}).get(body)
    if not fit or fit.get("status") == "not_fitted":
        return "not built"
    if fit.get("status") == "fail":
        return "fail"
    review = fit.get("review")
    if review == "reject":
        return "reject"
    if review == "accept":
        return "accept*" if fit.get("avoid") else "accept"
    return "pass"


def build() -> str:
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    rows, tot = [], {"accept": 0, "reject": 0, "fail": 0, "pass": 0, "not built": 0}
    for kind, group in (("outfit", idx["outfits"]), ("add-on", idx["addons"])):
        for name, e in group.items():
            cells = [cell(e, b) for b in BODIES]
            for c in cells:
                tot[c.rstrip("*")] += 1
            ready = sum(c.startswith("accept") for c in cells)
            rows.append(f"| {name} | {kind} | " + " | ".join(cells) + f" | {ready} |")
    head = "| Name | Kind | " + " | ".join(SHORT) + " | Bodies ready |\n|---|---|" + "---|" * (len(SHORT) + 1)
    n_out, n_add = len(idx["outfits"]), len(idx["addons"])
    summary = (f"Registry as of {idx.get('as_of', '?')}: {n_out} outfits and {n_add} add-ons across 8 bodies = {sum(tot.values())} pairs: "
               f"{tot['accept']} accepted (fit passed and reviewer accepted), {tot['reject']} rejected by the reviewer, {tot['fail']} failed the fit check, "
               f"{tot['pass']} passed but unreviewed, {tot['not built']} not built.")
    return summary + "\n\n" + head + "\n" + "\n".join(rows)


def main() -> int:
    text = build()
    if "--write" not in sys.argv:
        print(text)
        return 0
    s = README.read_text(encoding="utf-8")
    if START not in s or END not in s:
        raise SystemExit(f"{README} has no {START} ... {END} markers")
    a, b = s.index(START) + len(START), s.index(END)
    README.write_text(s[:a] + "\n" + text + "\n" + s[b:], encoding="utf-8", newline="")
    print(f"wrote the table into {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
