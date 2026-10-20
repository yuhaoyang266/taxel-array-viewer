"""Read recorded tactile arrays (ShearCue simulation records) without Qt.

Three on-disk schemas are supported; every one is converted to the viewer's
per-sensor frame layout (T, rows, cols, 3) where rows follow the sensor's v
axis and columns follow u, matching ShearCue's live adapter convention.

tactile-timeseries
    "tactile" (T, S, 3, U, V) plus a time key. ShearCue simulation records use
    this shape for its two virtual rasters (12 u by 32 v), with u as the first
    spatial index exactly like its live adapter.

tactile-trajectory
    "times" (T,) plus "readings" (T, R, C, 3), the legacy bridge export format.

tactile-snapshot
    "tactile_fixed"/"tactile_moving" (3, V, U) or a single "tactile" (3, V, U);
    a one-frame recording without timestamps.

Channels are kept in file order (normally Fu, Fv, Fn = tangential x, tangential
y, normal). Fn in ShearCue records is positive compression, not an outward
signed z force; the viewer must not silently flip it.
"""

from dataclasses import dataclass
import os

import numpy as np


DEFAULT_SENSOR_NAMES = ("tactile_fixed", "tactile_moving")
DEFAULT_CHANNELS = ("Fu", "Fv", "Fn")
TRAJECTORY_CHANNELS = ("fx", "fy", "fz")
TIME_KEYS = ("times", "logical_times", "actual_times")


@dataclass(frozen=True)
class SensorRecording:
    """One sensor's frames: (T, rows, cols, 3), rows = v, cols = u."""

    name: str
    frames: np.ndarray

    @property
    def rows(self):
        return int(self.frames.shape[1])

    @property
    def cols(self):
        return int(self.frames.shape[2])

    @property
    def frame_count(self):
        return int(self.frames.shape[0])


@dataclass(frozen=True)
class Recording:
    """A loaded recording: ordered sensors plus shared time/channel metadata."""

    sensors: dict
    times: np.ndarray
    time_kind: str
    channels: tuple
    units: str
    schema: str
    source: str

    @property
    def frame_count(self):
        return int(self.times.shape[0])

    def sensor_names(self):
        return tuple(self.sensors)


def _finite_frames(frames, *, what):
    frames = np.asarray(frames, dtype=np.float64)
    if frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError(f"{what} must have shape (T, rows, cols, 3), got {frames.shape}")
    if frames.shape[0] < 1 or frames.shape[1] < 1 or frames.shape[2] < 1:
        raise ValueError(f"{what} must not be empty, got {frames.shape}")
    if not np.isfinite(frames).all():
        raise ValueError(f"{what} must contain only finite force values")
    return np.ascontiguousarray(frames)


def _times_from(data, frame_count, *, source):
    for key in TIME_KEYS:
        if key in data.files:
            times = np.asarray(data[key], dtype=np.float64).reshape(-1)
            if times.shape[0] != frame_count:
                raise ValueError(
                    f"{source}: {key} has {times.shape[0]} entries for {frame_count} frames"
                )
            if not np.isfinite(times).all():
                raise ValueError(f"{source}: {key} must be finite")
            return times, key
    return np.arange(frame_count, dtype=np.float64), "index"


def _sensor_names_from(data, count):
    if "sensors" in data.files:
        names = [str(name) for name in np.asarray(data["sensors"]).reshape(-1)]
        if len(names) == count and len(set(names)) == count:
            return tuple(names)
    if count == len(DEFAULT_SENSOR_NAMES):
        return DEFAULT_SENSOR_NAMES
    return tuple(f"sensor{index}" for index in range(count))


def _recording_from_tactile(data, source):
    tactile = np.asarray(data["tactile"], dtype=np.float64)
    if tactile.ndim == 5:
        frame_count, sensor_count, channels, u_size, v_size = tactile.shape
        if channels != 3:
            raise ValueError(f"{source}: tactile must carry 3 channels, got {channels}")
        frames = tactile.transpose(0, 1, 4, 3, 2)  # (T, S, V, U, 3)
        names = _sensor_names_from(data, sensor_count)
        sensors = {
            name: SensorRecording(name, _finite_frames(frames[:, index], what=f"{source}:{name}"))
            for index, name in enumerate(names)
        }
    elif tactile.ndim == 4:
        if tactile.shape[1] != 3:
            raise ValueError(f"{source}: tactile must carry 3 channels in axis 1")
        frames = tactile.transpose(0, 3, 2, 1)  # (T, C, U, V) -> (T, V, U, C)
        sensors = {"taxel": SensorRecording("taxel", _finite_frames(frames, what=source))}
    elif tactile.ndim == 3:
        if tactile.shape[0] != 3:
            raise ValueError(f"{source}: tactile snapshot must be (3, rows, cols)")
        frames = tactile.transpose(2, 1, 0)[np.newaxis, ...]  # (C, U, V) -> (V, U, C)
        sensors = {"taxel": SensorRecording("taxel", _finite_frames(frames, what=source))}
    else:
        raise ValueError(f"{source}: unsupported tactile rank {tactile.ndim}")

    time_key = next((key for key in TIME_KEYS if key in data.files), None)
    frame_count = sensors[next(iter(sensors))].frame_count
    if time_key is not None:
        times, time_kind = _times_from(data, frame_count, source=source)
    else:
        times, time_kind = np.arange(frame_count, dtype=np.float64), "index"
    channels = _channels_from(data, DEFAULT_CHANNELS)
    return Recording(
        sensors=sensors,
        times=times,
        time_kind=time_kind,
        channels=channels,
        units=_units_from(data),
        schema="tactile-snapshot" if tactile.ndim == 3 else "tactile-timeseries",
        source=source,
    )


def _recording_from_trajectory(data, source):
    readings = np.asarray(data["readings"], dtype=np.float64)
    frames = _finite_frames(readings, what=f"{source}:readings")
    times, time_kind = _times_from(data, frames.shape[0], source=source)
    sensors = {"taxel": SensorRecording("taxel", frames)}
    channels = _channels_from(data, TRAJECTORY_CHANNELS)
    return Recording(
        sensors=sensors,
        times=times,
        time_kind=time_kind,
        channels=channels,
        units=_units_from(data),
        schema="tactile-trajectory",
        source=source,
    )


def _recording_from_snapshot_keys(data, source):
    names = [key for key in data.files if key in DEFAULT_SENSOR_NAMES]
    sensors = {}
    for name in names:
        snapshot = np.asarray(data[name], dtype=np.float64)
        if snapshot.ndim != 3 or snapshot.shape[0] != 3:
            raise ValueError(f"{source}:{name} must be (3, rows, cols)")
        frames = snapshot.transpose(2, 1, 0)[np.newaxis, ...]  # (C, U, V) -> (V, U, C)
        sensors[name] = SensorRecording(name, _finite_frames(frames, what=f"{source}:{name}"))
    if not sensors:
        raise ValueError(f"{source}: no supported tactile arrays found")
    return Recording(
        sensors=sensors,
        times=np.zeros(1, dtype=np.float64),
        time_kind="snapshot",
        channels=_channels_from(data, DEFAULT_CHANNELS),
        units=_units_from(data),
        schema="tactile-snapshot",
        source=source,
    )


def _channels_from(data, default):
    if "channels" in data.files:
        names = tuple(str(name) for name in np.asarray(data["channels"]).reshape(-1))
        if len(names) == 3:
            return names
    return default


def _units_from(data):
    if "units" in data.files:
        values = np.asarray(data["units"]).reshape(-1)
        if values.size:
            return str(values[0])
    return "N"


def load_recording(path):
    """Load one .npz recording; raises ValueError for unsupported content."""
    source = os.fspath(path)
    try:
        data = np.load(source, allow_pickle=False)
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read recording {source}: {error}") from error
    try:
        if "tactile" in data.files:
            return _recording_from_tactile(data, source)
        if "readings" in data.files:
            return _recording_from_trajectory(data, source)
        if "tactile_fixed" in data.files or "tactile_moving" in data.files:
            return _recording_from_snapshot_keys(data, source)
        raise ValueError(
            f"{source}: no supported arrays (expected tactile, readings, or tactile_fixed/moving)"
        )
    finally:
        close = getattr(data, "close", None)
        if callable(close):
            close()
