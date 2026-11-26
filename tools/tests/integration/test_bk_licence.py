"""bk_fetch must refuse any licence other than CC0 / Royalty Free before it downloads, record the licence of what it does download, and let a
batch go on past a failed id. Runs with plain Python (bpy and the add-on are stubbed):

    py -3 tools/tests/integration/test_bk_licence.py
"""
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.modules["bpy"] = types.SimpleNamespace(context=types.SimpleNamespace(preferences=types.SimpleNamespace(addons={})), app=types.SimpleNamespace(version=(5, 3, 0)))
sys.path.insert(0, str(ROOT / "tools" / "blender"))
import bk_fetch  # noqa: E402

TMP = Path(tempfile.mkdtemp())
bk_fetch.PROJECT = TMP
calls = {"url": 0, "download": 0}


class FakeClient:
    TIMEOUT = (0.1, 1)

    @staticmethod
    def get_download_url(asset, scene, key):
        calls["url"] += 1
        if calls["url"] < 3:                                       # the first two tries time out, like the real Client does
            raise TimeoutError("Read timed out. (read timeout=1)")
        assert FakeClient.TIMEOUT[1] >= 30, "the read timeout was not raised for the call"
        return True, "https://example.invalid/x", "blend_x.blend"

    @staticmethod
    def blocking_file_download(url, filepath, key):
        calls["download"] += 1
        Path(filepath).write_bytes(b"BLENDER" + b"0" * 4096)
        return types.SimpleNamespace(status_code=200)


bk = types.SimpleNamespace(client_lib=FakeClient, search=types.SimpleNamespace(parse_result=lambda r: r), global_vars=types.SimpleNamespace(SERVER="https://x"))
bk_fetch.ensure_client = lambda bk_: None
bk_fetch.api_key = lambda key: "k"
bk_fetch.time.sleep = lambda s: None                              # no real waiting in the test
A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
RESULTS = {A: {"assetBaseId": A, "id": "a", "name": "Chair CC-BY", "license": "cc_by", "assetType": "model"},
           B: {"assetBaseId": B, "id": "b", "name": "Chair RF", "license": "royalty_free", "assetType": "model", "isFree": True}}
bk_fetch.search = lambda bk_, key, q, asset_type="model", limit=8, free_only=False: [RESULTS[i] for i in RESULTS if i in q]

try:
    bk_fetch.fetch(bk, "k", A)
except bk_fetch.FetchError as e:
    assert "cc_by" in str(e), e
else:
    raise SystemExit("FAIL: a cc_by asset was not refused")
assert calls == {"url": 0, "download": 0}, "a refused asset must not start a download"
assert not (TMP / "library" / "_downloads" / "blenderkit" / A / "meta.json").exists()

meta = bk_fetch.fetch(bk, "k", B)
assert calls["url"] == 3 and calls["download"] == 1, calls         # two timeouts, then success
assert FakeClient.TIMEOUT == (0.1, 1), "the add-on's own timeout must be put back"
saved = json.loads((TMP / "library" / "_downloads" / "blenderkit" / B / "meta.json").read_text(encoding="utf-8"))
assert saved["license"] == "royalty_free" and saved["license_name"] == "Royalty Free" and saved["license_checked"], saved
print("bk_fetch licence gate, retry and meta.json: ok")
