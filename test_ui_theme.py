import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui, QtWidgets

import ui_theme


class ThemeTokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_surface_tokens_match_the_design_document(self):
        self.assertEqual(ui_theme.WINDOW_BG, "#0B0F17")
        self.assertEqual(ui_theme.PANEL_BG, "#111827")
        self.assertEqual(ui_theme.CANVAS_BG, "#0D131F")

    def test_axis_and_moment_colour_keys_are_stable(self):
        self.assertEqual(set(ui_theme.AXIS_COLOURS), {"Fx", "Fy", "Fz"})
        self.assertEqual(set(ui_theme.MOMENT_COLOURS), {"Mx", "My", "Mz"})
        self.assertEqual(ui_theme.AXIS_COLOURS["Fx"], (239, 83, 80))
        self.assertEqual(ui_theme.AXIS_COLOURS["Fy"], (102, 187, 106))
        self.assertEqual(ui_theme.AXIS_COLOURS["Fz"], (66, 165, 245))
        self.assertEqual(ui_theme.MOMENT_COLOURS["Mz"], (171, 71, 188))

    def test_mono_font_is_monospaced(self):
        font = ui_theme.mono_font()
        self.assertEqual(font.styleHint(), QtGui.QFont.StyleHint.Monospace)
        self.assertIn("monospace", ui_theme.mono_family_qss())

    def test_window_qss_has_no_layout_metrics(self):
        qss = ui_theme.window_qss().lower()
        for token in ("padding", "margin", "min-width", "max-width", "font-size"):
            self.assertNotIn(token, qss)

    def test_field_ramp_colour_matches_the_previous_implementation(self):
        self.assertEqual(ui_theme.field_ramp_colour(0.0), (25, 55, 150))
        self.assertEqual(ui_theme.field_ramp_colour(0.45), (80, 180, 235))
        self.assertEqual(ui_theme.field_ramp_colour(1.0), (245, 75, 55))
        self.assertEqual(ui_theme.field_ramp_colour(-1.0), (25, 55, 150))
        self.assertEqual(ui_theme.field_ramp_colour(2.0), (245, 75, 55))

        def previous(value):
            if value <= 0.45:
                fraction = value / 0.45
                return (
                    round(25 + fraction * 55),
                    round(55 + fraction * 125),
                    round(150 + fraction * 85),
                )
            fraction = (value - 0.45) / 0.55
            return (
                round(80 + fraction * 165),
                round(180 - fraction * 105),
                round(235 - fraction * 180),
            )

        for sample in (0.0, 0.1, 0.225, 0.45, 0.6, 0.8, 1.0):
            self.assertEqual(ui_theme.field_ramp_colour(sample), previous(sample))

    def test_apply_canvas_theme_sets_background_brush(self):
        view = QtWidgets.QGraphicsView()
        ui_theme.apply_canvas_theme(view)
        self.assertEqual(view.backgroundBrush().color(), QtGui.QColor(ui_theme.CANVAS_BG))
        ui_theme.apply_canvas_theme(view, "panel")
        self.assertEqual(view.backgroundBrush().color(), QtGui.QColor(ui_theme.PANEL_BG))

    def test_cloud_palettes_are_dark_friendly_and_monotonic(self):
        import numpy as np

        seq_stops, seq_colours = ui_theme.CLOUD_SEQUENTIAL_LUT
        self.assertEqual(seq_colours.shape, (len(seq_stops), 3))
        self.assertTrue(np.all(np.diff(seq_stops) > 0.0))
        self.assertLess(sum(seq_colours[0]) / 3.0, 60.0)

        div_stops, div_colours = ui_theme.CLOUD_DIVERGING_LUT
        self.assertEqual(div_colours.shape, (len(div_stops), 3))
        self.assertTrue(np.all(np.diff(div_stops) > 0.0))
        midpoint = div_colours[len(div_colours) // 2]
        self.assertLess(sum(midpoint) / 3.0, 90.0)
        self.assertLess(sum(div_colours[0]) / 3.0, 150.0)

    def test_with_alpha_and_qcolor_coerce_inputs(self):
        self.assertEqual(ui_theme.qcolor("#0B0F17"), QtGui.QColor("#0B0F17"))
        self.assertEqual(ui_theme.qcolor((1, 2, 3)), QtGui.QColor(1, 2, 3))
        colour = ui_theme.with_alpha(ui_theme.TEXT_PRIMARY, 90)
        self.assertEqual(colour.alpha(), 90)


if __name__ == "__main__":
    unittest.main()
