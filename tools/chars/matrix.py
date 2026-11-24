"""matrix.py - the whole action test matrix as ONE resumable queue (measure jobs on the CPU beside render jobs on the GPU).

    py -3 matrix.py [--out <dir>] [--dry]

What the machine allows (measured, see PROGRESS.md): a small EEVEE
render job is CPU-bound like the rest (the scene and its outline nodes are evaluated per frame; the GPU sits near 0 %), so
the whole matrix is about 15 hours of single-process work and the 6 cores bring it to about 2 hours. To fit, every frame
of the full matrix is MEASURED (no pictures, 4 s a job) and strips + MP4s are RENDERED for a representative subset.

MEASURED on every frame (pass / fail numbers):
  M1  every action  x 5 standard body types (AdultMan, Boy, Baby, SeniorMan, Queen)  x 3 views x 2 facings
  M2  every action  x 10 unusual bodies                                               x 3q:right, side:left, front:right
  M3  the 8 core actions x all 105 characters                                         x 3q:right, side:left, front:right
RENDERED (strip of every 2nd frame + MP4 at full speed), also measured:
  R1  every action on AdultMan                x 3q:right, side:left, front:right  (core actions: all six)
  R2  the body-dependent actions (30) on Boy, Baby, SeniorMan, Queen   x 3q:right
  R3  the body-dependent actions on the 10 unusual bodies  x 3q:right
  R4  walk and pick_up on every other character (90)        x 3q:right
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charpaths as P  # noqa: E402
import actiontests as AT  # noqa: E402
import mkqueue  # noqa: E402

STD = ["AdultMan", "Boy", "Baby", "SeniorMan", "Queen"]
UNUSUAL = ["Ghost", "Mermaid", "Dragon", "Fairy", "Robot", "Alien", "Werewolf", "Mummy", "Genie", "Goblin"]
BODY_ACTIONS = AT.CORE + ["run", "sneak", "stand_up", "kneel", "crouch", "jump", "climb", "hang", "swim", "lie_down", "fall", "curtsy", "stomp", "ride",
                          "carry", "throw", "wave", "laugh", "cheer", "bow", "juggle", "slip_banana"]
SIX = AT.ALL_COMBOS
THREE = ["3q:right", "side:left", "front:right"]


def jobs_for(names, acts, render, measure, out, px=256):
    jobs = []
    for n in names:
        for ac in acts:
            for combo, rend in [(c, True) for c in render] + [(c, False) for c in measure if c not in render]:
                v, f = combo.split(":")
                tag = f"{ac}__{v}_{f}"
                cmd = [P.BL, "-b", "--factory-startup", "--threads", "2", "--python", str(P.TOOLS / "bl" / "action_test.py"), "--",
                       "--pipeline", str(P.PIPELINE), "--char", n, "--action", ac, "--view", v, "--face", f, "--pack", str(P.LIB), "--out", str(out),
                       "--px", str(px), "--chars-dir", str(P.CHARS), "--frame-step", "2"] + ([] if rend else ["--no-render"])
                jobs.append({"id": f"{n}:{tag}", "kind": "action" if rend else "measure", "outputs": [str(out / n / f"{tag}.json")], "min_bytes": 300,
                             "fail_if": ["Traceback (most recent call last)"], "cmd": cmd, "post": [n, tag] if rend else None})
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(P.OUT / "actiontests_final"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    acts = AT.action_names()
    cast = mkqueue.all_names()
    other = [x for x in acts if x not in AT.CORE]
    J = []
    J += jobs_for(["AdultMan"], AT.CORE, SIX, [], out)                                  # R1 core, all six
    J += jobs_for(["AdultMan"], other, THREE, SIX, out)                                 # R1 + M1
    J += jobs_for(STD[1:], BODY_ACTIONS, ["3q:right"], SIX, out)                        # R2 + M1
    J += jobs_for(STD[1:], [x for x in acts if x not in BODY_ACTIONS], [], SIX, out)    # M1
    J += jobs_for(UNUSUAL, BODY_ACTIONS, ["3q:right"], THREE, out)                      # R3 + M2
    J += jobs_for(UNUSUAL, [x for x in acts if x not in BODY_ACTIONS], [], THREE, out)  # M2
    rest = [c for c in cast if c not in STD + UNUSUAL]
    J += jobs_for(rest, ["walk", "pick_up"], ["3q:right"], THREE, out)                              # R4 + M3
    J += jobs_for(rest, ["hand_over", "sit_down", "point", "hold_up", "gasp", "talk"], [], THREE, out)   # M3
    seen, uniq = set(), []
    for j in J:
        if j["id"] not in seen:
            seen.add(j["id"])
            uniq.append(j)
    uniq.sort(key=lambda j: j["kind"] != "action")                                       # renders first in the file; kinds run side by side
    q = P.QUEUES / "actions_matrix.jsonl"
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_text("\n".join(json.dumps(j) for j in uniq) + "\n", encoding="utf-8")
    nr = sum(1 for j in uniq if j["kind"] == "action")
    print(f"matrix: {len(uniq)} jobs ({nr} rendered, {len(uniq) - nr} measured only) -> {q}")
    if a.dry:
        return 0
    if not a.report_only:
        subprocess.run([sys.executable, str(P.TOOLS / "jobrun.py"), "run", str(q), "--limits", str(P.LIMITS)])
    import action_media
    n = 0
    for j in uniq:
        if j.get("post") and (out / j["post"][0] / "frames" / j["post"][1]).exists():
            try:
                action_media.one(out, j["post"][0], j["post"][1], step=1, cols=12, scale=110, fps=12)
                n += 1
            except Exception as ex:
                print("media failed", j["id"], ex)
    print(f"strips + mp4 written for {n} jobs")
    return subprocess.run([sys.executable, str(P.TOOLS / "actiontests.py"), "--report", "--out", str(out)]).returncode


if __name__ == "__main__":
    sys.exit(main())
