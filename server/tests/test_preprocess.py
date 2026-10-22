import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from app.preprocess import majority_filter, quantize_for_embroidery


class PreprocessTests(unittest.TestCase):
    def test_majority_filter_never_invents_labels_at_borders(self):
        # A median of {0,0,0,0,2,4,4,4,4} is 2: a one-pixel minority colour would win.
        labels = np.array([[0, 0, 0, 4, 4]] * 5)
        labels[:, 2] = [0, 0, 2, 4, 4]
        clean = majority_filter(labels, 5)
        self.assertEqual(set(np.unique(clean)), {0, 4})
        np.testing.assert_array_equal(clean[:, :2], 0)
        np.testing.assert_array_equal(clean[:, 3:], 4)

    def test_quantize_snaps_to_requested_thread_brand(self):
        img = Image.new("RGB", (60, 60), "white")
        img.paste((200, 0, 0), (20, 20, 40, 40))
        flat, threads = quantize_for_embroidery(img, num_colors=2, threads="janome")
        self.assertEqual({t["brand"] for t in threads}, {"Janome"})
        self.assertEqual(len(np.unique(np.array(flat).reshape(-1, 3), axis=0)), len(threads))

    def test_remove_background_cuts_out_subject_before_quantizing(self):
        img = Image.new("RGB", (60, 60), (30, 120, 30))  # photo-ish backdrop
        img.paste((200, 0, 0), (20, 20, 40, 40))
        cutout = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
        cutout.paste((200, 0, 0, 255), (20, 20, 40, 40))
        fake_rembg = SimpleNamespace(remove=lambda image, session: cutout)
        with patch("app.preprocess.background_remover"), patch.dict(sys.modules, {"rembg": fake_rembg}):
            _, threads = quantize_for_embroidery(img, num_colors=2, remove_background=True)
        self.assertNotIn("green", " ".join(t["name"].lower() for t in threads))

    def test_cutout_edges_do_not_leave_a_halo_colour(self):
        # A half-transparent red rim blends with white into pink, which would take a thread of its own.
        cutout = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
        cutout.paste((200, 0, 0, 128), (16, 16, 44, 44))
        cutout.paste((200, 0, 0, 255), (20, 20, 40, 40))
        fake_rembg = SimpleNamespace(remove=lambda image, session: cutout)
        with patch("app.preprocess.background_remover"), patch.dict(sys.modules, {"rembg": fake_rembg}):
            flat, _ = quantize_for_embroidery(Image.new("RGB", (60, 60)), num_colors=3, remove_background=True)
        self.assertEqual(len(np.unique(np.array(flat).reshape(-1, 3), axis=0)), 2)


if __name__ == "__main__":
    unittest.main()
