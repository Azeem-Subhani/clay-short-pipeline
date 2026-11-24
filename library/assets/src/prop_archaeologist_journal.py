"""Field journal: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_archaeologist_journal.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_archaeologist_journal", name="Field journal", kind="prop", tags=['journal', 'notebook', 'book', 'diary', 'archaeology'],
             era=['victorian', 'modern'], source="built", license="project",
             notes="22 x 16 x 4 cm leather notebook with a strap, lying flat; origin at its centre base: hold(journal, 'L', t)")


def build_asset():
    parts = []
    parts.append(build.box("journal.pages", (0.205, 0.15, 0.03), (0.004, 0, 0.005), "#F1E6CC", bevel=0.003))
    parts.append(build.box("journal.back", (0.22, 0.16, 0.006), (0, 0, 0), "#7A4A2A", bevel=0.003))
    parts.append(build.box("journal.front", (0.22, 0.16, 0.006), (0, 0, 0.034), "#7A4A2A", bevel=0.003))
    parts.append(build.box("journal.spine", (0.012, 0.16, 0.04), (-0.108, 0, 0), "#5E371E", bevel=0.003))
    parts.append(build.box("journal.strap", (0.024, 0.166, 0.046), (0.05, 0, -0.003), "#3E2616", bevel=0.003))
    parts.append(build.box("journal.clasp", (0.03, 0.008, 0.02), (0.05, -0.083, 0.012), "gold", bevel=0.002))
    return build.group("prop_archaeologist_journal", parts)
