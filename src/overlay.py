import html
import sys

from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

try:
    import objc
    from AppKit import (
        NSScreenSaverWindowLevel,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowSharingNone,
    )
    _HAS_APPKIT = True
except ImportError:
    _HAS_APPKIT = False


class _DragHandle(QWidget):
    """A widget that moves its top-level window when dragged."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window().pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class OverlaySignals(QObject):
    question_started = pyqtSignal(str)
    text_appended = pyqtSignal(str)
    error_shown = pyqtSignal(str)


class OverlayWindow(QWidget):
    quit_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._history_started = False
        self.signals = OverlaySignals()
        self.signals.question_started.connect(self._on_question_started)
        self.signals.text_appended.connect(self._on_text_appended)
        self.signals.error_shown.connect(self._on_error_shown)

        # ponytail: no Qt.WindowType.Tool here on purpose — Qt maps Tool to a
        # native NSPanel (QNSPanel) and keeps re-asserting its own "tool
        # window" defaults (hidesOnDeactivate=True, a lower window level) on
        # top of ours every time focus changes, which is why the overlay
        # used to vanish the moment another app (the browser) got focus. A
        # plain frameless window (QNSWindow) doesn't get that special-cased
        # treatment, so our native overrides in _configure_native_window
        # actually stick.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Note: no longer WA_TransparentForMouseEvents — the user asked to
        # be able to scroll the history, which needs the overlay to accept
        # wheel events. Trade-off: clicks over the overlay's corner no
        # longer reach the call window underneath it.

        self.label = QLabel("")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setText("Listening…")
        self.label.setWordWrap(True)
        # QLabel defaults to vertically-centered text; once the scroll area
        # below stretches this label to fill the box, centered text left a
        # large dead gap above (and below) short answers. Anchor to the top.
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.label.setStyleSheet(
            "background-color: rgba(20, 20, 20, 200); color: white;"
            "padding: 14px; font-size: 16px;"
        )

        self.close_button = QPushButton("×")
        self.close_button.setFixedSize(22, 22)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setStyleSheet(
            "QPushButton { background-color: rgba(255, 255, 255, 40); color: white;"
            "border: none; border-radius: 11px; font-size: 14px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 90); }"
        )
        self.close_button.clicked.connect(self.quit_requested.emit)

        # The close button used to float directly on the translucent window
        # background with nothing behind it — effectively invisible over an
        # unpredictable desktop. Give it its own opaque header bar instead.
        self.header = _DragHandle()
        self.header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.header.setStyleSheet(
            "background-color: rgba(20, 20, 20, 200);"
            "border-top-left-radius: 10px; border-top-right-radius: 10px;"
        )
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.addStretch()
        header_layout.addWidget(self.close_button)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.label)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "background: transparent;"
            "border-bottom-left-radius: 10px; border-bottom-right-radius: 10px;"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.scroll)
        self.setLayout(layout)

        self.setFixedWidth(480)
        screen = QApplication.primaryScreen()
        available_height = screen.availableGeometry().height() if screen else 900
        self.setFixedHeight(min(500, available_height - 120))
        self.move(60, 60)

    def showEvent(self, event):
        super().showEvent(event)
        # ponytail: pyobjc winId->NSWindow bridging is the most fragile
        # line in this app — if it silently no-ops on a future macOS/PyQt
        # version, screen-share exclusion just won't take effect. Verify
        # with a real screen recording (Task 7 Step 2), not just by reading
        # this code.
        self._configure_native_window()

    def _configure_native_window(self):
        if not _HAS_APPKIT:
            return
        try:
            ns_view = objc.objc_object(c_void_p=int(self.winId()))
            ns_window = ns_view.window()
            if ns_window is not None:
                ns_window.setSharingType_(NSWindowSharingNone)
                # Qt's WindowStaysOnTopHint alone doesn't float above a
                # full-screen call window or follow into other Spaces —
                # bump the native level/collection behavior too.
                ns_window.setLevel_(NSScreenSaverWindowLevel)
                ns_window.setCollectionBehavior_(
                    NSWindowCollectionBehaviorCanJoinAllSpaces
                    | NSWindowCollectionBehaviorFullScreenAuxiliary
                )
                # Qt.WindowType.Tool maps to an NSPanel, which by default
                # hides itself whenever this app isn't the frontmost one —
                # exactly the case during a call, since Meet/Zoom is active.
                ns_window.setHidesOnDeactivate_(False)
        except Exception:
            print(
                "WARNING: native window setup failed; the overlay may appear "
                "in screen recordings/shares or hide behind other windows.",
                file=sys.stderr,
            )

    _LABEL_COLOR = "#7fb2ff"
    _ERROR_COLOR = "#ff8080"

    def _on_question_started(self, question: str):
        prefix = "" if not self._history_started else "<br><br>"
        if not self._history_started:
            self.label.setText("")
            self._history_started = True
        q_html = html.escape(question)
        self.label.setText(
            self.label.text() + f'{prefix}<span style="color:{self._LABEL_COLOR}; '
            f'font-weight:600;">Q:</span> {q_html}<br>'
            f'<span style="color:{self._LABEL_COLOR}; font-weight:600;">A:</span> '
        )
        # New question always jumps to the bottom, even if the user had
        # scrolled up to read earlier history.
        self._scroll_to_bottom()

    def _on_text_appended(self, chunk: str):
        follow = self._is_at_bottom()
        escaped = html.escape(chunk).replace("\n", "<br>")
        self.label.setText(self.label.text() + escaped)
        if follow:
            self._scroll_to_bottom()

    def _on_error_shown(self, message: str):
        follow = self._is_at_bottom()
        escaped = html.escape(message)
        self.label.setText(
            self.label.text() + f'<br><span style="color:{self._ERROR_COLOR};">⚠ {escaped}</span>'
        )
        if follow:
            self._scroll_to_bottom()

    def _is_at_bottom(self) -> bool:
        bar = self.scroll.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    def _scroll_to_bottom(self):
        # Layout hasn't recomputed the new content height yet on this tick,
        # so defer the scroll by one event-loop pass.
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))

    def begin_question(self, question: str):
        self.signals.question_started.emit(question)

    def append_text(self, chunk: str):
        self.signals.text_appended.emit(chunk)

    def show_error(self, message: str):
        self.signals.error_shown.emit(message)
