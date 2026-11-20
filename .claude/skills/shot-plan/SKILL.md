---
name: shot-plan
description: The shot plan format (shotplan.json) for a clay-toy Short - fields, rules the validator enforces, and a worked example. Use when writing, fixing or reading a shot plan.
---

# Shot plan

One file, `output/clips/<clip>/shotplan.json`, turns the script into what gets built. It is checked by `python tools/clip.py plan-check <clip>` (`tools/plan.py`). The validator and this page must agree.

A complete, validated example is `examples/the-boy-in-the-basement/shotplan.json`. Read it before writing your first plan. Copy its level of reasoning, not its choices.

## Fields

```json
{
  "clip": "<slug>", "format": "<script format>", "title": "<script title>",
  "logline": "What the viewer should feel by the end, in one sentence.",
  "beat_feelings": {"<beat>": "what the viewer should feel at the end of this beat"},
  "look": {
    "palette": ["#hex", "#hex", "#hex"],
    "palette_note": "what each colour is for",
    "light_story": "how light changes across the film, and why",
    "must_not_show": [{"what": "the man's face", "until_shot": "sh05", "how": "seen from behind or as a shape"}]
  },
  "cast": [{"id": "man", "role": "...", "source": "pack", "spec": {"preset": "preset_father", "brows": "stern"}, "notes": "..."}],
  "sets": [{"id": "basement", "description": "...", "time": "night", "mood": "interior_night",
            "key_from": "where the motivated key comes from", "practicals": ["..."], "dressing": ["..."]}],
  "assets": [{"id": "prop_wire_cutters", "what": "...", "closest": "hero|mid|background", "shots": ["sh02"], "source_hint": "..."}],
  "shots": [{
    "id": "sh01", "set": "<set id>", "cast": ["man"],
    "vo_text": "the exact, continuous slice of narration this shot covers",
    "why_cut": "every shot after the first: what the cut gives that a move or focus shift could not",
    "purpose": "what this shot must do for the story",
    "staging": "what happens, in order, in buildable terms",
    "camera": {"start": "opening framing", "lens_mm": 40, "blur": "none|light|medium|strong|macro",
               "moves": [{"at": "on which words", "move": "slow dolly in", "why": "story reason"}]},
    "focus": [{"at": "on which words", "on": "what is sharp", "why": "story reason"}],
    "light_change": {"what": "...", "why": "..."},
    "clues": ["exact phrase from the script's clues"],
    "hold_after_s": 0.4,
    "sound": "ambience, effects and music idea for this shot"
  }],
  "sound": {"delivery": "how the narrator should sound, and where it changes", "music": "...", "ambience": "..."}
}
```

## What the validator enforces

- All `vo_text` joined equals the script's voiceover **word for word, in order**. Copy, do not retype.
- 4–5 shots is the aim; up to 8 passes with a warning; more is an error.
- Every shot has `set`, `vo_text`, `purpose`, `staging`, `camera.start`. Every camera move has a `why`. Every shot after the first has `why_cut`.
- `set` and `cast` ids exist. Each set has a `mood` (a name from `stagekit.lights.MOODS`).
- Every item in the script's `clues` is listed in the `clues` of the shot that speaks it.
- `must_not_show.until_shot` is a real shot id.
- `hold_after_s` is 0–2.5 per shot and 4 s in total. Holds are real silence after the shot's last word; they are shortened automatically if the take runs long.

## Field notes

- **`cast[].spec`** is passed to `stagekit.cast.cast(...)`: `preset` (`preset_father`, `preset_boy`, `preset_king`, `preset_female`, `preset_police`, `preset_pirate`) or `base` (`base_hoodie`, `base_shirt_tie`, `base_tshirt`) plus `proportions`, `hair`, `hair_color`, `skin`, `palette`, `outerwear`, `beard`, `brows`, `hat`. See `packs/release_1/docs/CHARACTERS.md` for pictures. Reuse the pack before asking for a new character; a non-human or special character goes in `assets` for the asset-maker.
- **`assets`** lists only what the sets do not provide by default: hero props, vehicles, special characters. Use ids like `prop_…`, `vehicle_…`, `creature_…`; the same id is reused from the library next time.
- **`why`** is a sentence about the story. Bad: "push-in adds tension". Good: "we lean in as the watching becomes a decision".
- **`staging`** must be buildable: see "Staging" in `style/STYLE_GUIDE.md`. If the script's action is hard (two characters touching, fingers, climbing), stage around it and say how.
- Write times as words ("on 'the lights went out'"), never as seconds. The builder gets exact times from the voice take.
