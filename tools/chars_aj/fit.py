"""fit.py - make, check and file Aj outfits: garments generated from each body, and BlenderKit dressed characters.

    blender -b --factory-startup --python tools/chars_aj/fit.py -- <command> ...

  custom <outfit> --bodies all|Male_Adult,Female_Kid [--params piece.key=value,...] [--jobs 2]
          build the outfit's garments from each body's own surface (ajkit.templates), run the UNCHANGED fit check
          (ajkit.fitcheck: rest pose, mask, six poses) and save library/wardrobe/fits/<Sex>_<Age>/<outfit>.blend only
          when it passes; a failure goes to output/_staging/wardrobe/<outfit>/<Sex>_<Age>/ with its report.
  addon <item> --bodies ...          the same for an add-on (library/wardrobe/addons/<item>.blend holds one fitted copy
                                     per body, each in its own collection)
  check <file.blend>                 run the fit check on a dressed file (opened, never saved) and print the report
  review <outfit> --bodies ...       render the review sheet of each fit (front, back, side, and the six check poses)
  look-all <item> --bodies ...        wear an add-on through stagekit.cast / aj_wardrobe.wear and render a look sheet (review gate lifted for the test)
  prep <download.blend> --out <name> --body <mesh> --garments a,b   prepare a BlenderKit dressed character (prep_asset)
  rigged <outfit> --source <prepared.blend> --bodies ...            fit it with the pack's fitter (fit_rigged)
  index-check                        validate the wardrobe registry (runs with plain Python too)
  recompute                          recompute fit_ready / fit_ready_bodies (accepted passes only) for every entry

Every command writes or updates the registry entry it concerns (library/wardrobe/index.json) and never sets
`review: "accept"`: the review verdict is somebody else's.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
PIPE = HERE.parents[2]
sys.path.insert(0, str(PIPE / "tools" / "blender"))
os.environ.setdefault("SHORTS_PROJECT", str(PIPE))

BODIES = [f"{s}_{a}" for s in ("Male", "Female") for a in ("Kid", "Teen", "Adult", "Senior")]
AJKIT = PIPE / "tools" / "blender" / "ajkit"
INDEX = PIPE / "library" / "wardrobe" / "index.json"
ALLOWED_LICENCES = {"own", "cc0", "royalty_free"}


# ================================================================================================ limits digest
def _consts(path: Path) -> dict:
    """Top-level constant assignments (literals) and every function's literal default arguments."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            v = node.value
            try:
                if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "dict" and not v.args:
                    out[node.targets[0].id] = {k.arg: ast.literal_eval(k.value) for k in v.keywords}   # LIMITS = dict(...)
                else:
                    out[node.targets[0].id] = ast.literal_eval(v)
            except Exception:
                pass
        if isinstance(node, ast.FunctionDef):
            args = node.args.args[len(node.args.args) - len(node.args.defaults):] + node.args.kwonlyargs
            defs = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
            for a, d in zip(args, defs):
                try:
                    out[f"{node.name}({a.arg})"] = ast.literal_eval(d)
                except Exception:
                    pass
    return out


def _code(path: Path) -> str:
    """The module's code without docstrings and comments (ast.dump), for 'the check algorithm is unchanged'."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body and \
                isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant) and \
                isinstance(node.body[0].value.value, str):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.dump(tree, include_attributes=False)


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=repr).encode()).hexdigest()


PATH_NAMES = ("ROOT", "FINAL", "OUTDIR", "BODY", "ARM", "HAIR_LIB", "HYBRID_HAIR_LIB")


def _limits_only(consts: dict) -> dict:
    """Constants without what vendoring was allowed to change: path names, and the new `arm=None` / `body=None`
    arguments (the armature and body passed in rather than looked up by name)."""
    out = {k: v for k, v in consts.items() if k not in PATH_NAMES}
    return {k: v for k, v in out.items() if not (v is None and (k.endswith("(arm)") or k.endswith("(body)")))}


def limits_digest(path: Path | None = None) -> str:
    """sha256 of fitcheck's LIMITS dict (the numbers every fit is judged by)."""
    return digest(_consts(path or AJKIT / "fitcheck.py").get("LIMITS"))


def limit_report() -> dict:
    """Vendored against pack originals: fitcheck code + constants, the fitters' and grips' constants."""
    from ajkit import paths
    pairs = {"fitcheck": (AJKIT / "fitcheck.py", paths.PACK_SCRIPTS / "fitcheck.py", True),
             "grips": (AJKIT / "grips.py", paths.PACK_SCRIPTS / "grips.py", False),
             "contacts": (AJKIT / "contacts.py", paths.PACK_SCRIPTS / "contacts.py", False),
             "fit_rigged": (AJKIT / "fit_rigged.py", paths.PACK_DRESS_TEST / "fit_rigged.py", False),
             "fit_costume": (AJKIT / "fit_costume.py", paths.PACK_DRESS_TEST / "fit_costume.py", False)}
    rep = {}
    for k, (ours, theirs, whole) in pairs.items():
        if not ours.exists():
            rep[k] = {"vendored": False}
            continue
        e = {"vendored": True, "constants_sha256": digest(_consts(ours))}
        if theirs.exists():
            a, b = _consts(ours), _consts(theirs)
            # paths are not limits: names the vendoring was allowed to change
            a, b = _limits_only(a), _limits_only(b)
            e["constants_match_pack"] = a == b
            miss = object()
            e["differences"] = sorted(n for n in set(a) | set(b) if a.get(n, miss) != b.get(n, miss))
            if whole:
                e["code_matches_pack"] = _code(ours) == _code(theirs)
        rep[k] = e
    rep["LIMITS_sha256"] = limits_digest()
    return rep


# ================================================================================================ registry
def load_index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def save_index(d: dict):
    d["as_of"] = time.strftime("%Y-%m-%d")
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, INDEX)


def rel(p) -> str:
    try:
        return Path(p).resolve().relative_to(PIPE).as_posix()
    except ValueError:
        return str(p)


def register(kind: str, name: str, meta: dict, body: str, fit: dict):
    """Write one body's fit into index.json > <kind>.<name> (kind: outfits | addons). Other entries are untouched;
    an existing review verdict is kept only while the fitted file is the same one it was given for."""
    d = load_index()
    sect = d.setdefault(kind, {})
    e = sect.get(name) or {}
    for k, v in meta.items():
        e[k] = v
    fits = e.setdefault("fits", {})
    old = fits.get(body) or {}
    if old.get("review") not in (None, "none") and old.get("file_sha256") != fit.get("file_sha256"):
        # a changed garment has to be judged again; the old verdict stays on record
        fit["previous_review"] = {k: old[k] for k in ("review", "reviewer", "reviewed_by", "review_file", "avoid", "file_sha256") if k in old}
        fit.setdefault("note", "")
        fit["note"] = (fit["note"] + f" previous review '{old['review']}' was for an older file; reset to none").strip()
        fit["review"] = "none"
    elif old.get("review") not in (None, "none"):
        for k in ("review", "reviewer", "reviewed_by", "review_file", "avoid", "previous_review"):
            if k in old:
                fit[k] = old[k]
    fit.setdefault("review", "none")
    if fit["review"] == "none" and "previous_review" not in fit and old.get("previous_review"):
        fit["previous_review"] = old["previous_review"]           # rebuilt again before anybody judged it: keep the verdict that was replaced
    fits[body] = fit
    recompute_ready(e)
    sect[name] = dict(sorted(e.items(), key=lambda kv: kv[0] != "title"))
    save_index(d)


def recompute_ready(e: dict):
    """fit_ready_bodies: bodies whose fit passed the check and was accepted by a reviewer (a rigid add-on needs no review);
    a rejected, failed or unreviewed pair is not in it."""
    ok = [b for b, f in (e.get("fits") or {}).items() if f.get("status") == "pass" and (f.get("review") == "accept" or
          (e.get("kind") == "rigid" and f.get("review") == "none"))]
    e["fit_ready_bodies"] = ok
    e["fit_ready"] = bool(ok)


def recompute_all() -> int:
    d = load_index()
    for kind in ("outfits", "addons"):
        for e in (d.get(kind) or {}).values():
            recompute_ready(e)
    save_index(d)
    print("recomputed", {k: {n: e.get("fit_ready_bodies") for n, e in (d.get(k) or {}).items()} for k in ("outfits", "addons")})
    return 0


def index_check() -> int:
    d = load_index()
    problems, n = [], 0
    mats = d.get("materials", {})
    cur = limits_digest()
    lr = limit_report()
    if lr["fitcheck"].get("code_matches_pack") is False or lr["fitcheck"].get("constants_match_pack") is False:
        problems.append("ajkit/fitcheck.py differs from the pack original: " + ", ".join(lr["fitcheck"].get("differences", [])))
    for kind in ("outfits", "addons"):
        for name, e in (d.get(kind) or {}).items():
            if e.get("licence") not in ALLOWED_LICENCES:
                problems.append(f"{kind}.{name}: licence {e.get('licence')!r} is not cc0, royalty_free or own")
            for dep in e.get("depends_on", []) or []:
                if dep in mats and mats[dep].get("licence") not in ALLOWED_LICENCES:
                    problems.append(f"{kind}.{name}: depends on {dep} with licence {mats[dep].get('licence')!r}")
            for body, f in (e.get("fits") or {}).items():
                if f.get("status") != "pass":
                    continue
                n += 1
                for k in ("file", "report"):
                    if not f.get(k) or not (PIPE / f[k]).exists() and not Path(f[k]).exists():
                        problems.append(f"{kind}.{name}.{body}: pass without a {k} on disk ({f.get(k)})")
                if f.get("limits_sha256") and f["limits_sha256"] != cur:
                    problems.append(f"{kind}.{name}.{body}: checked against other limits ({f['limits_sha256'][:12]}, now {cur[:12]})")
                who = f.get("reviewer") or f.get("reviewed_by")
                if f.get("review") == "accept" and who in (None, "", "fitter"):
                    problems.append(f"{kind}.{name}.{body}: review accept without a reviewer")
                if f.get("review") in ("accept", "reject") and f.get("review_file") and not (PIPE / f["review_file"]).exists():
                    problems.append(f"{kind}.{name}.{body}: review_file {f['review_file']} does not exist")
                if f.get("review") == "accept" and f.get("reviewer") and not f.get("review_file"):
                    problems.append(f"{kind}.{name}.{body}: review accept by {who} has no review_file")
    print(json.dumps({"passes_checked": n, "limits_sha256": cur, "limit_report": lr, "problems": problems}, indent=1))
    print("INDEX OK" if not problems else f"INDEX PROBLEMS {len(problems)}")
    return 0 if not problems else 1


# ================================================================================================ blender side
def blender_exe() -> str:
    sys.path.insert(0, str(PIPE / "tools"))
    from common import blender_cmd
    return blender_cmd()[0]


def run_child(args: list[str], log: Path) -> int:
    cmd = [blender_exe(), "-b", "--factory-startup", "--python-exit-code", "3", "--python", str(HERE), "--"] + args
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        return subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT)


def bodies_arg(s: str) -> list[str]:
    return BODIES if s in ("all", "") else [b.strip() for b in s.split(",") if b.strip()]


def parse_params(s: str) -> dict:
    out = {}
    for item in [x for x in (s or "").split(",") if x]:
        k, v = item.split("=", 1)
        try:
            v = json.loads(v)
        except Exception:
            pass
        out[k] = v
    return out


def custom_many(outfit: str, bodies: list[str], params: str, jobs: int, kind: str = "outfits") -> int:
    """One Blender per body (each opens its own body file), then the registry is updated here, one writer."""
    from ajkit import paths
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()

    def one(b):
        res = paths.staging_dir(outfit, b) / "result.json"
        if res.exists():
            res.unlink()
        code = run_child(["custom-one", outfit, b, "--params", params, "--kind", kind], paths.staging_dir(outfit, b) / "build.log")
        r = json.loads(res.read_text()) if res.exists() else {"status": "error", "exit": code}
        return b, r
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        results = list(ex.map(one, bodies))
    rows = []
    for b, r in results:
        if r.get("status") in ("pass", "fail"):
            meta = r["meta"]
            fit = {k: r[k] for k in ("status", "file", "report", "file_sha256", "limits_sha256", "build_s", "check_s",
                                     "failures", "note") if k in r}
            fit["review"] = "none"
            fit["review_sheet"] = r.get("review_sheet")
            register(kind, outfit, meta, b, fit)
        rows.append((b, r.get("status"), r.get("build_s"), r.get("check_s"), "; ".join(r.get("failures", [])[:3])))
    for row in rows:
        print("FIT", *row)
    print(f"done in {time.time() - t0:.0f} s")
    return 0 if all(r[1] == "pass" for r in rows) else 1


def custom_one(outfit: str, body_key: str, params: dict, kind: str):
    """Inside Blender: build, check, save (pass -> library, fail -> staging), write result.json."""
    import bpy
    from ajkit import paths, fitcheck, templates as T; TO = T
    stg = paths.staging_dir(outfit, body_key); stg.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(paths.BODIES / f"Aj_{body_key}.blend"))   # read only: never saved here
    arm = bpy.data.objects["Armature"]; body = bpy.data.objects["Aj_Base_Body"]
    t0 = time.time()
    B = T.Body(arm, body)
    col = bpy.data.collections.new(f"Outfit_{outfit}"); bpy.context.scene.collection.children.link(col)
    mine, rigid = [], False
    if kind == "addons":
        mine, base = TO.build_addon(outfit, B, col, params, body_key)
        rigid = TO.ADDONS[outfit]["kind"] == "rigid"
        gs_check = base + ([] if rigid else mine)
    else:
        gs_check = TO.build(outfit, B, col, params, body_key)
    for g in gs_check:
        T.fit_record(g, B)
    t1 = time.time()
    if rigid:
        # a rigid add-on rides on one bone and is placed from the surface: the cloth fit check does not apply. What is
        # measured instead: the base outfit under it still passes, and no vertex of the add-on is inside the skin or the base
        rest = fitcheck.rest_check(arm, body, gs_check) if gs_check else {"pass": True, "failures": [], "garments": {}}
        mask = fitcheck.build_mask(arm, body, gs_check) if gs_check else None
        posed = fitcheck.pose_check(arm, body, gs_check) if gs_check else {"pass": True, "failures": [], "poses": {}}
        inside = rigid_inside(mine, B)
        if inside["max_inside_mm"] > 0.6:
            rest["pass"] = False
            rest["failures"].append({"garment": mine[0].name, "check": "inside the skin", "value": inside["max_inside_mm"], "unit": "mm",
                                     "limit": 0.6, "where": [], "pose": "rest"})
        rest["garments"][mine[0].name] = inside
    else:
        rest = fitcheck.rest_check(arm, body, gs_check)
        mask = fitcheck.build_mask(arm, body, gs_check)
        posed = fitcheck.pose_check(arm, body, gs_check)
    t2 = time.time()
    ok = bool(rest["pass"] and posed["pass"])
    text = fitcheck.summary(rest, mask, posed)
    if kind == "addons":
        text += ("\n## Add-on " + outfit + (": rigid on the " + TO.ADDONS[outfit]["bone"] + " bone" if rigid else ": skinned") +
                 f", built over {TO.ADDONS[outfit].get('base')}; the check above covers the base outfit and the add-on together" +
                 ("; for a rigid add-on the cloth rules do not apply, 'max_inside_mm' is the deepest vertex inside the skin" if rigid else "") + "\n")
    gs = mine if kind == "addons" else gs_check
    text += f"\n## Built by tools/chars_aj/fit.py custom {outfit} (ajkit.templates), {time.strftime('%Y-%m-%d %H:%M')}\n" \
            f"- generated from this body: the fit record is the garment itself, so floating / place / rest stretch / " \
            f"ragged-edge checks compare it with itself; skin, clearance and all pose checks are measured\n" \
            f"- params: {json.dumps(params)}\n- build {t1 - t0:.1f} s, check {t2 - t1:.1f} s\n"
    fails = [f"{f.get('pose', 'rest')}/{f['garment']}: {f['check']} {f['value']} {f['unit']} (limit {f['limit']})"
             for f in rest["failures"] + posed["failures"]]
    LOG = {"outfit": outfit, "body": body_key, "pass": ok, "rest": rest, "mask": mask, "posed": posed,
           "limits_sha256": limits_digest(), "params": params, "pieces": {g.name: {"verts": len(g.data.vertices)} for g in gs}}
    fitcheck.set_mask(body, True)
    if kind == "addons":                                    # the file keeps only the add-on's own objects, in this body's frame
        for o in mine:
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw
            for m in list(o.modifiers):
                if rigid:
                    o.modifiers.remove(m)
                elif m.type == "ARMATURE":
                    m.object = None
            if rigid:
                for vg in list(o.vertex_groups):
                    o.vertex_groups.remove(vg)
            for at in [a for a in o.data.attributes if a.name.startswith("fit_asset")]:
                o.data.attributes.remove(at)
        for o in [o for o in bpy.data.objects if o not in mine]:
            bpy.data.objects.remove(o, do_unlink=True)
    if ok:
        out = paths.fit_file(body_key, outfit) if kind == "outfits" else paths.ADDONS / body_key / f"{outfit}.blend"
        rep_dir = paths.REPORTS / outfit
        for stale in (stg / f"{outfit}_FAILED.blend", stg / f"{body_key}_fit_report.md", stg / f"{body_key}_fit_report.json"):
            if stale.exists():
                stale.unlink()
    else:
        out = stg / f"{outfit}_FAILED.blend"
        rep_dir = stg
        old = paths.fit_file(body_key, outfit) if kind == "outfits" else paths.ADDONS / body_key / f"{outfit}.blend"
        if old.exists():                                   # a pass from an earlier build no longer stands
            old.unlink()
    out.parent.mkdir(parents=True, exist_ok=True); rep_dir.mkdir(parents=True, exist_ok=True)
    rep_md = rep_dir / f"{body_key}_fit_report.md"
    rep_md.write_text(text, encoding="utf-8")
    (rep_dir / f"{body_key}_fit_report.json").write_text(json.dumps(LOG, indent=1, default=float), encoding="utf-8")
    try:
        bpy.ops.file.pack_all()
    except Exception as ex:                                                      # reported, not hidden
        LOG["pack_error"] = str(ex)
    TO.limit_textures(2048)
    bpy.context.preferences.filepaths.save_version = 0            # no .blend1 beside the fit
    bpy.ops.wm.save_as_mainfile(filepath=str(out), copy=True, compress=True)
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    res = {"status": "pass" if ok else "fail", "file": rel(out), "report": rel(rep_md), "file_sha256": sha,
           "limits_sha256": limits_digest(), "build_s": round(t1 - t0, 1), "check_s": round(t2 - t1, 1),
           "failures": fails, "note": "generated from this body (ajkit.templates)",
           "meta": TO.addon_meta(outfit) if kind == "addons" else TO.registry_meta(outfit)}
    (stg / "result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("FITCHECK", "PASS" if ok else "FAIL", out)
    print(text)


def rigid_inside(objs, B) -> dict:
    """How deep the vertices of a rigid add-on stand inside the body's skin, in millimetres (0 = none inside). A vertex is inside
    when a ray from it crosses the skin an odd number of times along +x, -x and +y (two of three): the body has parts the nearest-surface
    sign test cannot tell apart (eyes, mouth, ears), so the depth is then the distance to the nearest skin."""
    from mathutils import Vector

    def crossings(p, d):
        n, o = 0, Vector(p)
        for _ in range(12):
            h = B.bvh.ray_cast(o, d, 3.0)
            if h[0] is None:
                break
            n += 1
            o = h[0] + d * 1e-5
        return n
    worst, n, at = 0.0, 0, None
    for o in objs:
        for v in o.data.vertices:
            p = o.matrix_world @ v.co
            hit, nrm, fi, d = B.bvh.find_nearest(p, 0.15)
            if hit is None or d > 0.15:
                continue
            votes = sum(crossings(p, Vector(dd)) % 2 for dd in ((1, 0, 0), (-1, 0, 0), (0, 1, 0)))
            if votes >= 2:
                if d * 1000 > worst:
                    worst, at = d * 1000, [round(float(c), 3) for c in p]
                n += 1
    return {"max_inside_mm": round(worst, 2), "worst_at": at, "vertices_inside": n, "vertices": sum(len(o.data.vertices) for o in objs)}


def check_file(path: str):
    import bpy
    from ajkit import fitcheck
    bpy.ops.wm.open_mainfile(filepath=path)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    body = bpy.data.objects.get("Aj_Base_Body") or next(o for o in bpy.data.objects if o.type == "MESH" and o.parent == arm and not o.name.startswith("D_"))
    gs = [o for o in bpy.data.objects if o.type == "MESH" and o.data.attributes.get("fit_asset_co") and not o.name.startswith("REF_")]
    rest = fitcheck.rest_check(arm, body, gs)
    mask = fitcheck.build_mask(arm, body, gs)
    posed = fitcheck.pose_check(arm, body, gs)
    print(fitcheck.summary(rest, mask, posed))
    print("FITCHECK", "PASS" if rest["pass"] and posed["pass"] else "FAIL", path)


def review_one(outfit: str, body_key: str, kind: str = "outfits"):
    """Front, back, side at rest, then the six check poses (front and side), and close-ups of every opening."""
    import bpy, math
    from ajkit import paths, fitcheck, stage, sheetutil
    f = paths.fit_file(body_key, outfit) if kind == "outfits" else paths.ADDONS / body_key / f"{outfit}.blend"
    if not f.exists():
        f = paths.staging_dir(outfit, body_key) / f"{outfit}_FAILED.blend"
    bpy.ops.wm.open_mainfile(filepath=str(f))
    arm = bpy.data.objects["Armature"]; body = bpy.data.objects["Aj_Base_Body"]
    fitcheck.set_mask(body, True)
    stage.setup_stage()
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 420, 640
    H = max((arm.matrix_world @ b.head_local).z for b in arm.data.bones if b.name.endswith("HeadTop_End"))
    out = paths.staging_dir(outfit, body_key) / "review"; out.mkdir(parents=True, exist_ok=True)
    files = []
    cam = sc.camera

    def shot(tag, ang, tz=None, dist=None, lens=55):
        cam.data.type = "PERSP"; cam.data.lens = lens
        r = math.radians(ang); d = dist or H * 2.9; z = tz if tz is not None else H * 0.52
        cam.location = (math.sin(r) * d, -math.cos(r) * d, z + 0.05)
        stage.look_at(cam, (0, 0, z))
        files.append(stage.render(str(out / f"{tag}_{ang}.png")))
    fitcheck.apply_pose(arm, {})
    arm.data.pose_position = "POSE"
    poses = fitcheck.standard_poses(arm)
    fitcheck.apply_pose(arm, poses["arms_down"])
    for ang in (0, 180, 90, 35):
        shot("relaxed", ang)
    for pn in ("arms_up", "arms_forward", "stride", "sit", "bend"):
        fitcheck.apply_pose(arm, poses[pn])
        shot(pn, 0); shot(pn, 90)
    fitcheck.apply_pose(arm, poses["arms_down"])
    shot("upper", 20, tz=H * 0.72, dist=H * 1.3)
    shot("lower", 200, tz=H * 0.35, dist=H * 1.4)
    shot("shoe_34", 35, tz=H * 0.035, dist=H * 0.62)          # the shoes close up: three-quarter, side, from above
    shot("shoe_side", 90, tz=H * 0.035, dist=H * 0.62)
    cam.location = (0.0, -H * 0.30, H * 0.50); stage.look_at(cam, (0, -0.02, 0.02))
    files.append(stage.render(str(out / "shoe_top_0.png")))
    fitcheck.apply_pose(arm, poses["sit"])
    shot("sit_back", 160, tz=H * 0.35, dist=H * 1.4)
    shot("sit_front", 0, tz=H * 0.38, dist=H * 1.5)
    shot("sit_side", 90, tz=H * 0.38, dist=H * 1.5)
    sheet = paths.staging_dir(outfit, body_key) / f"{body_key}_{outfit}_review.png"
    sheetutil.sheet(files, str(sheet), cols=6)
    for p in files:
        try:
            os.remove(p)
        except OSError:
            pass
    print("REVIEW SHEET", sheet)



def addon_look(item: str, body_key: str, outfit: str = ""):
    """Wear the add-on through the real loader (stagekit.cast -> aj_wardrobe.wear) on a character of this body in the outfit it was
    built over, and render a sheet: four turns, close-ups, arms up, sitting (front, back). The wardrobe's review gate is lifted for this
    test only (an unreviewed fit is refused by the loader), nothing is saved. Writes output/_staging/wardrobe/<item>/<body>/<body>_<item>_look.png"""
    import math
    import bpy
    import numpy as np
    from mathutils import Vector
    sys.path.insert(0, str(PIPE / "tools" / "blender"))
    import stagekit
    from stagekit import aj_wardrobe, cast, cast_aj, lights
    from ajkit import paths, templates as TO
    spec = TO.ADDONS[item]
    base_outfit = outfit or spec.get("base") or "shirt_trousers"
    ent0 = cast_aj.entry(body_key)
    via_wear = os.environ.get("ADDON_VIA_WEAR") == "1"        # actor.wear() after placing (the shot-time path) instead of the cast entry
    ent = dict(ent0, name="T", outfit=base_outfit, addons=[] if via_wear else [{"item": item}], bare=False, era=["modern"], height_m=None)
    cast_aj.entry = lambda b: dict(ent) if b == "T" else ent0
    aj_wardrobe.fit_ok = lambda f, rigid=False: bool(f) and f.get("status") == "pass"
    out = paths.staging_dir(item, body_key); out.mkdir(parents=True, exist_ok=True)
    W, H_ = 360, 540
    shot = stagekit.begin("addon_look", 8.0, "draft")
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = W, H_
    sc.render.resolution_percentage = 100
    lights.rig("day_clear", sun_from=35.0)
    m = bpy.data.materials.new("floor"); m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.52, 0.47, 1)
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0)); bpy.context.active_object.data.materials.append(m)
    act = cast.actor("t", "T", at=(0, 0), face="right", view="front", costume={"wear": [{"item": item}]} if via_wear else None)
    act.heading(0.0)
    act.pose("rest", 0.0, 0.0)
    act.legs(0.0, 0.0, 0.0, 0.0)                              # legs straight until the sit (a pose with no legs key holds the first key)
    act.pose("cheer", 2.0, 0.3)
    act.legs(0.0, 0.0, 3.0, 0.0)
    act.pose("rest", 3.3, 0.2)
    act.pose("sit", 4.0, 0.3)
    for x in shot.actors.values():
        x._finalize()
    cd = bpy.data.cameras.new("cam"); cd.lens = 55
    cam = bpy.data.objects.new("cam", cd); sc.collection.objects.link(cam); sc.camera = cam
    Hh = act.height

    def look(at, aim, ortho=None):
        cd.type = "ORTHO" if ortho else "PERSP"
        if ortho:
            cd.ortho_scale = ortho
        cam.location = Vector(at)
        cam.rotation_euler = (Vector(aim) - Vector(at)).to_track_quat("-Z", "Y").to_euler()

    def render(tag, frame):
        sc.frame_set(frame)
        sc.render.filepath = str(out / f"_{tag}.png")
        bpy.ops.render.render(write_still=True)
        return out / f"_{tag}.png"
    fx, fz, fd = {"tie": (0, .68, .85), "lanyard_badge": (0, .66, .85), "blazer": (0, .64, 1.2), "cardigan": (0, .64, 1.2), "belt": (0, .52, .8),
                  "glasses": (0, .92, .55), "wrist_watch": (0.25, .5, .7)}.get(item, (0, .6, 1.0))
    tiles = []
    f0, fc, fs = 1, shot.f(2.1), shot.f(4.1)

    def turn(ang, frame, zf=0.5, dist=3.0, ortho=None):
        r = math.radians(ang)
        d = dist * Hh
        look((math.sin(r) * d, -math.cos(r) * d, zf * Hh), (0, 0, zf * Hh), ortho)
    for ang in (0, 40, 90, 180):
        turn(ang, f0, 0.52, 1.5 if False else 3.0, ortho=Hh * 1.25); tiles.append(render(f"t{ang}", f0))
    for ang in (0, 35, 150):
        turn(ang, f0, fz, fd * 1.0, None); tiles.append(render(f"c{ang}", f0))
    turn(0, fc, 0.55, 3.0, Hh * 1.3); tiles.append(render("cheer", fc))
    turn(0, fs, 0.42, 3.0, Hh * 1.3); tiles.append(render("sitf", fs))
    turn(160, fs, 0.42, 3.0, Hh * 1.3); tiles.append(render("sitb", fs))
    turn(90, fs, 0.42, 3.0, Hh * 1.3); tiles.append(render("sits", fs))
    cols = 6
    ims = [bpy.data.images.load(str(t_)) for t_ in tiles]
    rows = (len(ims) + cols - 1) // cols
    canvas = np.ones((rows * H_, cols * W, 4), dtype=np.float32) * 0.12
    for i, im in enumerate(ims):
        px = np.array(im.pixels[:], dtype=np.float32).reshape(H_, W, 4)
        r_, c_ = divmod(i, cols)
        canvas[(rows - 1 - r_) * H_:(rows - r_) * H_, c_ * W:(c_ + 1) * W] = px
    img = bpy.data.images.new("sheet", cols * W, rows * H_, alpha=True)
    img.pixels.foreach_set(canvas.ravel()); img.filepath_raw = str(out / f"{body_key}_{item}_look.png"); img.file_format = "PNG"; img.save()
    for t_ in tiles:
        try:
            os.remove(t_)
        except OSError:
            pass
    print("LOOK SHEET", out / f"{body_key}_{item}_look.png", "worn:", aj_wardrobe.describe(act))


# ================================================================================================ main
def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="fit.py")
    ap.add_argument("command")
    ap.add_argument("name", nargs="?")
    ap.add_argument("body", nargs="?")
    ap.add_argument("--bodies", default="all")
    ap.add_argument("--params", default="")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--kind", default="outfits")
    ap.add_argument("--source", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--garments", default="")
    a = ap.parse_args(argv)
    c = a.command
    if c == "index-check":
        return index_check()
    if c == "recompute":
        return recompute_all()
    if c == "limits":
        print(json.dumps(limit_report(), indent=1))
        return 0
    if c in ("custom", "addon"):
        return custom_many(a.name, bodies_arg(a.bodies), a.params, a.jobs, "addons" if c == "addon" else "outfits")
    if c == "custom-one":
        custom_one(a.name, a.body, parse_params(a.params), a.kind)
        return 0
    if c == "check":
        check_file(a.name)
        return 0
    if c == "look-all":
        from ajkit import paths
        for b in bodies_arg(a.bodies):
            code = run_child(["look", a.name, b], paths.staging_dir(a.name, b) / "look.log")
            print("LOOK", b, "ok" if code == 0 else f"exit {code}", paths.staging_dir(a.name, b) / f"{b}_{a.name}_look.png")
        return 0
    if c == "review":
        from ajkit import paths
        for b in bodies_arg(a.bodies):
            code = run_child(["review-one", a.name, b, "--kind", a.kind], paths.staging_dir(a.name, b) / "review.log")
            print("REVIEW", b, "ok" if code == 0 else f"exit {code}", paths.staging_dir(a.name, b) / f"{b}_{a.name}_review.png")
        return 0
    if c == "look":
        addon_look(a.name, a.body, a.params)
        return 0
    if c == "review-one":
        review_one(a.name, a.body, a.kind)
        return 0
    if c == "prep":
        return prep(a.name, a.out, a.body, a.garments)
    if c == "rigged":
        return rigged(a.name, a.source, bodies_arg(a.bodies))
    ap.error(f"unknown command {c}")
    return 2


def prep(download: str, out_name: str, body_obj: str, garments: str) -> int:
    """prep_asset check, then convert into library/_downloads/_prepared/<out_name>.blend, then check that."""
    from ajkit import paths
    script = str(AJKIT / "prep_asset.py")
    exe = blender_exe()
    paths.PREPARED.mkdir(parents=True, exist_ok=True)
    out = paths.PREPARED / f"{out_name}.blend"
    subprocess.call([exe, "-b", download, "--factory-startup", "--python", script, "--", "check"])
    if not (body_obj and garments):
        return 0
    code = subprocess.call([exe, "-b", download, "--factory-startup", "--python", script, "--", str(out), body_obj, garments])
    if code or not out.exists():
        print("PREP FAILED", code)
        return 1
    return subprocess.call([exe, "-b", str(out), "--factory-startup", "--python", script, "--", "check"])


def rigged(outfit: str, source: str, bodies: list[str]) -> int:
    """The pack's fitter per body; a pass is copied to library/wardrobe/fits/<body>/<outfit>.blend."""
    import shutil
    from ajkit import paths
    exe = blender_exe()
    for b in bodies:
        sx, ag = b.split("_")
        stg = paths.staging_dir(outfit, b); stg.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        with open(stg / "rigged.log", "w", encoding="utf-8", errors="replace") as fh:
            subprocess.call([exe, "-b", "--factory-startup", "--python", str(AJKIT / "fit_rigged.py"), "--", sx, ag, source, outfit],
                            stdout=fh, stderr=subprocess.STDOUT)
        log = (stg / "rigged.log").read_text(encoding="utf-8", errors="replace")
        passed = f"FITCHECK PASS" in log
        rep = stg / f"{b}_fit_report.md"
        fit = {"status": "pass" if passed else "fail", "report": rel(rep), "limits_sha256": limits_digest(),
               "build_s": round(time.time() - t0, 1), "note": f"fit_rigged from {rel(source)}"}
        if passed:
            src = stg / "pass" / f"Aj_{b}_{outfit}.blend"
            dst = paths.fit_file(b, outfit); dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            rd = paths.REPORTS / outfit; rd.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(rep, rd / rep.name)
            fit.update(file=rel(dst), report=rel(rd / rep.name), file_sha256=hashlib.sha256(dst.read_bytes()).hexdigest())
        elif "ASSET NOT READY" in log:
            fit["status"] = "fail"; fit["note"] += "; ASSET NOT READY"
        else:
            failed = stg / f"Aj_{b}_{outfit}_FAILED.blend"
            fit["file"] = rel(failed) if failed.exists() else None
        from ajkit import templates as TO
        register("outfits", outfit, TO.rigged_meta(outfit, source), b, fit)
        print("FIT", b, fit["status"], fit.get("report"))
    return 0


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        code = main(argv)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    if "bpy" in sys.modules and code:
        sys.exit(code)
    elif "bpy" not in sys.modules:
        sys.exit(code)
