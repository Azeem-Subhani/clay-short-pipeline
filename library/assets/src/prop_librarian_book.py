"""Thick library book: signature prop of the tradespeople sheet (character pack beta 0.4).

    python tools/clip.py asset library/assets/src/prop_librarian_book.py --no-save
"""
import math

from stagekit import build

ASSET = dict(id="prop_librarian_book", name="Thick library book", kind="prop", tags=['book', 'library', 'tome', 'reading', 'librarian'],
             era=['medieval', 'renaissance', 'age_of_sail', 'victorian', 'fantasy', 'modern'], source="built", license="project",
             notes="24 x 17 x 5.5 cm hardback lying flat; origin at its centre base: hold(book, 'R', t)")


def build_asset():
    parts = []
    parts.append(build.box("book.pages", (0.225, 0.16, 0.045), (0.005, 0, 0.005), "#F3EBD6", bevel=0.003))
    parts.append(build.box("book.back", (0.24, 0.17, 0.007), (0, 0, 0), "#8E3B36", bevel=0.003))
    parts.append(build.box("book.front", (0.24, 0.17, 0.007), (0, 0, 0.048), "#8E3B36", bevel=0.003))
    parts.append(build.box("book.spine", (0.014, 0.17, 0.055), (-0.118, 0, 0), "#73302C", bevel=0.004))
    for y in (-0.05, 0.05):
        parts.append(build.box(f"book.band{y}", (0.016, 0.012, 0.057), (-0.118, y, -0.001), "gold", bevel=0.002))
    parts.append(build.box("book.label", (0.11, 0.06, 0.002), (0.01, 0, 0.055), "gold", bevel=0.001))
    return build.group("prop_librarian_book", parts)
