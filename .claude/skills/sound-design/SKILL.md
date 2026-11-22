---
name: sound-design
description: Narration delivery, music and sound effects with the ElevenLabs API for a 50-second Short - how to direct the voice with audio tags and punctuation, the audio plan format, cue timing on words, and the commands that generate and place everything. Use when writing audio/plan.json or running the voice and sound steps.
---

# Sound design

You direct a narrator, a composer and a foley artist through one file: `output/clips/<clip>/audio/plan.json`. Scripts turn it into audio and put every sound on the film's clock.

```
python tools/clip.py voice <clip>      # one narration take with timestamps -> audio/narration.wav + timing.json
python tools/clip.py sound <clip>      # music, ambience, effects -> audio/cues.json
        --mock      placeholder audio without the API (dry runs)      --retake   generate again (costs credits)
```

Worked example: `examples/sound/the-boy-in-the-basement.audio-plan.json` (an audio plan from the first version of the pipeline; the format is unchanged).

## The voice

**Model: Eleven v4 (`eleven_v4`)**, with `eleven_v3` and `eleven_multilingual_v2` as automatic fallbacks (`config/voices.json`).

What controls delivery on v4 and v3 (checked against the ElevenLabs docs, November 2026):

| You want | How |
|---|---|
| Tone, emotion, volume | **Audio tags** in square brackets before the words they change: `[low, measured]`, `[whispers]`, `[urgent, breathless]`, `[warm, gentle]`, `[flat, deadpan]`. Tags are free text; describing the voice ("low, steady") is more reliable than naming a sound. |
| A pause | `[pause]` or `[long pause]`, an ellipsis `…`, a dash, or a full stop. **SSML `<break>` tags do not work on v4/v3.** Exact silences are not the model's job: put them in the plan as `hold_after_s` and the tools insert real silence. |
| Pace | No speed setting on v4/v3. Use `[slowly]`, `[rushed]`, and sentence length: short sentences slow a read down. |
| Emphasis | CAPITALS on one word, or punctuation. Use at most once or twice per script. |
| Consistency | `stability` (0.45–0.7). Higher is steadier, lower is more expressive. Narration likes 0.5–0.65 with tags doing the acting. `similarity_boost` 0.75. |

On `eleven_multilingual_v2` (fallback) tags are stripped automatically, `[pause]` becomes a `<break>`, and `style`, `speed` (0.7–1.2) and `use_speaker_boost` apply instead. Do not rely on it for expressive reads.

**Rules for tagged narration**

- **The words never change.** Tags and punctuation may; the tools reject a narration whose words differ from the shot's `vo_text`.
- **One direction per beat is enough.** A tag on every sentence makes the read jumpy and longer. Tag where the delivery *changes*: the hook, the turn, the last line.
- **Tags cost time.** A take with many tags and pauses runs seconds longer. The limit is 55 s.
- Put the format's opening direction on the first line (see `delivery` and `open_tag` for the format in `config/voices.json`), then tag only the changes.
- The last line is where the format pays off: deadpan for `twist`, warm and slow for `slow-burn`, the only change in the whole read for `unspoken-rules`.

**Voices** come from the format's shortlist in `config/voices.json`; the first usable one is taken. Set `"voice": "<name>"` in the plan only to override. `python tools/clip.py voices` shows what each format will use on this account.

**After the take**, read what `voice` prints: total seconds (target 46–53, limit 55), words per minute (about 140–155 is right), each shot's length. If it is over the limit the tool says so: ask for a tighter script. Do not use `--retake` just to see if it comes out shorter; change something first (fewer tags, fewer pauses).

## The plan

```json
{
  "voice": {"stability": 0.55, "similarity_boost": 0.75, "seed": 4107},
  "narration": [
    {"shot": "sh01", "text": "[low, measured] For three nights, a tall man watched a lonely house from the trees. [pause] Tonight, he would take the boy inside."}
  ],
  "music": {"prompt": "…", "gain_db": -19},
  "ambience": [{"id": "amb_night", "prompt": "… seamless loop", "shots": ["sh01", "sh02"], "seconds": 20, "gain_db": -25}],
  "sfx": [{"id": "wire_snip", "prompt": "…", "duration_s": 0.7, "at": {"word": "cut", "shot": "sh02", "offset_s": 0.05}, "gain_db": -7}]
}
```

`narration` has one entry per shot, in order. Leave a shot out to send its `vo_text` untouched.

**Where a cue starts (`at`)**

- `{"word": "lights went out", "shot": "sh01", "edge": "end", "offset_s": -0.2}`: on a spoken word or phrase. `edge` is `start` (default) or `end`; `nth` picks a repeat. **Prefer this**: it stays right when the take changes.
- `{"shot": "sh05", "t": 0.1}`: seconds into a shot (`t` negative counts from its end).
- `{"time": 12.3}`: seconds on the film. Avoid.

Line effects up with what the builder animates: the plan's `staging` and `light_change` say which word an action lands on. Use the same word.

## Music

One instrumental bed for the whole film (`music_v2_5`), generated at the film's length.

- Describe genre, instruments, tempo, mood, and **the shape over time**: "tension builds slowly for 40 seconds, thins to near silence, resolves into one warm chord at the end." The model follows structure words.
- Say "instrumental, no vocals, no drums" if you mean it. Sparse music leaves room for the voice.
- The mix puts music about 19 dB under the voice and ducks it further while the narrator speaks. Raise `gain_db` only for a musical moment with no narration.
- Licence: generated music is tied to your ElevenLabs plan's terms. For monetised uploads check them, or set `"enabled": false` and add licensed music later.

## Ambience and effects

Sound effects use `eleven_text_to_sound_v3` (0.5–30 s; `loop` for beds).

- **Ambience**: one bed per place, "seamless loop" in the prompt, 15–25 s. Say what is *not* there ("no birds, no traffic") to keep it clean.
- **Effects**: 5–10 per film is plenty. One sound per clue or action the viewer must notice. Prompt = the sound, the distance, the room: "Single sharp metal wire cutter snip, close, dry." Give `duration_s` close to the real sound.
- Typical gains: hero effect −6 to −9 dB, incidental −12 to −16, ambience −22 to −26.
- **Leave space.** Do not put an effect under the stressed word of a sentence; put it just after (`offset_s` 0.05–0.15) or in the hold. Let the last line be almost dry.

## Check before you return

- `python tools/clip.py voice` printed a total at or under 55 s and no word-mismatch error.
- `python tools/clip.py sound` listed every cue with a start time that makes sense against the shot times.
- You listened with your eyes: no two effects on the same half second, nothing starting before its shot.
