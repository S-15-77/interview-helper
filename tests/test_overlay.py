import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import src.overlay as overlay_module
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


def test_status_updates_before_history_but_does_not_erase_answers():
    overlay = OverlayWindow()

    overlay._on_status_changed("Loading speech model…")
    assert overlay.label.text() == "Loading speech model…"

    overlay._on_question_started("Tell me about yourself")
    history = overlay.label.text()
    overlay._on_status_changed("Listening…")

    assert overlay.label.text() == history


def test_manual_question_is_trimmed_submitted_and_cleared():
    overlay = OverlayWindow()
    submitted = []
    overlay.manual_question_submitted.connect(submitted.append)
    overlay.question_input.setText("  What is intermediate representation?  ")

    QTest.keyClick(overlay.question_input, Qt.Key.Key_Return)

    assert submitted == ["What is intermediate representation?"]
    assert overlay.question_input.text() == ""


def test_profile_selector_emits_internal_profile_name():
    overlay = OverlayWindow(["compiler-role", "ml-role"])
    selected = []
    overlay.profile_changed.connect(selected.append)

    overlay.profile_combo.setCurrentIndex(1)

    assert overlay.selected_profile() == "compiler-role"
    assert selected == ["compiler-role"]


def test_native_window_is_marked_private(monkeypatch):
    calls = []

    class FakeNativeWindow:
        def setSharingType_(self, value):
            calls.append(("sharing", value))

        def setLevel_(self, value):
            calls.append(("level", value))

        def setCollectionBehavior_(self, value):
            calls.append(("collection", value))

        def setHidesOnDeactivate_(self, value):
            calls.append(("hides", value))

    native_window = FakeNativeWindow()

    class FakeNativeView:
        def window(self):
            return native_window

    class FakeObjc:
        @staticmethod
        def objc_object(*, c_void_p):
            assert isinstance(c_void_p, int)
            return FakeNativeView()

    monkeypatch.setattr(overlay_module, "_HAS_APPKIT", True)
    monkeypatch.setattr(overlay_module, "objc", FakeObjc())
    monkeypatch.setattr(overlay_module, "NSWindowSharingNone", 0, raising=False)
    monkeypatch.setattr(overlay_module, "NSScreenSaverWindowLevel", 1000, raising=False)
    monkeypatch.setattr(
        overlay_module, "NSWindowCollectionBehaviorCanJoinAllSpaces", 1, raising=False
    )
    monkeypatch.setattr(
        overlay_module, "NSWindowCollectionBehaviorFullScreenAuxiliary", 2, raising=False
    )

    overlay = OverlayWindow()
    overlay._configure_native_window()

    assert ("sharing", 0) in calls
    assert ("level", 1000) in calls
    assert ("collection", 3) in calls
    assert ("hides", False) in calls
