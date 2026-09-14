import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import numpy as np
from PySide6 import QtCore, QtWidgets

from model import ArrayGeometry, TaxelArrayModel, validated_index
from pyqt_single_taxel import (
    SingleTaxelHistory,
    SingleTaxelWindow,
    generate_single_taxel_reading,
)


class ModelIndexValidationTests(unittest.TestCase):
    def test_fractional_indices_are_rejected_instead_of_truncated(self):
        geometry = ArrayGeometry()
        model = TaxelArrayModel(geometry=geometry)

        with self.assertRaises(ValueError):
            validated_index(1.9, 1, geometry)
        with self.assertRaises(ValueError):
            model.select_taxel(1, 0.2)
        with self.assertRaises(ValueError):
            model.set_taxel_force(0.5, 1, [1.0, 2.0, 3.0])

    def test_integer_valued_numeric_indices_remain_supported(self):
        geometry = ArrayGeometry()
        self.assertEqual(validated_index(1.0, np.int64(2), geometry), (1, 2))


class SingleTaxelGeneratorValidationTests(unittest.TestCase):
    def test_unknown_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_single_taxel_reading("typo", 0.0)

    def test_non_finite_elapsed_time_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_single_taxel_reading("dynamic", np.nan)


class SingleTaxelHistoryAgeTests(unittest.TestCase):
    def test_history_expires_samples_by_elapsed_age(self):
        history = SingleTaxelHistory(max_samples=100, max_age_seconds=1.0)
        history.append(0.0, [1.0, 0.0, 0.0])
        history.append(0.5, [2.0, 0.0, 0.0])
        history.append(2.0, [3.0, 0.0, 0.0])

        self.assertEqual(len(history), 1)
        np.testing.assert_allclose(history.relative_times(), [0.0])
        np.testing.assert_allclose(history.force_matrix()[:, 0], [3.0])


class SingleTaxelWindowRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_invalid_arrow_scale_is_rejected(self):
        for value in (0.0, -1.0, np.nan, np.inf):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    SingleTaxelWindow(arrow_scale_mm_per_n=value, start_timer=False)

    def test_delayed_frames_keep_real_elapsed_time_and_precise_timer(self):
        with patch("pyqt_single_taxel.time.perf_counter", return_value=100.0) as clock:
            window = SingleTaxelWindow(history_seconds=5.0, start_timer=False)
            self.addCleanup(window.close)
            clock.return_value = 100.5
            window.advance_frame()
            clock.return_value = 102.5
            window.advance_frame()

            np.testing.assert_allclose(window.history.relative_times(), [-2.5, -2.0, 0.0])
            self.assertEqual(window.timer.timerType(), QtCore.Qt.TimerType.PreciseTimer)

    def test_arrow_head_points_along_off_axis_force(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)
        force = np.array([1.0, 1.0, 2.0])
        window._update_sensor(force)

        line_x, line_y = window.arrow_line.getData()
        line_direction_deg = math.degrees(
            math.atan2(line_y[1] - line_y[0], line_x[1] - line_x[0])
        )
        polygon = window.arrow_head.path.toSubpathPolygons()[0]
        points = [(polygon.at(i).x(), polygon.at(i).y()) for i in range(polygon.count())]
        base_centre = np.mean(np.asarray(points[1:4]), axis=0)
        pointing_deg = math.degrees(math.atan2(-base_centre[1], -base_centre[0]))
        error_deg = abs((pointing_deg - line_direction_deg + 180.0) % 360.0 - 180.0)

        self.assertLess(error_deg, 0.01)
        self.assertAlmostEqual(window.arrow_head.x(), line_x[1], places=6)
        self.assertAlmostEqual(window.arrow_head.y(), line_y[1], places=6)

    def test_rectangle_status_uses_rectangular_size_not_diameter_symbol(self):
        window = SingleTaxelWindow(taxel_shape="rectangle", start_timer=False)
        self.addCleanup(window.close)
        self.assertIn("20×20mm", window.info_label.text())
        self.assertNotIn("Ø=20mm", window.info_label.text())

    def test_update_sensor_rejects_malformed_or_non_finite_force(self):
        window = SingleTaxelWindow(start_timer=False)
        self.addCleanup(window.close)
        for invalid in (
            [np.nan, 0.0, 0.0],
            [1.0, np.inf, 0.0],
            [1.0, 2.0],
            [1.0, 2.0, 3.0, 4.0],
            [[1.0, 2.0, 3.0]],
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    window._update_sensor(invalid)


if __name__ == "__main__":
    unittest.main()

