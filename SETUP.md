# Mock Interview Overlay — Setup & Run Guide

This tool listens to a friend's voice during a video call (Google Meet, Zoom,
etc.), transcribes what they ask, and shows a coached answer in a small
overlay on your screen. Everything runs locally on your Mac — nothing is
sent to the cloud.

You don't need to read or write Python code to configure or validate the app. A setup
window opens on every launch and saves your choices locally.

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
then select `qwen2.5:7b-instruct` from the app's setup window.

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

## 3. Personalize your answers (optional, per application)

The tool never presents a generic placeholder story as your real experience. If a
behavioral question needs details that are absent from your profile, it shows a clearly
marked STAR framework for you to complete.

Create a separate application profile containing the exact resume and JD used for that role:

```
mkdir -p my_data/applications
cp -R templates/application_profile my_data/applications/acme-compiler-engineer
```

Edit `resume.md`, `job_description.md`, `technical_context.md`, and `star_stories.md` in the
new directory. When the app starts, choose it from the **Profile** dropdown. Only the selected
profile is loaded, and it is read fresh before every answer. See `my_data/README.md` for the
file formats and a compiler-domain example.

Don't want to write it yourself? Open Claude Code in this folder, paste your resume and JD,
and ask it to fill the four files in your new application-profile directory.

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

The **Interview Overlay Setup** window appears before capture begins:

1. Choose the audio input. BlackHole is recommended for call audio, but any input works.
2. For response coaching, choose a different physical input as the candidate microphone.
3. Select whether candidate audio should be discarded after transcription (the default) or
   retained as local WAV files.
4. Confirm that everyone in this practice session consents. This is required again on every
   launch and before any audio test or capture begins.
5. Select a local Ollama model and the Whisper model/language.
6. Use **Test Audio Capture** and **Test Candidate Mic** to watch the live input meter.
7. Use **Test Transcription** and confirm the detected text.
8. Select **Refresh Diagnostics** to recheck Ollama or installed models.
9. Review the health summary and select **Save & Start**.

The same window configures answer style, VAD aggressiveness, silence timeout, overlay size
and opacity, session logging, and the default application profile. Settings are stored in
the versioned `my_data/settings.json` file, which is ignored by Git.

A small dark overlay box will appear near the top-center of your screen. Join
your call as normal. When your friend asks something, the app waits for
~1 second of silence, transcribes the question, and streams a coached answer
into the overlay. Drag the header bar to move the window anywhere on screen,
and click-drag over the answer text to select and copy it.

For a question supplied as text, paste or type it into the field at the bottom of the
overlay and press **Enter** or **Generate**. The exact text bypasses speech transcription.

When session logging is enabled, questions and answers are saved to a `sessions/` folder
as a timestamped log. Turn logging off in Setup for sessions that should not be retained.

Use the overlay control bar to pause/resume audio, regenerate the last answer, request a
shorter or more detailed version, clear visible history, copy answers, or adjust the view.
The shortcuts are **Ctrl+Option+P** (pause/resume), **Esc** (cancel), and
**Ctrl+Option+R** (regenerate) while the app is active. **Ctrl+Option+I** shows/hides the
overlay system-wide; if macOS does not respond to it, enable your terminal or packaged app
under **System Settings → Privacy & Security → Accessibility**.

After each coached answer, the separate candidate microphone listens for your response. It
automatically detects the start and end, transcribes locally, and displays scores, measured
speaking data, profile-grounding checks, up to two improvements, and a grounded improved
example. **Try Again** records another attempt for the same question and shows how the
scores, filler count, and pace changed. If Ollama becomes unavailable, local metrics and
clearly labeled fallback guidance still appear.

With session logging enabled, transcripts and feedback are stored in the session JSONL.
Audio is not retained unless the separate WAV-retention option was enabled with consent.

To stop: press `Ctrl+C` in the terminal running the app.

---

## Troubleshooting

- **Setup reports that Ollama is unreachable** — launch the Ollama app or run
  `ollama serve`, then select **Refresh Diagnostics**.
- **Setup reports that a model is missing** — run the exact `ollama pull <model>` command
  displayed in the status, then refresh the model list.
- **A `pkg_resources is deprecated` warning on startup** — harmless, ignore it.
- **No input devices appear** — connect or enable the desired input, grant microphone
  access to your terminal under macOS Privacy & Security, and restart the app.
- **You can't hear the call yourself** — double check both your speakers
  *and* BlackHole 2ch are checked in the Multi-Output Device (step 2.3), and
  that it's selected as your Mac's output (step 5).
