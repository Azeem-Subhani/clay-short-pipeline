---
name: cinematic-style
description: The channel's production style - flat 2D characters in a real 3D world, one period per story, sets built around the action, views instead of cuts, acting in poses, captions on one centred line, and how shots are reviewed. Use when planning shots, building a set or shot in Blender, or reviewing frames.
---

# Cinematic style

The full guide is **`style/STYLE_GUIDE.md`**; the evidence behind it is `docs/REFERENCE_BREAKDOWN.md`. Read the guide once at the start of your task. This page is the card you keep in front of you.

**One test:** at this moment, what does the viewer need to see to understand or feel what the narrator is saying? Show that, large and clear, a moment before the words.

## Shots and views

A **shot** is one staged take in one set and time of day. A **view** is one camera framing inside it. Expect 2–5 shots and 9–24 views.

| The narration… | Give the viewer |
|---|---|
| names a new thing that matters | that thing as the subject, on the word |
| describes something too small to read | an insert |
| gives a reaction or a quoted line | that face, mouth moving on the quote |
| sets the scene or shows a big result | the wide (the same wide, so the change shows) |
| jumps in time or place | a hard cut, new light |
| launches an object | the camera travelling with it |

Stay on a view while the action inside it is still developing. Inside one place, travel (`travel=0.3`) to lead the eye; cut to go in or out on the same subject and for every jump. Keep the camera on one side of the action so screen directions hold. Open on the character and the event, in motion, on frame one.

## World and sets

- One period (`world.era`). Cast for the period, then dress the role: `recolor`, `hide`, `wear`. Each character reads at a glance by silhouette, colour, one prop.
- Start a set from its marks: where each person stands, where each story object is, where the camera side is. Put what the ending needs in frame early.
- Make the mechanism visible: if the story turns on how something works, build it so it can be seen working.
- A tall frame has depth, not width: stagger people in depth, lay places out along the view.
- Low near things at the bottom corners, action in the middle, a tall background that fills the top.
- Surfaces by name (`mat.surface`), a light you can feel, dressing at edges and background only.

## Camera

- Subject centre about 40% from the top; faces above the caption line (70%) and inside the safe box.
- Sizes: insert, close, medium (default for acting), full, wide. Change size clearly between neighbours.
- People from waist height, level or slightly low. Objects from above. No more than about 30° of tilt with characters in frame.
- No back views exist: people face the camera or stand in profile.
- A held view leans in a few percent (`push`). Lock the frame only on the last image.

## Performance

- Anticipation (4–8 frames), action (2–4), hold (10+). Face first, body 2–4 frames later. Eyes lead by a quarter second.
- One pose, one idea, clear as a silhouette (`docs/poses.png`).
- Hands exactly on props: `reach`, then `hold`, then `release`. Lifting leans back, reaching leans forward.
- Reactions in turn, never all at once. Quoted lines get `speak`.
- Mark every contact: splash, ripple, puff, drips, sparkle, a camera jolt.
- `idle()` on everyone. Walks: first steps or arrival, not the journey.

## Light

- Sun 30–60° to one side of the camera so cut-out shadows fall beside the figures.
- Time of day tells story time. One rig per set and time; the rig also sets how the cast takes the light.
- Darkness is deep colour, never black.

## Captions

One to three words, centred on the frame, one fixed line at 70.5% of the height, never wrapped, 0.08 s ahead of the word. Compose so no face sits under the blue band in the review stills.

## Review (seven questions, in order)

1. One world: does everything belong to the period and place?
2. Purpose: does each view show what the plan says?
3. First glance: does the eye land on what the narrator names?
4. Performance: clear pose, right face, hands on things, nobody a mannequin?
5. Cause and effect: could a viewer with the sound off follow how the ending works?
6. Polish: feet on the ground, nothing floating, no one hidden, no empty thirds, consistent light?
7. Captions and UI: faces above the band and inside the box?

Smallest change that fixes it: camera size, side or place; a pose; a mark. An action that does not read gets restaged.
