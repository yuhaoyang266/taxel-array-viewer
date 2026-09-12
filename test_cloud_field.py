import unittest

import numpy as np

from cloud_field import (
    CLOUD_CHANNELS,
    DIVERGING_LUT,
    apply_lut,
    channel_map,
    interpolate_field,
)
from model import ArrayGeometry, TaxelArrayModel


class ChannelMapTests(unittest.TestCase):
    def test_constant_field_interpolates_to_same_constant_for_every_channel(self):
        geometry = ArrayGeometry()
        for index, channel in enumerate(CLOUD_CHANNELS):
            constant = 1.0 + index
            values = np.full((geometry.rows, geometry.cols), constant, dtype=np.float64)
            field, extent = interpolate_field(values, geometry, resolution=25)

            self.assertEqual(field.shape, (25, 25))
            np.testing.assert_allclose(field, constant, rtol=1e-9)
            self.assertAlmostEqual(extent[0], -geometry.footprint_x_mm / 2.0)
            self.assertAlmostEqual(extent[1], geometry.footprint_x_mm / 2.0)

    def test_nan_taxel_is_excluded_and_constant_neighbours_fill_the_grid(self):
        geometry = ArrayGeometry()
        values = np.full((geometry.rows, geometry.cols), 2.5, dtype=np.float64)
        values[1, 1] = np.nan
        field, _extent = interpolate_field(values, geometry, resolution=25)

        self.assertTrue(np.isfinite(field).all())
        np.testing.assert_allclose(field, 2.5, rtol=1e-9)

    def test_moment_channel_sums_match_verified_wrench(self):
        geometry = ArrayGeometry(pitch_x_mm=25.0, pitch_y_mm=25.0)
        rng = np.random.default_rng(20260910)
        readings = rng.uniform(-1.0, 1.0, size=geometry.shape)
        model = TaxelArrayModel(geometry=geometry)
        model.set_force_field(readings)
        wrench = model.wrench()

        np.testing.assert_allclose(channel_map("mx", readings, geometry).sum(), wrench["Mx"], rtol=1e-12)
        np.testing.assert_allclose(channel_map("my", readings, geometry).sum(), wrench["My"], rtol=1e-12)
        np.testing.assert_allclose(channel_map("mz", readings, geometry).sum(), wrench["Mz"], rtol=1e-12)

    def test_invalid_channel_is_rejected(self):
        geometry = ArrayGeometry()
        readings = np.zeros(geometry.shape)
        with self.assertRaises(ValueError):
            channel_map("bogus", readings, geometry)

    def test_single_blob_orientation_is_preserved(self):
        geometry = ArrayGeometry()
        readings = np.zeros(geometry.shape)
        readings[0, 2, 2] = 7.0  # row 0, col 2 taxel carries fz only
        values = channel_map("fz", readings, geometry)
        field, extent = interpolate_field(values, geometry, resolution=61)

        x_centres_mm, y_centres_mm = geometry.centre_coordinates_mm()
        x_grid = np.linspace(extent[0], extent[1], 61)
        y_grid = np.linspace(extent[2], extent[3], 61)
        col = int(np.argmin(np.abs(x_grid - x_centres_mm[2])))
        row = int(np.argmin(np.abs(y_grid - y_centres_mm[0])))
        transposed_col = int(np.argmin(np.abs(x_grid - x_centres_mm[0])))
        transposed_row = int(np.argmin(np.abs(y_grid - y_centres_mm[2])))

        self.assertGreater(field[row, col], field[transposed_row, transposed_col])

    def test_extent_matches_non_square_footprint(self):
        geometry = ArrayGeometry(
            rows=2,
            cols=5,
            pitch_x_mm=30.0,
            pitch_y_mm=25.0,
            taxel_width_x_mm=20.0,
            taxel_width_y_mm=15.0,
        )
        values = np.zeros((geometry.rows, geometry.cols), dtype=np.float64)
        field, extent = interpolate_field(values, geometry, resolution=7)

        self.assertEqual(field.shape, (7, 7))
        self.assertAlmostEqual(geometry.footprint_x_mm, 140.0)
        self.assertAlmostEqual(geometry.footprint_y_mm, 40.0)
        np.testing.assert_allclose(extent, (-70.0, 70.0, -20.0, 20.0))


class ApplyLutTests(unittest.TestCase):
    def test_diverging_midpoint_is_white_nan_transparent_and_clamping(self):
        field = np.array(
            [
                [0.0, np.nan, 3.0],
                [-3.0, 1.5, 0.75],
            ]
        )
        rgba = apply_lut(field, -1.5, 1.5, *DIVERGING_LUT)

        self.assertEqual(rgba.shape, field.shape + (4,))
        self.assertEqual(rgba.dtype, np.uint8)
        midpoint = rgba[0, 0]
        self.assertTrue(midpoint[0] >= 250 and midpoint[1] >= 250 and midpoint[2] >= 250)
        self.assertEqual(rgba[0, 1, 3], 0)
        above = rgba[0, 2]
        np.testing.assert_allclose(above[:3], (214, 39, 40))
        self.assertEqual(above[3], 255)
        below = rgba[1, 0]
        np.testing.assert_allclose(below[:3], (31, 119, 180))
        self.assertEqual(below[3], 255)

    def test_invalid_range_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_lut(np.zeros((2, 2)), 1.0, 1.0, *DIVERGING_LUT)


if __name__ == "__main__":
    unittest.main()
