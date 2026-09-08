# Interview Overlay

Fully local mock-interview practice tool: transcribes your friend's voice
during a video call and streams a coached answer onto a floating overlay.
Nothing leaves your machine. For practicing with a consenting friend — not
for use during a real employer interview.

## One-time setup

1. **Install Ollama** (if not already installed):
   ```
   brew install ollama
   ollama serve &   # or launch the Ollama app
   ollama pull qwen2.5:3b-instruct
   ```
   Verify: `ollama list` should show `qwen2.5:3b-instruct`. This is the fast model, tuned
   for real-time answers. For more reliable answers on hard technical questions, pull
   `qwen2.5:7b-instruct` and select it in the setup window.

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

6. **(Optional) Create an application profile:** copy
   `templates/application_profile/` into `my_data/applications/<company-role>/`,
   then add the exact resume, job description, technical domain notes, and STAR
   stories for that application. Select it from the overlay's **Profile** dropdown.
   Only the selected profile is sent to the model, and files are read fresh for
   every question. See `my_data/README.md` for the complete format. `my_data/`
   is gitignored so your personal information is not committed.

7. **(Optional) Customize the coaching style:** drop `.md` files into
   `skills/` to teach the bot new rules or question-type playbooks (a "tell
   me about yourself" framework, how to handle weakness questions, etc.) —
   read fresh on every question, same as `my_data/`. Unlike `my_data/`, this
   folder isn't gitignored — skills are general interview strategy, not
   personal data, so they're meant to be shared. See `skills/README.md`. Ask
   Claude Code to turn an article or video's tips into a new skill file for
   you instead of hand-editing the prompt.

## Running a session

```
source venv/bin/activate
python -m src.app
```

Choose a practice mode in Setup:

- **Learn** streams the concise coached answer immediately and keeps Shorter, More Detail, and
  Regenerate available.
- **Simulate** shows the question and timers while you answer, then reveals grounded feedback and
  an improved example. Try Again hides the feedback for the next attempt.
- **Review** opens the local dashboard without starting capture. You can also open it with the
  overlay's Review button during Learn or Simulate sessions.

**Start Mock** builds a job-specific interview from the selected application profile. Setup
controls its length, difficulty, and included rounds. **Next** advances the plan; candidate
responses can produce a response-aware follow-up, and generated questions are saved to the local
question bank for later tagging and practice. The overlay tracks both attempt time and total mock
interview time.

Run this from the project root (the `-m` form is required — `python
src/app.py` fails with `ModuleNotFoundError`).

The **Interview Overlay Setup** window opens first. Choose any available input device
(BlackHole is recommended for call system audio), select the installed Ollama model,
and review the remaining settings. **Test Audio Capture** shows a live level meter for
three seconds. **Test Transcription** captures five seconds and displays Whisper's detected
text. **Refresh Diagnostics** checks Ollama and lists local models; a missing model includes
the exact `ollama pull` command needed to install it. The health summary enables **Save &
Start** when the required inputs and Ollama model are available and session consent is
confirmed.

Settings are saved locally to the versioned, gitignored `my_data/settings.json` file. The
window lets you change the Ollama and Whisper models, transcription language, response
style, VAD and silence settings, input device, overlay appearance, session logging, and
default application profile without editing Python files. The setup window appears each
time the app starts so these choices remain accessible.

For candidate-response coaching, enable **Candidate-response capture**, choose a physical
microphone that is different from the interviewer/call input, and confirm the session
consent checkbox. Consent is intentionally requested again every launch and is required
even for audio tests. Candidate audio is discarded immediately after local transcription
by default. Enable **Retain candidate audio** only when everyone also consents to saving WAV
files; transcript-only session logging remains available without retaining audio.

After setup, an overlay window appears top-center and is pinned on top even when you click
into the browser or another app. The app requests macOS's best-effort window
capture exclusion, but current macOS versions do not guarantee it for entire-
display capture. To ensure other participants cannot see the overlay, share
only the interview browser/app window (or a browser tab), **not Entire
Screen**. It keeps a scrollable history of the whole session rather than
clearing after each question — scroll up to reread earlier answers; it
auto-follows the newest text as long as you're already at the bottom. Drag the header bar to
reposition the window, and click-drag over the answer text to select and
copy it. Start your video call
with your friend (with system output set to the Multi-Output Device from
step 3). When they ask a question, the app transcribes it after ~1s of
silence and streams a coached answer onto the overlay. Each Q&A pair is
logged to `sessions/<timestamp>.jsonl`.

If a question is provided as text rather than spoken, paste or type it into the
field at the bottom of the overlay and press **Enter** or **Generate**. This sends
the exact text to the answer pipeline without speech transcription. Typed questions
take priority: they cancel the active answer and replace any captured questions still
waiting to be processed. The header shows whether the app is listening, transcribing,
or generating. Use **Cancel** to stop the active operation and discard queued questions.

For spoken questions, an editable **Detected question** panel shows Whisper's text and
confidence before the answer is generated. If it is wrong, edit it and select **Regenerate**
to cancel the current answer and regenerate from the correction. **Retry STT** reruns local
transcription on the most recent captured question. Low-confidence or high no-speech results
remain available for review, but are not sent to the language model automatically.

The control bar provides the rest of the live session controls:

- **Pause/Resume** stops both interviewer and candidate audio processing without interrupting
  an answer already being generated. Resuming starts with fresh speech buffers.
- **Regenerate**, **Shorter**, and **More Detail** replace the latest answer while reusing
  the context from before that answer, so the old response does not bias its replacement.
- **Clear** resets only the visible overlay history. Session JSONL logs remain on disk.
- **Copy Answer** copies the latest answer as plain text; **Copy Session** copies all visible
  questions and answers.
- **View** opens sliders for overlay width, height, opacity, and answer font size.

When candidate coaching is enabled, the candidate microphone begins listening after the
coached answer is ready. It detects when the candidate starts and finishes speaking, then
shows the detected response and actionable feedback. The panel includes relevance, STAR,
clarity, conciseness, technical-correctness, and profile-support scores where applicable;
measured duration, speaking pace, filler words, and repeated phrases; clearly separated
observed facts and suggestions; missing trade-offs; and a grounded improved example.
Select **Try Again** to answer the same question another time. Attempts are numbered and
the newest one is compared with the previous attempt for that question.

Candidate transcripts, metrics, feedback, and comparisons are added to the session JSONL
when logging is enabled. Optional retained audio is stored under
`sessions/audio/<session-id>/`; it is never required for feedback.

The Review dashboard filters sessions by category and difficulty, compares original and improved
answers, tracks aggregate scores, pace, fillers and recurring weaknesses, and supports notes and
future-practice markers. It exports Markdown or PDF locally with optional identifier redaction.
Retention cleanup and confirmed per-session/all-data deletion include any retained audio. See
[`PRIVACY.md`](PRIVACY.md) for the exact storage map.

Developers can inspect context selection without sending a model request:

```
python -m src.prompt_inspector "Tell me about a time you led a project" --profile company-role
```

Run `pytest -m "not hardware and not ollama"`, `ruff check src tests`, and `mypy src` locally.
`packaging/build_macos.sh` builds the `.app`; setting `APPLE_SIGNING_IDENTITY` also signs it. Apple
notarization still requires the maintainer's Developer ID credentials.

Keyboard shortcuts are **Ctrl+Option+P** for Pause/Resume, **Esc** for Cancel, and
**Ctrl+Option+R** for Regenerate while the Interview Overlay app is active. On macOS,
**Ctrl+Option+I** shows or hides the overlay system-wide. macOS may require the terminal or
packaged app to be enabled under **System Settings → Privacy & Security → Accessibility**
before a system-wide keyboard monitor can receive key events.

To stop: click the **×** in the overlay's corner, or press `Ctrl+C` in the
terminal.

## Troubleshooting

- **Setup says Ollama is unreachable**: launch the Ollama app or run `ollama serve`,
  then select **Refresh Diagnostics**.
- **Setup says the selected model is missing**: run the displayed `ollama pull <model>`
  command, then refresh the model list.
- **No audio inputs are listed**: connect or enable an input, allow microphone access for
  the terminal under macOS Privacy & Security, and restart the app. BlackHole is only
  required when you want to capture the call's system audio.
- **Can't hear the call yourself**: confirm both your speakers/headphones
  *and* BlackHole 2ch are checked in the Multi-Output Device (step 3), and
  that device is selected as your Mac's output.
