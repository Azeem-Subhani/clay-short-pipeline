"""actiontests.py - test actions on characters in isolation: queue the jobs, run them in parallel, judge every frame.

    py -3 actiontests.py --names AdultMan,Boy --set core            # the 8 core actions, all 3 views, both facings
    py -3 actiontests.py --names Ghost --set all --combos 3q:right,side:left --measure-combos front:right,front:left,3q:left,side:right
    py -3 actiontests.py --names AdultMan --actions juggle,slip_banana       # just these actions
    py -3 actiontests.py --report                                   # re-judge what is on disk, write results.json + summary

--set core | all | smoke (every action once, measured only, no pictures: finds actions that crash)
Output: <out>/<Char>/<action>__<view>_<face>.json (per-frame measurements), .strip.jpg (every 2nd frame), .mp4 (full speed)
        <out>/results.json   one verdict per (character, action, view, facing) with the numbers behind it
A job passes only if it ran, wrote its frames, and every frame is inside the limits below. Limits are in metres at the figure.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charpaths as P  # noqa: E402

W = P.TOOLS.parent
BL = P.BL
LIB = P.LIB
CORE = ["walk", "point", "pick_up", "hold_up", "hand_over", "gasp", "talk", "sit_down"]
ALL_COMBOS = ["front:right", "front:left", "3q:right", "3q:left", "side:right", "side:left"]
LIMITS = {"joint_gap": 0.001,       # a limb part may not come away from the part above it (measured in the figure's own plane)
          "parallax": 0.03,         # a forearm lifted in front of the head sits 2 cm nearer the camera: the perspective shift
                                    # of its elbow against the upper arm must stay small on screen
          "held_gap": 0.035,        # a held prop must stay in the palm (on screen)
          "foot_slide": 0.015,      # a planted foot may not creep along the ground per frame
          "hand_target": 0.07}      # reach-type actions: the palm must arrive on the target at the hit frame
REACHES = {"pick_up", "press", "receive", "turn_key", "open_door", "push", "pull", "lift"}
SIDED = REACHES | {"point", "aim", "hand_over", "grab_person", "push_person", "pat_back", "handshake", "slam", "knock"}
GAITS = {"walk", "run", "sneak", "tiptoe", "step_forward", "pace", "chase", "haul"}


def action_names():
    cat = P.PIPELINE / "config" / "actions.json"
    if cat.exists():
        return [a["name"] for a in json.loads(cat.read_text(encoding="utf-8"))["actions"]]
    import re
    txt = (P.PIPELINE / "tools" / "blender" / "stagekit" / "actions.py").read_text(encoding="utf-8")
    return re.findall(r'^@action\("(\w+)"', txt, re.M)


def judge(meta: dict) -> dict:
    rows = meta["rows"]
    act = meta["action"]
    out = {"frames": meta["frames"], "fails": []}
    jg = max(r["joint_gap"] for r in rows)
    hg = max(r["held_gap"] for r in rows)
    out["joint_gap"] = jg
    out["held_gap"] = hg
    if jg > LIMITS["joint_gap"]:
        out["fails"].append(f"limb joint opens {jg * 1000:.1f} mm")
    out["parallax"] = max(r.get("parallax", 0.0) for r in rows)
    if out["parallax"] > LIMITS["parallax"]:
        out["fails"].append(f"lifted forearm shifts {out['parallax'] * 100:.1f} cm against its elbow (perspective)")
    if hg > LIMITS["held_gap"]:
        out["fails"].append(f"held prop leaves the palm by {hg * 100:.1f} cm")
    if act in GAITS and meta.get("body", {}).get("gait", "walk") == "walk":
        sl = [r["foot_slide"] for r in rows]
        fs = max(sl)
        run2 = max((min(sl[i], sl[i + 1]) for i in range(len(sl) - 1)), default=0.0)      # sliding = two frames in a row
        out["foot_slide"] = fs
        out["foot_slide_sustained"] = run2
        if run2 > LIMITS["foot_slide"]:
            out["fails"].append(f"planted foot slides {run2 * 100:.1f} cm per frame over consecutive frames")
        elif fs > 0.045:                             # one frame of adjustment (a start, a stop) may be up to 4.5 cm
            out["fails"].append(f"planted foot jumps {fs * 100:.1f} cm in one frame")
    over = [(r.get(f"over_head_{s}"), r.get(f"lifted_{s}")) for r in rows for s in "LR" if r.get(f"over_head_{s}")]
    if over:
        bad = sum(1 for o, l in over if not l)
        out["hand_over_head_frames"] = len(over)
        if bad > max(2, 0.15 * len(over)):          # the frame or two while the driver switches are not a fault
            out["fails"].append(f"hand behind the head in {bad} of {len(over)} frames where it is over the head")
    hit = min(len(rows) - 1, max(0, meta["hit_frame"] - 1))
    win = rows[hit:hit + 4]
    if act in SIDED and any("hand_side" in r for r in win):
        if not any(r.get("hand_side") == 1 for r in win):
            out["fails"].append("acting hand is on the wrong side of the body for the target")
    if act in REACHES and any("hand_target" in r for r in win):
        ht = min(r["hand_target"] for r in win if "hand_target" in r)
        out["hand_target"] = ht
        if ht > LIMITS["hand_target"]:
            out["fails"].append(f"palm stops {ht * 100:.1f} cm from the target")
    out["elbow_min"] = min(min(r["elbow_L"], r["elbow_R"]) for r in rows)
    out["pass"] = not out["fails"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default=None)
    ap.add_argument("--set", default="core", choices=("core", "all", "smoke"))
    ap.add_argument("--actions", default=None)
    ap.add_argument("--combos", default=None, help="view:face pairs to RENDER (default: all six)")
    ap.add_argument("--measure-combos", default="", help="view:face pairs measured without pictures")
    ap.add_argument("--out", default=str(P.OUT / "actiontests"))
    ap.add_argument("--pack", default=str(LIB))
    ap.add_argument("--other", default="AdultMan")
    ap.add_argument("--px", type=int, default=300)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--queue-only", action="store_true")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--max", type=int, default=0, help="cap on parallel workers per job kind (0 = as many as memory and CPU allow)")
    a = ap.parse_args()
    out = Path(a.out)
    if not a.report:
        names = a.names.split(",")
        acts = a.actions.split(",") if a.actions else (CORE if a.set == "core" else action_names())
        render = ([c for c in a.combos.split(",") if c] if a.combos is not None else ALL_COMBOS) if a.set != "smoke" else []
        measure = [c for c in a.measure_combos.split(",") if c] if a.set != "smoke" else ["3q:right"]
        jobs = []
        for n in names:
            for ac in acts:
                for combo, rend in [(c, True) for c in render] + [(c, False) for c in measure]:
                    v, f = combo.split(":")
                    tag = f"{ac}__{v}_{f}"
                    cmd = [BL, "-b", "--factory-startup", "--threads", "2", "--python", str(P.TOOLS / "bl" / "action_test.py"), "--",
                           "--pipeline", str(P.PIPELINE), "--char", n, "--action", ac, "--view", v, "--face", f, "--pack", a.pack, "--out", str(out), "--px", str(a.px),
                           "--other", a.other, "--chars-dir", str(P.CHARS), "--pipeline", str(P.PIPELINE)] + ([] if rend else ["--no-render"])
                    jobs.append({"id": f"{n}:{tag}", "kind": "action" if rend else "measure", "outputs": [str(out / n / f"{tag}.json")],
                                 "min_bytes": 300, "fail_if": ["Traceback (most recent call last)"], "cmd": cmd,
                                 "post": [n, tag] if rend else None})
        q = P.QUEUES / f"actions_{a.tag}.jsonl"
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text("\n".join(json.dumps(j) for j in jobs) + "\n", encoding="utf-8")
        print(f"{len(jobs)} jobs -> {q}")
        if a.queue_only:
            return 0
        subprocess.run([sys.executable, str(P.TOOLS / "jobrun.py"), "run", str(q), "--limits", str(P.LIMITS)]
                       + (["--max", str(a.max)] if a.max else []))
        sys.path.insert(0, str(P.TOOLS))
        import action_media
        for j in jobs:
            if j.get("post") and (out / j["post"][0] / "frames" / j["post"][1]).exists():
                try:
                    action_media.one(out, j["post"][0], j["post"][1], step=2, cols=12, scale=120)
                except Exception as ex:
                    print("media failed", j["id"], ex)
    # ---- judge everything on disk
    res = {}
    state = {}
    for sp in (P.QUEUES).glob("actions_*.state.json"):
        jq = sp.with_name(sp.name.replace(".state.json", ".jsonl"))      # only queues that wrote into THIS output folder
        if jq.exists() and str(out).replace("\\", "/").lower() in jq.read_text(encoding="utf-8").replace("\\\\", "/").replace("\\", "/").lower():
            state.update(json.loads(sp.read_text(encoding="utf-8")))
    for jf in sorted(out.glob("*/*.json")):
        meta = json.loads(jf.read_text(encoding="utf-8"))
        key = f"{meta['char']}:{meta['action']}__{meta['view']}_{meta['face']}"
        v = judge(meta)
        v.update(char=meta["char"], action=meta["action"], view=meta["view"], face=meta["face"], group=meta["group"],
                 strip=(jf.with_suffix("").name + ".strip.png") if jf.with_name(jf.stem + ".strip.png").exists() else None)
        res[key] = v
    for jid, st in state.items():                       # jobs that crashed leave no json: they are failures, not gaps
        if st.get("status") != "ok" and jid not in res:
            c, tag = jid.split(":", 1)
            ac, vf = tag.split("__")
            v, f = vf.rsplit("_", 1)
            res[jid] = {"char": c, "action": ac, "view": v, "face": f, "pass": False, "fails": [f"did not run: {st.get('error')}"], "frames": 0}
    (out / "results.json").write_text(json.dumps(res, indent=0), encoding="utf-8")
    n_ok = sum(1 for v in res.values() if v["pass"])
    print(f"action tests: {n_ok}/{len(res)} pass")
    bad = {}
    for k, v in res.items():
        if not v["pass"]:
            bad.setdefault(v["action"], []).append(f"{v['char']} {v['view']}/{v['face']}: {'; '.join(v['fails'])}")
    for ac, lst in sorted(bad.items()):
        print(f"  FAIL {ac}: {len(lst)}  e.g. {lst[0]}")
    return 0 if n_ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())
