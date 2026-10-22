import base64
import io
import logging
import math
import subprocess
import threading
from collections import Counter

import pystitch
from pystitch.EmbConstant import STITCH
import vtracer
from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from PIL import Image, UnidentifiedImageError

from app.preprocess import quantize_for_embroidery
from app.stitcher import svg_to_pes
from app.tagging import tag_svg

logger = logging.getLogger(__name__)

# Hoop limits are width x height as the hoop is mounted; designs are not auto-rotated.
MACHINES = {
    "brother_4x4": {"name": "Brother 4x4", "max_w": 100.0, "max_h": 100.0, "format": "pes", "threads": "brother"},
    "brother_5x7": {"name": "Brother 5x7", "max_w": 130.0, "max_h": 180.0, "format": "pes", "threads": "brother"},
    "brother_6x10": {"name": "Brother 6x10", "max_w": 160.0, "max_h": 260.0, "format": "pes", "threads": "brother"},
    "brother_8x12": {"name": "Brother 8x12", "max_w": 200.0, "max_h": 300.0, "format": "pes", "threads": "brother"},
    "janome_sq14": {"name": "Janome SQ14", "max_w": 140.0, "max_h": 140.0, "format": "jef", "threads": "janome"},
    "janome_re20": {"name": "Janome RE20", "max_w": 170.0, "max_h": 200.0, "format": "jef", "threads": "janome"},
    "husqvarna_240x150": {"name": "Husqvarna Viking 240x150", "max_w": 240.0, "max_h": 150.0, "format": "vp3", "threads": "husqvarna"},
    "bernina_medium": {"name": "Bernina Medium", "max_w": 100.0, "max_h": 130.0, "format": "exp", "threads": "brother"},
    "bernina_large_oval": {"name": "Bernina Large Oval", "max_w": 145.0, "max_h": 255.0, "format": "exp", "threads": "brother"},
    "tajima_dst": {"name": "Tajima / commercial (DST)", "max_w": 200.0, "max_h": 300.0, "format": "dst", "threads": "brother"},
}
MM_PER_PX = 0.1  # finer than any stitch can resolve
GENERATION_LOCK = threading.Lock()
MIN_FEATURE_MM = 1.0  # smaller traced specks can't be stitched

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


def get_background_hex(img: Image.Image) -> str:
    """Samples four corners of the pre-quantized image to determine background hex."""
    rgb_img = img.convert("RGB")
    w, h = rgb_img.size

    corners = [
        rgb_img.getpixel((0, 0)),
        rgb_img.getpixel((w - 1, 0)),
        rgb_img.getpixel((0, h - 1)),
        rgb_img.getpixel((w - 1, h - 1)),
    ]
    bg_rgb = Counter(corners).most_common(1)[0][0]
    return f"#{bg_rgb[0]:02x}{bg_rgb[1]:02x}{bg_rgb[2]:02x}"


@app.get("/")
async def root():
    return {"message": "Hello from server!"}


@app.get("/machines")
def machines():
    return MACHINES


@app.post("/upload")
def upload_file(
    file: UploadFile,
    num_colors: int = Query(
        default=5, ge=2, le=12, description="Target thread color count"
    ),
    target_width_mm: float = Query(
        default=80.0, ge=10.0, le=300.0, description="Target width in mm"
    ),
    machine_key: str = Query(
        default="brother_4x4", description="Selected machine/hoop preset key"
    ),
    remove_background: bool = Query(
        default=False, description="Cut the subject out with an ML model first (photos)"
    ),
):
    try:
        img = Image.open(file.file)
    except UnidentifiedImageError:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file. Upload a raster image (png, jpeg, webp).",
        )

    if machine_key not in MACHINES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown machine selection '{machine_key}'.",
        )

    hoop = MACHINES[machine_key]

    source_width_px, source_height_px = img.size
    target_height_mm = target_width_mm * source_height_px / source_width_px

    if target_width_mm > hoop["max_w"] or target_height_mm > hoop["max_h"]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Design size {target_width_mm:.1f} x {target_height_mm:.1f}mm "
                f"exceeds the {hoop['name']} hoop limit of "
                f"{hoop['max_w']:.1f} x {hoop['max_h']:.1f}mm."
            ),
        )
    # ponytail: one generation at a time; peak RAM is ~2 GB with background removal. Size the box up to allow more.
    with GENERATION_LOCK:
        # Work at ~MM_PER_PX; never above the old fixed 800px, so large hoops cost no more than before
        max_dimension = min(800, max(200, round(max(target_width_mm, target_height_mm) / MM_PER_PX)))
        flat_img, used_threads = quantize_for_embroidery(
            img,
            num_colors=num_colors,
            threads=hoop["threads"],
            max_dimension=max_dimension,
            remove_background=remove_background,
        )

        bg_hex = get_background_hex(flat_img)

        buf = io.BytesIO()
        flat_img.save(buf, "PNG")

        filter_speckle = math.ceil(MIN_FEATURE_MM * flat_img.width / target_width_mm)
        # Cutout: each colour has holes where others sit, so no area is stitched twice.
        # Positional on purpose: vtracer 0.6.15 segfaults on Python 3.14 when given any keyword argument.
        svg_str: str = vtracer.convert_raw_image_to_svg(
            buf.getvalue(), "png", "color", "cutout", "spline", filter_speckle
        )

        tagged_svg = tag_svg(
            svg_str,
            bg_hex=bg_hex,
            target_width_mm=target_width_mm,
            target_height_mm=target_height_mm,
            palette=[t["hex"] for t in used_threads],
            non_overlapping=True,  # cutout tracing
        )

        try:
            pes = svg_to_pes(tagged_svg)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="Stitch generation timed out. Try fewer colours or a simpler image.") from exc
        except RuntimeError as exc:
            logger.error("Ink/Stitch failed: %s", exc)
            raise HTTPException(status_code=502, detail="Stitch generation failed.") from exc

        try:
            pattern = pystitch.read_pes(io.BytesIO(pes))
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Stitch generation returned invalid PES.") from exc
        if not pattern or not any(command == STITCH for _, _, command in pattern.stitches):
            raise HTTPException(status_code=502, detail="Stitch generation returned no stitches.")

        # Ink/Stitch's PES (v1) is shipped as-is; other formats are converted from the parsed pattern.
        if hoop["format"] == "pes":
            file_bytes = pes
        else:
            out = io.BytesIO()
            getattr(pystitch, f"write_{hoop['format']}")(pattern, out)
            file_bytes = out.getvalue()

        blocks: list[dict] = []
        min_x, min_y, max_x, max_y = pattern.bounds()

        for stitches, thread in pattern.get_as_colorblocks():
            blocks.append({"color": thread.hex_color(), "stitches": stitches})

        return {
            "preview": blocks,
            "bounds": {
                "widthUnits": max_x - min_x,
                "heightUnits": max_y - min_y,
                "minX": min_x,
                "minY": min_y,
                "maxX": max_x,
                "maxY": max_y,
            },
            "file_base64": base64.b64encode(file_bytes),
            "format": hoop["format"],
            "threads": used_threads,
        }
