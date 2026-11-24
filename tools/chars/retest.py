"""retest.py - re-measure given combinations (no pictures) and print the frames where a check is off. Stdlib only.

    py -3 retest.py <out-dir> Char:action:view:face [Char:action:view:face ...] [--show foot_slide]
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charpaths as P  # noqa: E402
import actiontests as AT  # noqa: E402

args = sys.argv[1:]
show = "foot_slide"
if "--show" in args:
    i = args.index("--show")
    show = args[i + 1]
    del args[i:i + 2]
out = Path(args[0]).resolve()


def one(spec):
    n, ac, v, f = spec.split(":")
    cmd = [P.BL, "-b", "--factory-startup", "--threads", "2", "--python", str(P.TOOLS / "bl" / "action_test.py"), "--", "--pipeline", str(P.PIPELINE),
           "--char", n, "--action", ac, "--view", v, "--face", f, "--pack", str(P.LIB), "--out", str(out), "--chars-dir", str(P.CHARS), "--no-render"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    j = out / n / f"{ac}__{v}_{f}.json"
    if not j.exists():
        return spec, None, (r.stdout + r.stderr)[-1500:]
    return spec, json.loads(j.read_text(encoding="utf-8")), ""


with ThreadPoolExecutor(5) as ex:
    for spec, d, err in ex.map(one, args[1:]):
        if d is None:
            print(spec, "NO RESULT", err)
            continue
        v = AT.judge(d)
        rows = d["rows"]
        vals = [(r.get("frame", i), r.get(show)) for i, r in enumerate(rows)]
        top = sorted([x for x in vals if isinstance(x[1], (int, float))], key=lambda x: -abs(x[1]))[:6]
        print(spec, "PASS" if not v["fails"] else "FAIL " + "; ".join(v["fails"]), "| frames", len(rows), "| worst", show, top)
