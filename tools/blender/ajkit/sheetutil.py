# Vendored from character-rework-v2/costumes_hybrid/work/grip_tests/sheetutil.py (2026-11-26; the pack omitted it).
# Unchanged.
"""Tile PNG files into one contact sheet using Blender's image API (no PIL on this machine)."""
import bpy
import numpy as np


def sheet(paths, out, cols=4):
    ims = []
    for p in paths:
        im = bpy.data.images.load(p)
        w, h = im.size
        a = np.empty(w * h * 4, dtype=np.float32)
        im.pixels.foreach_get(a)
        ims.append(a.reshape(h, w, 4))
        bpy.data.images.remove(im)
    h = max(i.shape[0] for i in ims); w = max(i.shape[1] for i in ims)
    rows = (len(ims) + cols - 1) // cols
    S = np.zeros((rows * h, cols * w, 4), dtype=np.float32); S[..., 3] = 1
    for k, i in enumerate(ims):
        r, c = divmod(k, cols)
        y0 = (rows - 1 - r) * h
        S[y0:y0 + i.shape[0], c * w:c * w + i.shape[1]] = i
    o = bpy.data.images.new("sheet", cols * w, rows * h, alpha=True)
    o.pixels.foreach_set(S.ravel())
    o.filepath_raw = out; o.file_format = "PNG"; o.save()
    bpy.data.images.remove(o)
    return out
