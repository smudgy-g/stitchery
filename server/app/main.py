import base64
import io
import tempfile
from collections import Counter
from pathlib import Path

import pystitch
import vtracer
from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

from app.preprocess import quantize_for_embroidery
from app.stitcher import svg_to_pes
from app.tagging import tag_svg

HOOP_LIMITS = {
    "brother_4x4": {"name": "Brother 4x4", "max_w": 100.0, "max_h": 100.0},
    "brother_5x7": {"name": "Brother 5x7", "max_w": 130.0, "max_h": 180.0},
    "brother_8x12": {"name": "Brother 8x12", "max_w": 200.0, "max_h": 300.0},
}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/upload")
async def upload_file(
    file: UploadFile,
    num_colors: int = Query(
        default=5, ge=2, le=12, description="Target thread color count"
    ),
    target_width_mm: float = Query(
        default=80.0, ge=10.0, le=300.0, description="Target width in mm"
    ),
    hoop_key: str = Query(
        default="brother_4x4", description="Selected hoop preset key"
    ),
):
    print(
        f"Query Params Received: num_colors={num_colors}, width={target_width_mm}mm, hoop={hoop_key}"
    )
    try:
        img = Image.open(file.file)
    except UnidentifiedImageError:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file. Upload a raster image (png, jpeg, webp).",
        )

    if hoop_key not in HOOP_LIMITS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown hoop selection '{hoop_key}'.",
        )

    hoop = HOOP_LIMITS[hoop_key]

    max_dimension = max(hoop["max_w"], hoop["max_h"])
    if target_width_mm > max_dimension:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Target width ({target_width_mm:.0f}mm) exceeds the maximum "
                f"capacity for {hoop['name']} ({max_dimension:.0f}mm)."
            ),
        )
    flat_img, used_threads = quantize_for_embroidery(
        img,
        num_colors=num_colors,
    )

    bg_hex = get_background_hex(flat_img)

    buf = io.BytesIO()
    flat_img.save(buf, "PNG")

    svg_str: str = vtracer.convert_raw_image_to_svg(
        buf.getvalue(),
        "png",
    )

    tagged_svg = tag_svg(svg_str, bg_hex=bg_hex, max_mm=80.0)

    pes = svg_to_pes(tagged_svg)

    with tempfile.TemporaryDirectory() as tmp_dir:
        pes_path = Path(tmp_dir) / "out.pes"
        with open(pes_path, "wb") as pf:
            pf.write(pes)

        pattern = pystitch.read_pes(str(pes_path))
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
        "file_base64": pes_base64,
        "threads": used_threads,
    }
