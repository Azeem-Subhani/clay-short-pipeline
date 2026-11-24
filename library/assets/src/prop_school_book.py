"""A closed hardback school book: blue cover, cream page block, a gold label. Grip point at the origin."""
from stagekit import build

ASSET = dict(id="prop_school_book", name="School book", kind="prop", tags=["book", "school", "teacher", "reading", "textbook"],
             era=["victorian", "modern"], source="built", license="project",
             notes="0.20 x 0.27 m, 4 cm thick, standing on its lower edge, front cover toward -Y, spine at -X; "
                   "teacher.hold(book, 'L', t) carries it against the body")


def build_asset():
    parts = [
        build.box("book.pages", (0.185, 0.030, 0.255), (0.004, 0, 0.008), "#F4EAD2", bevel=0.003),
        build.box("book.front", (0.20, 0.006, 0.27), (0, -0.018, 0), "#3F5E9C", bevel=0.004),
        build.box("book.back", (0.20, 0.006, 0.27), (0, 0.018, 0), "#3F5E9C", bevel=0.004),
        build.box("book.spine", (0.012, 0.042, 0.27), (-0.097, 0, 0), "#34508A", bevel=0.005),
        build.box("book.label", (0.11, 0.003, 0.05), (0.01, -0.022, 0.165), "#E8BE4E", bevel=0.0),
    ]
    return build.group("prop_school_book", parts)
