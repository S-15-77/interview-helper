import os
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from src.diagnostics import OllamaDiagnostics
from src.settings import AppSettings, load_settings
from src.setup_window import AudioDiagnosticThread, SetupWindow
from src.transcriber import TranscriptionResult

_app = QApplication.instance() or QApplication([])


class FakePyAudio:
    def __init__(self, devices=None):
        self.devices = devices or []

    def get_device_count(self):
        return len(self.devices)

    def get_device_info_by_index(self, index):
        return self.devices[index]


def input_device(name="USB Call Audio", index=0):
    return {
        "name": name,
        "maxInputChannels": 2,
        "defaultSampleRate": 48000,
    }


def ready_ollama(model="qwen2.5:3b-instruct"):
    return OllamaDiagnostics(
        reachable=True,
        models=(model, "llama3.2:latest"),
        selected_model=model,
        model_available=True,
        message=f"Ollama is ready with '{model}'.",
    )


def test_setup_form_exposes_and_saves_all_settings(tmp_path):
    path = tmp_path / "settings.json"
    setup = SetupWindow(
        FakePyAudio([input_device(), input_device("Candidate Microphone")]),
        AppSettings(),
        application_profiles=["compiler-role"],
        settings_path=path,
        auto_check=False,
    )
    setup.ollama_model_combo.setCurrentText("llama3.2:latest")
    setup.whisper_model_combo.setCurrentText("small.en")
    setup.whisper_language_combo.setCurrentText("auto")
    setup.answer_style_combo.setCurrentIndex(setup.answer_style_combo.findData("shorter"))
    setup.vad_combo.setCurrentIndex(setup.vad_combo.findData(2))
    setup.silence_timeout_spin.setValue(1600)
    setup.profile_combo.setCurrentIndex(setup.profile_combo.findData("compiler-role"))
    setup.logging_checkbox.setChecked(False)
    setup.retain_candidate_audio_checkbox.setChecked(True)
    setup.overlay_width_spin.setValue(650)
    setup.overlay_height_spin.setValue(700)
    setup.overlay_opacity_spin.setValue(75)
    setup.overlay_font_size_spin.setValue(20)

    assert setup._save_only()
    saved = load_settings(path)

    assert saved.audio_device_name == "USB Call Audio"
    assert saved.ollama_model == "llama3.2:latest"
    assert saved.whisper_model == "small.en"
    assert saved.whisper_language == "auto"
    assert saved.answer_style == "shorter"
    assert saved.vad_aggressiveness == 2
    assert saved.silence_timeout_ms == 1600
    assert saved.default_application_profile == "compiler-role"
    assert not saved.session_logging_enabled
    assert saved.candidate_capture_enabled
    assert saved.candidate_audio_device_name == "Candidate Microphone"
    assert saved.retain_candidate_audio
    assert (saved.overlay_width, saved.overlay_height) == (650, 700)
    assert (saved.overlay_opacity, saved.overlay_font_size) == (75, 20)


def test_health_summary_enables_start_only_for_audio_and_installed_model():
    setup = SetupWindow(
        FakePyAudio([input_device(), input_device("Candidate Microphone")]),
        AppSettings(candidate_capture_enabled=True),
        auto_check=False,
    )

    assert not setup.start_button.isEnabled()
    setup._ollama_checked(ready_ollama())
    assert not setup.start_button.isEnabled()
    setup.consent_checkbox.setChecked(True)

    assert setup.start_button.isEnabled()
    assert "✓ Audio input selected" in setup.health_summary.text()
    assert "✓ Ollama reachable" in setup.health_summary.text()
    assert "✓ Selected Ollama model installed" in setup.health_summary.text()
    assert "✓ Separate candidate microphone selected" in setup.health_summary.text()
    assert "✓ Session consent confirmed" in setup.health_summary.text()
    assert setup.ollama_model_combo.findText("llama3.2:latest") >= 0


def test_missing_audio_device_is_reported_with_a_fix():
    setup = SetupWindow(FakePyAudio(), AppSettings(), auto_check=False)
    setup._ollama_checked(ready_ollama())

    assert not setup.start_button.isEnabled()
    assert "No audio input device is available" in setup.audio_status_label.text()
    assert "microphone permission" in setup.audio_status_label.text()


def test_missing_model_is_visible_and_prevents_start():
    setup = SetupWindow(
        FakePyAudio([input_device()]),
        AppSettings(ollama_model="missing:7b"),
        auto_check=False,
    )
    setup._ollama_checked(
        OllamaDiagnostics(
            reachable=True,
            models=("other:latest",),
            selected_model="missing:7b",
            model_available=False,
            message="Selected model 'missing:7b' is not installed.",
            fix="Run `ollama pull missing:7b`, then refresh models.",
        )
    )

    assert not setup.start_button.isEnabled()
    assert "not installed" in setup.ollama_status_label.text()
    assert "ollama pull missing:7b" in setup.ollama_status_label.text()


def test_candidate_microphone_is_logically_separate_from_interviewer_input():
    setup = SetupWindow(
        FakePyAudio(
            [
                input_device("BlackHole 2ch"),
                input_device("MacBook Microphone"),
                input_device("USB Microphone"),
            ]
        ),
        AppSettings(),
        auto_check=False,
    )

    assert setup.audio_device_combo.currentData() == 0
    assert setup.candidate_device_combo.currentData() in {1, 2}
    assert setup.candidate_device_combo.currentData() != setup.audio_device_combo.currentData()

    setup.audio_device_combo.setCurrentIndex(1)

    assert setup.candidate_device_combo.currentData() != setup.audio_device_combo.currentData()


def test_consent_is_not_remembered_and_retention_change_requires_reconsent():
    setup = SetupWindow(
        FakePyAudio([input_device(), input_device("Candidate Microphone")]),
        AppSettings(retain_candidate_audio=True),
        auto_check=False,
    )

    assert not setup.consent_checkbox.isChecked()
    assert "retained as local WAV files" in setup.consent_details_label.text()
    assert not setup.test_audio_button.isEnabled()
    assert not setup.test_candidate_audio_button.isEnabled()
    setup.consent_checkbox.setChecked(True)
    assert setup.test_audio_button.isEnabled()
    assert setup.test_candidate_audio_button.isEnabled()
    setup.retain_candidate_audio_checkbox.setChecked(False)

    assert not setup.consent_checkbox.isChecked()
    assert "discarded after transcription" in setup.consent_details_label.text()


def test_audio_capture_test_updates_live_meter_and_success_state():
    stream = Mock()
    stream.read.return_value = b"\xff\x1f" * 480
    thread = AudioDiagnosticThread(
        Mock(),
        2,
        duration_seconds=0.03,
    )
    levels = []
    messages = []
    thread.level_changed.connect(levels.append)
    thread.capture_complete.connect(messages.append)

    with patch("src.setup_window.open_capture_stream", return_value=stream):
        thread.run()

    assert levels and levels[-1] > 0
    assert messages == ["Captured 0.03 seconds successfully (peak level 80%)."]
    stream.stop_stream.assert_called_once_with()
    stream.close.assert_called_once_with()


def test_transcription_test_uses_selected_whisper_configuration():
    stream = Mock()
    stream.read.return_value = b"\x00\x00" * 480
    thread = AudioDiagnosticThread(
        Mock(),
        2,
        duration_seconds=0.03,
        transcribe_audio=True,
        whisper_model="small.en",
        whisper_language="auto",
    )
    results = []
    thread.transcription_complete.connect(results.append)
    expected = TranscriptionResult("Detected test question", 0.9, 0.02)

    with (
        patch("src.setup_window.open_capture_stream", return_value=stream),
        patch(
            "src.setup_window.transcribe_with_metadata",
            return_value=expected,
        ) as transcribe,
    ):
        thread.run()

    assert results == [expected]
    transcribe.assert_called_once()
    assert transcribe.call_args.kwargs == {
        "model_name": "small.en",
        "language": "auto",
    }
