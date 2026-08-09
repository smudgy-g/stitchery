import cv2
import numpy as np
from PIL import Image
from pystitch.EmbThreadPec import get_thread_set
from scipy.ndimage import median_filter
from skimage.color import deltaE_ciede2000, rgb2lab
from sklearn.cluster import KMeans


def get_brother_catalog() -> list[dict]:
    """Extracts official Brother PEC thread catalog."""
    catalog = []
    for t in get_thread_set():
        if t is None:
            continue
        r, g, b = t.get_red(), t.get_green(), t.get_blue()
        code = str(getattr(t, "catalog_number", "") or "").strip()
        name = str(getattr(t, "description", "") or "Unknown").strip()

        catalog.append(
            {
                "brand": "Brother",
                "code": code if code else "000",
                "name": name,
                "hex": f"#{r:02x}{g:02x}{b:02x}",
                "rgb": (r, g, b),
            }
        )
    return catalog


def get_thread_catalog(brand: str = "brother") -> list[dict]:
    """Catalog router — easy to extend with Madeira, Isacord, Robison-Anton later."""
    brand_lower = brand.lower()
    if brand_lower == "brother":
        return get_brother_catalog()
    # Future extension point:
    # elif brand_lower == "madeira":
    #     return get_madeira_catalog()
    else:
        raise ValueError(f"Unsupported thread brand: {brand}")


def quantize_for_embroidery(
    img: Image.Image,
    num_colors: int = 5,
    catalog: list[dict] | None = None,
    max_dimension: int = 800,
) -> tuple[Image.Image, list[dict]]:
    """Generic, brand-agnostic CIELAB quantization engine."""
    # 1. Fallback to default catalog if none provided
    if catalog is None:
        catalog = get_thread_catalog("brother")

    # Prepare catalog arrays in CIELAB space
    catalog_rgbs = np.array([t["rgb"] for t in catalog], dtype=np.float64) / 255.0
    catalog_lab = rgb2lab(catalog_rgbs.reshape(1, -1, 3)).reshape(-1, 3)

    # 2. Normalize resolution to prevent processing freezes
    img_work = img.copy()
    if max(img_work.size) > max_dimension:
        img_work.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    # 3. Composite RGBA over white background
    rgba = img_work.convert("RGBA")
    flat = Image.new("RGB", rgba.size, (255, 255, 255))
    flat.paste(rgba, mask=rgba.getchannel("A"))
    img_np = np.array(flat)
    h, w, _ = img_np.shape

    # 4. Bilateral filter to flatten soft gradients into solid color blocks
    smoothed_np = cv2.bilateralFilter(img_np, d=7, sigmaColor=75, sigmaSpace=75)

    # 5. Convert image to CIELAB space
    img_float = smoothed_np.astype(np.float64) / 255.0
    img_lab = rgb2lab(img_float)
    pixels_lab = img_lab.reshape(-1, 3)

    # 6. Perform K-Means clustering driven by user's num_colors
    k = min(num_colors, max(1, len(pixels_lab)))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=3)
    labels = kmeans.fit_predict(pixels_lab).reshape(h, w)

    # 7. Compute cluster mean CIELAB vectors
    cluster_labs = np.zeros((k, 3), dtype=np.float64)
    for i in range(k):
        mask_i = labels == i
        if np.any(mask_i):
            cluster_labs[i] = img_lab[mask_i].mean(axis=0)

    # 8. Pure CIEDE2000 nearest-neighbor thread matching
    distances = deltaE_ciede2000(
        cluster_labs.reshape(-1, 1, 3), catalog_lab.reshape(1, -1, 3)
    )
    best_thread_indices = np.argmin(distances, axis=1)

    snapped_rgbs = np.array(
        [catalog[idx]["rgb"] for idx in best_thread_indices], dtype=np.uint8
    )

    # 9. Spatial label filter to clean up isolated anti-aliasing pixels
    clean_labels = median_filter(labels, size=3)

    # 10. Reconstruct flat raster image
    flat_np = snapped_rgbs[clean_labels]
    flat_img = Image.fromarray(flat_np, mode="RGB")

    # Deduplicate and return used thread spools
    unique_indices = sorted(list(set(best_thread_indices)))
    used_threads = [catalog[idx] for idx in unique_indices]

    return flat_img, used_threads
