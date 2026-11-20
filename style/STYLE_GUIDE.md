# Production style guide

How every Short on this channel is shot, lit and cut. It is written for the agents that make the film and for you when you review one. The numbers that scripts enforce live in [`style.json`](style.json); change a number there and every shot follows.

One test decides every choice: **does this make the viewer feel or understand exactly what the narrator's words need at this moment?** If you cannot say why a cut, a move, a light or a blur is there, take it out.

## The few things that never change

1. **1080×1920, 24 fps, 55 seconds at most.** Shot lengths come from the voice take, never from guesses.
2. **About 4–5 shots.** A shot is a long take with things happening inside it. Six to eight shots need a written reason per extra cut. More than eight is rejected by the validator.
3. **Fair play.** Never show what the narrator has not revealed. Every clue in the script is clearly visible in the shot that speaks it.
4. **The Shorts UI covers the edges.** Faces, clues and key action stay out of the bottom 24%, the top 8%, the left 5% and the right 14% of the frame. Review stills draw this box.
5. **One light rig per place and time of day.** Light changes only when the story changes it.
6. **Safety.** No real people, logos or brands. Never show a child being hurt. No copyable weapon or drug detail.

Everything below is craft: tools with reasons. Break a guideline when the film is better for it and you can say why.

## Why so few cuts

The last version of this pipeline made 32 cuts in 60 seconds. Cuts were standing in for ideas: nothing lasted long enough to be lit, animated or felt. A 10-second take in which the camera leans in, the focus moves from a sleeping boy to the shape behind him, and a window goes dark gives the viewer four new things without once resetting their eyes.

**Before you cut, try these in order.** Each is a way to show something new inside the shot.

| The story needs… | Do this inside the shot | Example |
|---|---|---|
| Attention to move between two things already in frame | **Shift focus** (rack) | The house is sharp while he watches it. On "Tonight, he would take the boy" focus moves to him. |
| A feeling to grow | **Slow dolly in**, 5–15% of the distance over the sentence | The room closes around the boy as the man crosses it. |
| New information in the same place | **Move the camera to reveal it**: crane, tilt, track, dolly past a foreground object | Start on the high window ("he climbed through a window"), crane down to the boy ("in the basement, a small boy"). |
| A change of state | **Change the light** on the word | The windows go dark on "the lights went out". Police blue arrives before the cars are named. |
| A reaction | **Let the character react**: head turn, brows, a step, a stop | The boy's brows jump and his head turns on "mouth". |
| Time to land a line | **Hold.** Stop the camera completely | Everything is still for "Papa." |

**Cut when the story truly jumps:**

- a new place or a jump in time ("At midnight…")
- a jump in scale that a move cannot make in time (the whole house → one wire)
- the hard part of an action must be skipped (start, cut, result)
- the twist needs a clean frame the viewer has not seen

Every shot after the first states `why_cut` in the plan. "To keep it interesting" is not a reason.

## When to hold, when to move, when to shift focus

**Hold the camera** when the action or the light is the event, when a line needs to land, and on the last image. A still camera in a world with small life in it (breathing, a blink, a flicker) looks confident and expensive.

**Move the camera** only with a motivation, and make one move at a time:

| Move | What the viewer feels | Use it for | Kit call |
|---|---|---|---|
| Slow dolly in | Growing importance, a decision, tension tightening | A sentence that turns ominous; approaching a clue | `cam.push(t0, t1, 0.10)` or two `cam.at` keys |
| Dolly out | Release, isolation, "now you see the whole picture" | The reveal; leaving a place | `cam.pull(t0, t1, 0.15)` |
| Crane or tilt | A vertical reveal: natural in 9:16 | Window down to the bed; boots up to a face | `cam.at(t, pos=…, aim=…)` with a new height |
| Track with a subject | We travel with them | Walking or running with purpose | `cam.track(actor.head, t0, t1)` |
| Follow from a fixed spot | We watch them come or go | A long approach; someone leaving | `cam.follow(actor.head, t0, t1)` |
| Static | Observation, dread, letting it play | The moment before the strike; the last word | `cam.hold(t)` |

- **Start a move before the word it lands on and finish on or just after it.** A push that arrives on the stressed word lands it. One that starts there feels late. Use `shot.t("phrase", offset=-0.5)`.
- **Slow is the default.** In a 6-second sentence a 10% dolly is felt without being noticed. A big move is a statement and should be rare.
- **Every move eases in and out.** The kit does this for you.
- Pans are weak in a narrow frame. Prefer dolly, crane and tilt.

**Shift focus** when attention moves between two things at different depths that are both in frame. It is the gentlest cut there is. Give it 0.5–0.9 s and finish it on the word that names the new subject. Never blur the thing the narrator is talking about.

**Background blur is a decision about the place.** Ask: does the viewer need to read where we are?

| Situation | `blur` | Why |
|---|---|---|
| A new place the viewer must understand | `light` | They need the geography |
| A character acting in a place that matters | `medium` | Subject clear, place still readable |
| An emotional close-up | `strong` | Only the face matters |
| A clue insert | `strong` or `macro` | The object is the only thing in the world |
| Two things that both matter at different depths | `light`, or a rack between them | Let the viewer connect them |

The kit turns the blur level into an f-stop for the lens and distance, and never lets the sharp zone get thinner than a head. Focus on an object or a character anchor (`actor.head`), not on a number.

## Framing for 9:16

- **Stack the frame top to bottom:** foreground low, subject in the upper-middle, sky or threat above. Eyes and key action sit between 45% and 80% of the frame height.
- **A tall frame shows a lot of ceiling and sky.** Build walls 3.3 m or higher, add a ceiling, or use a sky backdrop. The checks flag an empty black top.
- **Two people side by side do not fit.** Use depth: one near, one far, or over a shoulder.
- **Shot sizes:** wide for where and how alone, medium for what someone is doing, close for what they feel, insert for a clue. Change size or angle clearly from one shot to the next.
- **Angle is power:** eye level is with them, high makes them small or watched, low makes them a threat. In a story with a flip, a low angle on the secret hero is fair: it is how the scene feels before the truth.
- **Lens:** 24–35 mm stretches space and suits wide and moving shots. 50 mm is calm. 70–85 mm flattens and isolates: faces and inserts.
- **Keep screen direction.** If he walks left to right in one shot, he keeps going left to right in the next.

## Light

Light has two jobs: mood, and telling the eye where to go. A frame can have the right mood and still fail if the viewer cannot find the subject on a phone in two seconds.

**A rig is four ideas**, the same in every shot so the channel looks like one world:

| Part | What it is | Rule |
|---|---|---|
| **Key** | The motivated source: sun, moon, window, lamp | From the side or three-quarter back, 35–80° off the camera axis. Light from the camera flattens clay into a blob. |
| **Fill** | Soft ambient: world colour plus a huge weak light from the camera side | Always on. Shadows take its colour, so it is never grey. Less fill is more drama, but never zero. |
| **Rim** | A thin edge from behind | Separates the subject from a dark background. Essential at night. |
| **Practicals** | Sources the viewer can see: lamp, window, siren, the gap under a door | They add depth and story. A warm practical in a cold scene is where the eye goes. |

`lights.rig(mood, subject=…)` builds key, fill and rim in the right balance. Moods: `day_soft`, `golden_hour`, `overcast`, `night_moon`, `interior_warm`, `interior_cold`, `interior_night`, `dread`, `candle`, `relief`.

**What makes it look polished**

- **Soft ambient fill everywhere.** Darkness is deep colour (indigo, blue-green), not black. If most of the frame reads as pure black it is underexposed, not moody.
- **Shadows ground things.** Every character and prop sits on what it rests on and throws a contact shadow. The render settings (soft ray-traced shadows, ambient occlusion) are locked in `style.json` for this.
- **The subject is the brightest or most contrasted thing in frame**, unless you are hiding it on purpose as a silhouette.
- **Medium-soft shadows:** large sources, clear direction.
- **Light the eyes.** `lights.eye_light(cam.ob, actor.head)` adds a small catchlight for medium and close shots.
- **A night exterior needs a sky.** `build.backdrop` glows by itself so trees and roofs have something to stand against.
- **Indoors, keep lights inside the room** (rig `distance` 2.5–3.2 m) or the walls shadow them.
- **Haze** (`lights.haze(0.01)`) shows beams and depth. Use it rarely: it costs render time.

**Plan a light story.** Across the film, light should change with the meaning: warm window in a cold night → windows go dark → one cold pool of moonlight → police blue → a warm key opens on the truth. When the light turns on the same word as the story, the film feels designed.

**Common failures and fixes**

| You see | Usual cause | Fix |
|---|---|---|
| Flat and grey | World too bright, no clear key | Lower `ambient`, move the key further to the side |
| Burnt white patch | A practical too strong or too close | Halve its power, make it larger |
| Subject lost in the dark | No rim, subject turned from the key | Raise `rim`, add a practical behind, or turn the subject |
| Black empty frame top | No ceiling or sky | Backdrop, ceiling, taller walls, or tilt down |
| Light differs between shots of one place | Rig rebuilt per shot | Build the set and its rig in one function in `sets.py` and call it from every shot |
| Light through a wall | Rig distance larger than the room | `distance=2.8`, or leave that wall out of the set |

## Staging: what can be built well

Shots are built by an agent writing Python against `stagekit`. Some things come out right every time. Others cost many tries and still look stiff. Plan around that: it is how films hide expensive moments anyway.

| Reliable | Needs care (say why in the plan) | Stage around it |
|---|---|---|
| Camera moves, focus shifts, light changes | One character carrying another (`actor.carry`): keep it wide or frame faces only | Two characters touching with hands or faces in close-up |
| Standing, walking between marks, turning, stopping | Sitting down or standing up on camera (cut to them already seated) | Finger acting: turning a key, tying, typing |
| Sitting, lying, crouching, reaching, pointing | A prop changing hands | Climbing, falling, fighting |
| Head turns, brow expressions, blinks, breathing | Doors opened by a hand (animate the hinge, keep the hand off frame) | Mouth acting: the characters have no mouth. Emotion is brows, head and body. |
| A prop held in a hand | Fast action: keep it short and mid-distance | Pulling on clothes, folding cloth |
| Rigid prop motion: a key turning, a wire dropping, a door swinging | | |

Ways to stage the hard ones:

- **Start, cut, result.** Show the reach, cut, show him already carrying the boy.
- **Let the object act.** For "locked the door", the key turns by itself in a close-up while his shadow leaves the door.
- **Silhouette or shadow.** A shadow crossing a moonlit floor tells the climb.
- **One simple motion in a close-up.** A reach toward a face, and the face reacts.
- **Let sound carry it.** A snip, a clunk, a sharp breath off screen often lands harder.

**Never let the world freeze.** Every character gets `actor.idle()` (breathing, blinks). Eyes lead: a character looks 0.3 s before it acts. After a big action, hold a moment so it lands.

**Double meanings.** In flip stories an action must look threatening now and make sense later. Stage it honestly for both readings: the reach toward the boy is quick and firm, the carry holds him close.

## Sets and assets

- **One material language.** Everything is matte clay: chunky, rounded, bevelled, palette colours. A photoreal prop next to a clay character looks wrong however good it is. Imported assets go through `assets.clayify`.
- **Library first, then BlenderKit, then build.** Every asset used in a shot ends up in `library/assets` with its source and licence.
- **Quality follows the camera.** Hero props (close-ups) get the care. Background dressing needs silhouette and colour only.
- **Lived-in, but the subject's area stays clean.** Add a few story-telling details per set at the edges and in the blur: a cup, a bag, a coat. Keep negative space around the subject.
- **Depth in layers:** something near the lens, the subject, a middle ground, a far background.
- **Scale is real.** Doors about 2.05 m, chair seats 0.45 m, the adult cast 1.76 m, the child 1.1 m.
- **Palette of 3–5 colours per story.** Each character has one clear colour that separates it from the set.

## Sound and voice

- **The voice take is the clock.** Cuts land in the gaps between words. Holds are real silence added after a shot.
- **Delivery comes from the text.** With Eleven v4 and v3, direction is written as audio tags in square brackets plus punctuation: one direction per beat is enough. See the `sound-design` skill.
- **Pace:** about 145–150 words per minute. If a take runs over 55 s, cut words. Never speed the voice up.
- **Mix:** voice on top; music about 19 dB under it and ducked further while the narrator speaks; ambience under that; sound effects placed on words. Final loudness −14 LUFS, peaks at or below −1 dBTP.
- **Silence is a tool.** Thin the music before the last line. Let one sound effect own its moment.
- **Captions:** two or three words at a time, the spoken word lit, inside the safe area.

## Reviewing a shot

The reviewer sees stills (first frame, each marked moment, last frame) with the safe area drawn on, plus measured checks. It asks five questions in order:

1. **Purpose.** With the narration for this shot in mind, do the frames do what the plan's `purpose` says?
2. **First glance.** Where does the eye land first? It should be the thing the narrator is talking about.
3. **Mood and light.** Does it feel like the beat? Is the subject readable, the dark coloured rather than black, the light consistent with the set's other shots?
4. **Polish.** Anything cheap or broken: floating props, limbs through bodies or furniture, a stiff mannequin pose, empty black areas, sharp game-like edges, wrong scale?
5. **Fair play and safety.** Is anything shown before its time? Is each clue clearly visible? Is key content inside the safe area?

Feedback names the problem, where it is, and the smallest fix that serves the purpose. It never asks for another cut. If an action does not read, the answer is "restage", not more polish. A shot gets at most two fix rounds; then the best version goes forward with a note for the human.

Stills cannot show flicker, timing or how a move feels. Watch the animatic (`render --quality draft --step 4`, then `assemble --tag animatic`) for those.
