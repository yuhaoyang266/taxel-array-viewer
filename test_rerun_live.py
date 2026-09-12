import tempfile
import unittest
from pathlib import Path

import numpy as np

from live_source import generate_simulated_readings
from model import ArrayGeometry
from rerun_live import normal_force_colours, run_animation


class SimulatedLiveSourceTests(unittest.TestCase):
    def test_frame_contract_and_total_normal_force(self):
        readings = generate_simulated_readings(0.5, peak_force_n=5.0)

        self.assertEqual(readings.shape, (3, 3, 3))
        self.assertTrue(np.isfinite(readings).all())
        self.assertTrue(np.all(readings[:, :, 2] >= 0.0))
        total_normal_force = float(np.sum(readings[:, :, 2]))
        self.assertGreaterEqual(total_normal_force, 0.64 * 5.0)
        self.assertLessEqual(total_normal_force, 5.0)

    def test_generator_is_deterministic_and_moves(self):
        first = generate_simulated_readings(0.0)
        repeated = generate_simulated_readings(0.0)
        later = generate_simulated_readings(1.0)

        np.testing.assert_allclose(first, repeated)
        self.assertFalse(np.allclose(first, later))

    def test_generator_supports_non_square_geometry(self):
        geometry = ArrayGeometry(
            rows=2,
            cols=4,
            pitch_x_mm=25.0,
            pitch_y_mm=30.0,
            taxel_width_x_mm=20.0,
            taxel_width_y_mm=20.0,
        )

        readings = generate_simulated_readings(0.3, geometry=geometry)
        colours = normal_force_colours(readings, peak_force_n=5.0)

        self.assertEqual(readings.shape, (2, 4, 3))
        self.assertEqual(colours.shape, (8, 4))

    def test_colour_contract(self):
        readings = generate_simulated_readings(0.0)

        colours = normal_force_colours(readings, peak_force_n=5.0)

        self.assertEqual(colours.shape, (9, 4))
        self.assertEqual(colours.dtype, np.uint8)
        self.assertTrue(np.all(colours[:, 3] == 255))

    def test_invalid_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            generate_simulated_readings(0.0, peak_force_n=0.0)
        with self.assertRaises(ValueError):
            normal_force_colours(np.zeros((3, 3, 3)), peak_force_n=0.0)
        with self.assertRaises(ValueError):
            run_animation(hz=0.0, duration_s=0.1, save_rrd="unused.rrd")
        with self.assertRaises(ValueError):
            run_animation(duration_s=0.0, save_rrd="unused.rrd")


class RerunRecordingSmokeTests(unittest.TestCase):
    def test_finite_run_writes_rrd(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "taxel-live-smoke.rrd"
            geometry = ArrayGeometry(
                rows=2,
                cols=4,
                pitch_x_mm=25.0,
                pitch_y_mm=30.0,
                taxel_width_x_mm=20.0,
                taxel_width_y_mm=20.0,
            )

            frame_count = run_animation(
                hz=20.0,
                duration_s=0.15,
                geometry=geometry,
                save_rrd=output_path,
            )

            self.assertEqual(frame_count, 3)
            self.assertTrue(output_path.is_file())
            self.assertGreater(output_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
