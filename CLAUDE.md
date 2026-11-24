# Shorts pipeline (3D cast, 3D world)

Turns an idea into a finished YouTube Short: script → shot plan → voice → sets and characters staged in Blender → sound → assembled video with captions. Run it with **`/gen-clip`**.

Every Short: 1080×1920, 24 fps, about 60–65 seconds (70 at most), simple English (A2–B2), a narrator over **simple round cartoon characters (3D figures with drawn faces) in a real 3D world**. One period and place per story. Story clarity and viewer retention come first: at every moment the viewer sees what the narrator is talking about.

## How the work is split

| Stage | Who | Reads | Writes |
|---|---|---|---|
| Script | main session with a `script-*` skill | idea, format | `output/script-writer/<format>/<slug>.json` |
| Shot plan (world, cast, sets, shots, views) | `director` agent | script | `shotplan.json` |
| Voice, music, SFX | `sound-designer` agent + `tools/audio` | plan | `audio/plan.json`, `timing.json`, `audio/cues.json` |
| Surfaces, missing assets | `clip.py materials fetch`, `asset-maker` agent | plan | `library/materials/**`, `library/assets/**` |
| Set, cast, action, camera | `shot-builder` agent (one per set) | plan, timing | `blender/set_<id>.py`, `blender/<shot>.py`, review stills |
| Review | `frame-reviewer` agent | stills, plan | `review/<shot>/verdict.json` |
| Render, assemble, QA | `tools/clip.py` (scripts, no agent) | everything | `render/`, `final/<slug>.mp4` |

One clip lives in `output/clips/<slug>/`. Agents hand work to each other through those files only.

Two words used strictly everywhere: a **shot** is one staged take in one set at one time of day (a file, a render unit); a **view** is one camera framing inside a shot (what the viewer experiences).

## Commands

Use `python` on Windows and `python3` on macOS/Linux. All tools are standard library only.

```
python tools/clip.py doctor                 # what is installed and reachable
python tools/clip.py cast [Name] [--era e]  # the character pack: who fits which period, colours, parts, stand-ins, props
python tools/clip.py actions [word] [-v]    # the named actions the cast performs with actor.do(...)   (--rescan after adding one)
python tools/cast_registry.py merge|check   # put a new character's notes into config/cast.json; check eras, stand-ins, props
blender -b --factory-startup --python tools/chars3d/look3d.py -- --char <Name> --out <abs.png>   # look at ONE 3D character: four turns, four faces
blender -b --factory-startup --python tools/chars3d/action_test3d.py -- --char <Name> --out <abs dir> --set core   # measure actions on a 3D character
python tools/chars/charloop.py <Name>       # (2D pack only) build ONE flat character from its costume file
python tools/chars/actiontests.py --names <Name> --set core   # measure and render actions on characters, in parallel
python tools/clip.py materials [fetch <clip>]   # surfaces by name; fetch downloads the scanned textures from ambientCG
python tools/clip.py new --script <file>    # create the clip folder from a validated script
python tools/clip.py plan-check <clip>      # shot plan vs script, pack, period, surfaces, views, setups
python tools/clip.py voice <clip>           # narration take -> timing.json   (--mock without an API key; --from-media <file> to reuse a recording)
python tools/clip.py sound <clip>           # music, ambience, SFX            (--mock without an API key)
python tools/clip.py stills <clip> [shot] [--views a,b]   # build shot(s) in Blender, render review stills + measured checks
python tools/clip.py render <clip> [shot]   # final frames, resumable         (--quality draft --step 3 = animatic)
python tools/clip.py assemble <clip>        # Remotion + FFmpeg -> final MP4 + captions.json
python tools/clip.py qa <clip>              # measure the final file: format, loudness, captions placed and on time
python tools/clip.py sample <clip>          # one frame per view from the final file for a last look
python tools/clip.py status <clip>          # which stages are done
python tools/clip.py assets find <words>    # search the asset library      (asset <script.py> builds and files one)
python tools/clip.py voices                 # check the voice shortlist on the ElevenLabs account
python -I scripts/validate_script.py --format <format> <script.json>
```

## Rules that hold everywhere

- **The voice take is the clock.** Shot lengths and every word time come from `timing.json`. In shot code, key actions and views to words with `shot.t("phrase")`, never to guessed seconds. Captions are built from the same word times.
- **One world per story.** `world.era` in the plan; every character, costume piece, surface and library asset carries period tags and `plan-check` enforces them. Period data lives in `config/cast.json`, `library/materials/catalog.json` and `library/assets/index.json`.
- **The cast is 3D.** 92 standard characters (and the ones made here) are real models built from sheets in `config/cast3d.json` and `config/cast3d_custom.json`; `cast.actor` / `cast.from_plan` return them, the 118 actions and the wardrobe work on them unchanged, and the camera may go all the way round them. Read `docs/CHARACTERS_3D.md`. Thirteen special bodies (Ghost, Mermaid, Dragon, Fairy, Robot, Alien, Werewolf, Mummy, Genie, Goblin, Monster, Devil, Skeleton) are still flat 2D characters from the old pack in `packs/`: cast one only when the story needs it, and keep the camera in front of it. `python tools/clip.py cast <Name>` says which kind a character is.
- **Acting is named actions.** A character performs with `actor.do("pick_up", ring, hit=shot.t("picked up"))` from `stagekit.actions` (anticipation, motion, settle, in every view); poses and `reach`/`hold` are the building blocks. The catalogue is `config/actions.json`. A missing action is added with `docs/ADDING_NEW_ACTIONS.md`, a missing character with the `character-maker` skill: reuse first, then re-costume, then a new sheet in `config/cast3d_custom.json` (a few lines saying which character it is like and what differs).
- **Sets are built around the action:** marks first (`MARK` in the set file), then the place, then dressing at the edges.
- **Style numbers live in `style/style.json`; reasons live in `style/STYLE_GUIDE.md`; evidence lives in `docs/REFERENCE_BREAKDOWN.md`.** Render settings are locked there. Never change them per shot.
- **One light rig per set and time of day**, built in `blender/set_<id>.py` and reused by every shot of that set and time.
- **Surfaces by name** (`mat.surface("castle_stone")`), props from the kit, then the library, then BlenderKit, then built. Everything used is filed with its source and licence.
- **A skill or schema and its validator must agree.** If you change `tools/plan.py`, change the `shot-plan` skill in the same edit. Same for `scripts/validate_script.py` and the `script-*` skills.
- **Keep approved audio.** A voice take or sound is only generated again with `--retake`; every call costs credits and sounds different.
- **Generated media stays in `output/`** and is not committed. Script JSON, plans and shot code are.
- **One heavy job at a time on a small machine.** Blender renders and the Remotion assembly both want several GB of memory; do not run them together. (Small character jobs are the exception: `tools/chars/jobrun.py` runs builds, verify runs and action tests in parallel, sized to the free RAM, VRAM and CPU, and never beside an assembly.)
- Scripts measure what can be measured. Agents and the human judge purpose, performance and quality from images.

## Script formats

Seven writers live in `.claude/skills/script-*`. Each has fixed beats, timestamps and extra fields; see its `SKILL.md`. All target **170–198 words** (about 58–68 seconds at Alex's natural **~177 WPM**), sentences up to 24 words (mixing punchy short hits with smooth conversational beats), natural contractions allowed, and viewer retention as the top priority.

Every category uses the exact same standardized voice profile (**Alex — Upbeat, Energetic and Clear**) with contextual emotion tags directed by `sound-designer` (`.claude/skills/sound-design/SKILL.md`).

| Format | Shape | Voice |
|---|---|---|
| `twist` | A puzzle with a psychological reveal | Alex — Upbeat, Energetic and Clear |
| `slow-burn` | Someone looks dangerous; the last line flips it | Alex — Upbeat, Energetic and Clear |
| `rule-of-three` | A challenge, two failures, a clever third try | Alex — Upbeat, Energetic and Clear |
| `ticking-clock` | A countdown and a real, safe escape | Alex — Upbeat, Energetic and Clear |
| `reverse-chronology` | Starts at the end, rewinds to the cause | Alex — Upbeat, Energetic and Clear |
| `unspoken-rules` | Three rules, one broken; the threat is never named | Alex — Upbeat, Energetic and Clear |
| `micro-butterfly` | One tiny mistake grows into a collapse | Alex — Upbeat, Energetic and Clear |

Voice profile, pacing target (Alex's natural ~177 WPM), and format delivery notes live in `config/voices.json`.

## Layout

```
.claude/skills/      gen-clip (the command), script-* (7 writers), shot-plan, cinematic-style, stagekit, sound-design, asset-library, character-maker
.claude/agents/      director, sound-designer, asset-maker, shot-builder, frame-reviewer
style/               STYLE_GUIDE.md (how we shoot), style.json (numbers scripts enforce)
config/              cast.json (pack characters, periods, wardrobe), actions.json (named actions), voices.json (voice shortlist per format)
tools/               clip.py (entry point), plan.py, captions.py, materials.py, assemble.py, qa.py, cast_registry.py, audio/, blender/stagekit/,
                     chars/ (new characters and action tests: charloop, actiontests, verifyall, jobrun)
remotion/            final assembly project (captions, mix)
packs/               the 2D character pack goes here (not in git; see packs/README.md)
library/             materials/catalog.json (surfaces), assets/ (reusable props and set pieces)
examples/            a complete worked clip to learn from
docs/                REFERENCE_BREAKDOWN.md (the two reference Shorts, shot by shot), DIAGNOSIS.md, HANDOFF.md, poses.png,
                     ACTIONS.md, ADDING_NEW_ACTIONS.md, CHARACTERS_3D.md (the 3D cast: use, dress, make new), lineup_3d_*.png, wardrobe_3d.png,
                     CREATING_NEW_CHARACTERS.md (the old 2D pack only)
output/              scripts and clips
```
