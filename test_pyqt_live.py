import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import numpy as np
from PySide6 import QtCore, QtWidgets

from live_history import LiveHistory
from live_source import generate_bottom_right_readings, generate_uniform_clamp_readings
from model import ArrayGeometry, COMPONENTS, TaxelArrayModel
from pyqt_live import PyQtTaxelWindow


class LiveHistoryTests(unittest.TestCase):
    def test_history_is_bounded_and_switches_taxels(self):
        model = TaxelArrayModel()
        history = LiveHistory(max_samples=3)
        for frame_index in range(5):
            readings = np.zeros((3, 3, 3), dtype=np.float64)
            readings[0, 0] = [frame_index, 0.0, 0.0]
            readings[2, 2] = [0.0, frame_index, 0.0]
            model.set_force_field(readings)
            history.append(frame_index * 0.1, readings, model.wrench())

        self.assertEqual(len(history), 3)
        np.testing.assert_allclose(history.selected_taxel_matrix(0, 0)[:, 0], [2.0, 3.0, 4.0])
        np.testing.assert_allclose(history.selected_taxel_matrix(2, 2)[:, 1], [2.0, 3.0, 4.0])
        self.assertEqual(history.wrench_matrix().shape, (3, len(COMPONENTS)))
        np.testing.assert_allclose(history.relative_times(), [-0.2, -0.1, 0.0])

    def test_uniform_clamp_distributes_total_force_and_zero_moment(self):
        geometry = ArrayGeometry()
        model = TaxelArrayModel(geometry=geometry)
        readings = generate_uniform_clamp_readings(
            geometry,
            normal_force_n=100.0,
            tangential_force_n=40.0,
            tangential_axis="x",
        )
        model.set_force_field(readings)
        wrench = model.wrench()

        self.assertAlmostEqual(wrench["Fx"], 40.0)
        self.assertAlmostEqual(wrench["Fy"], 0.0)
        self.assertAlmostEqual(wrench["Fz"], 100.0)
        self.assertAlmostEqual(wrench["Mx"], 0.0)
        self.assertAlmostEqual(wrench["My"], 0.0)
        self.assertAlmostEqual(wrench["Mz"], 0.0)

    def test_bottom_right_distributes_force_and_generates_all_three_moments(self):
        geometry = ArrayGeometry(pitch_x_mm=25.0, pitch_y_mm=25.0)
        model = TaxelArrayModel(geometry=geometry)
        readings = generate_bottom_right_readings(
            geometry,
            normal_force_n=100.0,
            tangential_force_n=40.0,
            tangential_axis="x",
        )
        model.set_force_field(readings)
        wrench = model.wrench()

        self.assertAlmostEqual(wrench["Fx"], 40.0)
        self.assertAlmostEqual(wrench["Fy"], 0.0)
        self.assertAlmostEqual(wrench["Fz"], 100.0)
        self.assertAlmostEqual(wrench["Mx"], -1.25)
        self.assertAlmostEqual(wrench["My"], -1.25)
        self.assertAlmostEqual(wrench["Mz"], 0.50)


class PyQtTaxelWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_delayed_frames_keep_real_elapsed_time(self):
        with patch("time.perf_counter", return_value=100.0) as clock:
            window = PyQtTaxelWindow(start_timer=False)
            self.addCleanup(window.close)
            clock.return_value = 100.5
            window.advance_frame()
            clock.return_value = 102.5
            window.advance_frame()
            np.testing.assert_allclose(window.history.relative_times(), [-2.5, -2.0, 0.0])
            np.testing.assert_allclose(
                window.force_curves["Fz"].getData()[0], [-2.5, -2.0, 0.0],
            )
            self.assertEqual(window.timer.timerType(), QtCore.Qt.TimerType.PreciseTimer)

    def test_history_expires_by_age_after_a_stall(self):
        with patch("time.perf_counter", return_value=100.0) as clock:
            window = PyQtTaxelWindow(history_seconds=1.0, start_timer=False)
            self.addCleanup(window.close)
            clock.return_value = 100.5
            window.advance_frame()
            clock.return_value = 101.5
            window.advance_frame()
            np.testing.assert_allclose(window.history.relative_times(), [-1.0, 0.0])
            clock.return_value = 103.0
            window.advance_frame()
            self.assertEqual(len(window.history), 1)
            np.testing.assert_allclose(window.history.relative_times(), [0.0])

    def test_cloud_window_fits_an_800_pixel_workspace(self):
        window = PyQtTaxelWindow(view="cloud", start_timer=False)
        self.addCleanup(window.close)
        window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.resize(800, 600)
        window.show()
        self.application.processEvents()
        self.assertEqual(window.width(), 800)
        self.assertLessEqual(window.minimumSizeHint().width(), 800)
        self.assertTrue(window.selected_label.wordWrap())
        self.assertLess(
            window.selected_label.geometry().bottom(), window.field_plot.geometry().top(),
        )

    def test_window_updates_and_selection_switches_complete_history(self):
        window = PyQtTaxelWindow(hz=20.0, history_seconds=0.25, start_timer=False)
        for _frame in range(7):
            window.advance_frame()

        window.select_taxel(2, 0)
        self.application.processEvents()

        expected = window.history.selected_taxel_matrix(2, 0)
        curve_x, curve_y = window.taxel_curves["fz"].getData()
        self.assertEqual(window.selected, (2, 0))
        self.assertEqual(len(window.history), 5)
        np.testing.assert_allclose(curve_x, window.history.relative_times())
        np.testing.assert_allclose(curve_y, expected[:, 2])
        self.assertIn("row=2, col=0", window.selected_label.text())
        window.close()

    def test_invalid_window_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            PyQtTaxelWindow(hz=0.0, start_timer=False)

    def test_clamp_slider_window_uses_uniform_force(self):
        window = PyQtTaxelWindow(
            peak_force_n=100.0,
            scenario="clamp-slider",
            tangential_force_n=40.0,
            tangential_axis="x",
            start_timer=False,
        )
        wrench = window.model.wrench()

        self.assertAlmostEqual(wrench["Fx"], 40.0)
        self.assertAlmostEqual(wrench["Fz"], 100.0)
        self.assertAlmostEqual(wrench["Mz"], 0.0)
        window.close()

    def test_net_plots_cover_configured_signed_shear_loads(self):
        for scenario in ("clamp-slider", "bottom-right-4"):
            for axis in ("x", "y"):
                for normal, shear in ((100.0, -40.0), (5.0, 40.0), (5.0, -40.0)):
                    with self.subTest(scenario=scenario, axis=axis, normal=normal, shear=shear):
                        window = PyQtTaxelWindow(
                            scenario=scenario, peak_force_n=normal,
                            tangential_force_n=shear, tangential_axis=axis, start_timer=False,
                        )
                        self.addCleanup(window.close)
                        wrench = window.model.wrench()
                        for plot, components in (
                            (window.force_plot, ("Fx", "Fy", "Fz")),
                            (window.moment_plot, ("Mx", "My", "Mz")),
                        ):
                            low, high = plot.viewRange()[1]
                            for component in components:
                                self.assertLess(low, wrench[component], component)
                                self.assertGreater(high, wrench[component], component)

    def test_bottom_right_window_updates_wrench(self):
        geometry = ArrayGeometry(pitch_x_mm=25.0, pitch_y_mm=25.0)
        window = PyQtTaxelWindow(
            geometry=geometry,
            peak_force_n=100.0,
            scenario="bottom-right-4",
            tangential_force_n=40.0,
            tangential_axis="x",
            start_timer=False,
        )
        wrench = window.model.wrench()

        self.assertAlmostEqual(wrench["Fx"], 40.0)
        self.assertAlmostEqual(wrench["Fz"], 100.0)
        self.assertAlmostEqual(wrench["Mx"], -1.25)
        self.assertAlmostEqual(wrench["My"], -1.25)
        self.assertAlmostEqual(wrench["Mz"], 0.50)
        window.close()

    def test_circle_taxels_render_with_gap(self):
        geometry = ArrayGeometry(
            pitch_x_mm=25.0,
            pitch_y_mm=25.0,
            taxel_width_x_mm=20.0,
            taxel_width_y_mm=20.0,
        )
        window = PyQtTaxelWindow(
            geometry=geometry,
            peak_force_n=100.0,
            scenario="clamp-slider",
            tangential_force_n=40.0,
            taxel_shape="circle",
            start_timer=False,
        )

        self.assertTrue(all(isinstance(item, QtWidgets.QGraphicsEllipseItem) for item in window.taxel_rectangles))
        self.assertIn("shape=circle", window.selected_label.text())
        window.close()

    def test_non_square_geometry_builds_every_taxel_and_switches_selection(self):
        geometry = ArrayGeometry(
            rows=2,
            cols=4,
            pitch_x_mm=30.0,
            pitch_y_mm=25.0,
            taxel_width_x_mm=20.0,
            taxel_width_y_mm=15.0,
        )
        window = PyQtTaxelWindow(
            hz=10.0,
            history_seconds=0.3,
            geometry=geometry,
            start_timer=False,
        )
        window.select_taxel(1, 3)
        self.application.processEvents()

        self.assertEqual(len(window.taxel_rectangles), 8)
        self.assertEqual(len(window.arrow_heads), 8)
        self.assertEqual(window.selected, (1, 3))
        self.assertIn("size=20×15 mm", window.selected_label.text())
        window.close()

    def test_default_geometry_renders_taxels_with_visual_gap(self):
        # Default geometry has pitch == width on both axes (20/20), so every
        # cell must render shrunk to 88% and stay centred on its cell centre.
        window = PyQtTaxelWindow(start_timer=False)
        x_centres, y_centres = window.geometry.centre_coordinates_mm()

        for row in range(window.geometry.rows):
            for col in range(window.geometry.cols):
                rect = window.taxel_rectangles[row * window.geometry.cols + col].rect()
                self.assertAlmostEqual(rect.width(), 20.0 * 0.88, delta=1e-6)
                self.assertAlmostEqual(rect.height(), 20.0 * 0.88, delta=1e-6)
                self.assertAlmostEqual(rect.center().x(), x_centres[col], delta=1e-6)
                self.assertAlmostEqual(rect.center().y(), y_centres[row], delta=1e-6)
        window.close()

    def test_natural_gap_geometry_renders_true_taxel_rect(self):
        # pitch > width on both axes: a natural gap exists, so items must
        # render exactly the logical taxel_rect_mm with no visual inset.
        geometry = ArrayGeometry(
            rows=2,
            cols=4,
            pitch_x_mm=30.0,
            pitch_y_mm=25.0,
            taxel_width_x_mm=20.0,
            taxel_width_y_mm=15.0,
        )
        window = PyQtTaxelWindow(geometry=geometry, start_timer=False)

        for row in range(geometry.rows):
            for col in range(geometry.cols):
                rect = window.taxel_rectangles[row * geometry.cols + col].rect()
                left, bottom, width, height = geometry.taxel_rect_mm(row, col)
                # QRectF stores (x, y, w, h); taxel_rect_mm's "bottom" is the
                # QRectF y (its top()); QRectF.bottom() would be y + height.
                self.assertAlmostEqual(rect.left(), left, delta=1e-6)
                self.assertAlmostEqual(rect.top(), bottom, delta=1e-6)
                self.assertAlmostEqual(rect.width(), width, delta=1e-6)
                self.assertAlmostEqual(rect.height(), height, delta=1e-6)
        window.close()


class CloudViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_moment_colourbar_covers_both_signs_equally(self):
        cases = {
            "mx": ((2, 1, 2, 5.0), (0, 1, 2, 5.0)),
            "my": ((1, 0, 2, 5.0), (1, 2, 2, 5.0)),
            "mz": ((1, 2, 1, 5.0), (1, 2, 1, -5.0)),
        }
        for channel, loads in cases.items():
            for row, col, axis, force in loads:
                with self.subTest(channel=channel, load=(row, col, axis, force)):
                    readings = np.zeros((3, 3, 3))
                    readings[row, col, axis] = force
                    with patch("pyqt_live.generate_simulated_readings", return_value=readings):
                        window = PyQtTaxelWindow(
                            view="cloud", cloud_channel=channel, start_timer=False,
                        )
                    self.addCleanup(window.close)
                    np.testing.assert_allclose(window.cloud_colourbar.levels(), (-0.1, 0.1))

    def test_shear_colourbar_covers_load_independently_of_normal_force(self):
        for scale in ("auto", "fixed"):
            for shear in (-40.0, 40.0):
                with self.subTest(scale=scale, shear=shear):
                    window = PyQtTaxelWindow(
                        view="cloud", cloud_channel="shear", cloud_scale=scale,
                        scenario="clamp-slider", peak_force_n=5.0,
                        tangential_force_n=shear, start_timer=False,
                    )
                    self.addCleanup(window.close)
                    np.testing.assert_allclose(window.cloud_colourbar.levels(), (0.0, 40.0 / 9.0))
                    window.set_cloud_channel("fz")
                    np.testing.assert_allclose(window.cloud_colourbar.levels(), (0.0, 5.0 / 9.0))

    def test_fixed_mz_range_covers_shear_without_inflating_mx_my(self):
        window = PyQtTaxelWindow(
            view="cloud", cloud_channel="mz", cloud_scale="fixed",
            scenario="bottom-right-4", peak_force_n=5.0,
            tangential_force_n=-100.0, start_timer=False,
        )
        self.addCleanup(window.close)
        low, high = window.cloud_colourbar.levels()
        self.assertLessEqual(low, -0.5)
        self.assertGreaterEqual(high, 0.5)
        for channel in ("mx", "my"):
            window.set_cloud_channel(channel)
            np.testing.assert_allclose(window.cloud_colourbar.levels(), (-0.3, 0.3))

    def test_cloud_window_renders_cloud_and_hides_array_layers(self):
        window = PyQtTaxelWindow(view="cloud", cloud_channel="fz", start_timer=False)
        for _frame in range(3):
            window.advance_frame()
        self.application.processEvents()

        self.assertEqual(window.view_mode, "cloud")
        self.assertEqual(window.cloud_channel, "fz")
        self.assertFalse(window.cloud_channel_row.isHidden())
        image = window.cloud_image.image
        self.assertIsNotNone(image)
        self.assertEqual(image.shape[2], 4)
        visible = image[..., 3] > 0
        self.assertTrue(visible.any())
        self.assertTrue(np.isfinite(image[visible, :3]).all())
        self.assertTrue(window.cloud_image.isVisible())
        self.assertFalse(window.arrow_lines[0].isVisible())
        self.assertFalse(window.arrow_heads[0].isVisible())
        self.assertTrue(window.selection_outline.isVisible())
        self.assertEqual(
            window.taxel_rectangles[0].brush().style(),
            QtCore.Qt.BrushStyle.NoBrush,
        )
        self.assertIn("cloud | fz [N]", window._field_title)
        window.close()

    def test_cloud_mode_keeps_right_side_curves_updating(self):
        window = PyQtTaxelWindow(view="cloud", start_timer=False)
        for _frame in range(4):
            window.advance_frame()
        self.application.processEvents()

        curve_x, curve_y = window.force_curves["Fz"].getData()
        self.assertIsNotNone(curve_x)
        self.assertEqual(len(curve_x), len(window.history))
        self.assertTrue(len(curve_x) > 0)
        np.testing.assert_allclose(curve_y, window.history.wrench_matrix()[:, 2])
        moment_x, _moment_y = window.moment_curves["Mz"].getData()
        self.assertEqual(len(moment_x), len(window.history))
        window.close()

    def test_set_view_array_restores_array_layers(self):
        window = PyQtTaxelWindow(
            view="cloud",
            peak_force_n=100.0,
            scenario="clamp-slider",
            tangential_force_n=40.0,
            tangential_axis="x",
            start_timer=False,
        )
        self.application.processEvents()
        window.set_view("array")
        window.advance_frame()
        self.application.processEvents()

        self.assertEqual(window.view_mode, "array")
        self.assertTrue(window.cloud_channel_row.isHidden())
        self.assertFalse(window.cloud_image.isVisible())
        self.assertTrue(window.selection_outline.isVisible())
        self.assertNotEqual(
            window.taxel_rectangles[0].brush().style(),
            QtCore.Qt.BrushStyle.NoBrush,
        )
        self.assertTrue(window.arrow_lines[0].isVisible())
        self.assertTrue(window.arrow_heads[0].isVisible())
        self.assertIn("colour=fz, black arrows=fx/fy", window._field_title)
        window.close()

    def test_set_cloud_channel_updates_state_title_and_render(self):
        window = PyQtTaxelWindow(view="cloud", start_timer=False)
        window.set_cloud_channel("mz")
        self.application.processEvents()

        self.assertEqual(window.cloud_channel, "mz")
        self.assertIn("mz", window._field_title)
        self.assertIn("N·m", window._field_title)
        self.assertTrue(window.cloud_channel_buttons["mz"].isChecked())
        image = window.cloud_image.image
        self.assertIsNotNone(image)
        self.assertTrue((image[..., 3] > 0).any())
        window.close()

    def test_colourbar_gradient_follows_channel_family(self):
        window = PyQtTaxelWindow(view="cloud", cloud_channel="my", start_timer=False)
        window.set_cloud_channel("fz")
        self.application.processEvents()

        self.assertTrue(window.cloud_colourbar_ok)
        stops, colours = window._cloud_lut()
        stops01 = (stops - stops[0]) / (stops[-1] - stops[0])
        bar_stops, bar_colours = window.cloud_colourbar._colorMap.getStops()
        np.testing.assert_allclose(bar_stops, stops01)
        np.testing.assert_allclose(
            bar_colours,
            np.column_stack((colours.astype(int), np.full(len(stops), 255))),
        )
        window.close()

    def test_cloud_auto_scale_floors_at_five_percent_of_ceiling(self):
        window = PyQtTaxelWindow(view="cloud", cloud_channel="fz", start_timer=False)
        window._cloud_running_max = 0.0

        window._render_cloud_view(np.zeros(window.geometry.shape))

        vmin, vmax = window._cloud_display_range()
        self.assertAlmostEqual(vmin, 0.0)
        self.assertAlmostEqual(vmax, 0.05 * window.field_colour_max_n)
        window.close()

    def test_cloud_auto_scale_attacks_instantly_and_caps_at_ceiling(self):
        window = PyQtTaxelWindow(view="cloud", cloud_channel="fz", peak_force_n=5.0, start_timer=False)
        window._cloud_running_max = 0.0

        readings = np.zeros(window.geometry.shape)
        readings[1, 1, 2] = 2.0
        window._render_cloud_view(readings)
        _vmin, vmax = window._cloud_display_range()
        self.assertAlmostEqual(vmax, 2.0)

        readings[1, 1, 2] = 50.0
        window._render_cloud_view(readings)
        _vmin, vmax = window._cloud_display_range()
        self.assertAlmostEqual(vmax, window.field_colour_max_n)
        window.close()

    def test_cloud_auto_scale_decays_between_frames(self):
        with patch("time.perf_counter", return_value=100.0) as clock:
            window = PyQtTaxelWindow(view="cloud", start_timer=False)
            self.addCleanup(window.close)
            window._cloud_running_max = 5.0
            quiet = np.zeros(window.geometry.shape)
            clock.return_value = 100.0 + 1.0 / 30.0
            window._render_cloud_view(quiet)
            first_bound = window._cloud_display_range()[1]
            clock.return_value = 100.0 + 2.0 / 30.0
            window._render_cloud_view(quiet)
            second_bound = window._cloud_display_range()[1]
            self.assertLess(second_bound, first_bound)
            self.assertGreater(second_bound, 0.05 * window.field_colour_max_n)

    def test_cloud_decay_uses_elapsed_seconds_not_render_count(self):
        loaded = np.zeros((3, 3, 3))
        loaded[1, 1, 2] = 2.0
        with patch("time.perf_counter", return_value=100.0) as clock:
            with patch("pyqt_live.generate_simulated_readings", return_value=loaded) as source:
                window = PyQtTaxelWindow(view="cloud", start_timer=False)
                self.addCleanup(window.close)
                source.return_value = np.zeros_like(loaded)
                clock.return_value = 102.0
                window.advance_frame()
                np.testing.assert_allclose(window.cloud_colourbar.levels(), (0.0, 1.0))
                for _ in range(3):
                    window.set_view("array")
                    window.set_view("cloud")
                np.testing.assert_allclose(window.cloud_colourbar.levels(), (0.0, 1.0))
                clock.return_value = 104.0
                window.advance_frame()
                np.testing.assert_allclose(window.cloud_colourbar.levels(), (0.0, 0.5))

    def test_cloud_fixed_scale_range_stays_constant(self):
        window = PyQtTaxelWindow(
            view="cloud",
            cloud_channel="fz",
            cloud_scale="fixed",
            peak_force_n=5.0,
            start_timer=False,
        )
        loaded = np.zeros(window.geometry.shape)
        loaded[0, 0, 2] = 2.0

        window._render_cloud_view(loaded)
        range_one = window._cloud_display_range()
        window._render_cloud_view(np.zeros(window.geometry.shape))
        range_two = window._cloud_display_range()

        self.assertEqual(range_one, range_two)
        self.assertAlmostEqual(range_one[0], 0.0)
        self.assertAlmostEqual(range_one[1], window.field_colour_max_n)
        window.close()

    def test_invalid_cloud_scale_is_rejected(self):
        with self.assertRaises(ValueError):
            PyQtTaxelWindow(cloud_scale="bogus", start_timer=False)

    def test_invalid_view_and_channel_are_rejected(self):
        with self.assertRaises(ValueError):
            PyQtTaxelWindow(view="bogus", start_timer=False)
        with self.assertRaises(ValueError):
            PyQtTaxelWindow(cloud_channel="bogus", start_timer=False)
        window = PyQtTaxelWindow(start_timer=False)
        with self.assertRaises(ValueError):
            window.set_view("bogus")
        with self.assertRaises(ValueError):
            window.set_cloud_channel("bogus")
        self.assertEqual(window.view_mode, "array")
        self.assertEqual(window.cloud_channel, "fz")
        window.close()


class ArrowAlignmentTests(unittest.TestCase):
    """The arrow head must point along the same direction as its line.

    Regression guard for the mirrored-arrow defect: makeArrowPath points
    along -x with its tip at the anchor and setStyle rotates counter-
    clockwise, so an angle of ``180 - theta`` rendered every head mirrored
    across the x-axis (invisible for pure +x forces, wrong for off-axis).
    """

    OFF_AXIS_CASES = {
        (1, 1): (1.0, 1.0),    # +45 deg
        (2, 1): (0.0, 1.0),    # +90 deg
        (1, 0): (-1.0, 0.5),   # ~153 deg
        (1, 2): (0.6, -1.0),   # ~-59 deg
    }

    def test_arrow_heads_point_along_the_force_direction(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        window = PyQtTaxelWindow(start_timer=False)
        readings = np.zeros((3, 3, 3), dtype=np.float64)
        for (row, col), (fx, fy) in self.OFF_AXIS_CASES.items():
            readings[row, col, 0] = fx
            readings[row, col, 1] = fy
        window.model.set_force_field(readings)
        window._update_field(readings)

        for (row, col), (fx, fy) in self.OFF_AXIS_CASES.items():
            index = row * 3 + col
            line_x, line_y = window.arrow_lines[index].getData()
            line_direction_deg = math.degrees(
                math.atan2(line_y[1] - line_y[0], line_x[1] - line_x[0])
            )
            head = window.arrow_heads[index]
            # Tip sits at the local origin (rotations keep it there); the base
            # vertices are polygon entries 1..3 of the closed path polygon.
            polygon = head.path.toSubpathPolygons()[0]
            points = [(polygon.at(i).x(), polygon.at(i).y()) for i in range(polygon.count())]
            base_centre = np.mean(np.asarray(points[1:4]), axis=0)
            pointing_deg = math.degrees(math.atan2(-base_centre[1], -base_centre[0]))
            error_deg = abs((pointing_deg - line_direction_deg + 180.0) % 360.0 - 180.0)
            self.assertLess(error_deg, 0.01, msg=f"({row},{col}) fx={fx} fy={fy}")
            self.assertAlmostEqual(head.x(), line_x[1], places=6)
            self.assertAlmostEqual(head.y(), line_y[1], places=6)
        window.close()


if __name__ == "__main__":
    unittest.main()
