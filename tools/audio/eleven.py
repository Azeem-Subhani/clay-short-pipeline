"""Minimal ElevenLabs REST client (standard library only).

Endpoints used (checked against the API reference, November 2026):
  POST /v1/text-to-speech/{voice_id}/with-timestamps   narration + character timings
  POST /v1/text-to-dialogue/with-timestamps            fallback route for dialogue-only models
  POST /v1/forced-alignment                            word timings for any audio + text
  POST /v1/sound-generation                            sound effects and looping ambience
  POST /v1/music                                       background music
  GET  /v1/models, /v2/voices, /v1/voices/{id}, /v1/shared-voices, /v1/user/subscription
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io")


class ElevenError(RuntimeError):
    def __init__(self, status, body, url):
        self.status, self.body, self.url = status, body, url
        msg = body
        try:
            d = json.loads(body).get("detail")
            msg = d.get("message") if isinstance(d, dict) else json.dumps(d)
        except Exception:
            pass
        super().__init__(f"ElevenLabs {status} on {url.split('?')[0]}: {str(msg)[:400]}")


def api_key() -> str:
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not k:
        raise SystemExit("ELEVENLABS_API_KEY is not set. Put it in .env (see .env.example), or run this step with --mock.")
    return k


def has_key() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY", "").strip())


def _request(method, path, query=None, body=None, headers=None, raw=None, timeout=300):
    url = API + path + (("?" + urllib.parse.urlencode(query)) if query else "")
    h = {"xi-api-key": api_key(), "accept": "*/*"}
    data = None
    if raw is not None:
        data = raw
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        h["content-type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        raise ElevenError(e.code, e.read().decode("utf-8", "replace"), url) from None
    except urllib.error.URLError as e:
        raise SystemExit(f"cannot reach {API}: {e.reason}") from None


def get_json(path, query=None):
    b, _ = _request("GET", path, query)
    return json.loads(b)


def post_json(path, body, query=None):
    b, _ = _request("POST", path, query, body)
    return json.loads(b)


def post_bytes(path, body, query=None):
    return _request("POST", path, query, body)


def post_multipart(path, fields: dict, files: dict):
    """files: {"file": (filename, bytes, mime)}"""
    bnd = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out += [f"--{bnd}".encode(), f'Content-Disposition: form-data; name="{k}"'.encode(), b"", str(v).encode("utf-8")]
    for k, (fn, data, mime) in files.items():
        out += [f"--{bnd}".encode(), f'Content-Disposition: form-data; name="{k}"; filename="{fn}"'.encode(),
                f"Content-Type: {mime}".encode(), b"", data]
    out += [f"--{bnd}--".encode(), b""]
    b, _ = _request("POST", path, raw=b"\r\n".join(out), headers={"content-type": f"multipart/form-data; boundary={bnd}"})
    return json.loads(b)


# ----------------------------------------------------------------------------- high level
def tts_with_timestamps(voice_id: str, text: str, model_id: str, voice_settings: dict | None = None, seed: int | None = None,
                        output_format: str = "mp3_44100_128") -> dict:
    """Returns {"audio_base64", "alignment": {characters, character_start_times_seconds, character_end_times_seconds} | None, ...}."""
    body = {"text": text, "model_id": model_id}
    if voice_settings:
        body["voice_settings"] = voice_settings
    if seed is not None:
        body["seed"] = int(seed)
    return post_json(f"/v1/text-to-speech/{voice_id}/with-timestamps", body, {"output_format": output_format})


def dialogue_with_timestamps(voice_id: str, text: str, model_id: str, settings: dict | None = None, seed: int | None = None,
                             output_format: str = "mp3_44100_128") -> dict:
    body = {"inputs": [{"text": text, "voice_id": voice_id}], "model_id": model_id}
    if settings:
        body["settings"] = settings
    if seed is not None:
        body["seed"] = int(seed)
    return post_json("/v1/text-to-dialogue/with-timestamps", body, {"output_format": output_format})


def forced_alignment(audio: bytes, text: str, filename: str = "narration.mp3") -> dict:
    """{"words": [{"text", "start", "end", "loss"}], "characters": [...], "loss"}"""
    return post_multipart("/v1/forced-alignment", {"text": text}, {"file": (filename, audio, "audio/mpeg")})


def sound_effect(text: str, duration_seconds: float | None = None, loop: bool = False, prompt_influence: float = 0.4,
                 model_id: str = "eleven_text_to_sound_v3", output_format: str = "mp3_44100_128") -> bytes:
    body = {"text": text, "loop": bool(loop), "prompt_influence": prompt_influence, "model_id": model_id}
    if duration_seconds:
        body["duration_seconds"] = max(0.5, min(30.0, float(duration_seconds)))
    b, _ = post_bytes("/v1/sound-generation", body, {"output_format": output_format})
    return b


def music(prompt: str, length_ms: int, model_id: str = "music_v2_5", instrumental: bool = True, output_format: str | None = None) -> bytes:
    body = {"prompt": prompt[:4000], "music_length_ms": max(3000, min(600000, int(length_ms))), "model_id": model_id, "force_instrumental": bool(instrumental)}
    b, _ = post_bytes("/v1/music", body, {"output_format": output_format} if output_format else None)
    return b


def models() -> list[dict]:
    return get_json("/v1/models")


def my_voices(search: str = "") -> list[dict]:
    out, token = [], None
    for _ in range(20):
        q = {"page_size": 100, "include_total_count": "false"}
        if search:
            q["search"] = search
        if token:
            q["next_page_token"] = token
        d = get_json("/v2/voices", q)
        out += d.get("voices", [])
        token = d.get("next_page_token")
        if not d.get("has_more") or not token:
            break
    return out


def voice(voice_id: str) -> dict:
    return get_json(f"/v1/voices/{voice_id}")


def shared_voices(search: str, page_size: int = 10) -> list[dict]:
    return get_json("/v1/shared-voices", {"search": search, "page_size": page_size}).get("voices", [])


def add_shared_voice(public_user_id: str, voice_id: str, new_name: str) -> dict:
    return post_json(f"/v1/voices/add/{public_user_id}/{voice_id}", {"new_name": new_name})


def subscription() -> dict:
    return get_json("/v1/user/subscription")
