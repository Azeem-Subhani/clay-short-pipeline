"""Approval gates for one clip: recorded on disk, resumable, enforced by the tools.

Three checkpoints where a person looks at previews and decides:
  A  characters and wardrobe   before any shot is staged
  B  sets                      before any shot is staged
  C  camera                    before the final-quality render

State lives in output/clips/<clip>/approvals.json. Each gate remembers the fingerprint (a hash of the inputs it covers)
that was approved, so an edit to those inputs, and only those, makes that gate stale and asks for a new decision.
Standard library only; importing this module does nothing.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # tests point this at a temporary folder
GATES = ("A", "B", "C")
TITLES = {"A": "characters and wardrobe", "B": "sets", "C": "camera"}
STATUSES = ("pending", "ready", "approved", "changes_requested", "bypassed")
MODES = ("interactive", "autonomous")
VERSION = 1
BLOCK_EXIT = 4


class GateError(Exception):
    """A gate operation that is refused (the message says why)."""


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _as_dir(clip_dir) -> Path:
    return Path(clip_dir)


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _h(data: bytes | str) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def _file_h(p: Path) -> str:
    try:
        return _h(p.read_bytes())
    except OSError:
        return "absent"


# ----------------------------------------------------------------------------- inputs of each gate
def _wear_names(costume) -> list[str]:
    """Wardrobe item names a plan's costume block wears (a list, a string or a dict of slot -> name)."""
    if not isinstance(costume, dict):
        return []
    w = costume.get("wear")
    if isinstance(w, str):
        return [w]
    if isinstance(w, list):
        return [x if isinstance(x, str) else (x.get("id") or x.get("name") or "") for x in w if x]
    if isinstance(w, dict):
        return [x for x in w.values() if isinstance(x, str)]
    return []


def _lookup(table, key: str):
    """An entry of a registry that may be a dict keyed by id, or a list of dicts with an id/name; None when absent."""
    if isinstance(table, dict):
        return table.get(key)
    if isinstance(table, list):
        return next((x for x in table if isinstance(x, dict) and key in (x.get("id"), x.get("name"))), None)
    return None


def _section(doc, *names):
    """The first of these keys a registry file has (the wardrobe index may call it items, wardrobe or nothing)."""
    if not isinstance(doc, dict):
        return doc
    for n in names:
        if n in doc:
            return doc[n]
    return doc


def inputs(clip_dir, gate: str) -> dict:
    """label -> hash of every input the gate covers. Missing inputs hash as 'absent'."""
    clip = _as_dir(clip_dir)
    plan = _read_json(clip / "shotplan.json")
    plan = plan if isinstance(plan, dict) else {}
    out: dict[str, str] = {}

    def part(key):
        out[f"shotplan.json#{key}"] = _h(_canon(plan[key])) if key in plan else "absent"

    if gate == "A":
        part("cast")
        part("world")
        out["casting.json"] = _file_h(clip / "casting.json")
        cast_reg = _section(_read_json(ROOT / "config" / "cast.json"), "characters")
        wardrobe = _section(_read_json(ROOT / "library" / "wardrobe" / "index.json"), "items", "wardrobe", "pieces")
        for c in plan.get("cast") or []:
            if not isinstance(c, dict):
                continue
            base = c.get("base")
            if base:
                e = _lookup(cast_reg, base)
                out[f"config/cast.json#{base}"] = _h(_canon(e)) if e is not None else "absent"
            for item in _wear_names(c.get("costume")):
                e = _lookup(wardrobe, item)
                out[f"library/wardrobe/index.json#{item}"] = _h(_canon(e)) if e is not None else "absent"
    elif gate == "B":
        part("sets")
        for p in sorted((clip / "blender").glob("set_*.py")):
            out[f"blender/{p.name}"] = _file_h(p)
    elif gate == "C":
        for p in sorted((clip / "blender").glob("*.py")):
            if not p.name.startswith("set_"):
                out[f"blender/{p.name}"] = _file_h(p)
        out["timing.json"] = _file_h(clip / "timing.json")
    else:
        raise GateError(f"unknown gate {gate!r}: use A, B or C")
    return out


def fingerprint(clip_dir, gate: str) -> str:
    """SHA-256 over the sorted labels and content hashes of the gate's inputs."""
    return _h("\n".join(f"{k}={v}" for k, v in sorted(inputs(clip_dir, gate).items())))


# ----------------------------------------------------------------------------- state file
def _blank_gate() -> dict:
    return {"status": "pending", "fingerprint": None, "decided_at": None, "decided_by": None, "notes": None,
            "previews": [], "round": 0}


def _blank() -> dict:
    return {"version": VERSION, "mode": "interactive", "mode_reason": None, "mode_set": None,
            "gates": {g: _blank_gate() for g in GATES}, "history": []}


def path(clip_dir) -> Path:
    return _as_dir(clip_dir) / "approvals.json"


def load(clip_dir) -> dict:
    """The clip's approvals (a fresh interactive record if none is on disk yet; nothing is written)."""
    doc = _read_json(path(clip_dir))
    base = _blank()
    if not isinstance(doc, dict):
        return base
    base.update({k: v for k, v in doc.items() if k in ("version", "mode", "mode_reason", "mode_set", "history")})
    for g in GATES:
        base["gates"][g].update((doc.get("gates") or {}).get(g) or {})
    return base


def save(clip_dir, state: dict) -> Path:
    """Atomic write: a temporary file next to the real one, then a rename."""
    p = path(clip_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


def _log(state: dict, gate, action: str, **extra) -> None:
    """History is only ever appended to."""
    state["history"].append({"time": _now(), "gate": gate, "action": action, "mode": state["mode"], **extra})


def _check_gate(gate: str) -> str:
    g = str(gate).upper()
    if g not in GATES:
        raise GateError(f"unknown gate {gate!r}: use A, B or C")
    return g


def _stale(clip_dir, g: dict, gate: str) -> bool:
    return g["status"] in ("approved", "bypassed") and g["fingerprint"] != fingerprint(clip_dir, gate)


def changed_since(clip_dir, gate: str) -> list[str]:
    """Short list of input labels that differ from what was approved (needs the stored per-input hashes)."""
    g = load(clip_dir)["gates"][gate]
    old = g.get("inputs") or {}
    now = inputs(clip_dir, gate)
    return sorted(k for k in set(old) | set(now) if old.get(k, "absent") != now.get(k, "absent"))


# ----------------------------------------------------------------------------- decisions
def mark_ready(clip_dir, gate: str, previews) -> dict:
    """Previews for the gate exist and wait for a human. An approved gate whose inputs have not changed stays approved."""
    gate = _check_gate(gate)
    st = load(clip_dir)
    g = st["gates"][gate]
    fp = fingerprint(clip_dir, gate)
    g["previews"] = [str(p) for p in (previews or [])]
    g["previews_fingerprint"] = fp
    if not (g["status"] == "approved" and g["fingerprint"] == fp):
        g["status"] = "ready"
    _log(st, gate, "ready", previews=g["previews"], fingerprint=fp)
    save(clip_dir, st)
    return g


def approve(clip_dir, gate: str, by: str = "user", notes: str | None = None, no_previews: bool = False) -> dict:
    """Record approval of the gate's current inputs. Refused unless previews of these inputs were recorded first."""
    gate = _check_gate(gate)
    st = load(clip_dir)
    g = st["gates"][gate]
    fp = fingerprint(clip_dir, gate)
    if not no_previews:
        if not g["previews"]:
            raise GateError(f"Gate {gate} has no previews recorded: show it first (approval must follow something shown), "
                            "or pass --no-previews to approve without")
        if g.get("previews_fingerprint") != fp:
            raise GateError(f"Gate {gate}: its inputs changed since the previews were made; make the previews again before approving")
    g.update(status="approved", fingerprint=fp, inputs=inputs(clip_dir, gate), decided_at=_now(), decided_by=by, notes=notes)
    _log(st, gate, "approved", by=by, notes=notes, fingerprint=fp, no_previews=bool(no_previews))
    save(clip_dir, st)
    return g


def request_changes(clip_dir, gate: str, notes, by: str = "user") -> dict:
    """The reviewer wants changes: stores the list of requested changes and counts a review round."""
    gate = _check_gate(gate)
    notes = [notes] if isinstance(notes, str) else [n for n in (notes or []) if n]
    if not notes:
        raise GateError("say what to change (--revise \"...\")")
    st = load(clip_dir)
    g = st["gates"][gate]
    g.update(status="changes_requested", fingerprint=None, inputs={}, decided_at=_now(), decided_by=by, notes=notes, round=g["round"] + 1)
    _log(st, gate, "changes_requested", by=by, notes=notes, round=g["round"])
    save(clip_dir, st)
    return g


def _bypass(st: dict, clip_dir, gate: str, reason) -> None:
    fp = fingerprint(clip_dir, gate)
    g = st["gates"][gate]
    g.update(status="bypassed", fingerprint=fp, inputs=inputs(clip_dir, gate), decided_at=_now(), decided_by="autonomous mode",
             notes=reason)
    _log(st, gate, "bypassed", reason=reason, fingerprint=fp)


def bypass(clip_dir, gate: str, reason: str) -> dict:
    """Let a gate pass without a human decision (only meaningful in autonomous mode). Never recorded as an approval."""
    gate = _check_gate(gate)
    if not reason:
        raise GateError("a bypass needs a reason")
    st = load(clip_dir)
    _bypass(st, clip_dir, gate, reason)
    save(clip_dir, st)
    return st["gates"][gate]


def set_mode(clip_dir, mode: str, reason: str | None = None) -> dict:
    """interactive (default) or autonomous (the owner asked for an unattended run; the reason is required)."""
    if mode not in MODES:
        raise GateError(f"mode is one of {', '.join(MODES)}")
    if mode == "autonomous" and not (reason and reason.strip()):
        raise GateError("autonomous mode needs a reason (--reason \"...\"): say who asked for the unattended run")
    st = load(clip_dir)
    st.update(mode=mode, mode_reason=reason if mode == "autonomous" else None, mode_set=_now())
    _log(st, None, f"mode_{mode}", reason=reason)
    save(clip_dir, st)
    return st


# ----------------------------------------------------------------------------- derived state and enforcement
def status(clip_dir) -> dict:
    """Per gate: status, stale, what changed since approval, previews, last notes, round; plus mode and next decision."""
    st = load(clip_dir)
    out = {"clip": _as_dir(clip_dir).name, "mode": st["mode"], "mode_reason": st["mode_reason"], "mode_set": st["mode_set"], "gates": {}}
    for gate in GATES:
        g = st["gates"][gate]
        stale = _stale(clip_dir, g, gate)
        out["gates"][gate] = {
            "title": TITLES[gate], "status": g["status"], "stale": stale,
            "changed": changed_since(clip_dir, gate) if stale else [],
            "previews": g["previews"], "notes": g["notes"], "round": g["round"],
            "decided_at": g["decided_at"], "decided_by": g["decided_by"], "fingerprint": g["fingerprint"],
            "approved": g["status"] == "approved" and not stale,
        }
    out["next_decision"] = next_decision(clip_dir)
    return out


def next_decision(clip_dir) -> str | None:
    """The first gate a human must still decide, or None (autonomous mode never waits for one)."""
    st = load(clip_dir)
    if st["mode"] == "autonomous":
        return None
    for gate in GATES:
        g = st["gates"][gate]
        if not (g["status"] == "approved" and not _stale(clip_dir, g, gate)):
            return gate
    return None


def requirements(stage: str, quality: str | None = None, tag: str | None = None) -> set[str]:
    """Which gates a stage needs. Set-only previews and character sheets are not stages here: they need none."""
    if stage == "stills":
        return {"A", "B"}
    if stage == "render":
        return {"A", "B"} if quality in ("draft", "preview") else {"A", "B", "C"}
    if stage == "assemble":
        animatic = (tag or "").strip().lower() == "animatic" or quality == "draft"
        return {"A", "B"} if animatic else {"A", "B", "C"}
    return set()


def _py() -> str:
    return "py -3" if sys.platform == "win32" else "python3"


SHOW_WITH = {"A": "cast-sheets", "B": "setpreview", "C": "preview"}


def _problem(clip_name: str, gate: str, g: dict, stale: bool, changed: list[str]) -> str:
    cmd = f"{_py()} tools/clip.py gate {clip_name} {gate}"
    make = f"{_py()} tools/clip.py {SHOW_WITH[gate]} {clip_name}"
    state = g["status"] + (" but STALE (its inputs changed since the decision" + (": " + ", ".join(changed[:6]) if changed else "") + ")" if stale else "")
    if g["status"] == "changes_requested":
        how = f"changes were requested: {'; '.join(g['notes'] or [])}. Fix them, make new previews with `{make}`, then decide with `{cmd}`"
    elif stale or g["status"] in ("approved", "bypassed"):
        how = f"it needs a new decision: make previews with `{make}`, show them with `{cmd}`"
    elif g["status"] == "ready":
        how = f"previews are ready: show them and ask the user with `{cmd}`"
    else:
        how = f"no previews yet: make them with `{make}`, then show them with `{cmd}`"
    return f"Gate {gate} ({TITLES[gate]}) is {state}; {how}"


def check(clip_dir, stage: str, quality: str | None = None, tag: str | None = None) -> tuple[bool, list[str]]:
    """Can this stage run? Interactive: every required gate must be approved and not stale. Autonomous: never blocks, but a
    required gate without a current approval is recorded as 'bypassed' (never as approved) with the mode reason."""
    need = sorted(requirements(stage, quality, tag))
    if not need:
        return True, []
    st = load(clip_dir)
    name = _as_dir(clip_dir).name
    problems, dirty = [], False
    for gate in need:
        g = st["gates"][gate]
        stale = _stale(clip_dir, g, gate)
        if g["status"] == "approved" and not stale:
            continue
        if st["mode"] == "autonomous":
            if not (g["status"] == "bypassed" and not stale):
                _bypass(st, clip_dir, gate, st["mode_reason"])
                dirty = True
            continue
        problems.append(_problem(name, gate, g, stale, changed_since(clip_dir, gate) if stale else []))
    if dirty:
        save(clip_dir, st)
    return not problems, problems
