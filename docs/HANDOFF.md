# Handoff: the rebuild (22 November 2026)

For the next session, or for you when you come back to this. It replaces the handoff from the first (clay) version.

## Where the project stands

The visual pipeline was rebuilt around the 2D character pack (`characters_beta_0_3`) staged in a real 3D world. Scripts, voice, music, sound effects, the mix and the final assembly stack are the ones from the first version.

| Part | State |
|---|---|
| Script skills (7), `validate_script.py` | untouched |
| Voice, music, effects, mix (`tools/audio`, `sound-design` skill, `sound-designer` agent) | untouched, plus `voice --from-media` (reuse a recording) |
| Shot plan (`tools/plan.py`, `shot-plan` skill, `director` agent) | rewritten: world and period, cast and costume, sets and marks, shots, views keyed to words, setups |
| Blender toolkit (`tools/blender/stagekit`) | rewritten: `cast` (2D actors), `wardrobe`, `build` (world kit), `mat` (named surfaces), `lights`, `camera` (views), `fx`, `review` |
| Surfaces | `library/materials/catalog.json` + `tools/materials.py` (ambientCG API v3) |
| Captions | `tools/captions.py` + `remotion/src/Captions.tsx`: one centred line, 1–3 words |
| QA | `tools/qa.py` now measures caption placement and timing on the finished file |
| Docs for agents | `style/STYLE_GUIDE.md`, skills `gen-clip`, `shot-plan`, `cinematic-style`, `stagekit`, `asset-library`; agents `director`, `shot-builder`, `frame-reviewer`, `asset-maker` |
| Evidence | `docs/REFERENCE_BREAKDOWN.md` (both reference Shorts, shot by shot), `docs/DIAGNOSIS.md` (what went wrong in the pond video and where) |
| Worked example | `examples/the-ring-in-the-pond/` |

## The ideas the rebuild rests on

1. **A shot is a staged take; a view is what the viewer sees.** Shots stay few (one per place and time of day, so audio and rendering keep their simple contract). Views are many (9–24), each starting on the narrator's words, and are cuts, travels or follows. This is what the reference Shorts do: a new picture every two or three seconds, mostly by moving inside one place.
2. **One world, enforced.** The plan names a period. Every pack character, wardrobe item, surface and library asset carries period tags (`config/cast.json`, `library/materials/catalog.json`, `library/assets/index.json`), and `plan-check` refuses a mismatch. A character can be moved into a period only through a written costume recipe.
3. **Sets start from marks and from the mechanism.** Where people stand and how the ending physically works are decided before any dressing.
4. **Performance is poses with hands that land.** Named poses, eyes-face-body order, `reach` / `hold` / `release` for props, effects on contacts.
5. **Captions and pictures share one clock.** Both come from the word times in `timing.json`.

## Working agreements (unchanged unless noted)

- The character pack stays out of the project ZIP and out of git (`packs/` is git-ignored).
- Agent instructions stay lean: tools and examples of good decisions, not long rule lists.
- No human approval gates inside `/gen-clip`.
- Plain language; lead with what to do.
- No paid tools added without asking. (ambientCG is free and CC0; the optional speech model for `qa --listen` is free and runs offline.)
- The seven `script-*` skills are not edited without asking.
- A skill and its validator must agree (`shot-plan` skill ↔ `tools/plan.py`).

## What was run and looked at in the build sandbox

The sandbox had Blender 5.3 as a Python module with **software rendering only** (no GPU, 2 CPU cores), and its shell could reach only PyPI, npm and GitHub.

**Run through the normal entry point (`python tools/clip.py …`) on *The Ring in the Pond*:**

| Step | Result |
|---|---|
| `new --script`, `plan-check` | plan passes: medieval world, 4 pack characters in costume, 1 set, 4 shots, 20 views, 3 setups. A copy of the plan with a police officer, a top hat, red brick and a late setup is rejected with four errors |
| `voice --from-media <your earlier MP4>` | 127 of 127 script words found; 47.7 s; shot lengths 16.6, 8.1, 9.1 and 13.9 s |
| `stills` (all four shots, several rounds) | two stills per view; every sheet was looked at and the staging corrected from it (see below) |
| `render --quality draft --step 4` | the whole film as an animatic: 288 frames at quarter size |
| `assemble --tag animatic` | Remotion + FFmpeg: 1080×1920, 24 fps, 47.8 s, −14.0 LUFS, 74 captions |
| `qa --tag animatic --listen` | PASS. Captions measured on 25 frames of the finished file: centre x = 0.499 of the width (worst 0.494), line at 0.707 of the height, widest 0.52 of the width, none outside the safe area. Each caption appears 0.08 s before its word |
| `sample --tag animatic` | one frame per view (20), looked at |
| `render sh0N --quality preview --frames N-N` (4 frames), `--quality final --frames 300-300` (1 frame) | four half-size frames and one frame at full delivery quality (1080×1920, 48 samples; 210 s on two CPU cores), looked at |
| `asset examples/assets/set_stone_well.py --no-save` | the example asset builds and previews |
| `materials fetch` against a local stand-in for ambientCG, then a wall built from the downloaded set | the scanned-texture path works end to end with a synthetic texture set |

**What was checked by eye, and what came of it:**

- *One world.* Queen, soldier, rich man and gardener are all pack characters of the same drawing style, dressed for one period (crown and ermine; kettle helmet and blue tunic; wine-red coat, ruff and plumed cap; straw hat, apron and green dress), standing in a castle garden of stone, oak and iron. Nothing modern is on screen.
- *Gate → drain.* The gate is shown in the first shot as the camera travels from the queen across the water to it (water in front of the board, the dry stone channel behind it running to a culvert). In the last shot the gardener steps onto the stone beside it, puts both hands on the bar and lifts; the film cuts to the opening wide and the level falls to mud in about a second; lily pads lie on the bottom; the ring glints; she walks across.
- *Captions.* One centred line, one to three words, in step with the voice (see the QA numbers above).
- *Fixed after looking at stills or the animatic:* poses that drifted in from earlier keys; the camera cutting early; a raised finger hidden behind the head; hands not reaching the gate bar; the wide framing cutting people off; sky showing through the end of the channel; the sunset shot too dark; the net with no visible mesh; the ring rising out of the water before its close view.

**Caveats on those checks:**

- The caption timing check against recognised speech is not independent here: this clip's word times themselves came from the same recogniser. The independent evidence is the earlier measurement that the recogniser's word starts sit about 0.07 s before the audible onset, and the frame-accurate caption list (`final/*.captions.json`).
- I played director, builder and reviewer myself; no second pair of eyes reviewed the shots.
- **Memory.** With software rendering, Blender's memory grew with every frame that had characters in it (about 0.1–0.2 GB per character per frame) and the system stopped it after 8–16 frames on the four-character shots. `render` now carries on by itself in smaller chunks when that happens. Whether a GPU machine shows this growth is unknown; if your log says "carrying on in chunks of N", that is this. An opt-in switch that hides the two unused drawings of each character from the renderer (`CAST_CULL_VIEWS=1`) was tried and made no measurable difference.
- **Assembly memory.** Remotion was stopped for memory at 1080×1920 with default settings in the 6 GB sandbox; `assemble --concurrency 1` with `REMOTION_VIDEO_CACHE_MB=384` completed. Your machines should not need this.

## What could not be verified there

- **Final-quality rendering and render time.** One frame was rendered at full quality; the animatic is quarter size at a few samples and shows every fourth frame. Soft shadows, reflections on the water and the scanned textures will look better on your GPU; judge the look from your own first render.
- **ambientCG downloads.** The site was not reachable from the shell. The downloader was written against the documented API v3 (the response shape was read through a web fetch) and tested end to end against a local stand-in server with the same shape; the real download was never run. Everything in the example uses the procedural stand-ins.
- **BlenderKit** (`bk-search`, `bk-fetch`). Still unverified, as in the first version. The pond film needs nothing from it.
- **ElevenLabs.** Not reachable. The pond clip's clock and soundtrack were taken from your earlier MP4 with offline speech recognition. The facts about voices in the README come from the first version and were not re-checked.
- **A real `/gen-clip` run with the agents.** The stages were run by hand, playing each agent's role with the same commands the agents use. The new agent and skill texts have not been exercised by the agents themselves.
- **Windows and macOS paths.** Developed on Linux. The entry point and tools are standard-library Python as before.

## Known limits and next steps

- **The cast is flat.** No back views, no climbing, no gripping another character. The style guide says how to stage around this.
- **Wides are width-limited.** A 9:16 frame holds about 6 m of stage at a readable size. Lay sets out in depth (the pond set documents how its one wide was chosen).
- **Hands are solved for the camera that exists when `reach` is called.** Add the camera views first (the runner notes it when the order is wrong).
- **Costume pieces are few** (13). Add what a story needs in `wardrobe.py` + `config/cast.json`; each is a few lines.
- **The pose sheet and named poses** cover common acting. New poses are one line each in `cast.POSES`.
- **Animals** are not in the pack. The guide suggests flat cut-outs; nothing is built yet.
- **Sound for the pond clip** should be restored from your original clip folder (see the README), so music and effects are separate stems again.
