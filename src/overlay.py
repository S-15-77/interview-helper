import html
import sys

from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.settings import AppSettings

try:
    import AppKit
    import objc
    from AppKit import (
        NSScreenSaverWindowLevel,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowSharingNone,
    )
    NSEvent = AppKit.NSEvent
    NSEventMaskKeyDown = AppKit.NSEventMaskKeyDown
    NSEventModifierFlagControl = AppKit.NSEventModifierFlagControl
    NSEventModifierFlagOption = AppKit.NSEventModifierFlagOption
    _HAS_APPKIT = True
except (ImportError, AttributeError):
    _HAS_APPKIT = False


VISIBILITY_SHORTCUT_KEY_CODE = 34  # Physical I key on macOS.


def _matches_visibility_shortcut(key_code: int, modifier_flags: int) -> bool:
    if not _HAS_APPKIT:
        return False
    required = NSEventModifierFlagControl | NSEventModifierFlagOption
    return key_code == VISIBILITY_SHORTCUT_KEY_CODE and modifier_flags & required == required


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
    answer_cancelled = pyqtSignal()
    transcript_detected = pyqtSignal(str, float, float, bool)
    transcript_cleared = pyqtSignal()
    visibility_toggle_requested = pyqtSignal()
    error_shown = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    candidate_state_changed = pyqtSignal(str)
    candidate_transcript_detected = pyqtSignal(str, float, float)
    candidate_attempt_ready = pyqtSignal(object)


class OverlayWindow(QWidget):
    quit_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    manual_question_submitted = pyqtSignal(str)
    transcript_correction_submitted = pyqtSignal(str)
    retry_transcription_requested = pyqtSignal()
    listening_paused_changed = pyqtSignal(bool)
    regenerate_requested = pyqtSignal()
    shorter_answer_requested = pyqtSignal()
    more_detail_requested = pyqtSignal()
    profile_changed = pyqtSignal(object)
    retry_candidate_answer_requested = pyqtSignal()

    def __init__(
        self,
        application_profiles: list[str] | None = None,
        settings: AppSettings | None = None,
    ):
        super().__init__()
        settings = settings or AppSettings()
        self._history_started = False
        self._plain_history_parts: list[str] = []
        self._current_answer_chunks: list[str] = []
        self._global_key_monitor = None
        self._local_key_monitor = None
        self._visibility_fallback_shortcut: QShortcut | None = None
        self._answer_font_size = settings.overlay_font_size
        self.signals = OverlaySignals()
        self.signals.question_started.connect(self._on_question_started)
        self.signals.text_appended.connect(self._on_text_appended)
        self.signals.answer_cancelled.connect(self._on_answer_cancelled)
        self.signals.transcript_detected.connect(self._on_transcript_detected)
        self.signals.transcript_cleared.connect(self._on_transcript_cleared)
        self.signals.visibility_toggle_requested.connect(self._toggle_visibility)
        self.signals.error_shown.connect(self._on_error_shown)
        self.signals.status_changed.connect(self._on_status_changed)
        self.signals.candidate_state_changed.connect(self._on_candidate_state_changed)
        self.signals.candidate_transcript_detected.connect(
            self._on_candidate_transcript_detected
        )
        self.signals.candidate_attempt_ready.connect(self._on_candidate_attempt_ready)
        self._candidate_attempts = []

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
        self.label.setText("Starting…")
        self.label.setWordWrap(True)
        # QLabel defaults to vertically-centered text; once the scroll area
        # below stretches this label to fill the box, centered text left a
        # large dead gap above (and below) short answers. Anchor to the top.
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._apply_answer_style()

        self.close_button = QPushButton("×")
        self.close_button.setFixedSize(22, 22)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setStyleSheet(
            "QPushButton { background-color: rgba(255, 255, 255, 40); color: white;"
            "border: none; border-radius: 11px; font-size: 14px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 90); }"
        )
        self.close_button.clicked.connect(self.quit_requested.emit)

        self.profile_label = QLabel("Profile")
        self.profile_label.setStyleSheet(
            "color: rgba(255, 255, 255, 180); font-size: 12px;"
        )

        self.profile_combo = QComboBox()
        self.profile_combo.setToolTip(
            "Only the selected application's résumé, JD, and notes are sent to the model."
        )
        self.profile_combo.addItem("Default", None)
        for profile_name in application_profiles or []:
            self.profile_combo.addItem(profile_name.replace("-", " "), profile_name)
        self.profile_combo.setStyleSheet(
            "QComboBox { background-color: rgba(255, 255, 255, 35); color: white;"
            "border: 1px solid rgba(255, 255, 255, 45); border-radius: 5px;"
            "padding: 3px 7px; font-size: 12px; }"
            "QComboBox QAbstractItemView { background-color: #252525; color: white; }"
        )
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        if settings.default_application_profile:
            profile_index = self.profile_combo.findData(
                settings.default_application_profile
            )
            if profile_index >= 0:
                self.profile_combo.setCurrentIndex(profile_index)

        self.status_label = QLabel("Starting…")
        self.status_label.setStyleSheet(
            "color: rgba(255, 255, 255, 165); font-size: 11px;"
        )

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setToolTip(
            "Cancel the active operation and discard questions waiting in the queue."
        )
        self.cancel_button.setStyleSheet(
            "QPushButton { background-color: rgba(255, 128, 128, 55); color: white;"
            "border: none; border-radius: 5px; padding: 3px 7px; font-size: 11px; }"
            "QPushButton:hover { background-color: rgba(255, 128, 128, 100); }"
            "QPushButton:disabled { color: rgba(255, 255, 255, 80);"
            "background-color: rgba(255, 255, 255, 20); }"
        )
        self.cancel_button.clicked.connect(self.cancel_requested.emit)

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
        header_layout.addWidget(self.profile_label)
        header_layout.addWidget(self.profile_combo)
        header_layout.addStretch()
        header_layout.addWidget(self.status_label)
        header_layout.addWidget(self.cancel_button)
        header_layout.addWidget(self.close_button)

        self.transcript_label = QLabel("Detected question")
        self.transcript_label.setStyleSheet(
            "color: rgba(255, 255, 255, 175); font-size: 11px;"
        )

        self.transcript_input = QLineEdit()
        self.transcript_input.setPlaceholderText("No clear speech detected — type the question…")
        self.transcript_input.setStyleSheet(
            "QLineEdit { background-color: rgba(255, 255, 255, 28); color: white;"
            "border: 1px solid rgba(127, 178, 255, 110); border-radius: 5px;"
            "padding: 5px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #7fb2ff; }"
        )
        self.transcript_input.returnPressed.connect(self._submit_transcript_correction)

        self.regenerate_button = QPushButton("Regenerate")
        self.regenerate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.regenerate_button.setToolTip(
            "Cancel the active answer and generate again from the edited question."
        )
        self.regenerate_button.setStyleSheet(
            "QPushButton { background-color: #376ea8; color: white; border: none;"
            "border-radius: 5px; padding: 5px 8px; font-size: 11px; }"
            "QPushButton:hover { background-color: #4784c2; }"
        )
        self.regenerate_button.clicked.connect(self._submit_transcript_correction)

        self.retry_transcription_button = QPushButton("Retry STT")
        self.retry_transcription_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_transcription_button.setToolTip(
            "Run speech transcription again on the most recent captured question."
        )
        self.retry_transcription_button.setStyleSheet(
            "QPushButton { background-color: rgba(255, 255, 255, 35); color: white;"
            "border: 1px solid rgba(255, 255, 255, 45); border-radius: 5px;"
            "padding: 5px 8px; font-size: 11px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 65); }"
        )
        self.retry_transcription_button.clicked.connect(
            self.retry_transcription_requested.emit
        )

        self.transcript_panel = QWidget()
        self.transcript_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.transcript_panel.setStyleSheet(
            "background-color: rgba(28, 38, 52, 225);"
        )
        transcript_layout = QVBoxLayout(self.transcript_panel)
        transcript_layout.setContentsMargins(8, 6, 8, 7)
        transcript_layout.setSpacing(4)
        transcript_layout.addWidget(self.transcript_label)
        transcript_controls = QHBoxLayout()
        transcript_controls.setContentsMargins(0, 0, 0, 0)
        transcript_controls.setSpacing(5)
        transcript_controls.addWidget(self.transcript_input)
        transcript_controls.addWidget(self.regenerate_button)
        transcript_controls.addWidget(self.retry_transcription_button)
        transcript_layout.addLayout(transcript_controls)
        self.transcript_panel.setVisible(False)

        control_button_style = (
            "QPushButton { background-color: rgba(255, 255, 255, 30); color: white;"
            "border: 1px solid rgba(255, 255, 255, 38); border-radius: 5px;"
            "padding: 4px 7px; font-size: 10px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 60); }"
            "QPushButton:checked { background-color: #805a2b; }"
        )

        self.pause_button = QPushButton("Pause")
        self.pause_button.setCheckable(True)
        self.pause_button.setToolTip("Pause/resume call-audio capture (Ctrl+Option+P).")
        self.pause_button.setStyleSheet(control_button_style)
        self.pause_button.toggled.connect(self._on_pause_toggled)

        self.regenerate_answer_button = QPushButton("Regenerate")
        self.regenerate_answer_button.setToolTip(
            "Generate the last answer again (Ctrl+Option+R)."
        )
        self.regenerate_answer_button.setStyleSheet(control_button_style)
        self.regenerate_answer_button.clicked.connect(self.regenerate_requested.emit)

        self.shorter_button = QPushButton("Shorter")
        self.shorter_button.setStyleSheet(control_button_style)
        self.shorter_button.clicked.connect(self.shorter_answer_requested.emit)

        self.more_detail_button = QPushButton("More Detail")
        self.more_detail_button.setStyleSheet(control_button_style)
        self.more_detail_button.clicked.connect(self.more_detail_requested.emit)

        self.clear_history_button = QPushButton("Clear")
        self.clear_history_button.setStyleSheet(control_button_style)
        self.clear_history_button.clicked.connect(self._clear_history)

        self.copy_answer_button = QPushButton("Copy Answer")
        self.copy_answer_button.setStyleSheet(control_button_style)
        self.copy_answer_button.clicked.connect(self._copy_answer)

        self.copy_session_button = QPushButton("Copy Session")
        self.copy_session_button.setStyleSheet(control_button_style)
        self.copy_session_button.clicked.connect(self._copy_session)

        self.view_button = QPushButton("View")
        self.view_button.setCheckable(True)
        self.view_button.setStyleSheet(control_button_style)
        self.view_button.clicked.connect(self._toggle_view_settings)

        self.controls_panel = QWidget()
        self.controls_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.controls_panel.setStyleSheet("background-color: rgba(20, 20, 20, 220);")
        controls_layout = QVBoxLayout(self.controls_panel)
        controls_layout.setContentsMargins(6, 4, 6, 5)
        controls_layout.setSpacing(3)
        primary_controls = QHBoxLayout()
        primary_controls.setContentsMargins(0, 0, 0, 0)
        primary_controls.setSpacing(4)
        primary_controls.addWidget(self.pause_button)
        primary_controls.addWidget(self.regenerate_answer_button)
        primary_controls.addWidget(self.shorter_button)
        primary_controls.addWidget(self.more_detail_button)
        primary_controls.addWidget(self.clear_history_button)
        secondary_controls = QHBoxLayout()
        secondary_controls.setContentsMargins(0, 0, 0, 0)
        secondary_controls.setSpacing(4)
        secondary_controls.addWidget(self.copy_answer_button)
        secondary_controls.addWidget(self.copy_session_button)
        secondary_controls.addWidget(self.view_button)
        secondary_controls.addStretch()
        shortcut_hint = QLabel("Show/hide: Ctrl+Option+I")
        shortcut_hint.setStyleSheet(
            "color: rgba(255, 255, 255, 110); font-size: 9px;"
        )
        secondary_controls.addWidget(shortcut_hint)
        controls_layout.addLayout(primary_controls)
        controls_layout.addLayout(secondary_controls)

        self.candidate_state_label = QLabel("Candidate mic: waiting for a question.")
        self.candidate_state_label.setStyleSheet(
            "color: rgba(180, 220, 255, 190); font-size: 10px;"
        )
        self.candidate_state_label.setWordWrap(True)
        self.candidate_state_label.setVisible(settings.candidate_capture_enabled)
        controls_layout.addWidget(self.candidate_state_label)

        self.width_slider = self._view_slider(360, 800, settings.overlay_width)
        self.height_slider = self._view_slider(300, 900, settings.overlay_height)
        self.opacity_slider = self._view_slider(35, 100, settings.overlay_opacity)
        self.font_size_slider = self._view_slider(
            12,
            28,
            settings.overlay_font_size,
        )
        self.width_slider.valueChanged.connect(self.setFixedWidth)
        self.height_slider.valueChanged.connect(self.setFixedHeight)
        self.opacity_slider.valueChanged.connect(
            lambda value: self.setWindowOpacity(value / 100)
        )
        self.font_size_slider.valueChanged.connect(self._set_answer_font_size)

        self.view_settings_panel = QWidget()
        self.view_settings_panel.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        self.view_settings_panel.setStyleSheet(
            "background-color: rgba(24, 24, 24, 230); color: white;"
        )
        view_layout = QGridLayout(self.view_settings_panel)
        view_layout.setContentsMargins(8, 5, 8, 7)
        view_layout.setHorizontalSpacing(7)
        view_layout.setVerticalSpacing(3)
        for row, (name, slider) in enumerate(
            (
                ("Width", self.width_slider),
                ("Height", self.height_slider),
                ("Opacity", self.opacity_slider),
                ("Font", self.font_size_slider),
            )
        ):
            label = QLabel(name)
            label.setStyleSheet("color: rgba(255, 255, 255, 165); font-size: 10px;")
            view_layout.addWidget(label, row, 0)
            view_layout.addWidget(slider, row, 1)
        self.view_settings_panel.setVisible(False)

        self.candidate_feedback_panel = QWidget()
        self.candidate_feedback_panel.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        self.candidate_feedback_panel.setStyleSheet(
            "background-color: rgba(22, 34, 30, 235); color: white;"
        )
        candidate_layout = QVBoxLayout(self.candidate_feedback_panel)
        candidate_layout.setContentsMargins(8, 6, 8, 7)
        candidate_layout.setSpacing(4)
        candidate_header = QHBoxLayout()
        candidate_title = QLabel("Your practice response")
        candidate_title.setStyleSheet(
            "color: #8bd49c; font-size: 11px; font-weight: 600;"
        )
        self.candidate_attempt_combo = QComboBox()
        self.candidate_attempt_combo.setMinimumWidth(150)
        self.candidate_attempt_combo.currentIndexChanged.connect(
            self._render_candidate_attempt
        )
        self.retry_candidate_button = QPushButton("Try Again")
        self.retry_candidate_button.setStyleSheet(control_button_style)
        self.retry_candidate_button.clicked.connect(
            self.retry_candidate_answer_requested.emit
        )
        candidate_header.addWidget(candidate_title)
        candidate_header.addStretch()
        candidate_header.addWidget(self.candidate_attempt_combo)
        candidate_header.addWidget(self.retry_candidate_button)
        candidate_layout.addLayout(candidate_header)

        self.candidate_transcript_label = QLabel("")
        self.candidate_transcript_label.setWordWrap(True)
        self.candidate_transcript_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.candidate_transcript_label.setStyleSheet(
            "color: rgba(255, 255, 255, 190); font-size: 11px;"
        )
        candidate_layout.addWidget(self.candidate_transcript_label)

        self.candidate_feedback_view = QTextBrowser()
        self.candidate_feedback_view.setOpenExternalLinks(False)
        self.candidate_feedback_view.setMaximumHeight(230)
        self.candidate_feedback_view.setStyleSheet(
            "QTextBrowser { background: rgba(0, 0, 0, 35); color: white; "
            "border: none; padding: 4px; font-size: 11px; }"
        )
        candidate_layout.addWidget(self.candidate_feedback_view)
        self.candidate_feedback_panel.setVisible(False)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.label)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "background: transparent;"
        )

        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Paste or type a question shown on screen…")
        self.question_input.setClearButtonEnabled(True)
        self.question_input.setStyleSheet(
            "QLineEdit { background-color: rgba(255, 255, 255, 28); color: white;"
            "border: 1px solid rgba(255, 255, 255, 45); border-radius: 6px;"
            "padding: 7px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #7fb2ff; }"
        )
        self.question_input.returnPressed.connect(self._submit_manual_question)

        self.generate_button = QPushButton("Generate")
        self.generate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_button.setStyleSheet(
            "QPushButton { background-color: #376ea8; color: white; border: none;"
            "border-radius: 6px; padding: 7px 10px; font-size: 12px; }"
            "QPushButton:hover { background-color: #4784c2; }"
        )
        self.generate_button.clicked.connect(self._submit_manual_question)

        self.input_panel = QWidget()
        self.input_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.input_panel.setStyleSheet(
            "background-color: rgba(20, 20, 20, 220);"
            "border-bottom-left-radius: 10px; border-bottom-right-radius: 10px;"
        )
        input_layout = QHBoxLayout(self.input_panel)
        input_layout.setContentsMargins(8, 7, 8, 8)
        input_layout.addWidget(self.question_input)
        input_layout.addWidget(self.generate_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.transcript_panel)
        layout.addWidget(self.controls_panel)
        layout.addWidget(self.view_settings_panel)
        layout.addWidget(self.candidate_feedback_panel)
        layout.addWidget(self.scroll)
        layout.addWidget(self.input_panel)
        self.setLayout(layout)

        self.setFixedWidth(settings.overlay_width)
        self.setWindowOpacity(settings.overlay_opacity / 100)
        screen = QApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen else None
        available_height = geometry.height() if geometry else 900
        initial_height = min(settings.overlay_height, max(300, available_height - 120))
        self.setFixedHeight(initial_height)
        self.height_slider.setValue(initial_height)
        # Top-center, near the built-in webcam — easier to glance at than a
        # corner position, and can still be dragged anywhere via the header.
        if geometry:
            self.move(geometry.x() + (geometry.width() - self.width()) // 2, geometry.y() + 20)
        else:
            self.move(60, 60)
        self._setup_keyboard_shortcuts()

    @staticmethod
    def _view_slider(minimum: int, maximum: int, value: int) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        return slider

    def _apply_answer_style(self):
        self.label.setStyleSheet(
            "background-color: rgba(20, 20, 20, 200); color: white;"
            f"padding: 14px; font-size: {self._answer_font_size}px;"
        )

    def _set_answer_font_size(self, value: int):
        self._answer_font_size = value
        self._apply_answer_style()

    def _setup_keyboard_shortcuts(self):
        self._pause_shortcut = QShortcut(QKeySequence("Ctrl+Alt+P"), self)
        self._pause_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._pause_shortcut.activated.connect(self.pause_button.toggle)

        self._cancel_shortcut = QShortcut(QKeySequence("Escape"), self)
        self._cancel_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._cancel_shortcut.activated.connect(self.cancel_requested.emit)

        self._regenerate_shortcut = QShortcut(QKeySequence("Ctrl+Alt+R"), self)
        self._regenerate_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._regenerate_shortcut.activated.connect(self.regenerate_requested.emit)

        if not _HAS_APPKIT:
            self._visibility_fallback_shortcut = QShortcut(
                QKeySequence("Ctrl+Alt+I"),
                self,
            )
            self._visibility_fallback_shortcut.setContext(
                Qt.ShortcutContext.ApplicationShortcut
            )
            self._visibility_fallback_shortcut.activated.connect(
                self.signals.visibility_toggle_requested.emit
            )

    def showEvent(self, event):
        super().showEvent(event)
        # ponytail: pyobjc winId->NSWindow bridging is the most fragile
        # line in this app — if it silently no-ops on a future macOS/PyQt
        # version, screen-share exclusion just won't take effect. Verify
        # with a real screen recording (Task 7 Step 2), not just by reading
        # this code.
        self._configure_native_window()
        self._install_global_visibility_shortcut()

    def _install_global_visibility_shortcut(self):
        if not _HAS_APPKIT or self._global_key_monitor is not None:
            return

        def handle_global_key(event):
            if _matches_visibility_shortcut(
                int(event.keyCode()),
                int(event.modifierFlags()),
            ):
                self.signals.visibility_toggle_requested.emit()

        def handle_local_key(event):
            if _matches_visibility_shortcut(
                int(event.keyCode()),
                int(event.modifierFlags()),
            ):
                self.signals.visibility_toggle_requested.emit()
                return None
            return event

        try:
            self._global_key_monitor = (
                NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                    NSEventMaskKeyDown,
                    handle_global_key,
                )
            )
            self._local_key_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown,
                handle_local_key,
            )
            self._global_key_handler = handle_global_key
            self._local_key_handler = handle_local_key
        except Exception as exc:
            print(
                f"WARNING: global visibility shortcut unavailable: {exc}",
                file=sys.stderr,
            )

    def stop_global_visibility_shortcut(self):
        if not _HAS_APPKIT:
            return
        for monitor in (self._global_key_monitor, self._local_key_monitor):
            if monitor is not None:
                NSEvent.removeMonitor_(monitor)
        self._global_key_monitor = None
        self._local_key_monitor = None

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()

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
        except Exception as exc:
            print(
                "WARNING: native window setup failed; the overlay may appear "
                f"in screen recordings/shares or hide behind other windows: {exc}",
                file=sys.stderr,
            )

    _LABEL_COLOR = "#7fb2ff"
    _ERROR_COLOR = "#ff8080"

    def _on_question_started(self, question: str):
        prefix = "" if not self._history_started else "<br><br>"
        plain_prefix = "" if not self._history_started else "\n\n"
        if not self._history_started:
            self.label.setText("")
            self._history_started = True
        self._plain_history_parts.append(f"{plain_prefix}Q: {question}\nA: ")
        self._current_answer_chunks = []
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
        self._plain_history_parts.append(chunk)
        self._current_answer_chunks.append(chunk)
        escaped = html.escape(chunk).replace("\n", "<br>")
        self.label.setText(self.label.text() + escaped)
        if follow:
            self._scroll_to_bottom()

    def _on_answer_cancelled(self):
        follow = self._is_at_bottom()
        cancellation = "\n[Answer cancelled.]"
        self._plain_history_parts.append(cancellation)
        self._current_answer_chunks.append(cancellation)
        self.label.setText(
            self.label.text()
            + '<br><span style="color:rgba(255,255,255,140);"><i>Answer cancelled.</i></span>'
        )
        if follow:
            self._scroll_to_bottom()

    def _on_transcript_detected(
        self,
        question: str,
        confidence: float,
        no_speech_probability: float,
        is_reliable: bool,
    ):
        self.transcript_input.setText(question)
        confidence_percent = round(confidence * 100)
        no_speech_percent = round(no_speech_probability * 100)
        quality = "Ready" if is_reliable else "Review before generating"
        color = "#8bd49c" if is_reliable else self._ERROR_COLOR
        self.transcript_label.setText(
            f'<span style="color:{color};">{quality}</span> • '
            f"confidence {confidence_percent}% • no-speech {no_speech_percent}%"
        )
        self.regenerate_button.setEnabled(bool(question.strip()))
        self.transcript_panel.setVisible(True)

    def _on_transcript_cleared(self):
        self.transcript_input.clear()
        self.transcript_panel.setVisible(False)

    def _on_error_shown(self, message: str):
        follow = self._is_at_bottom()
        error_text = f"\n[Error: {message}]"
        self._plain_history_parts.append(error_text)
        self._current_answer_chunks.append(error_text)
        escaped = html.escape(message)
        self.label.setText(
            self.label.text() + f'<br><span style="color:{self._ERROR_COLOR};">⚠ {escaped}</span>'
        )
        if follow:
            self._scroll_to_bottom()

    def _on_status_changed(self, message: str):
        self.status_label.setText(message)
        busy = message.startswith(
            (
                "Transcribing",
                "Retrying transcription",
                "Generating",
                "Manual question queued",
                "Corrected question queued",
                "Regenerating",
                "Generating shorter",
                "Generating detailed",
                "Cancelling",
            )
        )
        self.cancel_button.setEnabled(busy)
        self.clear_history_button.setEnabled(not busy)
        # Startup/listening statuses should not erase an active Q&A history.
        if not self._history_started:
            self.label.setText(html.escape(message))

    def _on_candidate_state_changed(self, message: str):
        self.candidate_state_label.setText(message)

    def _on_candidate_transcript_detected(
        self,
        transcript: str,
        confidence: float,
        no_speech_probability: float,
    ):
        text = transcript.strip() or "No clear candidate speech was detected."
        self.candidate_transcript_label.setText(
            "<b>Detected response:</b> "
            + html.escape(text)
            + f" <span style='color:rgba(255,255,255,130);'>"
            f"(confidence {confidence:.0%}, no-speech {no_speech_probability:.0%})</span>"
        )
        self.candidate_feedback_panel.setVisible(True)

    @staticmethod
    def _score_label(value) -> str:
        return "—" if value is None else f"{value}/5"

    def _on_candidate_attempt_ready(self, attempt):
        self._candidate_attempts.append(attempt)
        self.candidate_attempt_combo.blockSignals(True)
        question_label = attempt.question.strip().replace("\n", " ")
        if len(question_label) > 22:
            question_label = question_label[:21] + "…"
        self.candidate_attempt_combo.addItem(
            f"{question_label} · #{attempt.attempt_number}"
        )
        self.candidate_attempt_combo.setCurrentIndex(
            self.candidate_attempt_combo.count() - 1
        )
        self.candidate_attempt_combo.blockSignals(False)
        self._render_candidate_attempt(len(self._candidate_attempts) - 1)
        self.candidate_feedback_panel.setVisible(True)

    def _render_candidate_attempt(self, index: int):
        if not 0 <= index < len(self._candidate_attempts):
            return
        attempt = self._candidate_attempts[index]
        feedback = attempt.feedback
        metrics = attempt.metrics
        self.candidate_transcript_label.setText(
            "<b>Detected response:</b> "
            + html.escape(attempt.transcript or "No clear speech detected.")
        )
        score_names = (
            ("Relevance", "relevance"),
            ("STAR", "star_completeness"),
            ("Clarity", "clarity_structure"),
            ("Conciseness", "conciseness"),
            ("Technical", "technical_correctness"),
            ("Profile support", "profile_support"),
        )
        scores = " • ".join(
            f"{label} {self._score_label(feedback.scores.get(key))}"
            for label, key in score_names
        )
        filler_detail = ", ".join(
            f"{name} ×{count}" for name, count in metrics.filler_counts
        ) or "none"
        repeated = ", ".join(metrics.repeated_phrases) or "none"
        facts = "".join(f"<li>{html.escape(item)}</li>" for item in feedback.facts)
        improvements = "".join(
            f"<li>{html.escape(item)}</li>" for item in feedback.improvements
        )
        unsupported = "".join(
            f"<li>{html.escape(item)}</li>" for item in feedback.unsupported_claims
        )
        tradeoffs = "".join(
            f"<li>{html.escape(item)}</li>" for item in feedback.missing_tradeoffs
        )
        comparison = (
            f"<p><b>Compared with attempt {attempt.comparison.previous_attempt_number}:</b> "
            f"{html.escape(attempt.comparison.summary)}</p>"
            if attempt.comparison
            else "<p><b>Comparison:</b> First attempt for this question.</p>"
        )
        support_section = (
            f"<p><b>Claims not supported by the supplied profile:</b></p><ul>{unsupported}</ul>"
            if unsupported
            else "<p><b>Profile check:</b> No unsupported claims were flagged.</p>"
        )
        tradeoff_section = (
            f"<p><b>Missing technical trade-offs:</b></p><ul>{tradeoffs}</ul>"
            if tradeoffs
            else ""
        )
        self.candidate_feedback_view.setHtml(
            f"<p><b>Scores:</b> {scores}</p>"
            f"<p><b>Measured:</b> {metrics.duration_seconds:.1f}s • "
            f"{metrics.words_per_minute} wpm • fillers: {html.escape(filler_detail)} • "
            f"repeated phrases: {html.escape(repeated)}</p>"
            f"<p><b>Observed facts:</b></p><ul>{facts}</ul>"
            f"{support_section}{tradeoff_section}"
            f"<p><b>Improvements:</b></p><ol>{improvements}</ol>"
            f"<p><b>Improved example:</b><br>{html.escape(feedback.improved_answer).replace(chr(10), '<br>')}</p>"
            f"{comparison}"
            f"<p style='color:#aaa;'>Analysis source: {html.escape(feedback.source)}</p>"
        )

    def _on_pause_toggled(self, paused: bool):
        self.pause_button.setText("Resume" if paused else "Pause")
        self.listening_paused_changed.emit(paused)

    def _toggle_view_settings(self, visible: bool):
        self.view_settings_panel.setVisible(visible)

    def _clear_history(self):
        self._history_started = False
        self._plain_history_parts.clear()
        self._current_answer_chunks.clear()
        self.label.setText(html.escape(self.status_label.text()))

    def _copy_answer(self):
        QApplication.clipboard().setText("".join(self._current_answer_chunks).strip())

    def _copy_session(self):
        QApplication.clipboard().setText("".join(self._plain_history_parts).strip())

    def _submit_manual_question(self):
        question = self.question_input.text().strip()
        if not question:
            return
        self.question_input.clear()
        self.manual_question_submitted.emit(question)

    def _submit_transcript_correction(self):
        question = self.transcript_input.text().strip()
        if question:
            self.transcript_correction_submitted.emit(question)

    def _on_profile_changed(self):
        self.profile_changed.emit(self.selected_profile())

    def selected_profile(self) -> str | None:
        return self.profile_combo.currentData()

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

    def show_cancelled(self):
        self.signals.answer_cancelled.emit()

    def show_transcript(
        self,
        question: str,
        confidence: float,
        no_speech_probability: float,
        is_reliable: bool,
    ):
        self.signals.transcript_detected.emit(
            question,
            confidence,
            no_speech_probability,
            is_reliable,
        )

    def clear_transcript(self):
        self.signals.transcript_cleared.emit()

    def show_error(self, message: str):
        self.signals.error_shown.emit(message)

    def show_status(self, message: str):
        self.signals.status_changed.emit(message)

    def show_candidate_state(self, message: str):
        self.signals.candidate_state_changed.emit(message)

    def show_candidate_transcript(
        self,
        transcript: str,
        confidence: float,
        no_speech_probability: float,
    ):
        self.signals.candidate_transcript_detected.emit(
            transcript,
            confidence,
            no_speech_probability,
        )

    def show_candidate_attempt(self, attempt):
        self.signals.candidate_attempt_ready.emit(attempt)
