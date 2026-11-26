import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from app.preprocess import majority_filter, quantize_for_embroidery, remove_background


class PreprocessTests(unittest.TestCase):
    def test_majority_filter_never_invents_labels_at_borders(self):
        # A median of {0,0,0,0,2,4,4,4,4} is 2: a one-pixel minority colour would win.
        labels = np.array([[0, 0, 0, 4, 4]] * 5)
        labels[:, 2] = [0, 0, 2, 4, 4]
        clean = majority_filter(labels, 5)
        self.assertEqual(set(np.unique(clean)), {0, 4})
        np.testing.assert_array_equal(clean[:, :2], 0)
        np.testing.assert_array_equal(clean[:, 3:], 4)

    def test_quantize_matches_threads_across_brands(self):
        # A muted brown that Brother's catalog has no close match for (best is an orange)
        img = Image.new("RGB", (60, 60), "white")
        img.paste((190, 132, 115), (20, 20, 40, 40))
        flat, colours = quantize_for_embroidery(img, num_colors=2)
        threads = [c["thread"] for c in colours]
        brown = min(threads, key=lambda t: sum(t["rgb"]))  # the other thread is white
        self.assertNotEqual(brown["brand"], "Brother")
        self.assertLess(sum(abs(a - b) for a, b in zip(brown["rgb"], (190, 132, 115))), 90)
        self.assertEqual(len(np.unique(np.array(flat).reshape(-1, 4), axis=0)), len(threads))
        # Largest area first, and the plain white surround starts out not stitched
        self.assertEqual([c["stitched"] for c in colours], [False, True])

        _, colours = quantize_for_embroidery(img, num_colors=2, brands=["brother"])
        self.assertEqual({c["thread"]["brand"] for c in colours}, {"Brother"})

    def test_transparent_pixels_stay_transparent_and_take_no_thread(self):
        img = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
        img.paste((200, 0, 0, 255), (20, 20, 40, 40))
        flat, colours = quantize_for_embroidery(img, num_colors=3)
        self.assertEqual(len(colours), 1)
        self.assertTrue(colours[0]["stitched"], "the only colour is never treated as background")
        self.assertEqual(flat.getpixel((0, 0))[3], 0)
        self.assertEqual(flat.getpixel((30, 30))[3], 255)

    def test_plain_background_found_on_a_turned_picture(self):
        # Turned in the hoop, the picture's corners are transparent; its white surround is still background
        img = Image.new("RGBA", (80, 80), (255, 255, 255, 255))
        img.paste((200, 0, 0, 255), (30, 30, 50, 50))
        img = img.rotate(30, expand=True)
        _, colours = quantize_for_embroidery(img, num_colors=2)
        white = [c for c in colours if sum(c["thread"]["rgb"]) > 700]
        self.assertEqual([c["stitched"] for c in white], [False])

    def test_remove_background_cuts_out_subject_with_hard_edges(self):
        # A half-transparent red rim would blend into a halo colour that takes a thread of its own.
        cutout = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
        cutout.paste((200, 0, 0, 128), (16, 16, 44, 44))
        cutout.paste((200, 0, 0, 255), (20, 20, 40, 40))
        fake_rembg = SimpleNamespace(remove=lambda image, session: cutout.copy())
        with patch("app.preprocess.background_remover"), patch.dict(sys.modules, {"rembg": fake_rembg}):
            result = remove_background(Image.new("RGB", (60, 60)))
        self.assertEqual(set(result.getchannel("A").getdata()), {0, 255})


if __name__ == "__main__":
    unittest.main()
