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

import ui_theme
from sensor_structure_items import (
    SCHEMATIC_NOTE,
    SECTION_CAPTION,
    TOP_VIEW_CAPTION,
    CrossSectionItem,
    StructureLegendWidget,
    StructureMetrics,
    StructureView,
    TopViewStructureItem,
)


FORCE_COMPONENTS = ("fx", "fy", "fz")
# Lower-case keys keep the existing curve and taxel lookups unchanged; the
# values come from the shared theme tokens.
FORCE_COLOURS = {name.lower(): colour for name, colour in ui_theme.AXIS_COLOURS.items()}
SCENARIOS = ("clamp-slider", "constant", "dynamic", "sine-shear")
# The structure detail panel would squeeze the force field on narrow screens,
# so it only opens above this width and folds itself back below it.
STRUCTURE_MIN_WINDOW_WIDTH = 900


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
        diameter_mm=10.0,
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
        self.setWindowTitle(f"Single 3-Axis Taxel Sensor Visualizer · synthetic data ({self.scenario})")
        self.resize(1200, 680)
        ui_theme.apply_window_theme(self)

        central_widget = QtWidgets.QWidget(self)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        info_row = QtWidgets.QHBoxLayout()
        self.info_label = QtWidgets.QLabel(central_widget)
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(
            ui_theme.label_qss() + " font-weight: bold; padding: 6px;"
        )
        self.info_label.setFont(ui_theme.mono_font(bold=True))
        info_row.addWidget(self.info_label, stretch=1)

        self.structure_toggle = QtWidgets.QToolButton(central_widget)
        self.structure_toggle.setText("结构详情")
        self.structure_toggle.setCheckable(True)
        self.structure_toggle.setChecked(False)
        self.structure_toggle.setStyleSheet(ui_theme.toggle_qss())
        self.structure_toggle.toggled.connect(self.set_structure_details_visible)
        info_row.addWidget(self.structure_toggle)
        main_layout.addLayout(info_row)

        content_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(content_layout, stretch=1)

        left_column = QtWidgets.QVBoxLayout()
        content_layout.addLayout(left_column, stretch=5)

        self.sensor_plot = pg.PlotWidget()
        ui_theme.apply_canvas_theme(self.sensor_plot, "canvas")
        # The plot can be resized without the window resizing (for example when
        # the structure panel opens), so re-fit on its viewport resize too.
        self.sensor_plot.viewport().installEventFilter(self)
        left_column.addWidget(self.sensor_plot, stretch=1)

        # Plot titles must stay short (pyqtgraph sizes the plot from the title),
        # so the force-field encoding lives in a wrappable caption instead.
        self.field_legend_label = QtWidgets.QLabel(
            "力场编码：颜色 = 法向力 fz（N）；箭头 = 切向力 (fx, fy)（N）",
            central_widget,
        )
        self.field_legend_label.setWordWrap(True)
        self.field_legend_label.setStyleSheet(ui_theme.legend_qss())
        left_column.addWidget(self.field_legend_label)

        self.structure_panel = self._build_structure_panel(central_widget)
        self._structure_requested = False
        self.structure_panel.setVisible(False)
        left_column.addWidget(self.structure_panel, stretch=0)

        self.force_plot = pg.PlotWidget()
        ui_theme.apply_canvas_theme(self.force_plot, "panel")
        content_layout.addWidget(self.force_plot, stretch=6)
        self.setCentralWidget(central_widget)

        self._setup_sensor_plot()
        self._setup_force_plot()

    def _build_structure_panel(self, parent):
        panel = QtWidgets.QWidget(parent)
        panel.setObjectName("StructurePanel")
        ui_theme.apply_panel_theme(panel)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)

        metrics = StructureMetrics.from_diameter(self.diameter_mm)
        self.structure_top_view = StructureView(TopViewStructureItem(metrics), panel)
        self.structure_section_view = StructureView(CrossSectionItem(metrics), panel)

        views_row = QtWidgets.QHBoxLayout()
        for caption, view in (
            (TOP_VIEW_CAPTION, self.structure_top_view),
            (SECTION_CAPTION, self.structure_section_view),
        ):
            column = QtWidgets.QVBoxLayout()
            caption_label = QtWidgets.QLabel(caption, panel)
            caption_label.setWordWrap(True)
            caption_label.setStyleSheet(ui_theme.legend_qss())
            column.addWidget(caption_label)
            view.setMinimumHeight(210)
            view.setMinimumWidth(140)
            column.addWidget(view, stretch=1)
            views_row.addLayout(column, stretch=1)
        layout.addLayout(views_row)

        self.structure_legend = StructureLegendWidget(panel)
        layout.addWidget(self.structure_legend)

        self.structure_caption = QtWidgets.QLabel(SCHEMATIC_NOTE, panel)
        self.structure_caption.setWordWrap(True)
        self.structure_caption.setStyleSheet(ui_theme.legend_qss())
        layout.addWidget(self.structure_caption)

        panel.setMinimumWidth(0)
        panel.setMaximumHeight(400)
        return panel

    def set_structure_details_visible(self, visible):
        self._structure_requested = bool(visible)
        if self.structure_toggle.isChecked() != self._structure_requested:
            self.structure_toggle.blockSignals(True)
            self.structure_toggle.setChecked(self._structure_requested)
            self.structure_toggle.blockSignals(False)
        self._apply_structure_visibility()

    def _structure_fits(self):
        return self.width() >= STRUCTURE_MIN_WINDOW_WIDTH

    def _apply_structure_visibility(self):
        show = self._structure_requested and self._structure_fits()
        self.structure_panel.setVisible(show)
        if self._structure_requested and not show:
            self.structure_toggle.setToolTip("窗口宽度不足 900 px，结构详情已折叠")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "structure_panel", None) is not None:
            self._apply_structure_visibility()
        if getattr(self, "sensor_plot", None) is not None:
            self._fit_sensor_view()

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "sensor_plot", None) is not None:
            self._fit_sensor_view()

    def eventFilter(self, watched, event):
        sensor_plot = getattr(self, "sensor_plot", None)
        if (
            sensor_plot is not None
            and watched is sensor_plot.viewport()
            and event.type() == QtCore.QEvent.Type.Resize
        ):
            self._fit_sensor_view()
        return super().eventFilter(watched, event)

    def _setup_sensor_plot(self):
        shape_title = f"Circle (Ø={self.diameter_mm:g}mm)" if self.taxel_shape == "circle" else f"Rect ({self.diameter_mm:g}×{self.diameter_mm:g}mm)"
        # Plot titles stay short on purpose: pyqtgraph sizes the PlotItem from
        # its title, so a long title widens the whole view past the viewport
        # and clips the diagram. Source/scenario text lives in the info label
        # and the window title instead.
        self.sensor_plot.setTitle("Single Taxel 2D Force Field")
        self.sensor_plot.setLabel("bottom", "x", units="mm")
        self.sensor_plot.setLabel("left", "y", units="mm")

        # Ranges are computed from the widget aspect instead of relying on
        # setAspectLocked: in pyqtgraph 0.14 an aspect-locked ViewBox inside a
        # portrait widget grows its own geometry past the viewport and clips the
        # taxel. Explicit ranges keep cells square at every widget size.
        self._fit_sensor_view()
        self.sensor_plot.showGrid(x=True, y=True, alpha=0.35)
        self.sensor_plot.hideButtons()

        radius = self.diameter_mm / 2.0
        left = -radius
        bottom = -radius
        if self.taxel_shape == "circle":
            self.taxel_item = QtWidgets.QGraphicsEllipseItem(left, bottom, self.diameter_mm, self.diameter_mm)
        else:
            self.taxel_item = QtWidgets.QGraphicsRectItem(left, bottom, self.diameter_mm, self.diameter_mm)
        self.taxel_item.setPen(pg.mkPen(ui_theme.TAXEL_PEN, width=1.5))
        self.taxel_item.setBrush(pg.mkBrush(ui_theme.field_ramp_colour(0.0)))
        self.sensor_plot.addItem(self.taxel_item)

        center_mark = pg.ScatterPlotItem(
            [0.0],
            [0.0],
            size=6,
            pen=pg.mkPen(None),
            brush=pg.mkBrush(ui_theme.TEXT_MUTED),
            symbol="+",
        )
        self.sensor_plot.addItem(center_mark)

        self.arrow_line = pg.PlotDataItem(pen=pg.mkPen(ui_theme.ARROW_LINE_COLOUR, width=3))
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
            pen=pg.mkPen(ui_theme.ARROW_COLOUR),
            brush=pg.mkBrush(ui_theme.ARROW_COLOUR),
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
            pen=pg.mkPen(ui_theme.SELECTION_COLOUR, width=3),
        )
        self.selection_outline.setZValue(20.0)
        self.sensor_plot.addItem(self.selection_outline)

    def _fit_sensor_view(self):
        """Keep the taxel square and fully visible inside the current widget.

        The fit is recomputed only when the viewport size actually changes, so
        it settles after layout without fighting a user's manual zoom.
        """
        view_box = self.sensor_plot.getPlotItem().vb
        size = (max(1, int(view_box.width())), max(1, int(view_box.height())))
        fitted = getattr(self, "_fitted_viewport_size", None)
        if size == fitted:
            return
        self._fitted_viewport_size = size
        # Never crop the taxel: both half-ranges stay at least "limit" while
        # keeping square units, so a tall/narrow window grows the Y range
        # instead of shrinking X below the taxel diameter.
        limit = self.diameter_mm * 0.9
        aspect = size[0] / size[1]
        y_limit = max(limit, limit / aspect)
        x_limit = y_limit * aspect
        self.sensor_plot.getPlotItem().setRange(
            xRange=(-x_limit, x_limit),
            yRange=(-y_limit, y_limit),
            padding=0.04,
        )

    def _setup_force_plot(self):
        self.force_plot.setTitle("3-Axis Force Components History [N]")
        self.force_plot.setLabel("left", "Force [N]")
        self.force_plot.setLabel("bottom", "Time from latest [s]")
        self.force_plot.getAxis("left").enableAutoSIPrefix(False)
        self.force_plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.force_plot.showGrid(x=True, y=True, alpha=0.3)
        # Horizontal reference at y = 0 (the bottom axis is time).
        zero_line = pg.InfiniteLine(
            angle=0,
            pos=0.0,
            movable=False,
            pen=pg.mkPen(
                ui_theme.ZERO_LINE_COLOUR,
                width=1,
                style=QtCore.Qt.PenStyle.DashLine,
            ),
        )
        zero_line.setZValue(-10.0)
        self.force_plot.addItem(zero_line, ignoreBounds=True)
        self.force_plot.addLegend(
            offset=(10, 10),
            labelTextColor=ui_theme.TEXT_MUTED,
            labelTextSize="9pt",
        )
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
        if getattr(self, "sensor_plot", None) is not None:
            self._fit_sensor_view()
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
        self.taxel_item.setBrush(pg.mkBrush(ui_theme.field_ramp_colour(normalised)))

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
            f"Shape: {self.taxel_shape} ({shape_size})  |  "
            f"synthetic data · {self.scenario}"
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
    parser.add_argument("--diameter-mm", type=float, default=10.0, help="Sensor diameter/width in mm")
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
