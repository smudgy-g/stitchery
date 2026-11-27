import unittest

from lxml import etree

from app.tagging import SVG_NS, tag_svg, widest_circle_mm

INKSTITCH_NS = "http://inkstitch.org/namespace"


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

    def test_vtracer_thin_rectangle_becomes_running_stitch(self):
        svg = f'''<svg xmlns="{SVG_NS}" width="100" height="100">
            <path id="line" d="M0 0 C27 0 54 0 81 0 C81 1.7 81 3.3 81 5 C54 5 27 5 0 5 C0 3.3 0 1.7 0 0 Z" fill="#000000" transform="translate(10,48)"/>
            <path id="square" d="M0 0 C10 0 20 0 30 0 C30 10 30 20 30 30 C20 30 10 30 0 30 C0 20 0 10 0 0 Z" fill="#ff0000"/>
        </svg>'''

        root = etree.fromstring(tag_svg(svg, target_width_mm=20, target_height_mm=20))
        line, square = root.findall(f"{{{SVG_NS}}}path")
        self.assertEqual(line.get("d"), "M81 2.5 L0 2.5")
        self.assertEqual(line.get("transform"), "translate(10,48)")
        self.assertEqual(line.get("fill"), "none")
        self.assertEqual(line.get("stroke"), "#000000")
        self.assertEqual(line.get(f"{{{INKSTITCH_NS}}}stroke_method"), "running_stitch")
        self.assertEqual(square.get("fill"), "#ff0000")
        self.assertEqual(square.get("stroke"), "none")
        self.assertEqual(square.get(f"{{{INKSTITCH_NS}}}min_stitch_length_mm"), "0.8")
        self.assertIsNone(line.get(f"{{{INKSTITCH_NS}}}min_stitch_length_mm"))
        # Ink/Stitch blocks on an "update document?" dialog for inkstitch:* attributes without this
        self.assertEqual(root.find(f"{{{SVG_NS}}}metadata/{{{INKSTITCH_NS}}}inkstitch_svg_version").text, "3")

    def test_vtracer_curved_and_wide_shapes_stay_fills(self):
        svg = f'''<svg xmlns="{SVG_NS}" width="100" height="100">
            <path id="wide" d="M0 0 C20 0 40 0 60 0 C60 4 60 8 60 12 C40 12 20 12 0 12 C0 8 0 4 0 0 Z" fill="#000"/>
            <path id="curve" d="M0 0 C20 -10 40 -10 60 0 C60 1 60 4 60 5 C40 5 20 5 0 5 C0 4 0 1 0 0 Z" fill="#f00"/>
            <path id="scaled" d="M0 0 C20 0 40 0 60 0 C60 1 60 4 60 5 C40 5 20 5 0 5 C0 4 0 1 0 0 Z" fill="#0f0" transform="scale(3)"/>
        </svg>'''
        root = etree.fromstring(tag_svg(svg, target_width_mm=20, target_height_mm=20))
        for path in root.findall(f"{{{SVG_NS}}}path"):
            self.assertEqual(path.get("stroke"), "none")
            self.assertNotEqual(path.get("fill"), "none")

    def test_full_canvas_artwork_is_not_discarded_as_background(self):
        svg = f'''<svg xmlns="{SVG_NS}" width="100" height="100">
            <path id="artwork" d="M0 0 L100 0 L100 100 L0 100 Z" fill="#000"/>
            <path id="detail" d="M20 20 L80 20 L80 80 Z" fill="#f00"/>
        </svg>'''

        root = etree.fromstring(tag_svg(svg, bg_hex="#fff"))
        self.assertEqual(
            [path.get("id") for path in root.findall(f"{{{SVG_NS}}}path")],
            ["artwork", "detail"],
        )

    def test_traced_fills_snap_back_to_thread_palette(self):
        # vtracer averages merged regions, so #f0f0f0 fabric comes back as #EFEFEF.
        svg = f'''<svg xmlns="{SVG_NS}" width="100" height="100">
            <path id="bg" d="M0 0 L100 0 L100 100 L0 100 Z" fill="#EFEFEF"/>
            <path id="art" d="M20 20 L80 20 L80 80 Z" fill="#FE0101"/>
            <path id="art2" d="M30 30 L70 30 L70 70 Z" fill="#0000FF"/>
        </svg>'''

        root = etree.fromstring(tag_svg(svg, bg_hex="#f0f0f0", palette=["#f0f0f0", "#ff0000", "#0000ff"]))
        paths = root.findall(f"{{{SVG_NS}}}path")
        self.assertEqual([(p.get("id"), p.get("fill")) for p in paths], [("art", "#ff0000"), ("art2", "#0000ff")])

    def test_non_overlapping_paths_are_grouped_by_colour(self):
        # Each colour run is a thread change on a single-needle machine.
        svg = f'''<svg xmlns="{SVG_NS}" width="100" height="100">
            <path id="red1" d="M0 0 L10 0 L10 10 Z" fill="#ff0000"/>
            <path id="blue" d="M20 0 L30 0 L30 10 Z" fill="#0000ff"/>
            <path id="red2" d="M40 0 L50 0 L50 10 Z" fill="#ff0000"/>
            <path id="green" d="M60 0 L70 0 L70 10 Z" fill="#00ff00"/>
        </svg>'''

        root = etree.fromstring(tag_svg(svg, non_overlapping=True))
        self.assertEqual([p.get("id") for p in root.findall(f"{{{SVG_NS}}}path")], ["red1", "red2", "blue", "green"])

    def test_widest_circle_counts_holes(self):
        square = "M0 0 L40 0 L40 40 L0 40 Z"
        self.assertAlmostEqual(widest_circle_mm(square, 0.5), 20, delta=0.6)
        # A 30-wide hole leaves a 5-wide frame
        self.assertAlmostEqual(widest_circle_mm(square + " M5 5 L35 5 L35 35 L5 35 Z", 0.5), 2.5, delta=0.6)

    def test_small_shapes_fall_back_from_meander(self):
        svg = f'''<svg xmlns="{SVG_NS}" width="100" height="100">
            <path id="big" d="M10 10 L60 10 L60 60 L10 60 Z" fill="#ff0000"/>
            <path id="speck" d="M80 80 L86 80 L86 86 L80 86 Z" fill="#ff0000"/>
        </svg>'''
        root = etree.fromstring(tag_svg(svg, target_width_mm=100, target_height_mm=100, fill_params={"fill_method": "meander_fill"}))
        method = {p.get("id"): p.get(f"{{{INKSTITCH_NS}}}fill_method") for p in root.findall(f"{{{SVG_NS}}}path")}
        self.assertEqual(method, {"big": "meander_fill", "speck": "auto_fill"})


if __name__ == "__main__":
    unittest.main()
