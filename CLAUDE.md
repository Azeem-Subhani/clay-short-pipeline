# Shorts pipeline (3D cast, 3D world)

Turns an idea into a finished YouTube Short: script → shot plan → casting → voice → sets and characters staged in Blender → sound → assembled video with captions. Run it with **`/gen-clip`**. It stops three times for the user's approval (characters, sets, camera).

Every Short: 1080×1920, 24 fps, about 60–65 seconds (70 at most), simple English (A2–B2), a narrator over **simple round cartoon characters (3D figures with drawn faces) in a complete, richly dressed 3D world**. One period and place per story. Story clarity and viewer retention come first: at every moment the viewer sees what the narrator is talking about, from a camera that moves for a reason.

**Windows launcher.** On this machine `python` is the Microsoft Store stub, so every command here is run as `PY`: `py -3` on Windows, `python3` on macOS/Linux. All tools are standard library only.

## How the work is split

| Stage | Who | Reads | Writes |
|---|---|---|---|
| Script | main session with a `script-*` skill | idea, format | `output/script-writer/<format>/<slug>.json` |
| Shot plan (format 2: world, cast, sets as complete places, shots, views with camera design) | `director` agent | script | `shotplan.json` |
| Casting | `clip.py casting` (script) | plan, `config/cast.json`, `library/wardrobe/` | `casting.json`, `casting.md`; a MISSING stops the run |
| Character sheets, **Gate A** | `clip.py cast-sheets`; the user approves | casting | `review/cast/`, `approvals.json` |
| Voice, music, SFX | `sound-designer` agent + `tools/audio` | plan | `audio/plan.json`, `timing.json`, `audio/cues.json` |
| Surfaces, missing assets | `clip.py materials fetch`, `asset-maker` agent | plan | `library/materials/**`, `library/assets/**` |
| Sets | `shot-builder` agent (SET mode, one per set) | plan | `blender/set_<id>.py` |
| Set previews, **Gate B** | `clip.py setpreview`; the user approves | set files | `review/sets/`, `approvals.json` |
| Acting and camera | `shot-builder` agent (STAGE mode, one per set's shots) | plan, timing, approved sets | `blender/<shot>.py`, review stills, motion strips |
| Review | `frame-reviewer` agent | stills, strips, plan | `review/<shot>/verdict.json` |
| Camera previews, **Gate C** | `clip.py preview`; the user approves | shot files | `review/<shot>/camera/`, `approvals.json` |
| Render, assemble, QA | `tools/clip.py` (scripts, no agent) | everything | `render/`, `final/<slug>.mp4` |

One clip lives in `output/clips/<slug>/`. Agents hand work to each other through those files only.

Two words used strictly everywhere: a **shot** is one staged take in one set at one time of day (a file, a render unit); a **view** is one camera framing inside a shot (what the viewer experiences).

## Commands

```
PY tools/clip.py doctor                      # what is installed and reachable
PY tools/clip.py cast [Name] [--era e] [--rescan]   # the characters that exist: body, outfit, period, hair; what each body may wear
PY tools/clip.py casting <clip> [--apply]    # match the plan's cast to the registry: EXISTING / ADAPT / MISSING (exit 2); --apply registers ADAPT results as drafts
PY tools/clip.py actions [word] [-v]         # the named actions the cast performs with actor.do(...)
PY tools/clip.py materials [fetch <clip>]    # surfaces by name; fetch downloads the scanned textures from ambientCG
PY tools/clip.py new --script <file>         # create the clip folder from a validated script
PY tools/clip.py plan-check <clip>           # shot plan (format 2) vs script, registry, period, surfaces, sets, camera, transitions
PY tools/clip.py voice <clip>                # narration take -> timing.json   (--mock without an API key; --from-media <file> to reuse a recording)
PY tools/clip.py sound <clip>                # music, ambience, SFX            (--mock without an API key)
PY tools/clip.py cast-sheets <clip>          # Gate A previews: one sheet per character in costume
PY tools/clip.py setpreview <clip> [set]     # Gate B previews: six angles per set and light mood, with the set audit
PY tools/clip.py stills <clip> [shot] [--views a,b] [--quality preview]   # build shots, review stills, motion strips, checks; exit 3 while blocking, 4 if a gate is not approved
PY tools/clip.py preview <clip> [shot]       # Gate C previews: low-res motion film + camera path diagram per shot
PY tools/clip.py gate <clip> [A|B|C] [--approve | --revise "..."] [--by who] [--json]   # the three approval gates (--autonomous --reason "..." for an unattended run)
PY tools/clip.py render <clip> [shot]        # final frames, resumable (--quality draft --step 3 = animatic; final needs gates A, B and C)
PY tools/clip.py assemble <clip>             # Remotion + FFmpeg -> final MP4 + captions.json (transitions from the plan)
PY tools/clip.py qa <clip>                   # measure the final file: format, loudness, captions placed and on time
PY tools/clip.py sample <clip>               # one frame per view from the final file for a last look
PY tools/clip.py status <clip>               # which stages and gates are done, and the next one
PY tools/clip.py assets find <words>         # search the asset library      (asset <script.py> builds and files one)
PY tools/clip.py bk-search "<words>" | bk-fetch <id>    # BlenderKit; only CC0 or Royalty Free is downloaded
PY tools/clip.py voices                      # check the voice shortlist on the ElevenLabs account
PY -I scripts/validate_script.py --format <format> <script.json>
```

Standalone Blender tools (run `blender -b --factory-startup --python <file> -- <args>`; `tools/common.py` finds Blender): `tools/blender/set_preview.py` (one set file, `--set --time --out`), `tools/blender/cam_preview.py` (one shot script, `--script --seconds --out`), `tools/tests/camera/test_moves.py` (every camera move), `tools/tests/sets/` (the architecture and furniture tests). Character tools: `tools/chars_aj/` (clips registry `clips.py`, sheets `gate_a_sheets.py`, `qa.py`, fitting) and `tools/cast_registry.py merge|check`.

## Rules that hold everywhere

- **The voice take is the clock.** Shot lengths and every word time come from `timing.json`. In shot code, key actions and views to words with `shot.t("phrase")`, never to guessed seconds. Captions are built from the same word times.
- **Three gates, enforced by the tools.** Gate A (characters and wardrobe), B (sets), C (camera) are decided by the user from pictures, recorded in `approvals.json`, and `stills`, `render` and `assemble` exit 4 without them. A gate goes `stale` when its own inputs change after approval; nothing else reopens it. Never work around one. An unattended run happens only when the user's own words ask for it, and the gates are then recorded as bypassed, never approved.
- **Checks that measure a real fault block.** Every finding in `review/<shot>/checks.json` is `block` or `warn`; `stills` exits 3 until the blocking count is zero. Warnings are fixed or explained in the report. "It renders" is never the standard: the builder and the reviewer look at the pictures.
- **Sets are complete places.** Marks first, then a real enclosure with something behind every opening, four depth layers, 14 kinds of prop and 60 objects in a wide, practical lights, atmosphere, readable details, one light rig per time of day, and the reverse angle survives. Built from `stagekit/arch`, `furnish`, `dress`; worked sets in `examples/sets/`. The set audit (`stagekit/audit.py`) measures it.
- **The camera has a library and a bar.** Moves (`dolly`, `truck`, `pan`, `tilt`, `orbit`, `crane`, `follow`, `track_with`, `whip`, `through`, `rack_focus`, `reveal`...) chosen for what they show, the camera moving 60–80% of screen time, transitions as camera events, one side of the line of action. Path checks (`stagekit/campath.py`) block the impossible. `tools/tests/camera/test_moves.py` is the cookbook.
- **One world per story.** `world.era` in the plan; every character, costume piece, surface and library asset carries period tags and `plan-check` enforces them. Period data lives in `config/cast.json`, `library/materials/catalog.json`, `library/assets/index.json` and `library/wardrobe/index.json`.
- **The cast is 3D Aj characters** on a Mixamo skeleton, with outfits from a fit-checked wardrobe. The registry is `config/cast.json`, the wardrobe rules are in `library/wardrobe/README.md`, and `PY tools/clip.py cast` says who exists and what each body may wear; a role nobody can play is a MISSING from `casting`, never an invention.
- **Acting is named actions and Mixamo clips.** `actor.do("pick_up", ring, hit=shot.t("picked up"))`, `actor.walk(...)`, `actor.play_clip(...)`. The catalogue is `config/actions.json`, the clips `config/mixamo_clips.json`. A missing action is added with `docs/ADDING_NEW_ACTIONS.md`; a missing clip with `PY tools/chars_aj/clips.py --ask <Name>`.
- **Style numbers live in `style/style.json`; reasons live in `style/STYLE_GUIDE.md`; evidence lives in `docs/REFERENCE_BREAKDOWN.md`.** Render settings are locked there. Never change them per shot.
- **Surfaces by name** (`mat.surface("castle_stone")`), furniture from `furnish`, architecture from `arch`, then the library, then BlenderKit (CC0 or Royalty Free only), then built and registered. Everything used is filed with its source and licence.
- **A skill or schema and its validator must agree.** If you change `tools/plan.py` or `tools/plan_v2.py`, change the `shot-plan` skill in the same edit. Same for `scripts/validate_script.py` and the `script-*` skills.
- **Keep approved audio.** A voice take or sound is only generated again with `--retake`; every call costs credits and sounds different.
- **Generated media stays in `output/`** and is not committed. Script JSON, plans and shot code are.
- **One heavy job at a time on a small machine.** Blender renders and the Remotion assembly both want several GB of memory; do not run them together.
- Scripts measure what can be measured. Agents and the human judge purpose, performance and quality from images.

## Script formats

Seven writers live in `.claude/skills/script-*`. Each defines a different audience expectation and uses `.claude/skills/script-development.md` to develop, draft, and review the story before production. Viewers should have a reason to stay through the payoff. Beat count, point of view, and word counts are creative choices. Plan around a minute at Alex's natural **~177 WPM**, with room for pauses under the limit in `style/style.json`. The validator checks the JSON contract.

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
config/              cast.json (the cast registry), actions.json, mixamo_clips.json, voices.json
tools/               clip.py (entry point), gates.py (approval gates), plan.py + plan_v2.py (plan checks), casting.py + cast_data.py (casting), captions.py, materials.py,
                     assemble.py, qa.py, cast_registry.py, audio/, chars_aj/ (Aj characters: clips, sheets, fitting, QA),
                     blender/ (run_shot.py, set_preview.py, cam_preview.py, planlink.py, stagekit/ = arch, furnish, dress, audit, lights, camera, campath, cast_aj, aj_clips, review ...),
                     tests/ (camera, sets, cast, plan, gates)
remotion/            final assembly project (captions, transitions, mix)
packs/               the Aj character pack goes here (not in git)
library/             materials/catalog.json (surfaces), assets/ (reusable props and set pieces), wardrobe/ (outfits, add-ons, fits, licences), characters/aj/ (bodies, hair, Mixamo clips)
examples/            sets/ (worked sets: throne room, office), the-ring-in-the-pond (an older worked clip), assets/
docs/                REFERENCE_BREAKDOWN.md, DIAGNOSIS.md, HANDOFF.md (status and the gate workflow), ACTIONS.md, ADDING_NEW_ACTIONS.md, CHARACTERS_3D.md, poses.png
output/              scripts and clips
```
