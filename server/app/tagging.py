import logging
import re

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
logger = logging.getLogger(__name__)


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


def tag_svg(
    svg_str: str,
    bg_hex: str | None = None,
    max_mm: float = 80.0,
) -> bytes:
    """Prepares VTracer SVG for stitch generation:
    1. Rescales dimensions from px to physical mm units.
    2. Strips background canvas path if detected.
    3. Groups and sorts paths by fill color to minimize thread color changes.
    """
    root = etree.fromstring(svg_str.encode())

    # Scale SVG canvas from pixels to physical millimeters
    w_px = float(root.get("width"))
    h_px = float(root.get("height"))
    scale = max_mm / max(w_px, h_px)

    w_mm = w_px * scale
    h_mm = h_px * scale

    root.set("viewBox", f"0 0 {w_px} {h_px}")
    root.set("width", f"{w_mm}mm")
    root.set("height", f"{h_mm}mm")

    paths = root.findall(f"{{{SVG_NS}}}path")

    # Strip background path if it spans canvas
    if paths and spans_canvas(paths[0], w_px, h_px):
        bg_path = paths.pop(0)
        root.remove(bg_path)
    else:
        logger.warning("VTracer base layer not found; keeping all paths")

    # Filter out paths that match background hex color
    if bg_hex:
        paths_to_keep = []
        for p in paths:
            if p.get("fill") == bg_hex:
                root.remove(p)
            else:
                paths_to_keep.append(p)
        paths = paths_to_keep

    # Group and sort paths by fill color (groups identical threads together)
    paths.sort(key=lambda p: p.get("fill") or "")

    # Re-append paths in sorted order
    for p in paths:
        root.append(p)
        p.set("stroke", "none")

    return etree.tostring(root)
