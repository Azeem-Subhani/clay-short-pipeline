"""Surfaces from ambientCG (CC0 scanned PBR textures) for the set kit.

    python tools/clip.py materials                       what the catalog lists and which sets are already downloaded
    python tools/clip.py materials fetch                 download the first choice of every catalog surface (1K JPG, about 5-20 MB each)
    python tools/clip.py materials fetch <clip>          only the surfaces that clip's plan names (world.surfaces + sets[].surfaces)
    python tools/clip.py materials fetch castle_stone Bricks094 ...   named surfaces or ambientCG ids
    python tools/clip.py materials search stone wall medieval          look for sets on ambientCG (id, title, tags)
    python tools/clip.py materials add <surface> <AssetId> [--first]   put an id on a catalog surface's list

Files go to library/materials/ambientcg/<AssetId>/ (not committed). stagekit.mat.surface("<name>") uses a downloaded
set when it is there and the procedural stand-in when it is not, so fetching changes how surfaces look, never where
things stand. Uses the ambientCG API v3 (https://docs.ambientcg.com/api/v3/). Standard library only.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, clip_dir, load_env, read_json, write_json  # noqa: E402

LIB = ROOT / "library" / "materials"
CATALOG = LIB / "catalog.json"
API = os.environ.get("AMBIENTCG_API", "https://ambientcg.com/api/v3/assets")
UA = "shorts-pipeline/2.0 (ambientCG API v3 client)"
KEEP = ("_Color", "_NormalGL", "_Roughness", "_Metalness", "_AmbientOcclusion", "_Displacement", "_Opacity")


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def api(**params) -> dict:
    url = API + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    try:
        return json.loads(_get(url).decode("utf-8"))
    except urllib.error.URLError as e:
        raise SystemExit(f"ambientCG is not reachable ({e}). Surfaces keep their procedural stand-ins until a fetch succeeds.")


def search(words: list[str], limit: int = 12) -> list[dict]:
    d = api(type="material", q=",".join(words), sort="popular", limit=limit, include="title,tags,dimensions")
    return d.get("assets", [])


def have(asset_id: str) -> bool:
    d = LIB / "ambientcg" / asset_id
    return d.is_dir() and any(p.stem.endswith("_Color") for p in d.iterdir())


def download(asset_id: str, res: str = "1K", fmt: str = "JPG", force: bool = False) -> Path:
    """Fetch one texture set and unpack its maps. Returns the folder."""
    out = LIB / "ambientcg" / asset_id
    if have(asset_id) and not force:
        return out
    d = api(id=asset_id, include="downloads,title,tags,dimensions")
    assets = d.get("assets") or []
    if not assets:
        raise SystemExit(f"ambientCG has no asset '{asset_id}' (ids are case-sensitive, e.g. Bricks100)")
    a = assets[0]
    want = f"{res}-{fmt}"
    dl = next((x for x in a.get("downloads", []) if x.get("attributes") == want and x.get("extension") == "zip"), None)
    if dl is None:
        opts = sorted({x.get("attributes") for x in a.get("downloads", []) if x.get("extension") == "zip"})
        raise SystemExit(f"{asset_id} has no {want} download. It has: {', '.join(o for o in opts if o)}")
    print(f"  {asset_id}: downloading {want} ({dl.get('size', 0) / 1e6:.1f} MB)")
    blob = _get(dl["url"], timeout=300)
    out.mkdir(parents=True, exist_ok=True)
    root = out.resolve()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for m in z.infolist():
            name = Path(m.filename).name
            stem = Path(name).stem
            if m.is_dir() or not any(stem.endswith(k) for k in KEEP) or Path(name).suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            target = (root / name).resolve()
            if not target.is_relative_to(root):
                continue
            target.write_bytes(z.read(m))
    write_json(out / "source.json", {"id": asset_id, "title": a.get("title"), "tags": a.get("tags"), "dimensions_cm": a.get("dimensions"),
                                    "resolution": res, "format": fmt, "url": dl["url"], "licence": "CC0 1.0 Universal", "source": "ambientCG.com"})
    if not have(asset_id):
        raise SystemExit(f"{asset_id}: the archive held no colour map")
    return out


def plan_surfaces(clip: Path) -> list[str]:
    plan = read_json(clip / "shotplan.json")
    names = list((plan.get("world") or {}).get("surfaces", []))
    for s in plan.get("sets", []):
        names += s.get("surfaces", [])
    return list(dict.fromkeys(names))


def cmd_list(_a):
    cat = read_json(CATALOG)["surfaces"]
    got = 0
    for name, e in cat.items():
        ids = e.get("ambientcg", [])
        here = [i for i in ids if have(i)]
        got += bool(here)
        state = f"scanned: {here[0]}" if here else (f"stand-in (wants {ids[0]})" if ids else f"stand-in (no id yet; query: {e.get('query') or '-'})")
        print(f"  {name:<16} {state:<34} {e['what']}")
    print(f"{len(cat)} surfaces, {got} with scanned textures in {LIB / 'ambientcg'}")
    return 0


def cmd_search(a):
    hits = search(a.words, a.limit)
    for h in hits:
        dim = h.get("dimensions")
        print(f"  {h['id']:<20} {h.get('title', ''):<24} {dim if dim else ''}  {', '.join((h.get('tags') or [])[:10])}")
    print(f"{len(hits)} result(s). Preview: https://ambientcg.com/view?id=<id>   Add one: python tools/clip.py materials add <surface> <id>")
    return 0


def cmd_add(a):
    cat = read_json(CATALOG)
    if a.surface not in cat["surfaces"]:
        raise SystemExit(f"no surface '{a.surface}' in the catalog: add an entry to {CATALOG.relative_to(ROOT)} first")
    ids = [i for i in cat["surfaces"][a.surface].get("ambientcg", []) if i != a.asset_id]
    cat["surfaces"][a.surface]["ambientcg"] = [a.asset_id, *ids] if a.first else [*ids, a.asset_id]
    write_json(CATALOG, cat)
    print(f"{a.surface}: {cat['surfaces'][a.surface]['ambientcg']}")
    return 0


def cmd_fetch(a):
    load_env()
    cat = read_json(CATALOG)
    surfaces = cat["surfaces"]
    names: list[str] = []
    for w in a.what:
        if w in surfaces or w[:1].isupper():
            names.append(w)
        else:
            names += plan_surfaces(clip_dir(w))
    if not a.what:
        names = list(surfaces)
    changed, failed = False, []
    for n in dict.fromkeys(names):
        if n not in surfaces:                                  # a raw ambientCG id
            download(n, a.res, a.format, a.force)
            continue
        e = surfaces[n]
        ids = e.get("ambientcg", [])
        if not ids and e.get("query"):
            hits = search([w for w in e["query"].split(",") if w], 5)
            if hits:
                ids = [hits[0]["id"]]
                e["ambientcg"] = ids
                changed = True
                print(f"  {n}: no id in the catalog; the query '{e['query']}' gives {ids[0]} ({hits[0].get('title')}). Check it: https://ambientcg.com/view?id={ids[0]}")
        if not ids:
            print(f"  {n}: procedural only (no scanned set fits or none was found)")
            continue
        if any(have(i) for i in ids) and not a.force:
            print(f"  {n}: already have {next(i for i in ids if have(i))}")
            continue
        try:
            download(ids[0], a.res, a.format, a.force)
        except SystemExit as ex:
            failed.append(f"{n}: {ex}")
            print(f"  {n}: FAILED - {ex}")
    if changed:
        write_json(CATALOG, cat)
    if failed:
        print(f"{len(failed)} surface(s) kept their procedural stand-in")
    return 1 if failed and not a.keep_going else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clip.py materials")
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser("fetch")
    f.add_argument("what", nargs="*", help="a clip, catalog surface names, or ambientCG ids; nothing = the whole catalog")
    f.add_argument("--res", default="1K", choices=("1K", "2K", "4K"))
    f.add_argument("--format", default="JPG", choices=("JPG", "PNG"))
    f.add_argument("--force", action="store_true")
    f.add_argument("--keep-going", action="store_true")
    s = sub.add_parser("search")
    s.add_argument("words", nargs="+")
    s.add_argument("--limit", type=int, default=12)
    ad = sub.add_parser("add")
    ad.add_argument("surface")
    ad.add_argument("asset_id")
    ad.add_argument("--first", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    return {"fetch": cmd_fetch, "search": cmd_search, "add": cmd_add, "list": cmd_list, None: cmd_list}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
