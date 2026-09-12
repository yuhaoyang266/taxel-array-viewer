import argparse
import math
import os
import sys
import time

import numpy as np

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from cloud_field import (
    CLOUD_CHANNELS,
    CHANNEL_UNITS,
    DIVERGING_LUT,
    SEQUENTIAL_LUT,
    apply_lut,
    channel_map,
    interpolate_field,
)
from live_history import LiveHistory
from live_source import (
    generate_bottom_right_readings,
    generate_simulated_readings,
    generate_uniform_clamp_readings,
)
from model import ArrayGeometry, COMPONENTS, TaxelArrayModel


FORCE_COMPONENTS = ("Fx", "Fy", "Fz")
MOMENT_COMPONENTS = ("Mx", "My", "Mz")
FORCE_COLOURS = {
    "Fx": (239, 83, 80),
    "Fy": (102, 187, 106),
    "Fz": (66, 165, 245),
}
MOMENT_COLOURS = {
    "Mx": (38, 198, 218),
    "My": (255, 202, 40),
    "Mz": (171, 71, 188),
}
MOMENT_CHANNELS = ("mx", "my", "mz")
CLOUD_BUTTON_LABELS = {
    "fz": "Fz",
    "shear": "|shear|",
    "mx": "Mx",
    "my": "My",
    "mz": "Mz",
}
TAXEL_PEN = (40, 40, 40)
CLOUD_TAXEL_PEN = (150, 150, 150)
# Render-only cell shrink applied per axis when pitch equals taxel width, so a
# fully pitched-out array still reads as discrete cells instead of one slab.
GAP_RENDER_SCALE = 0.88


class PyQtTaxelWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        hz=30.0,
        history_seconds=10.0,
        geometry=None,
        peak_force_n=5.0,
        scenario="moving-contact",
        tangential_force_n=0.0,
        tangential_axis="x",
        taxel_shape="rectangle",
        arrow_scale_mm_per_n=None,
        view="array",
        cloud_channel="fz",
        cloud_scale="auto",
        start_timer=True,
    ):
        super().__init__()
        self.hz = float(hz)
        self.history_seconds = float(history_seconds)
        self.peak_force_n = float(peak_force_n)
        self.scenario = str(scenario)
        self.tangential_force_n = float(tangential_force_n)
        self.tangential_axis = str(tangential_axis)
        self.taxel_shape = str(taxel_shape)
        self.geometry = ArrayGeometry() if geometry is None else geometry
        if not isinstance(self.geometry, ArrayGeometry):
            raise TypeError("geometry must be an ArrayGeometry")
        if not np.isfinite(self.hz) or self.hz <= 0.0:
            raise ValueError("hz must be finite and positive")
        if not np.isfinite(self.history_seconds) or self.history_seconds <= 0.0:
            raise ValueError("history_seconds must be finite and positive")
        if not np.isfinite(self.peak_force_n) or self.peak_force_n <= 0.0:
            raise ValueError("peak_force_n must be finite and positive")
        if self.scenario not in {"moving-contact", "clamp-slider", "bottom-right-4"}:
            raise ValueError("scenario must be 'moving-contact', 'clamp-slider', or 'bottom-right-4'")
        if not np.isfinite(self.tangential_force_n):
            raise ValueError("tangential_force_n must be finite")
        if self.tangential_axis not in {"x", "y"}:
            raise ValueError("tangential_axis must be 'x' or 'y'")
        if self.taxel_shape not in {"rectangle", "circle"}:
            raise ValueError("taxel_shape must be 'rectangle' or 'circle'")
        if view not in {"array", "cloud"}:
            raise ValueError("view must be 'array' or 'cloud'")
        if cloud_channel not in CLOUD_CHANNELS:
            raise ValueError(f"cloud_channel must be one of {CLOUD_CHANNELS}")
        if cloud_scale not in {"auto", "fixed"}:
            raise ValueError("cloud_scale must be 'auto' or 'fixed'")
        self.view_mode = str(view)
        self.cloud_channel = str(cloud_channel)
        self.cloud_scale = str(cloud_scale)
        # Auto-scale state: strongest finite channel value seen recently in the
        # active cloud channel (instant attack, smooth decay, clamped later).
        self._cloud_running_max = 0.0
        self._last_cloud_time = None
        self._last_readings = None
        self.cloud_colourbar = None
        self.cloud_colourbar_ok = False
        if self.taxel_shape == "circle" and not np.isclose(
            self.geometry.taxel_width_x_mm,
            self.geometry.taxel_width_y_mm,
        ):
            raise ValueError("circle taxels require equal x/y widths")
        if self.scenario in {"clamp-slider", "bottom-right-4"}:
            active_divisor = (
                max(1, (self.geometry.rows + 1) // 2) * max(1, self.geometry.cols - self.geometry.cols // 2)
                if self.scenario == "bottom-right-4"
                else self.geometry.point_count
            )
            per_taxel_tangential = abs(self.tangential_force_n) / active_divisor
            ref_shear = per_taxel_tangential if per_taxel_tangential > 1e-6 else (self.peak_force_n / active_divisor)
            self.field_colour_max_n = self.peak_force_n / active_divisor
            self.shear_total_max_n = abs(self.tangential_force_n)
            shear_colour_max_n = per_taxel_tangential or self.field_colour_max_n
        else:
            ref_shear = self.peak_force_n * 0.25
            self.field_colour_max_n = self.peak_force_n
            self.shear_total_max_n = self.peak_force_n * 0.22
            shear_colour_max_n = self.shear_total_max_n
        if arrow_scale_mm_per_n is None:
            arrow_scale_mm_per_n = 0.38 * min(
                self.geometry.taxel_width_x_mm,
                self.geometry.taxel_width_y_mm,
            ) / max(ref_shear, 1e-9)
        self.arrow_scale_mm_per_n = float(arrow_scale_mm_per_n)
        if not np.isfinite(self.arrow_scale_mm_per_n) or self.arrow_scale_mm_per_n <= 0.0:
            raise ValueError("arrow_scale_mm_per_n must be finite and positive")
        footprint_m = max(
            self.geometry.footprint_x_mm,
            self.geometry.footprint_y_mm,
        ) / 1000.0
        normal_moment_limit = self.peak_force_n * footprint_m
        self.moment_limit = max(self.peak_force_n, self.shear_total_max_n) * footprint_m
        self.cloud_channel_limits = {
            "fz": self.field_colour_max_n,
            "shear": shear_colour_max_n,
            "mx": normal_moment_limit,
            "my": normal_moment_limit,
            "mz": self.moment_limit,
        }

        self.model = TaxelArrayModel(geometry=self.geometry)
        self.history = LiveHistory(
            max_samples=max(1, math.ceil(self.hz * self.history_seconds)),
            geometry=self.geometry,
            max_age_seconds=self.history_seconds,
        )
        self.selected = self.model.selected
        self.frame_index = 0
        self._setup_window()
        self._start_time = time.perf_counter()
        self.advance_frame()
        self.view_buttons[self.view_mode].setChecked(True)
        self.cloud_channel_buttons[self.cloud_channel].setChecked(True)
        self.set_view(self.view_mode)

        self.timer = QtCore.QTimer(self)
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.advance_frame)
        if start_timer:
            self.timer.start(max(1, round(1000.0 / self.hz)))

    def _setup_window(self):
        pg.setConfigOptions(antialias=True, imageAxisOrder="row-major")
        self.setWindowTitle("Live 3-axis taxel array")
        self.resize(1450, 850)

        central_widget = QtWidgets.QWidget(self)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        self.selected_label = QtWidgets.QLabel(central_widget)
        self.selected_label.setWordWrap(True)
        self.selected_label.setStyleSheet("font-size: 15px; padding: 4px;")
        main_layout.addWidget(self.selected_label)
        self._setup_view_buttons(main_layout)

        content_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(content_layout, stretch=1)
        self.field_plot = pg.PlotWidget()
        content_layout.addWidget(self.field_plot, stretch=3)
        right_plots = pg.GraphicsLayoutWidget()
        content_layout.addWidget(right_plots, stretch=2)
        self.setCentralWidget(central_widget)

        self._setup_field_plot()
        self.force_plot = right_plots.addPlot(row=0, col=0)
        self.moment_plot = right_plots.addPlot(row=1, col=0)
        self.taxel_plot = right_plots.addPlot(row=2, col=0)
        self.force_curves = self._setup_curve_plot(
            self.force_plot,
            "Net force across all taxels",
            FORCE_COMPONENTS,
            FORCE_COLOURS,
            "N",
        )
        self.moment_curves = self._setup_curve_plot(
            self.moment_plot,
            "Net moment about array centre",
            MOMENT_COMPONENTS,
            MOMENT_COLOURS,
            "N·m",
        )
        self.taxel_curves = self._setup_curve_plot(
            self.taxel_plot,
            "Selected taxel force",
            ("fx", "fy", "fz"),
            {"fx": FORCE_COLOURS["Fx"], "fy": FORCE_COLOURS["Fy"], "fz": FORCE_COLOURS["Fz"]},
            "N",
        )
        self.force_plot.setYRange(
            -max(0.3 * self.peak_force_n, 1.1 * self.shear_total_max_n),
            1.1 * max(self.peak_force_n, self.shear_total_max_n),
            padding=0.0,
        )
        self.moment_plot.setYRange(-self.moment_limit, self.moment_limit, padding=0.0)
        if self.scenario in {"clamp-slider", "bottom-right-4"}:
            active_divisor = (
                max(1, (self.geometry.rows + 1) // 2) * max(1, self.geometry.cols - self.geometry.cols // 2)
                if self.scenario == "bottom-right-4"
                else self.geometry.point_count
            )
            per_taxel_normal_n = self.peak_force_n / active_divisor
            per_taxel_tangential_n = abs(self.tangential_force_n) / active_divisor
            taxel_limit = 1.15 * max(per_taxel_normal_n, per_taxel_tangential_n, 1e-9)
            self.taxel_plot.setYRange(-taxel_limit, taxel_limit, padding=0.0)
        else:
            self.taxel_plot.setYRange(-0.35 * self.peak_force_n, self.peak_force_n, padding=0.0)
        self.select_taxel(*self.selected)

    def _setup_view_buttons(self, main_layout):
        self.view_buttons = {}
        self.view_button_group = QtWidgets.QButtonGroup(self)
        view_row = QtWidgets.QHBoxLayout()
        for label, view_name in (("Array view", "array"), ("Cloud view", "cloud")):
            button = QtWidgets.QPushButton(label)
            button.setCheckable(True)
            self.view_button_group.addButton(button)
            view_row.addWidget(button)
            self.view_buttons[view_name] = button
            button.clicked.connect(lambda checked=False, target=view_name: self.set_view(target))
        main_layout.addLayout(view_row)

        self.cloud_channel_buttons = {}
        self.cloud_channel_group = QtWidgets.QButtonGroup(self)
        self.cloud_channel_row = QtWidgets.QWidget()
        channel_layout = QtWidgets.QHBoxLayout(self.cloud_channel_row)
        channel_layout.setContentsMargins(0, 0, 0, 0)
        for channel in CLOUD_CHANNELS:
            button = QtWidgets.QPushButton(CLOUD_BUTTON_LABELS[channel])
            button.setCheckable(True)
            self.cloud_channel_group.addButton(button)
            channel_layout.addWidget(button)
            self.cloud_channel_buttons[channel] = button
            button.clicked.connect(
                lambda checked=False, target=channel: self.set_cloud_channel(target)
            )
        self.cloud_channel_row.setVisible(False)
        main_layout.addWidget(self.cloud_channel_row)

    def _set_field_title(self, text):
        self._field_title = str(text)
        self.field_plot.setTitle(self._field_title)

    def _setup_field_plot(self):
        self._set_field_title(
            f"{self.scenario} | colour=fz, black arrows=fx/fy"
        )
        self.field_plot.setLabel("bottom", "x", units="mm")
        self.field_plot.setLabel("left", "y", units="mm")
        self.field_plot.setAspectLocked(True)
        x_limit = self.geometry.footprint_x_mm / 2.0
        y_limit = self.geometry.footprint_y_mm / 2.0
        self.field_plot.setXRange(-x_limit, x_limit, padding=0.04)
        self.field_plot.setYRange(-y_limit, y_limit, padding=0.04)
        self.field_plot.showGrid(x=True, y=True, alpha=0.35)
        self.field_plot.hideButtons()

        self.taxel_rectangles = []
        # Render-only visual gap: when an axis has pitch == taxel width the
        # filled cells would merge into one slab, so that dimension is drawn
        # smaller and centred on the logical cell centre. Hit-testing
        # (locate_taxel) and the selection outline keep using the full cell.
        inset_x = (
            1.0 - GAP_RENDER_SCALE
            if np.isclose(self.geometry.pitch_x_mm, self.geometry.taxel_width_x_mm)
            else 0.0
        )
        inset_y = (
            1.0 - GAP_RENDER_SCALE
            if np.isclose(self.geometry.pitch_y_mm, self.geometry.taxel_width_y_mm)
            else 0.0
        )
        for row in range(self.geometry.rows):
            for col in range(self.geometry.cols):
                left, bottom, width, height = self.geometry.taxel_rect_mm(row, col)
                shrink_x = width * inset_x
                shrink_y = height * inset_y
                if self.taxel_shape == "circle":
                    if inset_x > 0.0 and inset_y > 0.0:
                        taxel_item = QtWidgets.QGraphicsEllipseItem(
                            left + shrink_x / 2.0,
                            bottom + shrink_y / 2.0,
                            width - shrink_x,
                            height - shrink_y,
                        )
                    else:
                        taxel_item = QtWidgets.QGraphicsEllipseItem(left, bottom, width, height)
                else:
                    taxel_item = QtWidgets.QGraphicsRectItem(
                        left + shrink_x / 2.0,
                        bottom + shrink_y / 2.0,
                        width - shrink_x,
                        height - shrink_y,
                    )
                taxel_item.setPen(pg.mkPen((40, 40, 40), width=1))
                taxel_item.setBrush(pg.mkBrush((25, 55, 150)))
                self.field_plot.addItem(taxel_item)
                self.taxel_rectangles.append(taxel_item)

        self.selection_outline = pg.PlotDataItem(pen=pg.mkPen((255, 215, 0), width=4))
        self.selection_outline.setZValue(20.0)
        self.field_plot.addItem(self.selection_outline)

        self.arrow_lines = []
        self.arrow_heads = []
        arrow_head_length = 0.16 * min(
            self.geometry.taxel_width_x_mm,
            self.geometry.taxel_width_y_mm,
        )
        arrow_head_width = 0.13 * min(
            self.geometry.taxel_width_x_mm,
            self.geometry.taxel_width_y_mm,
        )
        for _row in range(self.geometry.rows):
            for _col in range(self.geometry.cols):
                line = pg.PlotDataItem(pen=pg.mkPen((30, 30, 30), width=2))
                arrow = pg.ArrowItem(
                    angle=180.0,
                    headLen=arrow_head_length,
                    headWidth=arrow_head_width,
                    tailLen=None,
                    pxMode=False,
                    pen=pg.mkPen((20, 20, 20)),
                    brush=pg.mkBrush((20, 20, 20)),
                )
                line.setZValue(10.0)
                arrow.setZValue(11.0)
                self.field_plot.addItem(line)
                self.field_plot.addItem(arrow)
                self.arrow_lines.append(line)
                self.arrow_heads.append(arrow)

        self.cloud_image = pg.ImageItem(axisOrder="row-major")
        self.cloud_image.setZValue(-1.0)
        self.cloud_image.hide()
        self.field_plot.addItem(self.cloud_image)

        self.field_plot.scene().sigMouseClicked.connect(self._on_field_click)

    def _setup_curve_plot(self, plot, title, components, colours, unit):
        plot.setTitle(title)
        plot.setLabel("left", f"value [{unit}]")
        plot.setLabel("bottom", "time from latest [s]")
        plot.getAxis("left").enableAutoSIPrefix(False)
        plot.getAxis("bottom").enableAutoSIPrefix(False)
        plot.showGrid(x=True, y=True, alpha=0.25)
        plot.addLegend(offset=(8, 8))
        plot.hideButtons()
        curves = {}
        for component in components:
            curves[component] = plot.plot(
                pen=pg.mkPen(colours[component], width=2),
                name=component,
            )
        return curves

    def _on_field_click(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        if not self.field_plot.sceneBoundingRect().contains(event.scenePos()):
            return
        view_point = self.field_plot.getPlotItem().getViewBox().mapSceneToView(event.scenePos())
        taxel = self.geometry.locate_taxel(view_point.x(), view_point.y(), shape=self.taxel_shape)
        if taxel is not None:
            self.select_taxel(*taxel)

    def select_taxel(self, row, col):
        self.model.select_taxel(row, col)
        self.selected = self.model.selected
        selected_row, selected_col = self.selected
        left, bottom, width, height = self.geometry.taxel_rect_mm(selected_row, selected_col)
        if self.taxel_shape == "circle":
            x_coordinates_mm, y_coordinates_mm = self.geometry.centre_coordinates_mm()
            angles = np.linspace(0.0, 2.0 * math.pi, 65)
            radius = width / 2.0
            outline_x = x_coordinates_mm[selected_col] + radius * np.cos(angles)
            outline_y = y_coordinates_mm[selected_row] + radius * np.sin(angles)
        else:
            right = left + width
            top = bottom + height
            outline_x = [left, right, right, left, left]
            outline_y = [bottom, bottom, top, top, bottom]
        self.selection_outline.setData(outline_x, outline_y)
        self.selected_label.setText(
            f"Selected taxel: row={selected_row}, col={selected_col}   "
            f"| shape={self.taxel_shape}   "
            f"| size={self.geometry.taxel_width_x_mm:g}×{self.geometry.taxel_width_y_mm:g} mm"
        )
        self.taxel_plot.setTitle(f"Taxel row={selected_row}, col={selected_col} force")
        self._update_history_plots()

    def advance_frame(self):
        elapsed_s = time.perf_counter() - self._start_time
        if self.scenario == "clamp-slider":
            readings = generate_uniform_clamp_readings(
                self.geometry,
                normal_force_n=self.peak_force_n,
                tangential_force_n=self.tangential_force_n,
                tangential_axis=self.tangential_axis,
            )
        elif self.scenario == "bottom-right-4":
            readings = generate_bottom_right_readings(
                self.geometry,
                normal_force_n=self.peak_force_n,
                tangential_force_n=self.tangential_force_n,
                tangential_axis=self.tangential_axis,
            )
        else:
            readings = generate_simulated_readings(elapsed_s, self.peak_force_n, self.geometry)
        self.model.set_force_field(readings)
        wrench = self.model.wrench()
        self.history.append(elapsed_s, readings, wrench)
        self.frame_index += 1
        self._update_field(readings)
        self._update_history_plots()

    def _update_field(self, readings):
        self._last_readings = readings
        if self.view_mode == "cloud":
            self._render_cloud_view(readings)
        else:
            self._render_array_view(readings)

    def set_view(self, view):
        if view not in {"array", "cloud"}:
            raise ValueError("view must be 'array' or 'cloud'")
        self.view_mode = view
        self.view_buttons[view].setChecked(True)
        if view == "array":
            for item in self.taxel_rectangles:
                item.setPen(pg.mkPen(TAXEL_PEN, width=1))
            self.selection_outline.setVisible(True)
            self.cloud_channel_row.setVisible(False)
            self.cloud_image.setVisible(False)
            if self.cloud_colourbar is not None:
                self.cloud_colourbar.setVisible(False)
            self._set_field_title(f"{self.scenario} | colour=fz, black arrows=fx/fy")
            if self._last_readings is not None:
                self._render_array_view(self._last_readings)
        else:
            for item in self.taxel_rectangles:
                item.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                item.setPen(pg.mkPen(CLOUD_TAXEL_PEN, width=1))
            for item in self.arrow_lines:
                item.setVisible(False)
            for item in self.arrow_heads:
                item.setVisible(False)
            # The gold selection outline stays visible on top of the cloud
            # (zValue 20 > cloud_image's -1) so the selected taxel remains
            # identifiable and clickable in cloud mode.
            self.cloud_channel_row.setVisible(True)
            self.cloud_image.setVisible(True)
            self._sync_cloud_colourbar()
            if self._last_readings is not None:
                self._render_cloud_view(self._last_readings)
            self._update_cloud_title()

    def set_cloud_channel(self, channel):
        if channel not in CLOUD_CHANNELS:
            raise ValueError(f"cloud_channel must be one of {CLOUD_CHANNELS}")
        self.cloud_channel = channel
        # Fresh auto-scale per channel: the running max of the previous
        # channel's magnitude must not leak into the new channel's range.
        self._cloud_running_max = 0.0
        self.cloud_channel_buttons[channel].setChecked(True)
        if self.view_mode == "cloud":
            self._sync_cloud_colourbar()
            if self._last_readings is not None:
                self._render_cloud_view(self._last_readings)
            self._update_cloud_title()

    def _cloud_display_range(self):
        moment_channel = self.cloud_channel in MOMENT_CHANNELS
        ceiling = self.cloud_channel_limits[self.cloud_channel]
        if self.cloud_scale != "auto":
            return (-ceiling, ceiling) if moment_channel else (0.0, ceiling)
        bound = min(max(self._cloud_running_max, 0.05 * ceiling), ceiling)
        return (-bound, bound) if moment_channel else (0.0, bound)

    def _cloud_lut(self):
        if self.cloud_channel in MOMENT_CHANNELS:
            return DIVERGING_LUT
        return SEQUENTIAL_LUT

    def _update_cloud_title(self):
        unit = CHANNEL_UNITS[self.cloud_channel]
        if self.cloud_colourbar_ok:
            self._set_field_title(f"cloud | {self.cloud_channel} [{unit}] | display interpolation only")
        else:
            vmin, vmax = self._cloud_display_range()
            self._set_field_title(
                f"cloud | {self.cloud_channel} [{unit}] | display interpolation only "
                f"| range [{vmin:.3g}, {vmax:.3g}] {unit}"
            )

    def _cloud_pg_colour_map(self):
        stops, colours = self._cloud_lut()
        stops01 = (stops - stops[0]) / (stops[-1] - stops[0])
        return pg.ColorMap(
            pos=list(stops01),
            # integer 0-255 colours: pyqtgraph 0.14 returns an all-zero
            # LUT for float colours, which renders a black bar.
            color=colours.astype(int),
        )

    def _sync_cloud_colourbar(self):
        vmin, vmax = self._cloud_display_range()
        try:
            if self.cloud_colourbar is None:
                self.cloud_colourbar = pg.ColorBarItem(
                    values=(vmin, vmax),
                    colorMap=self._cloud_pg_colour_map(),
                    interactive=False,
                    width=12,
                )
                # Insert beside the plot at the same layout slot that pyqtgraph's
                # ColorBarItem.setImageItem(insert_in=...) uses. The bar is
                # intentionally NOT bound to cloud_image: binding would push
                # scalar levels/LUT into the pre-baked RGBA image and blank it.
                plot_item = self.field_plot.getPlotItem()
                plot_item.layout.addItem(self.cloud_colourbar, 2, 5)
                plot_item.layout.setColumnFixedWidth(4, 5)
                self.cloud_colourbar_ok = True
            elif self.cloud_colourbar_ok:
                self.cloud_colourbar.setLevels(values=(vmin, vmax))
                # gradient must follow the channel family (sequential vs diverging)
                self.cloud_colourbar.setColorMap(self._cloud_pg_colour_map())
        except Exception:
            self.cloud_colourbar_ok = False
        if self.cloud_colourbar is not None:
            self.cloud_colourbar.setVisible(self.view_mode == "cloud" and self.cloud_colourbar_ok)

    def _render_cloud_view(self, readings):
        values = channel_map(self.cloud_channel, readings, self.geometry)
        now = time.perf_counter()
        elapsed_s = 0.0 if self._last_cloud_time is None else max(0.0, now - self._last_cloud_time)
        self._last_cloud_time = now
        if self.cloud_scale == "auto":
            # Instant attack toward the strongest finite value, smooth decay
            # afterwards, with a two-second half-life even after missed ticks.
            finite_values = values[np.isfinite(values)]
            if self.cloud_channel in MOMENT_CHANNELS:
                finite_values = np.abs(finite_values)
            observed = float(finite_values.max()) if finite_values.size else 0.0
            observed = max(observed, 0.0)
            decay = 0.5 ** (elapsed_s / 2.0)
            self._cloud_running_max = max(observed, self._cloud_running_max * decay)
        field, extent = interpolate_field(values, self.geometry, resolution=200)
        vmin, vmax = self._cloud_display_range()
        stops, colours = self._cloud_lut()
        rgba = apply_lut(field, vmin, vmax, stops, colours)
        xmin, xmax, ymin, ymax = extent
        self.cloud_image.setImage(rgba, autoLevels=False)
        self.cloud_image.setRect(QtCore.QRectF(xmin, ymin, xmax - xmin, ymax - ymin))
        # The colourbar must follow the live auto-scale bound every frame.
        self._sync_cloud_colourbar()

    def _render_array_view(self, readings):
        x_coordinates_mm, y_coordinates_mm = self.geometry.centre_coordinates_mm()
        item_index = 0
        for row in range(self.geometry.rows):
            for col in range(self.geometry.cols):
                normalised = float(np.clip(readings[row, col, 2] / self.field_colour_max_n, 0.0, 1.0))
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
                self.taxel_rectangles[item_index].setBrush(pg.mkBrush(colour))
                fx, fy = readings[row, col, :2]
                centre_x = x_coordinates_mm[col]
                centre_y = y_coordinates_mm[row]
                endpoint_x = centre_x + self.arrow_scale_mm_per_n * fx
                endpoint_y = centre_y + self.arrow_scale_mm_per_n * fy
                magnitude = math.hypot(fx, fy)
                arrow_length_mm = self.arrow_scale_mm_per_n * magnitude

                self.arrow_lines[item_index].setData([centre_x, endpoint_x], [centre_y, endpoint_y])

                if magnitude > 1e-8 and arrow_length_mm > 0.1:
                    head_len = min(
                        0.30 * arrow_length_mm,
                        0.12 * min(self.geometry.taxel_width_x_mm, self.geometry.taxel_width_y_mm),
                    )
                    head_width = head_len * 0.75
                    angle_degrees = math.degrees(math.atan2(fy, fx))
                    self.arrow_heads[item_index].setPos(endpoint_x, endpoint_y)
                    self.arrow_heads[item_index].setStyle(
                        # makeArrowPath points along -x with its tip at the anchor;
                        # setStyle rotates counter-clockwise in the y-up view, so the
                        # rendered direction is 180 + angle. angle must therefore be
                        # theta - 180 for the head to follow the [fx, fy] direction.
                        angle=angle_degrees - 180.0,
                        headLen=head_len,
                        headWidth=head_width,
                    )
                    self.arrow_heads[item_index].setVisible(True)
                    self.arrow_lines[item_index].setVisible(True)
                else:
                    self.arrow_heads[item_index].setVisible(False)
                    self.arrow_lines[item_index].setVisible(False)
                item_index += 1

    def _update_history_plots(self):
        times = self.history.relative_times()
        wrench_matrix = self.history.wrench_matrix()
        selected_matrix = self.history.selected_taxel_matrix(*self.selected)
        if times.size == 0:
            return

        for component_index, component in enumerate(COMPONENTS):
            if component in self.force_curves:
                self.force_curves[component].setData(times, wrench_matrix[:, component_index])
            if component in self.moment_curves:
                self.moment_curves[component].setData(times, wrench_matrix[:, component_index])
        for channel_index, channel in enumerate(("fx", "fy", "fz")):
            self.taxel_curves[channel].setData(times, selected_matrix[:, channel_index])

        for plot in (self.force_plot, self.moment_plot, self.taxel_plot):
            plot.setXRange(-self.history_seconds, 0.0, padding=0.0)


def parse_args():
    parser = argparse.ArgumentParser(description="Click-linked PyQtGraph viewer for a 3-axis taxel array")
    parser.add_argument("--hz", type=float, default=30.0)
    parser.add_argument("--history-s", type=float, default=10.0)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--pitch-x-mm", type=float, default=20.0)
    parser.add_argument("--pitch-y-mm", type=float, default=20.0)
    parser.add_argument("--taxel-width-x-mm", type=float, default=20.0)
    parser.add_argument("--taxel-width-y-mm", type=float, default=20.0)
    parser.add_argument("--peak-force-n", type=float, default=5.0)
    parser.add_argument(
        "--scenario",
        choices=("moving-contact", "clamp-slider", "bottom-right-4"),
        default="moving-contact",
    )
    parser.add_argument("--tangential-force-n", type=float, default=0.0)
    parser.add_argument("--tangential-axis", choices=("x", "y"), default="x")
    parser.add_argument("--taxel-shape", choices=("rectangle", "circle"), default="rectangle")
    parser.add_argument("--view", choices=("array", "cloud"), default="array")
    parser.add_argument("--cloud-channel", choices=CLOUD_CHANNELS, default="fz")
    parser.add_argument(
        "--cloud-scale",
        choices=("auto", "fixed"),
        default="auto",
        help="Cloud colour range: auto-scaled to observed data (default) or fixed physical range",
    )
    parser.add_argument("--duration-s", type=float, default=0.0, help="Close automatically after this duration")
    return parser.parse_args()


def main():
    arguments = parse_args()
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    geometry = ArrayGeometry(
        rows=arguments.rows,
        cols=arguments.cols,
        pitch_x_mm=arguments.pitch_x_mm,
        pitch_y_mm=arguments.pitch_y_mm,
        taxel_width_x_mm=arguments.taxel_width_x_mm,
        taxel_width_y_mm=arguments.taxel_width_y_mm,
    )
    window = PyQtTaxelWindow(
        hz=arguments.hz,
        history_seconds=arguments.history_s,
        geometry=geometry,
        peak_force_n=arguments.peak_force_n,
        scenario=arguments.scenario,
        tangential_force_n=arguments.tangential_force_n,
        tangential_axis=arguments.tangential_axis,
        taxel_shape=arguments.taxel_shape,
        view=arguments.view,
        cloud_channel=arguments.cloud_channel,
        cloud_scale=arguments.cloud_scale,
    )
    window.show()
    if arguments.duration_s > 0.0:
        QtCore.QTimer.singleShot(round(arguments.duration_s * 1000.0), window.close)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
