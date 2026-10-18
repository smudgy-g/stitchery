import io
import unittest
from unittest.mock import patch

import pystitch
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def upload(self, size, width_mm):
        image = Image.new("RGB", size, "white")
        w, h = size
        ImageDraw.Draw(image).rectangle((w // 4, h // 4, w * 3 // 4, h * 3 // 4), fill="red")
        data = io.BytesIO()
        image.save(data, "PNG")
        return self.client.post(
            f"/upload?num_colors=2&target_width_mm={width_mm}&hoop_key=brother_4x4",
            files={"file": ("design.png", data.getvalue(), "image/png")},
        )

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

    def test_dev_cors_allows_vite_port_change(self):
        response = self.client.options(
            "/upload",
            headers={
                "Origin": "http://localhost:5175",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5175")

        response = self.client.options(
            "/upload",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_invalid_and_empty_pes(self):
        empty = io.BytesIO()
        pystitch.write_pes(pystitch.EmbPattern(), empty)
        for output in [b"not a PES", empty.getvalue()]:
            with self.subTest(output=output[:10]), patch("app.main.svg_to_pes", return_value=output):
                response = self.upload((40, 40), 40)
                self.assertEqual(response.status_code, 502, response.text)


if __name__ == "__main__":
    unittest.main()
