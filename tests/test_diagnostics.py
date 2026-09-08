from unittest.mock import Mock, patch

import numpy as np

from src.diagnostics import (
    AudioInputDevice,
    audio_level_percent,
    check_ollama,
    list_audio_input_devices,
    preferred_audio_device_index,
)


class FakePyAudio:
    def __init__(self, devices):
        self.devices = devices

    def get_device_count(self):
        return len(self.devices)

    def get_device_info_by_index(self, index):
        return self.devices[index]


def test_audio_selector_lists_every_input_and_ignores_outputs():
    pa = FakePyAudio(
        [
            {
                "name": "MacBook Microphone",
                "maxInputChannels": 1,
                "defaultSampleRate": 48000,
            },
            {
                "name": "Speakers",
                "maxInputChannels": 0,
                "defaultSampleRate": 48000,
            },
            {
                "name": "USB Call Audio",
                "maxInputChannels": 2,
                "defaultSampleRate": 44100,
            },
        ]
    )

    devices = list_audio_input_devices(pa)

    assert [(device.index, device.name) for device in devices] == [
        (0, "MacBook Microphone"),
        (2, "USB Call Audio"),
    ]


def test_saved_audio_device_name_survives_an_index_change():
    devices = [
        AudioInputDevice(1, "Other Input", 1, 48000),
        AudioInputDevice(4, "Call Audio", 2, 48000),
    ]

    assert preferred_audio_device_index(devices, 2, "Call Audio") == 4


def test_blackhole_is_only_a_preference_not_a_requirement():
    ordinary = [AudioInputDevice(3, "USB Interface", 1, 48000)]
    with_blackhole = ordinary + [AudioInputDevice(5, "BlackHole 2ch", 2, 48000)]

    assert preferred_audio_device_index(ordinary) == 3
    assert preferred_audio_device_index(with_blackhole) == 5


def test_audio_level_meter_maps_silence_and_signal():
    silence = np.zeros(480, dtype="<i2").tobytes()
    signal = np.full(480, 12000, dtype="<i2").tobytes()

    assert audio_level_percent(silence) == 0
    assert 0 < audio_level_percent(signal) <= 100


def test_ollama_diagnostics_list_models_and_confirm_selection():
    response = Mock()
    response.json.return_value = {
        "models": [
            {"name": "qwen2.5:3b-instruct"},
            {"model": "llama3.2:latest"},
        ]
    }

    with patch("src.diagnostics.requests.get", return_value=response) as get:
        result = check_ollama(
            "http://localhost:11434/",
            "qwen2.5:3b-instruct",
        )

    get.assert_called_once_with("http://localhost:11434/api/tags", timeout=3.0)
    response.raise_for_status.assert_called_once_with()
    assert result.ready
    assert result.models == ("llama3.2:latest", "qwen2.5:3b-instruct")


def test_ollama_diagnostics_explain_how_to_install_missing_model():
    response = Mock()
    response.json.return_value = {"models": [{"name": "other:latest"}]}

    with patch("src.diagnostics.requests.get", return_value=response):
        result = check_ollama("http://localhost:11434", "missing:7b")

    assert result.reachable
    assert not result.model_available
    assert "not installed" in result.message
    assert result.fix == "Run `ollama pull missing:7b`, then refresh models."


def test_ollama_diagnostics_explain_unreachable_service():
    from requests import ConnectionError

    with patch(
        "src.diagnostics.requests.get",
        side_effect=ConnectionError("connection refused"),
    ):
        result = check_ollama("http://localhost:11434", "qwen:latest")

    assert not result.reachable
    assert "unreachable" in result.message
    assert "ollama serve" in result.fix
