"""jobrun.py - run many small Blender jobs in parallel, sized to the RAM, VRAM and CPU that are free (stdlib only, Windows).

    py -3 jobrun.py run <queue.jsonl> [--limits limits.json] [--max N] [--only kind]
    py -3 jobrun.py measure <kind> [--limits limits.json] -- <command ...>      run one job alone, record its peaks
    py -3 jobrun.py status <queue.jsonl>

Queue: one JSON object per line
    {"id": "build:Soldier", "kind": "build", "cmd": ["blender", "-b", ...], "outputs": ["abs/path.blend"], "min_bytes": 2000}
State is kept next to the queue in <queue>.state.json, so an interrupted batch picks up where it stopped: a job whose
state is "ok" and whose outputs still exist is skipped. Every job writes its own log (<queue>.logs/<id>.log) and its own
output files; two jobs never write the same file.

Limits (limits.json), measured with `measure`, per job kind:
    {"build": {"ram_gb": 0.9, "vram_gb": 0.0, "threads": 2, "gpu": false}, ...}
Workers for a kind = min( (free RAM - 4 GB) / ram, (free VRAM - 1 GB) / vram if gpu, 12 / threads ).
Free RAM and VRAM are read again before EVERY launch; a job waits if starting it would break a reserve.
A job that fails (exit code, missing or tiny output = blank frame) lowers the cap of its kind by one and is retried
ALONE at the end; a second failure is final and is reported. A failed job is never counted as a pass.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

RAM_RESERVE_GB = 4.0
VRAM_RESERVE_GB = 1.0
CPU_THREADS = os.cpu_count() or 12
DEFAULT_LIMITS = {"ram_gb": 1.2, "vram_gb": 0.5, "threads": 2, "gpu": True}


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


JOB_TIMEOUT = 1500.0      # seconds; a job may set its own "timeout"

def free_ram_gb() -> float:
    """Free memory a new process can really get: the smaller of free physical RAM and free commit (RAM + page file).
    Windows refuses to start a process when the commit charge is exhausted even if RAM looks free."""
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return min(m.ullAvailPhys, m.ullAvailPageFile) / 2 ** 30


_VRAM = [0.0, (0.0, 0.0)]


def vram_gb() -> tuple[float, float]:
    """(used, total) GB on the first GPU; (0, 0) if nvidia-smi is missing. Read at most once a second: the scheduler asks
    for every pending job, and with thousands of jobs a fresh nvidia-smi each time stalled the whole queue."""
    if time.time() - _VRAM[0] < 1.0:
        return _VRAM[1]
    _VRAM[0] = time.time()
    _VRAM[1] = _vram_now()
    return _VRAM[1]


def _vram_now() -> tuple[float, float]:
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True,
                           text=True, timeout=10).stdout.strip().splitlines()[0]
        u, t = (float(x) for x in o.split(","))
        return u / 1024, t / 1024
    except Exception:
        return 0.0, 0.0


def peak_rss_gb(proc) -> float:
    c = PMC()
    c.cb = ctypes.sizeof(c)
    try:
        k32 = ctypes.windll.kernel32
        k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        if k32.K32GetProcessMemoryInfo(int(proc._handle), ctypes.byref(c), c.cb):
            return c.PeakWorkingSetSize / 2 ** 30
    except Exception:
        pass
    return 0.0


def load_limits(path) -> dict:
    p = Path(path) if path else None
    return json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else {}


def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)


def outputs_ok(job) -> str | None:
    for o in job.get("outputs", []):
        p = Path(o)
        if not p.exists():
            return f"missing output {p.name}"
        if p.stat().st_size < int(job.get("min_bytes", 200)):
            return f"output {p.name} is only {p.stat().st_size} bytes (blank?)"
    return None


def cmd_measure(a):
    kind = a.kind
    limits = load_limits(a.limits)
    v0, _vt = vram_gb()
    t0 = time.time()
    proc = subprocess.Popen(a.cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    peak, vpeak = 0.0, v0
    while proc.poll() is None:
        peak = max(peak, peak_rss_gb(proc))
        vpeak = max(vpeak, vram_gb()[0])
        time.sleep(0.4)
    secs = time.time() - t0
    rec = limits.get(kind, {})
    n = rec.get("samples", 0)
    rec["ram_gb"] = round(max(rec.get("ram_gb", 0.0), peak * 1.15 + 0.05), 2)
    rec["vram_gb"] = round(max(rec.get("vram_gb", 0.0), max(0.0, vpeak - v0) * 1.15), 2)
    rec["gpu"] = rec["vram_gb"] > 0.05
    rec.setdefault("threads", 2)
    rec["secs"] = round((rec.get("secs", secs) * n + secs) / (n + 1), 1)
    rec["samples"] = n + 1
    limits[kind] = rec
    if a.limits:
        Path(a.limits).write_text(json.dumps(limits, indent=1), encoding="utf-8")
    print(f"measure {kind}: exit {proc.returncode}, {secs:.1f}s, peak RAM {peak:.2f} GB, VRAM +{max(0.0, vpeak - v0):.2f} GB -> {rec}")
    return proc.returncode


def cap_for(kind, limits, lowered) -> int:
    L = {**DEFAULT_LIMITS, **limits.get(kind, {})}
    caps = [int((free_ram_gb() - RAM_RESERVE_GB) / max(L["ram_gb"], 0.05)), int(CPU_THREADS / max(1, L["threads"]))]
    if L.get("gpu"):
        u, t = vram_gb()
        if t > 0:
            caps.append(int((t - u - VRAM_RESERVE_GB) / max(L["vram_gb"], 0.05)))
    if L.get("max_workers"):
        caps.append(int(L["max_workers"]))           # e.g. GPU render jobs that do not get faster side by side
    return max(1, min(caps) - lowered.get(kind, 0))


def may_start(kind, limits, running_kinds) -> bool:
    L = {**DEFAULT_LIMITS, **limits.get(kind, {})}
    if free_ram_gb() - L["ram_gb"] < RAM_RESERVE_GB:
        return False
    if L.get("gpu"):
        u, t = vram_gb()
        if t > 0 and (t - u) - L["vram_gb"] < VRAM_RESERVE_GB:
            return False
    used = sum({**DEFAULT_LIMITS, **limits.get(k, {})}["threads"] for k in running_kinds)
    return used + L["threads"] <= CPU_THREADS + 2


def cmd_run(a):
    q = Path(a.queue)
    jobs = [json.loads(line) for line in q.read_text(encoding="utf-8").splitlines() if line.strip()]
    if a.only:
        jobs = [j for j in jobs if j["kind"] == a.only]
    sp = q.with_suffix(".state.json")
    state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    logs = q.with_suffix(".logs")
    logs.mkdir(exist_ok=True)
    limits = load_limits(a.limits)
    lowered: dict[str, int] = {}
    todo = [j for j in jobs if not (state.get(j["id"], {}).get("status") == "ok" and outputs_ok(j) is None)]
    print(f"jobrun: {len(jobs)} jobs, {len(jobs) - len(todo)} already done, {len(todo)} to run; free RAM {free_ram_gb():.1f} GB, "
          f"VRAM used/total {vram_gb()}")
    t_all = time.time()
    running = []                                    # (job, proc, t0, logfile)
    retry_alone = []
    serial_secs = 0.0

    def save():
        sp.write_text(json.dumps(state, indent=0), encoding="utf-8")

    def finish(job, proc, t0, lf):
        nonlocal serial_secs
        lf.close()
        secs = time.time() - t0
        serial_secs += secs
        err = None if proc.returncode == 0 else f"exit code {proc.returncode}"
        err = err or outputs_ok(job)
        if err is None and job.get("fail_if"):
            txt = Path(lf.name).read_text(encoding="utf-8", errors="replace")
            if any(k in txt for k in job["fail_if"]):
                err = "log contains " + next(k for k in job["fail_if"] if k in txt)
        st = state.setdefault(job["id"], {"tries": 0})
        st["tries"] += 1
        st["secs"] = round(secs, 1)
        st["peak_ram_gb"] = round(job.get("_peak", 0.0), 2)
        if err is None:
            st["status"] = "ok"
            st.pop("error", None)
        else:
            st["status"] = "failed"
            st["error"] = err
            try:
                txt = Path(lf.name).read_text(encoding="utf-8", errors="replace")
            except OSError:
                txt = ""
            # a Python traceback or a check that says FAIL is the job's own fault and will fail again at any load: only
            # crashes, kills and blank outputs (the signs of memory pressure) make the runner use fewer workers
            pressure = "Traceback (most recent call last)" not in txt and "FAIL " not in txt
            if pressure:
                lowered[job["kind"]] = lowered.get(job["kind"], 0) + 1
            print(f"  FAILED {job['id']}: {err} ({'workers for ' + repr(job['kind']) + ' lowered; ' if pressure else ''}retry alone: {st['tries'] < 2})", flush=True)
            if st["tries"] < 2:
                retry_alone.append(job)
        save()

    pending = list(todo)
    done_n = 0
    while pending or running:
        for item in list(running):
            job, proc, t0, lf = item
            job["_peak"] = max(job.get("_peak", 0.0), peak_rss_gb(proc))
            if proc.poll() is None and time.time() - t0 > float(job.get("timeout", JOB_TIMEOUT)):
                # a hung job (a Blender left waiting on a lost GPU device) would hold its worker slot for ever
                print(f"  TIMEOUT {job['id']} after {time.time() - t0:.0f}s: killed", flush=True)
                proc.kill()
                proc.wait()
            if proc.poll() is not None:
                running.remove(item)
                finish(job, proc, t0, lf)
                done_n += 1
                if done_n % 10 == 0 or not pending:
                    print(f"  {done_n}/{len(todo)} done, {len(running)} running, {time.time() - t_all:.0f}s", flush=True)
        started = False
        full = set()                                # kinds that cannot take another job right now: skip them without asking again
        kinds_left = {j["kind"] for j in pending}
        for job in list(pending):
            kind = job["kind"]
            if kind in full:
                if full >= kinds_left:
                    break
                continue
            n_kind = sum(1 for r in running if r[0]["kind"] == kind)
            cap = cap_for(kind, limits, lowered)
            if a.max:
                cap = min(cap, a.max)
            if n_kind >= cap or (len(running) and not may_start(kind, limits, [r[0]["kind"] for r in running])):
                full.add(kind)
                continue
            lf = open(logs / (safe(job["id"]) + ".log"), "w", encoding="utf-8", errors="replace")
            for o in job.get("outputs", []):
                Path(o).parent.mkdir(parents=True, exist_ok=True)
            try:
                proc = subprocess.Popen(job["cmd"], stdout=lf, stderr=subprocess.STDOUT, cwd=job.get("cwd"))
            except OSError as ex:                   # the machine refused a new process (out of commit memory): back off, try later
                lf.close()
                lowered[kind] = lowered.get(kind, 0) + 1
                print(f"  could not start {job['id']} ({ex}); workers for '{kind}' lowered, waiting", flush=True)
                time.sleep(8)
                break
            running.append((job, proc, time.time(), lf))
            pending.remove(job)
            started = True
            time.sleep(0.15)                        # let it claim memory before the next check
        if not started:
            time.sleep(0.3)
    for job in retry_alone:                         # one at a time, nothing else running
        lf = open(logs / (safe(job["id"]) + ".retry.log"), "w", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(job["cmd"], stdout=lf, stderr=subprocess.STDOUT, cwd=job.get("cwd"))
        t0 = time.time()
        while proc.poll() is None:
            job["_peak"] = max(job.get("_peak", 0.0), peak_rss_gb(proc))
            if time.time() - t0 > float(job.get("timeout", JOB_TIMEOUT)):
                print(f"  TIMEOUT {job['id']} (retry): killed", flush=True)
                proc.kill()
            time.sleep(0.3)
        retry_alone_before = len(retry_alone)
        finish(job, proc, t0, lf)
        del retry_alone[retry_alone_before:]        # no third try
    wall = time.time() - t_all
    failed = [j["id"] for j in jobs if state.get(j["id"], {}).get("status") != "ok"]
    summary = {"jobs": len(jobs), "ran": len(todo), "failed": failed, "wall_s": round(wall, 1), "sum_job_s": round(serial_secs, 1),
               "speedup": round(serial_secs / wall, 2) if wall > 0 else 0, "lowered": lowered}
    q.with_suffix(".summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("jobrun summary:", json.dumps(summary))
    return 1 if failed else 0


def cmd_status(a):
    q = Path(a.queue)
    jobs = [json.loads(line) for line in q.read_text(encoding="utf-8").splitlines() if line.strip()]
    sp = q.with_suffix(".state.json")
    state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    ok = sum(1 for j in jobs if state.get(j["id"], {}).get("status") == "ok")
    bad = [(j["id"], state[j["id"]].get("error")) for j in jobs if state.get(j["id"], {}).get("status") == "failed"]
    print(f"{ok}/{len(jobs)} ok, {len(bad)} failed, {len(jobs) - ok - len(bad)} not run")
    for i, e in bad:
        print("  FAILED", i, e)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmdname", required=True)
    r = sub.add_parser("run")
    r.add_argument("queue")
    r.add_argument("--limits", default=None)
    r.add_argument("--max", type=int, default=0)
    r.add_argument("--only", default=None)
    m = sub.add_parser("measure")
    m.add_argument("kind")
    m.add_argument("--limits", default=None)
    m.add_argument("cmd", nargs=argparse.REMAINDER)
    st = sub.add_parser("status")
    st.add_argument("queue")
    argv = sys.argv[1:]
    tail = []
    if len(argv) and argv[0] == "measure" and "--" in argv:      # everything after the first "--" is the command to run
        k = argv.index("--")
        argv, tail = argv[:k], argv[k + 1:]
    a = ap.parse_args(argv)
    if a.cmdname == "measure":
        a.cmd = tail or a.cmd
        if a.cmd and a.cmd[0] == "--":
            a.cmd = a.cmd[1:]
        sys.exit(cmd_measure(a))
    sys.exit({"run": cmd_run, "status": cmd_status}[a.cmdname](a))
