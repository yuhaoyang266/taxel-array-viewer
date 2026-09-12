import math

import numpy as np

from model import ArrayGeometry


def generate_uniform_clamp_readings(
    geometry,
    normal_force_n=100.0,
    tangential_force_n=40.0,
    tangential_axis="x",
):
    if not isinstance(geometry, ArrayGeometry):
        raise TypeError("geometry must be an ArrayGeometry")
    normal_force_n = float(normal_force_n)
    tangential_force_n = float(tangential_force_n)
    if not np.isfinite(normal_force_n) or normal_force_n < 0.0:
        raise ValueError("normal_force_n must be finite and non-negative")
    if not np.isfinite(tangential_force_n):
        raise ValueError("tangential_force_n must be finite")
    if tangential_axis not in {"x", "y"}:
        raise ValueError("tangential_axis must be 'x' or 'y'")

    readings = np.zeros(geometry.shape, dtype=np.float64)
    readings[:, :, 2] = normal_force_n / geometry.point_count
    tangential_channel = 0 if tangential_axis == "x" else 1
    readings[:, :, tangential_channel] = tangential_force_n / geometry.point_count
    return readings


def generate_bottom_right_readings(
    geometry,
    normal_force_n=100.0,
    tangential_force_n=40.0,
    tangential_axis="x",
):
    if not isinstance(geometry, ArrayGeometry):
        raise TypeError("geometry must be an ArrayGeometry")
    normal_force_n = float(normal_force_n)
    tangential_force_n = float(tangential_force_n)
    if not np.isfinite(normal_force_n) or normal_force_n < 0.0:
        raise ValueError("normal_force_n must be finite and non-negative")
    if not np.isfinite(tangential_force_n):
        raise ValueError("tangential_force_n must be finite")
    if tangential_axis not in {"x", "y"}:
        raise ValueError("tangential_axis must be 'x' or 'y'")

    readings = np.zeros(geometry.shape, dtype=np.float64)
    active_rows = range(0, max(1, (geometry.rows + 1) // 2))
    active_cols = range(geometry.cols // 2, geometry.cols)
    active_count = len(active_rows) * len(active_cols)
    if active_count == 0:
        return readings

    tangential_channel = 0 if tangential_axis == "x" else 1
    for row in active_rows:
        for col in active_cols:
            readings[row, col, 2] = normal_force_n / active_count
            readings[row, col, tangential_channel] = tangential_force_n / active_count
    return readings


def generate_simulated_readings(elapsed_s, peak_force_n=5.0, geometry=None):
    elapsed_s = float(elapsed_s)
    peak_force_n = float(peak_force_n)
    if not np.isfinite(elapsed_s):
        raise ValueError("elapsed_s must be finite")
    if not np.isfinite(peak_force_n) or peak_force_n <= 0.0:
        raise ValueError("peak_force_n must be finite and positive")
    geometry = ArrayGeometry() if geometry is None else geometry
    if not isinstance(geometry, ArrayGeometry):
        raise TypeError("geometry must be an ArrayGeometry")

    phase = 2.0 * math.pi * 0.18 * elapsed_s
    centre_x = 0.78 * (geometry.cols - 1) / 2.0 * math.cos(phase)
    centre_y = 0.78 * (geometry.rows - 1) / 2.0 * math.sin(phase)
    grid_x, grid_y = np.meshgrid(
        np.arange(geometry.cols, dtype=np.float64) - (geometry.cols - 1) / 2.0,
        np.arange(geometry.rows, dtype=np.float64) - (geometry.rows - 1) / 2.0,
    )
    variance = 0.58**2
    weights = np.exp(-((grid_x - centre_x) ** 2 + (grid_y - centre_y) ** 2) / (2.0 * variance))
    weights /= np.sum(weights)

    normal_total_n = peak_force_n * (0.82 + 0.18 * math.sin(0.63 * phase))
    readings = np.zeros(geometry.shape, dtype=np.float64)
    readings[:, :, 2] = normal_total_n * weights
    shear_total_n = 0.22 * normal_total_n
    readings[:, :, 0] = -math.sin(phase) * shear_total_n * weights
    readings[:, :, 1] = math.cos(phase) * shear_total_n * weights
    return readings
