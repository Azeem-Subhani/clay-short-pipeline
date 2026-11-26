"""Search and download BlenderKit assets headlessly, through the official add-on and YOUR logged-in account.

    python tools/clip.py bk-search "wire cutters" [--type model] [--limit 8]
    python tools/clip.py bk-fetch <assetBaseId or gallery URL> [...]

This runs inside your normal Blender (not --factory-startup), so it sees the BlenderKit add-on you installed and the
account you logged in with. It only calls the add-on's own functions: the same search endpoint the asset bar uses and the
add-on Client's blocking download route that the add-on ships for background scripts. Nothing is scraped and no login
is automated: log in once in the add-on UI, then this works.

Downloads land in library/_downloads/blenderkit/<assetBaseId>/ with a meta.json (name, author, licence, URL) so
stagekit.assets.adopt() can file the asset with its source.

Only assets under a licence we may use are downloaded: CC0 ("cc_zero") or Royalty Free ("royalty_free"). Anything else is refused before
the download starts, and the licence of every download is written into its meta.json.

The add-on's own calls time out after 1 s (fine for the UI, which retries; too short here). This script raises those timeouts, retries the
download address and the download a few times with a growing pause, and in a batch `fetch` carries on past an id that failed and lists the
failures at the end (exit code 1 if any failed).

STATUS: written against add-on 3.21.7. If a step still fails, the message says which; the fallback always works: click download in the
add-on, then `python tools/clip.py bk-local "<words>"` lists what the add-on has on disk.
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

for _stream in (sys.stdout, sys.stderr):                       # a Windows console is cp1252 by default: never die on a name or message
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ALLOWED_LICENCES = {"cc_zero": "CC0", "royalty_free": "Royalty Free"}      # BlenderKit's licence ids; nothing else may be used
URL_TIMEOUT = (10.0, 60.0)                                     # (connect, read) seconds for the add-on Client's "give me the download address"
DOWNLOAD_TIMEOUT = (10.0, 900.0)
URL_TRIES = 6
DOWNLOAD_TRIES = 3

PROJECT = Path(os.environ.get("SHORTS_PROJECT") or os.environ.get("CLAY_PROJECT") or Path(__file__).resolve().parents[2])


class FetchError(Exception):
    """One asset could not be fetched (a batch goes on with the next id)."""


def say(text: str):
    """A line of progress, plain ASCII with no emoji, flushed so a long download shows life."""
    print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def fail(msg, code=2):
    print("BK_RESULT " + json.dumps({"ok": False, "error": msg}))
    sys.exit(code)


def pause(attempt: int, base: float = 2.0, cap: float = 30.0) -> float:
    """Back-off before try number attempt+1: 2, 4, 8, 16, 30 s."""
    return min(cap, base * (2 ** attempt))


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
    url = bk.search.query_to_url(q, f"{av[0]}.{av[1]}.{av[2]}", "%d.%d.%d" % bpy.app.version, "", page_size=limit)
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=bk.utils.get_headers(api_key(key)), timeout=30)
            if r.status_code == 200:
                return r.json().get("results", [])
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code < 500 and r.status_code != 429:
                break
        except requests.RequestException as e:
            last = str(e)
        time.sleep(pause(attempt))
    raise FetchError(f"BlenderKit search failed ({last})")


def brief(r, bk):
    p = r.get("dictParameters") or {}
    return {
        "assetBaseId": r.get("assetBaseId"), "id": r.get("id"), "name": r.get("name"), "type": r.get("assetType"),
        "author": (r.get("author") or {}).get("fullName", ""), "license": r.get("license"), "license_name": ALLOWED_LICENCES.get(r.get("license"), r.get("license")),
        "usable": r.get("license") in ALLOWED_LICENCES, "free": r.get("isFree"),
        "can_download": r.get("canDownload"), "score": r.get("score"), "quality": r.get("ratingsAverage", {}).get("quality") if isinstance(r.get("ratingsAverage"), dict) else None,
        "faces": p.get("faceCount"), "size_m": [p.get("dimensionX"), p.get("dimensionY"), p.get("dimensionZ")],
        "texture_px": p.get("textureResolutionMax"), "style": p.get("modelStyle"),
        "url": f"{bk.global_vars.SERVER}/asset-gallery-detail/{r.get('id')}/",
        "description": (r.get("description") or "")[:160],
    }


def download_address(bk, asset, k):
    """(can_download, url, filename) from the add-on's Client. The add-on's wrapper uses a 1 s read timeout; raise it for the call, retry with back-off."""
    old = bk.client_lib.TIMEOUT
    bk.client_lib.TIMEOUT = URL_TIMEOUT
    last = None
    try:
        for attempt in range(URL_TRIES):
            try:
                return bk.client_lib.get_download_url(asset, str(uuid.uuid4()), k)
            except Exception as e:  # noqa: BLE001
                last = e
                if attempt + 1 < URL_TRIES:
                    say(f"  download address not ready ({type(e).__name__}), try {attempt + 2} of {URL_TRIES} in {pause(attempt):.0f} s")
                    time.sleep(pause(attempt))
    finally:
        bk.client_lib.TIMEOUT = old
    raise FetchError(f"BlenderKit Client did not give a download address after {URL_TRIES} tries: {last}")


def download_file(bk, url, dst: Path, k):
    """Download through the add-on Client's blocking route with a patient timeout (the add-on's own wrapper allows 1 s to connect)."""
    last = None
    for attempt in range(DOWNLOAD_TRIES):
        dst.unlink(missing_ok=True)
        try:
            cl = bk.client_lib
            if hasattr(cl, "ensure_minimal_data") and hasattr(cl, "get_base_url"):
                import requests
                data = cl.ensure_minimal_data({"url": url, "filepath": str(dst)})
                with requests.Session() as session:
                    resp = session.get(f"{cl.get_base_url()}/wrappers/blocking_file_download", json=data, timeout=DOWNLOAD_TIMEOUT, proxies=getattr(cl, "NO_PROXIES", None))
            else:
                resp = cl.blocking_file_download(url, str(dst), k)
            if getattr(resp, "status_code", 200) == 200 and dst.exists() and dst.stat().st_size > 1024:
                return
            last = f"HTTP {getattr(resp, 'status_code', '?')}, file {'missing' if not dst.exists() else str(dst.stat().st_size) + ' bytes'}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        if attempt + 1 < DOWNLOAD_TRIES:
            say(f"  download failed ({last}), try {attempt + 2} of {DOWNLOAD_TRIES} in {pause(attempt):.0f} s")
            time.sleep(pause(attempt))
    dst.unlink(missing_ok=True)
    raise FetchError(f"download failed after {DOWNLOAD_TRIES} tries ({last})")


def fetch(bk, key, ident):
    """Download one asset and write its meta.json (with the licence). Raises FetchError for this asset only."""
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", ident)
    if not m:
        raise FetchError(f"'{ident}' is not an assetBaseId or a BlenderKit gallery URL")
    aid = m.group(1)
    res = search(bk, key, f"asset_base_id:{aid}", asset_type="model,scene,material", limit=1)
    if not res:
        res = [r for r in search(bk, key, f"asset_id:{aid}", asset_type="model,scene,material", limit=1)]
    if not res:
        raise FetchError(f"no BlenderKit asset with id {aid}")
    r = res[0]
    lic = r.get("license")
    if lic not in ALLOWED_LICENCES:
        raise FetchError(f"'{r.get('name')}' is licensed '{lic}': only {', '.join(f'{v} ({k_})' for k_, v in ALLOWED_LICENCES.items())} may be used, so it is not downloaded")
    try:
        asset = bk.search.parse_result(dict(r)) or r
    except Exception:  # noqa: BLE001
        asset = r
    out_dir = PROJECT / "library" / "_downloads" / "blenderkit" / r["assetBaseId"]
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("*.blend"), key=lambda p: p.stat().st_size)
    dst = existing[-1] if existing and existing[-1].stat().st_size > 1024 else None
    if dst is None:
        ensure_client(bk)
        k = api_key(key)
        can, url, filename = download_address(bk, asset, k)
        if not can or not url:
            raise FetchError(f"'{r.get('name')}' cannot be downloaded with this account (plan or permissions). canDownload={r.get('canDownload')}")
        dst = out_dir / (filename or f"{r['assetBaseId']}.blend")
        say(f"  downloading '{r.get('name')}' ({ALLOWED_LICENCES[lic]}) ...")
        download_file(bk, url, dst, k)
    meta = brief(r, bk) | {"blend": str(dst), "downloaded": time.strftime("%Y-%m-%d"), "license_checked": True, "bytes": dst.stat().st_size}
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
        try:
            res = search(bk, key, a.query, a.type, a.limit)
        except FetchError as e:
            fail(str(e))
        print("BK_RESULT " + json.dumps({"ok": True, "results": [brief(r, bk) for r in res]}))
        return
    done, failed = [], []
    for i in a.ids:
        say(f"[bk_fetch] {i}")
        try:
            done.append(fetch(bk, key, i))
            say(f"  ok: {done[-1]['name']} -> {done[-1]['blend']}")
        except FetchError as e:
            failed.append({"id": i, "error": str(e)})
            say(f"  FAILED: {e}")
    print("BK_RESULT " + json.dumps({"ok": not failed, "assets": done, "failed": failed}))
    if failed:
        say(f"[bk_fetch] {len(done)} downloaded, {len(failed)} failed: " + "; ".join(f["id"] for f in failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
