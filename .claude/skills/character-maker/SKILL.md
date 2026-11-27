---
name: character-maker
description: How to get a person the story needs when the Aj cast does not have them - deciding between reuse, a per-clip costume from accepted wardrobe, a new starter recipe, a new garment through the fitter and an independent review, and asking the owner for what the pipeline cannot supply (a body, a hair style, a Mixamo clip, a licence). Use when the story needs someone the cast does not have, when casting returns ADAPT or MISSING, or when a garment, add-on or clip is missing.
---

# character-maker: a person the cast does not have

The cast is the **Aj** family: eight bodies on a Mixamo skeleton, dressed from a fit-checked wardrobe (`config/cast.json`, `library/wardrobe/`). Full reference with every command, the limits and the pack owner's rules: `docs/CHARACTERS_3D.md`. This page is the decision order and the stops. `PY` is `py -3` on Windows, `python3` elsewhere.

A character is a body, a face preset, hair, an outfit, add-ons, a palette, a skin tone, a period and `avoid` limits. Nothing is drawn on a sheet and there is no build step for a person: a person is a **registry entry** made from parts that already passed the fit check.

## Decide, in this order. Stop at the first that works

1. **Reuse.** `PY tools/clip.py cast` (all), `cast --era <era>`, `cast <Name>` (everything about one character: what it may wear, its `avoid` limits, its QA, its sheet). Look at `library/characters/aj/previews/<Name>.png`. Most roles are an existing character.
2. **Re-dress in the plan.** Same body, other look: the plan's `cast[].costume` with `recolor` (palette slots, `hair`, `facial_hair`, `skin`, or a garment's name), `hide` (`hair`, `<outfit>.<piece>`, `addon:<item>`; a bare body is refused) and `wear` (an add-on the body may wear: tie, belt, blazer, cardigan, lanyard badge, glasses, wrist watch). No new file. Write `reads_as` so the viewer can tell people apart: silhouette, colour, one prop.
3. **A per-clip adaptation.** Different hair, beard, face, skin or outfit: put `wants` in the plan's cast entry (`sex`, `age`, `era`, `tags`, `hair`, `facial_hair`, `palette_hint`), run `PY tools/clip.py casting <clip>`, and when it says **ADAPT**, `casting <clip> --apply`: it files a draft character in `config/cast.json` from accepted wardrobe only and points the plan's `base` at it. Check `casting.md`.
4. **A new starter recipe** when the person will come back in other films: add a recipe to `tools/chars_aj/make_starter_cast.py`, run it with `--dry`, then for real; then `PY tools/clip.py cast --rescan` and `PY tools/cast_registry.py check`. Rules for a recipe: no two characters share silhouette and colour scheme; office and uniform looks use shirt_trousers, blouse_trousers or blouse_skirt with tie, belt, blazer, cardigan, lanyard badge, glasses, wrist watch; children wear the child cuts; honest `era`.
5. **A new garment** (a casting **MISSING** for an outfit or add-on, or a period piece): through the fitter and an independent review, below. Never an unfitted garment, not for one shot.
6. **Ask the owner** for what the pipeline cannot make: a new body, a hair style (the library has 25 styles and 7 beards), a Mixamo clip, a licence confirmation. Say exactly what is wanted; do not substitute.

A special body (ghost, mermaid, dragon, robot, a creature) is **not in this cast**. Do not fake one with a costume. Ask.

## Look and measure a character

```
PY tools/clip.py cast <Name>                        # what it is, what it may wear, AVOID, QA, sheet path
PY tools/chars_aj/qa.py <Name> [--no-actions]       # measured QA -> library/characters/aj/qa/<Name>.json (blocking items = not ready)
blender -b --factory-startup --python tools/chars_aj/gate_a_sheets.py -- --char <Name>      # its sheet -> library/characters/aj/previews/<Name>.png
blender -b --factory-startup --python tools/chars_aj/gate_a_sheets.py -- --lineup           # everyone together
PY tools/clip.py cast-sheets <clip>                 # Gate A for a film: every cast member in this plan's costume + QA
```

**Look at the sheet** (the Read tool, then send it to the user): four turns, five faces, an action pose holding a prop, a height line-up. Check the back and the side too: the camera goes there. A character with blocking QA items is not "ready". A warning that stays needs a reason. The hair licence warning is expected (see below).

## A new garment or add-on

A garment is generated from each body's own surface and checked by the pack's **unchanged** fit check. Run all of this headless in Blender: `blender -b --factory-startup --python tools/chars_aj/fit.py -- <command> ...`.

1. Add the outfit to `templates.OUTFITS` (or the add-on to `templates.ADDONS`) in `tools/blender/ajkit/templates.py`: pieces, template per piece (`top`, `trousers`, `shoes`, `skirt`, `belt`, `crown`), fabric, colours, era, tags, per-body overrides. Copy the nearest existing entry.
2. `custom <outfit> --bodies all` (or `addon <item> --bodies all`; `--jobs 2`). A fit is saved **only when it passes**; a failure leaves a report in `output/_staging/wardrobe/<outfit>/<Body>/`.
3. `check <file.blend>` runs the check on any dressed file (opened, never saved). **The limits are never loosened.** `PY -I tools/tests/cast/test_fit_limits.py` proves they are the pack's. Fix the garment.
4. `review <outfit> --bodies all` renders the review sheets (front, back, side, three-quarter, arms up, arms forward, stride, sit, bend, sit seen from behind).
5. **An independent review.** The one who built it does not judge it. A reviewer looks at every sheet and writes `library/wardrobe/reports/<outfit>/<Body>_review.json`: `accept` or `reject` and the limits in `avoid` ("accept" always means "inside these limits"). `fit.py` never writes `accept`.
6. `PY tools/chars_aj/fit.py recompute`, `index-check`, then `PY tools/clip.py cast --rescan`.

Third-party garments are used only when CC0 or BlenderKit royalty-free, with the licence recorded from the asset's own metadata (`library/wardrobe/README.md`); unknown or other licences are quarantined. Generated garments are `own`.

## A new Mixamo clip

`PY tools/clip.py clips --ask <Name>` prints the request for the owner: search words, the title to pick, and the settings (upload `packs/aj_rebuild_v1/09_Animations/Aj_upload.fbx` as the character once; FBX Binary, **Without Skin**, **30 fps**, Keyframe Reduction none, **In Place** where offered, Mirror for a mirrored clip). File: `library/characters/aj/mixamo/<File>.fbx`. A clip not in `config/mixamo_clips.json` needs an entry first (`file`, `mixamo_title`, `search`, `in_place`, `loop`, `kind`, `owns`, `actions`). Then `PY tools/clip.py clips --register <Name>` (analysis), `clips --check`. A shot that needs a missing clip **stops with exit 5**, prints the exact request and writes `MISSING_DOWNLOADS.md`; `clips --need <clip>` lists them all. Give the request to the owner and wait. Hooking a clip to a named action: `docs/ADDING_NEW_ACTIONS.md` and `stagekit/aj_clips.py`.

## When to stop and ask

- A body, hair style, skin or period that no registry part can make; a creature or special body.
- A clip file is missing (exit 5): the owner downloads it.
- A new fit fails the check and a change of the garment's parameters does not fix it: report the failure, never relax a limit.
- A fit passes but the reviewer rejects it: it stays unused. Say what the reviewer wrote.
- The hair licence (`unknown` in the registry) needs the owner's confirmation before anyone writes `own` over it.
- Anything that would change the head shape, the 3D mouth, a bone name or a rest pose, or save a pack `.blend`: the answer is no.

## What to report

For a new character: its registry entry, its QA result (blocking and warnings), the sheet you looked at, and its `avoid` limits. For a new garment: the fit result per body, the review verdicts, the limits, and what is still not covered.
