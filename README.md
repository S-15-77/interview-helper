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

## Running a session

```
source venv/bin/activate
python src/app.py
```

An overlay window appears top-left. Start your video call with your friend
(with system output set to the Multi-Output Device from step 3). When they
ask a question, the app transcribes it after ~1s of silence and streams a
coached answer onto the overlay. Each Q&A pair is logged to
`sessions/<timestamp>.jsonl`.
