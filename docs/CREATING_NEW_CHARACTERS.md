# Creating a new character for the 2D pack (beta 0.4)

For an agent in the Shorts pipeline. One new character takes one session: about 15 seconds per build-and-look round, usually 4 to 8 rounds. You never rebuild or re-verify the rest of the cast.

Paths below are relative to the pack folder `characters_beta_0.4/` unless they start with `tools/`, `config/` or `library/` (the pipeline root).

## 1. Do you need a new character at all?

The director decides in this order and writes the choice into the shot plan's `cast` entry.

1. **Reuse.** `python tools/clip.py cast --era <world era>` lists who fits the period. If a listed character already reads as the role (a Soldier is a guard, a Nobleman is a rich merchant), use it. Each entry's `stand_in` names the characters it can replace or be swapped with.
2. **Re-costume.** If the body and age are right but the clothes are not, dress an existing character in the plan: `costume: {"recolor": {...}, "hide": [...], "wear": [{"item": "straw_hat"}, {"item": "apron"}]}`. The wardrobe pieces and their periods are in `config/cast.json > wardrobe`. A gardener is the Boy with a straw hat and an apron; a miller is the Adult Man with an apron and a flat cap.
3. **Build new** only when the silhouette itself is missing: a body type the pack lacks (very fat, very old, a creature), a signature shape no wardrobe piece gives (an astronaut's helmet, a diver's suit, a flapper's bob and fringe dress), or a role that will come back in later videos. A character seen for two seconds in a wide shot never justifies a build.

Write one line in the plan saying why (`"why_new": "no pack character has a diving helmet; the helmet is the story"`).

## 2. From a line of text to a design

The usual input is the director's line: *"a 1920s lighthouse keeper, old, bearded, yellow oilskin coat"*. There is no image generator. You design inside the pack's rules, mock the front view, compare it with the cast, and only then draw the other two views. If a reference image is supplied, crop it to `character_refs/crops_v4/<Name>.png`; the loop then shows it beside your render.

### Design rules (the pack's style, not the softer style of a reference sheet)

- **Proportions.** Start from a template: `T_A` (adult man: 1.56 m to the head top, head radius 0.27 m) or `T_B` (adult woman: 1.52 m, same head). Children: copy the Boy's numbers (head 0.24, legs shorter). The head is about a third of the height. Do not make realistic proportions: a small head reads as a different show.
- **Height grid.** Adults 1.50 to 1.60 m to the top of the head (hats add to that), old people 3 to 5 cm shorter, children 1.15 to 1.30 m. Check with `--next-to`.
- **Face.** The pack face system is fixed: dot eyes, thin brows, a small smile, ears on the template. You choose skin, hair, beard, glasses and brow colour; you do not redraw eyes or mouths (expressions and lip sync depend on them).
- **Ink.** One weight, set by the build (`INK_W`). Pass `outline=0.016` (the default look) on parts; `outline=0` for flat marks drawn in a colour (stripes, seams, pleats); `outline=0.008` only for pupils-sized detail. Never thicker.
- **Colour.** Flat colours only. At most 6 costume colours plus skin, hair and the ink. Take them from the reference or pick muted, slightly warm tones like the existing cast (look at `PAL` in the build script). One colour must dominate; one accent may be bright.
- **Silhouette first.** At Shorts size a character is 150 to 400 pixels tall. It must be recognisable as a black shape: one strong hat or hair shape, one costume idea (apron, long coat, cape, big collar), nothing thinner than 1.5 cm, no texture.
- **The three views agree.** Same hat, hair, colours and layers in front, three-quarter and side. In 3q and side the character faces +X.
- **Signature props are separate props**, never painted into the hand: a crook, a lantern, a bell is a library asset the hand holds with `hold()` (section 7).
- **Period honesty.** Decide the eras now (section 6): they depend on the design (a zip, a wristwatch or trainers make a character modern only).

### What the body gives you for free

You write a spec and a costume function. The build draws head, face, ears, torso, two-part arms and legs, hands (mitten, open, pinch, fist, point, grip), shoes, the rig, the walk, run and sneak cycles, expressions and visemes. All 100+ actions in `stagekit.actions` then work, because they only use the standard bones.

## 3. The costume file

Create `scripts/costumes_v4/<prefix>_<yourfile>.py` (a 2 or 3 letter prefix that no other file uses; every helper function and every colour key you add starts with it). The build loads every file in that folder automatically. Copy `scripts/costumes_v4/ex_example.py` (the worked example: a 1920s flapper made from one line of text) and change it.

```python
PAL_ADD = {"lk_coat": "#E0B63A", "lk_coat_dark": "#B88F22", "lk_beard": "#E8E4DC", "lk_hat": "#3B4A5E", "lk_boot": "#2E2A2A"}

NEW = [
    T_A(name="LighthouseKeeper", label="Lighthouse Keeper", group="storybook",
        torso=dict(color="lk_coat", tw=0.17, bw=0.21, bz=0.38),      # tw / bw = half width at shoulders / hem, bz = hem height (m)
        pants="lk_hat", robe=True,                                    # robe=True: a long coat / skirt (legs under it, hem opens, sits)
        boot=dict(BOOT_A, color="lk_boot"), ear=False,
        walk=dict(N=28, S=0.18, lift=0.06, bounce=0.02, arm=0.2, elbow=0.25, lean=-0.045, arm_s=0.3, elbow_s=0.4)),   # an old man's shuffle
]

def lk_souwester():        # helper: (front, three-quarter, side) outlines in HEAD UNITS
    ...

def costume_lighthousekeeper(ctx, ch):        # called once per view; ctx.view is "Front", "ThreeQuarter" or "Side"
    hpart(ctx, "Hat", front_pts, "lk_hat", LY["hat"], q=q_pts, s=side_pts)
    hpart(ctx, "Beard", ..., "lk_beard", LY["beard"], s=...)
    buttons(ctx, [(0, F(ch, f)) for f in (0.8, 0.6, 0.4)], color="lk_coat_dark")
    belt(ctx, ch, 0.42, 0.52, color="lk_boot")

COSTUMES_ADD = {"LighthouseKeeper": costume_lighthousekeeper}
```

Rules of the file: nothing at top level may call a build helper (they are defined later in the build script); only `def`, `NEW`, `PAL_ADD`, `COSTUMES_ADD`, `SPEC_PATCH` and plain data. `PAL_ADD` may not redefine an existing colour key.

### Spec keys you will use

| Key | Meaning |
|---|---|
| `name`, `label`, `group` | CamelCase id, display name, lineup group: `village`, `storybook`, `trades`, `professions`, `creatures` or `custom` |
| `R`, `head_z`, `neck_z`, `hip_z`, `ankle_z` | head radius; heights of head centre, collar, hips, ankles (m) |
| `arm_len`, `sh_drop`, `hand_r`, `leg_dx`, `arm_angle` | arm length, shoulder below collar, hand radius, half distance between legs, how far the arms hang out (degrees, front view) |
| `torso=dict(tw, tz, bw, bz, color, corner)` | body: half width at top / bottom, top / bottom height, colour |
| `limb=dict(sh, el, wr, hip, kn, an)` | radii of shoulder, elbow, wrist, hip, knee, ankle: thick or thin limbs |
| `sleeve`, `forearm`, `pants` | colour keys (`"skin"` for bare) |
| `sleeve_len` | `None` full sleeve; `0.0` to `0.5` short or rolled sleeve over a bare arm (fraction of the arm) |
| `shorts_len`, `leg_color` | shorts / short skirt: bare or stockinged legs below a hem |
| `boot=dict(hw, top, toe, toe_h, color[, style="sandal"])` or `None` | shoes; `None` = bare feet |
| `skin`, `ear`, `face=dict(...)` | skin colour key; ears; face tweaks (`ez` eye height, `mz` mouth height, `eye` size, `brow_color`) |
| `robe=True` | long coat, robe, dress: legs are rigged underneath, the hem opens on the step and makes a lap when sitting |
| `walk=dict(...)` | the walk: `N` frames per cycle, `S` half stride (m), `lift`, `bounce`, arm swing. `run=` and `sneak=` dicts patch those cycles |
| `legs=False` | a body without legs (ghost, mermaid, genie): the leg bones stay, no leg art is drawn; you draw a tail or wisp on the `"body"` bone |
| `no_torso=True` | you draw the torso yourself as a part named `"Torso"` (sloped shoulders, a gown) |
| `head_shape` | `"skull"`, `"fur"` or leave out for the round head |

### Drawing helpers (all defined in `scripts/build_character_library_v4.py`; read their docstrings)

- `hpart(ctx, name, front_pts, color, layer, outline=0.02, kind="shape", q="auto", s="auto")`: a part on the **head**. Points in **head units** (origin = head centre, 1 = head radius; front view +x = the character's left). `q` / `s`: the three-quarter and side outlines; `"auto"` maps the front art (fine for hats and round things, wrong for hair and beards: give them), `None` hides the part in that view. `kind="rigid"` keeps a small detail's shape and only moves it.
- `tpart(ctx, name, front_pts, color, layer, ...)`: a part on the **torso**, points in **metres** (x = 0 body centre, z up from the ground). `vpart` when you computed the points for the current view yourself.
- `make_part(ctx, name, pts, color, layer, bone, outline=..., pivot=...)`: a part on any bone, rig coordinates in metres: `"arm_upper.R"`, `"arm_lower.L"`, `"hand.R"`, `"leg_upper.L"`, `"leg_lower.R"`, `"foot.L"`, `"head"`, `"torso"`, `"body"`. Get joint positions from `joints(ch, ctx.view)` (`J["sh.R"]`, `J["wr.L"]`, `J["hip.L"]`, `J["an.R"]`). In 3q and side `.R` is the near arm and leg.
- `skin_part(...)`: a wide sleeve or trouser leg across a joint (it becomes two rigid parts, upper and `_Lower`).
- Shapes: `circle`, `ellipse`, `rect`, `rounded(pts, r)`, `chaikin(pts, n)`, `stadium(A, B, w)`, `stroke(curve, width)`, `stroke_path`, `polyline`, `arc_pts`, `star`, `mirror_x`.
- Hair and faces: `cap_hair(...)` returns front and 3q, `side_cap(...)` the profile, `back_hair`, `side_tufts`, `braid`, `mustache_pts`, `handlebar_pts`, `crown_parts`.
- Clothes: `belt`, `buttons`, `collar_flaps`, `v_neck`, `lapels`, `vline`, `band`, `trousers_top`, `F(ch, f)` (a height at fraction f of the torso), `fx(ctx, z)` (the torso's front edge in the side view).
- Alive parts: `wiggle(part, degrees, period)` makes stagekit swing a part about its pivot while the character is on stage (wings, a tail, antennae, a flame).
- Robes: `ctx.robe_parts.append(part)` for every extra skirt-like part (a cape, an apron hem) so it opens on the step and sits with the body. Details drawn ON the skirt (pleat lines, trim spots, a pocket) need nothing: every other part on the torso bone that hangs below the hips gets the same `Sit` key from the build, so it rises with the cloth when the figure sits.
- Layers: `LY["cape"]` 0 (behind everything), `hair_back` 1, far leg 2.5, far arm 4.6, near leg 6.5, `torso` 9, `det` 10, `det2` 11, `collar` 12, near upper arm 14.6, `head` 16.5, `face` 17.5, `beard` 18.5, `mustache` 19.5, `hair_front` 20.5, `ear` 21.2, `hat` 22, `hat_det` 23. Higher is nearer the camera. Forearms and hands are placed above everything on the chest automatically, and come in front of the head and the hat when a hand is raised to them.

## 4. The loop: mock, compare, finish

```
py -3 tools/charloop.py LighthouseKeeper --front-only --next-to SeniorMan      # 1. the front mock beside a cast member
py -3 tools/charloop.py LighthouseKeeper                                       # 2. three views + wave, proud, sit, carry
```

`tools/charloop.py` builds only your character (`build_character_library_v4.py -- --names <Name> --out <file>`, 3 to 4 seconds), renders it and writes `out/chars/<Name>/review.png`. **Look at the picture every round.** Fix, run again.

Round 1, front only: is it the described person at a glance? Right height next to the neighbour? Face clear (no hair or hat over the eyes or the mouth)? Then draw the 3q and side outlines of hair, hat, beard and anything `"auto"` got wrong, and run the full loop.

Build messages to act on:
- `POLY_ISSUES ... crossing(s)`: a hair, beard or moustache outline crosses itself and the fill breaks. Reorder or move points.
- `LIMB_NOSPLIT`: a `skin_part` outline does not cross the joint line twice. Make it span the joint.
- `PAL_ADD ... redefines`, `already exists`: rename your colour key or character.

## 5. Quality gate (all must hold before the character goes into a video)

1. Build with no error and no `POLY_ISSUES` for the character.
2. `review.png` read by eye:
   - front, 3q and side show the same person: same hat, hair, beard, colours, belt height;
   - the face is clear in every view; the profile has its nose and one eye;
   - **wave, proud, sit, carry**: no costume part is left behind when an arm or leg moves (a cuff or glove must ride `arm_lower` or `hand`, not the torso), nothing important is covered, hands are in front of the body they touch;
   - robe characters: the hem reaches the shoes standing and makes a lap sitting;
   - ink: one weight everywhere, nothing spiky, no doubled lines.
3. `blender -b <Name>.blend -P scripts/verify_character_library_v4.py -- --names <Name>` passes (rig, drivers, expressions, visemes, hand shapes, walk loop, joints, raised-hand depth, ink width).
4. `py -3 tools/actiontests.py --names <Name> --set core` passes: walk, point, pick up, hold, hand over, gasp, talk and sit are measured on every frame (joints closed, prop in the palm, no foot slide, hand on the target's side) and strips are written for you to look at.
5. The character stands in the lineup at the right height: `blender -b character-library_v4.blend -P scripts/render_lineup_v4.py -- --out <abs.png> --names <Name>,<two neighbours>`.

## 6. Put it in the library and register it

```
blender -b --factory-startup -P scripts/merge_character_library_v4.py -- --lib <pack>/character-library_v4.blend --add <abs>/<Name>.blend
python tools/clip.py cast --rescan          # reads parts and colours of new characters into config/cast.json
```

Then write by hand in `config/cast.json > characters > <Name>`:

| Field | What to write |
|---|---|
| `looks` | one line a director can cast from: age, build, hair, costume, and the roles it can play |
| `era` | only from `ancient`, `medieval`, `renaissance`, `age_of_sail`, `victorian`, `modern`, `east_asia_feudal`, `fantasy`. Several are fine. Be honest: an astronaut is `modern` only; a town crier is not `ancient` |
| `group` | the lineup group |
| `stand_in` | existing characters this one can replace or be swapped with (`["Soldier"]` for a Knight) |
| `adapt` | how to push it into other roles with recolor / hide / wear |
| `props` | ids of its signature props in `library/assets` |
| `body` | only for unusual bodies, see below |

`height_m`, `robe`, `colors`, `headwear_parts` and `parts` come from `--rescan`. Check with `python tools/clip.py cast <Name>` and `python tools/clip.py cast --era <era>`.

### Unusual bodies

The rig keeps every standard bone, so every `stagekit.cast` call still works. `body` tells stagekit what to do instead of what the body cannot do:

| `body` key | Effect |
|---|---|
| `"legs": false` | `legs()`, sit, kneel and crouch poses do not fold legs; sitting actions lower the body a little instead |
| `"gait": "float"` or `"swim"` | walk, run and sneak glide with a bob (ghost, genie) or a swim (mermaid) instead of the leg cycle |
| `"hover": 0.04` | the figure bobs this many metres while idle |
| `"notes": "..."` | what else is substituted; shown by `clip.py cast <Name>` |

## 7. Signature props

Each prop is a small 3D asset (chunky, real surfaces, real size, resting on z = 0, grip point at the origin where a hand should hold it). Write `library/assets/src/prop_<id>.py` after `examples/assets/set_stone_well.py`:

```python
from stagekit import build
ASSET = dict(id="prop_shepherd_crook", name="Shepherd's crook", kind="prop", tags=["crook", "staff", "shepherd", "stick"],
             era=["ancient", "medieval", "renaissance", "fantasy"], source="built", license="project",
             notes="1.6 m tall; hold it 1.0 m up: gardener.hold(crook, 'R', t, offset=(0, 0, -1.0)); turn=True to swing it")

def build_asset():
    ...
    return build.group("prop_shepherd_crook", parts)
```

```
python tools/clip.py asset library/assets/src/prop_shepherd_crook.py --no-save     # preview while you iterate
python tools/clip.py asset library/assets/src/prop_shepherd_crook.py               # file it: library/assets/index.json
python tools/clip.py assets find crook
```

In a shot: `crook = assets.use("prop_shepherd_crook", at=...)`, then `shepherd.hold(crook, "R", t)`: the palm goes behind it and the fingers in front, so it is gripped.

## 8. Where this plugs into the pipeline

- `director` agent: decides reuse / re-costume / new (section 1) and writes `why_new`; a new character is a task for the `character-maker` skill before any shot is built.
- `.claude/skills/character-maker/SKILL.md`: the short form of this guide.
- `stagekit` skill: poses, actions (`a.do(...)`), `hold`, wardrobe.
- `asset-library` skill: props (section 7).
- If the new character needs an action no script has used before, add it with `ADDING_NEW_ACTIONS.md`.

## 9. Worked example: the Flapper

Input line: *"a 1920s flapper: young woman, black bob with a headband, short fringed green dress, long pearl necklace"*.

1. Section 1: no pack woman has a bob or a short fringed dress and the era (1920s) has no close cast member; the silhouette is the point. Build new.
2. Design: `T_B` body, sleeveless (`sleeve_len=0.0`), dress to mid-thigh (`bz=0.50`), stockinged legs (`shorts_len=0.02, leg_color=...`), low black shoes. Three costume colours (dress green, darker fringe, gold band) plus pearl, hair, stocking. Silhouette idea: helmet-like bob + the toothed hem.
3. Round 1 (`--front-only --next-to Barista`): height right. **The hair covered the whole face**: the build printed `POLY_ISSUES Flapper_Front_Hair: 2 crossing(s)`; my inner hairline started on the outer arc. Moved the inner line in (x 0.80 at the jaw) and the arc ends to -26 / 206 degrees.
4. Round 2: face clear, fringe above the brows. Drew the side bob (`side_cap` with a chin-length hem) and moved the headband jewel for the profile.
5. Round 3, full loop: wave, proud, sit, carry clean; the dress keeps its fringe when she sits.
6. Verify and the core action tests pass; merged; registered as `era: ["modern"]` with the note that the 1920s sit inside the pipeline's `modern` only loosely (`adapt`: for a 1950s-or-later story swap the headband for a `kerchief` and recolor the dress).

The file is `scripts/costumes_v4/ex_example.py`; the review sheet, strips and lineup crop are in `proof/worked_example_flapper/`.
