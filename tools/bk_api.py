"""bk_api.py - search and download BlenderKit assets straight from the BlenderKit web API. Standard library only.

    python tools/bk_api.py search "pirate hat" [--type model|material|hdr] [--limit 8] [--free]
    python tools/bk_api.py fetch <asset base id> [--file gltf|blend|resolution_1K|...]     (the "base" field of a search result)

For machines without the add-on (a server, a cloud session). tools/blender/bk_fetch.py does the same through the add-on
on your own computer. Downloads need your account's API key in BLENDERKIT_API_KEY (BlenderKit profile > API key); where
a network proxy adds the key by itself, set it to any placeholder. Files land in library/_downloads/blenderkit/<id>/
with a meta.json (name, author, licence, URL), the same place and shape bk_fetch.py uses, so the asset can be filed
with its source and licence.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

PROJECT = Path(os.environ.get("SHORTS_PROJECT") or Path(__file__).resolve().parents[1])
API = "https://www.blenderkit.com/api/v1"


def _get(url):
    h = {"accept": "application/json", "Platform-Version": sys.platform, "addon-version": "3.12.0"}
    key = os.environ.get("BLENDERKIT_API_KEY", "").strip()
    if key:
        h["Authorization"] = f"Bearer {key}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
        return r.read()


def search(words, kind="model", limit=8, free=False):
    q = f"{words} asset_type:{kind}" + (" is_free:true" if free else "")
    d = json.loads(_get(f"{API}/search/?query={urllib.parse.quote_plus(q)}&page_size={limit}"))
    return [dict(id=r["id"], base=r.get("assetBaseId"), name=r["name"], type=r["assetType"], free=bool(r.get("isFree")), licence=r.get("license"),
                 author=(r.get("author") or {}).get("fullName"), files=[f["fileType"] for f in r.get("files", [])],
                 thumb=r.get("thumbnailMiddleUrl") or r.get("thumbnailSmallUrl"), url=f"https://www.blenderkit.com/asset-gallery-detail/{r['id']}/",
                 faces=(r.get("dictParameters") or {}).get("faceCount"), _files=r.get("files", [])) for r in d.get("results", [])]


def fetch(asset_id, want=None):
    """asset_id: the asset's BASE id (the "base" field of a search result; it stays the same across versions)"""
    res = json.loads(_get(f"{API}/search/?query={urllib.parse.quote_plus('asset_base_id:' + asset_id)}")).get("results")
    if not res:
        raise SystemExit(f"no BlenderKit asset with base id {asset_id} (use the \"base\" field of a search result)")
    r = res[0]
    files = {f["fileType"]: f for f in r.get("files", [])}
    order = [want] if want else (["gltf", "blend"] if r["assetType"] == "model" else ["resolution_1K", "resolution_2K", "blend"])
    ft = next((k for k in order if k in files), None)
    if ft is None:
        raise SystemExit(f"{r['name']}: no file of kind {order}; it has {sorted(files)}")
    info = json.loads(_get(files[ft]["downloadUrl"] + "?scene_uuid=" + str(uuid.uuid4())))
    out = PROJECT / "library" / "_downloads" / "blenderkit" / (r.get("assetBaseId") or r["id"])
    out.mkdir(parents=True, exist_ok=True)
    name = urllib.parse.urlparse(info["filePath"]).path.rsplit("/", 1)[-1]
    data = None
    for u in [info["filePath"]] + [p["url"] for p in info.get("filePaths", [])]:
        try:
            data = _get_plain(u)
            break
        except Exception as ex:                              # the same file is offered on more than one host
            err = ex
    if data is None:
        raise SystemExit(f"download failed: {err}")
    (out / name).write_bytes(data)
    meta = dict(id=r["id"], assetBaseId=r.get("assetBaseId"), name=r["name"], type=r["assetType"], author=(r.get("author") or {}).get("fullName"),
                licence=r.get("license"), free=bool(r.get("isFree")), url=f"https://www.blenderkit.com/asset-gallery-detail/{r['id']}/", file=name, fileType=ft)
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return dict(meta, path=str(out / name), bytes=len(data))


def _get_plain(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "shorts-pipeline"}), timeout=300) as r:
        return r.read()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("words")
    s.add_argument("--type", default="model")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--free", action="store_true")
    s.add_argument("--thumbs", default="", help="a folder to save the thumbnails in")
    f = sub.add_parser("fetch")
    f.add_argument("id")
    f.add_argument("--file", default=None)
    a = ap.parse_args()
    if a.cmd == "search":
        for i, r in enumerate(search(a.words, a.type, a.limit, a.free)):
            fl = r.pop("_files")
            print(json.dumps(r))
            if a.thumbs and r["thumb"]:
                Path(a.thumbs).mkdir(parents=True, exist_ok=True)
                try:
                    (Path(a.thumbs) / f"{i:02d}_{r['id'][:8]}.jpg").write_bytes(_get_plain(r["thumb"]))
                except Exception as ex:
                    print("  thumbnail not saved:", ex)
    else:
        print("BK_RESULT " + json.dumps(fetch(a.id, a.file)))
