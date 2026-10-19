"""Display-only theme tokens and helpers for the taxel viewer windows.

This module owns colours, typography and QSS for the PySide6/pyqtgraph
frontends. It deliberately carries no mechanics, geometry or history logic,
and it must not import pyqtgraph or cloud_field:

* pyqtgraph is imported by the GUI modules only after PYQTGRAPH_QT_LIB is set,
  so importing it here would change that ordering.
* cloud_field keeps the authoritative cloud LUTs (DIVERGING_LUT is pinned by
  test_cloud_field.py), so this module never wraps or replaces them.

Every token is a plain module constant so tests can assert them without
constructing a window.
"""

import numpy as np
from PySide6 import QtGui


WINDOW_BG = "#0B0F17"
PANEL_BG = "#111827"
CANVAS_BG = "#0D131F"
BORDER = "#243244"
TEXT_PRIMARY = "#E5E7EB"
TEXT_MUTED = "#94A3B8"
ZERO_LINE_COLOUR = "#4B5563"

# Force/moment semantic colours. Keys match the existing FORCE_COMPONENTS /
# MOMENT_COMPONENTS tuples so the GUI modules can reuse their dict lookups.
AXIS_COLOURS = {
    "Fx": (239, 83, 80),
    "Fy": (102, 187, 106),
    "Fz": (66, 165, 245),
}
MOMENT_COLOURS = {
    "Mx": (38, 198, 218),
    "My": (255, 202, 40),
    "Mz": (171, 71, 188),
}

# Shear arrows used to be near-black on a deep-blue cell, which is invisible at
# low load. These light values keep the arrow readable on every cell colour.
ARROW_LINE_COLOUR = (203, 213, 225)
ARROW_COLOUR = (231, 236, 245)
SELECTION_COLOUR = (255, 215, 0)
TAXEL_PEN = (12, 18, 28)
CLOUD_TAXEL_PEN = (100, 116, 139)

# Structural diagram identity colours. Yellow marks the moving plate and white
# the contact force face; neither changes with load, so the diagram never turns
# a part into an unreadable load colour.
FRAME_FILL = "#1B2534"
FRAME_PEN = "#3F4C5F"
FIXED_ELECTRODE_FILL = "#8FA3B8"
FIXED_ELECTRODE_PEN = "#C7D2DE"
MOVING_PLATE_FILL = "#F2C744"
MOVING_PLATE_PEN = "#B9880E"
FORCE_FACE_FILL = "#F8FAFC"
FORCE_FACE_PEN = "#CBD5E1"
SILICONE_FILL = "#1F6F6B"
SILICONE_PEN = "#3DD6C4"
GAP_ACCENT = "#22D3EE"
LEADER_COLOUR = "#7C8BA1"

# Cloud display palettes (UI layer only). cloud_field keeps its own pinned
# LUTs because apply_lut tests assert their exact RGB values; the array window
# draws and colours its colourbar from these dark-background-friendly ramps.
CLOUD_SEQUENTIAL_LUT = (
    np.array([0.0, 0.25, 0.5, 0.75, 1.0]),
    np.array(
        [
            (15, 23, 42),      # unloaded: near the canvas background
            (30, 64, 175),
            (8, 145, 178),
            (245, 158, 11),
            (239, 68, 68),     # peak load
        ],
        dtype=np.float64,
    ),
)
CLOUD_DIVERGING_LUT = (
    np.array([-1.0, -0.5, 0.0, 0.5, 1.0]),
    np.array(
        [
            (14, 116, 144),    # negative moment: teal
            (56, 189, 248),
            (30, 41, 59),      # zero: dark slate, no white glare on the canvas
            (251, 146, 60),
            (244, 63, 94),     # positive moment
        ],
        dtype=np.float64,
    ),
)

MONO_FAMILIES = (
    "JetBrains Mono",
    "Cascadia Mono",
    "Consolas",
    "DejaVu Sans Mono",
    "Menlo",
    "monospace",
)
MONO_POINT_SIZE = 10


def _as_colour(value):
    """Return a QColor without touching the original object."""
    if isinstance(value, QtGui.QColor):
        return QtGui.QColor(value)
    if isinstance(value, QtGui.QBrush):
        return QtGui.QColor(value.color())
    if isinstance(value, (tuple, list)):
        if len(value) not in (3, 4):
            raise ValueError("colour tuples must have 3 or 4 components")
        return QtGui.QColor(*(int(component) for component in value))
    return QtGui.QColor(value)


def qcolor(value):
    """Coerce a QColor, an (r, g, b) tuple or a #RRGGBB string to QColor."""
    return _as_colour(value)


def with_alpha(value, alpha):
    """Return a copy of value with the given integer alpha (0-255)."""
    colour = _as_colour(value)
    colour.setAlpha(int(alpha))
    return colour


def mono_font(point_size=MONO_POINT_SIZE, bold=False):
    """Return the monospaced font used for numeric readouts."""
    font = QtGui.QFont()
    font.setFamilies(list(MONO_FAMILIES))
    font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
    font.setPointSize(int(point_size))
    font.setBold(bool(bold))
    return font


def mono_family_qss():
    """Return a CSS font-family list with a generic monospace fallback."""
    families = ", ".join('"' + name + '"' if " " in name else name for name in MONO_FAMILIES)
    return families


def window_qss():
    """Window-level QSS: colours only, never layout metrics.

    padding/margin/min-width/font-size are intentionally absent: the array
    window has an 800-pixel workspace assertion that a wider
    stylesheet-driven minimum size would break.
    """
    return (
        f"QMainWindow {{ background: {WINDOW_BG}; }}"
        f"QMainWindow > QWidget {{ background: {WINDOW_BG}; }}"
        f"QLabel {{ color: {TEXT_PRIMARY}; }}"
        f"QPushButton, QToolButton {{"
        f" color: {TEXT_PRIMARY}; background: {PANEL_BG};"
        f" border: 1px solid {BORDER}; border-radius: 4px; }}"
        f"QPushButton:checked, QToolButton:checked {{"
        f" background: #1E2A3A; border-color: {GAP_ACCENT}; }}"
        f"QPushButton:hover, QToolButton:hover {{ background: #172335; }}"
    )


def label_qss(role="primary"):
    """QLabel QSS by role: primary text, muted text, or mono readout."""
    if role == "muted":
        return f"color: {TEXT_MUTED};"
    if role == "mono":
        return f"color: {TEXT_PRIMARY}; font-family: {mono_family_qss()};"
    if role == "primary":
        return f"color: {TEXT_PRIMARY};"
    raise ValueError("role must be 'primary', 'muted' or 'mono'")


def panel_qss():
    """Card-style QSS for the structure detail panel."""
    return (
        f"QWidget#StructurePanel {{ background: {PANEL_BG};"
        f" border: 1px solid {BORDER}; border-radius: 6px; }}"
    )


def legend_qss():
    """Small muted text used by legends and diagram captions."""
    return f"color: {TEXT_MUTED};"


def scroll_area_qss():
    """Transparent scroll area with a slim dark scrollbar for detail panels."""
    return (
        "QScrollArea { background: transparent; border: none; }"
        "QScrollArea > QWidget > QWidget { background: transparent; }"
        f"QScrollBar:vertical {{ background: {WINDOW_BG}; width: 8px; margin: 0px; border: none; }}"
        f"QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 24px; border-radius: 4px; }}"
        "QScrollBar::handle:vertical:hover { background: #3B4D66; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }"
    )


def toggle_qss():
    """Compact toggle button used only by the single-taxel window.

    This window has no 800-pixel assertion, so a small padding is allowed here;
    it is still kept out of window_qss() for the array window.
    """
    return (
        f"QToolButton {{ color: {TEXT_PRIMARY}; background: {PANEL_BG};"
        f" border: 1px solid {BORDER}; border-radius: 4px; padding: 2px 8px; }}"
        f"QToolButton:checked {{ background: #1E2A3A; border-color: {GAP_ACCENT}; }}"
    )


def apply_window_theme(window):
    """Apply the window-local stylesheet (never QApplication.setStyleSheet)."""
    window.setStyleSheet(window_qss())


def apply_panel_theme(widget):
    """Apply the structure-panel card stylesheet."""
    widget.setStyleSheet(panel_qss())


def apply_canvas_theme(widget, role="canvas"):
    """Paint a pyqtgraph GraphicsView background without importing pyqtgraph.

    pyqtgraph GraphicsView exposes setBackground; plain Qt widgets fall back to
    setBackgroundBrush (QGraphicsView) or a palette override.
    """
    if role not in {"canvas", "panel"}:
        raise ValueError("role must be 'canvas' or 'panel'")
    colour = qcolor(CANVAS_BG if role == "canvas" else PANEL_BG)
    set_background = getattr(widget, "setBackground", None)
    if callable(set_background):
        set_background(colour)
        return
    set_brush = getattr(widget, "setBackgroundBrush", None)
    if callable(set_brush):
        set_brush(QtGui.QBrush(colour))
        return
    palette = widget.palette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, colour)
    widget.setPalette(palette)


def field_ramp_colour(normalised):
    """Map a normalised normal force to the sequential field colour.

    Mathematically identical to the ramp previously inlined in
    pyqt_live._render_array_view and pyqt_single_taxel._update_sensor, so cell
    colours are unchanged while the implementation lives in one place.
    """
    n = 0.0 if normalised < 0.0 else (1.0 if normalised > 1.0 else float(normalised))
    if n <= 0.45:
        fraction = n / 0.45
        return (
            round(25 + fraction * 55),
            round(55 + fraction * 125),
            round(150 + fraction * 85),
        )
    fraction = (n - 0.45) / 0.55
    return (
        round(80 + fraction * 165),
        round(180 - fraction * 105),
        round(235 - fraction * 180),
    )
