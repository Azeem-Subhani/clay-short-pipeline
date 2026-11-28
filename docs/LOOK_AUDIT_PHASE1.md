# Look audit, phase 1: what actually causes the flat picture

Date: 2026-11-28. Subject: the test film "Two Seconds at the Office Door", scored 4.5/10 for visual polish by an outside reviewer who saw only frames. Their assessment gave causes as guesses. This audit checked each guess against the code and against the training-room shot (sh08) built in Blender. Nothing in the pipeline was changed.

Evidence: five area reports, the scene dumps and the reviewer's text are in `output/experiments/look_audit/`. "Measured" below means read from the built scene or from the film's frames; "code" means read in a file. A second opinion from Gemini Neon (T3 thread "Look audit: second opinion (Neon)") found the shot-file lighting block independently; its claims quoted here were checked against the code.

## The short answer

The reviewer is right about what is wrong on screen and mostly wrong about why. The renderer is EEVEE, not Cycles, and it is not short of samples. The picture is flat because of four decisions in the code, in this order of weight:

1. **Almost no light casts a shadow.** In sh08, 2 of 34 lights cast shadows, and both are suns that the ceiling blocks (measured: 12 of 12 rays from the faces to the suns hit the ceiling slab, walls or trim). No light in the room can put a shadow under a chin, a hand or a chair.
2. **The strongest light on the faces is a blue, shadowless spot next to the lens.** The shot file adds four "screen glow" lights totalling 2,210 W of the scene's 3,262 W. One of them is an 1,800 W spot at about 11,000 K aimed at the seated hires (`sh08.py:181-187`), almost on the camera axis for the 01:03 view.
3. **Nothing is warm and nothing is graded.** Every fixture in the room is between 4,900 K and 7,000 K. The view transform is "Khronos PBR Neutral" with no look, exposure 0, no compositor, and a finish of a 0.16 vignette and 0.02 grain.
4. **Nobody judges the look.** The measured checks are three wide brightness limits. The reviewing agent saw 270x480 draft stills without ray tracing, and its verdict on sh08 names no light or colour fault.

Clothing is a separate problem with a different cause (section 5).

## 1. Light (the main cause)

| Fact | Value | Evidence |
|---|---|---|
| Lights in sh08 | 34: 15 area, 10 spot, 7 point, 2 sun | measured |
| Lights that cast shadows | 2, both suns (`SUN_rake`, `SUN_window`) | measured |
| Can a sun reach a face | No: 12 of 12 rays blocked | measured |
| Screen glow share of all watts | 2,210 of 3,262 W (68%) | measured; `sh08.py:178-187` |
| Estimated share of face light from the glow | 44 to 65% (inverse-square ranking, not exposure) | estimate |
| Ceiling panels, fill and downlights together | about 250 W | measured |
| Warmest fixture in the room | about 4,900 K (window key, downlights 5,050 K) | code and measured |
| Ceiling panel colour | #F4F6FF, about 7,000 K | `furnish.py:724` |
| World | dim blue-grey dome, strength 0.065 | measured |

Why nothing casts a shadow:

- The kit creates ceiling panels, downlights, fills, rims and glows shadowless (`furnish.py:730`, `lights.py:174, 451, 467`).
- The set passes `shadow=False` on its three window keys (`set_training_room.py:49`).
- `limit_shadows` exists to stop EEVEE's "Shadow buffer full" error and switches shadows off on all but the strongest few local lights (`lights.py:351-365`). In this room it has nothing left to switch off.
- Where shadows are on, their resolution is set to 3 to 8 cm per texel (`lights.py:163, 212, 311, 343`). A chair leg is 2.6 cm wide, so it could not cast a clean shadow even from a casting light.

How the light is put together:

- The set author lights the room once in `build_set`, before any camera or actor exists. `rim_light` and `sun_from` assume the camera stands on -Y.
- The shot author then rewrites it by hand. `sh08.daylight_grade()` cuts panels to 40%, downlights to 50%, fill to 35%, keys to 60%, halves the world, and adds an 8 W/m2 sun that the ceiling blocks (`sh08.py:115-142`). The glow lights are added after it and are not scaled. `sh05`, `sh03` and `sh06` have their own versions. No gate or review compares the result with the set the user approved.
- The dimming touches the panel lights but not the panel surfaces, which stay emissive at strength 5.5 and render white. The ceiling fills 21 to 22% of the frame in both views (measured).
- There is no notion of a key, fill or rim per character, no light placed relative to a face or to the real camera, and no exposure control per view.

The film's own frames agree (measured on `render/*/final`, every 12th frame):

| Shot | Mean brightness | Darkest tenth | Brightest tenth | Colour lean |
|---|---|---|---|---|
| sh01 entrance, dusk | 0.31 | 0.09 | 0.60 | neutral |
| sh02 entrance, rain | 0.40 | 0.15 | 0.62 | slightly cool |
| sh03 lobby, rain | 0.36 | 0.18 | 0.56 | cool |
| sh04 office, day | 0.53 | 0.21 | 0.78 | slightly warm |
| sh05 dark room | 0.25 | 0.07 | 0.66 | strong blue |
| sh06 office, night | 0.28 | 0.08 | 0.59 | blue |
| sh07 entrance, dusk | 0.37 | 0.17 | 0.63 | strong orange |
| sh08 training room | 0.55 | 0.26 | 0.80 | blue-cyan |

sh08 has no dark tones at all (its darkest tenth sits at 26% brightness), which is what "washed out" is. Brightness swings from 0.25 to 0.55 between shots and the colour lean flips from blue to orange with nothing balancing them.

Other shots, from code and the scene dump (leads, not measured exposure):

- sh06, about 00:50: one 120 W warm lamp spot is 1 m from one investigator and 1.7 m from the other, the rim and fill are aimed at one head only, and the guard has no directional light.
- sh05: a hand-added fill of #2A3F9A (blue 14 times red) on warm grey walls, plus a blue kit fill and LED strip.
- sh02: 86 lights, 1 shadow caster (a 26 degree soft sun), cool by design.

## 2. Render and colour chain

| Fact | Value | Evidence |
|---|---|---|
| Engine | EEVEE, Blender 5.3.0 | measured |
| Final quality | 48 samples, ray tracing on (screen space), fast GI on | measured; `core.py:164-186` |
| Left at Blender defaults | ray tracing at half resolution, trace quality 0.25; fast GI at half resolution, 2 rays; shadow jitter off; film filter 1.5 px | measured |
| View transform | Khronos PBR Neutral, look None, exposure 0 (it did apply) | measured |
| Compositor | none | measured |
| Frames | 8-bit PNG | `core.py:147-150` |
| Finish | vignette 0.16, grain 0.02, no contrast, colour or sharpening step | `remotion/src/Short.tsx:34-50` |
| Encode | each frame encoded twice (CRF 12 per shot, CRF 16 for the film), 10.1 Mbit/s | `assemble.py:127, 176`; ffprobe |
| Balancing between shots | none | code |

"Khronos PBR Neutral" was chosen for the old flat 2D cast, to keep drawn colours unchanged (`core.py:139`). It has almost no contrast curve. `docs/RESEARCH.md:70` records that the intent was once AgX "Medium High Contrast" with shadow jitter; neither is in the code.

The reviewer's settings table (their section 6.2) is mostly Cycles rows: bounces, adaptive sampling and OpenImageDenoise do not exist in EEVEE.

## 3. Environment materials and geometry

- 30 of the 52 catalogued surfaces are ambientCG scans, all at 1K. A scan gets its colour, roughness and normal maps at full strength, with no variation, rotation or anti-tiling (`mat.py:426-475`).
- The wall scan (1024x512) is mapped to a square 2 m tile, so it is stretched 2x vertically, at full normal strength. This is the "aggressive wall texture".
- The ceiling tile is not a ceiling material. It uses the stone-block generator, including its stain multipliers (`mat.py:150-161`), under seven emissive panels. A plain `ceiling_smooth` exists and is not used here.
- Furniture is flat colour with one hand-typed roughness per part: 436 `mat.solid` calls in `furnish.py`, with no convention per material family.
- Edges are bevelled, contrary to the reviewer's guess: 171 meshes in sh08 carry a bevel modifier, typically 8 to 10 mm. Chair legs are 6-sided rods without one.
- Glass is a 16% alpha blend with no refraction, and the city backdrop is hidden from reflections (`arch.py:1033-1035`).
- Puddles are opaque hard-edged discs placed on the ground (`dress.py:428-430`), separate from the wet-ground material, which only applies where a set author picked a `_wet` surface. There is no scene-wide wetness.
- Scanned photographic surfaces sit beside flat-coloured props and cartoon characters with no shared palette, saturation limit or roughness convention. Nothing in the material code reads `style/style.json`.

## 4. Skin and hair

- Skin: head texture, roughness 0.58, specular 0.35, subsurface weight 0, no normal or bump (measured). Under an unshadowed blue spot this is a plausible cause of the pale faces; it needs a render to confirm.
- Hair: one material, roughness 0.62, specular 0.3, a root-to-tip ramp, no sheen or anisotropy (`hairkit.py:175-196`).
- A skin shader change must leave the mouth controller node intact (`aj_face.py:42-48`).

## 5. Clothing

The reviewer guessed missing fabric detail. That is wrong for most garments: the cotton and woven kinds already carry 2K weave normal and roughness maps (measured). The causes are these:

- **A garment is an offset shell of the body's own skin.** Skin faces are subdivided once, pushed out 6 to 30 mm, smoothed and given the body's bone weights (`templates.py:821-881`). It is single-sided, smooth-shaded everywhere, with only an Armature modifier: no thickness, no folds, no structural seams (measured: no Solidify, 214 open boundary edges on a T-shirt). Collars, cuffs, buttons and rolled hems do exist as geometry.
- **The weave is too fine to see.** It tiles every 16 to 18 cm, so at phone size it averages to a smooth surface, while specular stays at 0.5 and sheen at 0.3.
- **The fabric's own contrast is cut to about 37%** by a halving at build and a further tint step at load (`templates.py:1383-1385`, `aj_wardrobe.py:161-203`). Code only; a render would confirm it.
- **One fabric plays four roles.** Cardigans, blazers, ties and all trousers and skirts use the same woven scan, tinted (`templates.py:1753, 2291, 2299`). There is no knit or wool.
- Flat shadowless light makes all of this worse.

What the limits allow: the pack rules forbid changing the head, the 3D mouth, bone names and rest poses, loosening a fit limit, and using an unfitted garment. They do not forbid new materials, and the fit check never reads a material. So a shader change is free. Folds, thickness or new weights mean rebuilding garments through the fitter and an independent review.

Where a change would reach: the fabric recipe is one function, but garments are baked into per-body fit files, so a recipe change needs a rebuild. The load-time tint (`aj_wardrobe.tint_material`, `tint_skin`) runs for every character in every film and is the one place a shader override reaches the whole cast without rebuilding anything.

## 6. Quality control and art direction

- Measured look checks: mean brightness between 0.10 and 0.72, up to 4% blown, up to 50% pure black (`review.py:280-296`). No contrast, colour, face exposure, shot-to-shot or reference comparison.
- The reviewing agent judges draft stills at 270x480, 6 samples, no ray tracing. Its sh08 verdict lists six issues, none about light or colour, and praises the sun shafts.
- The shot plan carries a time-of-day name per shot and a palette for the world. It has no lighting intention per shot or view.
- No approved reference frame and no look-development step exist. Gate B approves sets before the shot's lights and camera exist, and the shot author's later light changes pass no gate.

## 7. The reviewer's guesses, judged

| Guess | Verdict |
|---|---|
| Lights are functional, not shaped; no primary source | Confirmed, and the cause is shadowless lights |
| Too much fill | Refuted: fill is about 250 W of 3,262 W |
| Weak contact shadows from weak indirect light or poor shadow quality | Confirmed as seen; the cause is that no local light casts a shadow |
| Low render quality or samples | Mostly refuted; some EEVEE options sit at half-resolution defaults |
| Colour management and grading missing | Confirmed |
| Clinical white light | Confirmed; it comes from the fixtures and a blue spot, not from a grade |
| Garments are simplified body shells without thickness or drape | Confirmed |
| Fabric lacks normal and roughness detail | Refuted for cotton and woven; the detail is too fine and too flattened to read |
| Skin flat, needs subsurface | Confirmed in the settings (subsurface 0); effect unmeasured |
| Sharp unbevelled edges | Mostly refuted |
| No approved material library | Partly: a surface catalogue exists; props bypass it with typed constants |
| The critic checks that objects exist, not that the picture looks finished | Confirmed |
| Ceiling too prominent | Confirmed: 21 to 22% of the frame, white panels, a stained stone material |

## 8. What is fixed in one place

Reaches every future film: `style/style.json` and `core.py` (engine options, view transform, exposure, a compositor if one is added), the mood table and light functions in `lights.py`, fixture defaults in `furnish.py`, `mat.surface` and the catalogue, the fabric recipe and the load-time tint, the finish in Remotion, the review thresholds, and the agents' and skills' instructions.

Typed by hand each time: every set's lights and shadow flags, every shot's light edits, material choices on props.

## 9. Phase 2 results: what the comparison renders showed

Same day. One frame of sh08 (shot frame 25, film 01:03; frame 73 for the screen view), one change per render, all made in memory after the pipeline built the shot. Sheets, renders, the harness and three write-ups with every value are in `output/experiments/look_phase2/` (`PART_A.md`, `PART_B.md`, `PART_C.md`, `sheets/`). The film's own sh08 frames are older than the current shot file, so the baseline is the shot as it builds today; the blue glow lights are in the committed shot file too.

| Question | Result | Sheet |
|---|---|---|
| Does the blue glow cause the wash | Yes, the largest single change. Face brightness drops from 155 to 105 of 255 and the skin regains colour and shape | `sheet_L` L1 |
| Is the set's own light better than the shot's edit | Yes. With the shot's edits undone and shadows on the three window lights (B0), the picture is natural and grounded | `sheet_F` B0 |
| Do shadows on the existing fixtures ground chairs, hands and feet | Yes. 25 casting lights overflow the 512 MB shadow pool; it needs 2048 MB and 0.002 m. Render time goes from 3 s to 7 or 8 s a frame | `sheet_L` L3F |
| Do higher EEVEE options help | No. Nothing visible on the film's light (ssim 0.99) at 3.5 times the time | `sheet_R` R1 |
| Is Cycles needed | No. A half-size Cycles frame took 7 s and looks close to EEVEE once the light is right: a little brighter and smoother | `sheet_R` C1 |
| Which view transform | Not settled. AgX Medium High Contrast handles a warm cast best but pushes skin pale or orange depending on exposure; PBR Neutral keeps colours and the strongest cast. Filmic yellows skin, Standard clips | `sheet_T_f25`, `sheet_C_f25` |
| Does skin subsurface help | No. Invisible in EEVEE even at weight 0.8 | `sheet_S_detail` |
| What moves clothing from plastic to cloth | A matte response does the most (specular 0.15, sheen 0.7, roughness floor 0.8; the trousers' roughness map runs from 0.28). Thickness of 2.5 mm rounds cuffs and hems. A weave three times larger reads as a fishnet on jeans. Restored contrast and crevice shading are invisible at phone size. The smooth shell with no folds remains and no shader removes it | `sheet_G_detail` |
| Ceiling and wall | The plain ceiling surface removes the stained grid but leaves an empty slab; the wall fix is small at phone size | `sheet_M` |
| Grade | A restrained grade adds a little and costs about 0.5 s a frame | `sheet_F` F1 |

Two warm rigs were tried:

- The first (every source warm, a wide key 21 degrees off the lens) turned the whole room orange and left the faces flat: shadow cheek at 90% of the lit cheek.
- The second, from Gemini Neon's design (a smaller 4,300 K key from the window side about 50 degrees off the lens, cool 5,800 to 6,500 K window light and fill, ceiling at 3,900 K and dimmed), reads warm with real shadows on the floor and models the front woman's face at a ratio of 0.41. It still fails on four counts: white paper and the tablet arms go cream, chair backs go near black, only the front woman is modelled (the others stay at 0.85 to 0.90, the trainer at 0.92), and the trainer barely separates from the wall. `sheet_C_f25`, `sheet_C_f73`.

## 10. Phase 3 so far: the gold-standard candidate

The owner chose the second warm rig as the starting point. Two rounds refined it on both frames; every value and measurement is in `output/experiments/look_phase3/ROUND1.md` and `ROUND2.md`, the candidate frames are `renders/EF_f25.png` and `EF_f73.png`, and `sheets/before_after.png` sets it against the film's light. It is still an experiment: all of it is applied in memory by `output/experiments/look_phase2/harness/variants_d.py`, and no pipeline file has changed.

The candidate's recipe:

- One 760 W, 4,300 K key from the window side, about 50 degrees off the lens, casting shadows. Weak cool window lights (5,800 K), a 25 W cool fill, a 25 W cool bounce at the screen wall, a 35 W low fill from the camera side, an edge light on the trainer.
- Ceiling panels and downlights at 3,400 K and a few watts, panel emission 2.0, a clean off-white tile grid at half albedo, the exit sign's light at a third.
- White balance 5,000 K in the view settings, so the key reads mildly warm and the fill slightly cool. This replaced a 300 W fill and is what lets the other faces keep some shape.
- Khronos PBR Neutral kept as the transform: at matched face brightness plain AgX washes the skin pale and loses the warm look. A near-neutral grade (contrast 1.03, soft bloom).
- Matte cloth response and 2.5 mm garment thickness, the wall mapping fix, a warm-grey carpet tint, shadow pool 2048 MB.

Measured: front woman's shadow cheek 0.46 of the lit cheek; every other face at least 74% of her brightness; chair backs Y 58 (33 before); whole-frame colour lean U/V 121/133 (the film's light: blue-cyan); darkest tenth 49 at 01:03 and 40 at 01:05; 0.04% clipped; screen legible and unclipped; ceiling at 0.82 of the wall's brightness.

Still wrong: paper and tablet arms read warm cream (Y 161, target 185) and the frame has no bright highlights (brightest tenth 182); the ceiling is a dull taupe and its panels are flat peach blocks; the trainer's white hair is lost against the whiteboard, which is a staging problem that no light fixed; faces other than the front woman's are only mildly modelled; garments are still smooth shells.

What this means for the pipeline:

- Part of a good rig belongs to the room and can live in the set or the kit: no glow floods, weak cool window light, dim warm ceiling fixtures, a low world, a larger shadow pool, shadows on by default.
- The key, the fill and the exposure depend on where the camera and the faces are. They cannot be typed into a set file before the shot is staged, which is where the pipeline puts light today.
- One key models one face. A group needs light designed per view, or a lower target ratio for the group.
- Warmth from light alone tints the whites. Some of it has to come from the grade or a white balance, with a cool source holding the reference.
