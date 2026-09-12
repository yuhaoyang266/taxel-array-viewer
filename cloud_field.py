"""Scalar cloud-map channels and Gaussian display interpolation for the taxel-array viewer.

This module converts per-taxel `[fx, fy, fz]` readings into per-taxel scalar
channel maps (normal force, shear magnitude, or moment contributions about the
array centre) and blurs them into a smooth cloud image for the viewer's cloud
mode. It is pure NumPy and carries no Qt imports so it stays unit-testable
headless.

Honesty caveat: the interpolation is display-only smoothing. It does not
reconstruct a physical traction field and does not model mechanical coupling
through a shared cover layer; the underlying sensing result remains a discrete
force field. NaN taxel readings are excluded from the weighted average so a
future real-data seam can mark untrusted taxels.
"""

import numpy as np


CLOUD_CHANNELS = ("fz", "shear", "mx", "my", "mz")
CHANNEL_UNITS = {"fz": "N", "shear": "N", "mx": "N·m", "my": "N·m", "mz": "N·m"}

# (stops, colours): stops are positions in the LUT's own domain; colours are RGB.
# Sequential ramp mirrors the discrete-view colour ramp for visual consistency.
SEQUENTIAL_LUT = (
    np.array([0.0, 0.45, 1.0]),
    np.array(
        [
            (25, 55, 150),
            (80, 180, 235),
            (245, 75, 55),
        ],
        dtype=np.float64,
    ),
)
DIVERGING_LUT = (
    np.array([-1.0, 0.0, 1.0]),
    np.array(
        [
            (31, 119, 180),
            (255, 255, 255),
            (214, 39, 40),
        ],
        dtype=np.float64,
    ),
)

_SIGMA_PITCH_FACTOR = 0.55


def channel_map(channel, readings, geometry):
    """Return the (rows, cols) float64 scalar map for one cloud channel.

    `fz` is the normal force, `shear` is hypot(fx, fy), and `mx`/`my`/`mz` are
    the per-taxel moment contributions about the array centre with lever arms
    in metres, matching the verified wrench aggregation law.
    """
    if channel not in CLOUD_CHANNELS:
        raise ValueError(f"channel must be one of {CLOUD_CHANNELS}, got {channel!r}")
    readings = np.asarray(readings, dtype=np.float64)
    if readings.shape != (geometry.rows, geometry.cols, 3):
        raise ValueError(
            f"readings must have shape ({geometry.rows}, {geometry.cols}, 3), got {readings.shape}"
        )
    fx = readings[:, :, 0]
    fy = readings[:, :, 1]
    fz = readings[:, :, 2]
    if channel == "fz":
        return fz.copy()
    if channel == "shear":
        return np.hypot(fx, fy)
    x_coordinates_mm, y_coordinates_mm = geometry.centre_coordinates_mm()
    x_m = (x_coordinates_mm / 1000.0)[np.newaxis, :]  # broadcasts over rows
    y_m = (y_coordinates_mm / 1000.0)[:, np.newaxis]  # broadcasts over cols
    if channel == "mx":
        return y_m * fz
    if channel == "my":
        return -x_m * fz
    return x_m * fy - y_m * fx  # mz


def interpolate_field(values, geometry, resolution=200):
    """Blur a (rows, cols) map over taxel centres into a dense display grid.

    The grid spans the full array footprint in millimetres with `resolution`
    samples per axis. Each grid point is a Gaussian-weighted average of the
    taxel values with separable sigmas `0.55 * pitch` per axis; weights are
    normalized over finite taxels only, so NaN taxels are excluded. Grid points
    with no finite contribution become NaN. Returns `(field, extent)` where
    field is (resolution, resolution) with row index = y and column index = x,
    and extent is (xmin_mm, xmax_mm, ymin_mm, ymax_mm).
    """
    values = np.asarray(values, dtype=np.float64)
    if values.shape != (geometry.rows, geometry.cols):
        raise ValueError(
            f"values must have shape ({geometry.rows}, {geometry.cols}), got {values.shape}"
        )
    resolution = int(resolution)
    if resolution <= 0:
        raise ValueError("resolution must be a positive integer")

    x_centres_mm, y_centres_mm = geometry.centre_coordinates_mm()
    x_grid = np.linspace(-geometry.footprint_x_mm / 2.0, geometry.footprint_x_mm / 2.0, resolution)
    y_grid = np.linspace(-geometry.footprint_y_mm / 2.0, geometry.footprint_y_mm / 2.0, resolution)

    weight_x = np.exp(
        -0.5
        * ((x_grid[:, np.newaxis] - x_centres_mm[np.newaxis, :]) / (_SIGMA_PITCH_FACTOR * geometry.pitch_x_mm)) ** 2
    )  # (resolution, cols)
    weight_y = np.exp(
        -0.5
        * ((y_grid[:, np.newaxis] - y_centres_mm[np.newaxis, :]) / (_SIGMA_PITCH_FACTOR * geometry.pitch_y_mm)) ** 2
    )  # (resolution, rows)
    # Separable Gaussian: the (resolution, resolution, rows, cols) weight tensor
    # factorizes into (weight_y @ ... @ weight_x.T) matrix products, so each
    # grid point's weighted average is computed without materializing the tensor.
    finite = np.isfinite(values)
    finite_mask = finite.astype(np.float64)
    safe_values = np.where(finite, values, 0.0)
    denominator = weight_y @ finite_mask @ weight_x.T
    numerator = weight_y @ safe_values @ weight_x.T
    field = np.where(denominator > 0.0, numerator / np.where(denominator > 0.0, denominator, 1.0), np.nan)

    extent = (x_grid[0], x_grid[-1], y_grid[0], y_grid[-1])
    return field, extent


def apply_lut(field, vmin, vmax, stops, colours):
    """Map scalar values through a stop/colour LUT into (res, res, 4) RGBA uint8.

    Values are linearly normalized between `vmin` and `vmax` onto the span of
    the stops, then interpolated per RGB channel. NaN maps to alpha 0 and
    out-of-range values clamp to the end-stop colours without error.
    """
    vmin = float(vmin)
    vmax = float(vmax)
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        raise ValueError(f"vmax must be finite and greater than vmin, got vmin={vmin}, vmax={vmax}")
    stops = np.asarray(stops, dtype=np.float64)
    colours = np.asarray(colours, dtype=np.float64)
    if stops.ndim != 1 or len(stops) < 2 or not np.all(np.diff(stops) > 0.0):
        raise ValueError("stops must be a 1-D array of at least 2 strictly increasing positions")
    if colours.shape != (len(stops), 3):
        raise ValueError(f"colours must have shape ({len(stops)}, 3), got {colours.shape}")

    field = np.asarray(field, dtype=np.float64)
    finite = np.isfinite(field)
    safe = np.where(finite, field, vmin)
    fraction = np.clip((safe - vmin) / (vmax - vmin), 0.0, 1.0)
    positions = stops[0] + fraction * (stops[-1] - stops[0])
    rgba = np.empty(safe.shape + (4,), dtype=np.uint8)
    for channel_index in range(3):
        rgba[..., channel_index] = np.rint(
            np.interp(positions, stops, colours[:, channel_index])
        ).astype(np.uint8)
    rgba[..., 3] = np.where(finite, 255, 0).astype(np.uint8)
    return rgba
