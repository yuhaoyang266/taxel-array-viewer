import argparse
from collections import deque
import math
import os
import sys
import time

import numpy as np

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets


FORCE_COMPONENTS = ("fx", "fy", "fz")
FORCE_COLOURS = {
    "fx": (239, 83, 80),
    "fy": (102, 187, 106),
    "fz": (66, 165, 245),
}
SCENARIOS = ("clamp-slider", "constant", "dynamic", "sine-shear")


class SingleTaxelHistory:
    def __init__(self, max_samples, max_age_seconds=None):
        max_samples = int(max_samples)
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        if max_age_seconds is not None:
            max_age_seconds = float(max_age_seconds)
            if not np.isfinite(max_age_seconds) or max_age_seconds <= 0.0:
                raise ValueError("max_age_seconds must be finite and positive")
        self.max_samples = max_samples
        self.max_age_seconds = max_age_seconds
        self._times = deque(maxlen=max_samples)
        self._forces = deque(maxlen=max_samples)

    def __len__(self):
        return len(self._times)

    def append(self, elapsed_s, force):
        elapsed_s = float(elapsed_s)
        if not np.isfinite(elapsed_s):
            raise ValueError("elapsed_s must be finite")
        force_vec = np.asarray(force, dtype=np.float64)
        if force_vec.shape != (3,) or not np.isfinite(force_vec).all():
            raise ValueError("force must have 3 finite components")
        self._times.append(elapsed_s)
        self._forces.append(force_vec.copy())
        if self.max_age_seconds is not None:
            cutoff = elapsed_s - self.max_age_seconds
            while self._times and self._times[0] < cutoff:
                self._times.popleft()
                self._forces.popleft()

    def relative_times(self):
        if not self._times:
            return np.empty(0, dtype=np.float64)
        times = np.asarray(self._times, dtype=np.float64)
        return times - times[-1]

    def force_matrix(self):
        if not self._forces:
            return np.empty((0, 3), dtype=np.float64)
        return np.stack(self._forces)


def generate_single_taxel_reading(
    scenario,
    elapsed_s,
    peak_force_n=100.0,
    tangential_force_n=40.0,
    tangential_axis="x",
):
    scenario = str(scenario)
    elapsed_s = float(elapsed_s)
    peak_force_n = float(peak_force_n)
    tangential_force_n = float(tangential_force_n)
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")
    if not np.isfinite(elapsed_s):
        raise ValueError("elapsed_s must be finite")
    if not np.isfinite(peak_force_n) or peak_force_n < 0.0:
        raise ValueError("peak_force_n must be finite and non-negative")
    if not np.isfinite(tangential_force_n):
        raise ValueError("tangential_force_n must be finite")
    if tangential_axis not in {"x", "y"}:
        raise ValueError("tangential_axis must be 'x' or 'y'")

    if scenario in {"clamp-slider", "constant"}:
        fx = tangential_force_n if tangential_axis == "x" else 0.0
        fy = tangential_force_n if tangential_axis == "y" else 0.0
        fz = peak_force_n
    elif scenario == "sine-shear":
        phase = 2.0 * math.pi * 0.25 * elapsed_s
        fx = tangential_force_n * math.sin(phase)
        fy = tangential_force_n * math.cos(phase)
        fz = peak_force_n * (0.85 + 0.15 * math.sin(0.5 * phase))
    else:
        phase = 2.0 * math.pi * 0.2 * elapsed_s
        fz = peak_force_n * (0.8 + 0.2 * math.sin(phase))
        shear_mag = 0.25 * fz
        fx = shear_mag * math.cos(1.5 * phase)
        fy = shear_mag * math.sin(1.5 * phase)

    return np.array([fx, fy, fz], dtype=np.float64)


class SingleTaxelWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        hz=30.0,
        history_seconds=10.0,
        diameter_mm=20.0,
        taxel_shape="circle",
        peak_force_n=100.0,
        tangential_force_n=40.0,
        tangential_axis="x",
        scenario="clamp-slider",
        arrow_scale_mm_per_n=None,
        start_timer=True,
    ):
        super().__init__()
        self.hz = float(hz)
        self.history_seconds = float(history_seconds)
        self.diameter_mm = float(diameter_mm)
        self.taxel_shape = str(taxel_shape)
        self.peak_force_n = float(peak_force_n)
        self.tangential_force_n = float(tangential_force_n)
        self.tangential_axis = str(tangential_axis)
        self.scenario = str(scenario)

        if not np.isfinite(self.hz) or self.hz <= 0.0:
            raise ValueError("hz must be finite and positive")
        if not np.isfinite(self.history_seconds) or self.history_seconds <= 0.0:
            raise ValueError("history_seconds must be finite and positive")
        if not np.isfinite(self.diameter_mm) or self.diameter_mm <= 0.0:
            raise ValueError("diameter_mm must be finite and positive")
        if self.taxel_shape not in {"circle", "rectangle"}:
            raise ValueError("taxel_shape must be 'circle' or 'rectangle'")
        if not np.isfinite(self.peak_force_n) or self.peak_force_n < 0.0:
            raise ValueError("peak_force_n must be finite and non-negative")
        if not np.isfinite(self.tangential_force_n):
            raise ValueError("tangential_force_n must be finite")
        if self.tangential_axis not in {"x", "y"}:
            raise ValueError("tangential_axis must be 'x' or 'y'")
        if self.scenario not in SCENARIOS:
            raise ValueError(f"scenario must be one of {SCENARIOS}")

        ref_shear = abs(self.tangential_force_n) if abs(self.tangential_force_n) > 1e-6 else self.peak_force_n
        if arrow_scale_mm_per_n is None:
            arrow_scale_mm_per_n = 0.38 * self.diameter_mm / max(ref_shear, 1e-6)
        self.arrow_scale_mm_per_n = float(arrow_scale_mm_per_n)
        if not np.isfinite(self.arrow_scale_mm_per_n) or self.arrow_scale_mm_per_n <= 0.0:
            raise ValueError("arrow_scale_mm_per_n must be finite and positive")

        self.history = SingleTaxelHistory(
            max_samples=max(1, math.ceil(self.hz * self.history_seconds)),
            max_age_seconds=self.history_seconds,
        )
        self.frame_index = 0
        self._setup_window()
        self._start_time = time.perf_counter()
        self.advance_frame()

        self.timer = QtCore.QTimer(self)
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.advance_frame)
        if start_timer:
            self.timer.start(max(1, round(1000.0 / self.hz)))

    def _setup_window(self):
        pg.setConfigOptions(antialias=True, imageAxisOrder="row-major")
        self.setWindowTitle("Single 3-Axis Taxel Sensor Visualizer")
        self.resize(1200, 680)

        central_widget = QtWidgets.QWidget(self)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        self.info_label = QtWidgets.QLabel(central_widget)
        self.info_label.setStyleSheet("font-size: 15px; font-weight: bold; padding: 6px; color: #ECEFF1;")
        main_layout.addWidget(self.info_label)

        content_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(content_layout, stretch=1)

        self.sensor_plot = pg.PlotWidget()
        content_layout.addWidget(self.sensor_plot, stretch=5)

        self.force_plot = pg.PlotWidget()
        content_layout.addWidget(self.force_plot, stretch=6)
        self.setCentralWidget(central_widget)

        self._setup_sensor_plot()
        self._setup_force_plot()

    def _setup_sensor_plot(self):
        shape_title = f"Circle (Ø={self.diameter_mm:g}mm)" if self.taxel_shape == "circle" else f"Rect ({self.diameter_mm:g}×{self.diameter_mm:g}mm)"
        self.sensor_plot.setTitle(f"Single Taxel 2D Force Field [{shape_title}] | Colour=fz, Arrow=fx/fy")
        self.sensor_plot.setLabel("bottom", "x", units="mm")
        self.sensor_plot.setLabel("left", "y", units="mm")
        self.sensor_plot.setAspectLocked(True)

        limit = self.diameter_mm * 0.9
        self.sensor_plot.setXRange(-limit, limit, padding=0.04)
        self.sensor_plot.setYRange(-limit, limit, padding=0.04)
        self.sensor_plot.showGrid(x=True, y=True, alpha=0.35)
        self.sensor_plot.hideButtons()

        radius = self.diameter_mm / 2.0
        left = -radius
        bottom = -radius
        if self.taxel_shape == "circle":
            self.taxel_item = QtWidgets.QGraphicsEllipseItem(left, bottom, self.diameter_mm, self.diameter_mm)
        else:
            self.taxel_item = QtWidgets.QGraphicsRectItem(left, bottom, self.diameter_mm, self.diameter_mm)
        self.taxel_item.setPen(pg.mkPen((50, 50, 50), width=1.5))
        self.taxel_item.setBrush(pg.mkBrush((25, 55, 150)))
        self.sensor_plot.addItem(self.taxel_item)

        center_mark = pg.ScatterPlotItem(
            [0.0],
            [0.0],
            size=6,
            pen=pg.mkPen(None),
            brush=pg.mkBrush((100, 100, 100)),
            symbol="+",
        )
        self.sensor_plot.addItem(center_mark)

        self.arrow_line = pg.PlotDataItem(pen=pg.mkPen((20, 20, 20), width=3))
        self.arrow_line.setZValue(10.0)
        self.sensor_plot.addItem(self.arrow_line)

        arrow_head_len = 0.22 * self.diameter_mm
        arrow_head_width = 0.16 * self.diameter_mm
        self.arrow_head = pg.ArrowItem(
            angle=180.0,
            headLen=arrow_head_len,
            headWidth=arrow_head_width,
            tailLen=None,
            pxMode=False,
            pen=pg.mkPen((20, 20, 20)),
            brush=pg.mkBrush((20, 20, 20)),
        )
        self.arrow_head.setZValue(11.0)
        self.sensor_plot.addItem(self.arrow_head)

        if self.taxel_shape == "circle":
            angles = np.linspace(0.0, 2.0 * math.pi, 65)
            outline_x = radius * np.cos(angles)
            outline_y = radius * np.sin(angles)
        else:
            outline_x = [left, radius, radius, left, left]
            outline_y = [bottom, bottom, radius, radius, bottom]
        self.selection_outline = pg.PlotDataItem(
            outline_x,
            outline_y,
            pen=pg.mkPen((255, 215, 0), width=3),
        )
        self.selection_outline.setZValue(20.0)
        self.sensor_plot.addItem(self.selection_outline)

    def _setup_force_plot(self):
        self.force_plot.setTitle("3-Axis Force Components History [N]")
        self.force_plot.setLabel("left", "Force [N]")
        self.force_plot.setLabel("bottom", "Time from latest [s]")
        self.force_plot.getAxis("left").enableAutoSIPrefix(False)
        self.force_plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.force_plot.showGrid(x=True, y=True, alpha=0.3)
        self.force_plot.addLegend(offset=(10, 10))
        self.force_plot.hideButtons()

        self.force_curves = {}
        for comp in FORCE_COMPONENTS:
            self.force_curves[comp] = self.force_plot.plot(
                pen=pg.mkPen(FORCE_COLOURS[comp], width=2.5),
                name=comp,
            )

        max_limit = 1.15 * max(self.peak_force_n, abs(self.tangential_force_n), 1.0)
        min_limit = -1.15 * max(abs(self.tangential_force_n), 0.2 * self.peak_force_n, 1.0)
        self.force_plot.setYRange(min_limit, max_limit, padding=0.0)

    def advance_frame(self):
        elapsed_s = time.perf_counter() - self._start_time
        force = generate_single_taxel_reading(
            self.scenario,
            elapsed_s,
            peak_force_n=self.peak_force_n,
            tangential_force_n=self.tangential_force_n,
            tangential_axis=self.tangential_axis,
        )
        self.history.append(elapsed_s, force)
        self.frame_index += 1
        self._update_sensor(force)
        self._update_force_plot()

    def _update_sensor(self, force):
        force = np.asarray(force, dtype=np.float64)
        if force.shape != (3,) or not np.isfinite(force).all():
            raise ValueError("force must have 3 finite components")
        fx, fy, fz = force
        ref_fz = max(self.peak_force_n, 1e-6)
        normalised = float(np.clip(fz / ref_fz, 0.0, 1.0))
        if normalised <= 0.45:
            fraction = normalised / 0.45
            colour = (
                round(25 + fraction * 55),
                round(55 + fraction * 125),
                round(150 + fraction * 85),
            )
        else:
            fraction = (normalised - 0.45) / 0.55
            colour = (
                round(80 + fraction * 165),
                round(180 - fraction * 105),
                round(235 - fraction * 180),
            )
        self.taxel_item.setBrush(pg.mkBrush(colour))

        endpoint_x = self.arrow_scale_mm_per_n * fx
        endpoint_y = self.arrow_scale_mm_per_n * fy
        magnitude = math.hypot(fx, fy)
        arrow_length_mm = self.arrow_scale_mm_per_n * magnitude

        self.arrow_line.setData([0.0, endpoint_x], [0.0, endpoint_y])

        if magnitude > 1e-6 and arrow_length_mm > 0.1:
            head_len = min(0.30 * arrow_length_mm, 0.12 * self.diameter_mm)
            head_width = head_len * 0.75
            angle_degrees = math.degrees(math.atan2(fy, fx))
            self.arrow_head.setPos(endpoint_x, endpoint_y)
            self.arrow_head.setStyle(
                angle=angle_degrees - 180.0,
                headLen=head_len,
                headWidth=head_width,
            )
            self.arrow_head.setVisible(True)
            self.arrow_line.setVisible(True)
        else:
            self.arrow_head.setVisible(False)
            self.arrow_line.setVisible(False)

        total_norm = math.sqrt(fx**2 + fy**2 + fz**2)
        shape_size = (
            f"Ø={self.diameter_mm:g}mm"
            if self.taxel_shape == "circle"
            else f"{self.diameter_mm:g}×{self.diameter_mm:g}mm"
        )
        self.info_label.setText(
            f"Single 3-Axis Taxel Sensor | "
            f"fx = {fx:+.2f} N,  fy = {fy:+.2f} N,  fz = {fz:.2f} N  "
            f"(Shear: {magnitude:.2f} N,  Total ||f||: {total_norm:.2f} N)  |  "
            f"Shape: {self.taxel_shape} ({shape_size})"
        )

    def _update_force_plot(self):
        times = self.history.relative_times()
        matrix = self.history.force_matrix()
        if times.size == 0:
            return

        for idx, comp in enumerate(FORCE_COMPONENTS):
            self.force_curves[comp].setData(times, matrix[:, idx])

        self.force_plot.setXRange(-self.history_seconds, 0.0, padding=0.0)


def parse_args():
    parser = argparse.ArgumentParser(description="Single 3-axis taxel sensor visualizer")
    parser.add_argument("--hz", type=float, default=30.0, help="Refresh frequency in Hz")
    parser.add_argument("--history-s", type=float, default=10.0, help="Rolling history window in seconds")
    parser.add_argument("--diameter-mm", type=float, default=20.0, help="Sensor diameter/width in mm")
    parser.add_argument("--taxel-shape", choices=("circle", "rectangle"), default="circle")
    parser.add_argument("--peak-force-n", type=float, default=100.0, help="Normal force Fz in N")
    parser.add_argument("--tangential-force-n", type=float, default=40.0, help="Tangential force Fx/Fy in N")
    parser.add_argument("--tangential-axis", choices=("x", "y"), default="x", help="Tangential shear axis")
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="clamp-slider",
        help="Simulation scenario",
    )
    parser.add_argument("--duration-s", type=float, default=0.0, help="Close automatically after this duration")
    return parser.parse_args()


def main():
    arguments = parse_args()
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = SingleTaxelWindow(
        hz=arguments.hz,
        history_seconds=arguments.history_s,
        diameter_mm=arguments.diameter_mm,
        taxel_shape=arguments.taxel_shape,
        peak_force_n=arguments.peak_force_n,
        tangential_force_n=arguments.tangential_force_n,
        tangential_axis=arguments.tangential_axis,
        scenario=arguments.scenario,
    )
    window.show()
    if arguments.duration_s > 0.0:
        QtCore.QTimer.singleShot(round(arguments.duration_s * 1000.0), window.close)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
