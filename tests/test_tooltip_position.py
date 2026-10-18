import unittest

from offline_pdf.ui import Tooltip


class TooltipPositionTests(unittest.TestCase):
    def test_below_pointer_on_right_monitor(self):
        self.assertEqual(
            Tooltip.position(2200, 250, 300, 80, (1920, 100, 3200, 900)),
            (2212, 268),
        )

    def test_negative_coordinates_on_left_and_upper_monitors(self):
        self.assertEqual(
            Tooltip.position(-1200, -600, 300, 80, (-1600, -900, -320, -100)),
            (-1188, -582),
        )

    def test_right_and_bottom_edges_flip_above_and_clamp_inside(self):
        self.assertEqual(
            Tooltip.position(3150, 880, 300, 80, (1920, 100, 3200, 900)),
            (2892, 788),
        )

    def test_small_window_stays_inside_owner(self):
        x, y = Tooltip.position(30, 30, 300, 80, (0, 0, 400, 200))
        self.assertEqual((x, y), (42, 48))
