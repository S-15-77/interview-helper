import json

import pytest

from src.settings import (
    SETTINGS_VERSION,
    AppSettings,
    SettingsError,
    load_settings,
    save_settings,
)


def test_settings_round_trip_all_configurable_values(tmp_path):
    path = tmp_path / "settings.json"
    settings = AppSettings(
        ollama_base_url="http://127.0.0.1:11434/",
        ollama_model="qwen2.5:7b-instruct",
        whisper_model="small.en",
        whisper_language="auto",
        answer_style="shorter",
        vad_aggressiveness=2,
        silence_timeout_ms=1400,
        audio_device_index=7,
        audio_device_name="Call Audio",
        candidate_capture_enabled=True,
        candidate_audio_device_index=9,
        candidate_audio_device_name="Candidate Mic",
        retain_candidate_audio=True,
        overlay_width=620,
        overlay_height=640,
        overlay_opacity=82,
        overlay_font_size=19,
        session_logging_enabled=False,
        default_application_profile="compiler-role",
    )

    save_settings(settings, path)

    assert load_settings(path) == AppSettings(
        **{
            **settings.__dict__,
            "ollama_base_url": "http://127.0.0.1:11434",
        }
    )
    raw = json.loads(path.read_text())
    assert raw["version"] == SETTINGS_VERSION
    assert raw["audio"]["device_name"] == "Call Audio"
    assert raw["audio"]["candidate_device_name"] == "Candidate Mic"
    assert raw["audio"]["retain_candidate_audio"] is True
    assert "consent" not in json.dumps(raw).casefold()
    assert raw["session"]["logging_enabled"] is False


def test_missing_settings_file_uses_safe_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.json")

    assert settings.version == SETTINGS_VERSION
    assert settings.ollama_model == "qwen2.5:3b-instruct"
    assert settings.audio_device_index is None


def test_future_settings_version_reports_actionable_error(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"version": SETTINGS_VERSION + 1}))

    with pytest.raises(SettingsError, match="Unsupported settings version"):
        load_settings(path)


def test_invalid_setting_identifies_the_bad_field(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": SETTINGS_VERSION,
                "audio": {"vad_aggressiveness": "maximum"},
            }
        )
    )

    with pytest.raises(SettingsError, match="audio.vad_aggressiveness"):
        load_settings(path)


def test_version_one_settings_are_migrated_with_safe_candidate_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "ollama": {"model": "legacy-model"},
                "audio": {"device_index": 2, "device_name": "BlackHole 2ch"},
            }
        )
    )

    settings = load_settings(path)

    assert settings.version == SETTINGS_VERSION
    assert settings.ollama_model == "legacy-model"
    assert settings.candidate_capture_enabled
    assert not settings.retain_candidate_audio


def test_same_device_cannot_be_used_for_both_audio_roles():
    with pytest.raises(SettingsError, match="must use different inputs"):
        AppSettings(
            audio_device_index=2,
            candidate_audio_device_index=2,
        ).validated()
