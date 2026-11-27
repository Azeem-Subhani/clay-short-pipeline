"""What the shot code asked its actors to do, written down as it is asked, so the physical checks (stagekit.physical) can measure
the result against the intent instead of guessing it from the scene.

    shot.holds          every hold, kept after the release:  {actor, prop (name), side, f0, f1 (None while held), grip, solved, hang}
    shot.interactions   every reach, aim and targeted action: {actor, kind (reach | aim | action), action (the named action it
                        belongs to, or None for a hand-posed reach), side, target (the live object, anchor or point), label, t}
    shot.passages       every walk through a barrier that was not open wide enough: {actor, barrier (object name), frame, open_deg, clearance_cm}
    shot.wears          every thing hung on a body through the kit (wear_bag...): {actor, prop, where}

Nothing here changes a pose. A shot that poses by hand without a target (a raw `arm(...)` wave) leaves no record, and the checks say
so: an action with no declared target cannot be checked, which is itself reported.
"""
from __future__ import annotations


def _log(shot, name: str) -> list:
    if shot is None:
        return []
    cur = getattr(shot, name, None)
    if cur is None:
        cur = []
        setattr(shot, name, cur)
    return cur


def label_of(target) -> str:
    """A short name for a target: the object's name, an anchor's name, or the point."""
    if target is None:
        return "nothing"
    for attr in ("name", "id"):
        n = getattr(target, attr, None)
        if isinstance(n, str) and n:
            return n
    ob = getattr(target, "ob", None)
    if ob is not None and getattr(ob, "name", None):
        return ob.name
    try:
        return "pt(" + ", ".join(f"{float(v):.2f}" for v in list(target)[:3]) + ")"
    except (TypeError, ValueError):
        return type(target).__name__


def hold(actor, prop, side: str, frame: int, grip: bool, solved: bool, hang: bool = False) -> None:
    """hang: the prop is carried by a handle on top and hangs from the fist (hold(hang=True)): the handle is inside the closed hand on
    purpose and the prop rides beside the leg, not in front of the chest, so the checks judge it differently."""
    _log(getattr(actor, "shot", None), "holds").append(
        {"actor": actor.id, "prop": prop.name, "side": side, "f0": int(frame), "f1": None, "grip": bool(grip), "solved": bool(solved), "hang": bool(hang)})


def release(actor, prop, frame: int) -> None:
    for h in reversed(_log(getattr(actor, "shot", None), "holds")):
        if h["actor"] == actor.id and h["prop"] == prop.name and h["f1"] is None:
            h["f1"] = int(frame)
            return


def reach(actor, kind: str, side: str, target, t: float) -> None:
    doing = getattr(actor, "_doing", None) or []
    _log(getattr(actor, "shot", None), "interactions").append(
        {"actor": actor.id, "kind": kind, "action": doing[-1] if doing else None, "side": side, "target": target, "label": label_of(target), "t": float(t)})


def action(actor, name: str, side: str, target, t_hit: float) -> None:
    _log(getattr(actor, "shot", None), "interactions").append(
        {"actor": actor.id, "kind": "action", "action": name, "side": side, "target": target, "label": label_of(target), "t": max(0.0, float(t_hit))})


def passage(actor, barrier: str, frame: int, open_deg: float, clearance_cm: float) -> None:
    """A walk that goes through a barrier (door leaf, gate flap, lift door) that is not open wide enough: shot.passages, one entry per frame
    found (stagekit.anchors.check_walk writes it; physical.sweep turns it into a through_closed_leaf item). Nothing is raised: the walk is still
    animated, so the shot can be looked at."""
    _log(getattr(actor, "shot", None), "passages").append(
        {"actor": actor.id, "barrier": barrier, "frame": int(frame), "open_deg": float(open_deg), "clearance_cm": float(clearance_cm)})


def wear(actor, prop, where: str) -> None:
    _log(getattr(actor, "shot", None), "wears").append({"actor": actor.id, "prop": prop.name, "where": where})


class doing:
    """with record.doing(actor, "press"): every reach inside is filed under that action."""

    def __init__(self, actor, name: str):
        self.actor, self.name = actor, name

    def __enter__(self):
        stack = getattr(self.actor, "_doing", None)
        if stack is None:
            stack = []
            try:
                self.actor._doing = stack
            except AttributeError:
                pass
        stack.append(self.name)
        return self

    def __exit__(self, *exc):
        stack = getattr(self.actor, "_doing", None)
        if stack:
            stack.pop()
        return False
