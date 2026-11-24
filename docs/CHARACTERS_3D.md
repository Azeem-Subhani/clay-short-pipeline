# The 3D cast

Every standard character is now one real model: a round body, a painted face that follows the head, and clothes, hair and
hats with thickness and material. The camera can go anywhere round a figure, including behind it. Nothing is swapped
or mirrored when the camera moves.

The look (approved on the Queen): no outline; sturdy arms, hands and feet; eyes with a white, a big iris and
catch-lights, whose opening changes shape for each expression; a soft back light from the light rig that lifts the
figures off the set.

Shot files and the action library do not change. `cast.actor(...)` and `cast.from_plan(...)` return a 3D figure whenever
the character has a sheet in `config/cast3d.json` or `config/cast3d_custom.json`.

| | |
|---|---|
| Characters | 92 converted from the 2D pack, plus the ones made in this project (`config/cast3d_custom.json`) |
| Left out on purpose | Ghost, Mermaid, Dragon, Fairy, Robot, Alien, Werewolf, Mummy, Genie, Goblin, Monster, Devil, Skeleton. A plan that casts one of these still gets the flat 2D character, if the 2D pack is installed. Decide per story. |
| Pictures | `docs/lineup_3d_front.png`, `docs/lineup_3d_3q.png`, `docs/lineup_3d_back.png`, `docs/wardrobe_3d.png` |
| Code | `tools/blender/stagekit/fig3d.py` (builds a figure from a sheet), `tools/blender/stagekit/cast3d.py` (the actor) |
| Tools | `tools/chars3d/` : `look3d.py`, `lineup3d.py`, `action_test3d.py`, `run_actions.py`, `convert_pack.py`, `dump_pack.py` |

The 2D pack is no longer needed for the 92. To force the old flat cast for a whole project, put `CAST_STYLE=2d` in `.env`.

## Using a character in a shot

Nothing new to learn. The calls are the ones in the `stagekit` skill:

```python
queen = cast.from_plan("queen", at=M["queen"], face="left", view="3q")
queen.do("pick_up", ring, hit=shot.t("picked up"))
queen.expr("surprised", t)
t1 = queen.walk(t, to=(2.0, -3.0))
```

What is different, because the figure is real:

- **`face` and `view` turn the whole body.** `view="front"` faces the camera, `"3q"` turns about 40 degrees toward the
  facing side, `"side"` turns to profile. `face="left"` / `"right"` is that side on screen. The heading is measured from
  where the camera stands at that moment and then held in the world. When the camera moves on, the figure does not turn
  with it. That is what lets a dolly go round someone.
- **`a.heading((x, y), t)`** turns the figure to face a point in the world, whatever the camera. `a.heading(90, t)` takes
  a compass angle (0 = toward -Y, 90 = toward +X). Use it when two people must face each other while the camera circles.
- **Walking turns the figure toward where it goes**, on planted feet. `then_view="3q"` turns it back toward the camera
  on arrival. `cycle="walk" | "run" | "sneak"`.
- **`reach` is a reach in space.** The palm goes to the world point; it no longer depends on the camera.
- **More faces.** `expr(name, t)` sets the whole face (eye opening, iris, brows, mouth, tears):

  | Name | Looks like |
  |---|---|
  | `neutral`, `happy` | open eyes; happy lifts the lower lid and smiles |
  | `laugh`, `grin` | eyes shut in an arch; an open laugh / a wide grin with both rows of teeth |
  | `excited` | wide eyes, big iris and catch-lights, open laugh |
  | `surprised`, `worried`, `scared` | wide eyes, small iris; round mouth / worried mouth / both |
  | `angry` | lids slanted down toward the nose, frown, teeth |
  | `sad`, `weeping`, `crying` | lids slanted the other way; plus a tear; eyes shut with streaming tears and an open mouth |
  | `sly`, `sleepy` | half-shut eyes with a smirk / without |
  | `wink` | one eye shut, a smile |

  `a.eyes(dx, dz, t)` moves the iris (dx +1 toward the facing side, dz +1 up). `a.blink(t)` and `a.eyes_closed(t0, t1)`
  shut the lids. The older names `joyful, amazed, gasp, joker, smile` still work.
- **Hands have fingers.** `hand(side, "open")` spreads four fingers, `"point"` extends one, `"fist"` and `"grip"` close.

A camera move round a figure is ordinary camera code: many short `cam.move(...)` steps along a circle. See
`output/clips/queen3d-pilot/blender/sh01.py` for a full circle and a push-in.

## Dressing a character

From least work to most. The first three are the plan's `costume` dict and work exactly as they did for the flat cast.

1. **Recolor.** `a.recolor(tunic_tan="#7A1F2B")`. The colour names are the pack's own; `python tools/clip.py cast <Name>`
   lists them.
2. **Hide.** `a.hide("Helmet*", "Belt*")` takes parts off by name pattern.
3. **Wear a wardrobe piece.** `a.wear("straw_hat")`. All 17 pieces of `stagekit/wardrobe.py` work on the 3D cast without
   change: `apron, beret, bonnet, bowler, buttons, cloak, crown, flat_cap, freckles, fur_trim, hood, kerchief, ruff, sash,
   straw_hat, top_hat, tricorn`. See `docs/wardrobe_3d.png`.
4. **Add one flat drawing.** Draw the piece as seen from the front; the figure makes it 3D.

   ```python
   a.add_flat("Scarf", "torso", [(-1.0, 0.92), (1.0, 0.92), (1.0, 1.02), (-1.0, 1.02)], "#C8302C", units="torso")
   a.add_flat("Party_Hat", "head", [(-0.5, 0.75), (0.0, 1.9), (0.5, 0.75)], "#3A7BD5", layer=22, units="head")
   ```

5. **A new wardrobe piece.** Copy a short one in `stagekit/wardrobe.py` (`sash`, `kerchief`), list it in
   `config/cast.json > wardrobe`. It then works for every character, 3D and 2D.

### How a flat drawing becomes 3D

You give an outline in the front view. `on` says what it rides: `"head"`, `"torso"`, `"arm_upper.L"`, `"arm_lower.R"`,
`"leg_upper.L"`, `"leg_lower.R"`. The figure chooses how to make it round from where it is and how big it is. Force the
choice with `as_=` in `add_flat`, or `"as":` in a sheet.

| How | What it does | Chosen by itself when |
|---|---|---|
| `decal` | bends the drawing onto the surface of the head or body, with a little thickness | the default: collars, ties, pockets, aprons, beards, face marks |
| `band` | a ring all the way round the body at the drawing's height | on the body, as wide as the body and under 12 cm tall: belts, hems, waistbands |
| `panel` | the drawing on the front, and the back closed in the same colour | on the body, as wide as the body and taller: vests, coats, overalls |
| `stud` | a small raised button | small, and named button, gem, badge, buckle, medal, brooch, clasp, pearl, rivet |
| `lathe` | spins the outline round the head's axis: a solid hat | on the head, centred, wide, at hat height (`layer` 22 or more) |
| `peak` | the same, but only the front arc and pushed forward | a hat part named peak or visor |
| `hair` | sculpted hair (see below): the drawings are measured for parting, fringe, length and volume | named Hair..., fringe, curl, lock |
| `beard` | a sculpted beard and moustache (see below), sized from the drawing | named beard, mustache, goatee, sideburn |
| `blob` | a rounded lump where it was drawn | named bun, ponytail, braid, topknot, puff, earring |
| `cape` | a cape round the shoulders and down the back, with a lining | on the body, drawn behind it (`layer` under 8.5) and named cape, cloak, mantle, coat, shawl |
| `crown` | a pointed crown with balls and gems, sized from the drawing | named Crown |
| `collar_fur` | a fur collar all round the neck | only when asked for |
| `limb` | a ring round an arm or leg where it was drawn | anything on an arm or leg: cuffs, stripes, socks |

Three rules the builder applies by itself, so you do not have to:

- A hat, helmet or hood that comes down over the eyes gets an opening for the face.
- Hair never comes lower than just above the brows over the face.
- A beard leaves the mouth free; a moustache sits above the lip.

Units: metres in the figure's own space by default (x to its left, z up, it stands at the origin). `units="head"` is
x and z from the centre of the head, in head radii (the top of the head is z = 1, the chin z = -1). `units="torso"` is
u from -1 to 1 across the body and v from 0 at the hip to 1 at the shoulders. `layer` orders things on the same spot:
on the body 9 is the cloth, 10 to 13 are details on it; on the head 17.5 is the face, 18.5 a beard, 20.5 hair, 22 and up hats.

Surface (`"mat"` in a sheet, chosen from the part's name and colour if left out): `cloth`, `skin`, `hair`, `fur`,
`metal`, `leather`, `gem`, `plain`.

### Hair and beards

Hair and beards are sculpted like modelling clay: one thick cap carved into locks with rounded tips, and a beard with
real volume under the face that leaves the mouth free, with the moustache as its own piece. One clean colour, no speckle.

A converted character's style is read from its 2D design. To choose it yourself, give the sheet a `hair` and / or
`beard` entry. A named style is a starting point; any number can be given on top.

```json
"hair":  {"style": "bob", "color": "#6B4428", "part": 0.4},
"beard": {"style": "full", "color": "#5A3A22", "length": 0.5}
```

| Hair style | Looks like |
|---|---|
| `short` | a short crop with a low fringe |
| `side_part` | short, parted to one side, forehead clear |
| `swept_back` | short, combed back |
| `curtains` | chin length, parted in the middle |
| `bob` | a bob with a side parting |
| `fringe_bob` | a bob with a straight fringe |
| `long` / `long_fringe` | past the shoulders, parted / with a fringe |
| `ring` | a bald crown with hair round the sides and back |
| `back_only` | hair behind the head only (under a hat that covers the front) |

Hair numbers (head units, the centre of the head is 0, the top 1): `part` -1..1 where the parting sits; `fringe` how low
the hair comes on the forehead, or `null` for a clear forehead; `side` how low it hangs beside the face; `back` how low
behind; `vol` its size over the head (1.09 close .. 1.22 big); `locks` how many locks round the head. Hair never comes
lower than just above the brows over the face, and lies close under a hat. Buns, braids and ponytails are still drawn
as flat parts named `Hair_Bun`, `Braid...`, `Hair_Ponytail` and become rounded lumps.

**Generated hair.** A sheet can ask for a ready-made hair model from `library/hair/` instead of a sculpted style:

```
"hair": {"model": "female_layered_locks", "color": "#7E4526"}
```

The model replaces the sculpted hair and the character's drawn buns, braids and tails, hides the ears, and a crown is
seated on top of it. `color` is the character's hair colour; `scale` (1.0) makes it bigger or smaller. The models are
listed in `library/hair/index.json`. They are made outside the pipeline from image-to-3D models, with the fringe already
ending above the brow line. The Queen uses `female_layered_locks`.

**Who wears what.** The generated hair and beards of the standard cast are listed in one file, `config/cast3d_generated.json`
(`"Blacksmith": {"hair": "male_messy", "beard": "facial_beard_full"}`). After changing it run
`python tools/chars3d/apply_generated.py` (`--check` to preview, `--clear` to go back to sculpted hair everywhere). Characters
in hats, helmets, caps, hoods and head wraps are not listed: generated hair would poke through the headwear.

**Generated beards and moustaches.** The same library holds beard and moustache models (the `facial` list in
`library/hair/index.json`):

```
"beard": {"model": "facial_beard_short", "color": "#4A3122"}
```

The model replaces the sculpted beard and the character's drawn beard and moustache. It is fitted to this character's
face when the character is built: the moustache is squeezed between the nose and the mouth (`nz` and `mz` in the
sheet's `face`), the beard starts under the mouth, and the sides end at the ears. `model` may be a list (a beard and a
moustache); without `color` the drawn beard's colour is used; `scale` (1.0) sizes it and `drop` (head radii, 0) moves
the mouth line it aims at.

| Beard style | Looks like |
|---|---|
| `stubble` | a thin shadow along the jaw |
| `short` | a trimmed full beard with a moustache |
| `full` | a full beard to below the chin |
| `long` | a long beard (a wizard, a sea captain) |
| `goatee` | chin only |
| `moustache` | a moustache and no beard |

Beard numbers: `length` below the chin (0.1 short .. 0.8 long), `thick` (1 = normal), `full` true = ear to ear,
`moustache` true or false.

## Making a new character

Reuse first, then re-costume, then build. Check `python tools/clip.py cast --era <era>` before making anyone.

### 1. Re-costume in the plan (no new character)

If an existing character with a costume dict plays the part, stop here. The pond clip's rich man is the Adult Man with
`recolor`, `hide` and three wardrobe pieces.

### 2. A new character from an existing one (the quick way)

Add an entry to `config/cast3d_custom.json`. Say who it is like and give only what differs.

```json
"Beekeeper": {
  "like": "Farmer", "label": "Beekeeper", "group": "custom",
  "looks": "a beekeeper: white overalls and shirt, a wide veiled hat, thick gloves",
  "era": ["victorian", "modern"], "stand_in": ["Farmer", "Gardener"],
  "hide": ["Cap*", "Mustache*", "Overall_Button*", "Overall_Pocket*"],
  "colors": {"torso": "#F1EEE4", "sleeve_u": "#F1EEE4", "sleeve_l": "#F1EEE4", "leg_u": "#E9E5D8", "leg_l": "#E9E5D8",
             "hand": "#C9A66B", "shoe": "#5B4632"},
  "recolor": {"fc_fm_overall": "#E9E5D8"},
  "add": [
    {"name": "Bee_Hat", "on": "head", "units": "head", "layer": 22, "color": "#E8D9A8", "mat": "cloth",
     "pts": [[-0.80, 0.62], [-0.72, 1.10], [-0.40, 1.30], [0.40, 1.30], [0.72, 1.10], [0.80, 0.62]]},
    {"name": "Bee_Hat_Brim", "on": "head", "units": "head", "layer": 23, "color": "#E8D9A8", "mat": "cloth",
     "pts": [[-1.55, 0.58], [-1.55, 0.68], [1.55, 0.68], [1.55, 0.58]]}
  ]
}
```

| Key | Meaning |
|---|---|
| `like` | the character to start from (any sheet, converted or custom) |
| `colors` | the body's own colours by role: `skin, torso, sleeve_u, sleeve_l, hand, leg_u, leg_l, shoe` |
| `recolor` | costume parts by the pack's colour name, as in a plan's costume |
| `hide` | part-name patterns to leave off |
| `add` | flat drawings to add (the table above) |
| `wear` | wardrobe pieces that are part of this character: `[{"item": "cloak", "color": "#5A2F2A"}]` |
| `body` | proportions to change, for example `{"R": 0.25}` for a smaller head |
| `face` | `ex, ez` eye position and `es` eye size, `bx, bz` brows, `mz` mouth height and `mw` width (head units), colours `iris, lash, brow, lips`, `blush` true or false |
| `trim` | costume trim: `{"hem": "#FFC83A", "cuffs": "#FFC83A", "front": "#F6E7C2"}` (two bands round a gown's hem, a band at each sleeve end, a pale panel down the bodice) |
| `slim` | `true` keeps the thinner 2D proportions (the default is sturdier arms, hands and feet and a fuller skirt) |
| `label, looks, era, stand_in, props, group` | what the plan and `clip.py cast` show. Give honest era tags. |

`TownGuard` in the same file is the shortest possible example: the Soldier, two colours changed, a cloak, a short beard.

### 3. A character from nothing

Copy the body of the nearest character (`"like"` does this) and replace its costume: `"hide": ["*"]` removes every
converted part, then `add` draws the new clothes, hair and hat as flat front drawings. Hair is one or more outlines
named `Hair...` on the head, in head units, covering the top of the head down to the hairline.

### Look at it

```
blender -b --factory-startup --python tools/chars3d/look3d.py -- --char Beekeeper --out <abs path>/look.png
```

One sheet: the character from the front, three-quarter, side and back, then happy, surprised, angry and grinning. It
takes a few seconds. Fix the sheet and look again until it reads. Add `--wear straw_hat,apron` to try wardrobe on it.

Then prove it acts:

```
blender -b --factory-startup --python tools/chars3d/action_test3d.py -- --char Beekeeper --out <abs dir> --set core
```

`--set all` runs all 118 actions. `--render walk,pick_up` also writes frames of those actions.

### Register it

A 3D character needs no build step and no library file: the sheet is the character. So that `plan-check` accepts it as
a cast base, also add it to `config/cast.json > characters` with `looks`, `era`, `group`, `stand_in` and `props`
(`python tools/cast_registry.py check` verifies the tags).

## What was tested

- The four shot files of the example clip (`the-ring-in-the-pond`) build unedited with the 3D cast, wardrobe included.
- Every action of the library on every character, measured on every frame: held props stay in the palm, feet on the
  ground do not slide, nothing sinks through the floor, hands reach what they must touch. Results:
  `docs/ACTIONS_3D_RESULTS.md`.
- The measurements do not judge how a pose reads. Look at the strips before trusting an action on an unusual costume.

## Known limits

- **Faces are the round-head house style for everyone.** Eyes, brows and mouth are placed from the 2D design, but every
  character has the same kind of nose and eyes, and brown irises unless the sheet gives `face.iris`.
- **Costume trim is on the royals only** (Queen, King, Princess). Other costumes are as converted; add `trim` or flat
  drawings to a sheet to dress one up.
- **Hair and beards are stiff.** They are sculpted shapes: they do not swing, and long hair does not drape over the
  shoulders when the head turns.
- **Hair styles are read from the 2D design by measuring it.** Most come out right; an unusual cut may need a `hair`
  entry in the sheet. Curls are not built: curly hair comes out as smooth locks.
- **Gowns move a little, capes do not.** A gown's skirt is pushed out by the legs, ripples at the hem when the figure walks
  or runs, and keeps its hem on the ground in a sit or crouch. It is not simulated cloth. A cape hangs behind the arms
  and stays rigid.
- **Hats made by spinning are round.** A hat that is not round in plan (a tricorn's corners) is approximated.
- **Clothes drawn on the front have a plain back.** A vest or coat is closed behind in its own colour, without seams
  or details.
- **The special bodies are not rebuilt** (see the list at the top).
