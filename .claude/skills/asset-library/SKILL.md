---
name: asset-library
description: Where the world comes from - surfaces from ambientCG by name, furniture and architecture from the stagekit kit (furnish, arch), the project asset library, BlenderKit (CC0 or Royalty Free only, licence recorded), or built in Blender - and how an asset is sized, tagged with its period, registered for the set audit, checked and filed for reuse. Use when a shot or set needs a surface, prop or set piece the kit does not provide, or when sourcing or making an asset.
---

# Assets: surfaces, props and set pieces

The cast is 3D (Aj characters, `config/cast.json`). The world around them should be rich enough that a camera can go anywhere: scanned surfaces, solid shapes, period detail, and enough kinds of thing that a wide reads as a lived-in place (the set audit counts them). Every Short should leave the library richer. `PY` is `py -3` on Windows, `python3` elsewhere.

## Surfaces (ambientCG, free, CC0)

Sets ask for surfaces by name: `mat.surface("castle_stone")`. The names, their periods and the ambientCG sets behind them are in `library/materials/catalog.json`.

```
PY tools/clip.py materials                         # the catalog and what is downloaded
PY tools/clip.py materials fetch <clip>            # download what this clip's plan names (1K JPG, 5-20 MB each)
PY tools/clip.py materials search half timbered wall     # look for a set on ambientCG
PY tools/clip.py materials add plaster_ochre Plaster003 --first    # put a better scan first on a surface's list
```

A surface that is not downloaded renders with a procedural stand-in, so nothing breaks, but the set audit warns `stand_in` and the set looks plainer. To add a surface, copy an entry in the catalog: `ids` (ambientCG asset ids, best first), `era`, `tile_m` (metres one repeat covers), and a `procedural` stand-in.

## Furniture, props and set pieces: the order is fixed

**1. The kit.** `stagekit.furnish` has about 140 registered pieces (tables, chairs, beds, shelves, lamps and candles that are real lights, goblets, barrels, signs, notice boards, office and kitchen gear, carts, tents, a horse, a fountain...) each tagged with its periods: `furnish.REGISTRY` lists them, `furnish.make("goblet", at=(x, y, z))` builds one. `stagekit.arch` has rooms, doors, windows, columns, stairs, dais, fireplaces, rugs, house fronts, streets, plazas, stalls, wells, lamp posts, skylines, vistas. `stagekit.build` has the older outdoor kit (trees, ponds, walls, towers). See the `stagekit` skill. Reuse these before anything else: they are sized in metres, grounded, tagged for the audit and made with the project's surfaces.

**2. The library.**

```
PY tools/clip.py assets find well bucket
PY tools/clip.py assets list
```

In a shot or set: `root = assets.use("set_stone_well", at=(x, y, 0), rot_z=20)`, then **`arch.tag(root, "stone_well", kind="prop")`** so the set audit counts it as a prop type (an untagged object is not counted; the audit looks for `sk_type` on the piece or its parent). Each library entry carries the periods it belongs to; using one outside the plan's period prints a `WORLD:` note.

**3. BlenderKit** (the user has a Full plan).

```
PY tools/clip.py bk-search "medieval market stall" --limit 8 [--type model]    # id, author, licence, faces, size, score
PY tools/clip.py bk-fetch <assetBaseId or gallery URL> [...]                    # downloads through the add-on, as the user
PY tools/clip.py assets bk-local market stall                                   # what the add-on already has on disk
```

**Licence rule:** only **CC0** or **Royalty Free** assets are used. `bk-fetch` refuses any other licence before downloading and writes the licence of every download into `library/_downloads/blenderkit/<id>/meta.json`. Never pass a refused asset through another route, and never use a model from anywhere else (CGTrader is excluded). If the add-on is missing, not logged in, or the service is unreachable, do not work around it: go to step 4 and report the search words so the user can click the asset in the add-on later.

Choosing: the right **period** first, then solid readable shapes, under about 80k faces, real-world size. Realistic textured models are welcome (the world is meant to be rich); avoid ones whose detail is so fine it turns to noise on a phone, and anything with modern fittings in an old world.

File it in one call inside an asset script:

```python
from stagekit import assets
entry = assets.adopt("library/_downloads/blenderkit/<id>/<file>.blend", "set_market_stall", "Market stall", kind="set",
                     tags=["market", "stall", "awning"], era=("medieval", "fantasy"), longest=2.4, saturation=0.9,
                     source_id="<assetBaseId>", author="<author>", license="royalty-free (BlenderKit)")
```

`adopt` = import, `fit` to a real size standing on z = 0, optional `tone` (pull saturation or tint toward the story palette; it keeps the model's own textures), `save` with its periods.

**4. Build it.** Write `output/clips/<clip>/assets/<asset_id>.py` (example: `examples/assets/set_stone_well.py`):

```python
from stagekit import arch, build
ASSET = dict(id="set_stone_well", name="Stone well", kind="set", tags=["well", "water"], era=["medieval", "fantasy"],
             notes="1.5 m across; 'well.crank' turns about X, 'well.bucket' moves in Z")

def build_asset():                     # at the world origin, resting on z = 0, front toward -Y
    ...
    root = build.group("set_stone_well", parts)
    arch.tag(root, "stone_well", kind="prop", size=[1.5, 1.5, 2.2])      # registers it for the set audit: sk_type + sk_size [w, d, h] in metres
    return root
```

```
PY tools/clip.py asset output/clips/<clip>/assets/set_stone_well.py --no-save     # preview only, while you iterate
PY tools/clip.py asset output/clips/<clip>/assets/set_stone_well.py               # preview + file in the library
```

A piece that a theme could dress with repeatedly belongs in `stagekit/furnish.py` as a `@piece(...)` (a few lines, drawn with `Parts`; copy a short one such as `stool`), so recipes and the audit know it. That is a toolkit change: ask the producer before editing `stagekit`.

## Hand props

Held things come from the wardrobe registry's `props` (`library/wardrobe/index.json`: `kind` held, worn or perched, `grip`), from the kit, or from the library. A character never has a prop painted into its hand: bring the object on (`assets.use`, `furnish.make`) and give it to the hand with an action (`actor.do("pick_up", prop, ...)`) or `actor.hold(prop, "R", t)`. The grip solver closes the fingers on the real surface when the shape is a **rod or handle** (longer than about 2.6 times its width and thinner than 7 cm: `power` grip) or **small and thin** (under 7 cm and 2.5 cm thick: `pinch`); anything else is carried in the palm. So a prop meant to be held is modelled with a clear handle or as a small flat thing, and its `notes` say its grip type, its length and where to hold it (`offset=`).

## The bar

Look at the preview (`library/assets/previews/<id>.png`, or the `.preview.png` next to your script) before you call an asset done.

- **Of the period.** Materials, joinery, fittings. Tag `era` honestly; `["any"]` only for things like rocks and trees.
- **Reads at phone size.** Silhouette first. Thicken thin parts.
- **Real surfaces by name** (`"oak_planks"`, `"iron_dark"`), not flat colours, except for tiny parts.
- **Real scale in metres**, stands on z = 0 (it will be tested for floating and sinking), front toward -Y, `sk_size` set. Put the size and how to use it in `notes`.
- **Registered:** `sk_type` (what it is) so the audit counts it; `sk_tops` (flat surfaces small props may stand on) if it is a table or shelf; wall pieces declare their mount height and stand on a wall face.
- **Moving parts are separate children** with clear names, so a shot can animate them.
- **Light sources** (lamp, candle, fire) have a real light (`lights.practical`) as well as a glowing part.
- **Effort follows the camera:** a hero prop seen in an insert deserves detail; background needs shape and surface only.
- If a downloaded model still looks wrong after one pass, replace it. Do not keep polishing.

## Characters and costume

People come from the cast registry (`PY tools/clip.py cast`; `library/wardrobe/README.md` says what each body can wear and under which licence). A missing outfit, add-on or hairstyle is a wardrobe task with its own fit check, not an asset: ask for it through `PY tools/clip.py casting <clip>`. Animals and creatures are not in the cast: build them as simple solid shapes or stage around them.

## Licences

Record where everything came from: `source` (`built`, `blenderkit`, `ambientcg`...), `source_id`, `author`, `license`. ambientCG is CC0. BlenderKit assets must be CC0 or Royalty Free and may be used in videos; do not redistribute the library itself.
