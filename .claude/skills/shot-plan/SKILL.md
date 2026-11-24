---
name: shot-plan
description: The shot plan format (shotplan.json) for a Short - the world and its period, the cast and their costumes, sets and marks, shots and the views inside them, setups and payoffs - with the rules the validator enforces and a worked example. Use when writing, fixing or reading a shot plan.
---

# Shot plan

One file, `output/clips/<clip>/shotplan.json`, turns the script into what gets built. `python tools/clip.py plan-check <clip>` (`tools/plan.py`) checks it. The validator and this page must agree.

A complete, validated example is `examples/the-ring-in-the-pond/shotplan.json`. Read it before writing your first plan. Copy its level of reasoning, not its choices.

Two words, used strictly:

- **shot**: one staged take in one set at one time of day. A render unit. Usually 2–5 per Short.
- **view**: one camera framing inside a shot. What the viewer experiences. Usually 9–24 per Short.

## Fields

```json
{
  "clip": "<slug>", "format": "<script format>", "title": "<script title>",
  "logline": "What the viewer should feel by the end, in one sentence.",
  "world": {
    "era": "medieval",
    "place": "one sentence: where we are and what is in it",
    "time_span": "how time passes across the film, and the light for each part",
    "rules": ["what belongs here", "what never appears", "the thing that must be visible in every wide view"],
    "palette": ["#hex", "#hex", "#hex"], "palette_note": "who or what owns each colour",
    "surfaces": ["castle_stone", "oak_planks", "pond_water"],
    "must_not_show": [{"what": "the thief's face", "until": "sh03/reveal", "how": "hood, or from the shoulder down"}]
  },
  "cast": [{
    "id": "rich_man", "role": "the clever rich man who trusts his tools", "base": "AdultMan", "color": "#7A1F2B",
    "costume": {"recolor": {"tunic_tan": "#7A1F2B"}, "hide": ["Tunic_Lace*"], "wear": [{"item": "beret"}, {"item": "ruff"}]},
    "reads_as": "wine-red coat with gold buttons, white ruff, plumed cap"
  }],
  "sets": [{
    "id": "pond_garden", "description": "what the place is",
    "layout": "camera side; where each person stands (marks); where each story object is; what is visible from where",
    "surfaces": ["..."], "dressing": ["edges and background only"]
  }],
  "setups": [{"what": "the gate holds the water in", "shown_in": "sh01/the_gate", "pays_off_in": "sh04/lifts_the_gate"}],
  "shots": [{
    "id": "sh01", "set": "pond_garden", "time": "day_clear", "cast": ["queen", "gardener"],
    "vo_text": "the exact, continuous slice of narration this shot covers",
    "purpose": "what this shot must do for the story",
    "action": "what happens, in order, as things a camera can see: who does what, with what, and how others react",
    "views": [{
      "id": "ring_slips", "on": "start", "size": "medium",
      "shows": "who and what is in frame, doing what",
      "why": "what the viewer needs now that the view before did not give",
      "inside": "what changes during the view (needed if it runs longer than about 6 s)"
    }],
    "hold_after_s": 0.0,
    "sound": "ambience and every contact effect on screen, so the sound designer can place them"
  }],
  "sound": {"delivery": "how the narrator should sound", "music": "...", "ambience": "..."}
}
```

## What the validator enforces

**The narration.** All `vo_text` joined equals the script's voiceover word for word, in order. Copy, do not retype.

**One world.**
- `world.era` is one of the periods in `config/cast.json` (`python tools/clip.py cast` lists them). `world.place` and `world.rules` are filled in.
- Every `cast[].base` is a pack character whose period includes the era, or one with a costume recipe for it (`python tools/clip.py cast <Name>` shows the recipe; its `hide` parts are then required).
- Every wardrobe `item` exists and belongs to the era. Every `recolor` key and `hide` pattern exists on that character.
- Every surface named in `world.surfaces` and `sets[].surfaces` is in `library/materials/catalog.json` and belongs to the era.

**Views.**
- Every shot has `set`, `time` (a light mood: `day_clear`, `day_soft`, `morning`, `golden_hour`, `sunset`, `dusk`, `night_moon`, `storm`, `interior_day`, `interior_warm`, `cave`), `vo_text`, `purpose`, `action`, and at least one view.
- A view has `id`, `on`, `size` (`insert`, `close`, `medium`, `full`, `wide`), `shows`, `why`.
- `on` is the words of this shot's `vo_text` on which the view starts, in order. The first view of a shot uses `"start"`.
- Warnings: a view shorter than about 0.7 s that is not an insert; a view longer than about 6.5 s with no `inside`; fewer than 9 or more than 24 views in the Short; a `wide` first view.

**Fair payoffs.**
- Each `setups` entry names real `shot/view` ids, and `shown_in` comes before `pays_off_in`.
- Formats with a turn (`rule-of-three`, `twist`, `ticking-clock`, `slow-burn`) get a warning without any `setups`.
- Every item in the script's `clues` is listed in the `clues` of the view that speaks it.

**Timing.** `hold_after_s` is 0–2.5 per shot and 4 s in total.

## Writing views

Work through the narration clause by clause and ask what the viewer needs to see for each one.

| The clause… | Usually means |
|---|---|
| names a new thing that matters | a view with that thing as its subject, starting on or just before the noun |
| is an action too small to read at this size | an `insert` |
| is a reaction, or a line in quotation marks | a `close` or `medium` on that character (the builder moves the mouth on quoted words) |
| establishes the place, or shows a result that changes the whole place | a `wide`: reuse the same wide so the change is obvious |
| continues the action already on screen | no new view: note it in `inside` |

- **The first view shows the character and the event of the first clause, already happening.** Not the place.
- **`on` is where the picture starts, not where the word ends.** Start a view on the first word of the clause it shows; the builder leads it by a few frames.
- **Say how the camera gets there only when it matters:** "the camera travels across the water to the gate" in `inside` or `shows`. The builder chooses cut or travel otherwise.
- **`why` is about the viewer.** Bad: "variety". Good: "the reason it fails must be seen: the ring is smaller than the hole".
- Write times as words, never as seconds.

## Field notes

- **`cast[].base`** is a name from the pack. Reuse the pack before asking for anything else. **`costume`** is passed to the actor as written: `recolor` (keys from `clip.py cast <Name>`), `hide` (part-name patterns), `wear` (wardrobe items with options). Give each main character one signature `color` nobody else has.
- **`sets[].layout`** is the most useful paragraph in the plan for the builder: camera side, each person's mark, each story object's position, and what must be visible from where. Lay places out along the view (depth), not across it: a 9:16 frame is narrow.
- **`do`** (optional, per shot): the named actions that carry the shot, in order, so the builder and the validator agree on what is performed: `"do": [{"who": "gardener", "action": "pick_up", "what": "ring"}, {"who": "queen", "action": "laugh"}]`. `who` is a cast id; `action` is a name from `python tools/clip.py actions` (the validator rejects unknown names and points at `docs/ADDING_NEW_ACTIONS.md`); `what` / `to` are free text.
- **`cast[].why_new`** (optional): one line when `base` is a character made for this story with the `character-maker` skill (reuse first, then re-costume, then build).
- **`action`** must be buildable. The pack has front, three-quarter and side drawings and no back view; people face the camera or stand in profile. Skip climbing and getting up or down: start, cut, result.
- **`time`** per shot carries the light story. A different `time` on the same `set` is how a film says "later".
- **`sound`** lists every contact on screen (a plop, a crack, a splash): the sound designer places effects on the same words the builder keys the action to.
