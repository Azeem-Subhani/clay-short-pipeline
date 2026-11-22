---
name: asset-library
description: Where the world comes from - surfaces from ambientCG by name, set pieces and props from the kit, the project asset library, BlenderKit through the user's Full plan, or built in Blender - and how an asset is sized, tagged with its period, checked and filed for reuse. Use when a shot needs a surface, prop or set piece the kit does not provide, or when sourcing or making an asset.
---

# Assets: surfaces, props and set pieces

The cast is 2D and comes from the character pack. Everything else is 3D and should look real enough to make the flat characters pop: scanned surfaces, solid shapes, period detail. Every Short should leave the library richer.

## Surfaces (ambientCG, free, CC0)

Sets ask for surfaces by name: `mat.surface("castle_stone")`. The names, their periods and the ambientCG sets behind them are in `library/materials/catalog.json`.

```
python tools/clip.py materials                         # the catalog and what is downloaded
python tools/clip.py materials fetch <clip>            # download what this clip's plan names (1K JPG, 5-20 MB each)
python tools/clip.py materials search half timbered wall     # look for a set on ambientCG
python tools/clip.py materials add plaster_ochre Plaster003 --first    # put a better scan first on a surface's list
```

A surface that is not downloaded renders with a procedural stand-in of the same colour and scale, so nothing breaks; it just looks plainer. To add a new surface, copy an entry in the catalog: `ids` (ambientCG asset ids, best first), `era`, `tile_m` (how many metres one repeat covers), and a `procedural` stand-in.

## Props and set pieces: the order is fixed

**1. The kit.** `stagekit.build` already has walls, towers, doors, trees, ponds, barrels, crates, benches, torches and more (see the `stagekit` skill).

**2. The library.**

```
python tools/clip.py assets find well bucket
python tools/clip.py assets list
```

In a shot or set: `assets.use("set_stone_well", at=(x, y, 0), rot_z=20)`. Each entry carries the periods it belongs to; using one outside the plan's period prints a `WORLD:` note.

**3. BlenderKit** (the user has a Full plan).

```
python tools/clip.py bk-search "medieval market stall" --limit 8    # id, author, licence, faces, size, score
python tools/clip.py bk-fetch <assetBaseId or gallery URL>          # downloads the .blend through the add-on, as the user
python tools/clip.py assets bk-local market stall                   # what the add-on already has on disk
```

These run inside the user's own Blender with the BlenderKit add-on logged in. If they fail (add-on missing, not logged in, service unreachable), do not work around it: go to step 4 and report the search words so the user can click the asset in the add-on later.

Choosing: the right **period** first, then solid readable shapes, under about 80k faces, real-world size. Realistic textured models are welcome now (the world is meant to be rich); avoid ones whose detail is so fine it turns to noise on a phone, and anything with modern fittings in an old world.

File it in one call inside an asset script:

```python
from stagekit import assets
entry = assets.adopt("library/_downloads/blenderkit/<id>/<file>.blend", "set_market_stall", "Market stall", kind="set",
                     tags=["market", "stall", "awning"], era=("medieval", "fairytale"), longest=2.4, saturation=0.9,
                     source_id="<assetBaseId>", author="<author>", license="royalty-free (BlenderKit)")
```

`adopt` = import → `fit` to a real size standing on z = 0 → optional `tone` (pull saturation or tint toward the story palette; it keeps the model's own textures) → `save` with its periods.

**4. Build it.** Write `output/clips/<clip>/assets/<asset_id>.py` (example: `examples/assets/set_stone_well.py`):

```python
from stagekit import build
ASSET = dict(id="set_stone_well", name="Stone well", kind="set", tags=["well", "water"], era=["medieval", "fairytale"],
             notes="1.5 m across; 'well.crank' turns about X, 'well.bucket' moves in Z")

def build_asset():                     # at the world origin, resting on z = 0, front toward -Y
    ...
    return build.group("set_stone_well", parts)
```

```
python tools/clip.py asset output/clips/<clip>/assets/set_stone_well.py --no-save     # preview only, while you iterate
python tools/clip.py asset output/clips/<clip>/assets/set_stone_well.py               # preview + file in the library
```

## The bar

Look at the preview (`library/assets/previews/<id>.png`, or the `.preview.png` next to your script) before you call an asset done.

- **Of the period.** Materials, joinery, fittings. Tag `era` honestly; `["any"]` only for things like rocks and trees.
- **Reads at phone size.** Silhouette first. Thicken thin parts.
- **Real surfaces by name** (`"oak_planks"`, `"iron_dark"`), not flat colours, except for tiny parts.
- **Real scale**, stands on z = 0, front toward −Y. Put the size and how to use it in `notes`.
- **Moving parts are separate children** with clear names, so a shot can animate them.
- **Effort follows the camera:** a hero prop seen in an insert deserves detail; background needs shape and surface only.
- If a downloaded model still looks wrong after one pass, replace it. Do not keep polishing.

## Characters and costume

People come from the pack (`python tools/clip.py cast`). Vary them with the plan's `costume` (`recolor`, `hide`, `wear`). A missing costume piece is a few lines in `tools/blender/stagekit/wardrobe.py` plus an entry in `config/cast.json` with its periods: flat shapes with an outline, drawn in head or torso units so they fit every character. Animals and creatures are not in the pack: build them as simple flat cut-outs (a few planes with flat colour and an outline) or stage around them.

## Licences

Record where everything came from: `source` (`built`, `blenderkit`, `ambientcg`, …), `source_id`, `author`, `license`. ambientCG is CC0. BlenderKit assets are royalty-free or CC0 and may be used in your videos; do not redistribute the library itself.
