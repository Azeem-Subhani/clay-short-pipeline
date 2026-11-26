"""import_fits - the pack's accepted outfit fits as the project's wardrobe files.

    blender -b --factory-startup --python tools/chars_aj/import_fits.py -- [--outfit jeans_shirt] [--body Male_Teen] [--dry]

For every outfit fit in library/wardrobe/index.json that passed the fit check AND was accepted by review and still
points into the pack (packs/aj_rebuild_v1/04_Outfit_Fits/...): open the pack file (read only: it is never saved),
keep the armature, the body (with its HideUnderClothes mask) and the outfit's garments, drop the fit-check stage
(reference copies, lights, camera, floor), shrink every image over 2048 px to 2048 px, pack the images, and save
library/wardrobe/fits/<Sex>_<Age>/<outfit>.blend. Then the registry's `file` field is pointed at the new file.
Hair is not in these files: it is mounted separately (ajkit.hairkit).

The contract with the garment agent (tools/chars_aj/fit.py): one complete file per body and outfit holding that body's
armature, the body mesh and the garments skinned to the armature: a dressed body without hair.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import bpy

PROJECT = Path(os.environ.get("SHORTS_PROJECT") or Path(__file__).resolve().parents[2])
INDEX = PROJECT / "library" / "wardrobe" / "index.json"
FITS = PROJECT / "library" / "wardrobe" / "fits"
MAXPX = 2048
BODY, ARM = "Aj_Base_Body", "Armature"


def _read_index() -> tuple[dict, str]:
    raw = INDEX.read_bytes().decode("utf-8")
    return json.loads(raw), ("\r\n" if "\r\n" in raw else "\n")


def _write_index(idx: dict, eol: str):
    text = json.dumps(idx, indent=1, ensure_ascii=False)
    INDEX.write_bytes(text.replace("\n", eol).encode("utf-8"))


def _prune(keep_names: set[str]):
    for o in list(bpy.data.objects):
        if o.name not in keep_names:
            bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        if not c.objects and not c.children:
            bpy.data.collections.remove(c)
    for _ in range(3):                    # recursive: a removed material frees its images
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)


def _shrink() -> list[list]:
    """Every image larger than MAXPX on a side goes to MAXPX (aspect kept), then is packed again."""
    done = []
    for im in bpy.data.images:
        if im.type != "IMAGE" or im.source == "VIEWER" or im.size[0] == 0:
            continue
        w, h = im.size
        if max(w, h) > MAXPX:
            k = MAXPX / max(w, h)
            nw, nh = max(1, round(w * k)), max(1, round(h * k))
            im.scale(nw, nh)
            done.append([im.name, [w, h], [nw, nh]])
        if im.packed_file is None or max(w, h) > MAXPX:
            im.pack()
    return done


def one(outfit: str, body_id: str, fit: dict, pieces: dict) -> dict:
    src = PROJECT / (fit.get("pack_file") or fit["file"])
    out = FITS / body_id / f"{outfit}.blend"
    before = src.stat().st_size
    bpy.ops.wm.open_mainfile(filepath=str(src))
    names = {ARM, BODY, *pieces}
    missing = [n for n in names if n not in bpy.data.objects]
    if missing:
        raise SystemExit(f"{src.name}: no object {missing}")
    _prune(names)
    arm = bpy.data.objects[ARM]
    arm.animation_data_clear()
    for o in bpy.data.objects:
        o.select_set(False)
    coll = bpy.data.collections.new(f"Fit_{outfit}")
    bpy.context.scene.collection.children.link(coll)
    for o in bpy.data.objects:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    for c in list(bpy.data.collections):
        if c is not coll and not c.objects and not c.children:
            bpy.data.collections.remove(c)
    shrunk = _shrink()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True, copy=True)
    px = sum(i.size[0] * i.size[1] for i in bpy.data.images if i.size[0])
    rec = {"outfit": outfit, "body": body_id, "bytes_before": before, "bytes_after": out.stat().st_size, "images": len(bpy.data.images),
           "pixels_after": px, "shrunk": len(shrunk), "file": str(out.relative_to(PROJECT)).replace("\\", "/")}
    return rec


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--outfit")
    ap.add_argument("--body")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    idx, eol = _read_index()
    jobs = []
    for oid, o in idx["outfits"].items():
        if a.outfit and oid != a.outfit:
            continue
        for body_id, fit in (o.get("fits") or {}).items():
            if a.body and body_id != a.body:
                continue
            f = fit.get("pack_file") or fit.get("file") or ""
            if fit.get("status") == "pass" and fit.get("review") == "accept" and f.startswith("packs/"):
                jobs.append((oid, body_id, fit, o["pieces"]))
    print(f"{len(jobs)} fit(s) to import")
    results = []
    for oid, body_id, fit, pieces in jobs:
        if a.dry:
            print("  would import", oid, body_id, fit["file"])
            continue
        rec = one(oid, body_id, fit, pieces)
        results.append(rec)
        print(f"  {oid:<12} {body_id:<14} {rec['bytes_before'] / 1e6:7.1f} MB -> {rec['bytes_after'] / 1e6:6.1f} MB   "
              f"{rec['images']} images, {rec['pixels_after'] / 1e6:.0f} Mpx, {rec['shrunk']} shrunk", flush=True)
    if results:
        idx, eol = _read_index()                           # read again just before writing: other agents edit this file
        for r in results:
            fit = idx["outfits"][r["outfit"]]["fits"][r["body"]]
            fit.setdefault("pack_file", fit["file"])
            fit["file"] = r["file"]
        _write_index(idx, eol)
        print(f"registry updated: {len(results)} file field(s)")
        tb, ta = sum(r["bytes_before"] for r in results), sum(r["bytes_after"] for r in results)
        print(f"total {tb / 1e6:.0f} MB -> {ta / 1e6:.0f} MB")
    print(json.dumps({"imported": results}))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
