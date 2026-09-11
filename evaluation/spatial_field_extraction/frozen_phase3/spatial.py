"""
Deterministic 2-D spatial primitives over OCR elements.

An "element" is a dict: {"text": str, "bbox": [x1, y1, x2, y2]} with
coordinates normalised to the HunyuanOCR [0, 1000] range (x right, y down).

No regex, no ML. Every relation here is a plain geometric comparison so a
human can re-derive any score by hand from the bbox numbers alone.
"""


def x1(e): return e["bbox"][0]
def y1(e): return e["bbox"][1]
def x2(e): return e["bbox"][2]
def y2(e): return e["bbox"][3]


def cx(e):
    return (e["bbox"][0] + e["bbox"][2]) / 2.0


def cy(e):
    return (e["bbox"][1] + e["bbox"][3]) / 2.0


def width(e):
    return max(0.0, e["bbox"][2] - e["bbox"][0])


def height(e):
    return max(0.0, e["bbox"][3] - e["bbox"][1])


def center_distance(a, b):
    dx = cx(a) - cx(b)
    dy = cy(a) - cy(b)
    return (dx * dx + dy * dy) ** 0.5


def horizontal_overlap(a, b):
    """Overlap width of the two bboxes' x-extents, in [0, 1000]. 0 = disjoint."""
    lo = max(x1(a), x1(b))
    hi = min(x2(a), x2(b))
    return max(0.0, hi - lo)


def vertical_overlap(a, b):
    lo = max(y1(a), y1(b))
    hi = min(y2(a), y2(b))
    return max(0.0, hi - lo)


def horizontal_overlap_ratio(a, b):
    """Overlap width / narrower element width. 1.0 = one fully spans the other."""
    denom = min(width(a), width(b))
    if denom <= 0:
        return 0.0
    return horizontal_overlap(a, b) / denom


def vertical_overlap_ratio(a, b):
    denom = min(height(a), height(b))
    if denom <= 0:
        return 0.0
    return vertical_overlap(a, b) / denom


def same_row(a, b, min_ratio=0.35):
    """Their vertical extents overlap enough to be read as one printed line."""
    return vertical_overlap_ratio(a, b) >= min_ratio


def same_column(a, b, min_ratio=0.35):
    return horizontal_overlap_ratio(a, b) >= min_ratio


def is_right_of(a, b, min_ratio=0.20):
    """a sits to the right of b, on roughly the same line."""
    return same_row(a, b, min_ratio) and cx(a) > cx(b)


def is_left_of(a, b, min_ratio=0.20):
    return same_row(a, b, min_ratio) and cx(a) < cx(b)


def is_below(a, b, min_ratio=0.15):
    """a sits below b, in roughly the same column."""
    return same_column(a, b, min_ratio) and cy(a) > cy(b)


def is_above(a, b, min_ratio=0.15):
    return same_column(a, b, min_ratio) and cy(a) < cy(b)


def vertical_gap(a, b):
    """Signed vertical whitespace from the lower edge of the upper box to the
    upper edge of the lower box. Negative when they overlap vertically."""
    if cy(a) >= cy(b):
        lower, upper = a, b
    else:
        lower, upper = b, a
    return y1(lower) - y2(upper)


def horizontal_gap(a, b):
    if cx(a) >= cx(b):
        right, left = a, b
    else:
        right, left = b, a
    return x1(right) - x2(left)
