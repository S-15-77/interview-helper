# Mock Interview Overlay — Setup & Run Guide

This tool listens to a friend's voice during a video call (Google Meet, Zoom,
etc.), transcribes what they ask, and shows a coached answer in a small
overlay on your screen. Everything runs locally on your Mac — nothing is
sent to the cloud.

You don't need to read or edit any code. Just follow the steps below in
Terminal (Applications → Utilities → Terminal).

---

## 1. One-time install

### a) Get the project
```
git clone https://github.com/S-15-77/interview-helper.git
cd interview-helper
```

### b) Install Homebrew (skip if you already have it)
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### c) Install system tools
```
brew install ollama portaudio blackhole-2ch
```

### d) Download the AI model (one-time, ~2GB)
```
ollama serve &
ollama pull llama3.2
```
Check it worked: `ollama list` should show `llama3.2` in the list.

### e) Set up the Python environment
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Route call audio to the app (one-time setup, per Mac)

The app "hears" the call through a virtual audio device (BlackHole), but you
still want to hear the call yourself — so you combine both into one output.

1. Open **Audio MIDI Setup** (Spotlight search → type it).
2. Click the **+** at the bottom-left → **Create Multi-Output Device**.
3. In the device list, check the box next to **both**:
   - your normal speakers/headphones
   - **BlackHole 2ch**
4. Rename it (double-click the name) to something like "Call + BlackHole".
5. Leave the **Sample Rate** at whatever it defaults to (e.g. 48.0 kHz) —
   no need to change it.

You'll select this device as your output before each session (step 4 below).

---

## 3. Every time you want to use it

### Start Ollama (if it's not already running)
```
ollama serve
```
Leave this running in its own terminal tab/window.

### Set your Mac's audio output
**System Settings → Sound → Output** → select the Multi-Output Device you
made in step 2 (e.g. "Call + BlackHole").

### Start the app
In a new terminal tab, from the project folder:
```
cd interview-helper
source venv/bin/activate
python -m src.app
```

The first time it runs, macOS may ask for microphone permission — allow it.

A small dark overlay box will appear near the top-left of your screen. Join
your call as normal. When your friend asks something, the app waits for
~1 second of silence, transcribes the question, and streams a coached answer
into the overlay.

Each session's questions and answers are saved to a `sessions/` folder as a
timestamped log.

To stop: press `Ctrl+C` in the terminal running the app.

---

## Troubleshooting

- **"Ollama error: ... Connection refused"** in the overlay — Ollama isn't
  running. Run `ollama serve` in a terminal and leave it open, then try
  again (no need to restart the app).
- **Overlay disappears quickly** — that's normal; it clears itself as soon
  as the next question is detected.
- **A `pkg_resources is deprecated` warning on startup** — harmless, ignore it.
- **"No input device matching 'BlackHole' found"** — BlackHole isn't
  installed, or you skipped step 1c. Run `brew install blackhole-2ch` and
  try again.
- **You can't hear the call yourself** — double check both your speakers
  *and* BlackHole 2ch are checked in the Multi-Output Device (step 2.3), and
  that it's selected as your Mac's output (step 3).
