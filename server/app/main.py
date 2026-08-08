import base64
import io
import tempfile
from collections import Counter
from pathlib import Path

import pyembroidery as pe
import vtracer
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

from app.stitcher import svg_to_pes
from app.tagging import tag_svg

NUM_COLORS = 5

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_background_rgb(img: Image.Image) -> tuple[int, int, int]:
    rgb_img = img.convert("RGB")
    w, h = rgb_img.size

    # Sample the four corners
    corners = [
        rgb_img.getpixel((0, 0)),
        rgb_img.getpixel((w - 1, 0)),
        rgb_img.getpixel((0, h - 1)),
        rgb_img.getpixel((w - 1, h - 1)),
    ]

    return Counter(corners).most_common(1)[0][0]


@app.get("/")
async def root():
    return {"message": "Hello from server!"}


@app.post("/upload")
async def upload_file(file: UploadFile):
    try:
        img = Image.open(file.file)
    except UnidentifiedImageError:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file. Upload a raster image (png, jpeg, webp).",
        )

    rgba = img.convert("RGBA")
    flat = Image.new("RGB", rgba.size, (255, 255, 255))
    flat.paste(rgba, mask=rgba.getchannel("A"))
    quantized = flat.convert("P", palette=Image.ADAPTIVE, colors=NUM_COLORS)

    bg_rgb = get_background_rgb(quantized)

    buf = io.BytesIO()
    quantized.save(buf, "PNG")
    palette = quantized.getpalette()

    svg_str: str = vtracer.convert_raw_image_to_svg(buf.getvalue(), "png")

    tagged_svg = tag_svg(svg_str, palette, bg_rgb=bg_rgb, palette_colors=NUM_COLORS)

    pes = svg_to_pes(tagged_svg)

    with tempfile.TemporaryDirectory() as tmp_dir:
        pes_path = Path(tmp_dir) / "out.pes"
        with open(pes_path, "wb") as pf:
            pf.write(pes)

        pattern = pe.read_pes(str(pes_path))
        color_blocks = list(pattern.get_as_colorblocks())

        with open(pes_path, "rb") as f:
            file_bytes = f.read()

        pes_base64 = base64.b64encode(file_bytes)

    blocks: list[dict] = []
    min_x, min_y, max_x, max_y = pattern.bounds()

    for stitches, thread in color_blocks:
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
        "file_base64": pes_base64
    }
