from collections import deque

import numpy as np

from model import ArrayGeometry, CHANNELS, COMPONENTS, validated_index, validated_readings


class LiveHistory:
    def __init__(self, max_samples, geometry=None, max_age_seconds=None):
        max_samples = int(max_samples)
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self.geometry = ArrayGeometry() if geometry is None else geometry
        if not isinstance(self.geometry, ArrayGeometry):
            raise TypeError("geometry must be an ArrayGeometry")
        self.max_samples = max_samples
        if max_age_seconds is not None:
            max_age_seconds = float(max_age_seconds)
            if not np.isfinite(max_age_seconds) or max_age_seconds <= 0.0:
                raise ValueError("max_age_seconds must be finite and positive")
        self.max_age_seconds = max_age_seconds
        self._times = deque(maxlen=max_samples)
        self._fields = deque(maxlen=max_samples)
        self._wrenches = deque(maxlen=max_samples)

    def __len__(self):
        return len(self._times)

    def append(self, elapsed_s, readings, wrench):
        elapsed_s = float(elapsed_s)
        if not np.isfinite(elapsed_s):
            raise ValueError("elapsed_s must be finite")
        readings = validated_readings(readings, self.geometry)
        wrench_vector = np.asarray([wrench[component] for component in COMPONENTS], dtype=np.float64)
        if wrench_vector.shape != (len(COMPONENTS),) or not np.isfinite(wrench_vector).all():
            raise ValueError("wrench must provide six finite components")

        self._times.append(elapsed_s)
        self._fields.append(readings)
        self._wrenches.append(wrench_vector)
        if self.max_age_seconds is not None:
            cutoff = elapsed_s - self.max_age_seconds
            while self._times and self._times[0] < cutoff:
                self._times.popleft()
                self._fields.popleft()
                self._wrenches.popleft()

    def relative_times(self):
        if not self._times:
            return np.empty(0, dtype=np.float64)
        times = np.asarray(self._times, dtype=np.float64)
        return times - times[-1]

    def wrench_matrix(self):
        if not self._wrenches:
            return np.empty((0, len(COMPONENTS)), dtype=np.float64)
        return np.stack(self._wrenches)

    def selected_taxel_matrix(self, row, col):
        row, col = validated_index(row, col, self.geometry)
        if not self._fields:
            return np.empty((0, CHANNELS), dtype=np.float64)
        return np.stack([field[row, col] for field in self._fields])
