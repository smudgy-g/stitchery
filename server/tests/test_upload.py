import base64
import io
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import pystitch
from fastapi.testclient import TestClient
from lxml import etree
from PIL import Image, ImageDraw

from app.main import MACHINES, app
from app.tagging import INKSTITCH_NS, SVG_NS

RECT_PES = (Path(__file__).parent / "fixtures" / "rect40.pes").read_bytes()


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def make(self, image, width_mm, machine_key="brother_4x4", num_colors=2, extra=""):
        """Runs the client's two steps: /colours, then /stitch with the stitched colours in order."""
        data = io.BytesIO()
        image.save(data, "PNG")
        colours = self.client.post(f"/api/colours?num_colors={num_colors}", files={"file": ("design.png", data.getvalue(), "image/png")})
        self.assertEqual(colours.status_code, 200, colours.text)
        body = colours.json()
        # The client paints colours it won't stitch transparent
        flat = Image.open(io.BytesIO(base64.b64decode(body["image"]))).convert("RGBA")
        skip = {tuple(c["thread"]["rgb"]) for c in body["colours"] if not c["stitched"]}
        flat.putdata([(0, 0, 0, 0) if p[:3] in skip else p for p in flat.getdata()])
        data = io.BytesIO()
        flat.save(data, "PNG")
        ids = "".join(f"&thread={c['thread']['id']}" for c in body["colours"] if c["stitched"])
        return self.client.post(
            f"/api/stitch?target_width_mm={width_mm}&machine_key={machine_key}{ids}{extra}",
            files={"file": ("design.png", data.getvalue(), "image/png")},
        )

    def upload(self, size, width_mm, machine_key="brother_4x4", background="white", extra=""):
        image = Image.new("RGB", size, background)
        w, h = size
        ImageDraw.Draw(image).rectangle((w // 4, h // 4, w * 3 // 4, h * 3 // 4), fill="red")
        return self.make(image, width_mm, machine_key, extra=extra)

    def test_landscape_and_portrait_sizes_and_hoop_limit(self):
        for size, width_mm, expected in [
            ((80, 40), 80, (40, 20)),
            ((40, 80), 40, (20, 40)),
        ]:
            with self.subTest(size=size):
                response = self.upload(size, width_mm)
                self.assertEqual(response.status_code, 200, response.text)
                bounds = response.json()["bounds"]
                self.assertAlmostEqual(bounds["widthUnits"] / 10, expected[0], delta=2)
                self.assertAlmostEqual(bounds["heightUnits"] / 10, expected[1], delta=2)

        response = self.upload((40, 80), 80)
        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds", response.json()["detail"])

    def test_off_white_background_is_not_stitched(self):
        # vtracer's default colour precision rounds #f0f0f0 to #efefef, defeating background removal.
        response = self.upload((80, 40), 80, background="#f0f0f0")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertAlmostEqual(response.json()["bounds"]["widthUnits"] / 10, 40, delta=2)

    def test_traced_colours_do_not_stack(self):
        # Stacked tracing puts a solid blue square under the red one, stitching that area twice.
        image = Image.new("RGB", (60, 60), "white")
        ImageDraw.Draw(image).rectangle((10, 10, 50, 50), fill="blue")
        ImageDraw.Draw(image).rectangle((25, 25, 35, 35), fill="red")
        with patch("app.main.svg_to_pes", return_value=RECT_PES) as svg_to_pes:
            response = self.make(image, 60, num_colors=3)
        self.assertEqual(response.status_code, 200, response.text)
        root = etree.fromstring(svg_to_pes.call_args.args[0])
        # Pure blue snaps to a purple thread, so pick the outer square as "not the red one".
        blue = [p for p in root.iter(f"{{{SVG_NS}}}path") if int(p.get("fill")[1:3], 16) < 150]
        self.assertEqual(len(blue), 1)
        self.assertGreaterEqual(blue[0].get("d").count("M"), 2, "blue fill should have a hole where the red sits")

    def test_rejects_invalid_and_empty_pes(self):
        empty = io.BytesIO()
        pystitch.write_pes(pystitch.EmbPattern(), empty)
        for output in [b"not a PES", empty.getvalue()]:
            with self.subTest(output=output[:10]), patch("app.main.svg_to_pes", return_value=output):
                response = self.upload((40, 40), 40)
                self.assertEqual(response.status_code, 502, response.text)

    def test_ink_stitch_failures_map_to_gateway_errors(self):
        for error, status in [
            (RuntimeError("no output"), 502),
            (subprocess.TimeoutExpired("inkstitch", 120), 504),
        ]:
            with self.subTest(status=status), patch("app.main.svg_to_pes", side_effect=error):
                self.assertEqual(self.upload((40, 40), 40).status_code, status)

    def test_sewing_order_and_outline_follow_the_request(self):
        image = Image.new("RGB", (60, 60), "white")
        ImageDraw.Draw(image).rectangle((10, 10, 50, 50), fill="blue")
        ImageDraw.Draw(image).rectangle((25, 25, 35, 35), fill="red")
        with patch("app.main.svg_to_pes", return_value=RECT_PES) as svg_to_pes:
            response = self.make(image, 60, num_colors=3, extra="&outline_thread=Brother:1&outline_style=bean&fill_method=contour_fill&row_spacing_mm=0.4")
        self.assertEqual(response.status_code, 200, response.text)
        paths = etree.fromstring(svg_to_pes.call_args.args[0]).findall(f"{{{SVG_NS}}}path")
        fills = [p for p in paths if p.get("fill") != "none"]
        outlines = [p for p in paths if p.get("fill") == "none"]
        self.assertEqual(len(outlines), len(fills))
        self.assertTrue(all(p.get(f"{{{INKSTITCH_NS}}}bean_stitch_repeats") == "1" for p in outlines))
        self.assertTrue(all(p.get(f"{{{INKSTITCH_NS}}}fill_method") == "contour_fill" for p in fills))
        self.assertTrue(all(p.get(f"{{{INKSTITCH_NS}}}row_spacing_mm") == "0.4" for p in fills))
        self.assertGreater(paths.index(outlines[0]), paths.index(fills[-1]), "outline is sewn last")

    def test_rejects_unknown_threads(self):
        data = io.BytesIO()
        Image.new("RGBA", (40, 40), "red").save(data, "PNG")
        for query in ["thread=Nope:1", "thread=Brother:1&outline_thread=Nope:1"]:
            with self.subTest(query=query):
                response = self.client.post(f"/api/stitch?{query}", files={"file": ("d.png", data.getvalue(), "image/png")})
                self.assertEqual(response.status_code, 400, response.text)

    def test_transparent_picture_has_nothing_to_stitch(self):
        data = io.BytesIO()
        Image.new("RGBA", (40, 40)).save(data, "PNG")
        response = self.client.post("/api/colours", files={"file": ("d.png", data.getvalue(), "image/png")})
        self.assertEqual(response.status_code, 400)

    def test_remove_background_returns_png(self):
        data = io.BytesIO()
        Image.new("RGB", (40, 40), "red").save(data, "PNG")
        cutout = Image.new("RGBA", (40, 40))
        with patch("app.main.remove_background", return_value=cutout):
            response = self.client.post("/api/remove-background", files={"file": ("d.png", data.getvalue(), "image/png")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Image.open(io.BytesIO(response.content)).mode, "RGBA")

    def test_machines_lists_presets(self):
        response = self.client.get("/api/machines")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["janome_sq14"]["format"], "jef")

    def test_each_machine_format_round_trips(self):
        for key, machine in MACHINES.items():
            with self.subTest(machine=key), patch("app.main.svg_to_pes", return_value=RECT_PES):
                response = self.upload((40, 40), 40, key)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body["format"], machine["format"])
                self.assertTrue(all(t["brand"] in ("Brother", "Janome", "Husqvarna") for t in body["threads"]))
                self.assertTrue(all(block["thread"] in body["threads"] for block in body["preview"]))
                pattern = getattr(pystitch, f"read_{machine['format']}")(io.BytesIO(base64.b64decode(body["file_base64"])))
                self.assertGreater(pattern.count_stitch_commands(pystitch.STITCH), 0)


if __name__ == "__main__":
    unittest.main()


class SiteFilesTests(unittest.TestCase):
    def test_client_pages_fall_back_to_index_but_api_does_not(self):
        import tempfile
        from starlette.applications import Starlette
        from app.main import SiteFiles

        with tempfile.TemporaryDirectory() as root:
            Path(root, "index.html").write_text("app")
            Path(root, "logo.svg").write_text("svg")
            site = Starlette()
            site.mount("/", SiteFiles(directory=root, html=True))
            client = TestClient(site)
            self.assertEqual(client.get("/logo.svg").text, "svg")
            self.assertEqual(client.get("/designs").text, "app")
            self.assertEqual(client.get("/api/nope").status_code, 404)
