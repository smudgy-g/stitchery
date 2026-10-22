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
def get_thread_catalog(brand: str = "brother") -> tuple[list[dict], np.ndarray]:
    """Thread catalog bundled with pystitch, plus its colours in CIELAB."""
    if brand not in THREAD_SETS:
        raise ValueError(f"Unsupported thread brand: {brand}")
    brand_name, module = THREAD_SETS[brand]
    catalog = []
    for t in module.get_thread_set():
        if t is None:
            continue
        r, g, b = t.get_red(), t.get_green(), t.get_blue()
        code = str(getattr(t, "catalog_number", "") or "").strip()
        name = str(getattr(t, "description", "") or "Unknown").strip()
        catalog.append(
            {
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


def quantize_for_embroidery(
    img: Image.Image,
    num_colors: int = 5,
    threads: str = "brother",
    max_dimension: int = 800,
    remove_background: bool = False,
) -> tuple[Image.Image, list[dict]]:
    """Brand-agnostic CIELAB quantization snapped to a thread catalog."""
    catalog, catalog_lab = get_thread_catalog(threads)

    # 1. Normalize resolution; JPEGs decode straight at reduced scale
    img.draft(None, (max_dimension, max_dimension))
    img_work = img.copy()
    if max(img_work.size) > max_dimension:
        img_work.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    if remove_background:
        from rembg import remove

        img_work = remove(img_work, session=background_remover())
        # Keep-or-cut edges: soft edges blend into halo colours that each take a thread
        img_work.putalpha(img_work.getchannel("A").point(lambda a: 255 if a >= 128 else 0))

    # 2. Composite RGBA over white background
    rgba = img_work.convert("RGBA")
    flat = Image.new("RGB", rgba.size, (255, 255, 255))
    flat.paste(rgba, mask=rgba.getchannel("A"))
    img_np = np.array(flat)
    h, w, _ = img_np.shape

    # 3. Bilateral filter to flatten soft gradients into solid color blocks
    smoothed_np = cv2.bilateralFilter(img_np, d=7, sigmaColor=75, sigmaSpace=75)

    # 4. Convert image to CIELAB space
    pixels_lab = rgb2lab(smoothed_np.astype(np.float64) / 255.0).reshape(-1, 3)

    # 5. K-Means fitted on a pixel sample, then applied to every pixel
    rng = np.random.default_rng(42)
    sample = pixels_lab[rng.choice(len(pixels_lab), min(len(pixels_lab), KMEANS_SAMPLE), replace=False)]
    k = min(num_colors, len(sample))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=3).fit(sample)
    labels = kmeans.predict(pixels_lab).reshape(h, w)

    # 6. Pure CIEDE2000 nearest-neighbor thread matching
    distances = deltaE_ciede2000(
        kmeans.cluster_centers_.reshape(-1, 1, 3), catalog_lab.reshape(1, -1, 3)
    )
    best_thread_indices = np.argmin(distances, axis=1)
    snapped_rgbs = np.array(
        [catalog[idx]["rgb"] for idx in best_thread_indices], dtype=np.uint8
    )

    # 7. Spatial label filter to clean up isolated anti-aliasing pixels
    clean_labels = majority_filter(labels, k)

    # 8. Reconstruct flat raster image
    flat_img = Image.fromarray(snapped_rgbs[clean_labels], mode="RGB")

    # Threads actually left in the image after filtering, deduplicated
    used_indices = np.unique(best_thread_indices[np.unique(clean_labels)])
    used_threads = [catalog[idx] for idx in used_indices]

    return flat_img, used_threads
