---
name: cinematic-style
description: The channel's production style - simple round cartoon characters (real 3D figures on a Mixamo skeleton, drawn faces) in a complete, richly dressed 3D world, one period per story, a camera that moves for a reason and leads the eye, light you can point to, three approval gates, and how shots are reviewed. Use when planning shots, building a set or shot in Blender, or reviewing frames.
---

# Cinematic style

The full guide is **`style/STYLE_GUIDE.md`**; the numbers scripts enforce are in `style/style.json`; the evidence is `docs/REFERENCE_BREAKDOWN.md`. Read the guide once at the start of your task. This page is the card you keep in front of you.

**One test:** at this moment, what does the viewer need to see to understand or feel what the narrator is saying? Show that, large and clear, a moment before the words, and make the picture worth looking at.

**The bar** (measured on four reference Shorts): 22-33 framings a minute; the camera moves 60-80% of screen time and "static" holds still drift 2-5%; more than half of the transitions are camera events (whip, travel through an opening or screen, crane), not plain cuts. Where the references are weak and we must be better: bare interiors, three-wall stages, characters that slide instead of stepping, flat lighting, repeated props, inconsistent set colour between shots.

## Shots, views and the camera

A **shot** is one staged take in one set and time of day. A **view** is one camera framing inside it. A Short has a few shots and many views.

| The narration... | Give the viewer |
|---|---|
| names a new thing that matters | that thing as the subject, on the word (a push or an `insert`, big) |
| describes something too small to read | an insert, an orbit or handheld on it |
| gives a reaction or a quoted line | that face, mouth moving on the quote, a slow push |
| sets the scene or shows a big result | the wide: a crane or `establish` from high; the same wide again so the change shows |
| leads from one thing to the next | a whip (0.3-0.5 s) or a trip `through` an opening |
| jumps in time or place | a transition event on the shot: whip, dissolve, dip |
| launches or drops an object | the camera follows it |

- **Moves have reasons.** Slow push 1.5-3 s (+5-40% subject size, ease out) for a realisation; fast push 0.5-1.5 s for a shock; lateral truck 1.5-3 s (a third to half the frame width) beside the action or past an occluder; orbit about 3 s, 25-30 degrees, to turn an object or person; crane 2.5-3 s, 35-75 degrees of pitch, from person to geography; follow or track 2-3 s; pull out through an object 0.5 s; rack focus to move the eye between two faces. A move that goes nowhere is cut.
- **Angles.** Wides low or eye level for people, high or top-down for geography. Hero props shown big when explained. A foreground occluder (column edge, plant, shoulder) in wides. Any angle is fine on a 3D figure: back views, walking away, reverse coverage, steep looks up at a hero (past 60 degrees the checks warn).
- **The line of action.** Two parties in a scene: the camera stays on one side of the line between them (`cam.line`); crossing it is a decision you show.
- **Frame for 9:16.** Subject in the upper middle (centre about 40% from the top); faces above the caption line at 70.5% and inside the safe box; stagger people in depth; a low near thing in a corner.
- **Size changes clearly** between neighbouring views. Open on the character and the event, in motion, on frame one.

## Sets: complete places

- A set is a place a camera can go round. Marks first, then enclosure (floor, ceiling, four walls, every opening with something behind it), then four depth layers (foreground occluder, midground, background, beyond), then practical lights, atmosphere, readable details, then one light rig per time of day.
- **The numbers:** a wide shows at least 14 kinds of thing and 60 objects; at least 3 visible practical lights indoors; one atmosphere element; at least 3 readable details; nothing floating, sunk or intersecting; no opening onto a void. `PY tools/clip.py setpreview` measures them and blocks.
- Start from a worked set (`examples/sets/`) and a theme of the right period (`stagekit/dress.py`). Surfaces by name; the same colours every time the set returns.
- One period (`world.era`). Everything carries period tags and `plan-check` enforces them.

## Characters

- Real 3D Aj figures from the registry (`PY tools/clip.py cast`): any angle, back views fine. A missing character, outfit or animation is asked for through `PY tools/clip.py casting <clip>`, never invented.
- Each reads at a glance by silhouette, colour and one prop (`reads_as`). Costume fits: no skin through cloth, no clipping.
- Acting is named actions and Mixamo clips keyed to words (`shot.t`). Eyes lead by a quarter second, face a few frames before the body, hands exactly on props (`reach`, `hold`, `release`), contact marked (splash, puff, a camera jolt), `idle()` on everyone, reactions in turn.

## Light

- A motivated key you can point to (window, lamp, fire), a rim or value step that separates figures from background, practicals you can see, one atmosphere element, darkness as deep colour.
- Time of day tells story time; one rig per set and time; the rig also sets how the cast takes the light.

## Gates and checks

The user approves **characters (A)**, **sets (B)** and **camera (C)** from previews, in that order; the tools refuse to go on without them (exit 4). `stills` ends with zero blocking items (exit 3 otherwise); warnings are fixed or explained. Nobody "improves" an approved gate's inputs without a new decision.

## Captions

One to three words, centred, one fixed line at 70.5% of the height, never wrapped, 0.08 s ahead of the word. Compose so no face sits under the blue band in the review stills.

## Review (in order)

1. One world. 2. A complete place: count it against the bar, from this angle. 3. Grounded and clean: no floating, no intersections, hands on props. 4. Costume and characters: fit, readable, consistent. 5. Purpose of each view. 6. First glance: the eye lands on what the narrator names. 7. Camera: each move has a purpose, reads as that move across its strip, holds the subject; line kept. 8. Transitions motivated. 9. Light motivated, separated, consistent. 10. Performance and cause and effect. 11. Captions and UI. Nothing broken is not the same as good: ask whether a viewer would notice a better film. Smallest change that fixes it; an action that does not read gets restaged.
