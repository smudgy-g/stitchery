import logging
import math
import re

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
INKSTITCH_NS = "http://inkstitch.org/namespace"
logger = logging.getLogger(__name__)
# Fill rows across thin traced bands (outlines, shading edges) otherwise sew as hundreds of
# sub-millimetre stitches. Measured on the wombat sample: 15.6k -> 9.8k stitches, same look.
MIN_FILL_STITCH_MM = 0.8


def spans_canvas(
    path_el: etree.Element, w_px: float, h_px: float, tol: float = 0.02
) -> bool:
    """Checks if a path spans the full SVG canvas (used to detect background layer)."""
    d = path_el.get("d") or ""
    nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", d)]
    if not nums or len(nums) < 2:
        return False

    xs = nums[0::2]
    ys = nums[1::2]

    dx, dy = 0.0, 0.0
    transform = path_el.get("transform") or ""
    if "translate" in transform:
        t_nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", transform)]
        if len(t_nums) >= 1:
            dx = t_nums[0]
        if len(t_nums) >= 2:
            dy = t_nums[1]

    min_x, max_x = min(xs) + dx, max(xs) + dx
    min_y, max_y = min(ys) + dy, max(ys) + dy

    span_w = max_x - min_x
    span_h = max_y - min_y

    return span_w >= w_px * (1.0 - tol) and span_h >= h_px * (1.0 - tol)


def thin_rectangle_centerline(d: str, x_mm_per_px: float, y_mm_per_px: float) -> str | None:
    """Only convert four straight cubic edges forming a narrow rectangle."""
    tokens = re.findall(r"[MCZ]|-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", d)
    if (len(tokens) != 32 or [t for t in tokens if t in ("M", "C", "Z")] != ["M", "C", "C", "C", "C", "Z"]
            or "".join(tokens) != re.sub(r"[\s,]", "", d)):
        return None

    points = [(float(tokens[1]), float(tokens[2]))]
    for i in range(3, 28, 7):
        values = [float(n) for n in tokens[i + 1:i + 7]]
        start, end = points[-1], (values[4], values[5])
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-6:
            return None
        for control in ((values[0], values[1]), (values[2], values[3])):
            cx, cy = control[0] - start[0], control[1] - start[1]
            if (abs(dx * cy - dy * cx) > 0.01 * length_sq
                    or not 0 <= dx * cx + dy * cy <= length_sq):
                return None
        points.append(end)

    if math.dist(points[0], points[4]) > 0.01:
        return None
    edges = [((points[i + 1][0] - points[i][0]) * x_mm_per_px,
              (points[i + 1][1] - points[i][1]) * y_mm_per_px) for i in range(4)]
    lengths = [math.hypot(*edge) for edge in edges]
    if any(length < 0.01 for length in lengths):
        return None
    if any(abs(edges[i][0] * edges[(i + 1) % 4][0] + edges[i][1] * edges[(i + 1) % 4][1]) >
           0.01 * lengths[i] * lengths[(i + 1) % 4] for i in range(4)):
        return None

    long_edge = 0 if lengths[0] >= lengths[1] else 1
    short_edge = (long_edge + 1) % 4
    if (max(lengths[short_edge], lengths[(short_edge + 2) % 4]) > 1.2
            or min(lengths[long_edge], lengths[(long_edge + 2) % 4]) < 5):
        return None
    a, b = short_edge, (short_edge + 2) % 4
    mid_a = ((points[a][0] + points[a + 1][0]) / 2, (points[a][1] + points[a + 1][1]) / 2)
    mid_b = ((points[b][0] + points[b + 1][0]) / 2, (points[b][1] + points[b + 1][1]) / 2)
    return f"M{mid_a[0]:g} {mid_a[1]:g} L{mid_b[0]:g} {mid_b[1]:g}"


def nearest_hex(fill: str, palette: list[str]) -> str:
    rgb = bytes.fromhex(fill.lstrip("#"))
    return min(palette, key=lambda p: sum((a - b) ** 2 for a, b in zip(rgb, bytes.fromhex(p.lstrip("#")))))


def tag_svg(
    svg_str: str,
    bg_hex: str | None = None,
    target_width_mm: float = 80.0,
    target_height_mm: float = 80.0,
    palette: list[str] | None = None,
    non_overlapping: bool = False,
    order: list[str] | None = None,
    fill_params: dict[str, str] | None = None,
    outline: dict[str, str] | None = None,
) -> bytes:
    """Prepares VTracer SVG for stitch generation:
    1. Rescales dimensions from px to physical mm units.
    2. Snaps fills back to the thread palette (VTracer averages merged regions).
    3. Strips background canvas path if detected.
    4. Keeps the trace's paint order so overlapping colours stay visible, unless the
       paths don't overlap: then same-colour paths are grouped, one thread change per colour,
       in `order` (fill colours) when given.
    5. Applies `fill_params` (Ink/Stitch fill attributes) to every fill, and with `outline`
       ({"hex", "style": running|bean}) sews a running stitch around every fill, last.
    """
    root = etree.fromstring(svg_str.encode())

    # Scale SVG canvas from pixels to physical millimeters
    w_px = float(root.get("width"))
    h_px = float(root.get("height"))

    w_mm = target_width_mm
    h_mm = target_height_mm

    # Without a version, Ink/Stitch treats any inkstitch:* attribute as an old document and
    # opens an "update?" dialog, which on a server never returns.
    metadata = etree.Element(f"{{{SVG_NS}}}metadata")
    etree.SubElement(metadata, f"{{{INKSTITCH_NS}}}inkstitch_svg_version").text = "3"
    root.insert(0, metadata)

    root.set("viewBox", f"0 0 {w_px} {h_px}")
    root.set("width", f"{w_mm}mm")
    root.set("height", f"{h_mm}mm")

    paths = root.findall(f"{{{SVG_NS}}}path")

    if palette:
        for p in paths:
            if p.get("fill", "").startswith("#"):
                p.set("fill", nearest_hex(p.get("fill"), palette))

    # Strip background path if it spans canvas
    if paths and bg_hex and paths[0].get("fill", "").lower() == bg_hex.lower() and spans_canvas(paths[0], w_px, h_px):
        bg_path = paths.pop(0)
        root.remove(bg_path)
    else:
        logger.debug("VTracer base layer not found; keeping all paths")

    # shortcut: corner-colour matching can remove intentional same-colour artwork; use explicit fabric colour for edge-to-edge designs.
    # Filter out paths that match background hex color
    if bg_hex:
        paths_to_keep = []
        for p in paths:
            if p.get("fill", "").lower() == bg_hex.lower():
                root.remove(p)
            else:
                paths_to_keep.append(p)
        paths = paths_to_keep

    for p in paths:
        # shortcut: only VTracer's straight narrow rectangles become running stitches; curved/thick regions stay fills.
        transform = p.get("transform", "")
        line = (thin_rectangle_centerline(p.get("d", ""), w_mm / w_px, h_mm / h_px)
                if p.get("fill") and (not transform or re.fullmatch(r"translate\([\d\s,.+-]+\)", transform)) else None)
        if line:
            p.set("d", line)
            p.set("stroke", p.get("fill"))
            p.set("fill", "none")
            p.set(f"{{{INKSTITCH_NS}}}stroke_method", "running_stitch")
        else:
            p.set("stroke", "none")
            p.set(f"{{{INKSTITCH_NS}}}min_stitch_length_mm", str(MIN_FILL_STITCH_MM))
            for name, value in (fill_params or {}).items():
                p.set(f"{{{INKSTITCH_NS}}}{name}", value)

    if non_overlapping:
        colour = lambda p: p.get("stroke") if p.get("fill") == "none" else p.get("fill")
        rank = ({c: i for i, c in enumerate(order)} if order
                else {c: i for i, c in reversed(list(enumerate(map(colour, paths))))})
        for p in sorted(paths, key=lambda p: rank.get(colour(p), len(rank))):
            root.append(p)  # append moves the element, so this reorders in place

    if outline:
        # ponytail: a border shared by two colours is outlined once from each side; dedupe edges if that shows
        for p in [p for p in paths if p.get("fill") != "none"]:
            line = etree.SubElement(root, f"{{{SVG_NS}}}path", d=p.get("d"), fill="none", stroke=outline["hex"])
            if p.get("transform"):
                line.set("transform", p.get("transform"))
            line.set(f"{{{INKSTITCH_NS}}}stroke_method", "running_stitch")
            if outline["style"] == "bean":
                line.set(f"{{{INKSTITCH_NS}}}bean_stitch_repeats", "1")

    return etree.tostring(root)
