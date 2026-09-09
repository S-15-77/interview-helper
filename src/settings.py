import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

SETTINGS_VERSION = 3
DEFAULT_SETTINGS_PATH = Path("my_data/settings.json")
ANSWER_STYLES = ("default", "shorter", "more_detail")
PRACTICE_MODES = ("learn", "simulate", "review")
INTERVIEW_DIFFICULTIES = ("introductory", "intermediate", "advanced")
INTERVIEW_ROUNDS = (
    "recruiter",
    "behavioral",
    "technical",
    "coding",
    "system_design",
)


class SettingsError(ValueError):
    """Raised when the local settings file cannot be safely loaded."""


@dataclass(frozen=True)
class AppSettings:
    version: int = SETTINGS_VERSION
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    whisper_model: str = "base.en"
    whisper_language: str = "en"
    answer_style: str = "default"
    practice_mode: str = "learn"
    interview_length: int = 8
    interview_difficulty: str = "intermediate"
    interview_rounds: tuple[str, ...] = INTERVIEW_ROUNDS
    vad_aggressiveness: int = 3
    silence_timeout_ms: int = 1000
    audio_device_index: int | None = None
    audio_device_name: str | None = None
    candidate_capture_enabled: bool = True
    candidate_audio_device_index: int | None = None
    candidate_audio_device_name: str | None = None
    retain_candidate_audio: bool = False
    overlay_width: int = 480
    overlay_height: int = 500
    overlay_opacity: int = 100
    overlay_font_size: int = 16
    session_logging_enabled: bool = True
    session_retention_days: int = 0
    redact_exports: bool = False
    default_application_profile: str | None = None

    def validated(self) -> "AppSettings":
        if self.version != SETTINGS_VERSION:
            raise SettingsError(
                f"Unsupported settings version {self.version}; expected {SETTINGS_VERSION}."
            )
        if not self.ollama_base_url.strip().startswith(("http://", "https://")):
            raise SettingsError("Ollama URL must begin with http:// or https://.")
        if not self.ollama_model.strip():
            raise SettingsError("An Ollama model must be selected.")
        if not self.whisper_model.strip():
            raise SettingsError("A Whisper model must be selected.")
        if not self.whisper_language.strip():
            raise SettingsError("A Whisper language or 'auto' must be selected.")
        if self.answer_style not in ANSWER_STYLES:
            raise SettingsError(f"Answer style must be one of: {', '.join(ANSWER_STYLES)}.")
        if self.practice_mode not in PRACTICE_MODES:
            raise SettingsError(f"Practice mode must be one of: {', '.join(PRACTICE_MODES)}.")
        if not 1 <= self.interview_length <= 30:
            raise SettingsError("Interview length must be between 1 and 30 questions.")
        if self.interview_difficulty not in INTERVIEW_DIFFICULTIES:
            raise SettingsError(
                "Interview difficulty must be introductory, intermediate, or advanced."
            )
        if not self.interview_rounds or any(
            round_name not in INTERVIEW_ROUNDS for round_name in self.interview_rounds
        ):
            raise SettingsError("Select at least one supported interview round.")
        if self.vad_aggressiveness not in range(4):
            raise SettingsError("VAD aggressiveness must be between 0 and 3.")
        if not 300 <= self.silence_timeout_ms <= 5000:
            raise SettingsError("Silence timeout must be between 300 and 5000 ms.")
        if self.audio_device_index is not None and self.audio_device_index < 0:
            raise SettingsError("Audio device index cannot be negative.")
        if self.candidate_audio_device_index is not None and self.candidate_audio_device_index < 0:
            raise SettingsError("Candidate microphone index cannot be negative.")
        if self.retain_candidate_audio and not self.candidate_capture_enabled:
            raise SettingsError(
                "Candidate audio cannot be retained while candidate capture is disabled."
            )
        if self.practice_mode == "simulate" and not self.candidate_capture_enabled:
            raise SettingsError("Simulate mode requires candidate-response capture.")
        if (
            self.candidate_capture_enabled
            and self.audio_device_index is not None
            and self.candidate_audio_device_index == self.audio_device_index
        ):
            raise SettingsError(
                "Interviewer audio and the candidate microphone must use different inputs."
            )
        if not 360 <= self.overlay_width <= 800:
            raise SettingsError("Overlay width must be between 360 and 800 pixels.")
        if not 300 <= self.overlay_height <= 900:
            raise SettingsError("Overlay height must be between 300 and 900 pixels.")
        if not 35 <= self.overlay_opacity <= 100:
            raise SettingsError("Overlay opacity must be between 35 and 100 percent.")
        if not 12 <= self.overlay_font_size <= 28:
            raise SettingsError("Overlay font size must be between 12 and 28 pixels.")
        if not 0 <= self.session_retention_days <= 3650:
            raise SettingsError("Session retention must be between 0 and 3650 days.")
        return replace(
            self,
            ollama_base_url=self.ollama_base_url.strip().rstrip("/"),
            ollama_model=self.ollama_model.strip(),
            whisper_model=self.whisper_model.strip(),
            whisper_language=self.whisper_language.strip(),
            audio_device_name=(self.audio_device_name or "").strip() or None,
            candidate_audio_device_name=(self.candidate_audio_device_name or "").strip() or None,
            default_application_profile=(self.default_application_profile or "").strip() or None,
        )

    def to_dict(self) -> dict[str, Any]:
        settings = self.validated()
        return {
            "version": settings.version,
            "ollama": {
                "base_url": settings.ollama_base_url,
                "model": settings.ollama_model,
            },
            "whisper": {
                "model": settings.whisper_model,
                "language": settings.whisper_language,
            },
            "answers": {
                "style": settings.answer_style,
                "practice_mode": settings.practice_mode,
            },
            "interview": {
                "length": settings.interview_length,
                "difficulty": settings.interview_difficulty,
                "rounds": list(settings.interview_rounds),
            },
            "audio": {
                "device_index": settings.audio_device_index,
                "device_name": settings.audio_device_name,
                "vad_aggressiveness": settings.vad_aggressiveness,
                "silence_timeout_ms": settings.silence_timeout_ms,
                "candidate_capture_enabled": settings.candidate_capture_enabled,
                "candidate_device_index": settings.candidate_audio_device_index,
                "candidate_device_name": settings.candidate_audio_device_name,
                "retain_candidate_audio": settings.retain_candidate_audio,
            },
            "overlay": {
                "width": settings.overlay_width,
                "height": settings.overlay_height,
                "opacity": settings.overlay_opacity,
                "font_size": settings.overlay_font_size,
            },
            "session": {
                "logging_enabled": settings.session_logging_enabled,
                "retention_days": settings.session_retention_days,
                "redact_exports": settings.redact_exports,
            },
            "application": {
                "default_profile": settings.default_application_profile,
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppSettings":
        if not isinstance(raw, dict):
            raise SettingsError("Settings must be a JSON object.")
        version = raw.get("version", SETTINGS_VERSION)
        if isinstance(version, bool) or not isinstance(version, int):
            raise SettingsError("Settings version must be an integer.")
        if version not in (1, 2, SETTINGS_VERSION):
            raise SettingsError(
                f"Unsupported settings version {version}; expected {SETTINGS_VERSION}."
            )

        ollama = _section(raw, "ollama")
        whisper = _section(raw, "whisper")
        answers = _section(raw, "answers")
        interview = _section(raw, "interview")
        audio = _section(raw, "audio")
        overlay = _section(raw, "overlay")
        session = _section(raw, "session")
        application = _section(raw, "application")
        defaults = cls()

        try:
            settings = cls(
                version=SETTINGS_VERSION,
                ollama_base_url=_text(
                    ollama.get("base_url", defaults.ollama_base_url),
                    "ollama.base_url",
                ),
                ollama_model=_text(ollama.get("model", defaults.ollama_model), "ollama.model"),
                whisper_model=_text(whisper.get("model", defaults.whisper_model), "whisper.model"),
                whisper_language=_text(
                    whisper.get("language", defaults.whisper_language),
                    "whisper.language",
                ),
                answer_style=_text(answers.get("style", defaults.answer_style), "answers.style"),
                practice_mode=_text(
                    answers.get("practice_mode", defaults.practice_mode),
                    "answers.practice_mode",
                ),
                interview_length=_integer(
                    interview.get("length", defaults.interview_length),
                    "interview.length",
                ),
                interview_difficulty=_text(
                    interview.get("difficulty", defaults.interview_difficulty),
                    "interview.difficulty",
                ),
                interview_rounds=_string_tuple(
                    interview.get("rounds", list(defaults.interview_rounds)),
                    "interview.rounds",
                ),
                vad_aggressiveness=_integer(
                    audio.get("vad_aggressiveness", defaults.vad_aggressiveness),
                    "audio.vad_aggressiveness",
                ),
                silence_timeout_ms=_integer(
                    audio.get("silence_timeout_ms", defaults.silence_timeout_ms),
                    "audio.silence_timeout_ms",
                ),
                audio_device_index=_optional_integer(
                    audio.get("device_index", defaults.audio_device_index),
                    "audio.device_index",
                ),
                audio_device_name=_optional_string(
                    audio.get("device_name", defaults.audio_device_name)
                ),
                candidate_capture_enabled=_boolean(
                    audio.get(
                        "candidate_capture_enabled",
                        defaults.candidate_capture_enabled,
                    ),
                    "audio.candidate_capture_enabled",
                ),
                candidate_audio_device_index=_optional_integer(
                    audio.get(
                        "candidate_device_index",
                        defaults.candidate_audio_device_index,
                    ),
                    "audio.candidate_device_index",
                ),
                candidate_audio_device_name=_optional_string(
                    audio.get(
                        "candidate_device_name",
                        defaults.candidate_audio_device_name,
                    )
                ),
                retain_candidate_audio=_boolean(
                    audio.get(
                        "retain_candidate_audio",
                        defaults.retain_candidate_audio,
                    ),
                    "audio.retain_candidate_audio",
                ),
                overlay_width=_integer(
                    overlay.get("width", defaults.overlay_width), "overlay.width"
                ),
                overlay_height=_integer(
                    overlay.get("height", defaults.overlay_height), "overlay.height"
                ),
                overlay_opacity=_integer(
                    overlay.get("opacity", defaults.overlay_opacity),
                    "overlay.opacity",
                ),
                overlay_font_size=_integer(
                    overlay.get("font_size", defaults.overlay_font_size),
                    "overlay.font_size",
                ),
                session_logging_enabled=_boolean(
                    session.get("logging_enabled", defaults.session_logging_enabled),
                    "session.logging_enabled",
                ),
                session_retention_days=_integer(
                    session.get("retention_days", defaults.session_retention_days),
                    "session.retention_days",
                ),
                redact_exports=_boolean(
                    session.get("redact_exports", defaults.redact_exports),
                    "session.redact_exports",
                ),
                default_application_profile=_optional_string(
                    application.get("default_profile", defaults.default_application_profile)
                ),
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, SettingsError):
                raise
            raise SettingsError(f"Invalid settings value: {exc}") from exc
        return settings.validated()


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise SettingsError(f"Settings section '{name}' must be a JSON object.")
    return value


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsError(f"{name} must be an integer.")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise SettingsError(f"{name} must be text.")
    return value


def _optional_integer(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return _integer(value, name)


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise SettingsError(f"{name} must be true or false.")
    return value


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SettingsError(f"{name} must be a list of strings.")
    return tuple(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SettingsError("Optional text settings must be strings or null.")
    return value


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> AppSettings:
    path = Path(path)
    if not path.exists():
        return AppSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SettingsError(f"Could not read {path}: {exc}") from exc
    return AppSettings.from_dict(raw)


def save_settings(
    settings: AppSettings,
    path: Path = DEFAULT_SETTINGS_PATH,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    serialized = json.dumps(settings.to_dict(), indent=2) + "\n"
    try:
        temporary_path.write_text(serialized, encoding="utf-8")
        temporary_path.replace(path)
    except OSError as exc:
        raise SettingsError(f"Could not save {path}: {exc}") from exc
    return path
