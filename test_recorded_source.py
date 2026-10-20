import tempfile
import unittest
from pathlib import Path

import numpy as np

from recorded_source import load_recording


def write_npz(directory, name, **arrays):
    path = Path(directory) / name
    np.savez_compressed(path, **arrays)
    return path


class TactileTimeSeriesTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.directory = self._directory.name

    def _tactile(self, frames, sensors, channels, u_size, v_size):
        # (T, S, C, U, V) with a unique value per (t, s, c, u, v), matching
        # ShearCue records where u is the first spatial index.
        grid = np.empty((frames, sensors, channels, u_size, v_size), dtype=np.float64)
        for t in range(frames):
            for s in range(sensors):
                for c in range(channels):
                    for u in range(u_size):
                        for v in range(v_size):
                            grid[t, s, c, u, v] = t * 10000 + s * 1000 + c * 100 + u * 10 + v
        return grid

    def test_two_sensor_timeseries_transposes_to_rows_v_cols_u(self):
        grid = self._tactile(3, 2, 3, u_size=6, v_size=4)
        times = np.array([0.0, 0.5, 1.25])
        path = write_npz(self.directory, "record.npz", tactile=grid, times=times,
                         channels=np.array(["Fu", "Fv", "Fn"]), units="N")

        recording = load_recording(path)

        self.assertEqual(recording.schema, "tactile-timeseries")
        self.assertEqual(recording.time_kind, "times")
        np.testing.assert_allclose(recording.times, times)
        self.assertEqual(recording.channels, ("Fu", "Fv", "Fn"))
        self.assertEqual(recording.units, "N")
        self.assertEqual(recording.sensor_names(), ("tactile_fixed", "tactile_moving"))

        fixed = recording.sensors["tactile_fixed"]
        self.assertEqual((fixed.rows, fixed.cols), (4, 6))  # rows = v, cols = u
        self.assertEqual(fixed.frames.shape, (3, 4, 6, 3))
        for t in range(3):
            for v in range(4):
                for u in range(6):
                    for channel in range(3):
                        self.assertEqual(
                            fixed.frames[t, v, u, channel],
                            t * 10000 + channel * 100 + u * 10 + v,
                        )
        moving = recording.sensors["tactile_moving"]
        self.assertEqual(moving.frames[1, 2, 5, 2], 10000 + 1000 + 2 * 100 + 5 * 10 + 2)

    def test_logical_time_key_is_used_when_times_are_absent(self):
        grid = self._tactile(2, 2, 3, u_size=3, v_size=3)
        path = write_npz(self.directory, "logical.npz", tactile=grid,
                         logical_times=np.array([10.0, 10.5]), actual_times=np.array([1.0, 2.0]))

        recording = load_recording(path)

        self.assertEqual(recording.time_kind, "logical_times")
        np.testing.assert_allclose(recording.times, [10.0, 10.5])

    def test_missing_time_keys_fall_back_to_indices(self):
        grid = self._tactile(4, 2, 3, u_size=2, v_size=2)
        path = write_npz(self.directory, "no-time.npz", tactile=grid)

        recording = load_recording(path)

        self.assertEqual(recording.time_kind, "index")
        np.testing.assert_allclose(recording.times, [0.0, 1.0, 2.0, 3.0])

    def test_single_sensor_tactile_array(self):
        grid = self._tactile(2, 1, 3, u_size=5, v_size=3)
        path = write_npz(self.directory, "single.npz", tactile=grid, times=np.array([0.0, 1.0]))

        recording = load_recording(path)

        self.assertEqual(recording.sensor_names(), ("sensor0",))
        self.assertEqual(recording.sensors["sensor0"].frames.shape, (2, 3, 5, 3))

    def test_nonfinite_or_wrong_channel_count_is_rejected(self):
        grid = self._tactile(2, 2, 3, u_size=2, v_size=2)
        grid[0, 0, 0, 0, 0] = np.nan
        bad = write_npz(self.directory, "nan.npz", tactile=grid, times=np.array([0.0, 1.0]))
        with self.assertRaises(ValueError):
            load_recording(bad)

        wrong = self._tactile(2, 2, 2, u_size=2, v_size=2)
        bad = write_npz(self.directory, "channels.npz", tactile=wrong, times=np.array([0.0, 1.0]))
        with self.assertRaises(ValueError):
            load_recording(bad)

    def test_mismatched_time_length_is_rejected(self):
        grid = self._tactile(3, 2, 3, u_size=2, v_size=2)
        bad = write_npz(self.directory, "times.npz", tactile=grid, times=np.array([0.0, 1.0]))
        with self.assertRaises(ValueError):
            load_recording(bad)


class TrajectoryAndSnapshotTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.directory = self._directory.name

    def test_trajectory_format_keeps_row_col_order(self):
        readings = np.arange(2 * 3 * 4 * 3, dtype=np.float64).reshape(2, 3, 4, 3)
        path = write_npz(self.directory, "traj.npz", times=np.array([0.0, 0.2]), readings=readings)

        recording = load_recording(path)

        self.assertEqual(recording.schema, "tactile-trajectory")
        sensor = recording.sensors["taxel"]
        self.assertEqual((sensor.rows, sensor.cols), (3, 4))
        np.testing.assert_array_equal(sensor.frames, readings)
        self.assertEqual(recording.channels, ("fx", "fy", "fz"))

    def test_snapshot_keys_become_one_frame_with_v_rows(self):
        # ShearCue snapshot arrays are (channel, u, v) = (3, 4, 6).
        fixed = np.arange(3 * 4 * 6, dtype=np.float64).reshape(3, 4, 6)
        moving = fixed * 2.0
        path = write_npz(self.directory, "snap.npz", tactile_fixed=fixed, tactile_moving=moving,
                         channels=np.array(["Fu", "Fv", "Fn"]), units="N")

        recording = load_recording(path)

        self.assertEqual(recording.schema, "tactile-snapshot")
        self.assertEqual(recording.sensor_names(), ("tactile_fixed", "tactile_moving"))
        self.assertEqual(recording.frame_count, 1)
        self.assertEqual(recording.time_kind, "snapshot")
        sensor = recording.sensors["tactile_fixed"]
        self.assertEqual((sensor.rows, sensor.cols), (6, 4))
        self.assertEqual(sensor.frames.shape, (1, 6, 4, 3))
        self.assertEqual(sensor.frames[0, 5, 2, 1], fixed[1, 2, 5])  # frame[v,u,c] = fixed[c,u,v]

    def test_unknown_arrays_are_rejected(self):
        path = write_npz(self.directory, "empty.npz", unrelated=np.zeros(3))
        with self.assertRaises(ValueError):
            load_recording(path)


if __name__ == "__main__":
    unittest.main()
