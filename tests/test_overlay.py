import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import src.overlay as overlay_module
from src.coaching import CandidateAttempt, CoachingFeedback, SpeechMetrics
from src.overlay import OverlayWindow
from src.settings import AppSettings

_app = QApplication.instance() or QApplication([])


def test_saved_overlay_appearance_and_profile_are_applied():
    overlay = OverlayWindow(
        ["compiler-role", "ml-role"],
        settings=AppSettings(
            overlay_width=610,
            overlay_height=620,
            overlay_opacity=78,
            overlay_font_size=21,
            default_application_profile="ml-role",
        ),
    )

    assert overlay.width() == 610
    assert overlay.height() == 620
    # Qt stores native window opacity as an 8-bit value.
    assert overlay.windowOpacity() == pytest.approx(0.78, abs=0.005)
    assert overlay._answer_font_size == 21
    assert overlay.selected_profile() == "ml-role"


def test_candidate_feedback_shows_scores_grounding_and_attempt_comparison():
    overlay = OverlayWindow(settings=AppSettings(candidate_capture_enabled=True))
    feedback = CoachingFeedback(
        question_type="technical",
        scores={
            "relevance": 4,
            "star_completeness": None,
            "clarity_structure": 3,
            "conciseness": 4,
            "technical_correctness": 4,
            "profile_support": 5,
        },
        facts=("The response named O(n) complexity.",),
        unsupported_claims=("The scale claim is not in the supplied profile.",),
        missing_tradeoffs=("It did not compare memory use.",),
        improvements=("State the trade-off.", "Lead with the approach."),
        improved_answer="Use a hash map, grounded in the response.",
    )
    attempt = CandidateAttempt(
        question="Explain the algorithm",
        transcript="I would use a hash map.",
        attempt_number=1,
        transcription_confidence=0.92,
        metrics=SpeechMetrics(12.0, 6, 30, (("um", 1),), ()),
        feedback=feedback,
    )

    overlay.show_candidate_attempt(attempt)

    rendered = overlay.candidate_feedback_view.toPlainText()
    assert overlay.candidate_feedback_panel.isVisibleTo(overlay)
    assert "Relevance 4/5" in rendered
    assert "STAR —" in rendered
    assert "Observed facts" in rendered
    assert "Claims not supported by the supplied profile" in rendered
    assert "Missing technical trade-offs" in rendered
    assert "State the trade-off" in rendered
    assert "Improved example" in rendered
    assert overlay.candidate_attempt_combo.count() == 1


def test_try_again_requests_another_candidate_attempt():
    overlay = OverlayWindow(settings=AppSettings(candidate_capture_enabled=True))
    requested = []
    overlay.retry_candidate_answer_requested.connect(lambda: requested.append(True))

    overlay.retry_candidate_button.click()

    assert requested == [True]


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
    assert overlay.status_label.text() == "Loading speech model…"

    overlay._on_question_started("Tell me about yourself")
    history = overlay.label.text()
    overlay._on_status_changed("Listening…")

    assert overlay.label.text() == history
    assert overlay.status_label.text() == "Listening…"


def test_busy_status_controls_cancel_button():
    overlay = OverlayWindow()

    overlay._on_status_changed("Transcribing…")
    assert overlay.cancel_button.isEnabled()

    overlay._on_status_changed("Generating…")
    assert overlay.cancel_button.isEnabled()

    overlay._on_status_changed("Listening • first 100ms • total 1.2s")
    assert not overlay.cancel_button.isEnabled()


def test_cancel_button_emits_request():
    overlay = OverlayWindow()
    requested = []
    overlay.cancel_requested.connect(lambda: requested.append(True))
    overlay._on_status_changed("Generating…")

    QTest.mouseClick(overlay.cancel_button, Qt.MouseButton.LeftButton)

    assert requested == [True]


def test_cancelled_answer_is_marked_in_history():
    overlay = OverlayWindow()
    overlay._on_question_started("Explain a hash map")

    overlay._on_answer_cancelled()

    assert "Answer cancelled." in overlay.label.text()


def test_pause_button_emits_pause_and_resume_states():
    overlay = OverlayWindow()
    states = []
    overlay.listening_paused_changed.connect(states.append)

    QTest.mouseClick(overlay.pause_button, Qt.MouseButton.LeftButton)
    assert overlay.pause_button.text() == "Resume"

    QTest.mouseClick(overlay.pause_button, Qt.MouseButton.LeftButton)
    assert overlay.pause_button.text() == "Pause"
    assert states == [True, False]


def test_answer_action_buttons_emit_requests():
    overlay = OverlayWindow()
    requested = []
    overlay.regenerate_requested.connect(lambda: requested.append("regenerate"))
    overlay.shorter_answer_requested.connect(lambda: requested.append("shorter"))
    overlay.more_detail_requested.connect(lambda: requested.append("detail"))

    QTest.mouseClick(overlay.regenerate_answer_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(overlay.shorter_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(overlay.more_detail_button, Qt.MouseButton.LeftButton)

    assert requested == ["regenerate", "shorter", "detail"]


def test_copy_answer_and_session_use_plain_text_clipboard():
    overlay = OverlayWindow()
    overlay._on_question_started("Question one?")
    overlay._on_text_appended("Answer one.")
    overlay._on_question_started("Question two?")
    overlay._on_text_appended("Answer two.")

    QTest.mouseClick(overlay.copy_answer_button, Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == "Answer two."

    QTest.mouseClick(overlay.copy_session_button, Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == (
        "Q: Question one?\nA: Answer one.\n\nQ: Question two?\nA: Answer two."
    )


def test_clear_history_resets_visible_and_plain_text_history():
    overlay = OverlayWindow()
    overlay._on_status_changed("Listening…")
    overlay._on_question_started("Question?")
    overlay._on_text_appended("Answer.")

    QTest.mouseClick(overlay.clear_history_button, Qt.MouseButton.LeftButton)

    assert overlay.label.text() == "Listening…"
    assert not overlay._history_started
    assert overlay._plain_history_parts == []
    assert overlay._current_answer_chunks == []


def test_view_sliders_adjust_overlay_dimensions_opacity_and_font():
    overlay = OverlayWindow()

    overlay.width_slider.setValue(620)
    overlay.height_slider.setValue(640)
    overlay.opacity_slider.setValue(70)
    overlay.font_size_slider.setValue(21)

    assert overlay.width() == 620
    assert overlay.height() == 640
    assert overlay.windowOpacity() == pytest.approx(0.7, abs=0.01)
    assert "font-size: 21px" in overlay.label.styleSheet()


def test_view_button_toggles_view_settings_panel():
    overlay = OverlayWindow()
    assert overlay.view_settings_panel.isHidden()

    QTest.mouseClick(overlay.view_button, Qt.MouseButton.LeftButton)

    assert not overlay.view_settings_panel.isHidden()


def test_pause_cancel_and_regenerate_keyboard_shortcuts_emit_actions():
    overlay = OverlayWindow()
    actions = []
    overlay.listening_paused_changed.connect(
        lambda paused: actions.append("pause" if paused else "resume")
    )
    overlay.cancel_requested.connect(lambda: actions.append("cancel"))
    overlay.regenerate_requested.connect(lambda: actions.append("regenerate"))

    overlay._pause_shortcut.activated.emit()
    overlay._cancel_shortcut.activated.emit()
    overlay._regenerate_shortcut.activated.emit()

    assert actions == ["pause", "cancel", "regenerate"]


def test_global_visibility_shortcut_matches_only_control_option_i(monkeypatch):
    monkeypatch.setattr(overlay_module, "_HAS_APPKIT", True)
    monkeypatch.setattr(overlay_module, "NSEventModifierFlagControl", 1, raising=False)
    monkeypatch.setattr(overlay_module, "NSEventModifierFlagOption", 2, raising=False)

    assert overlay_module._matches_visibility_shortcut(34, 3)
    assert not overlay_module._matches_visibility_shortcut(34, 1)
    assert not overlay_module._matches_visibility_shortcut(35, 3)


def test_global_visibility_shortcut_registers_and_unregisters_monitors(monkeypatch):
    calls = []

    class FakeNSEvent:
        @staticmethod
        def addGlobalMonitorForEventsMatchingMask_handler_(mask, handler):
            calls.append(("global", mask, handler))
            return "global-token"

        @staticmethod
        def addLocalMonitorForEventsMatchingMask_handler_(mask, handler):
            calls.append(("local", mask, handler))
            return "local-token"

        @staticmethod
        def removeMonitor_(token):
            calls.append(("remove", token))

    monkeypatch.setattr(overlay_module, "_HAS_APPKIT", True)
    monkeypatch.setattr(overlay_module, "NSEvent", FakeNSEvent, raising=False)
    monkeypatch.setattr(overlay_module, "NSEventMaskKeyDown", 99, raising=False)
    overlay = OverlayWindow()

    overlay._install_global_visibility_shortcut()
    overlay.stop_global_visibility_shortcut()

    assert [(kind, value) for kind, value, *_ in calls[:2]] == [
        ("global", 99),
        ("local", 99),
    ]
    assert ("remove", "global-token") in calls
    assert ("remove", "local-token") in calls


def test_detected_transcript_is_visible_with_confidence():
    overlay = OverlayWindow()

    overlay._on_transcript_detected("What is IR?", 0.82, 0.06, True)

    assert not overlay.transcript_panel.isHidden()
    assert overlay.transcript_input.text() == "What is IR?"
    assert "Ready" in overlay.transcript_label.text()
    assert "confidence 82%" in overlay.transcript_label.text()
    assert "no-speech 6%" in overlay.transcript_label.text()


def test_low_confidence_transcript_requests_review():
    overlay = OverlayWindow()

    overlay._on_transcript_detected("Was that IR?", 0.2, 0.75, False)

    assert "Review before generating" in overlay.transcript_label.text()
    assert overlay.regenerate_button.isEnabled()


def test_edited_transcript_can_be_submitted_for_regeneration():
    overlay = OverlayWindow()
    submitted = []
    overlay.transcript_correction_submitted.connect(submitted.append)
    overlay._on_transcript_detected("What is eye are?", 0.3, 0.2, False)
    overlay.transcript_input.setText("  What is IR?  ")

    QTest.mouseClick(overlay.regenerate_button, Qt.MouseButton.LeftButton)

    assert submitted == ["What is IR?"]


def test_retry_transcription_button_emits_request():
    overlay = OverlayWindow()
    requested = []
    overlay.retry_transcription_requested.connect(lambda: requested.append(True))
    overlay._on_transcript_detected("Was that IR?", 0.3, 0.2, False)

    QTest.mouseClick(
        overlay.retry_transcription_button,
        Qt.MouseButton.LeftButton,
    )

    assert requested == [True]


def test_transcript_preview_can_be_cleared():
    overlay = OverlayWindow()
    overlay._on_transcript_detected("What is IR?", 0.9, 0.05, True)

    overlay._on_transcript_cleared()

    assert overlay.transcript_panel.isHidden()
    assert overlay.transcript_input.text() == ""


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
