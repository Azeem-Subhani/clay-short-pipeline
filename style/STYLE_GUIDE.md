# Production style guide

How every Short on this channel is staged, shot and captioned. Written for the agents that make the film and for you when you review one. Numbers that scripts enforce live in [`style.json`](style.json). Where a rule comes from the two reference Shorts, the evidence is in [`docs/REFERENCE_BREAKDOWN.md`](../docs/REFERENCE_BREAKDOWN.md).

**The look:** flat 2D cartoon characters with bold outlines, staged in a real 3D world with real materials and light. Simple people, rich world.

**One test decides every choice:** at this moment, what does the viewer need to see to understand or feel what the narrator is saying? Show that, large and clear, a moment before the words. If you cannot say what a view gives the viewer that the one before it did not, it should not be there.

## The few things that never change

1. **1080×1920, 24 fps, 55 seconds at most.** Lengths come from the voice take, never from guesses.
2. **One world.** A story has one period and place (`world.era`). Every character, costume piece, surface and prop belongs to it. The plan check enforces the tags; your eyes enforce the rest.
3. **Fair play.** Never show what the narrator has not revealed. Anything the ending depends on is shown clearly before it is used (`setups`).
4. **The Shorts UI and the captions own part of the frame.** Faces and key action stay out of the bottom 24%, the top 8%, the left 5% and the right 14%, and above the caption line at 70% of the height. Review stills draw both.
5. **One light per place and time of day.** Light changes only when the story's time changes.
6. **Safety.** No real people, logos or brands. Never show a child being hurt. No copyable weapon or drug detail.

Everything below is craft: tools with reasons. Break a guideline when the film is better for it and you can say why.

## Shots and views

Two words, used strictly:

- A **shot** is one staged take: one set, one time of day, action that runs continuously. It is a file (`blender/sh03.py`) and a render unit. Most Shorts need two to five.
- A **view** is one camera framing inside a shot. The viewer experiences views. A Short has roughly 9–24 of them.

The first version of this pipeline cut 32 times in a minute; the second held five frames for nine seconds each. Both missed the same thing. The reference Shorts change the picture every two or three seconds, but most changes are the camera *travelling* inside one place: a whip from the bullet hole to the man watching, a push from the wide to the banknote, a flight with the rolling bomb. The viewer is led, not thrown. A hard cut is kept for a jump in place or time, or for going in or out on the same subject.

### When the viewer needs a new view

| The narration… | Give them |
|---|---|
| names a new thing that matters (a ring, a gate, a net) | that thing as the subject of the frame, on or just before the word |
| describes an action too small to read at this size (a ring slipping through mesh) | an insert of it |
| gives a character's reaction or a quoted line | that face, close enough to read, mouth moving on the quote |
| sets the scene or shows a result that changes the whole place (the pond empties) | the wide, ideally the same wide as before so the change is obvious |
| jumps in time or place | a hard cut and a new light or set |
| launches something (thrown, dropped, rolled) | the camera travelling with it |

### When to stay

Stay on the current view while the action inside it is still developing: a walk arriving, a pose changing, a second character reacting, a prop being used. The references hold up to five seconds when two things are playing at once (a man laughing in front, another rolling his eyes behind). A view may run long only if something new happens in it every second or two; write that in the plan's `inside`.

### How to get to the next view

- **Travel** (`cam.view(..., travel=0.3)`): inside one place, to carry the eye from one thing to another. About 0.3 s for a whip; 0.5–0.8 s when the journey itself shows geography (queen → across the water → the gate).
- **Follow** (`cam.follow(obj, t0, t1)`): with a falling, flying or rolling object.
- **Cut** (the default): to go closer or wider on the same subject, and for every jump in place or time.
- **Push** (`cam.push(t0, t1, 0.06)`): a held view should lean in a few percent. A truly locked frame is for the last image or a deliberate stillness.

Keep the camera on one side of the action. Draw a line between the two parties of a scene (the queen and the people she is talking to) and never cross it: then she is always on the right looking left, they are always on the left looking right, and no cut confuses anyone.

### The first two seconds

Open on the character and the event of the first clause, already in motion on frame one: the ring leaving her finger, not a garden. No fade-in. The place comes second, when the story needs geography.

## The world

Decide once, in the plan's `world`: the period (`era`), the place in one sentence, three or four rules for what belongs and what never appears, and a palette where each main character owns one colour.

- **Cast for the period, then dress the role.** The pack has 28 characters. `python tools/clip.py cast --era medieval` lists who fits. A rich merchant is the pack's peasant man in a wine-red coat with gold buttons, a ruff and a plumed cap (`costume`: `recolor`, `hide`, `wear`). A constable is never a soldier, a hoodie is never a tunic. If no character can be dressed to fit, say so in the plan rather than cast the wrong century.
- **Each character must read at a glance** by silhouette, colour and one prop. Write it down (`reads_as`).
- **Five or six kinds of object carry a period.** Repeat them: for a medieval castle garden, dressed stone, oak planks with iron bands, a banner, a barrel, ivy, a plank door in a round arch. Put period where the camera will be.
- **Text in the world is welcome when it is of the world** (a painted sign, a stencilled crate). Never modern type, never a brand.

## Sets

A set is built around what happens in it.

1. **Start from the marks.** Before any dressing, write the table of where each person stands and where each story object is (`MARK` in the set file), and where the camera side is. Place them so the camera can connect cause and effect: the gate that will drain the pond sits at the far end, in frame in every wide view from the first second.
2. **Make the mechanism visible.** If the story turns on how something works, build it so a viewer can see it work: water held high on one side of a board, a dry stone channel on the other; lift the board and the water runs down the channel while the level drops.
3. **A tall frame has depth to spare, not width.** Lay sets out along the view: a pond longer than it is wide, people staggered in depth so they stack up the frame instead of queueing across it. Two figures side by side fill the width; three need depth.
4. **Layers:** something low and near at the bottom corners, the action in the middle, a tall background (wall, tower, trees) that fills the top third instead of empty sky.
5. **Dress the edges and the background; keep the acting areas clear.** Tufts, flowers, ivy, reeds, a barrel: at wall feet, bank edges, frame corners. Nothing where someone stands or walks.
6. **Real surfaces.** Ask for surfaces by name (`mat.surface("castle_stone")`). Run `python tools/clip.py materials fetch <clip>` so they use scanned ambientCG textures; without them the same names give procedural stand-ins of the same colour and scale.
7. **A light you can see or feel:** a sun with a direction and long shadows, a torch, a window. One rig per time of day (`lights.rig("golden_hour", sun_from=-60)`).

Scale: adults in the pack are 1.6–1.8 m with heads about 0.55 m across. Doors about 2.5 m to the arch top, walls 4–6 m, a pond rim 0.2 m.

## Light

- **Side-front sun.** Flat characters throw cut-out shadows. Light from 30–60° to one side of the camera (`sun_from=40`) lays the shadow on the ground beside them and pins them down. From straight behind the camera the shadow hides behind the figure; from straight sideways it thins to a line.
- **Time of day is story.** Noon for the challenge, sunset for "he fished all day", a fresh morning for the simple answer. Changing the mood between shots tells time without a word.
- **The cast takes the colour of the hour.** `lights.rig` sets `cast.look` (tint, how much scene light reaches the figures, brightness). Do not relight characters by hand.
- **Darkness is deep colour, not black.** At night keep `ambient` up and add a visible warm source.
- Check every still: can you find the subject in under a second on a phone-sized image?

## Framing for 9:16

- **The subject sits in the upper middle:** centre about 40% from the top (`place=0.40`), faces above the caption line. Wide views may sit lower; the faces are too small for the captions to hurt.
- **Sizes** (`size=` in `cam.view`): `insert` an object or a hand action; `close` a face; `medium` waist up, hands in frame (the default for acting); `full` the whole figure with room to move; `wide` the place.
- **Change size clearly between neighbouring views.** Wide to medium to insert reads; medium to slightly-different-medium looks like a mistake.
- **Low for people, high for objects.** People from waist to chest height, looking level or slightly up (`high=-6` makes someone proud or threatening). Water, tables, hands on the ground from above.
- **Do not tilt more than about 30° with characters in frame.** They are flat; seen from steeply above they turn to slivers. Steep angles are for object inserts.
- **The pack has no back views.** Stage people facing the camera or in profile; never walking away from the lens. This is another reason to keep the camera on one side.
- **Check the wide for overlaps.** Staggered figures can hide each other from one angle and separate from another; `side=` is the tool.

## Performance

The characters have three drawings (front, three-quarter, side), five expressions plus neutral, a talking mouth, three hand shapes, a walk cycle, and bones that turn in the picture plane. That is enough for clear acting if every action is staged as poses.

- **Anticipation, action, hold.** Wind up for 4–8 frames, act in 2–4, then hold the result for 10 frames or more. `actor.squash(t, -0.08)` (a stretch) before a start; `squash(t, 0.12)` on a landing.
- **Face first.** Change the expression 2–4 frames before the body reacts (`expr(..., t)` then `pose(..., t + 0.15)`).
- **Eyes lead.** A character looks at a thing a quarter of a second before reaching for it or reacting to it (`eyes(dx, dz, t)`). Where the eyes point is where the viewer looks.
- **One pose, one idea, readable as a silhouette:** chest out and hands on hips is pride; both hands to the face is shock; a finger up is a rule; a sag with the head down is defeat. `docs/poses.png` shows every named pose.
- **Reactions in turn.** In a group, stagger reactions by 0.15–0.5 s, left to right or near to far. Never all on one frame.
- **Quoted lines get a mouth.** When the narrator speaks a character's words, call `actor.speak("first words", "last words")` and put the camera on that face.
- **Hands land exactly.** Use `actor.reach(side, thing, t)` so the hand is on the bar, the ring, the branch; then `hold` so the prop travels with the hand; `release` so it leaves cleanly. Key the reach again after the prop moves (a gate lifted) so the hands go with it.
- **Weight.** Lifting bends the body back; reaching bends it forward (`lean`); a fall stretches, a landing squashes. Light things spin as they fly.
- **Walking costs screen time.** Show the first steps or the arrival, not the journey: start, cut, result. Use the side or three-quarter view for walks across the frame.
- **Nothing freezes.** Call `actor.idle()` on everyone: blinks and breath. Give background characters one reaction per view.
- **Views of the character:** three-quarter is the default and the most alive; front for hanging, falling toward us, addressing the viewer; side for walking, pushing, pulling, reaching across.

Things to stage around rather than animate: climbing, getting up or down a level (hop, or cut), two characters gripping each other, anything seen from behind.

## Props and effects

- **A prop that matters is big in frame at least once** and is introduced in a hand or by the camera arriving on it.
- **Small precious things are drawn large and they glint:** a ring is 14 cm across here, with `fx.sparkle` when it should be found by the eye.
- **Mark every contact** with one small effect: `fx.splash` and `fx.ripple` on water, `fx.puff` for dust, a break or a landing, `fx.drips` after a soaking, `cam.shake` on a heavy impact.
- **Leave the evidence in the set.** The broken branch stays broken, the pond stays empty, the wet man stays wet in later views.

## Captions

Built by `tools/captions.py` from the same word times that set the shot lengths; drawn by Remotion.

- One caption at a time, **one to three words** (most are one), small words joined to the word they lead into: "her gold", "into the deep", "is yours,".
- **Centred on the frame, on one fixed line at 70.5% of the height.** Never wrapped: a long caption is scaled down a little instead.
- Bold white Montserrat with a thick dark outline and a soft shadow. Sentence case, the script's punctuation.
- Each caption appears 0.08 s before its first word and stays until the next one; after a sentence followed by a real pause the line clears.
- **Compose for them.** Review stills show the caption band in blue; a face under it is flagged.
- `python tools/clip.py qa <clip>` measures the finished file: caption centre and line on real frames, safe area, and word times against the narration's pauses (`--listen` adds a check against recognised speech).

## Sound and voice

Unchanged from the first version of the pipeline; see the `sound-design` skill.

- The voice take is the clock. Cuts and views land on words; holds are real silence after a shot.
- Delivery is directed in the text with audio tags and punctuation. About 145–165 words per minute; if a take runs over 55 s, cut words, never speed the voice.
- Mix: voice on top, music about 19 dB under and ducked further under speech, ambience below that, effects on their words. −14 LUFS, peaks at or below −1 dBTP.
- Every contact effect on screen wants a sound: list them in the shot's `sound` so the sound designer places them on the same words.

## Reviewing a shot

The reviewer sees two stills per view (stamped with the view, the time and the words being spoken), the safe area and caption band drawn on, and `checks.json`. Seven questions, in order:

1. **One world.** Does every person, costume, building and prop belong to the plan's period and place? Name anything that does not.
2. **Purpose.** With the words in the stamp in mind, does each view show what the plan says it `shows`?
3. **First glance.** Where does the eye land? It should be the thing the narrator is naming.
4. **Performance.** Is the pose a clear silhouette of one idea? Is the face right for the line? Are hands on what they hold? Does anyone stand like a mannequin?
5. **Cause and effect.** Can a viewer who has the sound off follow how the ending works (the `setups`)?
6. **Polish.** Feet on the ground, nothing floating or sunk, no figure hiding another, no empty top or bottom third, light consistent with the other views of this set.
7. **Captions and UI.** Faces above the blue band and inside the yellow box.

Feedback names the view, the problem and the smallest change that fixes it: a different size, side or place for the camera, a pose, a mark moved. If an action does not read, ask for it to be restaged, not polished. Two fix rounds per shot at most; then the best version goes forward with a note for the human.

Stills cannot show timing or how a move feels. Before the long render, make the animatic (`render --quality draft --step 3`, `assemble --tag animatic`) and watch it.
