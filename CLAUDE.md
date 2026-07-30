# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
It doubles as the architecture doc for human contributors — read it before opening a PR.

## What this is

A fully local, macOS-only mock-interview practice tool. It listens to a friend's voice
during a video call (via a BlackHole virtual audio device), transcribes their question,
and streams a coached spoken-answer script onto a floating always-on-top overlay. Nothing
leaves the machine — audio, transcription, and the LLM all run locally. Per the README,
this is explicitly for practicing with a consenting friend, not for use during a real
employer interview.

## Commands

```bash
# one-time setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

ollama serve &                        # must be running before the app starts
ollama pull qwen2.5:3b-instruct       # current default model (src/llm_client.py preload/stream_answer)

# run (must use -m from the project root — `python src/app.py` fails with
# ModuleNotFoundError because src/ modules use absolute `from src.xxx import` imports)
python -m src.app

# tests
python -m pytest tests/                          # pytest.ini sets pythonpath=. for `src.` imports
python -m pytest tests/test_llm_client.py -v      # single file
python -m pytest tests/test_llm_client.py::test_name  # single test

# GUI tests (tests/test_overlay.py) need an offscreen Qt platform:
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_overlay.py
```

External system deps (Homebrew, not in requirements.txt): `ollama`, `portaudio`,
`blackhole-2ch`. `audio_capture.find_device_index` looks for an input device whose name
contains "BlackHole" — the app will refuse to start without it configured as a
Multi-Output Device (see README/SETUP.md for the Audio MIDI Setup steps).

## Architecture

Two background threads feed a PyQt6 GUI on the main thread; there is no web server.

**Pipeline**, one utterance at a time:

1. `audio_capture.py` — `CaptureThread` reads 30ms PCM frames from the BlackHole input
   stream and feeds them to `UtteranceSegmenter`, which uses `webrtcvad` (aggressiveness 3,
   the strictest setting) to buffer speech frames and cut an utterance once ~1s of trailing
   silence is seen. Utterances shorter than `MIN_SPEECH_MS` (300ms) are dropped as noise
   rather than returned — Whisper otherwise "confidently" hallucinates text for short
   noise/comfort-noise blips (e.g. from a muted mic) that VAD mis-flagged as speech.
2. `app.py`'s `Worker` thread pulls utterances off that queue, converts PCM to float32
   (`pcm_bytes_to_float32`), and calls `transcriber.transcribe`.
3. `transcriber.py` lazy-loads a singleton `faster_whisper.WhisperModel("base.en")` and
   transcribes with `vad_filter=True` (faster-whisper's own Silero VAD pass) — same
   hallucination problem as above, second layer of defense. `preload()` is called once at
   startup so the first real utterance doesn't pay the model-load cost.
4. `llm_client.py`'s `stream_answer` builds a prompt from a large fixed `SYSTEM_PROMPT`
   (behavioral/technical answer rules, STAR method, output-format constraints), any
   `skills/` files, the candidate's personalization files, recent conversation context, and
   the question — then streams tokens from a local Ollama server (`POST /api/generate`),
   capped with `options.num_predict` so a runaway generation can't add unbounded latency.
5. The `Worker` forwards each streamed chunk to the overlay and appends the Q/A pair to
   `SessionLogger`, which writes one JSON line per turn to `sessions/<start-timestamp>.jsonl`.
6. `Worker` also maintains a rolling `context` string (`trim_context`, capped at
   `CONTEXT_WORD_LIMIT` words) passed into the next `stream_answer` call for continuity.

**Personalization**: `llm_client.load_knowledge_base()` re-reads every `.md`/`.txt` file
under `my_data/` (recursively) on *every* question and injects it into the prompt as
"Candidate Profile". `my_data/` is gitignored except its README template, so real resume
data never gets committed.

**Skills**: `llm_client.load_skills()` does the same thing for `skills/` — general
interview-coaching rules and question-type playbooks (e.g. `skills/hr_playbook.md`), meant
to be added instead of editing `SYSTEM_PROMPT` directly. Both functions share the same
directory-reading logic via `_read_markdown_dir()`. Unlike `my_data/`, `skills/` is **not**
gitignored — it's general strategy, not personal data, so it's meant to be committed and
shared. Everything in it is injected into *every* question regardless of relevance, so it
has a real cost: a weaker local model (see below) has a limited budget for how many rules
it reliably follows at once — more skill files can make behavior less consistent, not more.

**Threading/UI**: `OverlayWindow` (in `overlay.py`) is only ever mutated from the Qt main
thread — the `Worker`/`CaptureThread` background threads talk to it exclusively through
`pyqtSignal`s (`question_started`, `text_appended`, `error_shown`) defined on
`OverlaySignals`, not by calling its methods directly. It's a frameless, translucent,
always-on-top `QWidget` (deliberately *not* `Qt.WindowType.Tool` — that maps to a native
NSPanel that Qt keeps forcing back to "hide on deactivate", which fought a real bug where
the overlay vanished when the browser got focus). `showEvent` bridges to the real AppKit
`NSWindow` via `pyobjc` (`_configure_native_window`) to exclude the window from screen
recordings and force it above full-screen call windows — this bridge assumes a real Cocoa
window exists, so calling `.show()` on `OverlayWindow` under `QT_QPA_PLATFORM=offscreen`
(e.g. in tests) segfaults. `tests/test_overlay.py` avoids this deliberately by never
calling `.show()`. The header bar (`_DragHandle`) is a real click-drag window mover; the
answer label has `TextSelectableByMouse | TextSelectableByKeyboard` so users can select and
copy the streamed answer.

**Model choice**: the Ollama model is `llm_client.DEFAULT_MODEL`, not read from a config file
or env var — both `preload()` and `stream_answer()` default to it, so swapping models is a
one-line change. `qwen2.5:3b-instruct` (current default) measured ~2x the tok/s of
`qwen2.5:7b-instruct` on this project's dev machine, at the cost of looser
instruction-following (word-count targets, avoiding filler openers) — a real trade-off, not
a strict upgrade.

## Contributing

- Run `python -m pytest tests/` before opening a PR — there's no CI configured yet, so this
  is the only automated gate.
- No linter/formatter is configured; match the style already in the file you're editing.
- Comments in this codebase explain *why*, not *what* — they're reserved for non-obvious
  workarounds, rejected alternatives, or platform quirks (see the `Qt.WindowType.Tool` and
  `_configure_native_window` comments in `overlay.py` for the pattern). Don't add comments
  that restate the code.
- New runtime dependencies go in `requirements.txt`; new external/Homebrew deps should be
  documented in README.md/SETUP.md, same as `ollama`/`portaudio`/`blackhole-2ch` are now.
- Never add files to `my_data/` other than its own `README.md` template, and never remove it
  from `.gitignore` — that folder is where real personal resume/profile data lives locally
  and must never end up in a commit or a PR diff. `skills/` is the opposite: general
  interview-coaching rules are expected to be committed there — that's the intended way to
  extend behavior without touching `SYSTEM_PROMPT` in `src/llm_client.py`.
- This repo has no `LICENSE` file yet — add one before actually opening it up, since without
  one the default is "all rights reserved" and others can't legally reuse or contribute code.
