# Shorts pipeline (2D cast, 3D world)

Turns an idea into a finished YouTube Short: script → shot plan → voice → sets and 2D characters staged in Blender → sound → assembled video with captions. Run it with **`/gen-clip`**.

Every Short: 1080×1920, 24 fps, about 50 seconds (55 at most), simple English (A2–B2), a narrator over **flat 2D cartoon characters in a real 3D world**. One period and place per story. Story clarity and viewer retention come first: at every moment the viewer sees what the narrator is talking about.

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
python tools/clip.py cast [Name] [--era e]  # the character pack: who fits which period, colours, parts
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
- **Characters come from the 2D pack** in `packs/characters_beta_0_3/` through `stagekit.cast`. Do not edit files inside the pack. The pack is never committed and never shipped with the project.
- **Sets are built around the action:** marks first (`MARK` in the set file), then the place, then dressing at the edges.
- **Style numbers live in `style/style.json`; reasons live in `style/STYLE_GUIDE.md`; evidence lives in `docs/REFERENCE_BREAKDOWN.md`.** Render settings are locked there. Never change them per shot.
- **One light rig per set and time of day**, built in `blender/set_<id>.py` and reused by every shot of that set and time.
- **Surfaces by name** (`mat.surface("castle_stone")`), props from the kit, then the library, then BlenderKit, then built. Everything used is filed with its source and licence.
- **A skill or schema and its validator must agree.** If you change `tools/plan.py`, change the `shot-plan` skill in the same edit. Same for `scripts/validate_script.py` and the `script-*` skills.
- **Keep approved audio.** A voice take or sound is only generated again with `--retake`; every call costs credits and sounds different.
- **Generated media stays in `output/`** and is not committed. Script JSON, plans and shot code are.
- **One heavy job at a time on a small machine.** Blender renders and the Remotion assembly both want several GB of memory; do not run them together.
- Scripts measure what can be measured. Agents and the human judge purpose, performance and quality from images.

## Script formats

Seven writers live in `.claude/skills/script-*`. Each has fixed beats, timestamps and extra fields; see its `SKILL.md`. All target **170–198 words** (~50 seconds at **220–240 WPM**, ~230 WPM average), sentences up to 24 words (mixing punchy short hits with smooth conversational beats), natural contractions allowed, and viewer retention as the top priority.

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

Voice profile, pacing target (220–240 WPM), and format delivery notes live in `config/voices.json`.

## Layout

```
.claude/skills/      gen-clip (the command), script-* (7 writers), shot-plan, cinematic-style, stagekit, sound-design, asset-library
.claude/agents/      director, sound-designer, asset-maker, shot-builder, frame-reviewer
style/               STYLE_GUIDE.md (how we shoot), style.json (numbers scripts enforce)
config/              cast.json (pack characters, periods, wardrobe), voices.json (voice shortlist per format)
tools/               clip.py (entry point), plan.py, captions.py, materials.py, assemble.py, qa.py, audio/, blender/stagekit/
remotion/            final assembly project (captions, mix)
packs/               the 2D character pack goes here (not in git; see packs/README.md)
library/             materials/catalog.json (surfaces), assets/ (reusable props and set pieces)
examples/            a complete worked clip to learn from
docs/                REFERENCE_BREAKDOWN.md (the two reference Shorts, shot by shot), DIAGNOSIS.md, HANDOFF.md, poses.png
output/              scripts and clips
```
