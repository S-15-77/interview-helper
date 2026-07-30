from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from src.overlay import OverlayWindow

_app = QApplication.instance() or QApplication([])


def test_drag_header_moves_window():
    overlay = OverlayWindow()
    overlay.move(60, 60)
    start_pos = overlay.pos()

    header = overlay.header
    press_point = QPoint(header.width() // 2, header.height() // 2)
    QTest.mousePress(header, Qt.MouseButton.LeftButton, pos=press_point)
    QTest.mouseMove(header, press_point + QPoint(40, 25))
    QTest.mouseRelease(header, Qt.MouseButton.LeftButton, pos=press_point + QPoint(40, 25))

    end_pos = overlay.pos()
    assert end_pos == start_pos + QPoint(40, 25)


def test_label_text_is_selectable():
    overlay = OverlayWindow()
    flags = overlay.label.textInteractionFlags()
    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
