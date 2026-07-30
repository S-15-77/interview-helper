# Mock Interview Overlay — Setup & Run Guide

This tool listens to a friend's voice during a video call (Google Meet, Zoom,
etc.), transcribes what they ask, and shows a coached answer in a small
overlay on your screen. Everything runs locally on your Mac — nothing is
sent to the cloud.

You don't need to read or write any code to set this up or use it. If you
ever want to change how it behaves — a different AI model, your own
background info, a different coaching style — you do that by describing what
you want to **Claude Code** (Anthropic's AI coding assistant), not by editing
files yourself. If you don't have it yet:
```
npm install -g @anthropic-ai/claude-code
```
Then, from inside this project folder, run `claude` and just tell it what
you want changed in plain English — the sections below tell you which files
to point it at.

Follow the steps below in Terminal (Applications → Utilities → Terminal).

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

### d) Download the AI model (one-time, ~1.9GB)
```
ollama serve &
ollama pull qwen2.5:3b-instruct
```
Check it worked: `ollama list` should show `qwen2.5:3b-instruct` in the list.

This is the fast option — tuned for real-time answers, roughly 2x the speed of the larger
model, at the cost of occasionally missing an instruction (like the target answer length).
Want more reliable answers on hard technical questions instead of speed? Run:
```
ollama pull qwen2.5:7b-instruct
```
then open Claude Code in this folder and say something like *"switch the default Ollama
model to qwen2.5:7b-instruct"* — it'll make the change for you.

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

You'll select this device as your output before each session (step 5 below).

---

## 3. Personalize your answers (optional, one-time)

By default, the tool answers behavioral/HR questions ("Tell me about yourself") with generic
placeholder scenarios — it doesn't know anything about you until you tell it.

Open `my_data/profile.md` in any text editor and fill in your real name, role, experience,
key projects, and where you want to be in 5 years. Every file in `my_data/` (you can add
more, e.g. `target_job.txt` with a job posting you're prepping for) is read fresh before
every answer, so there's nothing to restart. This folder never gets committed to git — it's
your personal data, kept local to your machine.

Don't want to write it yourself? Open Claude Code in this folder, paste your resume or LinkedIn
summary, and say *"fill in my_data/profile.md with this."*

## 4. Customize the coaching style (optional)

The `skills/` folder holds general interview-coaching rules — how to handle a "what's your
weakness" question, how to structure an answer, and so on. A couple are already included
(`skills/hr_playbook.md`, `skills/communication_coach.md`) as examples. Unlike `my_data/`,
these files aren't personal — they're general strategy, so feel free to share/commit them.

Found a YouTube video or article with interview tips you like? Open Claude Code in this
folder, paste the tips in, and say *"add this as a skill."* It'll turn it into a new file in
`skills/` for you — no need to touch the Python code or the AI prompt directly.

---

## 5. Every time you want to use it

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
into the overlay. Drag the header bar to move the window anywhere on screen,
and click-drag over the answer text to select and copy it.

Each session's questions and answers are saved to a `sessions/` folder as a
timestamped log.

To stop: press `Ctrl+C` in the terminal running the app.

---

## Troubleshooting

- **"Ollama error: ... Connection refused"** in the overlay — Ollama isn't
  running. Run `ollama serve` in a terminal and leave it open, then try
  again (no need to restart the app).
- **A `pkg_resources is deprecated` warning on startup** — harmless, ignore it.
- **"No input device matching 'BlackHole' found"** — BlackHole isn't
  installed, or you skipped step 1c. Run `brew install blackhole-2ch` and
  try again.
- **You can't hear the call yourself** — double check both your speakers
  *and* BlackHole 2ch are checked in the Multi-Output Device (step 2.3), and
  that it's selected as your Mac's output (step 5).
