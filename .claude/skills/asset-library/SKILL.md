---
name: asset-library
description: Where sets, props and extra characters come from - the project asset library first, then BlenderKit through the user's paid plan, then built in Blender - and how an asset is restyled to clay, checked and filed for reuse. Use when a shot needs something the set builders do not provide, or when sourcing or making an asset.
---

# Asset library

Every Short should leave the library richer. An asset is one `.blend` in `library/assets/<kind>s/` plus an entry in `library/assets/index.json` (id, tags, size, source, licence, preview).

## The order is fixed

**1. Library.**

```
python tools/clip.py assets find wire cutters
python tools/clip.py assets list
```

In a shot: `assets.use("prop_wire_cutters", at=(x, y, z), rot_z=0, scale=1.0)`. If something close exists, use it; recolour or scale rather than making a near-duplicate.

**2. BlenderKit** (the user has a paid Full plan).

```
python tools/clip.py bk-search "police car low poly" --limit 8      # lists id, author, licence, faces, size, score
python tools/clip.py bk-fetch <assetBaseId or gallery URL>          # downloads the .blend through the add-on, as the user
python tools/clip.py assets bk-local police car                     # what the add-on already has on disk
```

These run inside the user's own Blender with the BlenderKit add-on logged in. If they fail (add-on not installed, not logged in, service unreachable), do not work around it: fall through to step 3 and note it in your report, with the search words, so the user can click the asset in the add-on later.

Choosing: prefer **simple, chunky, stylised** models with clean shapes over realistic ones; under ~50k faces; real-world size. Realistic photo-textured assets rarely survive the clay restyle well: fine detail turns to noise at phone size.

Then restyle, size and file it in one call inside an asset script:

```python
from stagekit import assets
entry = assets.adopt("library/_downloads/blenderkit/<id>/<file>.blend", "vehicle_police_car", "Police car", kind="vehicle",
                     tags=["police", "car"], height=1.55, recolor={"body": "#E9E6DF", "glass": "#1B2233"}, keep=("emission", "light"),
                     source_id="<assetBaseId>", author="<author>", license="royalty-free (BlenderKit)")
```

`adopt` = `import_blend` → `fit` (scale to a real size, stand on z = 0) → `clayify` (flat palette colours, clay surface, bevels) → `save`.

**3. Build it.** Write `output/clips/<clip>/assets/<asset_id>.py`:

```python
from stagekit import build
ASSET = dict(id="prop_door_key", name="Old door key", kind="prop", tags=["key", "door", "lock"], notes="0.09 m long; rotate about Y to turn it")

def build_asset():                     # at the world origin, resting on z = 0, front toward -Y
    ...
    return build.group("prop_door_key", parts)
```

```
python tools/clip.py asset output/clips/<clip>/assets/prop_door_key.py --no-save     # preview only, while you iterate
python tools/clip.py asset output/clips/<clip>/assets/prop_door_key.py               # preview + file in the library
```

Examples of built assets: `examples/assets/*.py` (wire cutters, door key, police car, school bag).

## The bar

Look at the preview (`library/assets/previews/<id>.png`, or the `.preview.png` next to your script) before you call an asset done.

- **Reads at phone size.** Silhouette first. Thicken thin parts; drop tiny detail.
- **Clay.** Rounded, bevelled, matte, palette colours. No photo textures, no mirror metal, no razor edges.
- **Real scale**, stands on z = 0, front toward −Y. Put the size and how to use it in `notes`.
- **Effort follows the camera.** `closest: hero` (seen close) deserves the detail; `background` needs shape and colour only.
- **Glows** (`build.glow`) for anything that is a light: screens, bulbs, sirens, lit windows.
- If a base model still looks cheap after one restyle, replace it. Do not keep polishing.

## Characters

People come from the character pack through `stagekit.cast` (six presets, three bases, hairs, beards, skin tones, outfits, hats): see `packs/release_1/docs/CHARACTERS.md` and `API.md`. Vary them with the plan's `cast[].spec` before asking for anything new. Only non-human or special characters (a dog, a robot, a ghost) are assets: build them simple and rigid, give them one or two moving parts as child objects the shot can rotate (head, tail), and file them as `kind="creature"` or `"character"`.

## Licences

Record where everything came from: `source` (`built`, `blenderkit`, `polyhaven`, …), `source_id`, `author`, `license`. BlenderKit assets are royalty-free or CC0 and may be used in your videos; do not redistribute the library itself.
