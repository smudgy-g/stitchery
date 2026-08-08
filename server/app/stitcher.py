import subprocess
import tempfile


def svg_to_pes(svg_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as temp_dir:
        svg_path = f"{temp_dir}/design.svg"

        with open(svg_path, "wb") as f:
            f.write(svg_bytes)

        result = subprocess.run(
            [
                "/usr/share/inkscape/extensions/inkstitch/bin/inkstitch",
                "--extension=output",
                "--format=pes",
                svg_path,
            ],
            capture_output=True,
            timeout=120,
        )

        print(result.stderr.decode("utf-8", errors="replace"))

        if not result.stdout:
            std_error = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Inkstitch failed to produce output. Stderr: {std_error}"
            )

        return result.stdout
