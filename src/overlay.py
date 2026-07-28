import sys

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

try:
    import objc
    from AppKit import NSWindowSharingTypeNone
    _HAS_APPKIT = True
except ImportError:
    _HAS_APPKIT = False


class OverlaySignals(QObject):
    text_appended = pyqtSignal(str)
    error_shown = pyqtSignal(str)
    cleared = pyqtSignal()


class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = OverlaySignals()
        self.signals.text_appended.connect(self._on_text_appended)
        self.signals.error_shown.connect(self._on_error_shown)
        self.signals.cleared.connect(self._on_cleared)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.label = QLabel("")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setText("Listening…")
        self.label.setWordWrap(True)
        self.label.setStyleSheet(
            "background-color: rgba(20, 20, 20, 200); color: white;"
            "padding: 14px; border-radius: 10px; font-size: 15px;"
        )
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)
        self.setFixedWidth(420)
        self.move(60, 60)

    def showEvent(self, event):
        super().showEvent(event)
        # ponytail: pyobjc winId->NSWindow bridging is the most fragile
        # line in this app — if it silently no-ops on a future macOS/PyQt
        # version, screen-share exclusion just won't take effect. Verify
        # with a real screen recording (Task 7 Step 2), not just by reading
        # this code.
        self._exclude_from_screen_capture()

    def _exclude_from_screen_capture(self):
        if not _HAS_APPKIT:
            return
        try:
            ns_view = objc.objc_object(c_void_p=int(self.winId()))
            ns_window = ns_view.window()
            if ns_window is not None:
                ns_window.setSharingType_(NSWindowSharingTypeNone)
        except Exception:
            print(
                "WARNING: screen-capture exclusion failed; the overlay WILL appear "
                "in screen recordings/shares.",
                file=sys.stderr,
            )

    def _on_text_appended(self, chunk: str):
        self.label.setText(self.label.text() + chunk)
        self.adjustSize()

    def _on_error_shown(self, message: str):
        self.label.setText(f"⚠ {message}")
        self.adjustSize()

    def _on_cleared(self):
        self.label.setText("")
        self.adjustSize()

    def append_text(self, chunk: str):
        self.signals.text_appended.emit(chunk)

    def show_error(self, message: str):
        self.signals.error_shown.emit(message)

    def clear(self):
        self.signals.cleared.emit()
