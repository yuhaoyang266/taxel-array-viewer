import argparse
import math
from pathlib import Path
import time

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

from live_source import generate_simulated_readings
from model import ArrayGeometry, TaxelArrayModel


APPLICATION_ID = "tri_axis_taxel_array_live"
FORCE_COMPONENTS = ("Fx", "Fy", "Fz")
MOMENT_COMPONENTS = ("Mx", "My", "Mz")


def normal_force_colours(readings, peak_force_n):
    readings = np.asarray(readings, dtype=np.float64)
    peak_force_n = float(peak_force_n)
    if not np.isfinite(peak_force_n) or peak_force_n <= 0.0:
        raise ValueError("peak_force_n must be finite and positive")
    if readings.ndim != 3 or readings.shape[2] != 3:
        raise ValueError(f"readings must have shape [rows, cols, 3], got {readings.shape}")
    if not np.isfinite(readings).all():
        raise ValueError("readings must contain only finite values")

    normalised = np.clip(readings[:, :, 2].reshape(-1) / peak_force_n, 0.0, 1.0)
    point_count = readings.shape[0] * readings.shape[1]
    colours = np.empty((point_count, 4), dtype=np.uint8)
    colours[:, 0] = np.round(255.0 * normalised).astype(np.uint8)
    colours[:, 1] = np.round(90.0 + 80.0 * normalised).astype(np.uint8)
    colours[:, 2] = np.round(255.0 * (1.0 - normalised)).astype(np.uint8)
    colours[:, 3] = 255
    return colours


def make_blueprint():
    return rrb.Blueprint(
        rrb.Horizontal(
            rrb.Spatial3DView(origin="/field", name="Animated taxel force field"),
            rrb.Vertical(
                rrb.TimeSeriesView(origin="/wrench/force", name="Net force [N]"),
                rrb.TimeSeriesView(origin="/wrench/moment", name="Net moment [N·m]"),
            ),
            column_shares=[2.0, 1.0],
        ),
        collapse_panels=True,
    )


def log_frame(model, frame_index, hz, peak_force_n, arrow_scale_m_per_n):
    elapsed_s = frame_index / hz
    rr.set_time("frame", sequence=frame_index)
    rr.set_time("sensor_time", duration=elapsed_s)

    readings = model.readings.reshape(-1, 3)
    colours = normal_force_colours(model.readings, peak_force_n)
    point_count = model.geometry.point_count
    point_radius_m = 0.4 * min(
        model.geometry.taxel_width_x_mm,
        model.geometry.taxel_width_y_mm,
    ) / 1000.0
    rr.log(
        "/field/taxels",
        rr.Points3D(
            model.positions,
            radii=np.full(point_count, point_radius_m, dtype=np.float32),
            colors=colours,
        ),
    )
    rr.log(
        "/field/forces",
        rr.Arrows3D(
            origins=model.positions,
            vectors=readings * arrow_scale_m_per_n,
            radii=np.full(point_count, 0.00045, dtype=np.float32),
            colors=colours,
        ),
    )

    wrench = model.wrench()
    for component in FORCE_COMPONENTS:
        rr.log(f"/wrench/force/{component}", rr.Scalars(wrench[component]))
    for component in MOMENT_COMPONENTS:
        rr.log(f"/wrench/moment/{component}", rr.Scalars(wrench[component]))


def run_animation(
    hz=30.0,
    duration_s=0.0,
    geometry=None,
    peak_force_n=5.0,
    arrow_scale_m_per_n=0.004,
    save_rrd=None,
):
    hz = float(hz)
    duration_s = float(duration_s)
    arrow_scale_m_per_n = float(arrow_scale_m_per_n)
    if not np.isfinite(hz) or hz <= 0.0:
        raise ValueError("hz must be finite and positive")
    if not np.isfinite(duration_s) or duration_s < 0.0:
        raise ValueError("duration_s must be finite and non-negative")
    peak_force_n = float(peak_force_n)
    if not np.isfinite(peak_force_n) or peak_force_n <= 0.0:
        raise ValueError("peak_force_n must be finite and positive")
    if not np.isfinite(arrow_scale_m_per_n) or arrow_scale_m_per_n <= 0.0:
        raise ValueError("arrow_scale_m_per_n must be finite and positive")

    output_path = None if save_rrd is None else Path(save_rrd).resolve()
    if output_path is not None and duration_s == 0.0:
        raise ValueError("--save-rrd requires a positive duration_s")
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    geometry = ArrayGeometry() if geometry is None else geometry
    if not isinstance(geometry, ArrayGeometry):
        raise TypeError("geometry must be an ArrayGeometry")
    model = TaxelArrayModel(geometry=geometry)
    rr.init(
        APPLICATION_ID,
        spawn=output_path is None,
        default_blueprint=make_blueprint(),
    )
    if output_path is not None:
        rr.save(output_path)

    frame_period_s = 1.0 / hz
    frame_limit = None if duration_s == 0.0 else max(1, math.ceil(duration_s * hz))
    frame_index = 0
    next_frame_time = time.perf_counter()
    try:
        while frame_limit is None or frame_index < frame_limit:
            elapsed_s = frame_index / hz
            model.set_force_field(generate_simulated_readings(elapsed_s, peak_force_n, geometry))
            log_frame(model, frame_index, hz, peak_force_n, arrow_scale_m_per_n)
            frame_index += 1

            if output_path is None:
                next_frame_time += frame_period_s
                delay_s = next_frame_time - time.perf_counter()
                if delay_s > 0.0:
                    time.sleep(delay_s)
                else:
                    next_frame_time = time.perf_counter()
    except KeyboardInterrupt:
        pass
    finally:
        rr.disconnect()

    return frame_index


def parse_args():
    parser = argparse.ArgumentParser(description="Real-time Rerun animation for a 3-axis taxel array")
    parser.add_argument("--hz", type=float, default=30.0, help="Viewer update rate")
    parser.add_argument("--duration-s", type=float, default=0.0, help="Run duration; zero means until interrupted")
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--pitch-x-mm", type=float, default=20.0)
    parser.add_argument("--pitch-y-mm", type=float, default=20.0)
    parser.add_argument("--taxel-width-x-mm", type=float, default=20.0)
    parser.add_argument("--taxel-width-y-mm", type=float, default=20.0)
    parser.add_argument("--peak-force-n", type=float, default=5.0, help="Total simulated normal force")
    parser.add_argument(
        "--arrow-scale-m-per-n",
        type=float,
        default=0.004,
        help="Visual arrow length scale; physical force values remain unchanged",
    )
    parser.add_argument("--save-rrd", type=Path, help="Save a finite recording instead of opening the Viewer")
    return parser.parse_args()


def main():
    arguments = parse_args()
    geometry = ArrayGeometry(
        rows=arguments.rows,
        cols=arguments.cols,
        pitch_x_mm=arguments.pitch_x_mm,
        pitch_y_mm=arguments.pitch_y_mm,
        taxel_width_x_mm=arguments.taxel_width_x_mm,
        taxel_width_y_mm=arguments.taxel_width_y_mm,
    )
    run_animation(
        hz=arguments.hz,
        duration_s=arguments.duration_s,
        geometry=geometry,
        peak_force_n=arguments.peak_force_n,
        arrow_scale_m_per_n=arguments.arrow_scale_m_per_n,
        save_rrd=arguments.save_rrd,
    )


if __name__ == "__main__":
    main()
