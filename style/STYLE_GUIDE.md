# Production style guide

How every Short on this channel is staged, shot and captioned. Written for the agents that make the film and for you when you review one. Numbers that scripts enforce live in [`style.json`](style.json). Where a rule comes from the reference Shorts, the evidence is in [`docs/REFERENCE_BREAKDOWN.md`](../docs/REFERENCE_BREAKDOWN.md) (two of them shot by shot; two more were measured since, and their numbers are used here). Commands are written with `PY` for `py -3` on Windows, `python3` elsewhere.

**The look:** simple round cartoon characters (real 3D figures with drawn faces, on a Mixamo skeleton) in a rich, complete 3D world with real materials and motivated light. Simple people, rich world, a camera that moves with purpose.

**One test decides every choice:** at this moment, what does the viewer need to see to understand or feel what the narrator is saying? Show that, large and clear, a moment before the words. If you cannot say what a view gives the viewer that the one before it did not, it should not be there.

## The few things that never change

1. **1080x1920, 24 fps, 70 seconds at most.** Lengths come from the voice take, never from guesses.
2. **One world.** A story has one period and place (`world.era`). Every character, costume piece, surface and prop belongs to it. The plan check enforces the tags; your eyes enforce the rest.
3. **Fair play.** Never show what the narrator has not revealed. Anything the ending depends on is shown clearly before it is used (`setups`).
4. **The Shorts UI and the captions own part of the frame.** Faces and key action stay out of the bottom 24%, the top 8%, the left 5% and the right 14%, and above the caption line at 70% of the height. Review stills draw both.
5. **One light rig per place and time of day.** Light changes only when the story's time changes.
6. **Safety.** No real people, logos or brands. Never show a child being hurt. No copyable weapon or drug detail.
7. **The user decides three things from pictures:** the characters (Gate A), the sets (Gate B), the camera (Gate C). The tools refuse to go on without them, and checks that measure a real fault block instead of warning.

Everything below is craft: tools with reasons. Break a guideline when the film is better for it and you can say why.

## The bar

Measured on four reference Shorts, and the bar every film is held to:

- **22-33 framings per minute.** The camera moves for 60-80% of the screen time, and the frames that look static still drift 2-5%.
- **More than half of the transitions are camera events**: a whip (0.3-0.5 s), a trip through an opening or a screen, a crane, a push into the next thing. Plain cuts are for jumps in place or time.
- **Wides are low or eye level for people, high or top-down for geography.** Subjects sit in the upper middle of the tall frame; captions are one centred line at 70% down.
- **Sets are complete.** A wide shows at least 14 kinds of prop and 60 objects in four depth layers, at least 3 visible practical lights indoors, a rim light on the characters, one atmosphere element, ground or floor detail, and at least 3 readable in-world details. Enclosed places survive a reverse angle.
- **Where the references are weak and we must be better:** bare interiors, three-wall stages, characters that slide instead of stepping, flat lighting, repeated props, inconsistent set colour between shots.

## Shots and views

Two words, used strictly:

- A **shot** is one staged take: one set, one time of day, action that runs continuously. It is a file (`blender/sh03.py`) and a render unit. Most Shorts need two to five.
- A **view** is one camera framing inside a shot. The viewer experiences views. The references hold 22-33 framings a minute (`style.json` > `views` > `reference_framings_per_minute`); the plan validator's 9-24 per Short is a sanity range and still warns above 24.

The first version of this pipeline cut 32 times in a minute; the second held five frames for nine seconds each. Both missed the same thing: the references change the picture every two or three seconds, mostly by the camera *travelling* inside one place: a whip from the bullet hole to the man watching, a push from the wide to the banknote, a flight with the rolling bomb. The viewer is led, not thrown. A new picture on every new noun or clause; a hard cut only for a jump in place or time, or for going in or out on the same subject.

### When the viewer needs a new view

| The narration... | Give them |
|---|---|
| names a new thing that matters (a ring, a gate, a net) | that thing as the subject of the frame, on or just before the word, big |
| describes an action too small to read at this size (a ring slipping through mesh) | an insert of it |
| gives a character's reaction or a quoted line | that face, close enough to read, mouth moving on the quote |
| sets the scene or shows a result that changes the whole place (the pond empties) | the wide, ideally the same wide as before so the change is obvious |
| jumps in time or place | a transition event (whip, dissolve, dip) and a new light or set |
| launches something (thrown, dropped, rolled) | the camera travelling with it |

### When to stay

Stay on the current view while the action inside it is still developing: a walk arriving, a pose changing, a second character reacting, a prop being used. Staying never means a locked frame: the camera pushes, drifts or tracks (a held view gets a 2-5% drift automatically; `still=True` needs a reason). A view may run long only if something new happens in it every second or two; write that in the plan's `inside`.

### The first two seconds

Open on the character and the event of the first clause, already in motion on frame one: the ring leaving her finger, not a garden. No fade-in. The place comes second, when the story needs geography.

## The camera

Every view is designed: a **move** and its reason, an **angle** and framing, a **side** of the line of action, and how it is **entered**. The library is `stagekit/camera.py`; `tools/tests/camera/test_moves.py` is a cookbook that runs every move. A move is **chosen for what it shows**, never for variety.

| Move | When | Typical amount and duration |
|---|---|---|
| slow push (`dolly`) | a realisation, a quiet beat, a hero prop being explained | 1.5-3 s, +5-40% subject size, ease out |
| fast push | a shock, a reveal | 0.5-1.5 s, x1.35-1.7 |
| lateral track (`truck`, `track_with`) | going beside a walker; revealing behind a foreground occluder | 1.5-3 s, a third to half of the frame width |
| arc or `orbit` | showing a person or object from a new side without a cut | about 3 s, 25-30 degrees |
| `crane` up or down | from a person to the geography, or into a scene | 2.5-3 s, 35-75 degrees of pitch |
| `follow` / chase | a thrown, falling, rolling or running thing | 2-3 s |
| `whip` | carrying the eye to the next subject inside a place | 0.3-0.5 s |
| `through` | an opening, a window, a screen: a transition into the next view | about 0.5 s for a pull out through an object; 1-2 s through a doorway |
| `rack_focus` | moving attention between two faces or objects | 0.6-1.2 s, over a slow push |
| `reveal` | coming out from behind an occluder onto the subject | 1.5-2.5 s |
| `handheld`, `shake`, `dolly_zoom` | nerves, impact, a sinking realisation | rare, short |
| static with drift | the last image; a moment that must be still | 2-5 s, only with a stated reason when held over 1.2 s |

Chained moves use `blend=0.3` so there is no velocity jump. The path is measured (`stagekit/campath.py`): speed, acceleration, turning, jerk, passing through walls, the subject leaving the frame, a face hidden or under a caption, and how much of the shot is a still camera. Limits are in `style.json` > `camera`; a whip is exempt from the speed limits but must last 0.25-0.5 s. Going over a limit warns, and by a factor of two blocks.

**Angles.** Low or eye level for people (waist to chest height, level or slightly up; `high=-6` makes someone proud or threatening); high or top-down for geography and for hands and objects on a table. The figures are solid 3D, so any angle holds: a back view, a walk away, a steep look up at a hero are all available. Past 60 degrees with characters in frame the check warns (heads foreshorten).

**The line of action.** Draw a line between the two parties of a scene and keep the camera on one side (`cam.line(a, b)`; the helpers `ots`, `two_shot`, `reverse`, `profile` hold to it). Then she is always on the right looking left, they are always on the left looking right. Cross it only on purpose (`cross_line=True`) and show the crossing; the path check warns `line_crossed` on a cut that does it by accident. A single figure or object has no line: the camera may go all the way round.

**Transitions.** The plan gives every shot after the first a `transition_in`: `whip` for energy toward the next place, `dissolve` for later, `dip` for a break, `flash`, `wipe`, `match` (a graphic match). A view reached by a whip or a trip through an opening is the end of the previous view's own move. Compose the last frame of a shot and the first of the next for the join.

**Framing for 9:16.**

- The subject sits in the upper middle: centre about 40% from the top (`place=0.40`), faces above the caption line. Wide views may sit lower; the faces are too small for the captions to hurt.
- Sizes (`size=`): `insert` an object or a hand action; `close` a face; `medium` waist up, hands in frame (the default for acting); `full` the whole figure with room to move; `wide` the place.
- Change size clearly between neighbouring views. Wide to medium to insert reads; medium to slightly-different-medium looks like a mistake.
- A foreground occluder in a wide (a column edge, a plant, a shoulder) makes it read as a place rather than a stage.
- Check the wide for overlaps. Staggered figures can hide each other from one angle and separate from another; `side=` is the tool.

## The world

Decide once, in the plan's `world`: the period (`era`), the place in one sentence, three or four rules for what belongs and what never appears, and a palette where each main character owns one colour.

- **Cast for the period, then dress the role.** `PY tools/clip.py cast --era <era>` lists who exists and what each body may wear. A character wears a fit-checked outfit and add-ons from the wardrobe (`library/wardrobe/README.md`); a role nobody can play is a `casting` MISSING, and the user is told exactly what is needed. A constable is never a soldier, a hoodie is never a tunic.
- **Each character must read at a glance** by silhouette, colour and one prop. Write it down (`reads_as`).
- **Five or six kinds of object carry a period.** Repeat them: for a medieval castle, dressed stone, oak planks with iron bands, banners, barrels, torches, a plank door in a round arch. Put period where the camera will be.
- **Text in the world is welcome when it is of the world** (a painted sign, a stencilled crate). Never modern type, never a brand.

## Sets

A set is a complete place that a camera can go round, built around what happens in it. Never the minimum the script needs.

1. **Start from the marks.** Before any dressing, write the table of where each person stands and where each story object is (`MARK` in the set file). Everything else is arranged around them, never on them, and the floor in front of every door stays clear.
2. **Enclose it.** Real floor, four walls with real openings, a ceiling (a vault, beams, tiles), or a ground, a horizon and a sky for an exterior. Every door and window has something behind it: `arch.vista` (hills, a street, a courtyard, a lit corridor). An opening onto a void is a blocking fault.
3. **Four depth layers.** Foreground occluder (a column edge, a hanging banner, a plant), midground action, background (walls, furniture, a skyline), and something beyond (sky, a vista, a room through a door).
4. **Make the mechanism visible.** If the story turns on how something works, build it so a viewer can see it work.
5. **Dress to the standard:** at least 14 kinds of prop and 60 objects visible in the wide; at least 3 visible practical lights indoors; a rim light on the characters; one atmosphere element (dust in a window shaft, haze, smoke, steam); ground or floor detail (rugs, straw, leaves, paper); at least 3 readable details (signs, banners with a crest, notices, labels). Nothing floats or is sunk more than 2 cm, nothing intersects, no mesh lacks a material.
6. **Survive a reverse angle.** The wall nearest the camera is hidden per view (`arch.cutaway` / `track_cutaway`), so one enclosed room serves cameras on any side. The plan says which angles a set must survive (`must_survive`).
7. **Real surfaces.** By name (`mat.surface("castle_stone")`); `PY tools/clip.py materials fetch <clip>` gets the scanned ambientCG textures.
8. **Consistent colour.** The same set has the same palette and light rig every time it returns, in every shot of its time of day.

Start from the worked sets in `examples/sets/` (a throne room and an open-plan office) and the themes in `stagekit/dress.py`. `PY tools/clip.py setpreview` renders six angles per set and light mood and measures it; the user approves the sheets at Gate B.

Scale: adults are about 1.6-1.8 m. Doors about 2.0-2.1 m (arched up to 4-5 m in a hall), house ceilings 2.6-3 m, halls 6-10 m wide and 6-8 m high, a pond rim 0.2 m.

## Light

- **A motivated key.** A window (`lights.window_key`, real shadows of the frame), a lamp, a fire, a low sun: you can point to it. One rig per set and time of day, reused by every shot of that set and time.
- **Separation.** A rim light on the characters (`lights.rim_light`) or a value step behind them, so the figure lifts off the background. Check every still: can you find the subject in under a second on a phone-sized image?
- **Practicals and atmosphere.** Visible light sources with a real light and a glowing part; dust or haze in the beams. Flat world light alone is the reference films' weak spot.
- **Time of day is story.** Noon for the challenge, sunset for "he fished all day", a fresh morning for the simple answer. Changing the mood between shots tells time without a word.
- **The cast takes the colour of the hour.** `lights.rig` sets how the figures take the scene light. Do not relight characters by hand.
- **Darkness is deep colour, not black.** At night keep ambient up and add a visible warm source. `mostly_black` and `blown_out` block.

## Characters and performance

The characters are real 3D figures (Aj, `config/cast.json`) on an unmodified Mixamo skeleton: a drawn mouth, real fingers, any angle; back views and walking away are fine. Walking, running, sitting, kneeling, lying, falling and jumping are Mixamo clips played on the figure (`actor.walk`, `actor.play_clip`, `actor.do("sit_down")`); gestures, reactions and hand work are named actions (`PY tools/clip.py actions`), keyed to words.

- **Anticipation, action, hold.** Wind up for 4-8 frames, act in 2-4, then hold the result for 10 frames or more.
- **Face first, eyes lead.** Change the expression 2-4 frames before the body reacts; a character looks at a thing a quarter of a second before reaching for it. Where the eyes point is where the viewer looks.
- **One pose, one idea, readable as a silhouette:** chest out and hands on hips is pride; both hands to the face is shock; a finger up is a rule; a sag with the head down is defeat. `docs/poses.png` shows the named poses.
- **Reactions in turn.** In a group, stagger reactions by 0.15-0.5 s, near to far. Never all on one frame.
- **Quoted lines get a mouth.** `actor.speak("first words", "last words")`, and put the camera on that face.
- **Hands land exactly.** `actor.reach(side, thing, t)` so the hand is on the bar, the ring, the branch; `hold` so the prop travels with the hand (the grip closes the fingers on a handle or small thing); `release` so it leaves cleanly. Key the reach again after the prop moves.
- **Weight and contact.** Feet on the floor, a seat that takes weight, a prop set down on a surface; mark every contact with a small effect (`fx.splash`, `fx.puff`, `fx.drips`, a `cam.shake`).
- **Nothing freezes.** `actor.idle()` on everyone: blinks and breath. Give background characters one reaction per view.
- **Costume fits.** No skin through cloth, no collar or sleeve clipping, hair on the head. A garment that fails is a wardrobe problem, never hidden by the camera.
- **Walking costs screen time.** Show the first steps or the arrival unless the walk is the camera's subject (a track beside it, a follow with room in front).

## Props and effects

- **A prop that matters is big in frame at least once** and is introduced in a hand or by the camera arriving on it.
- **Small precious things are drawn large and they glint:** a ring is 14 cm across here, with `fx.sparkle` when it should be found by the eye.
- **Leave the evidence in the set.** The broken branch stays broken, the pond stays empty, the wet man stays wet in later views.

## Captions

Built by `tools/captions.py` from the same word times that set the shot lengths; drawn by Remotion.

- One caption at a time, **one to three words** (most are one), small words joined to the word they lead into: "her gold", "into the deep", "is yours,".
- **Centred on the frame, on one fixed line at 70.5% of the height.** Never wrapped: a long caption is scaled down a little instead.
- Bold white Montserrat with a thick dark outline and a soft shadow. Sentence case, the script's punctuation.
- Each caption appears 0.08 s before its first word and stays until the next one; after a sentence followed by a real pause the line clears.
- **Compose for them.** Review stills show the caption band in blue; a face under it is flagged.
- `PY tools/clip.py qa <clip>` measures the finished file: caption centre and line on real frames, safe area, and word times against the narration's pauses (`--listen` adds a check against recognised speech).

## Sound and voice

Standardized across every category; see `config/voices.json` and the `sound-design` skill.

- The voice take is the clock. Cuts and views land on words; holds are real silence after a shot.
- Every category uses **Alex - Upbeat, Energetic and Clear** at his natural pace, about **177 words per minute** (165-190), directed with contextual emotion and delivery tags (`[energetic]`, `[upbeat]`, `[amused]`, `[dramatic]`, `[deadpan]`, etc.). Never speed the voice up. Scripts of 170-198 words run about 58-68 s; if a take runs over 70 s, trim pauses and tags.
- Mix: voice on top, music about 19 dB under and ducked further under speech, ambience below that, effects on their words. -14 LUFS, peaks at or below -1 dBTP.
- Every contact effect on screen wants a sound: list them in the shot's `sound` so the sound designer places them on the same words.

## Gates and checks

Three recorded decisions by the user, from pictures, before the expensive work:

- **Gate A, characters and wardrobe** (`PY tools/clip.py cast-sheets <clip>`): four turns, five faces, an action pose, height beside a door, for every character in costume.
- **Gate B, sets** (`PY tools/clip.py setpreview <clip>`): every set at every light mood from six angles, with the audit.
- **Gate C, camera** (`PY tools/clip.py preview <clip>`): a low-resolution motion film of every shot with the view and move burnt in, a top-down diagram of the camera path, and the path measurements.

`stills` needs A and B approved; the final `render` and `assemble` need C too (exit 4 otherwise). `PY tools/clip.py gate <clip>` shows each gate, and says `stale` and what changed when its inputs moved after approval. An unattended run happens only when the user's own words ask for it, and is recorded as bypassed, never approved.

A finding is graded `block` or `warn` in `review/<shot>/checks.json`. Blocking: a face hidden behind the set, a figure floating or sunk, the camera inside or through geometry, a camera move over twice the speed limit, a mostly still shot, a burnt-out or black frame, a set that fails its audit or disagrees with the plan. A shot is not staged until `stills` has zero blocking items (exit 3 otherwise). Warnings are fixed or explained.

## Reviewing a shot

The reviewer sees two stills per view (stamped with the view, the time and the words being spoken), the safe area and caption band, the motion strips of every move, the camera path diagram, the set sheet and `checks.json`. Questions, in order:

1. **One world.** Does everything belong to the period and place?
2. **A complete place.** Count what you see against the bar: kinds and number of props, four depth layers, visible lights, atmosphere, readable details. Any bare corner or wall, an opening onto nothing, a stamped repeat? As good from the reverse angle?
3. **Grounded and clean.** Everything on something; nothing through a hand, a table or a wall.
4. **Costume and characters.** Fit, readable at a glance, the same person in every view and shot.
5. **Purpose.** Does each view show what the plan says it `shows`?
6. **First glance.** Does the eye land on what the narrator names, in the upper middle and clear of the caption band?
7. **Camera.** Does each move have a purpose and read as that move across its strip; is the subject held where the eye should be through it; does it end somewhere new; is the line of action kept?
8. **Transitions** motivated; **light** motivated, separated from the background, consistent.
9. **Performance and cause and effect.** Clear pose, right face, hands on things; a sound-off viewer could follow the ending.
10. **Captions and UI.** Faces above the blue band and inside the yellow box.

Verdicts: `pass` only when no change would make a viewer notice a better film; `fix` for a small change (a camera side or move, a mark, a missing light or occluder); `restage` when an action or setup does not read. Feedback names the view, the problem and the smallest change. Two fix rounds per shot at most; then the best version goes forward with a note for the human. A final-film review judges the sample frames for continuity of character, costume and set between shots, rhythm, variety of camera angle and the opening and closing images.

Stills cannot show how a move feels: the camera preview at Gate C is where the user judges that. Before the long render, `render --quality draft --step 3` and `assemble --tag animatic` make an animatic if you want to watch the whole film.
