---
name: character-maker
description: How to add a new character to the 3D cast when a story needs someone the lineup does not have - deciding between reuse, re-costume and a new sheet; writing the sheet in config/cast3d_custom.json (which character it is like, what differs, flat front drawings for new clothes, hair and hats); looking at it, testing its actions, and registering it with honest era tags. Use when a shot plan needs a character that no existing character or wardrobe piece can play.
---

# character-maker: a new 3D character in minutes

Full reference with every key and every way a flat drawing becomes 3D: `docs/CHARACTERS_3D.md`. This page is the short form.
New actions for a character: `docs/ADDING_NEW_ACTIONS.md`.

A 3D character is a **sheet**: a JSON entry. There is no build step and no library file. Converted pack characters live
in `config/cast3d.json` (do not edit: it is regenerated); characters made here live in `config/cast3d_custom.json`.

## 1. Decide (the director does this, in this order)

1. **Reuse.** `python tools/clip.py cast --era <era>`; `cast <Name>` shows `stand_in` (who can replace whom) and whether the figure is 3D.
2. **Re-costume in the plan.** Same body, other clothes: the plan's `costume` (`recolor`, `hide`, `wear`). Wardrobe: `straw_hat`, `beret`, `ruff`, `hood`, `kerchief`, `top_hat`, `crown`, `flat_cap`, `bonnet`, `tricorn`, `bowler`, `apron`, `sash`, `cloak`, `buttons`, `fur_trim`, `freckles` (an older list: the wardrobe that fits the Aj bodies today is in `library/wardrobe/README.md`, and `py -3 tools/clip.py cast` lists who exists).
3. **A new sheet** only when the role recurs or the costume dict would be long. Write `"why_new"` on the plan's cast entry. A figure seen for two seconds in a wide view never justifies one.
4. **A special body** (ghost, mermaid, dragon, fairy, robot, alien, werewolf, mummy, genie, goblin, monster, devil, skeleton) is NOT in the 3D cast. Ask the user before casting one: it is a flat 2D character from the old pack and the camera must stay in front of it.

## 2. Write the sheet

In `config/cast3d_custom.json > characters`. Say who it is like and give only what differs:

```json
"TownGuard": {
  "like": "Soldier", "label": "Town Guard", "group": "custom",
  "looks": "the Soldier re-dressed as a town watchman: dark green tunic, black belt, a short cloak, a short brown beard",
  "era": ["medieval", "renaissance", "fantasy"], "stand_in": ["Soldier"],
  "recolor": {"soldier_blue": "#3F5A3A", "pants_soldier": "#3A342C"},
  "wear": [{"item": "cloak", "color": "#5A2F2A"}],
  "beard": {"style": "short", "color": "#6B4428"}
}
```

| Key | Use |
|---|---|
| `like` | the nearest existing character: its body, face and costume are the start |
| `colors` | body colours by role: `skin, torso, sleeve_u, sleeve_l, hand, leg_u, leg_l, shoe` |
| `recolor` | costume parts by the pack's colour name (`clip.py cast <like>` lists them) |
| `hide` | part-name patterns to leave off (`"*"` strips the whole costume) |
| `wear` | wardrobe pieces that belong to the character |
| `add` | new clothes, hair, hats as flat front drawings: `{"name", "on": "head" \| "torso" \| "arm_lower.L" ..., "units": "head" \| "torso", "layer", "color", "pts": [[x, z], ...]}` |
| `hair` | sculpted hair: `{"style": "short" \| "side_part" \| "swept_back" \| "curtains" \| "bob" \| "fringe_bob" \| "long" \| "long_fringe" \| "ring" \| "back_only", "color": "#..."}` plus optional `part, fringe, side, back, vol` |
| `beard` | sculpted beard: `{"style": "stubble" \| "short" \| "full" \| "long" \| "goatee" \| "moustache", "color": "#..."}` |
| `body`, `face` | proportions and face placement to change |

Drawing rules (the builder does the rest): head units are head radii from the head centre (top of the head z = 1);
torso units are u -1..1 across, v 0 at the hip to 1 at the shoulders. A centred wide outline at hat height (`layer` 22+)
is spun into a hat. An outline named `Hair...` grows a hair cap with that hairline. On the body, an outline as wide as
the body becomes a belt (short) or a closed garment (tall); a small one named button / badge / buckle becomes a stud;
anything else is laid on the surface. `"as"` forces one: `decal, band, panel, stud, lathe, peak, hair, blob, cape, crown, collar_fur, limb`.

Keep the house style: round head, simple shapes, one idea per character. Give honest `era` tags.

## 3. Look, test, register

```
blender -b --factory-startup --python tools/chars3d/look3d.py -- --char TownGuard --out <abs path>/look.png
blender -b --factory-startup --python tools/chars3d/action_test3d.py -- --char TownGuard --out <abs dir> --set core
python tools/cast_registry.py check
```

- **Look** at the sheet (front, three-quarter, side, back; happy, surprised, angry, grin). Fix the JSON and look again.
  Check from the back and the side too: the camera will go there.
- **Test**: `--set core` is twelve actions, `--set all` all 118. Every line must say PASS.
- **Register**: add the character to `config/cast.json > characters` (`looks`, `era`, `group`, `stand_in`, `props`,
  `height_m`, `robe`, `colors`, `parts`) so `plan-check` accepts it, then run the registry check.

Signature props are filed as before: `library/assets/` with period tags, size, source and licence (`asset-library` skill).

## The old 2D pack

`docs/CREATING_NEW_CHARACTERS.md` and `tools/chars/` are for the flat pack only. Do not add characters there.
