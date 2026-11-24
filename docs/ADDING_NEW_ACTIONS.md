# Adding a new action to the cast

For an agent in the Shorts pipeline. A script asks for something no action covers ("she juggles three apples", "he slips on a banana peel"). Adding it takes one function, one registry entry and one test run. Budget: under an hour.

Linked from the `stagekit` skill and from `CREATING_NEW_CHARACTERS.md`. The catalogue of what exists is `python tools/clip.py actions [word]` and `ACTIONS.md`.

## 0. Check that you need one

1. `python tools/clip.py actions <word>` and look at each entry's `covers` list (synonyms the scripts used).
2. Many requests are an existing action with other arguments: "hammer a nail" is `use_tool(kind="hammer")`, "unlock the door" is `turn_key`, "hold the lantern high" is `hold_up`.
3. A one-off inside one shot can be written straight in the shot file with `pose`, `arm`, `reach`, `hold`. Add a named action only if a second script could use it.

## 1. Write the function

All actions live in `tools/blender/stagekit/actions.py`. Copy a short one of the same family (`knock` for a hand gesture, `gasp` for a reaction, `jump` for a body move, `hand_over` for two people) and change it.

```python
@action("juggle", "hands", lead=0.45, dur=2.4, needs=("props",), loops=True,
        summary="keep two or three small things in the air: hands alternate low in front, eyes follow the top of the arc")
def juggle(A, t, props=None, until=None, height=0.55):
    a = A.a                                   # the Actor; A adds tempo and helpers
    ...
    return t1                                 # the time the action ends
```

The rules every action follows:

| Rule | Why |
|---|---|
| **Three beats: anticipation, main motion, settle.** A small opposite move first (lean back before reaching forward, a squash before a jump), then the action, then a return or a held end pose. | A single pose popping on is the look video 1 had. |
| **`t` is the start. Declare `lead`:** the seconds from the start to the key moment (the grab, the impact, the jump leaving the ground). | The shot code calls `a.do("x", hit=shot.t("word"))` and the key moment lands on the narrator's word. |
| **Every duration goes through `A.d(seconds)`.** | `speed=1.5` then plays the whole action faster. |
| **Face first, eyes lead.** `a.expr(...)` 2 to 4 frames before the body; `A.look(target, t)` a quarter second before a reach. | Reactions read as thought, not as a pose change. |
| **Build only from view-aware calls:** `a.pose`, `a.arm(side, raise, bend, t, blend, plane=)`, `("to", "chin")` spots, `a.reach`, `a.aim`, `a.hold` / `a.release`, `a.wrist`, `a.lean`, `a.tilt_head`, `a.legs`, `a.walk` / `A.go`, `a.move`, `a.hop`, `a.rock`, `a.squash`, `a.shake`, `a.eyes`, `a.hand`. Never key a bone yourself. | These already work in the three views and both facings, keep hands in front of the head, keep ink clean and feet on the ground. |
| **Things in hands go through `a.hold(prop, side, t)`** (`turn=True` if the prop must tip or swing with the hand) and leave through `a.release(prop, t)`. | The palm goes behind the prop and the fingers in front; the release keys where it was left. |
| **Feet:** travel with `A.go(t, to, "walk" | "run" | "sneak")`; change height with `a.legs(...)` (it lowers the body so feet or knees stay on the ground); leave the ground only with `a.move(..., arc=)` / `a.hop`; set `a.floating = True` while off the ground on purpose. | No sliding, no hovering, and the review check knows what is meant. |
| **Unusual bodies:** guard leg work with `if A.has_legs():` and travel with `A.go` (it floats or swims for bodies that do). | Ghost, Mermaid and Genie-style bodies must not crash or fold legs they do not have. |
| **Targets:** take `target=None` as the first keyword; use `A.face(target, t)` to turn toward it. Accept a point, an object, an anchor (`b.head`) or another actor. | One calling style for every action. |
| **Loops:** if it can run for a while, take `until=None`, set `loops=True`, and end at `until`. | Reading, laughing, juggling last as long as the line. |
| **Return the end time.** | Shot code chains: `t = a.do(...)`. |

Helpers on `A`: `A.d(s)`, `A.face(target, t)`, `A.look(target, t)`, `A.rest(t, blend)`, `A.go(t, to, cycle)`, `A.glide(...)`, `A.crouch_for(z, t, blend)` (lean and bend just enough for the hand to get down to a height), `A.pulse(fn, t0, t1, every=)` (call `fn(i, t)` on a beat), `A.has_legs()`, `A.side_of(target)`.

If the action needs a body position that does not exist, add a pose to `POSES` in `stagekit/cast.py` first (one line; give `"views"` overrides if the turned drawing needs different angles) and look at it with `tools/charloop.py <Name> --poses rest,<yourpose>`.

## 2. Test it on every body type

```
py -3 tools/actiontests.py --names AdultMan,Boy,Baby,SeniorMan,Queen --actions juggle
py -3 tools/actiontests.py --names Ghost,Mermaid,Dragon,Fairy,Robot,Alien,Werewolf,Mummy,Genie,Goblin --actions juggle --combos 3q:right,side:left --measure-combos front:right
```

Each run builds a plain test scene (backdrop, ground, the character, and whatever `needs` asks for: a prop, a target post, a destination, a second character), performs the action in all three views and both facings, and writes per combination:

- `<action>__<view>_<face>.strip.png`: every 2nd frame of the whole motion;
- `<action>__<view>_<face>.mp4`: the motion at full speed;
- `<action>__<view>_<face>.json`: measurements of every frame.

If your action needs something the test scene does not provide (several props, a wall, a seat), add a branch for it in `tools/blender/action_test.py` where the other props are made.

It passes when, **on every frame**: no limb part leaves its joint; a held prop stays in the palm; a planted foot does not slide; a hand over the head is drawn in front of it; the acting hand is on the target's side; a reaching palm arrives on the target at the `lead` moment. When one check fails, `python tools/chars/retest.py <out-dir> Name:action:view:face --show foot_slide` re-measures just that combination without pictures and prints the worst frames (each frame's row also carries the feet and the body position). Two walks in a row (`pace`) continue on the foot that is on the ground; start the second on the frame the first returns. Then **look at the strips and one MP4**: measurements do not see a silly pose, a hand through a face, or timing that drags.

## 3. Register it

```
python tools/clip.py actions --rescan
```

rewrites `config/actions.json` from the code. Then write by hand in that file, in your action's entry:

- `"bodies"`: what unusual bodies do instead, only where it differs (`{"no_legs": "floats up and down instead of hopping", "mermaid": "..."}`);
- `"covers"`: the words a script might use for it (`["toss and catch", "keep balls in the air"]`);
- `"sources"`: the script and beat that asked for it.

Add a row to `ACTIONS.md` (the test results table is regenerated by `py -3 tools/actiontests.py --report`).

The `director` agent reads `config/actions.json` when it writes a shot plan (a view's `action` should name actions from it); the `shot-builder` agent calls them with `actor.do(...)`. Both agent files point here. `python tools/clip.py actions` must list your action before a plan may use it.

## 4. Worked examples: the two actions added by following this page

Neither is in any gold script.

### `juggle`

- Step 0: `clip.py actions juggle`, `toss`, `catch`: nothing. `throw` releases a prop for good, so it is not a cover.
- Step 1: copied `tap` (a hand loop). Anticipation: a dip of the knees and a glance up. Main: the hands alternate between a low catch and a toss position in front of the belt while each prop flies an arc between them; the props are keyed, not held (they are in the air most of the time), and the eyes follow the top of the arc. Settle: catch all, hands together, a small bow of the head. `lead=0.45` (first toss), `loops=True`, `needs=("props",)`.
- Step 2: the test scene got a branch that makes three small balls. Passes on the five standard bodies and the ten unusual ones (the Baby's arcs are lower because `height` scales with the figure).
- Step 3: `bodies`: `{"no_legs": "no knee dip; the body bobs"}`; `covers`: `["toss and catch", "keep balls in the air", "circus trick"]`.

### `slip_banana`

- Step 0: `slip` exists (a foot slides on ice or moss and the figure goes down) but it has no cause on screen and no comic air time; the script wants the peel to shoot away and the fall to land on the word.
- Step 1: copied `slip` and `fall`. Anticipation: a carefree step (`step_forward`) with the eyes anywhere but down. Main: the stepping foot shoots forward (`a.legs(..., side="R", ground=False)`), the peel is kicked off along the ground (`core.move`), arms windmill for four frames, the figure hangs level in the air (`a.move(..., arc=)` with `a.rock(-88)`), then lands flat with a squash. Settle: a dazed head lift. `lead=0.75` (the landing), `needs=("prop",)` (the peel).
- Step 2: test scene branch: a flat yellow peel on the ground one step ahead. Passes on all bodies; for bodies without legs the first beat is a glide over the peel and a tumble.
- Step 3: `bodies`: `{"no_legs": "glides over the peel, tumbles in the air, lands flat", "mermaid": "same as no_legs"}`; `covers`: `["slip on a banana peel", "pratfall", "feet fly out"]`.

Strips and MP4s for both are in `proof/actions/_new_actions/`.
