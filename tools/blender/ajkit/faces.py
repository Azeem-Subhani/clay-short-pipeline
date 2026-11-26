# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/faces.py (Aj pack, 2026-11-26), unchanged: every
# function already takes the body as an argument (body=None falls back to the name "Aj_Base_Body").
"""Aj's rest-space face controls, for use inside Blender.

    import faces
    faces.add_face_keys()               # idempotent; preserves current values
    faces.apply_preset("Senior Soft")   # preserves expression, gaze and body controls
    faces.apply_preset("Teen Classic")  # zero all sculpt controls

The same presets work on either base. All lengths are in world metres, with
Aj facing -Y. Material names distinguish the floating eyeballs and brow/lash
islands from the skin. Vertex indices are never hardcoded as landmarks; all
regions and smooth transitions are computed from rest-pose positions and mesh
edge connectivity, so the keys match across any vertex permutation.
"""

import bpy
import numpy as np

BODY = "Aj_Base_Body"
EYE_CENTER = np.array((0.071, -0.165, 1.5805), dtype=np.float64)
EYE_MAT = "Aj_Eye_MAT"
BROW_LASH_MAT = "Aj_BrowLash_MAT"
EYE_SIDES = (("L", 1.0), ("R", -1.0))
EYE_SCALE = 0.105

# The keys are signed. Positive values enlarge, open, widen, raise, upturn,
# extend, or project the corresponding feature.
CONTROLS = (
    "Eye_Size", "Eye_Aperture", "Eye_Spacing", "Eye_Height", "Eye_Tilt",
    "Nose_Size", "Nose_Length", "Nose_Width", "Nose_Bridge", "Nose_Tip",
    "Upper_Cheek",
)
KEY_NAMES = tuple("Face_" + name for name in CONTROLS)

# Each face is a starting point for either body. Adult and senior alternatives
# cover distinct archetypes within the same age group.
PRESETS = {
    "Teen Classic": {},
    "Kid Round": dict(
        Eye_Size=0.90, Eye_Aperture=0.88, Eye_Spacing=0.35, Eye_Height=-0.76, Eye_Tilt=-0.06,
        Nose_Size=-0.88, Nose_Length=-0.55, Nose_Width=0.12, Nose_Bridge=-0.68, Nose_Tip=-0.45,
        Upper_Cheek=0.92,
    ),
    "Kid Bright": dict(
        Eye_Size=0.48, Eye_Aperture=0.98, Eye_Spacing=-0.42, Eye_Height=-0.42, Eye_Tilt=0.68,
        Nose_Size=-0.58, Nose_Length=-0.30, Nose_Width=0.22, Nose_Bridge=-0.45, Nose_Tip=0.55,
        Upper_Cheek=0.64,
    ),
    "Teen Tapered": dict(
        Eye_Size=0.06, Eye_Aperture=-0.56, Eye_Spacing=0.28, Eye_Height=0.30, Eye_Tilt=0.82,
        Nose_Size=-0.22, Nose_Length=0.22, Nose_Width=-0.65, Nose_Bridge=0.38, Nose_Tip=0.15,
        Upper_Cheek=-0.22,
    ),
    "Adult Broad": dict(
        Eye_Size=-0.50, Eye_Aperture=-0.68, Eye_Spacing=0.88, Eye_Height=0.64, Eye_Tilt=-0.22,
        Nose_Size=0.84, Nose_Length=0.56, Nose_Width=1.00, Nose_Bridge=0.58, Nose_Tip=0.34,
        Upper_Cheek=-0.35,
    ),
    "Adult Sculpted": dict(
        Eye_Size=-0.34, Eye_Aperture=-0.42, Eye_Spacing=-0.62, Eye_Height=0.48, Eye_Tilt=0.46,
        Nose_Size=0.34, Nose_Length=0.80, Nose_Width=-0.80, Nose_Bridge=0.95, Nose_Tip=-0.20,
        Upper_Cheek=0.72,
    ),
    "Senior Strong": dict(
        Eye_Size=-0.72, Eye_Aperture=-0.82, Eye_Spacing=-0.46, Eye_Height=0.72, Eye_Tilt=-0.92,
        Nose_Size=0.88, Nose_Length=0.90, Nose_Width=0.45, Nose_Bridge=0.95, Nose_Tip=0.58,
        Upper_Cheek=-0.88,
    ),
    "Senior Soft": dict(
        Eye_Size=-0.66, Eye_Aperture=-0.58, Eye_Spacing=0.45, Eye_Height=-0.38, Eye_Tilt=-0.72,
        Nose_Size=0.42, Nose_Length=0.78, Nose_Width=0.24, Nose_Bridge=0.32, Nose_Tip=0.42,
        Upper_Cheek=0.64,
    ),
}


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _positions(data):
    coords = np.empty(len(data) * 3, dtype=np.float32)
    data.foreach_get("co", coords)
    return coords.reshape(-1, 3)


def _material_vertices(mesh, name):
    slots = {i for i, mat in enumerate(mesh.materials) if mat and mat.name.split(".")[0] == name}
    mask = np.zeros(len(mesh.vertices), dtype=bool)
    for polygon in mesh.polygons:
        if polygon.material_index in slots:
            mask[list(polygon.vertices)] = True
    return mask


def _skin_graph(mesh, points, skin):
    """Build symmetric inverse-distance edge weights on skin vertices (order-invariant)."""
    edges = np.empty(len(mesh.edges) * 2, dtype=np.int64)
    mesh.edges.foreach_get("vertices", edges)
    edges = edges.reshape(-1, 2)
    keep = skin[edges[:, 0]] & skin[edges[:, 1]]
    edges = edges[keep]
    dists = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
    w = 1.0 / np.maximum(dists, 1e-4)
    return edges[:, 0], edges[:, 1], w


def _solve_harmonic(n, u, v, w, free_mask, fixed_vals):
    """Solve graph Laplacian L x = 0 on free_mask with Dirichlet boundary values elsewhere.

    Works for scalar (n,) or vector (n, k) arrays; returns exact fixed_vals outside free_mask.
    """
    out = fixed_vals.copy()
    free_idx = np.flatnonzero(free_mask)
    m = len(free_idx)
    if m == 0:
        return out
    loc = np.full(n, -1, dtype=np.int64)
    loc[free_idx] = np.arange(m)

    diag = np.bincount(u, weights=w, minlength=n) + np.bincount(v, weights=w, minlength=n)
    A = np.diag(np.maximum(diag[free_idx], 1e-12))

    ii = free_mask[u] & free_mask[v]
    if ii.any():
        lu, lv, lw = loc[u[ii]], loc[v[ii]], w[ii]
        np.add.at(A, (lu, lv), -lw)
        np.add.at(A, (lv, lu), -lw)

    rhs_shape = (m,) if fixed_vals.ndim == 1 else (m, fixed_vals.shape[1])
    rhs = np.zeros(rhs_shape, dtype=np.float64)
    ub = free_mask[u] & (~free_mask[v])
    if ub.any():
        val = fixed_vals[v[ub]]
        rhs_add = (w[ub] * val) if fixed_vals.ndim == 1 else (w[ub, None] * val)
        np.add.at(rhs, loc[u[ub]], rhs_add)
    vb = free_mask[v] & (~free_mask[u])
    if vb.any():
        val = fixed_vals[u[vb]]
        rhs_add = (w[vb] * val) if fixed_vals.ndim == 1 else (w[vb, None] * val)
        np.add.at(rhs, loc[v[vb]], rhs_add)

    sol = np.linalg.solve(A, rhs)
    out[free_idx] = sol
    return out


def _solve_screened(n, u, v, w, free_mask, target, gamma):
    """Solve screened Poisson (L + gamma*I) x = gamma*target on free_mask with x = 0 outside."""
    out = np.zeros_like(target, dtype=np.float64)
    free_idx = np.flatnonzero(free_mask)
    m = len(free_idx)
    if m == 0:
        return out
    loc = np.full(n, -1, dtype=np.int64)
    loc[free_idx] = np.arange(m)

    diag = np.bincount(u, weights=w, minlength=n) + np.bincount(v, weights=w, minlength=n)
    A = np.diag(diag[free_idx] + gamma)
    ii = free_mask[u] & free_mask[v]
    if ii.any():
        lu, lv, lw = loc[u[ii]], loc[v[ii]], w[ii]
        np.add.at(A, (lu, lv), -lw)
        np.add.at(A, (lv, lu), -lw)

    rhs = gamma * target[free_idx]
    out[free_idx] = np.linalg.solve(A, rhs)
    return out


def _relax_field(n, u, v, w, field, movable_mask, iters=3, alpha=0.45):
    """Weighted Laplacian smoothing inside movable_mask while pinning ~movable_mask."""
    out = field.copy()
    diag = np.maximum(np.bincount(u, weights=w, minlength=n) + np.bincount(v, weights=w, minlength=n), 1e-12)
    idx = np.flatnonzero(movable_mask)
    if len(idx) == 0:
        return out
    for _ in range(iters):
        if out.ndim == 1:
            acc = np.bincount(u, weights=w * out[v], minlength=n) + np.bincount(v, weights=w * out[u], minlength=n)
            avg = acc / diag
        else:
            acc = np.column_stack([
                np.bincount(u, weights=w * out[v, c], minlength=n) + np.bincount(v, weights=w * out[u, c], minlength=n)
                for c in range(out.shape[1])
            ])
            avg = acc / diag[:, None]
        out[idx] += alpha * (avg[idx] - out[idx])
    return out


def _outer_lid_damp(pts):
    """Taper eyelid motion cleanly near the outer eye corner and upper-outer temple transition."""
    ax = np.abs(pts[:, 0])
    z = pts[:, 2]
    lat = 1.0 - 0.72 * _smooth((ax - 0.095) / 0.022)
    upper_outer = 1.0 - 0.35 * _smooth((ax - 0.090) / 0.024) * _smooth((z - 1.586) / 0.020)
    return lat * upper_outer


def _eye_control_eval(pts, control, side_sign):
    """Analytic rest-space displacement of eyelid/lash points for Eye_Size, Eye_Aperture, Eye_Tilt."""
    u = np.abs(pts[:, 0]) - EYE_CENTER[0]
    v = pts[:, 1] - EYE_CENTER[1]
    w = pts[:, 2] - EYE_CENTER[2]
    zero = np.zeros(len(pts), dtype=np.float64)
    if control == "Eye_Size":
        raw = np.column_stack((side_sign * 0.13 * u, 0.06 * v, 0.13 * w))
    elif control == "Eye_Aperture":
        k_ap = 0.14 + 0.14 * _smooth((w + 0.008) / 0.016)
        raw = np.column_stack((zero, zero, k_ap * w))
    elif control == "Eye_Tilt":
        tilt = 0.19
        raw = np.column_stack((-side_sign * tilt * w, 0.25 * (-tilt * w), tilt * u))
    else:
        raise ValueError(control)
    return raw * _outer_lid_damp(pts)[:, None]


def _lid_and_perimeter(mesh, points, eye, detail, blocks, linear):
    """Compute skin masks, authored eyelid core (plus rest canthus seam), and skin graph."""
    n = len(points)
    skin = ~(eye | detail)
    x, y, z = points.T
    ax = np.abs(x)
    side = np.where(x >= 0.0, 1.0, -1.0)

    # Protected outer boundary strictly inside scalp, ears, jaw/head outline, mouth atlas, and all hair/beard fits
    # (including outer temple triangles overlapping deep Hy3D fringe/lock meshes).
    z_floor = (
        1.5125
        + 0.004 * np.clip((ax - 0.020) / 0.025, 0.0, 1.0)
        + 0.014 * np.clip((ax - 0.088) / 0.038, 0.0, 1.0)
    )
    z_ceil = 1.664 - 0.036 * np.clip((ax - 0.055) / 0.060, 0.0, 1.0)
    allowed_skin = skin & (ax < 0.1173) & (y < -0.168) & (z > z_floor) & (z < z_ceil)
    fixed_skin = skin & (~allowed_skin)

    # Identify front eyelid skin from authored EyeBlink keys plus the rest canthus seam vertices
    # (order-invariant), with position fallback.
    blink_moved = np.zeros(n, dtype=bool)
    for bname in ("EyeBlink_L", "EyeBlink_R"):
        if bname in blocks:
            bdelta = (_positions(blocks[bname].data) - _positions(blocks[0].data)) @ linear.T
            blink_moved |= skin & (np.linalg.norm(bdelta, axis=1) > 1e-5)
    if not blink_moved.any():
        blink_moved = skin & (y < -0.175) & (((ax - EYE_CENTER[0]) / 0.046) ** 2 + ((z - EYE_CENTER[2]) / 0.032) ** 2 <= 1.0)
    gu, gv, gw = _skin_graph(mesh, points, skin)
    has_above = np.zeros(n, dtype=bool)
    has_below = np.zeros(n, dtype=bool)
    m_uv = blink_moved[gv]
    has_above[gu[m_uv & (z[gv] > z[gu])]] = True
    has_below[gu[m_uv & (z[gv] < z[gu])]] = True
    m_vu = blink_moved[gu]
    has_above[gv[m_vu & (z[gu] > z[gv])]] = True
    has_below[gv[m_vu & (z[gu] < z[gv])]] = True
    canthus = has_above & has_below & (y < -0.179) & (np.abs(z - EYE_CENTER[2]) < 0.010)
    lid_core = (blink_moved | canthus) & allowed_skin

    brow = detail & (z > 1.615)
    lash = detail & (z <= 1.615)
    return skin, allowed_skin, fixed_skin, lid_core, lash, brow, gu, gv, gw, side, ax, y, z


def _extend_from_lid(n, gu, gv, gw, free_eye, eye_taper, fixed_skin, bc, relax_iters=3, relax_alpha=0.40):
    """Harmonic extension from boundary mask into free_eye, tapered smoothly to fixed_skin."""
    field = _solve_harmonic(n, gu, gv, gw, free_eye, bc)
    field[free_eye] *= eye_taper[free_eye, None]
    field = _relax_field(n, gu, gv, gw, field, free_eye, iters=relax_iters, alpha=relax_alpha)
    field[fixed_skin] = 0.0
    return field


def _face_fields(mesh, points, eye, detail, blocks, linear):
    n = len(points)
    x = points[:, 0]
    (skin, allowed_skin, fixed_skin, lid_core, lash, brow,
     gu, gv, gw, side, ax, y, z) = _lid_and_perimeter(mesh, points, eye, detail, blocks, linear)

    free_eye = allowed_skin & (~lid_core)
    eye_h = _solve_harmonic(n, gu, gv, gw, free_eye, lid_core.astype(np.float64))
    eye_taper = _smooth(eye_h) / np.maximum(eye_h, 1e-6)
    lat_damp = 1.0 - 0.72 * _smooth((ax - 0.095) / 0.022)
    outer_lid_damp = _outer_lid_damp(points)

    u = ax - EYE_CENTER[0]
    v = y - EYE_CENTER[1]
    w = z - EYE_CENTER[2]

    fields = {}

    # 1. Eye controls: rigid/uniform spherical eyeballs, coherent lid+lash rim, harmonic skin blend, smooth brows.
    for cname in ("Eye_Size", "Eye_Aperture", "Eye_Spacing", "Eye_Height", "Eye_Tilt"):
        delta = np.zeros_like(points)

        if cname == "Eye_Size":
            d_lid = _eye_control_eval(points, "Eye_Size", side)
            d_eye = np.column_stack((side * EYE_SCALE * u, EYE_SCALE * v, EYE_SCALE * w))
            d_brow = np.column_stack((side * 0.075 * u, np.zeros(n), 0.065 * w))
        elif cname == "Eye_Aperture":
            d_lid = _eye_control_eval(points, "Eye_Aperture", side)
            d_eye = np.zeros_like(points)
            arch = np.exp(-((ax - 0.070) / 0.038) ** 2)
            d_brow = np.column_stack((np.zeros(n), np.zeros(n), 0.0020 + 0.0028 * arch))
        elif cname == "Eye_Spacing":
            base_lid = np.column_stack((side * 0.0068, np.full(n, 0.0026), np.zeros(n)))
            d_eye = base_lid
            d_lid = base_lid * lat_damp[:, None]
            d_brow = np.column_stack((side * 0.0048, np.full(n, 0.0018), np.zeros(n)))
        elif cname == "Eye_Height":
            base_lid = np.column_stack((np.zeros(n), np.zeros(n), np.full(n, 0.0058)))
            d_eye = base_lid
            d_lid = base_lid * outer_lid_damp[:, None]
            d_brow = np.column_stack((np.zeros(n), np.zeros(n), np.full(n, 0.0046)))
        elif cname == "Eye_Tilt":
            d_lid = _eye_control_eval(points, "Eye_Tilt", side)
            d_eye = np.zeros_like(points)
            d_brow = np.column_stack((-side * 0.05 * (z - 1.640), np.zeros(n), 0.15 * u))

        bc = np.zeros_like(points)
        bc[lid_core] = d_lid[lid_core]
        skin_harm = _extend_from_lid(n, gu, gv, gw, free_eye, eye_taper, fixed_skin, bc, relax_iters=3, relax_alpha=0.40)

        delta[skin] = skin_harm[skin]
        delta[eye] = d_eye[eye]
        delta[lash] = d_lid[lash]
        delta[brow] = d_brow[brow]
        fields[cname] = delta

    # 2. Nose controls: soft rounded screened-Poisson fields strictly inside allowed non-lid skin.
    free_mid = allowed_skin & (~lid_core)
    nose_z_fade = _smooth((z - 1.513) / 0.016) * _smooth((1.622 - z) / 0.025)
    nose_x_fade = _smooth((0.044 - ax) / 0.020)
    nose_y_fade = _smooth((-0.198 - y) / 0.028)
    nose_env = nose_z_fade * nose_x_fade * nose_y_fade
    nose_env[~free_mid] = 0.0

    sz_size = np.where(z >= 1.534, 0.032, 0.015)
    g_size = np.exp(-((ax / 0.024) ** 2 + ((z - 1.534) / sz_size) ** 2)) * nose_env

    g_len_proj = np.exp(-((ax / 0.021) ** 2 + ((z - 1.545) / 0.032) ** 2)) * nose_env
    g_len_drop = np.exp(-((ax / 0.022) ** 2 + ((z - 1.540) / 0.024) ** 2)) * _smooth((z - 1.515) / 0.016) * nose_env

    g_wid = np.exp(-((ax / 0.029) ** 2 + ((z - 1.533) / 0.020) ** 2)) * nose_env
    g_ala = np.exp(-(((ax - 0.014) / 0.014) ** 2 + ((z - 1.532) / 0.016) ** 2)) * nose_env

    # Wider lateral Gaussian (0.022) keeps the dorsal bridge rounded instead of creating a sharp midline crest.
    g_bridge = np.exp(-((ax / 0.022) ** 2 + ((z - 1.572) / 0.032) ** 2)) * _smooth((z - 1.532) / 0.016) * nose_env
    g_tip = np.exp(-((ax / 0.021) ** 2 + ((z - 1.534) / 0.016) ** 2)) * _smooth((z - 1.514) / 0.014) * nose_env

    nose_raw = {
        "Nose_Size": np.column_stack((0.22 * x * g_size, -0.0074 * g_size, 0.11 * (z - 1.528) * g_size)),
        "Nose_Length": np.column_stack((np.zeros(n), -0.0054 * g_len_proj, -0.0046 * g_len_drop)),
        "Nose_Width": np.column_stack((0.35 * x * g_wid, -0.0026 * g_ala, -0.0008 * g_wid)),
        "Nose_Bridge": np.column_stack((np.zeros(n), -0.0082 * g_bridge, np.zeros(n))),
        "Nose_Tip": np.column_stack((np.zeros(n), -0.0054 * g_tip, 0.0022 * g_tip)),
    }
    for cname, target in nose_raw.items():
        sol = _solve_screened(n, gu, gv, gw, free_mid, target, gamma=150.0)
        sol = _relax_field(n, gu, gv, gw, sol, free_mid, iters=2, alpha=0.40)
        sol[~free_mid] = 0.0
        fields[cname] = sol

    # 3. Upper_Cheek: feather smoothly up across the lower orbital crease while keeping the blink seam exact.
    cheek_seam = lid_core & (z >= 1.560)
    free_cheek = allowed_skin & (~cheek_seam)
    cheek_g = np.exp(-(((ax - 0.072) / 0.044) ** 2 + ((z - 1.540) / 0.026) ** 2))
    cheek_fade = _smooth((ax - 0.022) / 0.022) * _smooth((z - 1.514) / 0.015) * _smooth((1.564 - z) / 0.022)
    cheek_target = np.column_stack((
        side * 0.0024 * cheek_g * cheek_fade,
        -0.0068 * cheek_g * cheek_fade,
        0.0014 * cheek_g * cheek_fade,
    ))
    cheek_sol = _solve_screened(n, gu, gv, gw, free_cheek, cheek_target, gamma=95.0)
    cheek_sol = _relax_field(n, gu, gv, gw, cheek_sol, free_cheek, iters=4, alpha=0.45)
    cheek_sol[~free_cheek] = 0.0
    fields["Upper_Cheek"] = cheek_sol

    return fields, lid_core, lash, brow, side, allowed_skin, skin, fixed_skin, gu, gv, gw, free_eye, eye_taper


def _write_key(body, name, basis, delta, inverse, limits):
    keys = body.data.shape_keys.key_blocks
    key = keys.get(name)
    if key is None:
        key = body.shape_key_add(name=name, from_mix=False)
        key.value = 0.0
    key.relative_key = keys[0]
    key.slider_min, key.slider_max = limits
    key.data.foreach_set("co", np.ascontiguousarray(basis + delta @ inverse.T, dtype=np.float32).ravel())
    return key


def _remove_key(body, name):
    sk = body.data.shape_keys
    kb = sk.key_blocks.get(name)
    if kb is None:
        return
    anim = sk.animation_data
    if anim and anim.drivers:
        path = kb.path_from_id("value")
        fc = anim.drivers.find(path)
        if fc is not None:
            anim.drivers.remove(fc)
    body.shape_key_remove(kb)


def _drive(keys, target, factors, expression):
    path = target.path_from_id("value")
    animation = keys.animation_data
    channel = animation.drivers.find(path) if animation else None
    if channel is None:
        channel = target.driver_add("value")
    driver = channel.driver
    driver.type = "SCRIPTED"
    for var in list(driver.variables):
        driver.variables.remove(var)
    driver.expression = expression
    for label, name in factors.items():
        var = driver.variables.new()
        var.name = label
        var.type = "SINGLE_PROP"
        var.targets[0].id_type = "KEY"
        var.targets[0].id = keys
        var.targets[0].data_path = keys.key_blocks[name].path_from_id("value")


def _motion_key(body, name, basis, delta, inverse, factors, formula, limits=(-1.0, 1.0)):
    key = _write_key(body, name, basis, delta, inverse, limits)
    _drive(body.data.shape_keys, key, factors, formula)
    return key


def _lid_relaxation(mesh, points, blink_delta, lid_core):
    """Soften the closed lid's corner folds strictly within lid_core while keeping seam height."""
    edges = np.array([tuple(edge.vertices) for edge in mesh.edges], dtype=np.int64)
    start, end = np.concatenate((edges.T, edges.T[::-1]), axis=1)
    degree = np.maximum(np.bincount(start, minlength=len(points)), 1)
    moved = lid_core & (np.linalg.norm(blink_delta, axis=1) > 1e-7)
    closed = points + blink_delta
    relaxed = closed.copy()
    for _ in range(3):
        average = np.column_stack([
            np.bincount(start, weights=component[end], minlength=len(points)) / degree
            for component in relaxed.T
        ])
        relaxed[moved] += 0.43 * (average[moved] - relaxed[moved])
    x, _, z = points.T
    corners = _smooth((np.abs(np.abs(x) - EYE_CENTER[0]) - 0.008) / 0.023)
    corners *= _smooth((z - 1.550) / 0.025) * _smooth((1.616 - z) / 0.018)
    delta = np.clip((relaxed - closed) * corners[:, None] * (0.82, 0.88, 0.15), -0.004, 0.004)
    delta[~lid_core] = 0.0
    return delta


def _fit_rotation(src, dst):
    """Best-fit proper 3x3 orthogonal rotation matrix taking src vectors to dst vectors."""
    u, _, vt = np.linalg.svd(dst.T @ src)
    rot = u @ vt
    if np.linalg.det(rot) < 0.0:
        u[:, -1] *= -1.0
        rot = u @ vt
    return rot


def smooth_vertical_gaze_keys(body=None):
    """Replace the outer orbital skin smear in authored EyeLook_Up/Down with harmonic falloff.

    Preserves the inner lid margin (ring >= 2 from non-lid skin), all eyeball vertices,
    all brow/lash vertices, and all skin outside the allowed orbital perimeter identically.
    Idempotent across repeated runs; invoke explicitly before add_face_keys().
    """
    body = body if body is not None else bpy.data.objects[BODY]
    keys = body.data.shape_keys
    if keys is None or not keys.use_relative:
        raise ValueError("Aj needs its original relative shape keys")
    blocks = keys.key_blocks

    transform = body.matrix_world
    linear = np.array(transform.to_3x3(), dtype=np.float64)
    inverse = np.linalg.inv(linear)
    basis = _positions(blocks[0].data)
    points = basis.astype(np.float64) @ linear.T + np.array(transform.translation)
    eye = _material_vertices(body.data, EYE_MAT)
    detail = _material_vertices(body.data, BROW_LASH_MAT)
    n = len(points)

    skin, allowed_skin, fixed_skin, lid_core, _, _, gu, gv, gw, _, _, _, _ = _lid_and_perimeter(
        body.data, points, eye, detail, blocks, linear
    )

    # Topological BFS ring distance inward from non-lid skin so the inner lid margin following the eye stays exact.
    adj = [[] for _ in range(n)]
    for a, b in zip(gu.tolist(), gv.tolist()):
        adj[a].append(b)
        adj[b].append(a)
    outer_ring = np.array([lid_core[i] and any(not lid_core[nb] for nb in adj[i]) for i in range(n)], dtype=bool)
    ring_dist = np.full(n, -1, dtype=int)
    ring_dist[outer_ring] = 0
    queue = list(np.flatnonzero(outer_ring))
    while queue:
        cur = queue.pop(0)
        for nb in adj[cur]:
            if lid_core[nb] and ring_dist[nb] == -1:
                ring_dist[nb] = ring_dist[cur] + 1
                queue.append(nb)

    inner_rim = lid_core & (ring_dist >= 2)
    free_v = allowed_skin & (~inner_rim)
    h_v = _solve_harmonic(n, gu, gv, gw, free_v, inner_rim.astype(np.float64))
    taper_v = _smooth(h_v) / np.maximum(h_v, 1e-6)

    updated = []
    for gname in ("EyeLook_Up", "EyeLook_Down"):
        kb = blocks.get(gname)
        if kb is None:
            continue
        orig_delta = (_positions(kb.data) - basis) @ linear.T
        bc = np.zeros_like(points)
        bc[inner_rim] = orig_delta[inner_rim]
        d_skin = _extend_from_lid(n, gu, gv, gw, free_v, taper_v, fixed_skin, bc, relax_iters=3, relax_alpha=0.40)
        d_new = orig_delta.copy()
        d_new[skin & allowed_skin] = d_skin[skin & allowed_skin]
        kb.data.foreach_set("co", np.ascontiguousarray(basis + d_new @ inverse.T, dtype=np.float32).ravel())
        updated.append(gname)

    body.data.update()
    keys.update_tag()
    bpy.context.view_layer.update()
    return updated


def add_face_keys(body=None):
    """Create or refresh the face controls and exact spherical-eye/blink expression correctives."""
    body = body if body is not None else bpy.data.objects[BODY]
    keys = body.data.shape_keys
    if keys is None or not keys.use_relative:
        raise ValueError("Aj needs its original relative shape keys")
    blocks = keys.key_blocks
    preserved = {name: blocks[name].value for name in KEY_NAMES if name in blocks}

    transform = body.matrix_world
    linear = np.array(transform.to_3x3(), dtype=np.float64)
    inverse = np.linalg.inv(linear)
    basis = _positions(blocks[0].data)
    points = basis.astype(np.float64) @ linear.T + np.array(transform.translation)
    eye = _material_vertices(body.data, EYE_MAT)
    detail = _material_vertices(body.data, BROW_LASH_MAT)
    if not eye.any() or not detail.any():
        raise ValueError("Aj's eye and brow/lash material slots are required")

    (fields, lid_core, lash, _, side, allowed_skin, skin, fixed_skin,
     gu, gv, gw, free_eye, eye_taper) = _face_fields(body.data, points, eye, detail, blocks, linear)
    n = len(points)
    active_keys = set(KEY_NAMES)

    for name, delta in fields.items():
        _write_key(body, "Face_" + name, basis, delta, inverse, (-1.0, 1.0))

    # 1. Exact finite-difference eyelid + lash closure correctives for Eye_Size, Eye_Aperture, Eye_Tilt (6 keys).
    for suffix, direction in EYE_SIDES:
        blink = f"EyeBlink_{suffix}"
        if blink not in blocks:
            continue
        blink_delta = (_positions(blocks[blink].data) - basis) @ linear.T
        same_lid = (lid_core | lash) & (side == direction)
        p_rest = points[same_lid]
        p_closed = p_rest + blink_delta[same_lid]
        for ctrl in ("Eye_Size", "Eye_Aperture", "Eye_Tilt"):
            d_corr = np.zeros_like(points)
            d_corr[same_lid] = _eye_control_eval(p_closed, ctrl, direction) - _eye_control_eval(p_rest, ctrl, direction)
            kname = f"FaceFollow_{ctrl}_{blink}"
            active_keys.add(kname)
            _motion_key(body, kname, basis, d_corr, inverse,
                        {"face": "Face_" + ctrl, "blink": blink}, "face * blink")

    # 2. Scale rigid eyeball gaze offsets proportionally with Face_Eye_Size on all 4 cardinal directions (4 keys).
    gaze_names = ("EyeLook_Left", "EyeLook_Right", "EyeLook_Up", "EyeLook_Down")
    gaze_deltas = {}
    for gname in gaze_names:
        if gname not in blocks:
            continue
        gd = (_positions(blocks[gname].data) - _positions(blocks[gname].relative_key.data)) @ linear.T
        gaze_deltas[gname] = gd
        d_eye_scale = np.zeros_like(points)
        d_eye_scale[eye] = EYE_SCALE * gd[eye]
        kname = f"FaceFollow_Eye_Size_{gname}"
        active_keys.add(kname)
        _motion_key(body, kname, basis, d_eye_scale, inverse,
                    {"size": "Face_Eye_Size", "gaze": gname}, "size * gaze", (-1.0, 1.0))

    # 3. Compose exact horizontal * vertical eyeball rotations on diagonal gazes without shearing the sphere (4 keys).
    if all(g in gaze_deltas for g in gaze_names):
        rot_by_side = {
            direction: {
                g: _fit_rotation(
                    points[eye & (side == direction)] - (EYE_CENTER * (direction, 1.0, 1.0)),
                    points[eye & (side == direction)] + gaze_deltas[g][eye & (side == direction)] - (EYE_CENTER * (direction, 1.0, 1.0)),
                )
                for g in gaze_names
            }
            for _, direction in EYE_SIDES
        }
        eye3 = np.eye(3, dtype=np.float64)
        for g_vert in ("EyeLook_Up", "EyeLook_Down"):
            for g_horiz in ("EyeLook_Left", "EyeLook_Right"):
                d_diag = np.zeros_like(points)
                for _, direction in EYE_SIDES:
                    same_eye = eye & (side == direction)
                    center = EYE_CENTER * (direction, 1.0, 1.0)
                    v_local = points[same_eye] - center
                    r_h = rot_by_side[direction][g_horiz]
                    r_v = rot_by_side[direction][g_vert]
                    d_diag[same_eye] = v_local @ ((r_h - eye3) @ (r_v - eye3)).T
                kname = f"FaceGazeDiag_{g_vert.split('_')[1]}_{g_horiz.split('_')[1]}"
                active_keys.add(kname)
                _motion_key(
                    body, kname, basis, d_diag, inverse,
                    {"gv": g_vert, "gh": g_horiz, "size": "Face_Eye_Size"},
                    f"gv * gh * (1.0 + {EYE_SCALE} * size)", (0.0, 2.0),
                )

    # 4. Track eyelid/lash/orbital skin follow on vertical gaze for Eye_Size, Eye_Aperture, Eye_Tilt (12 keys).
    for gname in ("EyeLook_Up", "EyeLook_Down"):
        if gname not in gaze_deltas:
            continue
        gd = gaze_deltas[gname]
        for suffix, direction in EYE_SIDES:
            blink = f"EyeBlink_{suffix}"
            if blink not in blocks:
                continue
            same_lid = (lid_core | lash) & (side == direction)
            p_rest = points[same_lid]
            p_gaze = p_rest + gd[same_lid]
            for ctrl in ("Eye_Size", "Eye_Aperture", "Eye_Tilt"):
                d_lid = _eye_control_eval(p_gaze, ctrl, direction) - _eye_control_eval(p_rest, ctrl, direction)
                bc = np.zeros_like(points)
                bc[same_lid] = d_lid
                d_corr = _extend_from_lid(
                    n, gu, gv, gw, free_eye, eye_taper, fixed_skin, bc, relax_iters=2, relax_alpha=0.35
                )
                d_corr[lash & (side == direction)] = bc[lash & (side == direction)]
                d_corr[eye] = 0.0
                d_corr[lash & (side != direction)] = 0.0
                kname = f"FaceFollow_{ctrl}_{gname}_{suffix}"
                active_keys.add(kname)
                _motion_key(
                    body, kname, basis, d_corr, inverse,
                    {"face": "Face_" + ctrl, "gaze": gname, "blink": blink},
                    "face * gaze * (1.0 - blink)", (-1.0, 1.0),
                )

    # 5. Hand eyelids and lashes over from vertical gaze (EyeLook_Up / EyeLook_Down) to blink (4 keys).
    for gaze in ("EyeLook_Up", "EyeLook_Down"):
        if gaze not in blocks:
            continue
        motion = (_positions(blocks[gaze].data) - _positions(blocks[gaze].relative_key.data)) @ linear.T
        for suffix, direction in EYE_SIDES:
            blink = f"EyeBlink_{suffix}"
            if blink not in blocks:
                continue
            mask = ((~eye) & (side == direction))[:, None]
            kname = f"FaceBlinkFollow_{gaze}_{suffix}"
            active_keys.add(kname)
            _motion_key(body, kname, basis, -motion * mask, inverse,
                        {"motion": gaze, "blink": blink}, "motion * blink")

    # 6. End-of-blink uniform whole-globe recess & closed-lid corner relaxation (4 keys).
    for suffix, direction in EYE_SIDES:
        blink = f"EyeBlink_{suffix}"
        if blink not in blocks:
            continue
        blink_delta = (_positions(blocks[blink].data) - basis) @ linear.T
        lid_relax = _lid_relaxation(body.data, points, blink_delta, lid_core & (side == direction))
        k_lid = f"FaceBlink_Lid_{suffix}"
        active_keys.add(k_lid)
        _motion_key(body, k_lid, basis, lid_relax, inverse, {"blink": blink}, "blink", (0.0, 1.0))

        delta = np.zeros_like(points)
        same_eye = eye & (side == direction)
        center = EYE_CENTER * (direction, 1.0, 1.0)
        ep = points[same_eye]
        delta[same_eye] = -0.24 * (ep - center) + (0.0, 0.072, 0.0)
        onset = "max(0, (blink - 0.72) / 0.28)"
        k_eye = f"FaceBlink_{suffix}"
        active_keys.add(k_eye)
        _motion_key(body, k_eye, basis, delta, inverse, {"blink": blink}, " * ".join([onset] * 4), (0.0, 1.0))

    # Remove obsolete corrective keys from older installs.
    for kb in list(blocks):
        if kb.name.startswith(("FaceFollow_", "FaceBlink", "FaceGaze")) and kb.name not in active_keys:
            _remove_key(body, kb.name)

    for name, val in preserved.items():
        if name in blocks:
            blocks[name].value = val

    body.data.update()
    keys.update_tag()
    bpy.context.view_layer.update()
    return {name: blocks[name] for name in KEY_NAMES}


def apply_preset(name, body=None):
    """Set a named face on either Aj base without changing other controls."""
    preset = PRESETS[name]
    body = body if body is not None else bpy.data.objects[BODY]
    keys = body.data.shape_keys
    if keys is None or any(key not in keys.key_blocks for key in KEY_NAMES):
        add_face_keys(body)
    blocks = body.data.shape_keys.key_blocks
    for control in CONTROLS:
        blocks["Face_" + control].value = preset.get(control, 0.0)
    body.data.shape_keys.update_tag()
    bpy.context.view_layer.update()
    return name
