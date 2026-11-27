import base64
import io
import logging
import math
import subprocess
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import pystitch
from pystitch.EmbConstant import STITCH
import vtracer
from fastapi import APIRouter, FastAPI, HTTPException, Query, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from PIL import Image, UnidentifiedImageError

from app import accounts
from app.machines import MACHINES
from app.preprocess import get_thread_catalog, nearest_thread, quantize_for_embroidery, remove_background
from app.stitcher import svg_to_pes
from app.tagging import tag_svg

logger = logging.getLogger(__name__)

MM_PER_PX = 0.1  # finer than any stitch can resolve
GENERATION_LOCK = threading.Lock()
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# The built web app; the Docker image puts it here so one server runs the whole site
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"



@asynccontextmanager
async def lifespan(_: FastAPI):
    accounts.open_database()
    yield


app = FastAPI(lifespan=lifespan)
# Everything the client calls lives under /api; the web app has the rest of the site
api = APIRouter(prefix="/api")
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ponytail: trusts Content-Length; a chunked upload skips it. Put a proxy limit in front if that matters.
@app.middleware("http")
async def limit_upload(request, call_next):
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_UPLOAD_BYTES:
        return JSONResponse({"detail": "That picture is too big. Please use one under 20 MB."}, status_code=413)
    return await call_next(request)


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


@api.get("/machines")
def machines():
    return MACHINES


@api.get("/threads")
def threads():
    return get_thread_catalog()[0]


@api.post("/remove-background")
def remove_background_endpoint(file: UploadFile):
    img = open_image(file)
    img.thumbnail((1600, 1600))  # bounds the model's memory; more than any hoop can use
    # ponytail: one heavy job at a time; peak RAM is ~2 GB with background removal. Size the box up to allow more.
    with GENERATION_LOCK:
        cutout = remove_background(img)
    buf = io.BytesIO()
    cutout.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


@api.post("/colours")
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


@api.post("/stitch")
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
            nearest = nearest_thread((emb_thread.get_red(), emb_thread.get_green(), emb_thread.get_blue()), used_threads)
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


app.include_router(api)
app.include_router(accounts.router)
class SiteFiles(StaticFiles):
    """The built client. Its pages (like /designs) exist only in the browser, so unknown paths get index.html."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


if STATIC_DIR.is_dir():
    app.mount("/", SiteFiles(directory=STATIC_DIR, html=True), name="site")
