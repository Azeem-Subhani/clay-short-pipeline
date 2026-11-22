# Diagnosis: why the first *Ring in the Pond* looked the way it did

What was examined: the delivered project ZIP (every tool, skill and agent file), the previous session's handoff, the rendered `the-ring-in-the-pond.mp4` (47.7 s, sampled at 1 fps and frame by frame for the captions), and the source script. The clip folder of that run (plan, shot code, timing) was not in the ZIP, so the plan itself could not be read; what it must have said is inferred from the render and from what the tools allow.

## The render against its script

| Beat | Script asks for | Render shows |
|---|---|---|
| challenge (0–9 s) | A queen in a red dress **gasps** as the ring **falls from her hand** | A long-haired girl in a red jacket and trousers with a crown. One arm held straight out for nine seconds. No gasp: the old characters had no mouth. The ring is a few pixels at her fingers; its fall is a one-second insert at 3 s. One framing from 0 to 8.9 s. The first 0.17 s is a fade from black. |
| catch (9–17 s) | The queen **holds up one finger**; three people listen; the gate stands at the far end | The queen from behind at the bottom of frame, arm still out. Three small figures far left: a blue police uniform, a purple business suit, a green T-shirt. The "gate" is an empty timber door frame; nothing shows it holding water. The pond has a flat white rim like a swimming pool. One framing for 8 s. |
| attempt one (17–25 s) | A proud **soldier swings** from a branch; it snaps | A policeman (peaked cap, tie, badge) hangs motionless from a branch for 6 s. The branch snaps at 23 s; he ends as a head in flat white rings. |
| attempt two (25–34 s) | A rich man **in fine clothes** at sunset pulls an empty net | A man in a purple modern suit and yellow tie holds a pole in one hand without moving. The net insert with the ring dropping through is the best idea in the film and reads well. |
| attempt three (34–47 s) | The gardener holds the ring up in the empty pond **as the queen laughs** | A figure in a T-shirt and straw hat. The gate board slides up and the water level drops, but there is nowhere for the water to go. The queen is a small figure in the background with no expression. |

## Causes, by stage

### 1. Casting had no idea of a period (the mixed world)

- The old pack (`release_1`) offered six presets (`preset_father`, `preset_boy`, `preset_king`, `preset_female`, `preset_police`, `preset_pirate`) and three bases (`base_hoodie`, `base_shirt_tie`, `base_tshirt`). There was no soldier, no rich man, no gardener and no dress, so the director took the nearest body: **police for the soldier, shirt-and-tie for the rich man, T-shirt for the gardener, the generic female with a crown for the queen.**
- Nothing in the project carried the word *period*. `tools/plan.py` checked that cast ids existed and nothing else. The director's instruction was "choose the cast from the pack, one clear colour per character", so it chose by colour. The reviewer's five questions never asked whether the people belong to the place.
- The characters had no mouths ("Mouth acting: the characters have no mouth", old style guide), so the two reactions the script is built on, the gasp and the laugh, could not be performed.

**Now:** a new pack with 28 characters, each tagged with the periods it belongs to (`config/cast.json`); a wardrobe that turns a pack character into the role (recolour, remove parts, add hat / ruff / apron…); `world.era` in the plan; `plan-check` refuses a police constable in a medieval story; faces have five expressions and talking mouths.

### 2. Sets were single-colour primitives by design (the simplistic look)

- `stagekit.build` made everything from bevelled boxes, cylinders and balls with one matte "clay" material per object. Trees were three balls on a cylinder. The old style guide required it: "One material language. Everything is matte clay… palette colours."
- BlenderKit was step two of asset sourcing, but `bk_fetch.py` had never run against the service, and ambientCG was not wired in at all, so in practice every set was built from the primitives.
- The example sets shipped with the project were, in the handoff's words, "sparsely dressed". Agents copy examples.
- No rule asked a set to explain the story's mechanism. A gate that "held the water in" was built as a door frame.

**Now:** the clay look is retired. Surfaces are named materials (`castle_stone`, `cobblestone`, `oak_planks`, `pond_water`…) that use scanned ambientCG textures when downloaded and matching procedural stand-ins when not. The kit builds masonry with battlements, towers, arched doors, trees with lumpy crowns and real branches, a pond with a rim of separate stones, a working sluice with a channel, plants, and props. A set file starts from a table of marks: where each person stands and where each story object is.

### 3. The cut rule produced nine-second frames with nothing in them

- `style.json` set "4–5 shots", the validator rejected more than 8, and the reviewer was told "never suggest adding a cut". This was a correction for an earlier version with 32 cuts in a minute, and it over-corrected: five framings in 47 s, each about 9 s, with a camera move of "5–15% of the distance".
- The references use 22 and 33 framings in a minute with only 10–14 hard cuts. The missing idea was the difference between a **cut** and a **view**: the camera can show many things in one place without the viewer being thrown anywhere.

**Now:** a shot is one staged take in one set (a render unit; the pond film has four). The viewer sees it through *views* (the pond film has twenty), each with the words it starts on, what it shows and why. A view begins with a cut or with a travel move.

### 4. Action was posed, not performed

- The script's verbs (gasps, holds up one finger, swings, pulls, laughs) each became one static pose held for the length of the shot. The plan format had `staging` as free prose and nothing checked that a verb became motion.
- The reviewer saw at most five quarter-size stills per shot, so a figure frozen for nine seconds looked fine in review.

**Now:** the cast API is built around acting beats (expression first, then pose, `reach` for exact hand contact, `hold` / `release` for props, walk cycle with planted feet, squash, shake, blink, speak). Review renders two stills per view, stamped with the words spoken, and flags views that run long with nothing listed inside them.

### 5. Subtitles: the timing was right; the placement and grouping were wrong

Measured on the render, frame by frame:

- **Timing.** The lit word was read from every frame and matched to the recognised narration: 123 of 127 words matched, mean offset +0.08 s (sd 0.11 s). The recogniser's own word starts sit about 0.07 s early, so the highlight was within a frame or two of the voice. ElevenLabs' timestamps and `timing.json` were sound. Timing was not the fault.
- **Horizontal placement.** The caption block was centred at **x = 0.453** of the frame width on every page: 49 px left of centre. `Captions.tsx` laid the text out between the Shorts safe-area margins, and those are not symmetric (5% left, 14% right), so "centred in the safe area" is visibly off-centre.
- **Vertical jumps.** Pages were up to 22 characters at 72 px; longer ones wrapped to two lines, and the block was centred on its own height, so the text jumped: one-line pages occupy y = 1296–1363 px, two-line pages 1255–1390 px.
- **Grouping.** Pages were cut by character count, which split phrases mid-thought and left small words hanging: "gold ring into the / deep castle pond.", "At the far end, a / small wooden gate held", "mud and picked up the / ring.".
- **First frames.** A 6-frame fade from black covered the first caption and the first image while the voice had already started.

**Now:** captions are built by `tools/captions.py` from the same word clock: one to three words, small words joined to the next word, one fixed line at 70.5% of the height, centred on the frame, scaled instead of wrapped, shown 0.08 s before the word. No fade-in. `clip.py qa` measures the centre, the line and the safe area on the finished frames and checks the word times against the audio.

## What was verified in the previous handoff

| Claim | Result |
|---|---|
| The repository should equal the ZIP plus three later files; `status` prints a `next:` line if the update is in | The ZIP received here already prints `next:`. It is the updated version. |
| Blender 5.3.0 through the `bpy` wheel | Confirmed: `pip install bpy==5.3.0` works and was used for everything here. |
| ambientCG and Poly Haven are not wired in | Confirmed. ambientCG is now wired in (`tools/materials.py`, `stagekit.mat`). Poly Haven is still not. |
| Nothing measures geometry; the reviewer sees little | Confirmed in `review.py`. Review now checks feet on the ground, hidden faces, faces under captions, camera inside objects, and renders every view. Limb-through-body checks were not carried over: flat characters do not have that problem. |
| `bk_fetch.py` has never run against BlenderKit | Still true. BlenderKit cannot be reached from the build sandbox. |
| Character pack smoke test, the worked example, the mock-audio run | Could not be re-run: they need the old `release_1` pack, which was not supplied. The old example and the clay code paths have been removed. |
| ElevenLabs default voices retire on 31 Dec 2026 | Not re-checked (ElevenLabs is not reachable from the sandbox). The voice code and `config/voices.json` are unchanged. |

## What was kept as it was

Script skills and `scripts/validate_script.py`; `tools/audio/eleven.py`, `sound.py` and the narration, timing and holds logic of `voice.py`; the mix, ducking and loudness steps of `assemble.py`; `config/voices.json`; the sound-designer agent and the sound-design skill. `voice.py` gained two options (`--from-media`, `--asr-setup`) and nothing else.
