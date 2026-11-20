"""Search and download BlenderKit assets headlessly, through the official add-on and YOUR logged-in account.

    python tools/clip.py bk-search "wire cutters" [--type model] [--limit 8]
    python tools/clip.py bk-fetch <assetBaseId or gallery URL> [...]

This runs inside your normal Blender (not --factory-startup), so it sees the BlenderKit add-on you installed and the
account you logged in with. It only calls the add-on's own functions: the same search endpoint the asset bar uses and the
add-on Client's blocking download route that the add-on ships for background scripts. Nothing is scraped and no login
is automated: log in once in the add-on UI, then this works.

Downloads land in library/_downloads/blenderkit/<assetBaseId>/ with a meta.json (name, author, licence, URL) so
stagekit.assets.adopt() can file the asset with its source.

STATUS: written against add-on 3.21.7 (source read on 2026-11-21). It could not be run against the live service from the
build sandbox. If a step fails, the message says which; the fallback always works: click download in the add-on,
then `python tools/clip.py bk-local "<words>"` lists what the add-on has on disk.
"""
import argparse
import importlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import bpy

PROJECT = Path(os.environ.get("CLAY_PROJECT", Path(__file__).resolve().parents[2]))


def fail(msg, code=2):
    print("BK_RESULT " + json.dumps({"ok": False, "error": msg}))
    sys.exit(code)


def addon():
    for key in bpy.context.preferences.addons.keys():
        if key.split(".")[-1].lower() in ("blenderkit", "blendkit"):
            try:
                return importlib.import_module(key), key
            except Exception as e:  # noqa: BLE001
                fail(f"BlenderKit add-on '{key}' is enabled but could not be imported: {e}")
    fail("BlenderKit add-on is not enabled in this Blender. Install it from blenderkit.com/get-blenderkit, enable it, log in once, "
         "then run again. (This command must not use --factory-startup.)")


def api_key(key):
    k = getattr(bpy.context.preferences.addons[key].preferences, "api_key", "")
    if not k:
        fail("BlenderKit add-on has no API key: open Blender, log in from the BlenderKit panel once, then run again.")
    return k


def ensure_client(bk, timeout=45.0):
    """The add-on talks to its own local Client process; in the UI a timer starts it. Headless, start it ourselves."""
    t0 = time.time()
    started = False
    while time.time() - t0 < timeout:
        try:
            bk.client_lib.get_reports(os.getpid())
            return
        except Exception:  # noqa: BLE001
            if not started:
                try:
                    bk.client_lib.start_blenderkit_client()
                except Exception as e:  # noqa: BLE001
                    fail(f"could not start the BlenderKit Client: {e}")
                started = True
            time.sleep(1.0)
    fail("BlenderKit Client did not answer in time (see the add-on's Client log in Preferences > Add-ons > BlenderKit)")


def search(bk, key, query, asset_type="model", limit=8, free_only=False):
    import requests
    q = {"query": query, "asset_type": asset_type}
    if free_only:
        q["is_free"] = True
    av = bk.global_vars.VERSION
    url = bk.search.query_to_url(q, f"{av[0]}.{av[1]}.{av[2]}.{av[3]}", "%d.%d.%d" % bpy.app.version, "", page_size=limit)
    r = requests.get(url, headers=bk.utils.get_headers(api_key(key)), timeout=30)
    if r.status_code != 200:
        fail(f"BlenderKit search returned HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("results", [])


def brief(r, bk):
    p = r.get("dictParameters") or {}
    return {
        "assetBaseId": r.get("assetBaseId"), "id": r.get("id"), "name": r.get("name"), "type": r.get("assetType"),
        "author": (r.get("author") or {}).get("fullName", ""), "license": r.get("license"), "free": r.get("isFree"),
        "can_download": r.get("canDownload"), "score": r.get("score"), "quality": r.get("ratingsAverage", {}).get("quality") if isinstance(r.get("ratingsAverage"), dict) else None,
        "faces": p.get("faceCount"), "size_m": [p.get("dimensionX"), p.get("dimensionY"), p.get("dimensionZ")],
        "texture_px": p.get("textureResolutionMax"), "style": p.get("modelStyle"),
        "url": f"{bk.global_vars.SERVER}/asset-gallery-detail/{r.get('id')}/",
        "description": (r.get("description") or "")[:160],
    }


def fetch(bk, key, ident):
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", ident)
    if not m:
        fail(f"'{ident}' is not an assetBaseId or a BlenderKit gallery URL")
    aid = m.group(1)
    res = search(bk, key, f"asset_base_id:{aid}", asset_type="model,scene,material", limit=1)
    if not res:
        res = [r for r in search(bk, key, f"asset_id:{aid}", asset_type="model,scene,material", limit=1)]
    if not res:
        fail(f"no BlenderKit asset with id {aid}")
    r = res[0]
    try:
        asset = bk.search.parse_result(dict(r)) or r
    except Exception:  # noqa: BLE001
        asset = r
    ensure_client(bk)
    k = api_key(key)
    can, url, filename = bk.client_lib.get_download_url(asset, str(uuid.uuid4()), k)
    if not can or not url:
        fail(f"'{r.get('name')}' cannot be downloaded with this account (plan or permissions). canDownload={r.get('canDownload')}")
    out_dir = PROJECT / "library" / "_downloads" / "blenderkit" / r["assetBaseId"]
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / (filename or f"{r['assetBaseId']}.blend")
    if not dst.exists() or dst.stat().st_size == 0:
        resp = bk.client_lib.blocking_file_download(url, str(dst), k)
        if getattr(resp, "status_code", 200) != 200 or not dst.exists():
            fail(f"download failed for '{r.get('name')}' (HTTP {getattr(resp, 'status_code', '?')})")
    meta = brief(r, bk) | {"blend": str(dst), "downloaded": time.strftime("%Y-%m-%d")}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="bk_fetch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--type", default="model")
    s.add_argument("--limit", type=int, default=8)
    f = sub.add_parser("fetch")
    f.add_argument("ids", nargs="+")
    a = ap.parse_args(argv)
    bk, key = addon()
    if a.cmd == "search":
        res = search(bk, key, a.query, a.type, a.limit)
        print("BK_RESULT " + json.dumps({"ok": True, "results": [brief(r, bk) for r in res]}))
    else:
        print("BK_RESULT " + json.dumps({"ok": True, "assets": [fetch(bk, key, i) for i in a.ids]}))


if __name__ == "__main__":
    main()
