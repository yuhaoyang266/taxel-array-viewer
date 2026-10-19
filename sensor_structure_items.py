"""Schematic structure items for one five-gap capacitive taxel unit.

Every length in this module is a **fraction of the nominal cell width** (the
span): the diagrams are schematics, not dimensioned drawings.  Real plate sizes,
initial gaps, displacements, silicone geometry and capacitance values are not
known for this build, so none is encoded or displayed here.  The only digits
allowed in scene text are the part counts "×4" and "×1"; dimension_texts() exists
so a test can enforce that.

The three part identities stay visually separate, per the design document: the
fixed frame/base and fixed electrodes are neutral, the moving plate is yellow and
the contact force face is white.  Cyan is used only to say "a capacitive gap is
here"; it never carries a number.

The five gaps: four lateral ones (one per side) are shown in the top view, and
the single bottom one is shown in the cross-section.  The top view additionally
carries the occluded bottom-capacitor contour so the reader does not conclude
that four gaps are all there is.

Coordinates: helpers take schematic millimetres with y pointing up and map them
through scene_point() / scene_rect(), the single place where the Qt scene's
downward y axis is flipped.  No item applies a negative scale, so text is never
mirrored.

Click safety: this module is display-only.  Every item answers
Qt.MouseButton.NoButton and is neither selectable, movable nor focusable, and
StructureView is a separate non-interactive widget with
WA_TransparentForMouseEvents, so it can never take clicks away from the
pyqtgraph plots it sits next to.  The array face items (TaxelFaceRectItem /
TaxelFaceEllipseItem) only override paint(): their geometry, shape() and mouse
handling stay inherited.
"""

import dataclasses
import math
import re

from PySide6 import QtCore, QtGui, QtWidgets

from ui_theme import (
    FIXED_ELECTRODE_FILL,
    FIXED_ELECTRODE_PEN,
    FORCE_FACE_FILL,
    FORCE_FACE_PEN,
    FRAME_FILL,
    FRAME_PEN,
    GAP_ACCENT,
    LEADER_COLOUR,
    MOVING_PLATE_FILL,
    MOVING_PLATE_PEN,
    SILICONE_FILL,
    SILICONE_PEN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    apply_canvas_theme,
    mono_font,
    qcolor,
    with_alpha,
)


# --- fixed wording (verbatim; asserted by test_sensor_structure_items) --------

SCHEMATIC_NOTE = "结构示意，非尺寸图；当前仅显示三轴力，未接入间隙/电容读数"
TOP_VIEW_CAPTION = "俯视示意：固定外框 + 中央活动板 + 四侧电容（间隙为示意，非尺寸）"
SECTION_CAPTION = "剖面示意：底部电容 + 侧向电容；硅胶位置仅示意"
IN_SCENE_NOTE = "结构示意，非尺寸图"

# Three quantities the diagram must never conflate: the body envelope, the white
# force face that actually transmits load, and the cell centre pitch. Bodies can
# be adjacent while force faces stay apart, and bodies can have assembly gaps.
GEOMETRY_UNCERTAINTY_NOTE = (
    "本体外轮廓、白色受力面、单元中心距是三个独立量：本体相邻不代表受力面相邻，"
    "受力面之间可能有固定框架，本体之间也可能有装配间隙。"
    "本图为标称演示配置，实际尺寸与间隙尚未确认。"
)

LEGEND_ITEMS = (
    ("固定外框 / 固定电极", "本体固定结构", FRAME_PEN),
    ("中央活动板", "随受力运动的部件", MOVING_PLATE_FILL),
    ("白色受力面", "接触传力面", FORCE_FACE_FILL),
    ("侧向电容 ×4", "电容间隙，示意", GAP_ACCENT),
    ("底部电容 ×1", "电容间隙，示意", GAP_ACCENT),
    ("硅胶支撑", "弹性复位，位置示意", SILICONE_PEN),
)
LEGEND_NOTE = "黄色=活动部件，白色=传力面，青色=示意间隙；间隙不作尺寸标注。"

LATERAL_GAP_COUNT = 4
BOTTOM_GAP_COUNT = 1

#: Schematic gap constant shared by all five gaps.  It is a drawing constant,
#: NOT a measured or assumed hardware gap: the real initial gaps are unknown.
SCHEMATIC_GAP_FRACTION = 0.05

#: Inset of the decorative face highlight, as a fraction of the shorter side.
FACE_HIGHLIGHT_INSET = 0.10

#: Scene text size.  Text ignores the view transform, so this is a pixel size;
#: 8 pt keeps the long labels inside the label band without overflowing the view.
SCENE_TEXT_POINT_SIZE = 8

# --- z bands (this module owns 1..8; the array view keeps its own bands) ------

Z_FRAME = 1.0
Z_ELECTRODE = 2.0
Z_SILICONE = 3.0
Z_GAP = 4.0
Z_PLATE = 5.0
Z_FACE = 6.0
Z_LEADER = 7.0
Z_TEXT = 8.0

#: Text columns live outside the geometry in bands of this width (span fraction).
LABEL_BAND_FRACTION = 0.24

_GRAPHICS_ITEM_FLAG = QtWidgets.QGraphicsItem.GraphicsItemFlag
_MOUSE_NO_BUTTON = QtCore.Qt.MouseButton.NoButton
_NO_BRUSH = QtCore.Qt.BrushStyle.NoBrush

_DIMENSION_PATTERN = re.compile(
    r"\d\s*(?:mm|µm|μm|um|nm|pF|\bN\b)", re.IGNORECASE
)


# --- coordinate mapping ------------------------------------------------------

def scene_point(x_mm, y_mm):
    """Map schematic millimetres (y up) to scene coordinates (y down).

    This is the only y flip in this module: every item and helper routes its
    points through it, so the two conventions cannot drift apart.
    """
    return QtCore.QPointF(float(x_mm), -float(y_mm))


def scene_rect(centre_x_mm, centre_y_mm, width_mm, height_mm):
    """Map a centred schematic rectangle (y up) to a scene rectangle (y down)."""
    width = float(width_mm)
    height = float(height_mm)
    return QtCore.QRectF(
        float(centre_x_mm) - width / 2.0,
        -(float(centre_y_mm) + height / 2.0),
        width,
        height,
    )


def _mm_rect(x_min, x_max, y_min, y_max):
    """Scene rect from schematic edges, still routed through scene_rect()."""
    return scene_rect(
        (x_min + x_max) / 2.0,
        (y_min + y_max) / 2.0,
        x_max - x_min,
        y_max - y_min,
    )


# --- pen/brush helpers -------------------------------------------------------

def _pen(colour, width=0.0, style=QtCore.Qt.PenStyle.SolidLine):
    """Cosmetic pen: device-pixel width, so zooming cannot fatten the strokes."""
    pen = QtGui.QPen(qcolor(colour), float(width), style)
    pen.setCosmetic(True)
    return pen


def _gap_pen(dashed=False):
    style = QtCore.Qt.PenStyle.DashLine if dashed else QtCore.Qt.PenStyle.SolidLine
    return _pen(GAP_ACCENT, 1.2, style)


def _leader_pen():
    return _pen(LEADER_COLOUR, 0.0)


def _outline_pen(colour):
    return _pen(colour, 0.0)


def _fill(colour, alpha=None):
    colour = qcolor(colour)
    if alpha is not None:
        colour.setAlpha(int(alpha))
    return QtGui.QBrush(colour)


# --- metrics -----------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class StructureMetrics:
    """Schematic geometry of one unit, all values as fractions of span.

    span is the nominal cell width in millimetres; internal coordinates are
    "schematic millimetres" whose absolute magnitude carries no meaning.  The
    four geometry self-checks asserted by the tests are:
    plate_bottom - bottom_electrode_top == gap,
    lateral_electrode_inner - plate_radius == gap,
    lateral_pad_inner - plate_radius == gap and
    lateral_pad_outer == frame_outer / 2 - frame_ring.
    """

    span: float

    # top view: fixed frame ring
    frame_outer: float
    frame_ring: float
    frame_radius: float

    # moving plate and contact face (shared by both views)
    plate_diameter: float
    face_diameter: float

    # schematic gap constant (all five gaps; see SCHEMATIC_GAP_FRACTION)
    gap: float

    # top view: four lateral fixed electrodes, radially inner/outer edges
    lateral_pad_inner: float
    lateral_pad_outer: float
    lateral_pad_width: float

    # top view: occluded bottom-capacitor contour radius
    hidden_bottom_radius: float

    # cross-section: base block
    base_half: float
    base_top: float
    base_bottom: float

    # cross-section: bottom fixed electrode
    bottom_electrode_half: float
    bottom_electrode_top: float

    # cross-section: moving plate and force face heights
    plate_bottom: float
    plate_top: float
    face_top: float

    # cross-section: side walls and lateral fixed electrodes
    side_wall_inner: float
    side_wall_outer: float
    lateral_electrode_inner: float
    lateral_electrode_top: float
    lateral_electrode_bottom: float

    # cross-section: silicone support radial range
    silicone_inner: float
    silicone_outer: float

    @classmethod
    def from_diameter(cls, diameter_mm):
        """Build metrics scaled to diameter_mm (the nominal cell width)."""
        span = float(diameter_mm)
        if not math.isfinite(span) or span <= 0.0:
            raise ValueError("diameter_mm must be a positive finite number")
        gap = SCHEMATIC_GAP_FRACTION * span
        return cls(
            span=span,
            frame_outer=1.30 * span,
            frame_ring=0.14 * span,
            frame_radius=0.10 * span,
            plate_diameter=0.66 * span,
            face_diameter=0.46 * span,
            gap=gap,
            lateral_pad_inner=0.38 * span,
            lateral_pad_outer=0.51 * span,
            lateral_pad_width=0.24 * span,
            hidden_bottom_radius=0.30 * span,
            base_half=0.65 * span,
            base_top=-0.36 * span,
            base_bottom=-0.50 * span,
            bottom_electrode_half=0.30 * span,
            bottom_electrode_top=-0.30 * span,
            plate_bottom=-0.25 * span,
            plate_top=-0.01 * span,
            face_top=0.12 * span,
            side_wall_inner=0.44 * span,
            side_wall_outer=0.51 * span,
            lateral_electrode_inner=0.38 * span,
            lateral_electrode_top=0.02 * span,
            lateral_electrode_bottom=-0.22 * span,
            silicone_inner=0.10 * span,
            silicone_outer=0.30 * span,
        )

    # -- derived helpers ------------------------------------------------------

    @property
    def plate_radius(self):
        return self.plate_diameter / 2.0

    @property
    def face_radius(self):
        return self.face_diameter / 2.0

    @property
    def label_band(self):
        return LABEL_BAND_FRACTION * self.span

    @property
    def frame_inner_half(self):
        return self.frame_outer / 2.0 - self.frame_ring


# --- inert item helpers ------------------------------------------------------

def _make_inert(item):
    """Make an item display-only: no mouse buttons, no selection/interaction."""
    item.setAcceptedMouseButtons(_MOUSE_NO_BUTTON)
    item.setFlag(_GRAPHICS_ITEM_FLAG.ItemIsSelectable, False)
    item.setFlag(_GRAPHICS_ITEM_FLAG.ItemIsMovable, False)
    item.setFlag(_GRAPHICS_ITEM_FLAG.ItemIsFocusable, False)
    return item


class _StructureItemBase(QtWidgets.QGraphicsItemGroup):
    """Common base: item registry, inert flags, scene text and leader helpers."""

    #: Fraction of the label band used as clearance for right-hand labels.
    _LABEL_CLEARANCE = 0.10

    def __init__(self, metrics, parent=None):
        super().__init__(parent)
        if not isinstance(metrics, StructureMetrics):
            raise TypeError("metrics must be a StructureMetrics instance")
        self.metrics = metrics
        self.texts = []
        self.text_items = []
        self.leader_items = []
        self.setAcceptedMouseButtons(_MOUSE_NO_BUTTON)
        self.setFlag(_GRAPHICS_ITEM_FLAG.ItemIsSelectable, False)
        self.setFlag(_GRAPHICS_ITEM_FLAG.ItemIsMovable, False)
        self.setFlag(_GRAPHICS_ITEM_FLAG.ItemIsFocusable, False)
        # Nothing here is interactive: child events never need forwarding.
        self.setHandlesChildEvents(False)

    def _add(self, item):
        _make_inert(item)
        self.addToGroup(item)
        return item

    # -- text ----------------------------------------------------------------

    def _label_x(self, side):
        half = self.metrics.frame_outer / 2.0
        band = self.metrics.label_band
        if side == "left":
            return -(half + band)
        if side == "right":
            return half + band * self._LABEL_CLEARANCE
        raise ValueError("side must be 'left' or 'right'")

    def _leader_start_x(self, side):
        half = self.metrics.frame_outer / 2.0
        band = self.metrics.label_band
        if side == "left":
            return -(half + band * 0.45)
        return half + band * 0.45

    def _label(self, side, y_mm, value, target_mm=None):
        label = QtWidgets.QGraphicsSimpleTextItem(value)
        label.setFont(mono_font(SCENE_TEXT_POINT_SIZE))
        label.setBrush(_fill(TEXT_PRIMARY))
        label.setFlag(_GRAPHICS_ITEM_FLAG.ItemIgnoresTransformations, True)
        label.setZValue(Z_TEXT)
        self._add(label)
        label.setPos(scene_point(self._label_x(side), y_mm))
        self.text_items.append(label)
        self.texts.append(value)
        if target_mm is not None:
            start = (self._leader_start_x(side), y_mm - self.metrics.span * 0.03)
            self._leader(start, target_mm)
        return label

    def _leader(self, start_mm, end_mm):
        line = QtWidgets.QGraphicsLineItem(
            QtCore.QLineF(scene_point(*start_mm), scene_point(*end_mm))
        )
        line.setPen(_leader_pen())
        line.setZValue(Z_LEADER)
        self._add(line)
        self.leader_items.append(line)
        return line


# --- top view ----------------------------------------------------------------

class TopViewStructureItem(_StructureItemBase):
    """Top view: frame ring, four lateral gaps, plate/face, hidden bottom gap."""

    _LATERAL_ANGLES = (0.0, 90.0, 180.0, 270.0)

    def __init__(self, metrics, parent=None):
        super().__init__(metrics, parent)
        self.frame_item = None
        self.electrode_items = []
        self.lateral_gap_markers = []
        self.bottom_cap_hidden_marker = None
        self.plate_item = None
        self.face_item = None
        self._build()

    # -- geometry ------------------------------------------------------------

    def _build(self):
        m = self.metrics
        self.frame_item = self._add(self._build_frame_ring())
        for angle in self._LATERAL_ANGLES:
            self.electrode_items.append(self._add(self._build_lateral_pad(angle)))
        for angle in self._LATERAL_ANGLES:
            self.lateral_gap_markers.append(
                self._add(self._build_lateral_gap_marker(angle))
            )
        self.plate_item = self._add(self._build_plate())
        # Qt paints a child after its parent.  The bottom capacitor sits under an
        # opaque plate (hidden radius < plate radius), so it is parented to the
        # plate to stay readable as a technical-drawing hidden line; its z band
        # is still Z_GAP.
        self.bottom_cap_hidden_marker = self._build_hidden_bottom_capacitor()
        self.bottom_cap_hidden_marker.setParentItem(self.plate_item)
        self.face_item = self._add(self._build_face())
        self._build_labels()

    def _oriented_rect(self, angle_degrees, radial_min, radial_max, tangential_half):
        """Axis-aligned rect for a 0/90/180/270 oriented electrode."""
        theta = math.radians(angle_degrees)
        mid = (radial_min + radial_max) / 2.0
        length = radial_max - radial_min
        centre_x = math.cos(theta) * mid
        centre_y = math.sin(theta) * mid
        if abs(math.cos(theta)) >= abs(math.sin(theta)):
            width, height = length, tangential_half * 2.0
        else:
            width, height = tangential_half * 2.0, length
        return scene_rect(centre_x, centre_y, width, height)

    def _rounded_path(self, rect, radius):
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def _build_frame_ring(self):
        m = self.metrics
        outer = scene_rect(0.0, 0.0, m.frame_outer, m.frame_outer)
        inner_half = m.frame_inner_half
        inner = scene_rect(0.0, 0.0, inner_half * 2.0, inner_half * 2.0)
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        path.addRoundedRect(outer, m.frame_radius, m.frame_radius)
        path.addRoundedRect(inner, m.frame_radius, m.frame_radius)
        item = QtWidgets.QGraphicsPathItem(path)
        item.setBrush(_fill(FRAME_FILL))
        item.setPen(_outline_pen(FRAME_PEN))
        item.setZValue(Z_FRAME)
        return item

    def _build_lateral_pad(self, angle_degrees):
        m = self.metrics
        rect = self._oriented_rect(
            angle_degrees,
            m.lateral_pad_inner,
            m.lateral_pad_outer,
            m.lateral_pad_width / 2.0,
        )
        radius = min(rect.width(), rect.height()) * 0.22
        item = QtWidgets.QGraphicsPathItem(self._rounded_path(rect, radius))
        item.setBrush(_fill(FIXED_ELECTRODE_FILL))
        item.setPen(_outline_pen(FIXED_ELECTRODE_PEN))
        item.setZValue(Z_ELECTRODE)
        return item

    def _build_lateral_gap_marker(self, angle_degrees):
        """Two parallel face lines across one lateral gap, plus end caps."""
        m = self.metrics
        theta = math.radians(angle_degrees)
        ux, uy = math.cos(theta), math.sin(theta)
        nx, ny = -uy, ux
        half = m.lateral_pad_width * 0.40
        inner_r = m.plate_radius
        outer_r = m.lateral_pad_inner
        path = QtGui.QPainterPath()
        for radius in (inner_r, outer_r):
            path.moveTo(scene_point(ux * radius - nx * half, uy * radius - ny * half))
            path.lineTo(scene_point(ux * radius + nx * half, uy * radius + ny * half))
        for sign in (1.0, -1.0):
            path.moveTo(scene_point(ux * inner_r - nx * half * sign,
                                    uy * inner_r - ny * half * sign))
            path.lineTo(scene_point(ux * outer_r - nx * half * sign,
                                    uy * outer_r - ny * half * sign))
        item = QtWidgets.QGraphicsPathItem(path)
        item.setBrush(_NO_BRUSH)
        item.setPen(_gap_pen())
        item.setZValue(Z_GAP)
        return item

    def _build_plate(self):
        m = self.metrics
        # The confirmed body has a square moving plate; only the contact force
        # face sitting on it is circular (the white cylinder's cross-section).
        # A square plate also lines the four lateral gaps up with flat edges,
        # which a circle could not do.
        rect = scene_rect(0.0, 0.0, m.plate_diameter, m.plate_diameter)
        item = QtWidgets.QGraphicsPathItem(self._rounded_path(rect, m.span * 0.03))
        item.setBrush(_fill(MOVING_PLATE_FILL))
        item.setPen(_outline_pen(MOVING_PLATE_PEN))
        item.setZValue(Z_PLATE)
        return item

    def _build_face(self):
        m = self.metrics
        item = QtWidgets.QGraphicsEllipseItem(
            scene_rect(0.0, 0.0, m.face_diameter, m.face_diameter)
        )
        item.setBrush(_fill(FORCE_FACE_FILL))
        item.setPen(_outline_pen(FORCE_FACE_PEN))
        item.setZValue(Z_FACE)
        return item

    def _build_hidden_bottom_capacitor(self):
        m = self.metrics
        diameter = m.hidden_bottom_radius * 2.0
        item = QtWidgets.QGraphicsEllipseItem(scene_rect(0.0, 0.0, diameter, diameter))
        item.setBrush(_NO_BRUSH)
        item.setPen(_gap_pen(dashed=True))
        item.setZValue(Z_GAP)
        _make_inert(item)
        return item

    # -- labels --------------------------------------------------------------

    def _build_labels(self):
        m = self.metrics
        self._label(
            "left", m.span * 0.42, "固定外框",
            (-m.frame_outer * 0.45, m.span * 0.42),
        )
        self._label(
            "left", m.span * 0.10, "中央活动板",
            (-m.plate_radius, m.span * 0.06),
        )
        self._label(
            "left", -m.span * 0.10, "受力面",
            (-m.face_radius * 0.72, -m.span * 0.06),
        )
        self._label(
            "right", m.span * 0.02, "侧向电容 ×4",
            (m.plate_radius + m.gap * 0.5, 0.0),
        )
        self._label(
            "left", -m.span * 0.52,
            "底部电容 ×1（板下）",
            (-m.hidden_bottom_radius * 0.75, -m.hidden_bottom_radius * 0.66),
        )
        self._label("left", -m.span * 0.74, IN_SCENE_NOTE)


# --- cross-section -----------------------------------------------------------

class CrossSectionItem(_StructureItemBase):
    """Cross-section: base, one bottom gap, two side gaps, silicone, plate, face."""

    def __init__(self, metrics, parent=None):
        super().__init__(metrics, parent)
        self.base_item = None
        self.electrode_items = []
        self.silicone_items = []
        self.silicone_hatch_items = []
        self.plate_item = None
        self.face_item = None
        self.bottom_gap_marker = None
        self.lateral_gap_markers = []
        self.lateral_gap_note = "侧向电容（左右）；前后两侧见俯视"
        self._build()

    # -- helpers -------------------------------------------------------------

    def _rounded_item(self, rect, radius, fill, pen, z_value):
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        item = QtWidgets.QGraphicsPathItem(path)
        item.setBrush(_fill(fill))
        item.setPen(_outline_pen(pen))
        item.setZValue(z_value)
        return item

    def _build(self):
        m = self.metrics
        self.base_item = self._add(self._build_base())
        for sign in (1.0, -1.0):
            self._add(self._build_side_wall(sign))
        self.electrode_items.append(self._add(self._build_bottom_electrode()))
        for sign in (1.0, -1.0):
            self.electrode_items.append(self._add(self._build_lateral_electrode(sign)))
        for sign in (1.0, -1.0):
            for part in self._build_silicone_support(sign):
                self._add(part)
        self.plate_item = self._add(self._build_plate())
        self.face_item = self._add(self._build_face())
        self.bottom_gap_marker = self._add(self._build_bottom_gap_marker())
        for sign in (1.0, -1.0):
            self.lateral_gap_markers.append(
                self._add(self._build_lateral_gap_marker(sign))
            )
        self._build_labels()

    def _build_base(self):
        m = self.metrics
        rect = _mm_rect(-m.base_half, m.base_half, m.base_bottom, m.base_top)
        return self._rounded_item(
            rect, m.frame_radius * 0.45, FRAME_FILL, FRAME_PEN, Z_FRAME
        )

    def _build_side_wall(self, sign):
        m = self.metrics
        x_min = sign * m.side_wall_inner
        x_max = sign * m.side_wall_outer
        rect = _mm_rect(
            min(x_min, x_max), max(x_min, x_max),
            m.base_top, m.lateral_electrode_top,
        )
        return self._rounded_item(
            rect, m.frame_radius * 0.35, FRAME_FILL, FRAME_PEN, Z_FRAME
        )

    def _build_bottom_electrode(self):
        m = self.metrics
        rect = _mm_rect(
            -m.bottom_electrode_half, m.bottom_electrode_half,
            m.base_top, m.bottom_electrode_top,
        )
        return self._rounded_item(
            rect, m.frame_radius * 0.25,
            FIXED_ELECTRODE_FILL, FIXED_ELECTRODE_PEN, Z_ELECTRODE,
        )

    def _build_lateral_electrode(self, sign):
        m = self.metrics
        x_min = sign * m.lateral_electrode_inner
        x_max = sign * m.side_wall_inner
        rect = _mm_rect(
            min(x_min, x_max), max(x_min, x_max),
            m.lateral_electrode_bottom, m.lateral_electrode_top,
        )
        return self._rounded_item(
            rect, m.frame_radius * 0.3,
            FIXED_ELECTRODE_FILL, FIXED_ELECTRODE_PEN, Z_ELECTRODE,
        )

    def _build_plate(self):
        m = self.metrics
        rect = _mm_rect(-m.plate_radius, m.plate_radius, m.plate_bottom, m.plate_top)
        radius = min(rect.width(), rect.height()) * 0.15
        return self._rounded_item(
            rect, radius, MOVING_PLATE_FILL, MOVING_PLATE_PEN, Z_PLATE
        )

    def _build_face(self):
        m = self.metrics
        rect = _mm_rect(-m.face_radius, m.face_radius, m.plate_top, m.face_top)
        radius = min(rect.width(), rect.height()) * 0.15
        return self._rounded_item(
            rect, radius, FORCE_FACE_FILL, FORCE_FACE_PEN, Z_FACE
        )

    def _build_silicone_support(self, sign):
        """Trapezoid between bottom electrode and plate (outer edge wider)."""
        m = self.metrics
        inner = sign * m.silicone_inner
        outer = sign * m.silicone_outer
        taper = (m.silicone_outer - m.silicone_inner) * 0.30
        bottom_inner = (inner, m.base_top)
        bottom_outer = (outer, m.base_top)
        top_outer = (outer - sign * taper, m.plate_bottom)
        top_inner = (inner + sign * taper, m.plate_bottom)
        polygon = QtGui.QPolygonF([
            scene_point(*bottom_inner),
            scene_point(*bottom_outer),
            scene_point(*top_outer),
            scene_point(*top_inner),
        ])
        item = QtWidgets.QGraphicsPolygonItem(polygon)
        item.setBrush(_fill(SILICONE_FILL, 150))  # translucent: position only
        item.setPen(_outline_pen(SILICONE_PEN))
        item.setZValue(Z_SILICONE)
        self.silicone_items.append(item)

        hatch = QtGui.QPainterPath()
        for fraction in (0.22, 0.46, 0.70):
            start_x = inner + (outer - inner) * fraction
            width_ratio = (top_outer[0] - top_inner[0]) / (outer - inner)
            end_x = top_inner[0] + (outer - inner) * width_ratio * min(fraction + 0.22, 1.0)
            hatch.moveTo(scene_point(start_x, m.base_top))
            hatch.lineTo(scene_point(end_x, m.plate_bottom))
        hatch_item = QtWidgets.QGraphicsPathItem(hatch)
        hatch_item.setBrush(_NO_BRUSH)
        hatch_item.setPen(_outline_pen(SILICONE_PEN))
        hatch_item.setZValue(Z_SILICONE)
        self.silicone_hatch_items.append(hatch_item)
        return item, hatch_item

    def _build_bottom_gap_marker(self):
        """The single bottom gap: two horizontal face lines plus end caps."""
        m = self.metrics
        half = m.bottom_electrode_half
        top_y = m.bottom_electrode_top
        bottom_y = m.plate_bottom
        path = QtGui.QPainterPath()
        for y_mm in (top_y, bottom_y):
            path.moveTo(scene_point(-half, y_mm))
            path.lineTo(scene_point(half, y_mm))
        for x_mm in (-half, half):
            path.moveTo(scene_point(x_mm, top_y))
            path.lineTo(scene_point(x_mm, bottom_y))
        item = QtWidgets.QGraphicsPathItem(path)
        item.setBrush(_NO_BRUSH)
        item.setPen(_gap_pen())
        item.setZValue(Z_GAP)
        return item

    def _build_lateral_gap_marker(self, sign):
        """One side gap: two vertical face lines plus end caps."""
        m = self.metrics
        x_inner = sign * m.plate_radius
        x_outer = sign * m.lateral_electrode_inner
        top_y = m.plate_top
        bottom_y = m.plate_bottom
        path = QtGui.QPainterPath()
        for x_mm in (x_inner, x_outer):
            path.moveTo(scene_point(x_mm, bottom_y))
            path.lineTo(scene_point(x_mm, top_y))
        for y_mm in (bottom_y, top_y):
            path.moveTo(scene_point(x_inner, y_mm))
            path.lineTo(scene_point(x_outer, y_mm))
        item = QtWidgets.QGraphicsPathItem(path)
        item.setBrush(_NO_BRUSH)
        item.setPen(_gap_pen())
        item.setZValue(Z_GAP)
        return item

    # -- labels --------------------------------------------------------------

    def _build_labels(self):
        m = self.metrics
        self._label(
            "right", m.span * 0.09, "受力面",
            (m.face_radius * 0.72, m.span * 0.06),
        )
        self._label(
            "right", -m.span * 0.13, "中央活动板",
            (m.plate_radius * 0.80, -m.span * 0.13),
        )
        self._label(
            "left", -m.span * 0.10, "侧向电容（左右）",
            (-(m.plate_radius + m.gap * 0.5), -m.span * 0.10),
        )
        self._label(
            "left", -m.span * 0.28, "底部电容 ×1",
            (-m.bottom_electrode_half * 0.70, m.bottom_electrode_top + m.gap * 0.5),
        )
        self._label("left", -m.span * 0.44, "前后两侧见俯视")
        self._label(
            "right", -m.span * 0.34, "硅胶支撑（示意）",
            ((m.silicone_inner + m.silicone_outer) / 2.0,
             (m.base_top + m.plate_bottom) / 2.0),
        )
        self._label("left", -m.span * 0.80, IN_SCENE_NOTE)


# --- view --------------------------------------------------------------------

class StructureView(QtWidgets.QGraphicsView):
    """Read-only view for one structure item: never interactive, never grabs."""

    #: Extra margin around the fitted diagram, as a fraction of its size.
    FIT_MARGIN_FRACTION = 0.18
    #: Device pixels kept clear around labels when reserving their space.
    TEXT_FIT_PADDING = 6.0

    def __init__(self, item, parent=None):
        super().__init__(parent)
        if item is None:
            raise ValueError("item must be a QGraphicsItem")
        self._root_item = item
        scene = QtWidgets.QGraphicsScene(self)
        scene.addItem(item)
        self.setScene(scene)
        self.setInteractive(False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.TextAntialiasing
        )
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        apply_canvas_theme(self, "canvas")
        self._fit()

    # -- fitting -------------------------------------------------------------

    def content_rect(self):
        """Geometry bounds, excluding device-sized text items.

        ItemIgnoresTransformations text reports a pixel-sized bounding rect, so
        including it in itemsBoundingRect() would zoom the diagram out to a dot.
        The fit therefore unions the real geometry only.
        """
        rect = QtCore.QRectF()
        stack = list(self._root_item.childItems())
        while stack:
            item = stack.pop()
            if item.flags() & _GRAPHICS_ITEM_FLAG.ItemIgnoresTransformations:
                continue
            mapped = item.mapRectToScene(item.boundingRect())
            if not mapped.isNull():
                rect = mapped if rect.isNull() else rect.united(mapped)
            stack.extend(item.childItems())
        if rect.isNull():
            rect = self._root_item.mapRectToScene(self._root_item.boundingRect())
        return rect

    def _text_items(self):
        """Collect the device-sized (ItemIgnoresTransformations) text items."""
        items = []
        stack = list(self._root_item.childItems())
        while stack:
            item = stack.pop()
            if item.flags() & _GRAPHICS_ITEM_FLAG.ItemIgnoresTransformations:
                items.append(item)
                continue
            stack.extend(item.childItems())
        return items

    def _text_scene_rect(self, scale):
        """Scene-space rect needed to show every label at this view scale.

        Labels ignore view transforms, so their bounding rect is in device
        pixels; dividing by the current scale converts it to scene units that
        the fit rect can reserve.
        """
        rect = QtCore.QRectF()
        if scale <= 0.0:
            return rect
        for item in self._text_items():
            bounds = item.boundingRect()
            if bounds.isEmpty():
                continue
            pos = item.scenePos()
            mapped = QtCore.QRectF(
                pos.x(),
                pos.y(),
                bounds.width() / scale,
                bounds.height() / scale,
            )
            rect = mapped if rect.isNull() else rect.united(mapped)
        return rect

    def _fit(self):
        viewport = self.viewport()
        if viewport is None or viewport.width() <= 0 or viewport.height() <= 0:
            return
        geometry = self.content_rect()
        if geometry.isNull() or geometry.isEmpty():
            return
        margin = self.FIT_MARGIN_FRACTION * max(geometry.width(), geometry.height())
        target = geometry.adjusted(-margin, -margin, margin, margin)
        # Device-sized text must not enlarge the zoom-out (it would shrink the
        # diagram to a dot), but it must not fall outside the viewport either.
        # Fit the geometry first, then reserve the label extents in scene units
        # at the resulting scale and refit; two passes settle in practice.
        self.setSceneRect(target)
        self.fitInView(target, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        for _ in range(3):
            scale = self.transform().m11()
            text_rect = self._text_scene_rect(scale)
            if text_rect.isNull():
                break
            padding = self.TEXT_FIT_PADDING / scale if scale > 0.0 else 0.0
            union = target.united(
                text_rect.adjusted(-padding, -padding, padding, padding)
            )
            if union == target:
                break
            target = union
            self.setSceneRect(target)
            self.fitInView(target, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit()


# --- legend ------------------------------------------------------------------

class StructureLegendWidget(QtWidgets.QWidget):
    """Legend rows: colour swatch plus name and meaning (never colour only)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StructureLegend")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        self.rows = []
        for name, meaning, colour in LEGEND_ITEMS:
            row = QtWidgets.QWidget(self)
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(5)
            swatch = QtWidgets.QFrame(row)
            swatch.setFixedSize(9, 9)
            swatch.setStyleSheet(
                "background: {0}; border: 1px solid {0};".format(qcolor(colour).name())
            )
            name_label = QtWidgets.QLabel(name, row)
            name_label.setFont(mono_font(SCENE_TEXT_POINT_SIZE))
            name_label.setStyleSheet("color: {};".format(TEXT_PRIMARY))
            meaning_label = QtWidgets.QLabel(meaning, row)
            meaning_label.setFont(mono_font(SCENE_TEXT_POINT_SIZE))
            meaning_label.setStyleSheet("color: {};".format(TEXT_MUTED))
            row_layout.addWidget(swatch)
            row_layout.addWidget(name_label)
            row_layout.addWidget(meaning_label, stretch=1)
            layout.addWidget(row)
            self.rows.append((row, name_label, meaning_label))
        self.note_label = QtWidgets.QLabel(LEGEND_NOTE, self)
        self.note_label.setFont(mono_font(SCENE_TEXT_POINT_SIZE))
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet("color: {};".format(TEXT_MUTED))
        layout.addWidget(self.note_label)


# --- array face items --------------------------------------------------------

def _paint_face_highlight(painter, rect, brush, *, square):
    """Draw an inset outline inside rect; skip it in NoBrush (cloud) mode."""
    if brush.style() == _NO_BRUSH:
        return
    inset = FACE_HIGHLIGHT_INSET * min(rect.width(), rect.height())
    inner = rect.adjusted(inset, inset, -inset, -inset)
    if inner.isEmpty():
        return
    colour = with_alpha(TEXT_PRIMARY, 90)
    painter.save()
    painter.setBrush(_NO_BRUSH)
    painter.setPen(QtGui.QPen(colour, 0.0))  # 0 width = cosmetic 1 px
    if square:
        radius_x = inner.width() * 0.18
        radius_y = inner.height() * 0.18
        painter.drawRoundedRect(inner, radius_x, radius_y)
    else:
        painter.drawEllipse(inner)
    painter.restore()


class TaxelFaceRectItem(QtWidgets.QGraphicsRectItem):
    """Array-cell face (rectangle) that keeps the inherited geometry semantics."""

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        _paint_face_highlight(painter, self.rect(), self.brush(), square=True)


class TaxelFaceEllipseItem(QtWidgets.QGraphicsEllipseItem):
    """Array-cell face (circle) that keeps the inherited geometry semantics."""

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        _paint_face_highlight(painter, self.rect(), self.brush(), square=False)


# --- test/inspection helpers -------------------------------------------------

def iter_items(root):
    """Yield root and every descendant item, parents before children."""
    stack = [root]
    while stack:
        item = stack.pop()
        yield item
        stack.extend(item.childItems())


def text_items(root):
    """Return every scene text item below root."""
    return [
        item
        for item in iter_items(root)
        if isinstance(
            item,
            (QtWidgets.QGraphicsSimpleTextItem, QtWidgets.QGraphicsTextItem),
        )
    ]


def text_values(root):
    """Return the strings of every scene text item below root."""
    values = []
    for item in text_items(root):
        if isinstance(item, QtWidgets.QGraphicsSimpleTextItem):
            values.append(item.text())
        else:
            values.append(item.toPlainText())
    return values


def structure_texts(root):
    """Return the scene texts that carry the schematic (non-dimensional) note."""
    return [value for value in text_values(root) if "结构示意" in value]


def dimension_texts(root):
    """Return scene texts that look like a physical dimension (must be empty)."""
    return [value for value in text_values(root) if _DIMENSION_PATTERN.search(value)]
