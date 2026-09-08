from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.audio_capture import FRAME_MS, FRAME_SIZE, SAMPLE_RATE, open_capture_stream
from src.diagnostics import (
    AudioInputDevice,
    OllamaDiagnostics,
    audio_level_percent,
    check_ollama,
    list_audio_input_devices,
    preferred_audio_device_index,
)
from src.settings import (
    ANSWER_STYLES,
    DEFAULT_SETTINGS_PATH,
    AppSettings,
    SettingsError,
    save_settings,
)
from src.transcriber import TranscriptionResult, transcribe_with_metadata


class AudioDiagnosticThread(QThread):
    level_changed = pyqtSignal(int)
    capture_complete = pyqtSignal(str)
    transcription_complete = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        pa,
        device_index: int,
        *,
        duration_seconds: float,
        transcribe_audio: bool = False,
        whisper_model: str = "base.en",
        whisper_language: str = "en",
    ):
        super().__init__()
        self.pa = pa
        self.device_index = device_index
        self.duration_seconds = duration_seconds
        self.transcribe_audio = transcribe_audio
        self.whisper_model = whisper_model
        self.whisper_language = whisper_language

    def run(self):
        stream = None
        frames: list[bytes] = []
        peak_level = 0
        try:
            stream = open_capture_stream(self.pa, self.device_index)
            frame_count = max(1, round(self.duration_seconds * 1000 / FRAME_MS))
            for _ in range(frame_count):
                if self.isInterruptionRequested():
                    return
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
                frames.append(frame)
                level = audio_level_percent(frame)
                peak_level = max(peak_level, level)
                self.level_changed.emit(level)
            if self.isInterruptionRequested():
                return
            captured = b"".join(frames)
            if self.transcribe_audio:
                import numpy as np

                samples = np.frombuffer(captured, dtype="<i2").astype(np.float32)
                samples /= 32768.0
                result = transcribe_with_metadata(
                    samples,
                    SAMPLE_RATE,
                    model_name=self.whisper_model,
                    language=self.whisper_language,
                )
                self.transcription_complete.emit(result)
            else:
                self.capture_complete.emit(
                    f"Captured {self.duration_seconds:g} seconds successfully "
                    f"(peak level {peak_level}%)."
                )
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                finally:
                    stream.close()


class OllamaCheckThread(QThread):
    checked = pyqtSignal(object)

    def __init__(self, base_url: str, selected_model: str):
        super().__init__()
        self.base_url = base_url
        self.selected_model = selected_model

    def run(self):
        self.checked.emit(check_ollama(self.base_url, self.selected_model))


class SetupWindow(QDialog):
    """Startup settings and dependency diagnostics for the local app."""

    ANSWER_STYLE_LABELS = {
        "default": "Balanced",
        "shorter": "Short (under 90 words)",
        "more_detail": "More detail",
    }

    def __init__(
        self,
        pa,
        settings: AppSettings | None = None,
        *,
        application_profiles: list[str] | None = None,
        settings_path: Path = DEFAULT_SETTINGS_PATH,
        settings_load_error: str | None = None,
        auto_check: bool = True,
    ):
        super().__init__()
        self.pa = pa
        self.settings_path = Path(settings_path)
        self.settings = settings or AppSettings()
        self.devices: list[AudioInputDevice] = []
        self.ollama_diagnostics: OllamaDiagnostics | None = None
        self._audio_thread: AudioDiagnosticThread | None = None
        self._ollama_thread: OllamaCheckThread | None = None
        self._audio_test_passed = False
        self._transcription_test_passed = False
        self._diagnostic_is_transcription = False
        self._settings_load_error = settings_load_error

        self.setWindowTitle("Interview Overlay Setup")
        self.setMinimumSize(680, 700)

        title = QLabel("Interview Overlay Setup")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        intro = QLabel(
            "Choose local models and an audio input, test the dependencies, then "
            "start the practice overlay. Settings stay on this computer."
        )
        intro.setWordWrap(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(self._build_audio_group())
        content_layout.addWidget(self._build_model_group())
        content_layout.addWidget(self._build_behavior_group(application_profiles or []))
        content_layout.addWidget(self._build_overlay_group())
        content_layout.addStretch()
        health_group = self._build_health_group()

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)

        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self._save_only)
        self.refresh_button = QPushButton("Refresh Diagnostics")
        self.refresh_button.clicked.connect(self.refresh_ollama)
        self.start_button = QPushButton("Save && Start")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._save_and_start)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addStretch()
        buttons.addWidget(self.save_button)
        buttons.addWidget(cancel_button)
        buttons.addWidget(self.start_button)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(scroll)
        layout.addWidget(health_group)
        layout.addLayout(buttons)

        self._populate_devices()
        self._load_form(self.settings)
        self._connect_change_signals()
        self._refresh_health()
        if auto_check:
            QTimer.singleShot(0, self.refresh_ollama)

    def _build_audio_group(self) -> QGroupBox:
        group = QGroupBox("Audio capture")
        layout = QGridLayout(group)
        self.audio_device_combo = QComboBox()
        self.audio_status_label = QLabel("Select an input device, then test it.")
        self.audio_status_label.setWordWrap(True)
        self.audio_meter = QProgressBar()
        self.audio_meter.setRange(0, 100)
        self.audio_meter.setValue(0)
        self.audio_meter.setFormat("Input level %p%")
        self.test_audio_button = QPushButton("Test Audio Capture (3 sec)")
        self.test_audio_button.clicked.connect(self.test_audio_capture)
        self.test_transcription_button = QPushButton("Test Transcription (5 sec)")
        self.test_transcription_button.clicked.connect(self.test_transcription)
        self.transcription_output = QPlainTextEdit()
        self.transcription_output.setReadOnly(True)
        self.transcription_output.setMaximumHeight(70)
        self.transcription_output.setPlaceholderText(
            "Detected text from the transcription test appears here."
        )

        layout.addWidget(QLabel("Input device"), 0, 0)
        layout.addWidget(self.audio_device_combo, 0, 1, 1, 2)
        layout.addWidget(self.audio_meter, 1, 0, 1, 3)
        layout.addWidget(self.test_audio_button, 2, 0)
        layout.addWidget(self.test_transcription_button, 2, 1)
        layout.addWidget(self.audio_status_label, 3, 0, 1, 3)
        layout.addWidget(self.transcription_output, 4, 0, 1, 3)
        return group

    def _build_model_group(self) -> QGroupBox:
        group = QGroupBox("Local models")
        form = QFormLayout(group)
        self.ollama_url_input = QLineEdit()
        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.setEditable(True)
        self.whisper_model_combo = QComboBox()
        self.whisper_model_combo.setEditable(True)
        self.whisper_model_combo.addItems(
            ["tiny.en", "base.en", "small.en", "medium.en"]
        )
        self.whisper_language_combo = QComboBox()
        self.whisper_language_combo.setEditable(True)
        self.whisper_language_combo.addItems(["en", "auto", "fr", "es", "de"])
        self.ollama_status_label = QLabel("Ollama has not been checked yet.")
        self.ollama_status_label.setWordWrap(True)

        form.addRow("Ollama URL", self.ollama_url_input)
        form.addRow("Ollama model", self.ollama_model_combo)
        form.addRow("Whisper model", self.whisper_model_combo)
        form.addRow("Whisper language", self.whisper_language_combo)
        form.addRow("Status", self.ollama_status_label)
        return group

    def _build_behavior_group(self, application_profiles: list[str]) -> QGroupBox:
        group = QGroupBox("Answers and listening")
        form = QFormLayout(group)
        self.answer_style_combo = QComboBox()
        for style in ANSWER_STYLES:
            self.answer_style_combo.addItem(self.ANSWER_STYLE_LABELS[style], style)
        self.vad_combo = QComboBox()
        for value, label in (
            (0, "0 — least aggressive"),
            (1, "1 — relaxed"),
            (2, "2 — balanced"),
            (3, "3 — most aggressive"),
        ):
            self.vad_combo.addItem(label, value)
        self.silence_timeout_spin = QSpinBox()
        self.silence_timeout_spin.setRange(300, 5000)
        self.silence_timeout_spin.setSingleStep(100)
        self.silence_timeout_spin.setSuffix(" ms")
        self.logging_checkbox = QCheckBox("Write Q&A sessions to local JSONL files")
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Default", None)
        for profile in application_profiles:
            self.profile_combo.addItem(profile.replace("-", " "), profile)

        form.addRow("Default answer style", self.answer_style_combo)
        form.addRow("VAD aggressiveness", self.vad_combo)
        form.addRow("Silence timeout", self.silence_timeout_spin)
        form.addRow("Default application profile", self.profile_combo)
        form.addRow("Session logging", self.logging_checkbox)
        return group

    def _build_overlay_group(self) -> QGroupBox:
        group = QGroupBox("Overlay appearance")
        form = QFormLayout(group)
        self.overlay_width_spin = self._spin(360, 800, " px")
        self.overlay_height_spin = self._spin(300, 900, " px")
        self.overlay_opacity_spin = self._spin(35, 100, "%")
        self.overlay_font_size_spin = self._spin(12, 28, " px")
        form.addRow("Width", self.overlay_width_spin)
        form.addRow("Height", self.overlay_height_spin)
        form.addRow("Opacity", self.overlay_opacity_spin)
        form.addRow("Answer font size", self.overlay_font_size_spin)
        return group

    def _build_health_group(self) -> QGroupBox:
        group = QGroupBox("Setup health")
        layout = QVBoxLayout(group)
        self.health_summary = QLabel()
        self.health_summary.setWordWrap(True)
        layout.addWidget(self.health_summary)
        return group

    @staticmethod
    def _spin(minimum: int, maximum: int, suffix: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSuffix(suffix)
        return spin

    def _populate_devices(self) -> None:
        saved_index = self.settings.audio_device_index
        saved_name = self.settings.audio_device_name
        self.audio_device_combo.clear()
        try:
            self.devices = list_audio_input_devices(self.pa)
        except Exception as exc:
            self.devices = []
            self.audio_status_label.setText(
                f"Could not enumerate audio devices: {exc}. Check macOS audio permission."
            )
        for device in self.devices:
            self.audio_device_combo.addItem(
                f"{device.name} ({device.channels} in)",
                device.index,
            )
        preferred = preferred_audio_device_index(
            self.devices,
            saved_index,
            saved_name,
        )
        if preferred is not None:
            combo_index = self.audio_device_combo.findData(preferred)
            self.audio_device_combo.setCurrentIndex(combo_index)
        if not self.devices:
            self.audio_device_combo.addItem("No input devices found", None)
            self.audio_device_combo.setEnabled(False)
            self.audio_status_label.setText(
                "No audio input device is available. Connect or enable one, grant "
                "microphone permission, then restart the app."
            )

    def _load_form(self, settings: AppSettings) -> None:
        self.ollama_url_input.setText(settings.ollama_base_url)
        self.ollama_model_combo.addItem(settings.ollama_model)
        self.ollama_model_combo.setCurrentText(settings.ollama_model)
        self.whisper_model_combo.setCurrentText(settings.whisper_model)
        self.whisper_language_combo.setCurrentText(settings.whisper_language)
        self.answer_style_combo.setCurrentIndex(
            self.answer_style_combo.findData(settings.answer_style)
        )
        self.vad_combo.setCurrentIndex(
            self.vad_combo.findData(settings.vad_aggressiveness)
        )
        self.silence_timeout_spin.setValue(settings.silence_timeout_ms)
        self.logging_checkbox.setChecked(settings.session_logging_enabled)
        profile_index = self.profile_combo.findData(
            settings.default_application_profile
        )
        self.profile_combo.setCurrentIndex(max(0, profile_index))
        self.overlay_width_spin.setValue(settings.overlay_width)
        self.overlay_height_spin.setValue(settings.overlay_height)
        self.overlay_opacity_spin.setValue(settings.overlay_opacity)
        self.overlay_font_size_spin.setValue(settings.overlay_font_size)

    def _connect_change_signals(self) -> None:
        self.audio_device_combo.currentIndexChanged.connect(
            self._audio_device_changed
        )
        self.ollama_url_input.textChanged.connect(self._ollama_selection_changed)
        self.ollama_model_combo.currentTextChanged.connect(
            self._ollama_selection_changed
        )
        self.whisper_model_combo.currentTextChanged.connect(
            self._transcription_settings_changed
        )
        self.whisper_language_combo.currentTextChanged.connect(
            self._transcription_settings_changed
        )

    def _audio_device_changed(self) -> None:
        self._audio_test_passed = False
        self._transcription_test_passed = False
        self.audio_meter.setValue(0)
        self.audio_status_label.setText("Audio device changed — run a capture test.")
        self.transcription_output.clear()
        self._refresh_health()

    def _ollama_selection_changed(self) -> None:
        if self.ollama_diagnostics is not None:
            checked_endpoint = self.ollama_status_label.property("checked_endpoint")
            same_endpoint = (
                isinstance(checked_endpoint, str)
                and self.ollama_url_input.text().strip().rstrip("/")
                == checked_endpoint
            )
            same_model = (
                self.ollama_model_combo.currentText().strip()
                == self.ollama_diagnostics.selected_model
            )
            if not (same_endpoint and same_model):
                self.ollama_diagnostics = None
                self.ollama_status_label.setText(
                    "Ollama settings changed — refresh diagnostics."
                )
        self._refresh_health()

    def _transcription_settings_changed(self) -> None:
        self._transcription_test_passed = False
        self.transcription_output.clear()
        self._refresh_health()

    def current_settings(self) -> AppSettings:
        device_index = self.audio_device_combo.currentData()
        device = next(
            (item for item in self.devices if item.index == device_index),
            None,
        )
        return AppSettings(
            ollama_base_url=self.ollama_url_input.text(),
            ollama_model=self.ollama_model_combo.currentText(),
            whisper_model=self.whisper_model_combo.currentText(),
            whisper_language=self.whisper_language_combo.currentText(),
            answer_style=self.answer_style_combo.currentData(),
            vad_aggressiveness=self.vad_combo.currentData(),
            silence_timeout_ms=self.silence_timeout_spin.value(),
            audio_device_index=device.index if device else None,
            audio_device_name=device.name if device else None,
            overlay_width=self.overlay_width_spin.value(),
            overlay_height=self.overlay_height_spin.value(),
            overlay_opacity=self.overlay_opacity_spin.value(),
            overlay_font_size=self.overlay_font_size_spin.value(),
            session_logging_enabled=self.logging_checkbox.isChecked(),
            default_application_profile=self.profile_combo.currentData(),
        ).validated()

    def refresh_ollama(self) -> None:
        if self._ollama_thread is not None and self._ollama_thread.isRunning():
            return
        self.ollama_status_label.setText("Checking Ollama and installed models…")
        self.refresh_button.setEnabled(False)
        self.ollama_diagnostics = None
        self._refresh_health()
        self._ollama_thread = OllamaCheckThread(
            self.ollama_url_input.text(),
            self.ollama_model_combo.currentText(),
        )
        self._ollama_thread.checked.connect(self._ollama_checked)
        self._ollama_thread.finished.connect(self._ollama_check_finished)
        self._ollama_thread.start()

    def _ollama_checked(self, diagnostics: OllamaDiagnostics) -> None:
        self.ollama_diagnostics = diagnostics
        endpoint = self.ollama_url_input.text().strip().rstrip("/")
        self.ollama_status_label.setProperty("checked_endpoint", endpoint)
        installed = ", ".join(diagnostics.models) or "none"
        message = f"{diagnostics.message} Installed models: {installed}."
        if diagnostics.fix:
            message += f" Fix: {diagnostics.fix}"
        self.ollama_status_label.setText(message)

        selected = self.ollama_model_combo.currentText().strip()
        self.ollama_model_combo.blockSignals(True)
        for model in diagnostics.models:
            if self.ollama_model_combo.findText(model) < 0:
                self.ollama_model_combo.addItem(model)
        self.ollama_model_combo.setCurrentText(selected)
        self.ollama_model_combo.blockSignals(False)
        self._refresh_health()

    def _ollama_check_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self._ollama_thread = None

    def test_audio_capture(self) -> None:
        self._start_audio_diagnostic(transcribe_audio=False, duration_seconds=3)

    def test_transcription(self) -> None:
        self.transcription_output.setPlainText(
            "Listening for five seconds, then loading Whisper…"
        )
        self._start_audio_diagnostic(transcribe_audio=True, duration_seconds=5)

    def _start_audio_diagnostic(
        self,
        *,
        transcribe_audio: bool,
        duration_seconds: float,
    ) -> None:
        if self._audio_thread is not None and self._audio_thread.isRunning():
            return
        device_index = self.audio_device_combo.currentData()
        if device_index is None:
            self.audio_status_label.setText(
                "No audio input is selected. Connect a device and restart setup."
            )
            self._refresh_health()
            return
        self._set_audio_buttons_enabled(False)
        self.start_button.setEnabled(False)
        self.audio_meter.setValue(0)
        self.audio_status_label.setText("Listening — speak or play call audio now…")
        self._audio_thread = AudioDiagnosticThread(
            self.pa,
            device_index,
            duration_seconds=duration_seconds,
            transcribe_audio=transcribe_audio,
            whisper_model=self.whisper_model_combo.currentText().strip(),
            whisper_language=self.whisper_language_combo.currentText().strip(),
        )
        self._diagnostic_is_transcription = transcribe_audio
        self._audio_thread.level_changed.connect(self.audio_meter.setValue)
        self._audio_thread.capture_complete.connect(self._audio_capture_complete)
        self._audio_thread.transcription_complete.connect(
            self._transcription_complete
        )
        self._audio_thread.failed.connect(self._audio_failed)
        self._audio_thread.finished.connect(self._audio_check_finished)
        self._audio_thread.start()

    def _audio_capture_complete(self, message: str) -> None:
        self._audio_test_passed = True
        self.audio_status_label.setText(message)
        self._refresh_health()

    def _transcription_complete(self, result: TranscriptionResult) -> None:
        text = result.text.strip()
        self._audio_test_passed = True
        self._transcription_test_passed = bool(text)
        if text:
            self.transcription_output.setPlainText(text)
            self.audio_status_label.setText(
                f"Transcription succeeded (confidence {result.confidence:.0%})."
            )
        else:
            self.transcription_output.setPlainText("No speech was detected.")
            self.audio_status_label.setText(
                "Audio was captured, but Whisper detected no speech. Check the "
                "selected device and play audio during the test."
            )
        self._refresh_health()

    def _audio_failed(self, message: str) -> None:
        self._audio_test_passed = False
        self._transcription_test_passed = False
        if self._diagnostic_is_transcription:
            self.audio_status_label.setText(
                f"Transcription test failed: {message}. Check the Whisper model "
                "name and internet access for its first download, then retry."
            )
        else:
            self.audio_status_label.setText(
                f"Audio test failed: {message}. Check the selected device and "
                "macOS microphone permission."
            )
        self._refresh_health()

    def _audio_check_finished(self) -> None:
        self._set_audio_buttons_enabled(True)
        self._audio_thread = None
        self._refresh_health()

    def _set_audio_buttons_enabled(self, enabled: bool) -> None:
        has_device = bool(self.devices)
        self.test_audio_button.setEnabled(enabled and has_device)
        self.test_transcription_button.setEnabled(enabled and has_device)
        self.audio_device_combo.setEnabled(enabled and has_device)

    def _refresh_health(self) -> None:
        audio_ready = self.audio_device_combo.currentData() is not None
        ollama_ready = bool(
            self.ollama_diagnostics and self.ollama_diagnostics.ready
        )
        diagnostics_idle = not (
            (self._audio_thread and self._audio_thread.isRunning())
            or (self._ollama_thread and self._ollama_thread.isRunning())
        )
        items = [
            (audio_ready, "Audio input selected"),
            (self._audio_test_passed, "Audio capture tested"),
            (self._transcription_test_passed, "Transcription tested"),
            (
                bool(self.ollama_diagnostics and self.ollama_diagnostics.reachable),
                "Ollama reachable",
            ),
            (ollama_ready, "Selected Ollama model installed"),
        ]
        lines = [f"{'✓' if ready else '○'} {label}" for ready, label in items]
        if self._settings_load_error:
            lines.append(
                "⚠ Existing settings could not be loaded; defaults are shown. "
                + self._settings_load_error
            )
        core_ready = audio_ready and ollama_ready
        if core_ready and diagnostics_idle:
            lines.append("\nReady to start.")
        elif core_ready:
            lines.append("\nFinishing the current diagnostic…")
        else:
            lines.append(
                "\nComplete the audio and Ollama checks above before starting."
            )
        self.health_summary.setText("\n".join(lines))
        self.start_button.setEnabled(core_ready and diagnostics_idle)

    def _save_only(self) -> bool:
        try:
            self.settings = self.current_settings()
            save_settings(self.settings, self.settings_path)
        except SettingsError as exc:
            self.health_summary.setText(f"Settings were not saved: {exc}")
            return False
        self._settings_load_error = None
        self.health_summary.setText(
            f"Settings saved locally to {self.settings_path}.\n\n"
            + self.health_summary.text()
        )
        return True

    def _save_and_start(self) -> None:
        if not (
            self.audio_device_combo.currentData() is not None
            and self.ollama_diagnostics
            and self.ollama_diagnostics.ready
            and not (self._audio_thread and self._audio_thread.isRunning())
            and not (self._ollama_thread and self._ollama_thread.isRunning())
        ):
            self._refresh_health()
            return
        if self._save_only():
            self.accept()

    def _stop_diagnostics(self) -> None:
        if self._audio_thread is not None and self._audio_thread.isRunning():
            self._audio_thread.requestInterruption()
            self._audio_thread.wait(1500)
        if self._ollama_thread is not None and self._ollama_thread.isRunning():
            self._ollama_thread.requestInterruption()
            # The HTTP request has a 3-second timeout and cannot be interrupted
            # inside requests, so let it unwind before Qt destroys the thread.
            self._ollama_thread.wait(4000)

    def reject(self) -> None:
        self._stop_diagnostics()
        super().reject()

    def closeEvent(self, event) -> None:
        self._stop_diagnostics()
        super().closeEvent(event)
