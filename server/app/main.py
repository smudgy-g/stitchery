import base64
import io
import logging
import math
import subprocess
import threading
from typing import Literal

import pystitch
from pystitch.EmbConstant import STITCH
import vtracer
from fastapi import FastAPI, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from PIL import Image, UnidentifiedImageError

from app.preprocess import get_thread_catalog, quantize_for_embroidery, remove_background
from app.stitcher import svg_to_pes
from app.tagging import tag_svg

logger = logging.getLogger(__name__)

# Hoop limits are width x height as the hoop is mounted; designs are not auto-rotated.
MACHINES = {
    "brother_4x4": {"name": "Brother 4x4", "max_w": 100.0, "max_h": 100.0, "format": "pes"},
    "brother_5x7": {"name": "Brother 5x7", "max_w": 130.0, "max_h": 180.0, "format": "pes"},
    "brother_6x10": {"name": "Brother 6x10", "max_w": 160.0, "max_h": 260.0, "format": "pes"},
    "brother_8x12": {"name": "Brother 8x12", "max_w": 200.0, "max_h": 300.0, "format": "pes"},
    "janome_sq14": {"name": "Janome SQ14", "max_w": 140.0, "max_h": 140.0, "format": "jef"},
    "janome_re20": {"name": "Janome RE20", "max_w": 170.0, "max_h": 200.0, "format": "jef"},
    "husqvarna_240x150": {"name": "Husqvarna Viking 240x150", "max_w": 240.0, "max_h": 150.0, "format": "vp3"},
    "bernina_medium": {"name": "Bernina Medium", "max_w": 100.0, "max_h": 130.0, "format": "exp"},
    "bernina_large_oval": {"name": "Bernina Large Oval", "max_w": 145.0, "max_h": 255.0, "format": "exp"},
    "tajima_dst": {"name": "Tajima / commercial (DST)", "max_w": 200.0, "max_h": 300.0, "format": "dst"},
}
MM_PER_PX = 0.1  # finer than any stitch can resolve
GENERATION_LOCK = threading.Lock()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Corners of the RGB cube: the one furthest from every thread marks "not stitched" for tracing
SENTINELS = [(r, g, b) for r in (0, 255) for g in (0, 255) for b in (0, 255)]


def open_image(file: UploadFile) -> Image.Image:
    try:
        img = Image.open(file.file)
        img.load()
        return img
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file. Upload a raster image (png, jpeg, webp).",
        )


def png_base64(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue())


@app.get("/")
async def root():
    return {"message": "Hello from server!"}


@app.get("/machines")
def machines():
    return MACHINES


@app.get("/threads")
def threads():
    return get_thread_catalog()[0]


@app.post("/remove-background")
def remove_background_endpoint(file: UploadFile):
    img = open_image(file)
    img.thumbnail((1600, 1600))  # bounds the model's memory; more than any hoop can use
    # ponytail: one heavy job at a time; peak RAM is ~2 GB with background removal. Size the box up to allow more.
    with GENERATION_LOCK:
        cutout = remove_background(img)
    buf = io.BytesIO()
    cutout.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


@app.post("/colours")
def colours(
    file: UploadFile,
    num_colors: int = Query(default=5, ge=2, le=12, description="Target thread colour count"),
    smoothing: int = Query(default=1, ge=0, le=3, description="How much to flatten fine detail"),
    brands: list[Literal["brother", "janome", "husqvarna"]] = Query(default=[], description="Thread brands to use; empty = all"),
):
    """The picture reduced to thread colours. Transparent areas are never stitched."""
    try:
        flat, used = quantize_for_embroidery(open_image(file), num_colors=num_colors, smoothing=smoothing, brands=brands)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="There's nothing to stitch in this picture.") from exc
    return {"image": png_base64(flat), "colours": used}


@app.post("/stitch")
def stitch(
    file: UploadFile,
    thread: list[str] = Query(description="Thread ids to stitch, in sewing order"),
    target_width_mm: float = Query(default=80.0, ge=10.0, le=300.0, description="Target width in mm"),
    machine_key: str = Query(default="brother_4x4", description="Selected machine/hoop preset key"),
    fill_method: Literal["auto_fill", "contour_fill", "meander_fill", "circular_fill"] = Query(default="auto_fill"),
    angle: float = Query(default=0, ge=0, lt=180, description="Fill row angle in degrees"),
    row_spacing_mm: float = Query(default=0.25, ge=0.15, le=1.0, description="Distance between fill rows"),
    max_stitch_length_mm: float = Query(default=3.0, ge=1.5, le=7.0),
    underlay: bool = Query(default=True),
    pull_compensation_mm: float = Query(default=0.0, ge=0.0, le=1.0),
    min_detail_mm: float = Query(default=1.0, ge=0.3, le=5.0, description="Smaller specks are dropped"),
    outline_thread: str | None = Query(default=None, description="Thread id to outline every shape with"),
    outline_style: Literal["running", "bean"] = Query(default="running"),
):
    """Stitches for a flat picture from /colours: every opaque colour is one thread, transparent is fabric."""
    if machine_key not in MACHINES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown machine selection '{machine_key}'.",
        )
    hoop = MACHINES[machine_key]

    by_id = {t["id"]: t for t in get_thread_catalog()[0]}
    unknown = [i for i in thread + [outline_thread or ""] if i and i not in by_id]
    if unknown or not 1 <= len(thread) <= 12:
        raise HTTPException(status_code=400, detail="Choose between 1 and 12 known threads.")
    used_threads = [by_id[i] for i in dict.fromkeys(thread)]
    outline = by_id[outline_thread] if outline_thread else None

    img = open_image(file).convert("RGBA")
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
    with GENERATION_LOCK:
        # Work at ~MM_PER_PX, never above 800px, so large hoops cost no more. Nearest keeps colours exact.
        max_dimension = min(800, max(200, round(max(target_width_mm, target_height_mm) / MM_PER_PX)))
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.NEAREST)

        palette = [t["rgb"] for t in used_threads]
        fabric = max(SENTINELS, key=lambda s: min(sum((a - b) ** 2 for a, b in zip(s, p)) for p in palette))
        bg_hex = "#{:02x}{:02x}{:02x}".format(*fabric)
        flat_img = Image.new("RGB", img.size, fabric)
        flat_img.paste(img, mask=img.getchannel("A").point(lambda a: 255 if a >= 128 else 0))

        buf = io.BytesIO()
        flat_img.save(buf, "PNG")

        filter_speckle = math.ceil(min_detail_mm * flat_img.width / target_width_mm)
        # Cutout: each colour has holes where others sit, so no area is stitched twice.
        # Positional on purpose: vtracer 0.6.15 segfaults on Python 3.14 when given any keyword argument.
        svg_str: str = vtracer.convert_raw_image_to_svg(
            buf.getvalue(), "png", "color", "cutout", "spline", filter_speckle
        )

        order = [t["hex"] for t in used_threads]
        tagged_svg = tag_svg(
            svg_str,
            bg_hex=bg_hex,
            target_width_mm=target_width_mm,
            target_height_mm=target_height_mm,
            palette=order + [bg_hex],
            non_overlapping=True,  # cutout tracing
            order=order,
            fill_params={
                "fill_method": fill_method,
                "angle": f"{angle:g}",
                "row_spacing_mm": f"{row_spacing_mm:g}",
                "max_stitch_length_mm": f"{max_stitch_length_mm:g}",
                "fill_underlay": str(underlay),
                "pull_compensation_mm": f"{pull_compensation_mm:g}",
            },
            outline={"hex": outline["hex"], "style": outline_style} if outline else None,
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

        if outline:
            used_threads.append(outline)
        blocks: list[dict] = []
        min_x, min_y, max_x, max_y = pattern.bounds()

        for stitches, emb_thread in pattern.get_as_colorblocks():
            # PES v1 stores palette colours, not our thread, so name each block by the nearest thread used
            rgb = (emb_thread.get_red(), emb_thread.get_green(), emb_thread.get_blue())
            nearest = min(used_threads, key=lambda t: sum((a - b) ** 2 for a, b in zip(t["rgb"], rgb)))
            blocks.append({"color": emb_thread.hex_color(), "stitches": stitches, "thread": nearest})

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
