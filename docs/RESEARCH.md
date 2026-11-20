# Research, decisions and verification

Written 21 November 2026. Sources are listed at the end.

## What was reviewed

- **`release_1.zip`**: the character pack. Six presets, three bases, nine hairs, beards, skin tones, over-layers, hats, a Mixamo walk with a retargeter, brow presets and blink, for **Blender 5.3 / EEVEE / AgX**. Its own smoke test (42 checks) passes on Blender 5.3.0 in the build sandbox.
- **`short-script-pipeline.zip`**: seven `script-*` skills with gold examples and `scripts/validate_script.py`. Included unchanged. All seven example files pass the validator.
- **`craft-pack-v2.zip`** and the **"Clay Toy Shorts Pipeline Blueprint"** document: Claude Opus's proposal from before the character pack existed.

## Opus's recommendations, judged one by one

| Opus recommended | Verdict | Why |
|---|---|---|
| Purpose first: every shot states what it must do; choices carry a `why` | **Kept** | It is the one idea that stops checklist film-making. It is the spine of the shot plan and the review. |
| Few fixed rules, craft as tools with reasons | **Kept** | Matches how the script skills already work. |
| Voice before Blender; cuts from real word timings | **Kept and made stricter** | Shot code now keys actions to spoken words (`shot.t("phrase")`), so a new take never desynchronises a shot. |
| One light rig per location and time | **Kept and enforced by structure** | A set module builds the place *and* its rig; shots cannot rebuild it. |
| Builders separate from critics; measure with scripts, judge with eyes | **Kept** | The reviewer is a separate, read-only agent. Framing, focus, occlusion and exposure are measured in Blender. |
| Stage around what an agent cannot animate | **Kept**, updated to what the pack really does | Your pack has no mouth and one walk clip. The style guide's "reliable / needs care / stage around" table is rewritten for it. |
| **12–16 shots per 50 seconds** | **Replaced with about 4–5** | Your brief, and the right call: with 3-second shots nothing can be lit, animated or felt. The plan format now asks "what changes *inside* this take?" and every cut needs `why_cut`. |
| A live Blender session driven through Blender MCP, one agent at a time | **Replaced with headless Blender + a Python toolkit** | `/gen-clip` must run unattended. Headless runs are reproducible (the shot is a file you can re-run), resumable, and several can run at once. MCP stays useful for your own look-dev, not for the pipeline. |
| Three human approval gates; ten-step state machine with `production.json`, hooks and attempt counters | **Dropped for now** | You asked for one command from idea to MP4. State is the files in the clip folder; `clip.py status` reads them. A gate is easy to add later as a pause in `/gen-clip`. |
| BlenderKit: "no API; you click download, agents pick up the file" | **Improved** | The official add-on ships blocking search and download routes "for background scripts". `tools/blender/bk_fetch.py` uses them headless with your login; the click-and-pick-up path remains as the fallback. |
| ElevenLabs: start on `eleven_multilingual_v2`, one voice, stability 50 / similarity 75 / style 0 | **Outdated** | Eleven v4 shipped in September 2026 and is the recommended model; delivery is directed with audio tags; there is no speed or style setting on it. Voices are per format, from your shortlist. |
| "Characters on 2s" (stepped animation) | **Not adopted** | The pack's walk is baked on 1s and reads smoothly; stepping it would need a second pass for little gain. Easy to add in `stagekit.cast` if you want the stop-motion feel. |
| Remotion captions via `createTikTokStyleCaptions`, FFmpeg two-pass loudnorm, −14 LUFS | **Kept** (own paging) | Captions are paged in `tools/assemble.py` (sentence ends, silences, shot changes) and drawn in Remotion. Loudness is two-pass, −14 LUFS, −1 dBTP, 48 kHz. |
| Seven roles | **Five agents** | See below. |

## How the pipeline is structured in Claude Code

Checked against the current Claude Code documentation:

- **Custom commands are skills now.** `.claude/skills/gen-clip/SKILL.md` creates `/gen-clip`. It has `disable-model-invocation: true` (only you start it), `argument-hint`, and `model: opus`.
- **Subagents** live in `.claude/agents/*.md` with `name`, `description`, `tools`, `model` (`sonnet`, `opus`, `haiku`, `fable`, a full id, or `inherit`) and `skills` to preload. They start with a fresh context and can run in parallel. That is the automatic model selection: each agent file pins its model.
- **Skills** are the reusable craft: loaded on demand, preloaded into the agents that need them.
- **Scripts** do everything measurable or mechanical.

**Who does what, and why it is split this way**

| Your idea | Final home | Reason |
|---|---|---|
| Direction | **`director` agent** (Opus) + `shot-plan` and `cinematic-style` skills | The most judgment-heavy step, self-contained, returns one file. |
| Set dressing | **`shot-builder` agent** (Opus), one per set | Set, light, blocking and camera are one decision: where people stand decides where the light and lens go. Splitting them into separate agents would make them negotiate through files. |
| Cinematography and camera movement | same `shot-builder`, with the `cinematic-style` skill and `stagekit.camera` | As above. The craft is a skill, the moves are toolkit calls. |
| Character production | `stagekit.cast` (script) for pack characters; **`asset-maker` agent** (Sonnet) for anything the pack cannot do | Using the pack is a function call. Building something new is separate, parallel, reusable work. |
| Review | **`frame-reviewer` agent** (Opus), read-only | A builder should not grade its own shot. |
| Voice and sound | **`sound-designer` agent** (Sonnet) + `tools/audio` | Different tools, runs in parallel with asset work, and its voice take is the clock for everything else. |
| Asset library | `asset-library` skill + `stagekit.assets` + `asset-maker` | A rule (library → BlenderKit → build) plus scripts; the agent only does the making. |
| Producer | the `/gen-clip` skill in the main session | It talks to you, so it stays in the conversation. |
| Render, assembly, mix, subtitles, QA | scripts (`clip.py render / assemble / qa`) | Nothing to decide. |

## Research findings that shaped the build

**ElevenLabs (docs read 21 November 2026)**

- Current TTS models: **`eleven_v4`** (recommended, most expressive, audio tags), `eleven_v4_turbo`, `eleven_v3`, `eleven_multilingual_v2`, `eleven_flash_v2_5`. `eleven_turbo_*` are deprecated.
- **Delivery, pacing, pauses, emphasis:** on v4 and v3 these are written into the text: audio tags in square brackets (`[whispers]`, `[low, measured]`, free text), `[pause]` / `[long pause]`, ellipses and punctuation, CAPITALS for emphasis. **SSML `<break>` tags are not supported on v4/v3.** The remaining voice settings are stability and similarity. Speed (0.7–1.2) and style apply to the v2 models.
- The page you linked (ElevenAgents voice customisation) covers the *Agents* product: multi-voice, pronunciation dictionaries, speed 0.7–1.2, expressive mode on "Eleven v3 Conversational". Those are conversational-agent controls. For this pipeline the relevant API is plain text-to-speech, where the controls are the ones above.
- **Timestamps:** `POST /v1/text-to-speech/{voice_id}/with-timestamps` returns character timings. The docs do not say which models support it, and there is a `text-to-dialogue/with-timestamps` route too. The voice tool therefore tries TTS with timestamps, falls back to the dialogue route, and if the timings do not match the script it calls **Forced Alignment** (`POST /v1/forced-alignment`), which works for any audio.
- **Exact pauses are inserted by the tool**, not asked of the model: the take is cut in the gaps between shots and real silence is added.
- **Voices:** see README. The important finding is that **all Default voices retire on 31 December 2026**, which covers five of your eight shortlisted voices; replacements are mapped.
- **Sound effects:** `eleven_text_to_sound_v3` (v2 is removed on 1 March 2027), 0.5–30 s, `loop` for ambience. **Music:** `music_v2_5` (`music_v1` is removed on 31 January 2027). Music rights vary by plan.

**Blender**

- Blender 5.3 was released on 10 November 2026; the pack targets it. The `bpy` 5.3.0 wheel was used to verify everything here.
- EEVEE settings that give the polished look, read from the 5.3 API and locked in `style/style.json`: AgX with the "Medium High Contrast" look, soft shadows by light jitter (`use_shadow_jitter`), horizon-scan global illumination for ambient occlusion and bounce (`use_fast_gi`), screen-space ray tracing, jittered depth of field for clean blur edges.
- Animation is written with the 5.x slotted-action API (`action.fcurve_ensure_for_datablock`).
- The pack's retargeter clears a rig's action on every call, so `stagekit.cast` bakes the walk once per character into a reusable cycle and writes it wherever a walk is needed. That is what allows several walks, turns and poses in one take.

**BlenderKit**

- The add-on (v3.21.7) talks to a local Client process and exposes `get_download_url` and `blocking_file_download` wrappers intended for background use. `bk_fetch.py` enables the add-on in headless Blender, starts the Client, searches with the add-on's own URL builder and your API key, and downloads.

**Remotion**

- 4.0.545 is current. Free for individuals and teams of up to three, including commercial use. Fonts are bundled from `@fontsource/montserrat`, so rendering needs no network.

## Verified end to end

Everything below was run in the build sandbox (Linux, 2 CPU cores, **no GPU**: EEVEE ran on software OpenGL).

| What | Result |
|---|---|
| Character pack on Blender 5.3.0 | The pack's own smoke test: **42 of 42 checks pass**. |
| Script skills | All seven `references/examples.json` files pass `scripts/validate_script.py`. The gold slow-burn script "The Boy in the Basement" was used as the test story. |
| Shot plan | A 5-shot plan was written for it and passes `clip.py plan-check` (word-for-word narration coverage, clues, holds, `why_cut`). |
| Voice step, offline | `voice --mock`: 130 words → 54.96 s, 1,319 frames, 5 shots, holds trimmed automatically to stay under 55 s. |
| Voice and sound steps, real code path | Run against a **local stand-in for the ElevenLabs API** (same routes and JSON shapes as the docs): v4 with character timestamps and audio tags stripped to words; the "model not supported on this route" fallback to text-to-dialogue; the missing-alignment fallback to forced alignment; sound effects, looping ambience and music; `doctor` and `voices` (default voice ok / not available / library voice found / several matches / not in My Voices). |
| stagekit | Sets, clay props, light rigs, characters (walk between marks, poses, look, brows, blink, idle, hold a prop, carry), camera keys, dolly, focus shifts, follow, light changes, review stills, contact sheets and measured checks all ran in Blender 5.3 on real pack characters. |
| Asset library | Four assets built, previewed and filed (wire cutters, door key, police car, school bag) and reused in shots. `assets.adopt` (import → fit → clay restyle → save → reuse) tested on a synthetic textured `.blend`. |
| Five shots built and reviewed | Each went through two to four stills rounds; the fixes made are the kind the reviewer agent is there to catch (a face that must stay hidden appearing at the frame edge, a camera path through a car roof, a clue prop that did not reach its target, a burnt-out roof under the police lights). |
| Render | All five shots rendered headless, resumable, in chunks: 113 frames at draft quality (270×480, 8 samples, every 12th frame). One frame at full final quality (1080×1920, 64 samples, jittered depth of field): `examples/the-boy-in-the-basement/final_quality_frame_sh03.png`. It took 10 minutes on software OpenGL. |
| Assembly | Remotion 4.0.545 rendered 1,319 frames at 1080×1920 with captions, narration, ducked music, three ambience beds and six effects; FFmpeg two-pass loudness. |
| QA | **PASS**: 1080×1920, 24 fps, 54.98 s, H.264 yuv420p + AAC 48 kHz, −14.0 LUFS, 5 shots, every cut in a gap between words. Warnings, as expected: draft render, mock audio, duration above the 46–53 s target. |

The result is `examples/the-boy-in-the-basement/the-boy-in-the-basement_animatic.mp4`.

**Not verified here, and why**

- **A real ElevenLabs call.** No API key in the sandbox and the host is not reachable from it. Request shapes follow the API reference; the first real run is the test. Whether `eleven_v4` returns timestamps on the TTS route is not stated in the docs, which is why the two fallbacks exist.
- **Voice availability on your account.** Verified from documentation only. `clip.py voices` checks it for real.
- **BlenderKit search and download.** Written from the add-on source; the service is not reachable from the sandbox.
- **Final-quality look and render time on a GPU.** The sandbox has no GPU. One full-quality frame and the draft frames show the lighting, shadows, framing and focus logic working, but the example's sets are sparsely dressed and its light moods were calibrated on a handful of low-resolution stills. The first full-quality render on your RTX 5060 is where the look should be judged and the moods in `stagekit/lights.py` tuned.
- **Motion.** The animatic shows every 12th frame. Walk timing, camera easing and flicker were not judged in motion.
- **The agents themselves.** The skills, agent files and `/gen-clip` are written to the current Claude Code spec, and every command they call was run. A full `/gen-clip` run inside Claude Code was not possible here; I played each agent's role by hand to produce the example.
- **Memory on software OpenGL** grew by several hundred MB per rendered frame in heavy scenes, which is why `render` restarts Blender in chunks. Whether a GPU shows the same growth is unknown; chunking makes it harmless either way.

## Sources

- Claude Code docs: skills and custom commands (`code.claude.com/docs/en/skills`), subagents (`/sub-agents`), permissions (`/permissions`)
- ElevenLabs docs: models (`elevenlabs.io/docs/overview/models`), text to speech and best practices (`/docs/overview/capabilities/text-to-speech`), create speech with timestamps, text to dialogue with timestamps, forced alignment, sound effects, compose music (`/docs/api-reference/...`), search voices, "What are Default voices?" and "How do I access ElevenLabs Default voices?" (help center), ElevenAgents voice customisation (`/docs/eleven-agents/customization/voice`), Eleven Music model-specific terms
- Blender 5.3 release notes (`developer.blender.org/docs/release_notes/5.3/eevee/`, `blender.org/download/releases/5-3/`); the `bpy` 5.3.0 API inspected directly
- BlenderKit add-on source (`github.com/BlenderKit/BlenderKit`: `client_lib.py`, `search.py`, `paths.py`, `timer.py`, `CONTRIBUTING.md`)
- Remotion: npm registry (4.0.545), licence and pricing pages (`remotion.dev/docs/license`)
