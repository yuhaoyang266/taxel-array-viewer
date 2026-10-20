import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import numpy as np
from PySide6 import QtWidgets

from recorded_source import load_recording
from replay_live import build_windows, geometry_for, resolve_times


DEFAULTS = dict(pitch_x_mm=2.0, pitch_y_mm=2.0,
                taxel_width_x_mm=2.0, taxel_width_y_mm=2.0)
ROWS = 5   # v
COLS = 3   # u


class ReplayWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.frames = 4
        grid = np.zeros((self.frames, 2, 3, COLS, ROWS), dtype=np.float64)
        for t in range(self.frames):
            grid[t, :, 2] = t + 1.0          # normal compression grows per frame
            grid[t, :, 0] = 0.1 * (t + 1)
        self.grid = grid
        self.times = np.array([0.0, 0.1, 0.2, 0.3])
        self.path = Path(self._directory.name) / "record.npz"
        np.savez_compressed(self.path, tactile=grid, times=self.times,
                            channels=np.array(["Fu", "Fv", "Fn"]), units="N")
        self.recording = load_recording(self.path)

    def _geometries(self, config=None):
        config = config or {}
        return {
            name: geometry_for(name, sensor, config, DEFAULTS)
            for name, sensor in self.recording.sensors.items()
        }

    def _windows(self, *, loop=True):
        times, note = resolve_times(self.recording, 30.0)
        return build_windows(self.recording, self._geometries(), loop=loop,
                             times=times, time_note=note)

    def test_window_already_holds_the_first_recorded_frame(self):
        windows = self._windows()
        self.addCleanup(lambda: [window.close() for window in windows.values()])
        window = windows["tactile_fixed"]

        self.assertEqual(len(window.history), 1)
        self.assertEqual(window.frame_index, 1)
        self.assertEqual((window.geometry.rows, window.geometry.cols), (ROWS, COLS))
        np.testing.assert_array_equal(
            window._last_readings, self.recording.sensors["tactile_fixed"].frames[0]
        )
        self.assertIn("recorded simulation data", window.windowTitle())
        status = window.statusBar().currentMessage()
        self.assertIn("tactile_fixed", status)
        self.assertIn("1/4", status)

    def test_advance_keeps_measured_values_and_loops(self):
        windows = self._windows(loop=True)
        self.addCleanup(lambda: [window.close() for window in windows.values()])
        window = windows["tactile_fixed"]

        for expected in range(1, self.frames):
            window.advance_frame()
            np.testing.assert_array_equal(
                window._last_readings, self.recording.sensors["tactile_fixed"].frames[expected]
            )

        window.advance_frame()  # wraps to frame 0
        np.testing.assert_array_equal(
            window._last_readings, self.recording.sensors["tactile_fixed"].frames[0]
        )
        self.assertFalse(window.finished)
        self.assertEqual(window.frame_index, self.frames + 1)

    def test_no_loop_stops_at_the_end(self):
        windows = self._windows(loop=False)
        self.addCleanup(lambda: [window.close() for window in windows.values()])
        window = windows["tactile_fixed"]

        for _ in range(self.frames):
            window.advance_frame()
        self.assertTrue(window.finished)
        last = window._last_readings.copy()
        window.advance_frame()
        np.testing.assert_array_equal(window._last_readings, last)
        self.assertIn("end", window.statusBar().currentMessage())

    def test_geometry_comes_from_config_and_rows_cols_must_match(self):
        config = {"tactile_fixed": dict(rows=ROWS, cols=COLS, pitch_x_mm=1.0, pitch_y_mm=1.0,
                                        taxel_width_x_mm=1.0, taxel_width_y_mm=1.0)}
        geometry, note = geometry_for("tactile_fixed", self.recording.sensors["tactile_fixed"], config, DEFAULTS)
        self.assertEqual((geometry.rows, geometry.cols), (ROWS, COLS))
        self.assertAlmostEqual(geometry.pitch_x_mm, 1.0)
        self.assertIn("config", note)

        with self.assertRaises(ValueError):
            geometry_for("tactile_fixed", self.recording.sensors["tactile_fixed"],
                         {"tactile_fixed": dict(rows=99)}, DEFAULTS)

    def test_default_geometry_is_flagged_as_not_from_the_recording(self):
        geometry, note = geometry_for("tactile_fixed", self.recording.sensors["tactile_fixed"], {}, DEFAULTS)
        self.assertEqual((geometry.rows, geometry.cols), (ROWS, COLS))
        self.assertIn("录制无几何", note)

    def test_index_times_use_the_playback_rate(self):
        path = Path(self._directory.name) / "no-time.npz"
        np.savez_compressed(path, tactile=self.grid)
        recording = load_recording(path)
        times, note = resolve_times(recording, 10.0)
        np.testing.assert_allclose(times, [0.0, 0.1, 0.2, 0.3])
        self.assertIn("10", note)


if __name__ == "__main__":
    unittest.main()
