# Mock Interview Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully local macOS app that transcribes a friend's voice during a mock-interview video call and streams a coached answer onto a floating overlay in real time.

**Architecture:** A capture thread reads BlackHole audio into 30ms frames and runs them through a VAD segmenter to find utterance boundaries; a worker thread transcribes each utterance with faster-whisper, streams a coached answer from local Ollama, pushes text to a PyQt6 overlay via Qt signals, and appends each Q&A pair to a JSONL session log. The Qt event loop owns the main thread; audio and inference never block the UI.

**Tech Stack:** Python 3.11+, PyAudio, webrtcvad, faster-whisper, Ollama (REST API), PyQt6, pyobjc-framework-Cocoa, requests, numpy, soundfile, pytest.

## Global Constraints

- Platform: macOS, Apple Silicon, 16GB+ RAM (per spec's environment assumptions).
- Fully local/offline: no audio, transcript, or question ever leaves the machine; the only network calls are to `http://localhost:11434` (local Ollama).
- No raw audio is ever written to disk in the running app; only the session logger's text (question/answer/timestamps) is persisted, to `sessions/<start-time>.jsonl`.
- Default LLM model: `llama3.2` (3B). `llama3.1:8b` is a user-swappable option, not required.
- VAD trailing-silence trigger: ~1000ms of silence after speech finalizes an utterance (per spec).
- Rolling LLM context cap: last 200 words.
- Overlay must be excluded from macOS screen-share/recording capture and must be click-through (per spec, since screen sharing happens during mock coding rounds).
- This is a self-practice tool for use with a consenting friend — not for use during a real employer interview (per spec's non-goals).

---

## File Structure

```
interview-helper/
  README.md
  requirements.txt
  .gitignore
  pytest.ini
  src/
    audio_capture.py
    transcriber.py
    llm_client.py
    overlay.py
    session_logger.py
    app.py
  tests/
    test_session_logger.py
    test_llm_client.py
    test_transcriber.py
    test_audio_capture.py
    test_app.py
    fixtures/
      hello.wav
  sessions/            # created at runtime, gitignored
```

---

### Task 1: Project scaffolding and environment setup

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `pytest.ini`
- Create: `README.md`

**Interfaces:**
- Produces: a working Python venv with all dependencies installed, a running local Ollama with `llama3.2` pulled, a BlackHole-based Multi-Output Device configured — all later tasks assume this environment exists.

- [ ] **Step 1: Create `requirements.txt`**

```
faster-whisper
pyaudio
webrtcvad
PyQt6
pyobjc-framework-Cocoa
requests
numpy
soundfile
pytest
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
sessions/
.DS_Store
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
pythonpath = .
```

This lets tests do `from src.session_logger import SessionLogger` etc. without needing `src/__init__.py` (namespace package import), as long as pytest is run from the project root.

- [ ] **Step 4: Create `README.md`** with the setup walkthrough

```markdown
# Mock Interview Overlay

Fully local mock-interview practice tool: transcribes your friend's voice
during a video call and streams a coached answer onto a floating overlay.
Nothing leaves your machine. For practicing with a consenting friend — not
for use during a real employer interview.

## One-time setup

1. **Install Ollama** (if not already installed):
   \`\`\`
   brew install ollama
   ollama serve &   # or launch the Ollama app
   ollama pull llama3.2
   \`\`\`
   Verify: \`ollama list\` should show \`llama3.2\`.

2. **Install BlackHole** (virtual audio device that lets the app "hear"
   your friend's voice from the call):
   \`\`\`
   brew install blackhole-2ch
   \`\`\`

3. **Create a Multi-Output Device** so you still hear the call while
   BlackHole also captures it:
   - Open **Audio MIDI Setup** (Spotlight search).
   - Click the **+** button (bottom-left) → **Create Multi-Output Device**.
   - Check both your normal output (e.g. "MacBook Pro Speakers" or your
     headphones) **and** "BlackHole 2ch".
   - Rename it to something recognizable, e.g. "Call + BlackHole".
   - Before each practice session: **System Settings → Sound → Output** →
     select that Multi-Output Device.

4. **Python environment:**
   \`\`\`
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   \`\`\`

5. **Permissions:** the first time you run the app, macOS will prompt for
   microphone/audio permission for your terminal — allow it.

## Running a session

\`\`\`
source venv/bin/activate
python src/app.py
\`\`\`

An overlay window appears top-left. Start your video call with your friend
(with system output set to the Multi-Output Device from step 3). When they
ask a question, the app transcribes it after ~1s of silence and streams a
coached answer onto the overlay. Each Q&A pair is logged to
\`sessions/<timestamp>.jsonl\`.
```

- [ ] **Step 5: Manual — install prerequisites**

Run yourself (not scriptable — Audio MIDI Setup is GUI-only):
1. `brew install ollama blackhole-2ch`
2. `ollama pull llama3.2`
3. Create the Multi-Output Device in Audio MIDI Setup per the README step 3.

- [ ] **Step 6: Create the venv and install Python deps**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: no errors; `pip list` includes `faster-whisper`, `pyaudio`, `webrtcvad`, `PyQt6`, `pyobjc-framework-Cocoa`, `requests`, `numpy`, `soundfile`, `pytest`.

- [ ] **Step 7: Verify environment**

```bash
ollama list
python -c "import pyaudio, webrtcvad, PyQt6, requests, numpy, soundfile; from faster_whisper import WhisperModel; print('ok')"
```

Expected: `ollama list` shows `llama3.2`; the Python command prints `ok` with no import errors.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore pytest.ini README.md
git commit -m "chore: project scaffolding and setup docs"
```

---

### Task 2: Session logger

**Files:**
- Create: `src/session_logger.py`
- Test: `tests/test_session_logger.py`

**Interfaces:**
- Produces: `class SessionLogger(sessions_dir: Path, start_time: datetime | None = None)` with `.log(question: str, answer: str, timestamp: datetime | None = None) -> None` and `.read_all() -> list[dict]`. `app.py` (Task 8) constructs one `SessionLogger` per run and calls `.log(...)` after each answer completes.

- [ ] **Step 1: Write the failing test**

`tests/test_session_logger.py`:

```python
from datetime import datetime
from pathlib import Path
import tempfile

from src.session_logger import SessionLogger


def test_log_round_trips_entry():
    with tempfile.TemporaryDirectory() as tmp:
        logger = SessionLogger(Path(tmp), start_time=datetime(2026, 7, 27, 10, 0, 0))
        logger.log(
            "What is a hash map?",
            "A hash map is...",
            timestamp=datetime(2026, 7, 27, 10, 0, 5),
        )

        entries = logger.read_all()

        assert len(entries) == 1
        assert entries[0]["question"] == "What is a hash map?"
        assert entries[0]["answer"] == "A hash map is..."
        assert entries[0]["timestamp"] == "2026-07-27T10:00:05"


def test_log_appends_multiple_entries_in_order():
    with tempfile.TemporaryDirectory() as tmp:
        logger = SessionLogger(Path(tmp), start_time=datetime(2026, 7, 27, 10, 0, 0))
        logger.log("Q1", "A1")
        logger.log("Q2", "A2")

        entries = logger.read_all()

        assert [e["question"] for e in entries] == ["Q1", "Q2"]


def test_read_all_returns_empty_list_when_no_entries_logged():
    with tempfile.TemporaryDirectory() as tmp:
        logger = SessionLogger(Path(tmp), start_time=datetime(2026, 7, 27, 10, 0, 0))
        assert logger.read_all() == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_session_logger.py -v
```

Expected: FAIL / ImportError — `src/session_logger.py` doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

`src/session_logger.py`:

```python
import json
from datetime import datetime
from pathlib import Path


class SessionLogger:
    def __init__(self, sessions_dir: Path, start_time: datetime | None = None):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        start_time = start_time or datetime.now()
        filename = start_time.strftime("%Y%m%d-%H%M%S") + ".jsonl"
        self.path = self.sessions_dir / filename

    def log(self, question: str, answer: str, timestamp: datetime | None = None) -> None:
        timestamp = timestamp or datetime.now()
        entry = {
            "timestamp": timestamp.isoformat(),
            "question": question,
            "answer": answer,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open() as f:
            return [json.loads(line) for line in f if line.strip()]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_session_logger.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/session_logger.py tests/test_session_logger.py
git commit -m "feat: add JSONL session logger"
```

---

### Task 3: LLM client (prompt builder + Ollama streaming)

**Files:**
- Create: `src/llm_client.py`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `build_prompt(context: str, question: str) -> str` and `stream_answer(question: str, context: str = "", model: str = "llama3.2") -> Iterator[str]`. `app.py` (Task 8) calls `stream_answer(question, self.context)` in a loop and forwards each yielded chunk to the overlay.

- [ ] **Step 1: Write the failing test (pure `build_prompt`, no network)**

`tests/test_llm_client.py`:

```python
from src.llm_client import build_prompt


def test_build_prompt_includes_question_and_star_guidance():
    prompt = build_prompt(context="", question="Tell me about a time you failed.")
    assert "Tell me about a time you failed." in prompt
    assert "STAR" in prompt


def test_build_prompt_includes_context_block_when_present():
    prompt = build_prompt(
        context="Interviewer: let's talk about teamwork.",
        question="Give an example.",
    )
    assert "Recent conversation:" in prompt
    assert "Interviewer: let's talk about teamwork." in prompt
    assert "Give an example." in prompt


def test_build_prompt_omits_context_block_when_context_empty():
    prompt = build_prompt(context="", question="What is a hash map?")
    assert "Recent conversation:" not in prompt
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_llm_client.py -v
```

Expected: FAIL — `src/llm_client.py` doesn't exist yet.

- [ ] **Step 3: Write implementation**

`src/llm_client.py`:

```python
import json
from collections.abc import Iterator

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

SYSTEM_PROMPT = (
    "You are a calm, concise interview coach helping someone practice mock "
    "interviews out loud with a friend. You'll be given the last part of the "
    "conversation for context and the question just asked. Respond with a "
    "short spoken-style answer the user can read and say naturally: use a "
    "STAR structure (Situation, Task, Action, Result) for behavioral "
    "questions, and a clear structured explanation (with a short code "
    "snippet only if truly needed) for technical questions. Keep it under "
    "150 words. Do not restate the question."
)


def build_prompt(context: str, question: str) -> str:
    context = context.strip()
    context_block = f"Recent conversation:\n{context}\n\n" if context else ""
    return f"{SYSTEM_PROMPT}\n\n{context_block}Question: {question}\n\nAnswer:"


def stream_answer(question: str, context: str = "", model: str = "llama3.2") -> Iterator[str]:
    payload = {
        "model": model,
        "prompt": build_prompt(context, question),
        "stream": True,
    }
    with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=30) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("response"):
                yield chunk["response"]
            if chunk.get("done"):
                break
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_llm_client.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Manual — verify streaming against live Ollama**

With `ollama serve` running and `llama3.2` pulled (from Task 1):

```bash
python -c "
from src.llm_client import stream_answer
for chunk in stream_answer('What is a hash map?'):
    print(chunk, end='', flush=True)
print()
"
```

Expected: a coherent streamed answer prints token-by-token, ending in a newline, no exceptions.

- [ ] **Step 6: Commit**

```bash
git add src/llm_client.py tests/test_llm_client.py
git commit -m "feat: add Ollama streaming client and prompt builder"
```

---

### Task 4: Transcriber + speech fixture

**Files:**
- Create: `src/transcriber.py`
- Create: `tests/fixtures/hello.wav`
- Test: `tests/test_transcriber.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str`. `app.py` (Task 8) calls this with the float32 array converted from each finalized utterance.

- [ ] **Step 1: Generate the speech fixture using macOS's built-in `say` and `afconvert`**

```bash
mkdir -p tests/fixtures
say -o /tmp/hello.aiff "Hello, can you tell me about yourself?"
afconvert -f WAVE -d LEI16@16000 -c 1 /tmp/hello.aiff tests/fixtures/hello.wav
```

Expected: `tests/fixtures/hello.wav` exists, is mono 16-bit PCM at 16000Hz (verify with `afinfo tests/fixtures/hello.wav` — should show `16000 Hz`, `1 ch`).

- [ ] **Step 2: Write the failing test**

`tests/test_transcriber.py`:

```python
from pathlib import Path

import soundfile as sf

from src.transcriber import transcribe

FIXTURES = Path(__file__).parent / "fixtures"


def test_transcribe_recognizes_known_speech():
    audio, sample_rate = sf.read(str(FIXTURES / "hello.wav"), dtype="float32")
    assert sample_rate == 16000

    text = transcribe(audio, sample_rate)

    assert "hello" in text.lower()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_transcriber.py -v
```

Expected: FAIL — `src/transcriber.py` doesn't exist yet.

- [ ] **Step 4: Write implementation**

`src/transcriber.py`:

```python
import numpy as np
from faster_whisper import WhisperModel

_MODEL: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = WhisperModel("base.en", device="auto", compute_type="int8")
    return _MODEL


def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str:
    model = _get_model()
    segments, _ = model.transcribe(audio, language="en")
    return " ".join(segment.text.strip() for segment in segments).strip()
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_transcriber.py -v
```

Expected: 1 passed (first run downloads the `base.en` model — allow a minute).

- [ ] **Step 6: Commit**

```bash
git add src/transcriber.py tests/test_transcriber.py tests/fixtures/hello.wav
git commit -m "feat: add faster-whisper transcriber with speech fixture"
```

---

### Task 5: VAD utterance segmenter

**Files:**
- Create: `src/audio_capture.py` (segmenter portion only — device I/O added in Task 6)
- Test: `tests/test_audio_capture.py`

**Interfaces:**
- Consumes: `tests/fixtures/hello.wav` (from Task 4) as real speech input for the test.
- Produces: constants `FRAME_MS = 30`, `SAMPLE_RATE = 16000`, `FRAME_SIZE`, `SILENCE_TRAILING_MS = 1000`, and `class UtteranceSegmenter` with `.push_frame(frame_bytes: bytes) -> bytes | None`. Task 6 adds `find_device_index` and `open_capture_stream` to this same file; Task 8's `CaptureThread` uses all four names.

- [ ] **Step 1: Write the failing test**

`tests/test_audio_capture.py`:

```python
from pathlib import Path

import soundfile as sf

from src.audio_capture import FRAME_SIZE, SAMPLE_RATE, UtteranceSegmenter

FIXTURES = Path(__file__).parent / "fixtures"


def _pcm_bytes(frame):
    ints = (frame * 32767).astype("<i2")
    return ints.tobytes()


def _frames(audio, frame_size):
    for start in range(0, len(audio) - frame_size + 1, frame_size):
        yield audio[start:start + frame_size]


def test_segmenter_finalizes_utterance_after_trailing_silence():
    audio, sample_rate = sf.read(str(FIXTURES / "hello.wav"), dtype="float32")
    assert sample_rate == SAMPLE_RATE

    segmenter = UtteranceSegmenter()
    for frame in _frames(audio, FRAME_SIZE):
        segmenter.push_frame(_pcm_bytes(frame))

    silence_frame = b"\x00\x00" * FRAME_SIZE
    utterance = None
    for _ in range(40):  # 40 * 30ms = 1200ms of silence
        result = segmenter.push_frame(silence_frame)
        if result is not None:
            utterance = result
            break

    assert utterance is not None
    assert len(utterance) > 0


def test_segmenter_ignores_leading_silence():
    segmenter = UtteranceSegmenter()
    silence_frame = b"\x00\x00" * FRAME_SIZE

    for _ in range(10):
        assert segmenter.push_frame(silence_frame) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_audio_capture.py -v
```

Expected: FAIL — `src/audio_capture.py` doesn't exist yet.

- [ ] **Step 3: Write implementation**

`src/audio_capture.py`:

```python
import webrtcvad

FRAME_MS = 30
SAMPLE_RATE = 16000
FRAME_SIZE = int(SAMPLE_RATE * FRAME_MS / 1000)
SILENCE_TRAILING_MS = 1000
SILENCE_TRAILING_FRAMES = SILENCE_TRAILING_MS // FRAME_MS


class UtteranceSegmenter:
    def __init__(self, vad_aggressiveness: int = 2):
        self._vad = webrtcvad.Vad(vad_aggressiveness)
        self._speech_frames: list[bytes] = []
        self._trailing_silence = 0

    def push_frame(self, frame_bytes: bytes) -> bytes | None:
        is_speech = self._vad.is_speech(frame_bytes, SAMPLE_RATE)

        if is_speech:
            self._speech_frames.append(frame_bytes)
            self._trailing_silence = 0
            return None

        if not self._speech_frames:
            return None

        self._trailing_silence += 1
        if self._trailing_silence < SILENCE_TRAILING_FRAMES:
            return None

        utterance = b"".join(self._speech_frames)
        self._speech_frames = []
        self._trailing_silence = 0
        return utterance
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_audio_capture.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/audio_capture.py tests/test_audio_capture.py
git commit -m "feat: add VAD-based utterance segmenter"
```

---

### Task 6: PyAudio capture integration (BlackHole device I/O)

**Files:**
- Modify: `src/audio_capture.py` (add device I/O functions alongside the Task 5 segmenter)

**Interfaces:**
- Consumes: `FRAME_SIZE`, `SAMPLE_RATE` (from Task 5, same file).
- Produces: `find_device_index(pa: pyaudio.PyAudio, name_substring: str = "BlackHole") -> int` and `open_capture_stream(pa: pyaudio.PyAudio, device_index: int) -> pyaudio.Stream`. Task 8's `CaptureThread` calls both.

This part needs a real BlackHole device and a live audio source, so it's verified manually rather than with an automated test.

- [ ] **Step 1: Add device I/O functions and a manual self-check to `src/audio_capture.py`**

Append to `src/audio_capture.py`:

```python
import sys

import pyaudio


def find_device_index(pa: pyaudio.PyAudio, name_substring: str = "BlackHole") -> int:
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if name_substring.lower() in info["name"].lower() and info["maxInputChannels"] > 0:
            return i
    available = [pa.get_device_info_by_index(i)["name"] for i in range(pa.get_device_count())]
    raise RuntimeError(
        f"No input device matching '{name_substring}' found. Available devices: {available}"
    )


def open_capture_stream(pa: pyaudio.PyAudio, device_index: int) -> pyaudio.Stream:
    return pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=FRAME_SIZE,
    )


def _manual_check():
    pa = pyaudio.PyAudio()
    try:
        device_index = find_device_index(pa)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    print(f"Reading from device index {device_index} for 5 seconds...")
    stream = open_capture_stream(pa, device_index)
    frame_count = 0
    for _ in range(int(5000 / FRAME_MS)):
        stream.read(FRAME_SIZE, exception_on_overflow=False)
        frame_count += 1
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print(f"Captured {frame_count} frames successfully.")


if __name__ == "__main__":
    _manual_check()
```

- [ ] **Step 2: Manual verification**

With the Multi-Output Device active (Task 1) and something playing audio through it (e.g. a YouTube video, or just system audio):

```bash
python src/audio_capture.py
```

Expected: prints `Reading from device index N for 5 seconds...` then `Captured 166 frames successfully.` (5000ms / 30ms ≈ 166). No `RuntimeError`.

If it raises `RuntimeError: No input device matching 'BlackHole' found`, re-check the BlackHole install from Task 1 Step 5.

- [ ] **Step 3: Re-run the Task 5 automated tests to confirm nothing broke**

```bash
pytest tests/test_audio_capture.py -v
```

Expected: still 2 passed (device I/O additions don't affect the segmenter tests).

- [ ] **Step 4: Commit**

```bash
git add src/audio_capture.py
git commit -m "feat: add BlackHole device discovery and capture stream"
```

---

### Task 7: Overlay window

**Files:**
- Create: `src/overlay.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `class OverlayWindow(QWidget)` with `.append_text(chunk: str) -> None`, `.show_error(message: str) -> None`, `.clear() -> None`. Task 8's `Worker` thread calls these (they're signal-based, so safe to call from a non-GUI thread).

This is a GUI component with a macOS-native screen-capture-exclusion call that's inherently hard to unit test — verified manually.

- [ ] **Step 1: Write `src/overlay.py`**

```python
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
            pass  # best-effort; overlay still functions if this fails

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
```

- [ ] **Step 2: Manual verification**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
from src.overlay import OverlayWindow

app = QApplication(sys.argv)
win = OverlayWindow()
win.show()
win.append_text('Testing the overlay window. ')
win.append_text('More text streams in here.')
sys.exit(app.exec())
"
```

Checklist while it's running:
1. A translucent dark rounded box appears near the top-left with the test text — confirms rendering.
2. Click on where the overlay is — confirms it's click-through (the click should reach whatever window is behind it, not the overlay).
3. Start a QuickTime Player **File → New Screen Recording**, record 5 seconds with the overlay visible, stop, and play it back — the overlay text should **not** appear in the recording. If it does appear, the pyobjc exclusion isn't taking effect; note this as a known limitation rather than silently shipping it broken.

- [ ] **Step 3: Commit**

```bash
git add src/overlay.py
git commit -m "feat: add PyQt6 overlay window with screen-capture exclusion"
```

---

### Task 8: End-to-end app wiring

**Files:**
- Create: `src/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `SessionLogger` (Task 2), `build_prompt`/`stream_answer` (Task 3), `transcribe` (Task 4), `UtteranceSegmenter`/`FRAME_SIZE`/`SAMPLE_RATE`/`find_device_index`/`open_capture_stream` (Tasks 5–6), `OverlayWindow` (Task 7).
- Produces: `pcm_bytes_to_float32(data: bytes) -> np.ndarray`, `trim_context(context: str, new_text: str, word_limit: int = 200) -> str`, `class Worker(threading.Thread)`, `class CaptureThread(threading.Thread)`, `main()`. This is the final integration point — nothing later depends on it.

- [ ] **Step 1: Write the failing test for the pure `trim_context` helper**

`tests/test_app.py`:

```python
from src.app import trim_context


def test_trim_context_keeps_last_n_words():
    context = " ".join(f"word{i}" for i in range(190))
    new_text = " ".join(f"new{i}" for i in range(20))

    trimmed = trim_context(context, new_text, word_limit=200)

    words = trimmed.split()
    assert len(words) == 200
    assert words[-1] == "new19"


def test_trim_context_handles_empty_context():
    trimmed = trim_context("", "hello world", word_limit=200)
    assert trimmed == "hello world"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_app.py -v
```

Expected: FAIL — `src/app.py` doesn't exist yet.

- [ ] **Step 3: Write `src/app.py`**

```python
import queue
import sys
import threading
from pathlib import Path

import numpy as np
import pyaudio
from PyQt6.QtWidgets import QApplication

from src.audio_capture import (
    FRAME_SIZE,
    SAMPLE_RATE,
    UtteranceSegmenter,
    find_device_index,
    open_capture_stream,
)
from src.llm_client import stream_answer
from src.overlay import OverlayWindow
from src.session_logger import SessionLogger
from src.transcriber import transcribe

CONTEXT_WORD_LIMIT = 200


def pcm_bytes_to_float32(data: bytes) -> np.ndarray:
    ints = np.frombuffer(data, dtype="<i2")
    return ints.astype(np.float32) / 32768.0


def trim_context(context: str, new_text: str, word_limit: int = CONTEXT_WORD_LIMIT) -> str:
    words = (context + " " + new_text).split()
    return " ".join(words[-word_limit:])


class Worker(threading.Thread):
    def __init__(self, utterance_queue: "queue.Queue[bytes]", overlay: OverlayWindow, logger: SessionLogger):
        super().__init__(daemon=True)
        self.utterance_queue = utterance_queue
        self.overlay = overlay
        self.logger = logger
        self.context = ""

    def run(self):
        while True:
            pcm_bytes = self.utterance_queue.get()
            audio = pcm_bytes_to_float32(pcm_bytes)
            question = transcribe(audio, SAMPLE_RATE)
            if not question.strip():
                continue

            self.overlay.clear()
            try:
                answer_parts = []
                for chunk in stream_answer(question, self.context):
                    answer_parts.append(chunk)
                    self.overlay.append_text(chunk)
            except Exception as exc:
                self.overlay.show_error(f"Ollama error: {exc}")
                continue

            answer = "".join(answer_parts)
            self.context = trim_context(self.context, f"Q: {question} A: {answer}")
            self.logger.log(question, answer)


class CaptureThread(threading.Thread):
    def __init__(self, utterance_queue: "queue.Queue[bytes]"):
        super().__init__(daemon=True)
        self.utterance_queue = utterance_queue
        self._stop = threading.Event()

    def run(self):
        pa = pyaudio.PyAudio()
        device_index = find_device_index(pa)
        stream = open_capture_stream(pa, device_index)
        segmenter = UtteranceSegmenter()
        try:
            while not self._stop.is_set():
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
                utterance = segmenter.push_frame(frame)
                if utterance is not None:
                    self.utterance_queue.put(utterance)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def stop(self):
        self._stop.set()


def main():
    app = QApplication(sys.argv)
    overlay = OverlayWindow()
    overlay.show()

    logger = SessionLogger(Path("sessions"))
    utterance_queue: "queue.Queue[bytes]" = queue.Queue()

    worker = Worker(utterance_queue, overlay, logger)
    worker.start()

    capture = CaptureThread(utterance_queue)
    capture.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_app.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```

Expected: all tests across every task pass (session logger, LLM client, transcriber, audio capture segmenter, app).

- [ ] **Step 6: Manual end-to-end verification**

1. Set system audio output to the Multi-Output Device (Task 1).
2. Run `ollama serve` (if not already running as a background service).
3. Start a real or test video call with your friend (or play a recorded question through the call app).
4. `python src/app.py`.
5. Have your friend ask a question, then go quiet.
6. Confirm: ~1s after they stop talking, the overlay clears and streams a coached answer word-by-word.
7. Confirm: `sessions/<timestamp>.jsonl` now has one line with that question and answer.
8. Ask a follow-up question and confirm the answer reflects context from the previous exchange (rolling context working).

- [ ] **Step 7: Commit**

```bash
git add src/app.py tests/test_app.py
git commit -m "feat: wire audio capture, transcription, LLM, overlay, and logging into app.py"
```

---

## Self-Review

**Spec coverage:**
- Audio capture (BlackHole, in-memory, no disk writes) → Tasks 6, 8. ✓
- VAD segmentation (~1s trailing silence) → Task 5. ✓
- STT via faster-whisper, in-memory arrays → Task 4. ✓
- LLM via Ollama streaming, rolling ~200-word context, STAR/technical coaching prompt → Tasks 3, 8. ✓
- Overlay: frameless/translucent/always-on-top, screen-capture exclusion, click-through → Task 7. ✓
- Session logging to JSONL → Tasks 2, 8. ✓
- Error handling (Ollama unreachable, empty transcription, missing BlackHole device, worker exceptions) → Task 8 (`Worker.run` try/except + skip-if-empty), Task 6 (`find_device_index` raises with device list). ✓
- Guided setup walkthrough → Task 1. ✓
- Non-goal (no mic/own-voice capture) → not implemented anywhere, correctly omitted. ✓

**Placeholder scan:** no TBD/TODO markers; every step has runnable code or an exact command with expected output.

**Type consistency:** `UtteranceSegmenter.push_frame` returns `bytes | None` consistently between Task 5 and its use in Task 8's `CaptureThread`. `transcribe(audio: np.ndarray, sample_rate: int)` signature matches its Task 4 definition and Task 8 call site. `stream_answer(question, context, model)` matches between Task 3 and Task 8. `SessionLogger.log(question, answer, timestamp=None)` matches between Task 2 and Task 8.
