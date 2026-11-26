from functools import cache

import cv2
import numpy as np
from PIL import Image
from pystitch import EmbThreadHus, EmbThreadJef, EmbThreadPec
from skimage.color import deltaE_ciede2000, rgb2lab
from sklearn.cluster import KMeans

THREAD_SETS = {
    "brother": ("Brother", EmbThreadPec),
    "janome": ("Janome", EmbThreadJef),
    "husqvarna": ("Husqvarna", EmbThreadHus),
}
KMEANS_SAMPLE = 20_000


@cache
def get_thread_catalog() -> tuple[list[dict], np.ndarray]:
    """Every thread catalog bundled with pystitch, plus their colours in CIELAB.

    Any brand of thread sews in any machine, and no single catalog covers everything
    (Brother's 64 colours have no muted browns), so threads are matched across all of them.
    """
    catalog = []
    for brand_name, module in THREAD_SETS.values():
        for t in module.get_thread_set():
            if t is None:
                continue
            r, g, b = t.get_red(), t.get_green(), t.get_blue()
            code = str(getattr(t, "catalog_number", "") or "").strip()
            name = str(getattr(t, "description", "") or "Unknown").strip()
            catalog.append(
                {
                    "id": f"{brand_name}:{code or '000'}",
                    "brand": brand_name,
                    "code": code if code else "000",
                    "name": name,
                    "hex": f"#{r:02x}{g:02x}{b:02x}",
                    "rgb": (r, g, b),
                }
            )
    catalog_rgbs = np.array([t["rgb"] for t in catalog], dtype=np.float64) / 255.0
    catalog_lab = rgb2lab(catalog_rgbs.reshape(1, -1, 3)).reshape(-1, 3)
    return catalog, catalog_lab


@cache
def background_remover():
    # Heavy (onnxruntime + ~170MB model), so only loaded when a request asks for it.
    # u2net: ~0.4s/image on CPU; rembg's newer default (bria-rmbg) is ~16s.
    from rembg import new_session

    return new_session("u2net")


def majority_filter(labels: np.ndarray, k: int, size: int = 3) -> np.ndarray:
    """Most common label in each size×size window; ties keep the pixel's own label.

    Labels are categories, so a median filter would invent in-between labels at borders.
    """
    onehot = (labels[None] == np.arange(k)[:, None, None]).astype(np.float32)
    votes = np.stack([cv2.boxFilter(m, -1, (size, size), normalize=False) for m in onehot])
    return (votes + 0.5 * onehot).argmax(axis=0)


def remove_background(img: Image.Image) -> Image.Image:
    """The main subject on a transparent background."""
    from rembg import remove

    cutout = remove(img.convert("RGB"), session=background_remover())
    # Keep-or-cut edges: soft edges blend into halo colours that each take a thread
    cutout.putalpha(cutout.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
    return cutout


def quantize_for_embroidery(
    img: Image.Image,
    num_colors: int = 5,
    max_dimension: int = 800,
    smoothing: int = 1,
    brands: list[str] | None = None,
) -> tuple[Image.Image, list[dict]]:
    """CIELAB quantization snapped to a thread catalog.

    Transparent pixels (alpha < 128) are never stitched and take no colour. Returns the flat
    RGBA picture and one entry per thread, largest area first, as {"thread", "stitched"}:
    a plain background colour (most of the content's outer edge) starts out not stitched.
    """
    catalog, catalog_lab = get_thread_catalog()
    allowed = np.array([not brands or t["brand"].lower() in brands for t in catalog])

    # 1. Normalize resolution; JPEGs decode straight at reduced scale
    img.draft(None, (max_dimension, max_dimension))
    img_work = img.convert("RGBA")
    if max(img_work.size) > max_dimension:
        img_work.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    arr = np.array(img_work)
    opaque = arr[..., 3] >= 128
    if not opaque.any():
        raise ValueError("The picture is empty.")
    h, w = opaque.shape

    # 2. Transparent areas read as white, so smoothing doesn't drag dark junk into the edges
    rgb = np.where(opaque[..., None], arr[..., :3], 255).astype(np.uint8)

    # 3. Bilateral filter flattens soft gradients into solid colour blocks; repeating it flattens more
    for _ in range(smoothing):
        rgb = cv2.bilateralFilter(rgb, d=7, sigmaColor=75, sigmaSpace=75)

    # 4. K-Means in CIELAB, fitted on a sample of the opaque pixels, then applied to every pixel
    pixels_lab = rgb2lab(rgb.astype(np.float64) / 255.0).reshape(-1, 3)
    opaque_lab = pixels_lab[opaque.ravel()]
    rng = np.random.default_rng(42)
    sample = opaque_lab[rng.choice(len(opaque_lab), min(len(opaque_lab), KMEANS_SAMPLE), replace=False)]
    k = min(num_colors, len(np.unique(sample, axis=0)))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=3).fit(sample)
    # Label k means "transparent", so the clean-up below treats it like any other colour
    labels = np.where(opaque, kmeans.predict(pixels_lab).reshape(h, w), k)

    # 5. Pure CIEDE2000 nearest-neighbour thread matching, within the allowed brands
    distances = deltaE_ciede2000(
        kmeans.cluster_centers_.reshape(-1, 1, 3), catalog_lab.reshape(1, -1, 3)
    )
    distances[:, ~allowed] = np.inf
    best = np.argmin(distances, axis=1)

    # 6. Spatial label filter to clean up isolated anti-aliasing pixels
    if smoothing:
        labels = majority_filter(labels, k + 1, size=2 * smoothing + 1)

    # 7. Flat RGBA picture in thread colours
    palette = np.array([(*catalog[i]["rgb"], 255) for i in best] + [(0, 0, 0, 0)], dtype=np.uint8)
    flat_img = Image.fromarray(palette[labels], mode="RGBA")

    # 8. Threads left after filtering, one entry per thread, largest area first
    counts = np.bincount(labels.ravel(), minlength=k + 1)[:k]
    area: dict[int, int] = {}
    for label in np.flatnonzero(counts):
        area[best[label]] = area.get(best[label], 0) + counts[label]
    # Plain background: one thread covering most of the content's outer edge (image border or next to transparency)
    content = (labels != k).astype(np.uint8)
    edge = content.astype(bool) & ~cv2.erode(content, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    edge_threads = best[labels[edge]]
    background = np.bincount(edge_threads).argmax()
    if (edge_threads == background).mean() < 0.5 or len(area) == 1:
        background = None  # no clear plain background, or it is the only colour
    colours = [
        {"thread": catalog[i], "stitched": bool(i != background)}
        for i in sorted(area, key=area.get, reverse=True)
    ]
    return flat_img, colours
