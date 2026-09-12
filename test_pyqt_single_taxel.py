import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import numpy as np
from PySide6 import QtWidgets

from pyqt_single_taxel import (
    SingleTaxelHistory,
    SingleTaxelWindow,
    generate_single_taxel_reading,
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

    def test_invalid_parameters_raise(self):
        with self.assertRaises(ValueError):
            SingleTaxelWindow(hz=0.0, start_timer=False)
        with self.assertRaises(ValueError):
            SingleTaxelWindow(taxel_shape="triangle", start_timer=False)


if __name__ == "__main__":
    unittest.main()
