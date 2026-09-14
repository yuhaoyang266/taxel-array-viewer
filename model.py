from dataclasses import dataclass, field
import importlib.util
from pathlib import Path

import numpy as np


CHANNELS = 3
COMPONENTS = ("Fx", "Fy", "Fz", "Mx", "My", "Mz")


def _integer(value, name):
    numeric = float(value)
    if not np.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"{name} must be an integer")
    return int(numeric)


def _positive_integer(value, name):
    numeric = _integer(value, name)
    if numeric <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return numeric


def _positive_float(value, name):
    numeric = float(value)
    if not np.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return numeric


@dataclass(frozen=True)
class ArrayGeometry:
    rows: int = 3
    cols: int = 3
    pitch_x_mm: float = 20.0
    pitch_y_mm: float = 20.0
    taxel_width_x_mm: float = 20.0
    taxel_width_y_mm: float = 20.0

    def __post_init__(self):
        object.__setattr__(self, "rows", _positive_integer(self.rows, "rows"))
        object.__setattr__(self, "cols", _positive_integer(self.cols, "cols"))
        object.__setattr__(self, "pitch_x_mm", _positive_float(self.pitch_x_mm, "pitch_x_mm"))
        object.__setattr__(self, "pitch_y_mm", _positive_float(self.pitch_y_mm, "pitch_y_mm"))
        object.__setattr__(self, "taxel_width_x_mm", _positive_float(self.taxel_width_x_mm, "taxel_width_x_mm"))
        object.__setattr__(self, "taxel_width_y_mm", _positive_float(self.taxel_width_y_mm, "taxel_width_y_mm"))
        if self.taxel_width_x_mm > self.pitch_x_mm:
            raise ValueError("taxel_width_x_mm must not exceed pitch_x_mm")
        if self.taxel_width_y_mm > self.pitch_y_mm:
            raise ValueError("taxel_width_y_mm must not exceed pitch_y_mm")

    @property
    def shape(self):
        return self.rows, self.cols, CHANNELS

    @property
    def point_count(self):
        return self.rows * self.cols

    @property
    def pitch_x_m(self):
        return self.pitch_x_mm / 1000.0

    @property
    def pitch_y_m(self):
        return self.pitch_y_mm / 1000.0

    @property
    def taxel_area_m2(self):
        return self.taxel_width_x_mm * self.taxel_width_y_mm / 1_000_000.0

    @property
    def footprint_x_mm(self):
        return (self.cols - 1) * self.pitch_x_mm + self.taxel_width_x_mm

    @property
    def footprint_y_mm(self):
        return (self.rows - 1) * self.pitch_y_mm + self.taxel_width_y_mm

    def centre_coordinates_mm(self):
        x_coordinates = (np.arange(self.cols, dtype=np.float64) - (self.cols - 1) / 2.0) * self.pitch_x_mm
        y_coordinates = (np.arange(self.rows, dtype=np.float64) - (self.rows - 1) / 2.0) * self.pitch_y_mm
        return x_coordinates, y_coordinates

    def positions_m(self):
        x_coordinates_mm, y_coordinates_mm = self.centre_coordinates_mm()
        grid_x_mm, grid_y_mm = np.meshgrid(x_coordinates_mm, y_coordinates_mm)
        return np.column_stack(
            (
                grid_x_mm.reshape(-1) / 1000.0,
                grid_y_mm.reshape(-1) / 1000.0,
                np.zeros(self.point_count, dtype=np.float64),
            )
        )

    def taxel_rect_mm(self, row, col):
        row, col = validated_index(row, col, self)
        x_coordinates_mm, y_coordinates_mm = self.centre_coordinates_mm()
        return (
            x_coordinates_mm[col] - self.taxel_width_x_mm / 2.0,
            y_coordinates_mm[row] - self.taxel_width_y_mm / 2.0,
            self.taxel_width_x_mm,
            self.taxel_width_y_mm,
        )

    def locate_taxel(self, x_mm, y_mm, shape="rectangle"):
        x_mm = float(x_mm)
        y_mm = float(y_mm)
        if not np.isfinite(x_mm) or not np.isfinite(y_mm):
            return None
        x_coordinates_mm, y_coordinates_mm = self.centre_coordinates_mm()
        col = int(np.argmin(np.abs(x_coordinates_mm - x_mm)))
        row = int(np.argmin(np.abs(y_coordinates_mm - y_mm)))
        delta_x = x_coordinates_mm[col] - x_mm
        delta_y = y_coordinates_mm[row] - y_mm
        if shape == "circle":
            if not np.isclose(self.taxel_width_x_mm, self.taxel_width_y_mm):
                raise ValueError("circle taxels require equal x/y widths")
            radius = self.taxel_width_x_mm / 2.0
            if delta_x**2 + delta_y**2 > radius**2:
                return None
        elif shape == "rectangle":
            if abs(delta_x) > self.taxel_width_x_mm / 2.0:
                return None
            if abs(delta_y) > self.taxel_width_y_mm / 2.0:
                return None
        else:
            raise ValueError("shape must be 'rectangle' or 'circle'")
        return row, col


def _load_verified_aggregator():
    module_path = Path(__file__).resolve().parent / "tri_axis_array" / "code" / "estimate.py"
    if not module_path.is_file():
        raise ImportError(f"Verified wrench aggregator not found: {module_path}")

    specification = importlib.util.spec_from_file_location("tri_axis_array_estimate", module_path)
    if specification is None or specification.loader is None:
        raise ImportError(f"Unable to load verified wrench aggregator: {module_path}")

    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.aggregate_tri_axis_wrench


aggregate_tri_axis_wrench = _load_verified_aggregator()


def validated_readings(readings, geometry):
    readings = np.asarray(readings, dtype=np.float64)
    if readings.shape != geometry.shape:
        raise ValueError(f"readings must have shape {geometry.shape}, got {readings.shape}")
    if not np.isfinite(readings).all():
        raise ValueError("readings must contain only finite values")
    return readings.copy()


def validated_index(row, col, geometry):
    row = _integer(row, "row")
    col = _integer(col, "col")
    if not 0 <= row < geometry.rows or not 0 <= col < geometry.cols:
        raise IndexError(f"taxel index out of range: row={row}, col={col}")
    return row, col


@dataclass
class TaxelArrayModel:
    geometry: ArrayGeometry = field(default_factory=ArrayGeometry)
    readings: np.ndarray | None = None
    selected: tuple[int, int] | None = None

    def __post_init__(self):
        if not isinstance(self.geometry, ArrayGeometry):
            raise TypeError("geometry must be an ArrayGeometry")
        self.positions = self.geometry.positions_m()
        self.reference_point = np.zeros(3, dtype=np.float64)
        source = np.zeros(self.geometry.shape, dtype=np.float64) if self.readings is None else self.readings
        self.readings = validated_readings(source, self.geometry)
        if self.selected is None:
            self.selected = (self.geometry.rows // 2, self.geometry.cols // 2)
        self.selected = validated_index(*self.selected, self.geometry)

    def select_taxel(self, row, col):
        self.selected = validated_index(row, col, self.geometry)

    def selected_force(self):
        row, col = self.selected
        return self.readings[row, col].copy()

    def set_selected_force(self, force):
        row, col = self.selected
        self.set_taxel_force(row, col, force)

    def set_force_field(self, readings):
        self.readings = validated_readings(readings, self.geometry)

    def set_taxel_force(self, row, col, force):
        row, col = validated_index(row, col, self.geometry)
        force = np.asarray(force, dtype=np.float64)
        if force.shape != (CHANNELS,):
            raise ValueError(f"force must have shape ({CHANNELS},), got {force.shape}")
        if not np.isfinite(force).all():
            raise ValueError("force must contain only finite values")
        self.readings[row, col] = force

    def wrench(self):
        return aggregate_tri_axis_wrench(
            self.readings.reshape(-1, CHANNELS),
            self.positions,
            self.reference_point,
        )
