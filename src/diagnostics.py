import math
from dataclasses import dataclass

import numpy as np
import requests


@dataclass(frozen=True)
class AudioInputDevice:
    index: int
    name: str
    channels: int
    default_sample_rate: int


@dataclass(frozen=True)
class OllamaDiagnostics:
    reachable: bool
    models: tuple[str, ...]
    selected_model: str
    model_available: bool
    message: str
    fix: str | None = None

    @property
    def ready(self) -> bool:
        return self.reachable and self.model_available


def list_audio_input_devices(pa) -> list[AudioInputDevice]:
    devices: list[AudioInputDevice] = []
    for index in range(pa.get_device_count()):
        try:
            info = pa.get_device_info_by_index(index)
            channels = int(info.get("maxInputChannels", 0))
            if channels <= 0:
                continue
            devices.append(
                AudioInputDevice(
                    index=index,
                    name=str(info.get("name", f"Input {index}")),
                    channels=channels,
                    default_sample_rate=round(
                        float(info.get("defaultSampleRate", 16000))
                    ),
                )
            )
        except (OSError, TypeError, ValueError):
            # One malformed or disconnected device should not hide the others.
            continue
    return devices


def preferred_audio_device_index(
    devices: list[AudioInputDevice],
    saved_index: int | None = None,
    saved_name: str | None = None,
) -> int | None:
    if saved_index is not None:
        saved = next((device for device in devices if device.index == saved_index), None)
        if saved is not None and (
            not saved_name or saved.name.casefold() == saved_name.casefold()
        ):
            return saved.index
    if saved_name:
        exact = next(
            (
                device
                for device in devices
                if device.name.casefold() == saved_name.casefold()
            ),
            None,
        )
        if exact is not None:
            return exact.index
    blackhole = next(
        (device for device in devices if "blackhole" in device.name.casefold()),
        None,
    )
    return blackhole.index if blackhole is not None else (
        devices[0].index if devices else None
    )


def audio_level_percent(pcm_bytes: bytes) -> int:
    if not pcm_bytes:
        return 0
    samples = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32)
    if not samples.size:
        return 0
    rms = float(np.sqrt(np.mean(np.square(samples / 32768.0))))
    if rms <= 0:
        return 0
    decibels = 20 * math.log10(rms)
    # Map the useful speech-meter range (-60 dBFS to 0 dBFS) onto 0-100.
    return round(min(max((decibels + 60) / 60 * 100, 0), 100))


def normalize_ollama_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def check_ollama(
    base_url: str,
    selected_model: str,
    *,
    timeout: float = 3.0,
) -> OllamaDiagnostics:
    base_url = normalize_ollama_base_url(base_url)
    selected_model = selected_model.strip()
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Ollama returned an invalid response")
        raw_models = payload.get("models", [])
        if not isinstance(raw_models, list):
            raise ValueError("Ollama returned an invalid models list")
        models = tuple(
            sorted(
                {
                    str(model.get("name") or model.get("model")).strip()
                    for model in raw_models
                    if isinstance(model, dict)
                    and (model.get("name") or model.get("model"))
                }
            )
        )
    except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
        return OllamaDiagnostics(
            reachable=False,
            models=(),
            selected_model=selected_model,
            model_available=False,
            message=f"Ollama is unreachable at {base_url}: {exc}",
            fix="Start the Ollama app or run `ollama serve`, then retry.",
        )

    available = selected_model in models
    if not selected_model:
        return OllamaDiagnostics(
            reachable=True,
            models=models,
            selected_model=selected_model,
            model_available=False,
            message="Ollama is reachable, but no model is selected.",
            fix="Select one of the installed models.",
        )
    if not available:
        return OllamaDiagnostics(
            reachable=True,
            models=models,
            selected_model=selected_model,
            model_available=False,
            message=f"Selected model '{selected_model}' is not installed.",
            fix=f"Run `ollama pull {selected_model}`, then refresh models.",
        )
    return OllamaDiagnostics(
        reachable=True,
        models=models,
        selected_model=selected_model,
        model_available=True,
        message=f"Ollama is ready with '{selected_model}'.",
    )
