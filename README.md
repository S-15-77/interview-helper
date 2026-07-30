# Mock Interview Overlay

Fully local mock-interview practice tool: transcribes your friend's voice
during a video call and streams a coached answer onto a floating overlay.
Nothing leaves your machine. For practicing with a consenting friend — not
for use during a real employer interview.

## One-time setup

1. **Install Ollama** (if not already installed):
   ```
   brew install ollama
   ollama serve &   # or launch the Ollama app
   ollama pull llama3.2
   ```
   Verify: `ollama list` should show `llama3.2`.

2. **Install BlackHole** (virtual audio device that lets the app "hear"
   your friend's voice from the call):
   ```
   brew install blackhole-2ch
   ```

3. **Create a Multi-Output Device** so you still hear the call while
   BlackHole also captures it:
   - Open **Audio MIDI Setup** (Spotlight search).
   - Click the **+** button (bottom-left) → **Create Multi-Output Device**.
   - Check both your normal output (e.g. "MacBook Pro Speakers" or your
     headphones) **and** "BlackHole 2ch".
   - Rename it to something recognizable, e.g. "Call + BlackHole".
   - Leave the **Sample Rate** at whatever it defaults to (e.g. 48.0 kHz) —
     the app always opens the BlackHole stream at 16000 Hz itself and
     CoreAudio resamples transparently, so there's nothing to change here.
   - Before each practice session: **System Settings → Sound → Output** →
     select that Multi-Output Device.

4. **Python environment:**
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. **Permissions:** the first time you run the app, macOS will prompt for
   microphone/audio permission for your terminal — allow it.

6. **(Optional) Personalize answers with your real background:** drop
   `.md`/`.txt` files into `my_data/` — a resume, project write-ups, a target
   job description, STAR story notes. Every file in there is read fresh on
   each question and used to ground behavioral/non-technical answers in your
   actual experience instead of generic placeholders. See `my_data/README.md`
   for details. This folder is gitignored (except its own README template)
   so your personal data never gets committed.

## Running a session

```
source venv/bin/activate
python -m src.app
```

Run this from the project root (the `-m` form is required — `python
src/app.py` fails with `ModuleNotFoundError`).

An overlay window appears top-left, excluded from screen shares/recordings
and pinned on top even when you click into the browser or another app. It
keeps a scrollable history of the whole session rather than clearing after
each question — scroll up to reread earlier answers; it auto-follows the
newest text as long as you're already at the bottom. Start your video call
with your friend (with system output set to the Multi-Output Device from
step 3). When they ask a question, the app transcribes it after ~1s of
silence and streams a coached answer onto the overlay. Each Q&A pair is
logged to `sessions/<timestamp>.jsonl`.

To stop: click the **×** in the overlay's corner, or press `Ctrl+C` in the
terminal.

## Troubleshooting

- **Overlay shows "Ollama error: ... Connection refused"**: Ollama isn't
  running. Run `ollama serve` in a terminal and leave it open — no need to
  restart the app.
- **`No input device matching 'BlackHole' found`**: BlackHole isn't
  installed, or wasn't picked up — run `brew install blackhole-2ch` and
  retry.
- **Can't hear the call yourself**: confirm both your speakers/headphones
  *and* BlackHole 2ch are checked in the Multi-Output Device (step 3), and
  that device is selected as your Mac's output.
