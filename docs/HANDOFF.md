# Handoff: the pipeline upgrade (27 November 2026)

For the next session, or for you when you come back to this. It replaces the handoff of the 2D-cast version (22 November), most of whose content described a cast that no longer exists.

## Where the project stands

The pipeline turns a script into a narrated 9:16 Short. Four things were rebuilt on branch `pipeline-upgrade-v1`: the characters (3D "Aj" figures on a Mixamo skeleton), the sets (complete, audited places), the camera (a move library with path checks), and the approval gates with blocking checks. Scripts, voice, music, effects, the mix and captions are unchanged from before.

| Part | State |
|---|---|
| Script skills (7), `validate_script.py` | unchanged |
| Voice, music, effects, mix (`tools/audio`, `sound-design`, `sound-designer`) | unchanged, plus `voice --from-media` |
| Shot plan | **format 2** (`tools/plan.py`, `tools/plan_v2.py`, `shot-plan` skill, `director` agent): structured sets (theme, architecture with what is seen through each opening, four layers, practicals, atmosphere, details, `must_survive`, marks), a camera design per view (move, angle, side, framing, how it is entered), line of action, `transition_in` per shot |
| Cast | Aj characters: `config/cast.json` (8 bodies, draft starter characters), `library/wardrobe/` (outfits and add-ons with fit checks and licences), `tools/chars_aj/`, `stagekit/cast_aj.py`, `aj_rig.py`, `aj_face.py`, `aj_hands.py`, `aj_wardrobe.py`. `clip.py casting` matches a plan to the registry and says what is MISSING. Few outfits pass the fit check yet (`jeans_shirt` on six bodies, `pants_top` on three): see `library/wardrobe/README.md` |
| Motion | Mixamo clips (`library/characters/aj/mixamo/`, registry `config/mixamo_clips.json`, `tools/chars_aj/clips.py`, `stagekit/aj_clips.py`): `actor.walk`, `play_clip`, and the clip-backed actions (sit, kneel, lie, fall, jump...) |
| Sets | `stagekit/arch.py` (rooms with real openings, vistas, cutaway), `furnish.py` (about 140 pieces), `dress.py` (15 themes), `audit.py` (measures the set against `style.json` > `sets`), `lights.py`; worked sets in `examples/sets/`; `tools/blender/set_preview.py` and `clip.py setpreview` |
| Camera | `stagekit/camera.py` (moves, helpers, line of action), `campath.py` (path checks), `tools/blender/cam_preview.py` and `clip.py preview`; cookbook `tools/tests/camera/test_moves.py` |
| Gates | `tools/gates.py`, `clip.py gate`; A characters, B sets, C camera; `stills`, `render`, `assemble` exit 4 without them |
| Checks | `stagekit/review.py` grades every finding `block` or `warn` in `checks.json`; `stills` exits 3 while any blocks; motion strips per move |
| Transitions | `transition_in` per shot read by `tools/assemble.py`, drawn by `remotion/src/Transitions.tsx` (whip, dissolve, dip, flash, wipe, match) |
| Captions, QA | unchanged: `tools/captions.py`, `remotion/src/Captions.tsx`, `tools/qa.py` |
| Agent instructions | rewritten for all of the above: `gen-clip` (the three stops), `director`, `shot-builder` (SET and STAGE modes), `frame-reviewer` (SHOT and FINAL-FILM modes), `asset-maker`, skills `shot-plan`, `stagekit`, `cinematic-style`, `asset-library`, `style/STYLE_GUIDE.md` |
| Worked example | `examples/sets/` (throne room, office). `examples/the-ring-in-the-pond/` is a plan and shots in the older format with a deleted 2D cast: good reasoning about views, not a model for sets, cast or camera |

## The ideas the rebuild rests on

1. **A shot is a staged take; a view is what the viewer sees.** Views are many (the references hold 22-33 framings a minute), each starting on the narrator's words, mostly reached by the camera moving inside one place and by camera-event transitions between places.
2. **One world, enforced.** The plan names a period; every character, wardrobe item, surface and asset carries period tags and `plan-check` refuses a mismatch.
3. **Sets are complete places**, built from marks outward and measured against numbers (14 kinds of prop, 60 objects, four layers, 3 practicals, atmosphere, 3 readable details, no void behind an opening, no floating or intersecting pieces).
4. **The camera is designed per view** with a reason, kept on one side of the line of action, and its path is measured.
5. **The user decides three things from pictures**, early, and the tools hold the line.
6. **Captions and pictures share one clock.** Both come from the word times in `timing.json`.

## The gate workflow

`/gen-clip` stops three times, in this order. The producer sends the previews into the chat (the user may be on another device), asks one question (approve or request changes), records the answer, and loops on changes.

| Gate | After | Previews | Command |
|---|---|---|---|
| A, characters and wardrobe | `casting` has nothing MISSING | one sheet per character in costume, a lineup | `clip.py cast-sheets <clip>` |
| B, sets | the sets are built and audited | six-angle sheets per set and light mood | `clip.py setpreview <clip>` |
| C, camera | shots staged, `stills` has zero blocking items | a low-res motion film and a camera path diagram per shot | `clip.py preview <clip>` |

- Record a decision with `clip.py gate <clip> <A|B|C> --approve --by "user in chat"` or `--revise "<change>"` (repeatable). `clip.py gate <clip> --json` shows every gate and whether it is `stale` and why.
- A gate's fingerprint covers only its own inputs (A: cast, world, casting, the registry entries used; B: the plan's sets and the set files; C: the shot files and `timing.json`). Later work does not reopen an approved gate unless one of those moved; then it is stale and needs a new decision.
- **Unattended runs** happen only when the user's own message asks for them in words (`clip.py gate <clip> --autonomous --reason "<their words>"`). Every preview is still produced and sent, the gates are recorded as bypassed, never approved, and the final report says so.
- A MISSING from `casting` (a garment, a hairstyle, a Mixamo animation) stops the run and the producer tells the user exactly what is needed.

## Working agreements

- The character pack stays out of git (`packs/` is git-ignored); finished pack `.blend` files are opened read-only.
- Pack owner rules that always hold: never change the head shape; never change the mouth in 3D (it is a 2D atlas driven by `Mouth_Index`); never rename bones or change rest poses; never loosen a fit-check limit.
- Agent instructions stay lean: tools and examples of good decisions, not long rule lists.
- **The user's approval gates are part of `/gen-clip`** (see above). The agents never decide for the user what the gates are for.
- Licence rule: only CC0 or BlenderKit Royalty Free for third-party assets, recorded per item (own generated geometry is `own`).
- Plain language; lead with what to do.
- No paid tools added without asking. (ambientCG is free and CC0; the optional speech model for `qa --listen` is free and runs offline.)
- The seven `script-*` skills are not edited without asking.
- A skill and its validator must agree (`shot-plan` skill with `tools/plan.py` and `tools/plan_v2.py`).

## What has been run, and what has not

- The camera moves, the architecture and furniture kits, the audit, the set themes, the gates, the plan schema and the transitions each have tests under `tools/tests/` (written and run by the agents that built them; this file was not checked by re-running them). The Aj actor, the Mixamo clips and the casting tool have their own tests under `tools/chars_aj/` and `tools/tests/cast/`.
- **No complete `/gen-clip` run has been made end to end with the rewritten agents and skills.** The instruction files were written from the code and its tests; the agents have not yet exercised them. Expect to fix wording the first time a real run shows a step the text got wrong.
- Final-quality rendering time and look on the target machine (RTX 5060, 8 GB) of the new sets and characters has not been measured as a whole film. `render` carries on in smaller chunks if Blender runs short of memory.
- ambientCG downloads (`materials fetch`) and BlenderKit (`bk-search`, `bk-fetch`) need the network and the user's add-on login; ElevenLabs needs the API key (`--mock` makes placeholder audio).

## Known limits and next steps

- **Few wearable outfits.** King, Pirate, Soldier and Roman Warrior fail the fit check on all eight bodies; Male_Adult and Male_Kid have no accepted outfit. Period stories outside "modern" will hit a MISSING in `casting` until garments are fitted (`library/wardrobe/README.md`, `candidates.json`).
- **Starter characters are drafts**, and the jumpers of the original starters were replaced by fit-checked outfits.
- **Clips need a flat floor.** Stairs, slopes and turning while walking are not handled by the clip layer; stage around them or cut.
- **Grips**: the solver closes the fingers on a handle (a rod under 7 cm thick) or a small thin thing; other props rest in the palm.
- **Reach is solved for the pose at the time it is called.** Call `reach` again after the target moves.
- **Animals** are not in the cast; build simple solid shapes or stage around them.
- **The plan validator still warns above 24 views** while the reference films hold 22-33 framings a minute; the director keeps the warning with a reason. `style.json` > `views` > `per_short` should move once the worked example in the `shot-plan` skill has that many views.
- `README_3D_CAST.md` at the repository root still describes the retired 92-character cast and its lineup pictures; it should be removed or rewritten.
