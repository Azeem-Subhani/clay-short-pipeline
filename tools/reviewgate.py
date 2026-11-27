"""The review rule: a shot goes to the final render only as the reviewer last saw it.

A shot's *build* is a short hash of everything in the clip that decides what the shot looks like: its script, the set
files, its length from the voice take, and its entry and cast in the plan. `clip.py stills` stamps the build into
review/<shot>/checks.json; the frame-reviewer copies it into verdict.json as "reviewed_build". Final `render` and
`assemble` then need, for every shot:

  1. stills made from the current build with no blocking check;
  2. a verdict written for the current build (a fix round always needs a new review);
  3. that verdict to be "pass", or a recorded acceptance of this build (review/<shot>/accepted.json: who, why).

Nothing here is bypassed by autonomous mode: the reviewer is an agent, so an unattended run can always get a review.
An acceptance is the only way past a "fix" or "restage", and it is written down with its reason.

Standard library only (Blender's Python imports this too).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path

BLOCK_EXIT = 4                      # the same exit code as an undecided approval gate


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _leans_on(text: str, stem: str) -> bool:
    """Does this source use the clip module `stem`? An import line naming it, its file name (`sh02.py`, read as text for its marks),
    or its name as a quoted string (importlib). A plain mention in a comment ("sh03 finds him at the gate") does not count."""
    s = re.escape(stem)
    return bool(re.search(rf"^[ \t]*(?:import|from)[ \t]+[^\n#]*\b{s}\b", text, re.M) or re.search(rf"\b{s}\.py\b", text)
                or re.search(rf"""["']{s}["']""", text))


def _closure(clip: Path, shot_id: str) -> list[Path]:
    """The shot script and every other module of the clip it leans on, followed through (sh03 reads sh02.py for its marks and door
    angles, so a change to sh02 reopens sh03)."""
    folder = clip / "blender"
    others = {p.stem: p for p in folder.glob("*.py") if not p.name.startswith("set_")}
    start = folder / f"{shot_id}.py"
    out, todo = [], [start]
    while todo:
        cur = todo.pop()
        if cur in out or not cur.exists():
            continue
        out.append(cur)
        text = cur.read_text(encoding="utf-8", errors="replace")
        todo += [q for stem, q in others.items() if q not in out and _leans_on(text, stem)]
    return out or [start]


def inputs(clip_dir, shot_id: str) -> dict:
    """label -> hash of each input that decides what the shot looks like: its script and the clip modules it leans on, its own set
    file(s), the clip assets those name, its length and word times (relative to the shot, so a retake of another shot does not
    reopen this one), and its slice of the plan with the cast it uses."""
    clip = Path(clip_dir)
    out: dict[str, str] = {}
    plan = _read(clip / "shotplan.json") or {}
    entry = next((s for s in plan.get("shots") or [] if s.get("id") == shot_id), None)
    mods = _closure(clip, shot_id)
    for m in mods:
        out[f"blender/{m.name}"] = _h(m.read_bytes()) if m.exists() else "absent"
    text = "\n".join(m.read_text(encoding="utf-8", errors="replace") for m in mods if m.exists())
    set_files = sorted((clip / "blender").glob("set_*.py"))
    named = {str((entry or {}).get("set") or "")}
    mine = [p for p in set_files if p.stem[4:] in named or re.search(rf"\b{re.escape(p.stem)}\b", text)]
    for p in mine or set_files:                           # a shot that names no set is checked against all of them
        out[f"blender/{p.name}"] = _h(p.read_bytes())
        text += "\n" + p.read_text(encoding="utf-8", errors="replace")
    assets = clip / "assets"
    if assets.is_dir():                                   # pictures and props the clip made for itself (a security still shown on a screen)
        for p in sorted(x for x in assets.rglob("*") if x.is_file()):
            if p.name in text or p.stem in text:
                out[f"assets/{p.relative_to(assets).as_posix()}"] = _h(p.read_bytes())
    timing = _read(clip / "timing.json") or {}
    t = (timing.get("shots") or {}).get(shot_id) or {}
    s0 = float(t.get("start_s") or 0.0)
    out["timing.json#length"] = _h(_canon({k: t.get(k) for k in ("seconds", "frames")}))
    out["timing.json#words"] = _h(_canon([[w.get("text"), round(float(w.get("start", 0)) - s0, 3), round(float(w.get("end", 0)) - s0, 3)]
                                          for w in timing.get("words") or [] if w.get("shot") == shot_id]))
    out["shotplan.json#shot"] = _h(_canon(entry))
    out["shotplan.json#world"] = _h(_canon(plan.get("world")))
    used = [c for c in plan.get("cast") or [] if isinstance(c, dict) and c.get("id") and re.search(rf"""["']{re.escape(str(c['id']))}["']""", text)]
    out["shotplan.json#cast"] = _h(_canon(used))
    return out


def kit_id() -> str:
    """16 hex characters naming the toolkit and registries every shot is built from (stagekit, actions, cast, clips, wardrobe index).
    A change here can change any shot, so `state` reports it; it does not reopen reviews by itself."""
    root = Path(__file__).resolve().parents[1]
    files = [*sorted((root / "tools" / "blender" / "stagekit").glob("*.py")),
             *[root / "config" / n for n in ("cast.json", "actions.json", "mixamo_clips.json")], root / "library" / "wardrobe" / "index.json"]
    return _h("\n".join(f"{p.name}={_h(p.read_bytes()) if p.exists() else 'absent'}" for p in files).encode("utf-8"))[:16]


def build_id(clip_dir, shot_id: str) -> str:
    """16 hex characters naming the current form of the shot."""
    return _h("\n".join(f"{k}={v}" for k, v in sorted(inputs(clip_dir, shot_id).items())).encode("utf-8"))[:16]


def state(clip_dir, shot_id: str) -> dict:
    """Where the shot stands: {"shot", "build", "status", "ok", "why", ...}.
    status: no_stills | stale_stills | blocked | no_verdict | stale_verdict | not_passed | accepted | pass."""
    clip = Path(clip_dir)
    rd = clip / "review" / shot_id
    build = build_id(clip, shot_id)
    out = {"shot": shot_id, "build": build, "kit": kit_id(), "kit_changed": False, "ok": False, "verdict": None, "stills_build": None, "reviewed_build": None, "blocking": None, "accepted": None}
    checks = _read(rd / "checks.json")
    verdict = _read(rd / "verdict.json")
    accepted = _read(rd / "accepted.json")
    if isinstance(verdict, dict):
        out["verdict"] = verdict.get("verdict")
        out["reviewed_build"] = verdict.get("reviewed_build")
    if not isinstance(checks, dict):
        return out | {"status": "no_stills", "why": "no review stills: build them first"}
    out["stills_build"] = checks.get("build")
    out["kit_changed"] = bool(checks.get("kit")) and checks.get("kit") != out["kit"]
    out["blocking"] = sum(1 for i in checks.get("items") or [] if i.get("level") == "block")
    if checks.get("build") != build:
        return out | {"status": "stale_stills", "why": "the shot changed after its review stills were made (or they carry no build stamp): make the stills again"}
    if out["blocking"]:
        return out | {"status": "blocked", "why": f"{out['blocking']} blocking check item(s) in review/{shot_id}/checks.json"}
    if not isinstance(verdict, dict) or not verdict.get("verdict"):
        return out | {"status": "no_verdict", "why": "never reviewed: run the frame-reviewer on it"}
    if verdict.get("reviewed_build") != build:
        return out | {"status": "stale_verdict", "why": f"its verdict ('{verdict.get('verdict')}') was written for an earlier form of the shot: review it again"}
    if verdict.get("verdict") == "pass":
        return out | {"status": "pass", "ok": True, "why": "reviewed and passed"}
    if isinstance(accepted, dict) and accepted.get("build") == build:
        out["accepted"] = accepted
        return out | {"status": "accepted", "ok": True, "why": f"verdict '{verdict.get('verdict')}' accepted by {accepted.get('by')}: {accepted.get('reason')}"}
    n = len(verdict.get("issues") or [])
    return out | {"status": "not_passed", "why": f"verdict '{verdict.get('verdict')}' with {n} open issue(s): fix and review again, or record an acceptance"}


def check(clip_dir, shot_ids) -> tuple[bool, list[dict]]:
    """(every shot may be rendered final, the states of those that may not)."""
    bad = [s for s in (state(clip_dir, sid) for sid in shot_ids) if not s["ok"]]
    return not bad, bad


def frames_state(clip_dir, shot_id: str, quality: str = "final") -> dict:
    """Do the rendered frames of the shot show its current build? {"shot", "status": none | current | stale, "why"}.
    Frames are resumable (an existing PNG is never rendered twice), so after a fix the old pictures would be reused."""
    out_dir = Path(clip_dir) / "render" / shot_id / quality
    meta = _read(out_dir / "render.json")
    if not (out_dir.is_dir() and any(out_dir.glob("*.png"))):
        return {"shot": shot_id, "status": "none", "why": "not rendered"}
    if isinstance(meta, dict) and meta.get("build") == build_id(clip_dir, shot_id):
        return {"shot": shot_id, "status": "current", "why": "frames show the current build"}
    return {"shot": shot_id, "status": "stale", "why": f"the {quality} frames in render/{shot_id}/{quality}/ were rendered from an earlier form of the shot "
            "(or carry no build stamp): render the shot again with --force"}


def stamp_stills(clip_dir, shot_id: str) -> str | None:
    """Write the current build (and kit) into review/<shot>/checks.json. Called by `clip.py stills` after a complete run only:
    a run of a few views, or with an overridden length, did not check the whole shot and must not make it look checked."""
    p = Path(clip_dir) / "review" / shot_id / "checks.json"
    data = _read(p)
    if not isinstance(data, dict):
        return None
    data["build"], data["kit"] = build_id(clip_dir, shot_id), kit_id()
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data["build"]


def accept(clip_dir, shot_id: str, reason: str, by: str = "user") -> dict:
    """Record that a shot goes ahead without a pass. Only a verdict on the current build can be accepted."""
    reason = (reason or "").strip()
    if len(reason) < 8:
        raise ValueError("an acceptance needs a reason (what is still wrong and why it ships anyway)")
    st = state(clip_dir, shot_id)
    if st["status"] in ("pass", "accepted"):
        return st
    if st["status"] != "not_passed":
        raise ValueError(f"{shot_id} cannot be accepted yet: {st['why']}")
    verdict = _read(Path(clip_dir) / "review" / shot_id / "verdict.json") or {}
    rec = {"shot": shot_id, "build": st["build"], "verdict": st["verdict"], "by": by, "reason": reason,
           "open_issues": [i.get("problem") for i in verdict.get("issues") or [] if isinstance(i, dict)],
           "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    (Path(clip_dir) / "review" / shot_id / "accepted.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    return state(clip_dir, shot_id)
