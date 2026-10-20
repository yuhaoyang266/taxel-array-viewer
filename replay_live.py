"""Replay recorded tactile arrays (ShearCue simulation records) in the viewer.

This is the read-only counterpart of the live UDP adapter: no simulator, no
synthetic source, no socket. It loads a recorded .npz through recorded_source
and drives the existing PyQt window frame by frame, keeping the measured
Newton values intact in the model and history.

Usage:
    conda run -n taxel-pyqt python replay_live.py --npz record.npz
    conda run -n taxel-pyqt python replay_live.py --npz record.npz --config shear_viewer.json
"""

import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

from PySide6 import QtCore, QtWidgets

from model import ArrayGeometry
from pyqt_live import PyQtTaxelWindow
from recorded_source import load_recording


GEOMETRY_KEYS = (
    "pitch_x_mm",
    "pitch_y_mm",
    "taxel_width_x_mm",
    "taxel_width_y_mm",
)


def load_sensor_config(path):
    """Read ShearCue's viewer config JSON: {"sensors": {name: {...}}}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sensors = data.get("sensors", {})
    if not isinstance(sensors, dict):
        raise ValueError("config sensors must be an object")
    return {str(name): dict(values) for name, values in sensors.items()}


def resolve_times(recording, hz):
    """Return replay timestamps in seconds plus a label for the time source."""
    if recording.time_kind == "index":
        return np.arange(recording.frame_count, dtype=np.float64) / float(hz), f"index/{hz:g} Hz"
    if recording.time_kind == "snapshot":
        return np.zeros(1, dtype=np.float64), "snapshot"
    return np.asarray(recording.times, dtype=np.float64), recording.time_kind


def geometry_for(name, sensor, config, defaults):
    """Build ArrayGeometry from the file shape and optional saved config."""
    values = dict(defaults)
    configured = config.get(name, {})
    configured_rows = configured.get("rows")
    configured_cols = configured.get("cols")
    if configured_rows is not None and int(configured_rows) != sensor.rows:
        raise ValueError(
            f"{name}: config rows={configured_rows} but recording has {sensor.rows}"
        )
    if configured_cols is not None and int(configured_cols) != sensor.cols:
        raise ValueError(
            f"{name}: config cols={configured_cols} but recording has {sensor.cols}"
        )
    for key in GEOMETRY_KEYS:
        if key in configured:
            values[key] = float(configured[key])
    values["rows"] = sensor.rows
    values["cols"] = sensor.cols
    geometry = ArrayGeometry(**values)
    if configured:
        note = "几何: config"
    else:
        note = f"几何: 默认标称 {geometry.pitch_x_mm:g}x{geometry.pitch_y_mm:g} mm（录制无几何）"
    return geometry, note


class ReplayTaxelWindow(PyQtTaxelWindow):
    """Measured frames only: the synthetic timer source is never started."""

    def __init__(self, sensor, times, geometry, *, loop=True, channels=(), geometry_note="", time_note=""):
        self.sensor_name = sensor.name
        self._replay_frames = sensor.frames
        self._replay_times = np.asarray(times, dtype=np.float64)
        self._replay_loop = bool(loop)
        self._replay_index = -1
        self._replay_finished = False
        self.channels = tuple(channels)
        self.geometry_note = str(geometry_note)
        self.time_note = str(time_note)
        super().__init__(geometry=geometry, start_timer=False)
        self.setWindowTitle(f"Replay {self.sensor_name} | recorded simulation data")

    def _array_title(self):
        # The base title carries the synthetic scenario name; a replay must not
        # claim a simulated contact scenario it is not running.
        return f"replay | {self.sensor_name} | colour=fz, arrows=fx/fy"

    @property
    def finished(self):
        return self._replay_finished

    def advance_frame(self):
        frames = getattr(self, "_replay_frames", None)
        if frames is None:
            # Base constructor calls this once before replay state exists.
            return
        index = self._replay_index + 1
        if index >= frames.shape[0]:
            if not self._replay_loop:
                self._replay_finished = True
                self._update_replay_status()
                return
            index = 0
        self._replay_index = index
        readings = frames[index]
        self.model.set_force_field(readings)
        self.history.append(float(self._replay_times[index]), readings, self.model.wrench())
        self.frame_index += 1
        self._update_field(readings)
        self._update_history_plots()
        self._update_replay_status()

    def _update_replay_status(self):
        total = int(self._replay_frames.shape[0])
        if self._replay_index < 0:
            self.statusBar().showMessage("recorded simulation data | waiting")
            return
        state = "end" if self._replay_finished else f"{self._replay_index + 1}/{total}"
        channels = ",".join(self.channels) if self.channels else "3 channels"
        self.statusBar().showMessage(
            f"{self.sensor_name} | {state} | t={self._replay_times[self._replay_index]:.3f}s"
            f" | {channels} (N) | 时间: {self.time_note} | {self.geometry_note}"
        )


def build_windows(recording, geometries, *, loop=True, times=None, time_note="", sensors=None):
    """Build one ReplayTaxelWindow per requested sensor."""
    names = list(sensors) if sensors else list(recording.sensor_names())
    windows = {}
    for name in names:
        if name not in recording.sensors:
            raise ValueError(f"unknown sensor {name!r}; have {recording.sensor_names()}")
        geometry, geometry_note = geometries[name]
        windows[name] = ReplayTaxelWindow(
            recording.sensors[name],
            times if times is not None else recording.times,
            geometry,
            loop=loop,
            channels=recording.channels,
            geometry_note=geometry_note,
            time_note=time_note or recording.time_kind,
        )
    return windows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Replay a recorded tactile array (.npz) in the viewer")
    parser.add_argument("--npz", type=Path, required=True, help="Recorded tactile arrays (.npz)")
    parser.add_argument("--sensor", action="append", help="Sensor name to show; default all")
    parser.add_argument("--config", type=Path, help="ShearCue viewer config JSON with per-sensor geometry")
    parser.add_argument("--hz", type=float, default=30.0, help="Playback rate (frames per second)")
    parser.add_argument("--no-loop", action="store_true", help="Stop at the last frame instead of looping")
    parser.add_argument("--pitch-x-mm", type=float, default=10.0)
    parser.add_argument("--pitch-y-mm", type=float, default=10.0)
    parser.add_argument("--taxel-width-x-mm", type=float, default=None)
    parser.add_argument("--taxel-width-y-mm", type=float, default=None)
    parser.add_argument("--duration-s", type=float, default=0.0, help="Close automatically after this duration")
    parser.add_argument("--screenshot", type=Path, help="Save a PNG of the window after 0.75 s")
    return parser.parse_args(argv)


def main(argv=None):
    arguments = parse_args(argv)
    if not np.isfinite(arguments.hz) or arguments.hz <= 0.0:
        raise SystemExit("--hz must be finite and positive")
    recording = load_recording(arguments.npz)
    config = load_sensor_config(arguments.config) if arguments.config else {}
    times, time_note = resolve_times(recording, arguments.hz)

    defaults = dict(
        pitch_x_mm=arguments.pitch_x_mm,
        pitch_y_mm=arguments.pitch_y_mm,
        taxel_width_x_mm=(
            arguments.pitch_x_mm if arguments.taxel_width_x_mm is None else arguments.taxel_width_x_mm
        ),
        taxel_width_y_mm=(
            arguments.pitch_y_mm if arguments.taxel_width_y_mm is None else arguments.taxel_width_y_mm
        ),
    )
    names = arguments.sensor or list(recording.sensor_names())
    geometries = {
        name: geometry_for(name, recording.sensors[name], config, defaults)
        for name in names
        if name in recording.sensors
    }
    unknown = [name for name in names if name not in recording.sensors]
    if unknown:
        raise SystemExit(f"unknown sensor(s) {unknown}; recording has {recording.sensor_names()}")

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    windows = build_windows(
        recording,
        geometries,
        loop=not arguments.no_loop,
        times=times,
        time_note=time_note,
        sensors=names,
    )

    if len(windows) == 1:
        container = next(iter(windows.values()))
        container.resize(1450, 850)
    else:
        container = QtWidgets.QWidget()
        container.setWindowTitle("Recorded tactile arrays | " + ", ".join(windows))
        layout = QtWidgets.QHBoxLayout(container)
        for name, window in windows.items():
            window.setWindowFlags(QtCore.Qt.WindowType.Widget)
            layout.addWidget(window)
        container.resize(1800, 850)
    container.show()

    timer = QtCore.QTimer()
    timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)

    def step():
        for window in windows.values():
            if not window.finished:
                window.advance_frame()
        if all(window.finished for window in windows.values()):
            timer.stop()

    timer.timeout.connect(step)
    timer.start(max(1, round(1000.0 / arguments.hz)))
    step()

    if arguments.duration_s > 0.0:
        QtCore.QTimer.singleShot(round(arguments.duration_s * 1000.0), container.close)
    if arguments.screenshot is not None:
        def screenshot():
            arguments.screenshot.parent.mkdir(parents=True, exist_ok=True)
            container.grab().save(str(arguments.screenshot))
        QtCore.QTimer.singleShot(750, screenshot)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
