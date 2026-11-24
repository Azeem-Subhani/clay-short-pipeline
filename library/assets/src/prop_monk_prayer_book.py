"""A thick leather-bound prayer book with gold bands, a cover plate and a clasp (signature prop of the Monk).

    python tools/clip.py asset library/assets/src/prop_monk_prayer_book.py --no-save     preview only
"""
from stagekit import build

ASSET = dict(id="prop_monk_prayer_book", name="Monk's prayer book", kind="prop", tags=["book", "prayer book", "bible", "monk", "tome"],
             era=["medieval", "renaissance", "age_of_sail", "victorian", "fantasy"], source="built", license="project",
             notes="0.20 x 0.27 m, 0.07 m thick, lying flat on z = 0 with the spine toward -X; carry it flat in the hand or "
                   "stand it up with turn=True")


def build_asset():
    parts = [build.box("book.back", (0.20, 0.27, 0.012), (0, 0, 0), "#5A2E22", bevel=0.004),
             build.box("book.pages", (0.18, 0.25, 0.046), (0.006, 0, 0.012), "#EFE4C8", bevel=0.003),
             build.box("book.front", (0.20, 0.27, 0.012), (0, 0, 0.058), "#5A2E22", bevel=0.004),
             build.box("book.spine", (0.016, 0.27, 0.07), (-0.10, 0, 0), "#4A241A", bevel=0.006),
             build.box("book.plate", (0.09, 0.13, 0.006), (0.005, 0, 0.068), "gold", bevel=0.002),
             build.box("book.clasp", (0.03, 0.05, 0.074), (0.10, 0, 0.0), "gold", bevel=0.004)]
    for sy in (-1, 1):
        parts.append(build.box(f"book.band{sy}", (0.024, 0.02, 0.076), (-0.10, sy * 0.085, 0.0), "gold", bevel=0.004))
    return build.group("prop_monk_prayer_book", parts)
