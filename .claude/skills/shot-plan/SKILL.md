---
name: shot-plan
description: The shot plan format (shotplan.json) for a Short - the world and its period, the cast and their costumes, sets and marks, shots and the views inside them, setups and payoffs - with the rules the validator enforces and a worked example. Use when writing, fixing or reading a shot plan.
---

# Shot plan

One file, `output/clips/<clip>/shotplan.json`, turns the script into what gets built. `python tools/clip.py plan-check <clip>` (`tools/plan.py`) checks it. The validator and this page must agree.

A complete example that passes the validator is at the end of this page (and `tools/tests/fixtures/plan_new_format.json`, a two-set story). Copy its level of reasoning, not its choices. `examples/the-ring-in-the-pond/shotplan.json` is a plan in the older format (sets without architecture, views without a move): good reasoning about views, not a model for sets or camera.

**Plan format 2.** New plans say `"plan_version": 2`. Format 2 asks the plan for two things the older format left to chance: a complete place (what encloses it, four depth layers, real light sources, things to read, the marks people stand on) and a designed camera (a move, an angle and a side for every view, a transition into every shot). The reason: a builder given only a description builds the minimum the script needs, and a view given only a size is shot as a static cut. A plan without `plan_version` and without any format 2 field is read as the older format, with one warning; do not write new plans that way.

Two words, used strictly:

- **shot**: one staged take in one set at one time of day. A render unit. Usually 2–5 per Short.
- **view**: one camera framing inside a shot. What the viewer experiences. The reference Shorts hold 22–33 framings a minute, so a Short of about a minute plans for roughly that many; the validator accepts 9–33.

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
    "id": "grandpa", "role": "the grandfather who trusts his tools", "base": "ElderManGreyHair", "color": "#4A6FA5",
    "costume": {"recolor": {"primary": "#7A1F2B", "secondary": "#3B3B3B"}, "hide": ["facial_hair"]},
    "reads_as": "wine-red polo, grey hair, charcoal jeans"
  }, {
    "id": "queen", "role": "the queen, a woman", "base": "WomanBunUpdo", "color": "#7D3C98",
    "wants": {"sex": "Female", "age": "Adult", "era": "medieval", "tags": ["gown", "crown"], "hair": "long", "palette_hint": ["purple", "gold"]},
    "reads_as": "purple gown, gold crown, long hair"
  }],
  "sets": [{
    "id": "throne_room", "kind": "interior", "theme": "throne_room", "size_m": [12, 20, 8],
    "description": "what the place is",
    "layout": "camera side; where each person stands (marks); where each story object is; what is visible from where",
    "surfaces": ["castle_stone", "oak_planks"],
    "architecture": {
      "floor": "flagstones with a long red runner", "ceiling": "timber-ribbed barrel vault, 8 m",
      "walls": [
        {"side": "N", "what": "stone, the dais and throne against it", "openings": []},
        {"side": "E", "what": "stone between tall arched windows", "openings": [{"kind": "window", "id": "win_e1", "vista": "a sunlit courtyard and hills"}]},
        {"side": "S", "what": "stone with big double doors", "openings": [{"kind": "door", "id": "gate", "vista": "the castle bailey"}]},
        {"side": "W", "what": "stone with a plank side door", "openings": [{"kind": "door", "id": "side", "vista": "a torch-lit corridor"}]}],
      "features": ["two rows of fluted columns", "a dais of three steps at the north end"]},
    "layers": {"foreground": ["a column edge", "a hanging banner"], "midground": ["the runner", "benches"], "background": ["tapestries", "weapon racks"], "beyond": ["courtyard through the windows"]},
    "dressing": [{"what": "banner", "where": "between the windows", "count": 8}, {"what": "goblet", "where": "on the long tables", "count": 12}],
    "practicals": [{"what": "chandelier", "where": "above the nave"}, {"what": "brazier", "where": "either side of the dais"}, {"what": "wall sconce", "where": "on every column"}],
    "atmosphere": ["dust motes in the window light"],
    "details": [{"what": "royal crest banner", "where": "behind the throne"}, {"what": "notice on the door", "where": "south doors"}, {"what": "tapestry of a battle", "where": "west wall"}],
    "must_survive": ["front", "reverse", "high"],
    "marks": {"throne": [0, 8.7, 0.45], "petitioner": [0, 1, 0]}
  }],
  "setups": [{"what": "the gate holds the water in", "shown_in": "sh01/the_gate", "pays_off_in": "sh04/lifts_the_gate"}],
  "shots": [{
    "id": "sh01", "set": "throne_room", "time": "interior_day", "cast": ["queen", "gardener"],
    "transition_in": {"type": "whip", "dur": 0.4, "dir": "left"},
    "line_of_action": {"between": ["queen", "gardener"], "camera_side": "front"},
    "vo_text": "the exact, continuous slice of narration this shot covers",
    "purpose": "what this shot must do for the story",
    "action": "what happens, in order, as things a camera can see: who does what, with what, and how others react",
    "views": [{
      "id": "ring_slips", "on": "start", "size": "medium",
      "move": {"type": "dolly", "amount": 0.1, "duration_s": 2.0, "ease": "ease_out", "target": "queen"},
      "framing": "two_shot", "angle": "eye", "side": "front", "lens_mm": 45, "enter": "cut",
      "shows": "who and what is in frame, doing what",
      "why": "what the viewer needs now that the view before did not give",
      "inside": "what changes during the view (needed if it runs longer than about 6 s)",
      "still_reason": "only on a static view longer than 1.2 s: why the camera must be still"
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
- Every `cast[].base` is a character of `config/cast.json` (an old name such as `TeenBoy` still works and gives a warning) or a body id (`Male_Teen`: a bare body, a warning). A base that does not exist is an error: run `python tools/clip.py casting <clip>`.
- A character wears one outfit and any add-ons: each must be fit-accepted on the character's body (`pass` and review `accept`; a rigid add-on may have review `none`) in `library/wardrobe/index.json`, licence `cc0`, `royalty_free` or `own`, and allowed in `world.era` (outfit and add-on `era` lists). The outfit of the character must belong to the era.
- Every `recolor` key is a colour slot of that character (`python tools/clip.py cast <Name>` lists them: the outfit's palette slots such as `primary` and `secondary`, a garment's own name such as `polo`, an add-on's slot, `hair`, `facial_hair`, `skin`). Every `hide` pattern matches something (`hair`, `facial_hair`, `<outfit>.<piece>` or `<piece>`, `addon:<item>`) and never leaves a bare body: an outfit piece can only come off when another worn piece covers its slot. Every `wear` item is an add-on of the wardrobe.
- A character whose `status` is `draft` gives the warning "not through Gate A": characters and wardrobe are approved with `python tools/clip.py gate <clip> A` after `cast-sheets`.
- Every surface named in `world.surfaces` and `sets[].surfaces` is in `library/materials/catalog.json` and belongs to the era.

**Views.**
- Every shot has `set`, `time` (a light mood: `day_clear`, `day_soft`, `morning`, `golden_hour`, `sunset`, `dusk`, `night_moon`, `storm`, `interior_day`, `interior_warm`, `candlelit`, `office_day`, `office_night`, `cave`: the moods of `stagekit/lights.py`), `vo_text`, `purpose`, `action`, and at least one view.
- A view has `id`, `on`, `size` (`insert`, `close`, `medium`, `full`, `wide`), `shows`, `why`.
- `on` is the words of this shot's `vo_text` on which the view starts, in order. The first view of a shot uses `"start"`.
- Warnings: a view shorter than about 0.7 s that is not an insert; a view longer than about 6.5 s with no `inside`; fewer than 9 or more than 33 views in the Short (`style/style.json` > `views` > `per_short`); a `wide` first view.

**Sets (format 2).** Errors unless said otherwise. The reason is in each line: it is what the builder would otherwise leave out.
- `kind` is `interior`, `exterior` or `mixed`; `theme` is `custom` or one of the dressing themes of `stagekit/dress.py` (`throne_room`, `great_hall`, `castle_kitchen`, `tavern`, `peasant_cottage`, `office_open_plan`, `office_private`, `home_living_room`, `home_kitchen`, `shop_interior`, `market_street`, `village_square`, `army_camp`, `battlefield`, `city_street`). A theme must belong to `world.era` and match the kind (a room theme for an interior).
- `size_m` is `[w, d, h]` for an interior (height 2-40 m), `[w, d]` or `[w, d, h]` for an exterior: the stage the people can walk on.
- `architecture` says what encloses the place. An interior has `floor`, `ceiling` and **all four** `walls` (`N` is the far wall, `S` the camera side, as in `arch.room`), each with a `what`; an exterior has `ground`. Every opening (`door`, `window`, `gap`, `arch`) names its `vista`: what is seen through it. An opening with nothing behind it renders as a void. `features` (columns, beams, stairs, a dais) is a list of strings; an interior without any gets a warning.
- `layers` has `foreground`, `midground`, `background` and `beyond`, none empty: something near the camera that partly covers the frame, the stage where the action happens, the far side, and what is seen past the set (sky, a vista, a room through a door).
- `dressing` is `[{"what", "where", "count"?}]`. Layers and dressing together name at least `style.json > sets.min_prop_types_wide` (14) different kinds of thing. A warning if the counted objects are under `min_objects_wide` (60). The old free-text list is accepted with a warning.
- `practicals` (visible light sources, each with `where`; at least 3 for an interior), `atmosphere` (at least 1: haze, dust, smoke, steam), `details` (at least 3 readable in-world things: signs, banners, papers).
- `must_survive` lists the angles the set will be seen from across all its shots, from `front`, `reverse`, `left`, `right`, `high`, `low`; it includes `front`. Every view's `side` (and a `low` or `high`/`top` `angle`) must be in it. Add an angle only when a view needs it: the builder then makes walls, ceiling and dressing that hold up from there.
- `marks` is `{"name": [x, y, z]}`: the standing points and object positions the shots use. The set file's `MARK` must contain every name (checked when the set is built, see Build-time agreement).

**Camera (format 2).**
- Every view has `move.type` from the camera library: `static`, `drift`, `dolly`, `truck`, `pan`, `tilt`, `orbit`, `crane`, `follow`, `track_with`, `whip`, `through`, `rack_focus`, `dolly_zoom`, `handheld`, `reveal`. Optional `amount` (a number: metres for a dolly or truck, degrees for a pan, tilt or orbit, metres of rise for a crane), `duration_s`, `ease` (`linear`, `ease_in`, `ease_out`, `ease_in_out`, `settle`, `whip`). `whip`, `through`, `orbit`, `follow`, `track_with`, `rack_focus` and `reveal` need a `target` (a view id, a cast id or a mark). A whip lasts 0.25-0.5 s (warning).
- `angle` is `eye`, `low`, `high` or `top`; `side` is one of the set's `must_survive`; `framing` (optional) is `ots`, `two_shot`, `reverse`, `low_hero`, `top_down`, `establish`, `insert` or `profile` (a warning when it disagrees with `angle` or `size`); `lens_mm` (optional) is 10-200.
- **Held frames.** A `static` view longer than 1.2 s is an error unless it says `still_reason`. Held views (`static` and `drift`) together are a warning above `style.json > camera > max_static_share` (40%) of the screen time: the references move the camera for 60-80% of it.
- **Variety (warnings).** At least 3 different move types besides `static` in the film, and no one type in more than half the views.
- **How a view is reached.** `enter` is `cut` (default), `travel`, `whip` or `through`. The first view of a shot is a `cut`, or `whip` when the shot's own `transition_in` is a whip. A view entered by a `whip` or `through` follows a view whose `move.type` is that same move with this view as the `target`, and the other way round.
- **Line of action.** A shot with two or more characters gives `line_of_action: {"between": [a, b], "camera_side": "front"}` (cast ids or marks). A view whose `side` is the opposite of `camera_side` (`front`/`reverse`, `left`/`right`) is an error unless it says `cross_line: true`: crossing swaps who is left and who is right, and the viewer loses track of who is who.
- **Wide coverage.** Each set is shown at least once in a `wide` view or `establish` framing (error if never; a warning if its first shot does not). A set listed in `world.must_not_show` with `"set": "<id>"` is exempt.
- **Transitions.** `transition_in` on a shot (not the first) is a type or `{type, dur, dir, color}`: exactly what `tools/assemble.py` reads (`cut`, `whip`, `dissolve`, `dip`, `flash`, `wipe`, `match`). A film in which every boundary is a plain cut gets a warning naming the boundary where a camera event fits (a whip into a new place, a dissolve into a later time).
- **`line_of_action`, `transition_in`, `enter` and `move` are read by the builder**: the shot script uses `cam.line(a, b)`, and the same moves as the plan.

**Build-time agreement (not the plan validator).** When a shot is built (`clip.py stills`), the set file `blender/set_<id>.py` is compared with the plan: its `MARK` contains every planned mark (a missing one blocks, a mark more than 0.5 m from the plan warns), its `THEME` equals the plan's theme, and its `LIGHT` has the shot's `time`. Then `stagekit.audit` measures the built set from its wide (`WIDE` in the set file) and from every view of the shot; what it finds goes into `review/<shot>/checks.json` as items with `source: "set"`, and a blocking item stops the shot like a broken camera. `clip.py setpreview <clip>` does the same for every set and light mood without staging a shot; it gates Gate B.

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

## Writing sets

A set is a complete place that a camera can go round, not the minimum the script needs. Write it in this order, as the builder will build it:

1. **Marks first.** List where people stand and where story objects are (`marks`), from the action of the shots. Everything else is arranged around them, never on them.
2. **The enclosure.** `architecture`: floor, ceiling, four walls, with every door and window and what lies behind it. Ask "what is seen through this?" for each opening: a street, a courtyard, a lit corridor. If you cannot answer, remove the opening.
3. **Depth.** `layers`: one thing at least in each of the four. The foreground occluder (a column edge, a plant) is what makes a wide read as a place rather than a stage.
4. **Light you can see.** `practicals` are lamps and windows in the picture, not just the light that comes from nowhere. `atmosphere` (dust in a window shaft, haze, steam) separates the layers.
5. **Things to read.** `details` are signs, banners, papers, labels: they tell the viewer where they are without a word of narration.
6. **Count the kinds.** Fourteen different kinds of thing is what a lived-in wide holds; a set of one table and four chairs has three.
7. **Angles last.** `must_survive` comes from the views you wrote: any `side` you used, plus `low` or `high` if an `angle` needs it. A set with a `reverse` is built with real walls and a ceiling on the camera's side too (the builder hides the near wall per view).

## Writing the camera

For every view decide four things after the framing: what the camera **does** (`move`), from **where** (`angle`, `side`), and how it **arrives** (`enter`). Reference Shorts move the camera for 60-80% of the screen time, so a still frame needs a reason.

| The moment… | Usually means |
|---|---|
| a person realises something, a small reaction | a slow `dolly` in (1.5-3 s, ease out), or a held `static` with a `still_reason` |
| a new place, or the result that changes the place | a `crane` or `establish` framing from `high`; the same wide again later for "afterwards" |
| two people trade something | `two_shot` or `ots`, a `truck` beside the action; keep the camera on one side of the line |
| an object the ending needs | an `insert` framing with `orbit` or `handheld`, readable at 9:16 |
| one thing leads straight to another | a `whip` (0.3-0.5 s) to the next view's subject, or a `through` an opening; `enter` says the same on the next view |
| the story jumps to another place or time | `transition_in` on the shot: `whip` for energy, `dissolve` for later, `dip` for a break |

- **A transition is a camera event, not decoration.** Over half of the transitions in the reference Shorts are a whip, a trip through something, or a crane, not a plain cut. Give most shot boundaries one.
- **Wides.** Low or eye level for people, high or top-down for geography. Show every set wide once, early.
- **Sides.** Keep one side per shot (`line_of_action.camera_side`). Cross it only on purpose, with `cross_line: true`, and show the crossing.
- **`amount` is for the builder**: the numbers are small and ordinary (a 10% push, a 25 degree orbit, 1 m of crane). Do not ask for more than the move library does.

## Field notes

- **`cast[].base`** is a character from `python tools/clip.py cast`. Reuse the cast before asking for anything else. **`costume`** is passed to the actor as written, in this order: `wear` (add-ons from the wardrobe, with options such as `color`), then `hide`, then `recolor` (slots from `clip.py cast <Name>`). Give each main character one signature `color` nobody else has.
- **`cast[].wants`** (optional) says who is needed when the base is not in the cast yet: `{"sex": "Female", "age": "Adult", "era": "medieval", "tags": ["gown", "crown"], "hair": "long", "facial_hair": "beard", "palette_hint": ["purple", "gold"]}`. `sex` is `Male` or `Female`, `age` is `Kid`, `Teen`, `Adult` or `Senior`; `tags` name garments, add-ons or looks; `palette_hint` is colour names or `#hex` for the top, then the bottom. Without `sex` and `age` they are read from the character's body, or from `role` and `reads_as`. `python tools/clip.py casting <clip>` matches every cast entry: EXISTING (the base satisfies the plan), ADAPT (the closest body dressed from fit-accepted items; `--apply` registers it as a draft and rewrites `base`) or MISSING (an explicit ask: an outfit or add-on fit-accepted on that body, a hairstyle, a Mixamo clip). It writes `casting.json` and `casting.md` and exits 2 while anything is MISSING. `base` may be a placeholder name until then.
- **`sets[].layout`** is the most useful paragraph in the plan for the builder: camera side, each person's mark, each story object's position, and what must be visible from where. Lay places out along the view (depth), not across it: a 9:16 frame is narrow. It says the same as `marks` and `architecture`, in words.
- **`sets[].marks`** are the same names the set file's `MARK` uses and the shot scripts use (`M["queen"]`). Agree them once, here.
- **`do`** (optional, per shot): the named actions that carry the shot, in order, so the builder and the validator agree on what is performed: `"do": [{"who": "gardener", "action": "pick_up", "what": "ring"}, {"who": "queen", "action": "laugh"}]`. `who` is a cast id; `action` is a name from `python tools/clip.py actions` (the validator rejects unknown names and points at `docs/ADDING_NEW_ACTIONS.md`); `what` / `to` are free text.
- **`cast[].why_new`** (optional): one line when `base` is a character made for this story with the `character-maker` skill (reuse first, then re-costume, then build).
- **`action`** must be buildable. The pack has front, three-quarter and side drawings and no back view; people face the camera or stand in profile. Skip climbing and getting up or down: start, cut, result.
- **`time`** per shot carries the light story. A different `time` on the same `set` is how a film says "later".
- **`sound`** lists every contact on screen (a plop, a crack, a splash): the sound designer places effects on the same words the builder keys the action to.

## Worked example

A complete plan in format 2 that passes `plan-check` (`tools/tests/test_plan_schema.py` extracts it from this page and checks it, so it cannot go stale). Two shots in one office: the morning hook and the same place that night, joined by a dissolve; a whip inside the first shot; one static held view with its reason; nine views with nine different camera moves. Its script is simply its own `vo_text` in order.

<!-- plan-example:start -->
```json
{
 "plan_version": 2,
 "clip": "the-note-on-the-screen",
 "format": "micro-butterfly",
 "title": "The Note on the Screen",
 "logline": "A man's blank screen finally lights up after a note and a key.",
 "world": {
  "era": "modern",
  "place": "A big open-plan office, present day.",
  "time_span": "A weekday morning, then the same office that night.",
  "rules": [
   "plain office furniture, no brand names",
   "the note is yellow and handwritten; the key is brass with a paper tag",
   "the whole floor is in frame in every wide view"
  ],
  "palette": ["#2B6CB0", "#E0B040", "#B8BCC4", "#5A3D2B"],
  "palette_note": "Sam blue, the note and shop lamps yellow, grey office, brown shop wood",
  "surfaces": ["carpet_grey", "painted_wall"],
  "must_not_show": []
 },
 "cast": [
  {
   "id": "sam",
   "role": "the office worker who gets the note",
   "base": "TeenBoyDarkHair",
   "color": "#2B6CB0",
   "reads_as": "blue shirt, dark hair, tired eyes"
  }
 ],
 "sets": [
  {
   "id": "office",
   "kind": "interior",
   "theme": "office_open_plan",
   "size_m": [16.0, 11.0, 2.8],
   "description": "A big open-plan office on a weekday: four rows of workstations on grey carpet under a tiled ceiling, a city outside the windows, a glass meeting room in the north-east corner.",
   "layout": "Camera side is south (-Y). Sam's desk is in the first row at the left (worker_a); the middle aisle runs away from the camera to the glass meeting room at the far right. The kitchenette is on the east wall. From the south-west corner the wide sees the whole floor with the city in the north windows; the reverse angle looks back at the entrance door and the street windows.",
   "surfaces": ["carpet_grey", "painted_wall", "ceiling_tile"],
   "architecture": {
    "floor": "grey carpet tiles with a darker walkway stripe down the middle aisle",
    "ceiling": "suspended white tile ceiling, 2.8 m, with recessed light panels",
    "walls": [
     {
      "side": "N",
      "what": "painted white wall, four wide office windows",
      "openings": [
       {"kind": "window", "id": "win_N-6", "vista": "the city skyline: towers and a pale sky"},
       {"kind": "window", "id": "win_N-2", "vista": "the city skyline: towers and a pale sky"},
       {"kind": "window", "id": "win_N+2", "vista": "the city skyline: towers and a pale sky"},
       {"kind": "window", "id": "win_N+6", "vista": "the city skyline: towers and a pale sky"}
      ]
     },
     {
      "side": "S",
      "what": "painted white wall with three shop-front windows",
      "openings": [
       {"kind": "window", "id": "win_S-5", "vista": "the street below: parked cars and shopfronts"},
       {"kind": "window", "id": "win_S+0", "vista": "the street below: parked cars and shopfronts"},
       {"kind": "window", "id": "win_S+5", "vista": "the street below: parked cars and shopfronts"}
      ]
     },
     {
      "side": "W",
      "what": "painted white wall with a glass entrance door standing a little open",
      "openings": [{"kind": "door", "id": "entrance", "vista": "rooftops under a pale sky"}]
     },
     {"side": "E", "what": "painted white wall with a notice board, a whiteboard and the kitchenette counter", "openings": []}
    ],
    "features": ["glass-walled meeting room in the north-east corner", "suspended ceiling grid with light panels", "kitchenette counter along the east wall"]
   },
   "layers": {
    "foreground": ["desk partition screen edge", "potted plant", "chair backs"],
    "midground": ["workstation rows with desks, chairs and monitors", "water cooler", "printer"],
    "background": ["filing cabinets", "bookcases", "whiteboard", "notice boards", "wall clock"],
    "beyond": ["city skyline through the north windows", "street through the south windows", "rooftops through the entrance door"]
   },
   "dressing": [
    {"what": "monitor", "where": "on every desk", "count": 12},
    {"what": "keyboard", "where": "in front of each monitor", "count": 12},
    {"what": "office chair", "where": "at every desk", "count": 12},
    {"what": "mug", "where": "on desks and the kitchenette", "count": 10},
    {"what": "paper stack", "where": "on desks and the printer", "count": 14},
    {"what": "laptop", "where": "on the meeting-room table and four desks", "count": 6},
    {"what": "desk phone", "where": "on desks", "count": 10},
    {"what": "poster", "where": "on the east wall", "count": 5},
    {"what": "waste bin", "where": "under desks and by the printer", "count": 6},
    {"what": "coat stand", "where": "by the entrance door", "count": 1},
    {"what": "desk lamp", "where": "on the first two rows of desks", "count": 8}
   ],
   "practicals": [
    {"what": "recessed ceiling light panels", "where": "in rows across the whole ceiling"},
    {"what": "desk lamps", "where": "on the first two rows of desks"},
    {"what": "monitor glow", "where": "on every desk"},
    {"what": "window light", "where": "through the four north windows"}
   ],
   "atmosphere": ["dust motes in the window light", "a soft light shaft from the north windows"],
   "details": [
    {"what": "whiteboard with a weekly plan", "where": "meeting-room east wall"},
    {"what": "notice board with printed rotas", "where": "east wall"},
    {"what": "wall clock", "where": "above the kitchenette"},
    {"what": "desk number plates", "where": "on each desk partition"}
   ],
   "must_survive": ["front", "reverse", "high", "low"],
   "marks": {"worker_a": [-5.0, -2.55, 0.0], "worker_b": [-1.6, 0.25, 0.0], "kitchen": [6.6, -2.6, 0.0]}
  }
 ],
 "shots": [
  {
   "id": "sh01",
   "set": "office",
   "time": "office_day",
   "cast": ["sam"],
   "vo_text": "Every morning Sam stares at the same blank screen in a busy open office. Today a tiny note is stuck to it. It says: go to the shop on the corner.",
   "purpose": "Hook: an ordinary man at an ordinary desk gets a strange note, in a place big enough to feel lonely in.",
   "action": "Sam sits at his desk in the first row and stares at his blank screen. The office hums around him. A small yellow note on the screen says to go to the shop on the corner.",
   "views": [
    {
     "id": "sam_stares",
     "on": "start",
     "size": "medium",
     "shows": "Sam, in profile, at his desk, staring at a blank screen while the office blurs behind him",
     "why": "the first second shows who this is and what he is stuck with",
     "move": {"type": "dolly", "amount": 0.1, "ease": "ease_out"},
     "angle": "eye",
     "side": "front",
     "enter": "cut"
    },
    {
     "id": "busy_office",
     "on": "in a busy open office",
     "size": "wide",
     "shows": "the whole open-plan floor from the south-west corner: rows of desks, the city in the windows, Sam small at the left",
     "why": "the place, and how many other people are not looking at his screen",
     "move": {"type": "crane", "amount": 1.2, "ease": "ease_in_out"},
     "angle": "high",
     "side": "front",
     "enter": "cut",
     "framing": "establish"
    },
    {
     "id": "tiny_note",
     "on": "Today a tiny note",
     "size": "insert",
     "shows": "the yellow note stuck to the corner of the screen, a shaky close look",
     "why": "the clue the story turns on must be the subject of a frame",
     "move": {"type": "whip", "target": "go_to_shop", "duration_s": 0.4},
     "angle": "eye",
     "side": "front",
     "enter": "cut",
     "framing": "insert"
    },
    {
     "id": "go_to_shop",
     "on": "It says",
     "size": "close",
     "shows": "Sam reads the note, his eyebrows rising",
     "why": "his reaction is the question the next shot answers",
     "move": {"type": "static"},
     "angle": "eye",
     "side": "front",
     "enter": "whip",
     "still_reason": "held on Sam's face while the message lands; any move would soften the beat"
    }
   ],
   "hold_after_s": 0.0,
   "sound": "office hum, keyboard clicks, a paper note rustling"
  },
  {
   "id": "sh03",
   "set": "office",
   "time": "office_night",
   "cast": ["sam"],
   "vo_text": "That night the office is empty. Sam opens the bottom drawer and finds a key. He turns it, and the screen finally lights up.",
   "transition_in": {"type": "dissolve", "dur": 0.6},
   "purpose": "Payoff: the same office, now empty at night; the key and the drawer, then the screen answers.",
   "action": "The office is dark and empty except for the glow of the street. Sam crouches at his desk, opens the bottom drawer, finds a key, turns it, and his blank screen lights up.",
   "views": [
    {
     "id": "empty_office",
     "on": "start",
     "size": "wide",
     "shows": "the same floor at night: dark rows of desks, city lights in the windows, Sam alone at the left",
     "why": "the same place as the hook, changed: that is the passage of the day",
     "move": {"type": "pan", "amount": 18, "ease": "ease_in_out"},
     "angle": "eye",
     "side": "front",
     "enter": "cut"
    },
    {
     "id": "opens_drawer",
     "on": "Sam opens the bottom drawer",
     "size": "medium",
     "shows": "Sam crouches at his desk and pulls the bottom drawer open",
     "why": "the action that leads to the key",
     "move": {"type": "truck", "amount": 0.25},
     "angle": "eye",
     "side": "front",
     "enter": "cut"
    },
    {
     "id": "finds_key",
     "on": "and finds a key",
     "size": "insert",
     "shows": "a brass key with a paper tag lying in the drawer",
     "why": "the object the ending needs, readable",
     "move": {"type": "handheld", "amount": 0.012},
     "angle": "eye",
     "side": "front",
     "enter": "cut",
     "framing": "insert"
    },
    {
     "id": "key_turns",
     "on": "He turns it",
     "size": "close",
     "shows": "from low behind the desk, Sam's hand turning the key in the lock",
     "why": "the action the key was for",
     "move": {"type": "tilt", "amount": 10, "ease": "ease_out"},
     "angle": "low",
     "side": "reverse",
     "enter": "cut"
    },
    {
     "id": "screen_lights",
     "on": "and the screen finally",
     "size": "medium",
     "shows": "Sam's face lit by the screen as it comes on",
     "why": "the answer the hook asked for",
     "move": {"type": "reveal", "target": "worker_a", "ease": "ease_in_out"},
     "angle": "eye",
     "side": "front",
     "enter": "cut"
    }
   ],
   "hold_after_s": 0.0,
   "sound": "a lock clicking, a screen powering up with a soft chime"
  }
 ],
 "sound": {"delivery": "warm and curious", "music": "light, a little mysterious", "ambience": "office hum"}
}
```
<!-- plan-example:end -->
