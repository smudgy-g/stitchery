import unittest

from lxml import etree

from app.tagging import SVG_NS, tag_svg


class TaggingTests(unittest.TestCase):
    def test_overlapping_paths_keep_trace_paint_order(self):
        svg = f'''<svg xmlns="{SVG_NS}" width="100" height="100">
            <path id="background" d="M0 0 L100 0 L100 100 L0 100 Z" fill="#fff"/>
            <path id="bottom" d="M10 10 L90 10 L90 90 Z" fill="#0000ff"/>
            <path id="middle" d="M20 20 L80 20 L80 80 Z" fill="#ff0000"/>
            <path id="top" d="M30 30 L70 30 L70 70 Z" fill="#0000ff"/>
        </svg>'''

        root = etree.fromstring(tag_svg(svg, bg_hex="#fff", target_width_mm=50, target_height_mm=50))
        paths = root.findall(f"{{{SVG_NS}}}path")

        self.assertEqual([path.get("id") for path in paths], ["bottom", "middle", "top"])
        self.assertEqual([path.get("stroke") for path in paths], ["none"] * 3)
        self.assertEqual(root.get("width"), "50mm")


if __name__ == "__main__":
    unittest.main()
