import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets

from model import ArrayGeometry
from pyqt_single_taxel import (
    SingleTaxelHistory,
    SingleTaxelWindow,
    generate_single_taxel_reading,
    parse_args,
)


class SingleTaxelHistoryTests(unittest.TestCase):
    def test_history_records_and_bounds(self):
        history = SingleTaxelHistory(max_samples=4)
        for idx in range(6):
            history.append(idx * 0.1, [idx, idx * 2.0, idx * 3.0])

        self.assertEqual(len(history), 4)
        matrix = history.force_matrix()
        self.assertEqual(matrix.shape, (4, 3))
        np.testing.assert_allclose(matrix[:, 0], [2.0, 3.0, 4.0, 5.0])
        np.testing.assert_allclose(history.relative_times(), [-0.3, -0.2, -0.1, 0.0])


class SingleTaxelGeneratorTests(unittest.TestCase):
    def test_clamp_slider_reading(self):
        reading = generate_single_taxel_reading(
            "clamp-slider",
            0.0,
            peak_force_n=100.0,
            tangential_force_n=40.0,
            tangential_axis="x",
        )
        np.testing.assert_allclose(reading, [40.0, 0.0, 100.0])

    def test_sine_shear_reading(self):
        reading = generate_single_taxel_reading(
            "sine-shear",
            0.0,
            peak_force_n=100.0,
            tangential_force_n=40.0,
        )
        self.assertAlmostEqual(reading[0], 0.0)
        self.assertAlmostEqual(reading[1], 40.0)
        self.assertAlmostEqual(reading[2], 85.0)


class SingleTaxelWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_window_advances_and_updates_curves(self):
        window = SingleTaxelWindow(
            hz=20.0,
            history_seconds=0.25,
            diameter_mm=20.0,
            taxel_shape="circle",
            peak_force_n=100.0,
            tangential_force_n=40.0,
            tangential_axis="x",
            scenario="clamp-slider",
            start_timer=False,
        )
        for _ in range(5):
            window.advance_frame()
        self.application.processEvents()

        self.assertEqual(len(window.history), 5)
        curve_x, curve_y = window.force_curves["fx"].getData()
        np.testing.assert_allclose(curve_y, np.full(5, 40.0))
        curve_fz_x, curve_fz_y = window.force_curves["fz"].getData()
        np.testing.assert_allclose(curve_fz_y, np.full(5, 100.0))
        self.assertIn("fx = +40.00 N", window.info_label.text())
        self.assertIn("fz = 100.00 N", window.info_label.text())
        window.close()

    def test_rectangle_shape_initialises(self):
        window = SingleTaxelWindow(
            taxel_shape="rectangle",
            start_timer=False,
        )
        self.assertTrue(isinstance(window.taxel_item, QtWidgets.QGraphicsRectItem))
        window.close()

    def test_default_diameter_follows_the_model_nominal_geometry(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)

        self.assertEqual(window.diameter_mm, ArrayGeometry().taxel_width_x_mm)

    def test_invalid_parameters_raise(self):
        with self.assertRaises(ValueError):
            SingleTaxelWindow(hz=0.0, start_timer=False)
        with self.assertRaises(ValueError):
            SingleTaxelWindow(taxel_shape="triangle", start_timer=False)


class SingleTaxelArgumentDefaultTests(unittest.TestCase):
    def test_diameter_default_follows_the_model_nominal_geometry(self):
        with patch.object(sys, "argv", ["pyqt_single_taxel.py"]):
            arguments = parse_args()

        self.assertEqual(arguments.diameter_mm, ArrayGeometry().taxel_width_x_mm)


class StageAStructurePanelTests(unittest.TestCase):
    """Stage A: static five-gap structure panel, display-only."""

    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_structure_panel_starts_collapsed(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)

        self.assertTrue(window.structure_panel.isHidden())
        self.assertFalse(window.structure_toggle.isChecked())

    def test_structure_panel_opens_on_wide_window(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)
        window.resize(1200, 680)

        window.set_structure_details_visible(True)

        self.assertFalse(window.structure_panel.isHidden())
        self.assertTrue(window.structure_toggle.isChecked())

    def test_structure_panel_autocollapses_below_900_pixels(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)
        window.resize(800, 600)

        window.set_structure_details_visible(True)

        self.assertTrue(window.structure_panel.isHidden())

    def test_structure_caption_is_the_mandated_note(self):
        from sensor_structure_items import SCHEMATIC_NOTE

        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)

        self.assertEqual(window.structure_caption.text(), SCHEMATIC_NOTE)
        self.assertIn("结构示意", SCHEMATIC_NOTE)
        self.assertIn("未接入间隙", SCHEMATIC_NOTE)

    def test_structure_panel_does_not_intercept_the_force_plot(self):
        from PySide6 import QtCore

        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)

        for view in (window.structure_top_view, window.structure_section_view):
            self.assertFalse(view.isInteractive())
            self.assertTrue(view.testAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents))

    def test_taxel_item_semantics_are_unchanged(self):
        circle = SingleTaxelWindow(start_timer=False)
        self.addCleanup(circle.close)
        self.assertIsInstance(circle.taxel_item, QtWidgets.QGraphicsEllipseItem)

        rectangle = SingleTaxelWindow(taxel_shape="rectangle", start_timer=False)
        self.addCleanup(rectangle.close)
        self.assertIsInstance(rectangle.taxel_item, QtWidgets.QGraphicsRectItem)
        self.assertAlmostEqual(rectangle.taxel_item.rect().width(), rectangle.diameter_mm)

    def test_sensor_units_stay_square_after_resize(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)

        for size in ((1200, 680), (900, 600)):
            window.resize(*size)
            window.advance_frame()
            plot = window.sensor_plot.getPlotItem()
            x_span = plot.viewRange()[0][1] - plot.viewRange()[0][0]
            y_span = plot.viewRange()[1][1] - plot.viewRange()[1][0]
            view_box = plot.vb
            self.assertAlmostEqual(
                x_span / y_span,
                view_box.width() / view_box.height(),
                places=2,
                msg=f"taxel would be distorted at {size}",
            )

    def test_sensor_view_never_crops_the_taxel(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)

        for width, height in ((240, 800), (900, 600)):
            window.sensor_plot.resize(width, height)
            app = QtWidgets.QApplication.instance()
            app.processEvents()
            window._fitted_viewport_size = None
            window._fit_sensor_view()
            plot = window.sensor_plot.getPlotItem()
            x_half = (plot.viewRange()[0][1] - plot.viewRange()[0][0]) / 2.0
            y_half = (plot.viewRange()[1][1] - plot.viewRange()[1][0]) / 2.0
            self.assertGreaterEqual(
                x_half, window.diameter_mm / 2.0,
                msg=f"taxel cropped horizontally at {width}x{height}",
            )
            self.assertGreaterEqual(
                y_half, window.diameter_mm / 2.0,
                msg=f"taxel cropped vertically at {width}x{height}",
            )
            self.assertAlmostEqual(
                x_half / y_half,
                plot.vb.width() / plot.vb.height(),
                places=2,
                msg="units must stay square",
            )

    def test_force_plot_has_a_horizontal_zero_line(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)

        zero_lines = [
            item for item in window.force_plot.getPlotItem().items
            if isinstance(item, pg.InfiniteLine) and item.angle == 0
        ]
        self.assertEqual(len(zero_lines), 1)
        self.assertEqual(zero_lines[0].value(), 0.0)

    def test_force_field_encoding_caption_is_present(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)

        text = window.field_legend_label.text()
        self.assertIn("fz", text)
        self.assertIn("fx", text)
        self.assertIn("箭头", text)

    def test_structure_panel_states_geometry_uncertainty(self):
        from sensor_structure_items import GEOMETRY_UNCERTAINTY_NOTE

        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)

        text = window.structure_geometry_note.text()
        self.assertEqual(text, GEOMETRY_UNCERTAINTY_NOTE)
        for token in ("本体外轮廓", "白色受力面", "单元中心距", "尚未确认"):
            self.assertIn(token, text)

    def test_info_label_contract_survives_the_structure_panel(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)
        window.advance_frame()

        text = window.info_label.text()
        self.assertIn("fx = ", text)
        self.assertIn("fz = ", text)


if __name__ == "__main__":
    unittest.main()
