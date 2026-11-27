# Fit check: PASS

## Rest pose, unmasked body: pass
- D_Shirt: crossing_body_triangles 0, skin_through_deepest_mm 0.0, min_clearance_mm 2.63, floating_vertices 0, misplaced_vertices 0, floating_worst_extra_mm 0.0
- D_Trousers: crossing_body_triangles 0, skin_through_deepest_mm 0.0, min_clearance_mm 7.01, floating_vertices 0, misplaced_vertices 0, floating_worst_extra_mm 0.0
- D_Shoes: crossing_body_triangles 0, skin_through_deepest_mm 0.0, min_clearance_mm 2.4, floating_vertices 0, misplaced_vertices 0, floating_worst_extra_mm 0.0
- D_Blazer: crossing_body_triangles 0, skin_through_deepest_mm 0.0, min_clearance_mm 2.02, floating_vertices 0, misplaced_vertices 0, floating_worst_extra_mm 0.0

## Skin hidden under clothes: 1708 of 9640 faces (34% of the skin), inset 45 mm from openings

## Poses, masked body: pass
- arms_down: pass
- arms_up: pass
- arms_forward: pass
- stride: pass
- sit: pass
- bend: pass

## Add-on blazer: skinned, built over shirt_trousers; the check above covers the base outfit and the add-on together

## Built by tools/chars_aj/fit.py custom blazer (ajkit.templates), 2026-11-27 05:57
- generated from this body: the fit record is the garment itself, so floating / place / rest stretch / ragged-edge checks compare it with itself; skin, clearance and all pose checks are measured
- params: {}
- build 13.2 s, check 7.2 s
