import argparse

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.widgets import Slider
import numpy as np

from model import ArrayGeometry, TaxelArrayModel


FORCE_COMPONENTS = ("Fx", "Fy", "Fz")
MOMENT_COMPONENTS = ("Mx", "My", "Mz")


class TaxelArrayApp:
    def __init__(self, model=None, force_limit_n=5.0):
        self.model = TaxelArrayModel() if model is None else model
        self.force_limit_n = float(force_limit_n)
        if not np.isfinite(self.force_limit_n) or self.force_limit_n <= 0.0:
            raise ValueError("force_limit_n must be finite and positive")

        self._synchronising_sliders = False
        self.figure = plt.figure(figsize=(11.5, 7.2))
        self.figure.suptitle("3-axis taxel array → net wrench", fontsize=15)
        layout = self.figure.add_gridspec(
            2,
            2,
            left=0.07,
            right=0.96,
            top=0.89,
            bottom=0.29,
            width_ratios=(1.2, 1.0),
            hspace=0.48,
            wspace=0.38,
        )
        self.field_axis = self.figure.add_subplot(layout[:, 0])
        self.force_axis = self.figure.add_subplot(layout[0, 1])
        self.moment_axis = self.figure.add_subplot(layout[1, 1])

        self._initialise_field_plot()
        self._initialise_controls()
        self.figure.canvas.mpl_connect("button_press_event", self._on_click)
        self.redraw()

    def _initialise_field_plot(self):
        rows = self.model.geometry.rows
        cols = self.model.geometry.cols
        extent = (-0.5, cols - 0.5, -0.5, rows - 0.5)
        self.normal_image = self.field_axis.imshow(
            self.model.readings[:, :, 2],
            origin="lower",
            extent=extent,
            cmap="coolwarm",
            vmin=-self.force_limit_n,
            vmax=self.force_limit_n,
            interpolation="nearest",
        )
        colorbar = self.figure.colorbar(self.normal_image, ax=self.field_axis, fraction=0.046, pad=0.04)
        colorbar.set_label("fz [N]")

        grid_columns, grid_rows = np.meshgrid(np.arange(cols), np.arange(rows))
        self.shear_quiver = self.field_axis.quiver(
            grid_columns,
            grid_rows,
            self.model.readings[:, :, 0],
            self.model.readings[:, :, 1],
            color="black",
            angles="xy",
            scale_units="xy",
            scale=self.force_limit_n,
            pivot="middle",
            width=0.012,
        )
        selected_row, selected_col = self.model.selected
        self.selection_outline = Rectangle(
            (selected_col - 0.5, selected_row - 0.5),
            1.0,
            1.0,
            fill=False,
            edgecolor="gold",
            linewidth=3.0,
        )
        self.field_axis.add_patch(self.selection_outline)
        self.field_axis.set(
            title="Discrete force field",
            xlabel="column / +x →",
            ylabel="row / +y →",
            xticks=np.arange(cols),
            yticks=np.arange(rows),
            xlim=(-0.5, cols - 0.5),
            ylim=(-0.5, rows - 0.5),
        )
        self.field_axis.set_aspect("equal")
        self.field_axis.grid(color="white", linewidth=1.2, alpha=0.8)

    def _initialise_controls(self):
        slider_left = 0.17
        slider_width = 0.66
        slider_height = 0.03
        slider_positions = (0.18, 0.125, 0.07)
        self.sliders = {}
        for component, vertical_position in zip(("fx", "fy", "fz"), slider_positions):
            slider_axis = self.figure.add_axes((slider_left, vertical_position, slider_width, slider_height))
            slider = Slider(
                slider_axis,
                f"{component} [N]",
                -self.force_limit_n,
                self.force_limit_n,
                valinit=0.0,
                valstep=self.force_limit_n / 100.0,
            )
            slider.on_changed(self._on_slider_change)
            self.sliders[component] = slider

        self.selected_text = self.figure.text(0.17, 0.025, "", ha="left", va="bottom")

    def _on_click(self, event):
        if event.inaxes is not self.field_axis or event.xdata is None or event.ydata is None:
            return
        rows = self.model.geometry.rows
        cols = self.model.geometry.cols
        if not -0.5 <= event.xdata < cols - 0.5 or not -0.5 <= event.ydata < rows - 0.5:
            return

        selected_col = int(np.floor(event.xdata + 0.5))
        selected_row = int(np.floor(event.ydata + 0.5))
        self.select_taxel(selected_row, selected_col)

    def select_taxel(self, row, col):
        self.model.select_taxel(row, col)
        self._synchronise_sliders()
        self.redraw()

    def _synchronise_sliders(self):
        selected_force = self.model.selected_force()
        self._synchronising_sliders = True
        try:
            for component, value in zip(("fx", "fy", "fz"), selected_force):
                self.sliders[component].set_val(float(value))
        finally:
            self._synchronising_sliders = False

    def _on_slider_change(self, _value):
        if self._synchronising_sliders:
            return
        force = [self.sliders[component].val for component in ("fx", "fy", "fz")]
        self.model.set_selected_force(force)
        self.redraw()

    def redraw(self):
        readings = self.model.readings
        self.normal_image.set_data(readings[:, :, 2])
        self.shear_quiver.set_UVC(readings[:, :, 0], readings[:, :, 1])

        selected_row, selected_col = self.model.selected
        self.selection_outline.set_xy((selected_col - 0.5, selected_row - 0.5))
        selected_force = self.model.selected_force()
        self.selected_text.set_text(
            f"selected taxel: row={selected_row}, col={selected_col}   "
            f"[fx, fy, fz] = [{selected_force[0]:+.2f}, {selected_force[1]:+.2f}, {selected_force[2]:+.2f}] N"
        )

        wrench = self.model.wrench()
        force_values = [wrench[component] for component in FORCE_COMPONENTS]
        moment_values = [wrench[component] for component in MOMENT_COMPONENTS]
        self._draw_wrench_axis(
            self.force_axis,
            FORCE_COMPONENTS,
            force_values,
            "Net force [N]",
            self.force_limit_n,
            "tab:blue",
        )
        self._draw_wrench_axis(
            self.moment_axis,
            MOMENT_COMPONENTS,
            moment_values,
            "Net moment about array centre [N·m]",
            self.force_limit_n * max(
                self.model.geometry.pitch_x_m,
                self.model.geometry.pitch_y_m,
            ),
            "tab:orange",
        )
        self.figure.canvas.draw_idle()

    @staticmethod
    def _draw_wrench_axis(axis, components, values, title, minimum_scale, colour):
        axis.clear()
        bars = axis.bar(components, values, color=colour, alpha=0.85)
        maximum_absolute = max(minimum_scale, *(abs(value) for value in values))
        axis.set_ylim(-1.2 * maximum_absolute, 1.2 * maximum_absolute)
        axis.axhline(0.0, color="0.25", linewidth=0.8)
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.25)

        label_offset = 0.05 * maximum_absolute
        for bar, value in zip(bars, values):
            vertical_alignment = "bottom" if value >= 0.0 else "top"
            label_y = value + label_offset if value >= 0.0 else value - label_offset
            axis.text(
                bar.get_x() + bar.get_width() / 2.0,
                label_y,
                f"{value:+.3f}",
                ha="center",
                va=vertical_alignment,
                fontsize=9,
            )


def parse_args():
    parser = argparse.ArgumentParser(description="Interactive 3-axis taxel-array wrench visualizer")
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--pitch-x-mm", type=float, default=20.0)
    parser.add_argument("--pitch-y-mm", type=float, default=20.0)
    parser.add_argument("--taxel-width-x-mm", type=float, default=20.0)
    parser.add_argument("--taxel-width-y-mm", type=float, default=20.0)
    parser.add_argument("--force-limit-n", type=float, default=5.0, help="Signed per-axis slider limit in newtons")
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
    model = TaxelArrayModel(geometry=geometry)
    TaxelArrayApp(model=model, force_limit_n=arguments.force_limit_n)
    plt.show()


if __name__ == "__main__":
    main()
