import numpy as np


COMPONENTS = ["Fx", "Fy", "Fz", "Mx", "My", "Mz"]


def aggregate_tri_axis_wrench(readings, positions, reference_point):
    readings = np.asarray(readings, dtype=np.float64)
    positions = np.asarray(positions, dtype=np.float64)
    reference_point = np.asarray(reference_point, dtype=np.float64)
    if readings.ndim != 2 or readings.shape[1] != 3:
        raise ValueError("3-axis readings must have shape [N, 3]")

    offsets = positions - reference_point
    force = np.sum(readings, axis=0)
    moments = np.sum(np.cross(offsets, readings), axis=0)
    return {
        "Fx": float(force[0]),
        "Fy": float(force[1]),
        "Fz": float(force[2]),
        "Mx": float(moments[0]),
        "My": float(moments[1]),
        "Mz": float(moments[2]),
    }


def estimate_tri_axis_wrench(readings, positions, reference_point):
    numeric = aggregate_tri_axis_wrench(readings, positions, reference_point)
    return {
        component: {
            "value": numeric[component],
            "status": "estimated",
            "reason": "recoverable from 3-axis distributed force readings",
        }
        for component in COMPONENTS
    }
