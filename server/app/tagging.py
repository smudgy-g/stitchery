import logging
import re

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
logger = logging.getLogger(__name__)


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    return (
        int(hex_str[0:2], 16),
        int(hex_str[2:4], 16),
        int(hex_str[4:6], 16),
    )


def closest_palette_hex(
    rgb: tuple[int, int, int], palette: list[tuple[int, int, int]]
) -> str:
    r, g, b = rgb
    best_color = palette[0]
    min_dist = float("inf")

    for pr, pg, pb in palette:
        dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if dist < min_dist:
            min_dist = dist
            best_color = (pr, pg, pb)

    return f"#{best_color[0]:02x}{best_color[1]:02x}{best_color[2]:02x}"


def spans_canvas(path_el: etree.Element, w_px: float, h_px: float, tol: float = 0.02) -> bool:
    d = path_el.get("d") or ""
    nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", d)]
    if not nums or len(nums) < 2:
        return False

    xs = nums[0::2]
    ys = nums[1::2]

    # Parse translate transform if present: transform="translate(dx, dy)" or "translate(dx)"
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
    raw_palette: list[int] | None,
    bg_rgb: tuple[int, int, int] | None = None,
    palette_colors: int = 5,
    max_mm: float = 80.0,
) -> bytes:
    root = etree.fromstring(svg_str.encode())

    w_px = float(root.get("width"))
    h_px = float(root.get("height"))
    scale = max_mm / max(w_px, h_px)

    w_mm = w_px * scale
    h_mm = h_px * scale

    root.set("viewBox", f"0 0 {w_px} {h_px}")
    root.set("width", f"{w_mm}mm")
    root.set("height", f"{h_mm}mm")

    paths = root.findall(f"{{{SVG_NS}}}path")
    bg_hex = None

    if paths and spans_canvas(paths[0], w_px, h_px):
        bg_path = paths.pop(0)
        root.remove(bg_path)
    else:
        logger.warning("VTracer base layer not found where expected; keeping all paths")

    if raw_palette:
        max_palette_ints = palette_colors * 3
        palette_rgb = [
            (raw_palette[i], raw_palette[i + 1], raw_palette[i + 2])
            for i in range(0, min(max_palette_ints, len(raw_palette)), 3)
        ]

        if bg_rgb:
            bg_hex = closest_palette_hex(bg_rgb, palette_rgb)

        for p in paths:
            fill = p.get("fill")
            if fill and fill != "none":
                try:
                    path_rgb = hex_to_rgb(fill)
                    snapped_fill = closest_palette_hex(path_rgb, palette_rgb)
                    p.set("fill", snapped_fill)
                except ValueError:
                    pass

    if bg_hex:
        paths_to_keep = []
        for p in paths:
            if p.get("fill") == bg_hex:
                root.remove(p)
            else:
                paths_to_keep.append(p)
        paths = paths_to_keep

    paths.sort(key=lambda p: p.get("fill") or "")

    for p in paths:
        root.append(p)

    for p in paths:
        p.set("stroke", "none")

    return etree.tostring(root)
