# Interview Helper Roadmap

This document is a practical backlog for evolving Interview Helper from a real-time
answer generator into a complete mock-interview practice and improvement system.

## Product direction

The strongest direction is to build a complete practice loop:

1. Hear or present an interview question.
2. Let the candidate answer it.
3. Analyze the candidate's response.
4. Provide specific feedback and an improved example.
5. Track progress across practice sessions.

This keeps the product aligned with its intended use: practicing with a consenting friend,
not receiving covert assistance during a real employer interview.

## Priority 0: Product integrity and reliability

Complete these before adding large new features.

### Align the prompt with the product purpose

- [x] Replace the prompt's "actual or mock interview" language with mock-interview-only
      language.
- [x] Correct the prompt's description of the audio source: the app currently captures the
      interviewer's call audio through BlackHole, not the candidate's microphone.
- [x] Stop presenting invented placeholder stories as if they were real candidate
      experiences.
- [x] When profile details are missing, produce a clearly marked answer framework or ask the
      candidate to add a relevant STAR story.
- [x] Add tests that verify these constraints are present in the generated prompt.

### Prevent stale or overlapping answers

The worker processes questions sequentially. If local generation is slow, newer questions
can wait behind old work and produce answers after they are no longer useful.

- [x] Add a bounded work queue.
- [x] Display a visible listening, transcribing, and generating state.
- [x] Add a Cancel button for the current generation.
- [x] Drop or replace stale queued questions when appropriate.
- [x] Detect duplicate transcriptions before generating another answer.
- [x] Prevent manual submissions from silently waiting behind old audio questions.
- [x] Record transcription time, time to first token, and total generation time.
- [x] Add concurrency and cancellation tests around the worker.

### Improve transcript confidence

- [x] Show the detected question before or while an answer is generated.
- [x] Let the user correct a bad transcript and regenerate.
- [x] Add a Retry Transcription action.
- [x] Consider using transcription confidence or no-speech probability to reject uncertain
      results.

## Priority 1: Essential live controls

These are relatively small changes with a large usability benefit.

- [x] Pause and resume audio listening.
- [x] Cancel the current answer.
- [x] Clear the visible session history.
- [x] Regenerate the last answer.
- [x] Add Shorter and More Detail actions.
- [x] Add Copy Answer and Copy Session actions.
- [x] Add a global shortcut to show or hide the overlay.
- [x] Add keyboard shortcuts for pause, cancel, and regenerate.
- [x] Make the overlay width, height, opacity, and font size adjustable.


### Definition of done

- The user can control a session without returning to the terminal.
- A slow or incorrect answer can be cancelled without restarting the app.

## Priority 2: Settings and setup wizard

BlackHole, Ollama, and model setup are the largest barriers for new users.

### Setup diagnostics

- [x] Add an audio input-device selector instead of requiring a device named BlackHole.
- [x] Show a live audio-level meter.
- [x] Add a Test Audio Capture button.
- [x] Add a Test Transcription button with the detected text.
- [x] Check whether Ollama is reachable.
- [x] List locally installed Ollama models.
- [x] Clearly report when the selected model is missing.
- [x] Add a setup-complete health summary.

### Configurable settings

- [x] Ollama model.
- [x] Whisper model and language.
- [x] Answer length or response style.
- [x] VAD aggressiveness and silence timeout.
- [x] Audio input device.
- [x] Overlay appearance.
- [x] Session logging on or off.
- [x] Default application profile.
- [x] Save settings locally in a versioned configuration file.

### Definition of done

- A user can configure and validate the application without editing Python files.
- Startup errors identify the failing dependency and explain how to fix it.

## Priority 3: Candidate-response capture and coaching

This is the highest-value major feature. It turns the application into a training tool that
helps users improve rather than only supplying an answer.

### Capture the candidate's response

- [x] Add a separate microphone input for the candidate.
- [x] Keep interviewer and candidate audio logically separate.
- [x] Detect when the candidate starts and finishes answering.
- [x] Transcribe the candidate's response locally.
- [x] Make audio recording optional; allow transcript-only storage.
- [x] Obtain clear consent before recording or retaining any audio.

### Analyze each answer

- [x] Score relevance to the question.
- [x] Evaluate STAR completeness for behavioral answers.
- [x] Evaluate clarity, structure, and conciseness.
- [x] Detect filler words and repeated phrases.
- [x] Estimate speaking pace and answer duration.
- [x] Check technical correctness and missing trade-offs.
- [x] Check whether claims are supported by the selected profile.
- [x] Identify one or two concrete improvements instead of overwhelming the user.
- [x] Produce an improved example answer grounded in the candidate's actual experience.

### Definition of done

- Every completed candidate answer can produce actionable feedback.
- Feedback distinguishes facts from suggestions and never invents candidate experience.
- The user can repeat the same question and compare attempts.

## Priority 4: Practice modes

### Learn mode

Show the coached answer immediately, matching the application's current behavior.

- [x] Stream a concise answer into the overlay.
- [x] Provide Shorter, More Detail, and Regenerate actions.

### Simulate mode

Create realistic practice without showing an answer before the candidate responds.

- [x] Hide the coached answer while the candidate is speaking.
- [x] Show only the question and timer during the attempt.
- [x] Reveal feedback and an example answer afterward.
- [x] Allow retrying the question.

### Review mode

- [x] Browse completed sessions and individual attempts.
- [x] Compare original and improved answers.
- [x] Add personal notes and mark questions for future practice.

## Priority 5: Job-specific mock interviews

Use the selected application profile to create a structured interview rather than handling
only ad hoc questions.

- [x] Generate questions from the résumé and job description.
- [x] Let the user choose interview length and difficulty.
- [x] Support recruiter, behavioral, technical, coding, and system-design rounds.
- [x] Generate realistic follow-up questions based on the candidate's previous response.
- [x] Avoid repeating questions or STAR stories within a session.
- [x] Add a timed full-interview mode.
- [x] Let users maintain a reusable question bank.
- [x] Allow questions to be tagged by topic, difficulty, and status.

### Suggested interview flow

1. Introduction and résumé walkthrough.
2. Role-specific experience questions.
3. Behavioral questions tied to the job requirements.
4. Technical fundamentals.
5. Coding or system-design discussion.
6. Candidate questions and closing feedback.

## Priority 6: Session review dashboard

The application already writes session data to JSONL. Build a useful interface on top of
that data.

- [x] List previous sessions by date and application profile.
- [x] Show questions, generated answers, candidate responses, and feedback.
- [x] Filter by question category and difficulty.
- [x] Track recurring weaknesses.
- [x] Track scores and improvement over time.
- [x] Surface STAR stories that are overused or underdeveloped.
- [x] Generate a concise end-of-session summary.
- [x] Recommend the next topics or questions to practice.
- [x] Export a session to Markdown or PDF.
- [x] Add delete, retention-period, and auto-cleanup controls.

### Useful metrics

- Average answer duration.
- Speaking pace.
- Filler words per minute.
- STAR component coverage.
- Technical-accuracy score.
- Relevance and conciseness scores.
- Most-practiced and weakest question categories.
- Change between first and most recent attempts.

## Priority 7: Smarter context and profile retrieval

Currently, all skill files and all files in the selected profile are injected into every
request. This can consume context and weaken instruction-following on smaller local models.

- [x] Classify the question before building the final prompt.
- [x] Load only relevant skill modules for the detected question type.
- [x] Select the most relevant résumé, job-description, and STAR-story passages.
- [x] Introduce an explicit prompt-size budget.
- [x] Replace the last-200-words strategy with structured conversation state.
- [x] Track topics discussed, stories already used, and open follow-ups.
- [x] Cache unchanged profile files while still detecting edits.
- [x] Add prompt-inspection tooling for development and troubleshooting.

## Priority 8: Privacy and data controls

- [x] Let users disable session logging.
- [x] Let users choose whether candidate audio is retained.
- [x] Default to deleting raw audio after transcription.
- [x] Add configurable automatic session deletion.
- [x] Add a Delete All Practice Data action with an explicit confirmation.
- [x] Redact common personal identifiers from exported reports when requested.
- [x] Document exactly what is stored and where.
- [x] Clearly label any future feature that stops being fully local.

## Priority 9: Distribution and engineering quality

- [ ] Package the project as a signed macOS application.
- [x] Provide a first-run setup flow inside the application.
- [x] Add CI that runs the unit tests on every pull request.
- [x] Configure a formatter and linter.
- [x] Add type checking for thread, queue, and signal boundaries.
- [x] Separate unit tests from tests requiring real audio hardware or Ollama.
- [x] Add integration tests for cancellation, queue pressure, and shutdown.
- [x] Add a versioned session-data schema and migrations.
- [x] Add structured application logs with a troubleshooting export.
- [x] Add a `LICENSE` before opening the repository for reuse or contribution.

The macOS build/sign script is present, but the signing checklist remains open until a Developer
ID identity is supplied and a signed/notarized artifact is verified. The repository is licensed
under GPL-3.0-only, matching the open-source GPLv3 edition of PyQt6 used by the application.

## Recommended implementation sequence

### Milestone 1: Reliable live session — complete

- [x] Prompt-purpose corrections.
- [x] Pause, cancel, regenerate, and clear controls.
- [x] Visible pipeline status.
- [x] Stale-question and duplicate handling.
- [x] Transcript correction.

### Milestone 2: Easy setup — complete

- [x] Settings storage.
- [x] Audio-device selector and level meter.
- [x] Ollama/model health checks.
- [x] In-app transcription test.

### Milestone 3: Real practice loop — complete

- [x] Candidate microphone capture.
- [x] Simulate mode.
- [x] Answer evaluation and actionable feedback.
- [x] Retry and attempt comparison.

### Milestone 4: Structured preparation — complete

- [x] Job-specific question generation.
- [x] Follow-up questions.
- [x] Session review dashboard.
- [x] Progress tracking and exports.

### Milestone 5: Shareable product — release preparation

- [x] Packaged macOS app and reproducible build script.
- [x] CI, formatting, type checking, and integration tests.
- [x] Privacy controls, data migrations, and documentation.
- [ ] Sign and notarize a release using the owner's Apple Developer ID credentials.
- [x] Select and add the repository license before public distribution (GPL-3.0-only).

## Recommended next step

**Simulate Mode with candidate-response feedback is complete.** It now captures a separate
candidate microphone, hides coaching until the attempt ends, evaluates the response, and supports
retry and attempt comparison.

The next step is a small real-user pilot of the packaged app, followed by Developer ID signing and
notarization.
