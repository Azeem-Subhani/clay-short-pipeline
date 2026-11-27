# The Aj cast

Every person on screen is an **Aj**: one stylised 3D body on an unmodified Mixamo skeleton (83 bones, `mixamorig:` names), with a drawn mouth, real fingers, hair, and clothes with thickness. The camera can go all the way round them, including behind. The body, the hair library and the Mixamo clips come from a pack installed at `packs/aj_rebuild_v1/` (never committed). Everything we added on top lives in the files named below.

This page is the guide for three kinds of reader: a **shot builder** (how to act with them), a **director or casting step** (who exists and how a role is filled), and a **character or wardrobe maker** (how to add a person, a garment or a clip). The short form for the maker is `.claude/skills/character-maker/SKILL.md`.

## Where things are

| What | Where |
|---|---|
| The cast registry: bodies, families, the starter characters, their limits | `config/cast.json` |
| Who may wear what, where each piece came from, its licence, its fit and review per body | `library/wardrobe/index.json`, rules in `library/wardrobe/README.md`, reviewers' reports in `library/wardrobe/reports/` |
| Fitted garments (one `.blend` per body, gitignored) | `library/wardrobe/fits/<Body>/`, `library/wardrobe/addons/<Body>/` |
| Measured bodies (joints, palms, skin spots, lengths) | `library/characters/aj/bodies/<Body>.json` |
| Hair and beard library (25 styles, 7 beards and moustaches; `.npz` files are gitignored) | `library/characters/aj/hair/` |
| Mixamo clips (FBX, gitignored) and their registry | `library/characters/aj/mixamo/`, `config/mixamo_clips.json` |
| Face: expressions, mouth cells, visemes, eye shape keys | `config/aj_face.json` |
| Preview sheets and measured QA of every starter character | `library/characters/aj/previews/`, `library/characters/aj/qa/` |
| The actor | `tools/blender/stagekit/cast_aj.py` (`ActorAj`), with `aj_rig.py` (hidden control rig that drives the real bones), `aj_face.py`, `aj_hands.py`, `aj_clips.py`, `aj_wardrobe.py` |
| Vendored pack code (fit check, grips, garment templates, hair kit) | `tools/blender/ajkit/` |
| Character tools | `tools/chars_aj/` (`install_pack`, `measure_bodies`, `fit`, `import_fits`, `make_starter_cast`, `clips`, `gate_a_sheets`, `qa`, `look_aj`, tests) |
| Casting a story | `tools/casting.py` (`clip.py casting`), shared rules in `tools/cast_data.py` |

## What a character is

A character is one entry in `config/cast.json > characters`. The pieces:

| Part | What it is |
|---|---|
| `body` | one of the eight bodies below. Sex and age are fixed by it |
| `face` | one of two face presets for that age (shape of the eyes and brows; the head shape never changes) |
| `hair`, `facial_hair` | a style from the hair library and a colour. Beards and moustaches use the same library |
| `outfit` | one fitted outfit from the wardrobe (top, trousers or skirt, shoes: they come as a set) |
| `addons` | tie, belt, blazer, cardigan, lanyard badge, glasses, wrist watch |
| `palette` | colours by slot (`primary`, `secondary`, `shoes`...): which slots exist depends on the outfit |
| `skin` | `porcelain`, `light`, `fair`, `tan`, `olive`, `brown`, `deep`, `dark`, or a hex colour |
| `era` | the periods it may appear in; `plan-check` enforces it |
| `looks`, `tags` | words that casting matches against a plan's `wants` and `reads_as` |
| `avoid` | the reviewers' limits on what it wears, as sentences ("Seated seen from behind: the tee hem forms a rounded lip"). They travel with the character into `clip.py cast`, `casting.md` and the plan check. A builder reads them before staging |
| `status`, `approved` | `draft` until the user approves it at Gate A. A draft may be filmed; the plan check says so |

The eight bodies (heights from the measured body records; the world scales every Aj by 0.9, set in `config/cast.json > families.aj.world_scale`). The table is generated from `library/wardrobe/index.json` and `config/cast.json`; do not edit the numbers by hand.

| Body | Height (model / x0.9 in the world) | Face presets | Starter characters | Outfits accepted | Add-ons accepted |
|---|---|---|---|---|---|
| `Male_Kid` | 1.46 m / 1.31 m | Kid Bright, Kid Round | 3 | 3 | 7 |
| `Male_Teen` | 1.80 m / 1.62 m | Teen Classic, Teen Tapered | 3 | 6 | 7 |
| `Male_Adult` | 1.97 m / 1.77 m | Adult Broad, Adult Sculpted | 6 | 6 | 7 |
| `Male_Senior` | 1.87 m / 1.68 m | Senior Soft, Senior Strong | 4 | 6 | 7 |
| `Female_Kid` | 1.46 m / 1.31 m | Kid Bright, Kid Round | 3 | 8 | 7 |
| `Female_Teen` | 1.80 m / 1.62 m | Teen Classic, Teen Tapered | 4 | 10 | 7 |
| `Female_Adult` | 1.93 m / 1.74 m | Adult Broad, Adult Sculpted | 6 | 9 | 7 |
| `Female_Senior` | 1.84 m / 1.66 m | Senior Soft, Senior Strong | 3 | 7 | 7 |

A character may wear an outfit or add-on only if its fit on that body is `pass` (the measured fit check) **and** the independent review is `accept` (rigid add-ons need no review). 32 starter characters exist, all `modern`, all `draft`, all with hair under the owner's approved plan (see Known limits).

### Outfits (x = fit passed the check and the review accepted it on that body)

| Outfit | Period | Licence | M Kid | M Teen | M Adult | M Senior | F Kid | F Teen | F Adult | F Senior |
|---|---|---|---|---|---|---|---|---|---|---|
| `pants_top` | modern | cc0 | | | | | x | x | x | |
| `jeans_shirt` | modern | royalty_free | | x | | x | x | x | x | x |
| `casual_tshirt_trousers` | modern | own | x | x | x | x | x | x | x | x |
| `shirt_trousers` | modern | own | x | x | x | x | x | x | x | x |
| `kid_tshirt_shorts` | modern | own | x | x | x | x | x | x | x | x |
| `blouse_skirt` | modern | own | | | | | x | x | x | x |
| `blouse_trousers` | modern | own | | | | | x | x | x | x |
| `dress_simple` | modern | own | | | | | x | x | | |
| `king_robes` | medieval | own | | | x | x | | | | |
| `guard_tabard` | medieval | own | | x | x | | | | | |
| `peasant_man` | medieval | own | | x | x | x | | | | |
| `peasant_woman` | medieval | own | | | | | | x | x | x |
| `kitchen_maid` | medieval | own | | | | | | x | x | |

### Add-ons (all eight bodies)

| Add-on | Kind | Notes from the reviewers |
|---|---|---|
| `tie` | skinned | a plain strip with no knot: keep neck close-ups loose |
| `belt` | skinned | bends into a wavy ribbon over the seat from behind or the side at close range |
| `blazer`, `cardigan` | skinned | usable standing and in medium shots; balloon over the seat when seated; a standing collar at the back of the neck |
| `lanyard_badge` | skinned | no strap behind the neck: keep back and side close-ups wide |
| `glasses` | rigid, on the head | large; the lens is noisy in a close look sheet |
| `wrist_watch` | rigid, left forearm | tiny; left wrist only; only in hand close-ups |

The `era` tags `early_modern` and `fairy_tale` on the period outfits are not plan eras (`config/cast.json > eras`); only a `medieval` world (and `fantasy`, through medieval) accepts them.

## How to see the cast

```
py -3 tools/clip.py cast                      # every character: body, outfit, period, status; then the outfits and add-ons and who may wear them
py -3 tools/clip.py cast ManagerBlazer        # one character in full: face, hair, colours you may recolour, what can be hidden, what else fits its body, AVOID limits, QA result, its sheet
py -3 tools/clip.py cast --era modern         # only one period
py -3 tools/clip.py cast --rescan             # run make_starter_cast again (it picks up newly accepted outfits) and check the registry
```

Pictures: `library/characters/aj/previews/<Name>.png` is a sheet per starter character (front, three-quarter, side, back; five faces; one action pose; a height line-up) and `_lineup.png` is all of them together. For a film, `py -3 tools/clip.py cast-sheets <clip>` draws the same sheet for every character of the plan **in the costume the plan gives them** (`review/cast/<id>.png`, `lineup.png`, `<id>.qa.json`) and is Gate A.

## Casting a story

The director names each role in the plan's `cast[]` with a `base` (the nearest character), an optional `wants` (`sex`, `age`, `era`, `tags`, `hair`, `facial_hair`, `palette_hint`) and a per-clip `costume` (`recolor`, `hide`, `wear`). Then:

```
py -3 tools/clip.py casting <clip>            # writes casting.json and casting.md; exit 0, or exit 2 when anything is MISSING
py -3 tools/clip.py casting <clip> --apply    # registers ADAPT results in config/cast.json as drafts and points the plan's base at them
```

| Result | Meaning | What happens next |
|---|---|---|
| **EXISTING** | the base exists and satisfies `wants` (body, period, outfit and add-on words, hair, beard) | nothing. Its `avoid` limits are listed in `casting.md` |
| **ADAPT** | the closest body (sex and age are hard filters), dressed only from accepted wardrobe: the exact change (outfit, add-ons, palette, hair, beard, face, skin) is written out | `--apply` files it as a draft character so later films reuse it |
| **MISSING** | something nothing can satisfy, written as an explicit ask: a wardrobe item (what, which body, how to get and fit it), a hairstyle, missing facts (`wants.sex` / `wants.age`), or a Mixamo clip (the exact download request) | the run stops. Do not invent a stand-in: see "Adding" below, or tell the owner what is asked |

The same input always gives the same output (no clock or randomness; where the rules leave a free choice a checksum of the character id picks). Gate A shows the result to the user; `stills` and `render` exit 4 until it is approved.

## Acting on an Aj

The actor API is the one every shot already uses (`stagekit` skill): `cast.from_plan("maya", at=..., face="left")`, `a.do(...)`, `a.walk(...)`, `a.expr(...)`, `a.hold(...)`. What differs because the skeleton is real:

**Named actions are unchanged.** `a.do("pick_up", ring, hit=shot.t("picked up"))` plays a timed performance with anticipation, motion and settle. The catalogue is `py -3 tools/clip.py actions [word] -v`, from `config/actions.json`. Some actions move the whole body and, on an Aj, are **clip-backed**: they play a Mixamo clip.

| Clip-backed | Clip | What to know |
|---|---|---|
| `walk`, `pace`, `step_forward`, `haul` | `Standard_Walk` | `a.walk(t0, to=(x, y), speed=, cycle=, arms=)` turns on the spot first, then walks straight; the stage moves exactly as the planted foot does, so feet do not slide; it eases out to a standing pose on the goal and returns the arrival time. Chain from that time |
| `run`, `chase` | `Standard_Run` | `cycle="run"` |
| `sneak`, `tiptoe` | `Sneak_Walk` | `cycle="sneak"`. On `Male_Senior` the standing walk, slow and crouched, stands in (the clip's contacts cannot be found on his bent knees: `body_overrides` in the registry says why) |
| `sit_down`, `sit_idle`, `stand_up` | `Stand_To_Sit`, `Sitting_Idle`, `Sit_To_Stand`, `Kneel_To_Stand`, `Getting_Up` | `sit_down(on=seat)` puts the hips at the seat's real top. `sit_idle` only works after `sit_down`. `stand_up` knows whether the figure is sitting, kneeling or lying |
| `kneel` | `Kneeling_Down`, `Kneeling_Idle` | |
| `lie_down`, `sleep`, `get_up`, `wake_up` | `Getting_Up` played backward (then `Laying_Idle`), `Sleeping_Idle`, `Getting_Up` | `lie_down` is the get-up reversed and faster, because a blend into `Laying_Idle` swung the legs through the floor. `sleep` on a standing figure is the procedural nod-off |
| `fall`, `slip` | `Falling_Back`, `Stumble_Backwards` | backward only. `fall(forward=True)` still falls back and writes a shot note. `slip` ends seated on the floor |
| `jump` | `Jump` | `jump(to=...)` (a hop to a point) stays procedural |
| `salute` | `Salute` | the legs stay with the figure; `target=` makes the head look at it |
| `idle` | `Standing_Idle`, `Happy_Idle` | `a.idle()` fills every gap where nothing else moves the body, so people shift their weight instead of freezing. Call it last, on everyone |

`py -3 tools/clip.py clips --check` says which clips are registered, on disk and analysed (22 now). A clip you play directly: `t1 = a.play_clip("Sitting_Idle", t0, loop=True, until=t)`.

**Timing and `hit=`.** A clip has a fixed shape. The action's key moment (the seat touches, the back meets the floor, the hand reaches the brow) was measured when the clip was registered (`events_s` in `config/mixamo_clips.json`). `hit=` puts that moment on the word, so the **action starts earlier than the word**, by the clip's lead (a sit starts about 1.5 s before the seat). Leave that time free: do not stage something else in the legs of that figure before the lead. `speed=` changes the tempo of the clip; do not stretch it more than a little, a clip played at the wrong pace looks wrong. Positions: after a travelling clip the actor's position is where its body is, and the next clip starts from there.

**Layers over clips.** A clip owns joint groups (`legs`, `spine`, `arm.L`, `arm.R`, `head`). The face, the eyes and the fingers are separate channels and always procedural. An arm the clip does not own is posed by the actor API on top of the clip's spine: a figure can walk and carry, point or wave. An arm that is holding a prop stays with the actor API. `head_turn` and `tilt_head` are added to the clip's head. `a.walk(arms=False)` leaves the arms as you posed them. A clip blends in over `blend` seconds from whatever the figure was doing and the figure holds its last pose when it ends: nothing pops.

**Hands.** Six shapes: `mitten` (the relaxed rest), `open`, `pinch`, `fist`, `point`, `grip` (`a.hand("R", "point", t)`). `a.hold(prop, "R", t, offset=)` makes the prop go with the hand. The grip solver closes the real finger bones on the prop's real surface. Which grip a prop gets comes from its `grip` field in `library/assets/index.json` (or the wardrobe `props` entry), else from its shape:

| `grip` | For | Behaviour |
|---|---|---|
| `power` | a rod or handle (stick, broom, hammer, bag strap); `grip_at` says how far up it is held (0 lower end, 1 upper) | fist round the handle |
| `pinch` | a small thin thing (key, card) | between thumb and index |
| `palm` | a box, ball, book, cup, phone, laptop | rests against the palm, fingers close onto it |
| `palm2` | anything wider than 30 cm (tray, basket, box) | the prop is brought to the palm, the other palm goes to the opposite face |
| `none` | not a held thing | no grip is solved |

`hold(..., grip=False)` for a bag that hangs from a strap (it follows the fist and stays upright); `turn=True` makes a plain hold turn with the hand. A wide prop that lies far away is brought to the palm first. `a.release(prop, t)` leaves it where the hand was. Reaches put the **palm** (not the wrist) on a target; `a.reach("R", point, t)`, `a.do("press", reader, hit=..., palm=True)` for a flat hand.

**Faces.** `a.expr(name, t, amount=)` with `neutral, happy, laugh, grin, excited, surprised, worried, scared, angry, sad, weeping, crying, sly, sleepy, wink`. An expression is brow and eyelid shape keys plus **one mouth cell**; the mouth is a drawn 2D atlas on the head (12 cells) and is **never changed in 3D**. While `a.speak("first words", "last words")` runs, visemes pick the mouth cells; the cell switches like a drawn mouth (constant interpolation). Change the face two to four frames before the body moves. `a.eyes(dx, dz, t)` points the eyes (dx +1 toward the facing side, dz +1 up); the eyes lead the head by about 0.25 s. `a.blink(t)` and `a.eyes_closed(t0, t1)` shut the lids.

**Seating and the limits.** The plan check warns when an action that seats someone hits a character whose `avoid` mentions seating. Read `avoid` for every character in the shot (it is printed in `casting.md` and `clip.py cast <Name>`) and frame to it: a blazer or cardigan seated, seen from behind or the side, is a bag over the seat.

## Adding a character

Reuse first. Stop at the first step that works.

1. **Reuse** an existing character. `clip.py cast`, `clip.py cast --era <era>`.
2. **Re-dress in the plan.** Same body, other colours or an add-on: the plan's `costume` (`recolor`, `hide`, `wear`). `recolor` takes palette slots, `hair`, `facial_hair`, `skin`, or a garment's own name; `hide` takes `hair`, `facial_hair`, `<outfit>.<piece>`, `addon:<item>` (refused when it would leave the body bare); `wear` takes an add-on this body may wear. This needs no new file.
3. **A per-clip adaptation.** A different hair, beard, face, skin or outfit for one story: `wants` in the plan, then `casting --apply`, which files a draft character. Only accepted wardrobe is used.
4. **A new starter recipe** when the person will come back: add a recipe to `tools/chars_aj/make_starter_cast.py` (body, face preset, hair, beard, a list of outfits in order of preference, add-ons, palette, skin, tags). Run `py -3 tools/chars_aj/make_starter_cast.py --dry`, then without `--dry`. It takes the first outfit of the list that is accepted on that body and writes the character with `status: "draft"` and `avoid` limits. (A single hand-written person can instead go in as a fragment: `py -3 tools/cast_registry.py merge <fragment.json>`.) No two characters should share silhouette and colours. Then `py -3 tools/clip.py cast --rescan`, `py -3 tools/cast_registry.py check`, `py -3 tools/chars_aj/qa.py <Name>`, and `blender -b --factory-startup --python tools/chars_aj/gate_a_sheets.py -- --char <Name>` for its sheet.
5. **A garment nobody has made**: see the next section. **Never put an unfitted garment on a body**, not even for one shot: it passes through the skin or floats, and the checks only exist to stop that.
6. **Ask the owner** for what the pipeline cannot supply: a new body, a hair style, a Mixamo clip, a licence confirmation.

A special body (ghost, dragon, robot, a child with a tail) does not exist in this cast. Do not fake one: ask.

## Adding a garment

A garment is **generated from each body's own surface** (`tools/blender/ajkit/templates.py`): cut from that body's skin, shaped, finished with hems and collars, bound to that body's bone weights. It follows the body by construction. A third-party rigged garment from BlenderKit (CC0 or royalty-free only) can be fitted with the pack's fitter (`fit.py prep`, `fit.py rigged`); generated is preferred.

```
blender -b --factory-startup --python tools/chars_aj/fit.py -- custom <outfit> --bodies all [--params piece.key=value,...] [--jobs 2]
blender -b --factory-startup --python tools/chars_aj/fit.py -- addon <item> --bodies all
blender -b --factory-startup --python tools/chars_aj/fit.py -- check <file.blend>        # run the fit check on a dressed file (opened, never saved)
blender -b --factory-startup --python tools/chars_aj/fit.py -- review <outfit> --bodies all   # review sheets of each fit
py -3 tools/chars_aj/fit.py index-check      # validate the registry; also: limits, recompute
```

1. Add the outfit to `templates.OUTFITS` (or the add-on to `templates.ADDONS`): its pieces, template per piece (`top`, `trousers`, `shoes`, `skirt`, `belt`, `crown`), fabric, colours, `per_body` overrides, era, tags.
2. `fit.py custom` builds it on each body and runs the **unchanged** fit check (`ajkit.fitcheck`: rest pose, a mask, six poses). A fit is saved (`library/wardrobe/fits/<Body>/<outfit>.blend`, filed in `library/wardrobe/index.json`) **only when it passes**. A failure goes to `output/_staging/wardrobe/<outfit>/<Body>/` with its report.
3. **The limits are never loosened.** `tools/tests/cast/test_fit_limits.py` records digests of `LIMITS` (zero crossings; skin through cloth at most 0.5 mm at rest and 3 mm in poses; cloth at least 1.5 mm from the skin; stretch 0.5 to 1.8 in poses...) and compares the vendored code with the pack's. Fix the garment, not the limit. Run `py -3 -I tools/tests/cast/test_fit_limits.py`.
4. `fit.py review` makes the review sheets. An **independent review** (a person or a separate reviewing agent that did not build it) looks at them and writes `library/wardrobe/reports/<outfit>/<Body>_review.json` with `review: accept` or `reject` and the **limits** in `avoid`. `fit.py` never sets `accept` itself: the review verdict is someone else's. Then `py -3 tools/chars_aj/fit.py recompute` and `index-check`.
5. **What `avoid` means.** An accept is "accept with notes": the garment is usable inside the limits written there (do not seat this character seen from behind; keep the collar out of tight close-ups). Every starter character carries the union of the limits of its outfit and add-ons.
6. **Licence.** Third-party items are used only when CC0 or BlenderKit royalty-free, recorded from the asset's own metadata. Unknown licences are quarantined. See `library/wardrobe/README.md`.
7. Then `py -3 tools/clip.py cast --rescan`, so starter recipes can use it.

## Adding a Mixamo clip

The pipeline only plays clips that are registered and on disk. Everything else stops.

1. Ask the registry what to download: `py -3 tools/clip.py clips --ask <Name>` prints the Mixamo search words, the title to pick and the exact settings. In short: on mixamo.com, **upload the character** `packs/aj_rebuild_v1/09_Animations/Aj_upload.fbx` once per account; download **FBX Binary, Without Skin, 30 fps, Keyframe Reduction none, In Place ticked** where the option is offered (and Mirror ticked for a mirrored clip); save as `library/characters/aj/mixamo/<File>.fbx`.
2. A clip not in the registry yet: add its entry to `config/mixamo_clips.json` by hand (`file`, `mixamo_title`, `search`, `in_place`, `loop`, `kind`, `owns`, `actions`).
3. `py -3 tools/clip.py clips --register <Name>` analyses it in Blender (duration, root travel, foot contacts, the event times `hit=` needs) and writes the measured fields. `py -3 tools/clip.py clips --check` verifies every file against its recorded sha256.
4. To make an action use the clip: add it in `tools/blender/stagekit/aj_clips.py` (`ACTIONS`) and follow `docs/ADDING_NEW_ACTIONS.md`.

**The MissingClip stop.** If a shot needs a clip that is not there, the build stops (it does not substitute), prints the exact request, writes `MISSING_DOWNLOADS.md` in the clip folder and exits **5**. `py -3 tools/clip.py clips --need <clip>` lists every clip a clip folder's shots need (exit 2 if any is missing). Pass the request to the owner; do not fake the motion.

## Character QA and the Gate A sheet

```
py -3 tools/chars_aj/qa.py <Character> [--clip <clip dir>] [--no-actions]
```

Measured, not judged, in Blender, on the character as the pipeline builds it: armature (bone names, count, rest pose against the pack's body), mesh (vertex count, the shape keys the face needs, head vertices unmoved), materials (no empty slot, drawn-mouth controller present, the skin material this actor's own), wardrobe (fit-accepted on this body, licence cc0, royalty-free or own; hair licence is a warning while the registry says `unknown`), hair (inside the neck and shoulders at rest and with the head turned: limit 2 mm; **known: the kids' hair enters their necks**), proportions, rig (control joints against the bones: 0.5 mm) and the core actions. It writes `library/characters/aj/qa/<Character>.json`, or `<clip>/review/cast/<id>.qa.json` with `--clip`. **A character with blocking items is not reported as ready**; its sheet is stamped in red.

Gate A (`py -3 tools/clip.py cast-sheets <clip>`, then the user decides with `clip.py gate <clip> A --approve | --revise "..."`) shows, per character: four turns, five faces, an action pose holding a prop, and a height line-up against a 2.0 m door and the rest of the cast. Look at the sheets (send them to the user), not only at the QA numbers.

## Rules from the pack owner

These always hold. They are why a character looks like itself in every film.

- **Never change the head shape.** Faces are presets of the same head.
- **Never change the mouth in 3D.** It is a 2D atlas driven by `Mouth_Index`; `Jaw_Drop` and the mouth shape keys are never keyed.
- **Never rename bones or change rest poses.** 83 bones, `mixamorig:` names, the pack's rest pose.
- **The base keeps its feet.** Outfits add shoes; they do not take the feet away.
- **Never loosen a fit limit.** Fix the garment.
- **Open pack `.blend` files read-only.** Append from them; never save them. Everything is appended, never linked.

## Installing the pack on a new machine

The pack is licensed for use, not redistribution, so it is not in git. Put `Character_Rebuild_Video_Pipeline.zip` in the repository root and run:

```
py -3 tools/chars_aj/install_pack.py            # unpack into packs/aj_rebuild_v1/ and verify every file against its MANIFEST.csv (size and SHA-256)
py -3 tools/chars_aj/install_pack.py --check    # verify only
blender -b --factory-startup --python tools/chars_aj/measure_bodies.py   # measure the eight bodies into library/characters/aj/bodies/
blender -b --factory-startup --python tools/chars_aj/import_fits.py      # bring the pack's own accepted fits (jeans_shirt, pants_top) into library/wardrobe/fits
```

Gitignored, and so to be copied or rebuilt on a new machine: `packs/*`; `library/characters/aj/hair/*.npz` (the hair library); `library/characters/aj/mixamo/*.fbx` (22 clips: download them with `clips --ask`); `library/wardrobe/fits/**/*.blend` (the fitted outfits: rebuild with `fit.py custom`, and `import_fits.py` for the pack's own two). Committed: the 56 add-on fits in `library/wardrobe/addons/`, the registries (`config/cast.json`, `config/mixamo_clips.json`, `config/aj_face.json`, `library/wardrobe/index.json`), the reports, the measured body records, the hair index, previews and QA results. `py -3 tools/clip.py doctor` reports Blender, FFmpeg and the like; its "character pack (2D)" line is stale and does not check the Aj pack, so use `install_pack.py --check` and `clips --check`.

## Known limits

Honest, from the reviewers' reports (`library/wardrobe/reports/REVIEW_2026-11-27.md`, two rounds) and the code. Plan to them; do not hope.

- **No outfit is unreservedly film-ready.** The first review round judged 52 outfit pairs and the second 88 (outfits and add-ons): none was a plain accept, all the rest were "accept with notes" (round one rejected 10, mostly period outfits and male `blouse_skirt`). The cleanest are `shirt_trousers` and `blouse_trousers` (tucked, real shoes, clean seat), then `casual_tshirt_trousers`. Keep medium and wide shots, and read `avoid`.
- **Blazers and cardigans balloon over the seat** when the figure sits, and stand up as a funnel collar at the back of the neck. Standing and medium shots only; do not seat them seen from behind or the side.
- **Tops that reach the hips bag when seated** (`casual_tshirt_trousers`: a rounded lip; `kid_tshirt_shorts`: the tee hangs in a bag over the shorts). A skin patch shows between the thighs under the front hem of `blouse_skirt` when seated, seen from the front.
- **Kid cuts of `shirt_trousers`** read as a child's blouse (puffed sleeves above the wrist, round collar). `blouse_skirt` on male bodies was rejected and not rebuilt; it is not offered.
- **Long hair and hats.** Hair and beards are sculpted stiff shapes: they do not swing or drape. Long hair is lifted off the neck and shoulders at build time but is not simulated. There are no hats in the wardrobe, and no hair-under-hat handling.
- **Two-handed carrying and some grips fall back.** When the grip solver's penetration is above its 1.5 mm limit (seen on cards and some wide props in the first test film), the hand uses the plain `grip` shape and the shot notes say so; check the close-up. A second hand on a wide prop that cannot be solved is left open with a note.
- **No self-contact guard.** Nothing stops a hand passing through the figure's own body or head (a prop brought to the face, arms crossed). Check these frames by eye.
- **Fall and slip scrape.** `Falling_Back` and `Stumble_Backwards` are the only fall clips and the feet can drag on the floor as the body goes down; look at the strip before relying on them. A forward fall is not possible.
- **Clips assume a flat floor**: no stairs or uneven ground, and a walk turns on the spot first rather than curving.
- **The hair library's licence is `unknown`** in the registry (Tripo3D output made by the project owner; the generator's plan terms were never confirmed). It is used under the owner's approved plan, every character with hair carries a `licence_note`, and QA shows a warning. When the owner confirms, set `hair.licence` to `own` and `hair.usable` to true in `library/wardrobe/index.json`.
- **Period and royal wardrobe is not usable yet.** There are no medieval starter characters. `king_robes` is a knee tunic that reads as a prince; `queen_gown` and `knight_armour` were rejected and are not offered; the peasant, kitchen-maid and guard pieces are usable with limits. There is no east-asian, renaissance, age-of-sail or victorian clothing at all.
- **Eight body shapes only**, two faces per age, a fixed list of skin tones. Two characters of the same body and outfit differ only in hair, face, skin and colour.
