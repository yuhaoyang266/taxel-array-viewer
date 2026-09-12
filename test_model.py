import unittest
from types import SimpleNamespace

import numpy as np

from model import ArrayGeometry, TaxelArrayModel


class TaxelArrayModelTests(unittest.TestCase):
    def test_zero_field_produces_zero_wrench(self):
        model = TaxelArrayModel()

        self.assertEqual(model.wrench(), {component: 0.0 for component in ("Fx", "Fy", "Fz", "Mx", "My", "Mz")})

    def test_centre_normal_force_has_no_moment(self):
        model = TaxelArrayModel()
        model.set_taxel_force(1, 1, [0.0, 0.0, 2.0])

        wrench = model.wrench()

        self.assertAlmostEqual(wrench["Fz"], 2.0)
        self.assertAlmostEqual(wrench["Mx"], 0.0)
        self.assertAlmostEqual(wrench["My"], 0.0)
        self.assertAlmostEqual(wrench["Mz"], 0.0)

    def test_corner_normal_force_has_expected_moments(self):
        geometry = ArrayGeometry(
            pitch_x_mm=10.0,
            pitch_y_mm=10.0,
            taxel_width_x_mm=10.0,
            taxel_width_y_mm=10.0,
        )
        model = TaxelArrayModel(geometry=geometry)
        model.set_taxel_force(2, 2, [0.0, 0.0, 2.0])

        wrench = model.wrench()

        self.assertAlmostEqual(wrench["Mx"], 0.02)
        self.assertAlmostEqual(wrench["My"], -0.02)
        self.assertAlmostEqual(wrench["Mz"], 0.0)

    def test_tangential_force_has_expected_lever_arm_moment(self):
        geometry = ArrayGeometry(
            pitch_x_mm=10.0,
            pitch_y_mm=10.0,
            taxel_width_x_mm=10.0,
            taxel_width_y_mm=10.0,
        )
        model = TaxelArrayModel(geometry=geometry)
        model.set_taxel_force(2, 1, [2.0, 0.0, 0.0])

        wrench = model.wrench()

        self.assertAlmostEqual(wrench["Fx"], 2.0)
        self.assertAlmostEqual(wrench["Mz"], -0.02)

    def test_balanced_tangential_pair_produces_pure_mz(self):
        geometry = ArrayGeometry(
            pitch_x_mm=10.0,
            pitch_y_mm=10.0,
            taxel_width_x_mm=10.0,
            taxel_width_y_mm=10.0,
        )
        model = TaxelArrayModel(geometry=geometry)
        model.set_taxel_force(2, 1, [-1.0, 0.0, 0.0])
        model.set_taxel_force(0, 1, [1.0, 0.0, 0.0])

        wrench = model.wrench()

        self.assertAlmostEqual(wrench["Fx"], 0.0)
        self.assertAlmostEqual(wrench["Fy"], 0.0)
        self.assertAlmostEqual(wrench["Fz"], 0.0)
        self.assertAlmostEqual(wrench["Mx"], 0.0)
        self.assertAlmostEqual(wrench["My"], 0.0)
        self.assertAlmostEqual(wrench["Mz"], 0.02)

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(ValueError):
            ArrayGeometry(pitch_x_mm=0.0)
        with self.assertRaises(ValueError):
            TaxelArrayModel(readings=np.zeros((9, 3)))

        readings = np.zeros((3, 3, 3))
        readings[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            TaxelArrayModel(readings=readings)

    def test_dynamic_geometry_positions_footprint_and_gap_hit_testing(self):
        geometry = ArrayGeometry(
            rows=2,
            cols=4,
            pitch_x_mm=30.0,
            pitch_y_mm=25.0,
            taxel_width_x_mm=20.0,
            taxel_width_y_mm=15.0,
        )
        model = TaxelArrayModel(geometry=geometry)

        self.assertEqual(model.readings.shape, (2, 4, 3))
        self.assertEqual(model.positions.shape, (8, 3))
        self.assertAlmostEqual(geometry.footprint_x_mm, 110.0)
        self.assertAlmostEqual(geometry.footprint_y_mm, 40.0)
        self.assertAlmostEqual(geometry.taxel_area_m2, 0.0003)
        self.assertEqual(geometry.locate_taxel(-45.0, -12.5), (0, 0))
        self.assertIsNone(geometry.locate_taxel(-30.0, -12.5))

    def test_taxel_width_cannot_exceed_pitch(self):
        with self.assertRaises(ValueError):
            ArrayGeometry(pitch_x_mm=15.0, taxel_width_x_mm=20.0)

    def test_circle_hit_testing_respects_gap(self):
        geometry = ArrayGeometry(
            rows=3,
            cols=3,
            pitch_x_mm=25.0,
            pitch_y_mm=25.0,
            taxel_width_x_mm=20.0,
            taxel_width_y_mm=20.0,
        )

        self.assertEqual(geometry.locate_taxel(0.0, 0.0, shape="circle"), (1, 1))
        self.assertIsNone(geometry.locate_taxel(12.5, 0.0, shape="circle"))


class TaxelArrayAppSmokeTests(unittest.TestCase):
    def test_headless_figure_updates(self):
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        from app import TaxelArrayApp

        application = TaxelArrayApp()
        application.model.set_taxel_force(2, 2, [1.0, -0.5, 2.0])
        application.redraw()

        self.assertAlmostEqual(application.force_axis.patches[0].get_height(), 1.0)
        self.assertAlmostEqual(application.force_axis.patches[1].get_height(), -0.5)
        self.assertAlmostEqual(application.force_axis.patches[2].get_height(), 2.0)
        plt.close(application.figure)

    def test_taxel_selection_and_slider_update_model(self):
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        from app import TaxelArrayApp

        application = TaxelArrayApp()
        click = SimpleNamespace(inaxes=application.field_axis, xdata=2.1, ydata=0.1)
        application._on_click(click)
        application.sliders["fx"].set_val(1.25)

        self.assertEqual(application.model.selected, (0, 2))
        self.assertAlmostEqual(application.model.readings[0, 2, 0], 1.25)
        self.assertAlmostEqual(application.force_axis.patches[0].get_height(), 1.25)
        plt.close(application.figure)


if __name__ == "__main__":
    unittest.main()
