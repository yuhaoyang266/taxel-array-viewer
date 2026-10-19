"""Tests for the schematic structure items (offscreen Qt, no GUI window).

Covers spec section 5.3 items 1-10 for test_sensor_structure_items.py plus a few
implementation-safety checks (single y flip, face paint containment, view fit).
Every assertion is about the schematic contract: no physical dimension may leak
into the diagram, nothing may take mouse input, and the five gaps stay countable.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import dataclasses
import unittest

from PySide6 import QtCore, QtGui, QtWidgets

import sensor_structure_items as ssi


SPAN_MM = 10.0
_APP = None


def setUpModule():
    global _APP
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _metrics():
    return ssi.StructureMetrics.from_diameter(SPAN_MM)


def _structure_items():
    metrics = _metrics()
    return [ssi.TopViewStructureItem(metrics), ssi.CrossSectionItem(metrics)]


class StructureMetricsTests(unittest.TestCase):
    def test_metrics_scale_with_the_nominal_width(self):
        small = ssi.StructureMetrics.from_diameter(10.0)
        large = ssi.StructureMetrics.from_diameter(20.0)
        names = [field.name for field in dataclasses.fields(small)]
        self.assertEqual(names, [field.name for field in dataclasses.fields(large)])
        for name in names:
            self.assertAlmostEqual(
                getattr(large, name), 2.0 * getattr(small, name), places=9,
                msg="field {} must scale with the nominal width".format(name),
            )
        # gap/span is invariant across widths (schematic constant, not a size)
        self.assertAlmostEqual(small.gap / small.span, large.gap / large.span, places=12)
        self.assertAlmostEqual(
            small.gap / small.span, ssi.SCHEMATIC_GAP_FRACTION, places=12
        )

    def test_gap_geometry_is_consistent(self):
        m = _metrics()
        self.assertAlmostEqual(
            m.plate_bottom - m.bottom_electrode_top, m.gap, places=12,
            msg="bottom plate-to-electrode distance must equal the schematic gap",
        )
        self.assertAlmostEqual(
            m.lateral_electrode_inner - m.plate_diameter / 2.0, m.gap, places=12,
            msg="cross-section side gap must equal the schematic gap",
        )
        self.assertAlmostEqual(
            m.lateral_pad_inner - m.plate_diameter / 2.0, m.gap, places=12,
            msg="top-view lateral pad gap must equal the schematic gap",
        )
        self.assertAlmostEqual(
            m.lateral_pad_outer, m.frame_outer / 2.0 - m.frame_ring, places=12,
            msg="lateral pads must end exactly at the frame ring inner edge",
        )

    def test_metrics_reject_non_positive_or_non_finite_widths(self):
        for bad in (0.0, -1.0, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                ssi.StructureMetrics.from_diameter(bad)


class StructureSafetyTests(unittest.TestCase):
    def test_no_item_accepts_mouse_buttons(self):
        flag = QtWidgets.QGraphicsItem.GraphicsItemFlag
        for root in _structure_items():
            items = list(ssi.iter_items(root))
            self.assertGreater(len(items), 10)
            for item in items:
                self.assertEqual(
                    item.acceptedMouseButtons(), QtCore.Qt.MouseButton.NoButton,
                    msg="{} must not accept mouse buttons".format(type(item).__name__),
                )
                flags = item.flags()
                self.assertFalse(
                    bool(flags & flag.ItemIsSelectable),
                    msg="{} must not be selectable".format(type(item).__name__),
                )
                self.assertFalse(
                    bool(flags & flag.ItemIsMovable),
                    msg="{} must not be movable".format(type(item).__name__),
                )
                self.assertFalse(
                    bool(flags & flag.ItemIsFocusable),
                    msg="{} must not be focusable".format(type(item).__name__),
                )

    def test_structure_view_is_not_interactive(self):
        view = ssi.StructureView(ssi.TopViewStructureItem(_metrics()))
        self.assertFalse(view.isInteractive())
        self.assertTrue(
            view.testAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        )
        self.assertIsNotNone(view.scene())
        self.assertGreater(len(view.scene().items()), 0)


class StructureTextTests(unittest.TestCase):
    def test_no_physical_dimension_is_printed(self):
        for root in _structure_items():
            self.assertEqual(
                ssi.dimension_texts(root), [],
                msg="scene text must never carry a physical dimension",
            )
            self.assertTrue(
                any("结构示意" in value for value in ssi.text_values(root)),
                msg="every view must carry the schematic note",
            )

    def test_structure_texts_use_the_design_wording(self):
        # Design document line 151, verbatim.
        expected = "结构示意，非尺寸图；当前仅显示三轴力，未接入间隙/电容读数"
        self.assertEqual(ssi.SCHEMATIC_NOTE, expected)
        self.assertEqual(ssi.IN_SCENE_NOTE, "结构示意，非尺寸图")
        for root in _structure_items():
            self.assertIn(ssi.IN_SCENE_NOTE, ssi.structure_texts(root))
        for caption in (
            ssi.TOP_VIEW_CAPTION,
            ssi.SECTION_CAPTION,
            ssi.LEGEND_NOTE,
            ssi.SCHEMATIC_NOTE,
        ):
            self.assertIn("示意", caption)
            self.assertNotRegex(caption, r"\d")


class TopViewTests(unittest.TestCase):
    def setUp(self):
        self.metrics = _metrics()
        self.item = ssi.TopViewStructureItem(self.metrics)

    def test_show_four_lateral_gaps_and_the_hidden_bottom_capacitor(self):
        self.assertEqual(len(self.item.lateral_gap_markers), ssi.LATERAL_GAP_COUNT)
        self.assertEqual(len(self.item.lateral_gap_markers), 4)
        self.assertIsNotNone(self.item.bottom_cap_hidden_marker)
        values = ssi.text_values(self.item)
        self.assertTrue(any("×4" in value for value in values))
        self.assertTrue(any("底部电容 ×1" in value for value in values))
        self.assertEqual(ssi.BOTTOM_GAP_COUNT, 1)


class CrossSectionTests(unittest.TestCase):
    def setUp(self):
        self.metrics = _metrics()
        self.item = ssi.CrossSectionItem(self.metrics)

    def test_shows_one_bottom_gap_and_two_side_gaps(self):
        self.assertIsNotNone(self.item.bottom_gap_marker)
        self.assertEqual(len(self.item.lateral_gap_markers), 2)
        self.assertIn("前后两侧见俯视", self.item.lateral_gap_note)
        values = ssi.text_values(self.item)
        self.assertIn("前后两侧见俯视", values)
        self.assertIn("侧向电容（左右）", values)
        self.assertTrue(any("底部电容 ×1" in value for value in values))
        # Both silicone supports must really be in the drawn hierarchy (fill and
        # hatch): a built-but-unparented item would silently vanish.
        self.assertEqual(len(self.item.silicone_items), 2)
        self.assertEqual(len(self.item.silicone_hatch_items), 2)
        for entry in self.item.silicone_items + self.item.silicone_hatch_items:
            self.assertIs(entry.parentItem(), self.item)


class ZOrderTests(unittest.TestCase):
    def test_z_order_separates_part_identity_layers(self):
        chain = (
            ssi.Z_FRAME,
            ssi.Z_ELECTRODE,
            ssi.Z_SILICONE,
            ssi.Z_GAP,
            ssi.Z_PLATE,
            ssi.Z_FACE,
            ssi.Z_LEADER,
            ssi.Z_TEXT,
        )
        self.assertEqual(list(chain), sorted(chain))
        self.assertEqual(len(set(chain)), len(chain))
        for root in _structure_items():
            self.assertEqual(root.plate_item.zValue(), ssi.Z_PLATE)
            self.assertEqual(root.face_item.zValue(), ssi.Z_FACE)
            for marker in root.lateral_gap_markers:
                self.assertEqual(marker.zValue(), ssi.Z_GAP)
        top = ssi.TopViewStructureItem(_metrics())
        self.assertEqual(top.frame_item.zValue(), ssi.Z_FRAME)
        self.assertEqual(top.bottom_cap_hidden_marker.zValue(), ssi.Z_GAP)
        for item in top.electrode_items:
            self.assertEqual(item.zValue(), ssi.Z_ELECTRODE)
        section = ssi.CrossSectionItem(_metrics())
        self.assertEqual(section.base_item.zValue(), ssi.Z_FRAME)
        self.assertEqual(section.bottom_gap_marker.zValue(), ssi.Z_GAP)
        for item in section.electrode_items:
            self.assertEqual(item.zValue(), ssi.Z_ELECTRODE)
        for item in section.silicone_items:
            self.assertEqual(item.zValue(), ssi.Z_SILICONE)


class SceneMappingTests(unittest.TestCase):
    def test_scene_helpers_flip_y_exactly_once(self):
        self.assertEqual(ssi.scene_point(2.0, 3.0), QtCore.QPointF(2.0, -3.0))
        self.assertEqual(ssi.scene_point(-1.5, -0.5), QtCore.QPointF(-1.5, 0.5))
        self.assertEqual(
            ssi.scene_rect(0.0, 1.0, 4.0, 2.0),
            QtCore.QRectF(-2.0, -2.0, 4.0, 2.0),
        )
        self.assertEqual(
            ssi.scene_rect(1.0, -2.0, 2.0, 6.0),
            QtCore.QRectF(0.0, -1.0, 2.0, 6.0),
        )


class FaceItemTests(unittest.TestCase):
    def test_face_items_keep_rect_and_paint_inside_it(self):
        rect_item = ssi.TaxelFaceRectItem(0.0, 0.0, 10.0, 10.0)
        self.assertEqual(rect_item.rect(), QtCore.QRectF(0.0, 0.0, 10.0, 10.0))
        # A cosmetic 0-width pen keeps the inherited bounding rect equal to rect().
        rect_item.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 0.0))
        self.assertEqual(rect_item.boundingRect(), rect_item.rect())
        # The inherited pen half-width rule is untouched (nothing overridden).
        rect_item.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1.0))
        self.assertEqual(
            rect_item.boundingRect(),
            rect_item.rect().adjusted(-0.5, -0.5, 0.5, 0.5),
        )
        ellipse_item = ssi.TaxelFaceEllipseItem(1.0, 2.0, 8.0, 6.0)
        self.assertEqual(ellipse_item.rect(), QtCore.QRectF(1.0, 2.0, 8.0, 6.0))
        ellipse_item.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 0.0))
        self.assertEqual(ellipse_item.boundingRect(), ellipse_item.rect())
        # Subclass identity is preserved for the array view isinstance checks.
        self.assertIsInstance(rect_item, QtWidgets.QGraphicsRectItem)
        self.assertIsInstance(ellipse_item, QtWidgets.QGraphicsEllipseItem)
        # Only paint() is allowed to be overridden.
        for cls, base in (
            (ssi.TaxelFaceRectItem, QtWidgets.QGraphicsRectItem),
            (ssi.TaxelFaceEllipseItem, QtWidgets.QGraphicsEllipseItem),
        ):
            self.assertIn("paint", vars(cls))
            for name in ("boundingRect", "shape", "mousePressEvent",
                         "mouseReleaseEvent", "mouseMoveEvent", "mouseDragEvent"):
                self.assertNotIn(name, vars(cls))

    def test_face_highlight_stays_inside_the_rect_and_skips_nobrush(self):
        image = QtGui.QImage(40, 40, QtGui.QImage.Format.Format_ARGB32)
        option = QtWidgets.QStyleOptionGraphicsItem()

        image.fill(QtCore.Qt.GlobalColor.transparent)
        decorated = ssi.TaxelFaceRectItem(0.0, 0.0, 20.0, 20.0)
        decorated.setBrush(QtGui.QBrush(QtGui.QColor("#F2C744")))
        decorated.setPen(QtGui.QPen(QtGui.QColor("#B9880E"), 1.0))
        painter = QtGui.QPainter(image)
        try:
            decorated.paint(painter, option, None)
        finally:
            painter.end()
        self.assertEqual(decorated.rect(), QtCore.QRectF(0.0, 0.0, 20.0, 20.0))
        inside_drawn = False
        for x in range(0, 21):
            for y in range(0, 21):
                if image.pixelColor(x, y).alpha() > 0:
                    inside_drawn = True
                    break
            if inside_drawn:
                break
        self.assertTrue(inside_drawn)
        for x in range(21, 40):
            for y in range(21, 40):
                self.assertEqual(
                    image.pixelColor(x, y).alpha(), 0,
                    msg="highlight must stay inside the item rect",
                )

        # Cloud (NoBrush) mode: paint() must only run the inherited baseline.
        clean = QtGui.QImage(40, 40, QtGui.QImage.Format.Format_ARGB32)
        clean.fill(QtCore.Qt.GlobalColor.transparent)
        plain = ssi.TaxelFaceRectItem(0.0, 0.0, 20.0, 20.0)
        plain.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        plain.setPen(QtCore.Qt.PenStyle.NoPen)
        painter = QtGui.QPainter(clean)
        try:
            plain.paint(painter, option, None)
        finally:
            painter.end()
        for x in range(0, 40):
            for y in range(0, 40):
                self.assertEqual(clean.pixelColor(x, y).alpha(), 0)


class ViewFitTests(unittest.TestCase):
    def test_view_fits_the_geometry_not_the_text_pixels(self):
        view = ssi.StructureView(ssi.CrossSectionItem(_metrics()))
        view.resize(320, 240)
        view._fit()
        content = view.content_rect()
        self.assertFalse(content.isNull())
        self.assertLess(content.width(), 3.0 * SPAN_MM)
        self.assertLess(content.height(), 3.0 * SPAN_MM)
        self.assertGreater(view.transform().m11(), 5.0)


class LegendTests(unittest.TestCase):
    def test_legend_pairs_every_colour_with_text(self):
        legend = ssi.StructureLegendWidget()
        self.assertEqual(len(legend.rows), len(ssi.LEGEND_ITEMS))
        names = []
        meanings = []
        for row, name_label, meaning_label in legend.rows:
            self.assertIs(row.parentWidget(), legend)
            names.append(name_label.text())
            meanings.append(meaning_label.text())
        for name, meaning, _colour in ssi.LEGEND_ITEMS:
            self.assertIn(name, names)
            self.assertIn(meaning, meanings)
        self.assertEqual(legend.note_label.text(), ssi.LEGEND_NOTE)


class GeometryUncertaintyTests(unittest.TestCase):
    def test_note_separates_envelope_face_and_pitch(self):
        text = ssi.GEOMETRY_UNCERTAINTY_NOTE
        for token in ("本体外轮廓", "白色受力面", "单元中心距", "装配间隙"):
            self.assertIn(token, text)
        self.assertIn("尚未确认", text)
        self.assertNotIn("无物理间隙", text)


class StageAFixTests(unittest.TestCase):
    """Regression tests for review findings on the Stage A diagram."""

    def test_moving_plate_is_square_while_the_face_stays_round(self):
        root = ssi.TopViewStructureItem(ssi.StructureMetrics.from_diameter(SPAN_MM))
        plate = root.plate_item
        plate_rect = plate.mapRectToScene(plate.boundingRect())
        self.assertAlmostEqual(plate_rect.width(), plate_rect.height(), places=6)
        self.assertAlmostEqual(plate_rect.width(), root.metrics.plate_diameter, places=6)
        self.assertNotIsInstance(plate, QtWidgets.QGraphicsEllipseItem)
        self.assertIsInstance(root.face_item, QtWidgets.QGraphicsEllipseItem)

    def test_four_lateral_gaps_line_up_with_the_square_plate_edges(self):
        root = ssi.TopViewStructureItem(ssi.StructureMetrics.from_diameter(SPAN_MM))
        self.assertEqual(len(root.lateral_gap_markers), ssi.LATERAL_GAP_COUNT)
        for marker in root.lateral_gap_markers:
            bounds = marker.mapRectToScene(marker.boundingRect())
            self.assertGreater(bounds.width(), 0.0)
            self.assertGreater(bounds.height(), 0.0)

    def test_labels_fit_inside_the_default_panel_viewport(self):
        import math

        for factory in (ssi.TopViewStructureItem, ssi.CrossSectionItem):
            view = ssi.StructureView(factory(ssi.StructureMetrics.from_diameter(SPAN_MM)))
            self.addCleanup(view.close)
            view.resize(500, 210)  # matches the real panel view size
            view.show()
            _APP.processEvents()
            view._fit()
            _APP.processEvents()

            viewport = view.viewport().rect().adjusted(-1, -1, 1, 1)
            for item in view._text_items():
                bounds = item.boundingRect()
                top_left = view.mapFromScene(item.scenePos())
                rect = QtCore.QRect(
                    top_left,
                    QtCore.QSize(math.ceil(bounds.width()), math.ceil(bounds.height())),
                )
                self.assertTrue(
                    viewport.contains(rect),
                    msg=f"label {item.text()!r} clipped: {rect} not in {viewport}",
                )


if __name__ == "__main__":
    unittest.main()
