import logging
import subprocess
import tempfile
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def svg_to_pes(svg_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as temp_dir:
        svg_path = f"{temp_dir}/design.svg"

        with open(svg_path, "wb") as f:
            f.write(svg_bytes)

        inkstitch_bin = os.environ.get(
            "INKSTITCH_BIN",
            "/usr/share/inkscape/extensions/inkstitch/bin/inkstitch",
        )

        if not Path(inkstitch_bin).is_file():
            raise RuntimeError(f"Ink/Stitch executable not found at {inkstitch_bin}")

        result = subprocess.run(
            [
                inkstitch_bin,
                "--extension=output",
                "--format=pes",
                svg_path,
            ],
            capture_output=True,
            # Pull compensation on detailed pictures takes minutes (koala: ~140s). Kept under Firefox's
            # 300s response timeout so the person gets our message, not a dropped connection.
            timeout=240,
        )

        logger.debug(result.stderr.decode("utf-8", errors="replace"))

        if not result.stdout:
            std_error = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Inkstitch failed to produce output. Stderr: {std_error}"
            )

        return result.stdout
