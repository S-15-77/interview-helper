# Mock Interview Overlay — Design

## Purpose

A fully local, offline desktop tool for practicing mock interviews with a friend
over a video call (Zoom/Meet/etc.). The friend asks interview questions live;
the app transcribes their voice, generates a coached answer with a local LLM,
and streams it onto a floating overlay so the user can read it while answering
out loud. No audio or transcript ever leaves the machine. This is a self-study
aid for practice sessions with a consenting friend, not a tool for use during a
real employer's interview.

## Non-goals

- Not for use during real/live job interviews with an actual employer.
- Not transcribing or logging the user's own mic audio (only the friend's
  side, captured via BlackHole from the call). Adding the user's own side is a
  possible future enhancement, not in scope now.
- Not a general-purpose meeting assistant — overlay behavior (screen-share
  exclusion, click-through) is tuned specifically for this practice-session
  use case.

## Environment assumptions

- macOS, Apple Silicon (M-series), 16GB+ RAM.
- Friend is remote on a video call; their voice comes through the user's
  speakers/headphones.
- User sometimes screen-shares (e.g. IDE) for mock coding rounds.
- Ollama, BlackHole, and Python dependencies are installed per the README
  setup walkthrough (guided, included in this project).

## Architecture

Five components wired by one Python process, all local:

1. **Audio capture** (`src/audio_capture.py`) — PyAudio reads continuously
   from a BlackHole virtual input device (fed by the video call's system
   audio output) in small frames (30ms), directly into memory. No `.wav`
   files are written.
2. **VAD segmentation** (`src/audio_capture.py`) — `webrtcvad` classifies
   each frame as speech/silence. Consecutive speech frames accumulate into a
   candidate utterance buffer. After ~1s of continuous silence following
   speech, the utterance is finalized and handed off via a queue; the frame
   buffer resets for the next utterance.
3. **STT** (`src/transcriber.py`) — `faster-whisper` (`base.en` model)
   transcribes the utterance's raw float32 numpy array directly (no disk
   round-trip). Empty/whitespace transcriptions are dropped (silence
   misfire) and never reach the LLM.
4. **LLM** (`src/llm_client.py`) — Ollama, default model `llama3.2:3b`
   (`llama3.1:8b` optional for stronger answers at some latency cost, viable
   given 16GB+ RAM). Prompt = system instructions (coach persona: STAR
   structure for behavioral questions, structured explanations for technical
   questions, mixed-type handling) + a rolling transcript context (last
   ~200 words, deque-capped) + the latest question. Calls
   `http://localhost:11434/api/generate` with `stream: true` and yields
   tokens as they arrive.
5. **Overlay** (`src/overlay.py`) — PyQt6, frameless / translucent /
   always-on-top window, positioned top-right by default, word-wrapped
   auto-resizing label. On macOS, `NSWindow.sharingType` is set to
   `NSWindowSharingTypeNone` via `pyobjc` so the window is excluded from
   screen-share capture (relevant since the user sometimes shares their
   screen for coding rounds — same mechanism legitimate teleprompter/password
   manager apps use to exclude their own UI from recordings). The window is
   click-through (`ignoresMouseEvents`) so it never steals focus from the
   call window, with a global hotkey to toggle visibility.

**Session logging** (`src/session_logger.py`): every (question, answer,
timestamps) triple is appended as one JSON line to
`sessions/<start-time>.jsonl` as it completes — append-only, so a crash
mid-session loses nothing already answered.

**Threading model**: main thread runs the Qt event loop only. A background
thread owns audio capture + VAD segmentation. Finalized utterances are handed
to a worker thread (via a queue) that runs STT → LLM streaming → emits Qt
signals back to the overlay for thread-safe UI updates. The UI never blocks
on audio or inference.

## Data flow (step by step)

1. App starts → capture thread opens the BlackHole input stream, reads 30ms
   frames continuously into an in-memory ring buffer.
2. `webrtcvad` tags frames; consecutive speech frames accumulate.
3. After ~1s of trailing silence, the accumulated utterance buffer is put on
   a queue; the frame accumulator resets.
4. Worker thread pulls the utterance, runs `faster-whisper` → text. If
   empty/whitespace, discard and go back to step 2.
5. Append transcribed text to the rolling context deque (~200 words cap).
6. Build the LLM prompt (system + rolling context + new question), POST to
   Ollama with streaming enabled.
7. As tokens stream in, emit a Qt signal per chunk; overlay label appends
   text live.
8. On stream completion, `session_logger` appends one JSON line with
   timestamp, question, and full answer.
9. Loop back to step 2.

## Error handling

- Ollama unreachable or model not pulled → overlay shows a one-line inline
  error message; capture loop keeps running so the next utterance can still
  be attempted once Ollama is available.
- Empty/whitespace transcription → silently skipped, nothing logged, no LLM
  call made.
- BlackHole device not found at startup → fail fast with a clear error
  listing available audio input devices (so the user can fix Audio MIDI
  Setup / Multi-Output Device config before the loop starts).
- Any exception inside the worker thread is caught and logged to stderr; the
  session continues rather than crashing on one bad utterance.

## File structure

```
interview-helper/
  README.md              # setup walkthrough: Ollama, BlackHole, Multi-Output
                          # Device, Python venv, run steps
  requirements.txt
  .gitignore              # sessions/, __pycache__, venv/
  src/
    audio_capture.py      # BlackHole reader + VAD segmenter
    transcriber.py         # faster-whisper wrapper
    llm_client.py            # Ollama streaming client + prompt building
    overlay.py                # PyQt6 window
    session_logger.py         # JSONL writer
    app.py                      # wires everything together, entry point
  tests/                         # one lightweight self-check per non-trivial
                                  # module (assert-based, no framework)
    fixtures/
      hello.wav                  # short known-speech fixture for STT test
  sessions/                       # gitignored, created at runtime
```

## Testing (self-checks, no framework)

- `tests/test_transcriber.py` — feeds `fixtures/hello.wav` through
  `faster-whisper`, asserts non-empty recognizable text.
- `tests/test_llm_client.py` — asserts the streaming generator yields
  non-empty concatenated text against a running local Ollama instance.
- `tests/test_session_logger.py` — writes one entry, reads the JSONL file
  back, asserts fields round-trip.
- `src/audio_capture.py` — `__main__` self-check feeding synthetic
  speech-then-silence energy patterns into the VAD segmenter, asserting an
  utterance boundary is detected at the expected frame count.

## Setup (guided walkthrough, delivered in README.md)

1. Install Ollama, `ollama pull llama3.2`, confirm the service runs.
2. `brew install blackhole-2ch`.
3. Create a macOS Multi-Output Device in Audio MIDI Setup combining
   BlackHole 2ch + the user's normal headphones/speakers, so the call audio
   is both heard and captured; set it as the system output before each
   session.
4. Python venv + `pip install -r requirements.txt`.
5. Grant microphone/audio permission to the terminal/Python on first run.
6. `python src/app.py` to start a session.
