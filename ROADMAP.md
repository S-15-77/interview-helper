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

- [ ] Add a bounded work queue.
- [ ] Display a visible listening, transcribing, and generating state.
- [ ] Add a Cancel button for the current generation.
- [ ] Drop or replace stale queued questions when appropriate.
- [ ] Detect duplicate transcriptions before generating another answer.
- [ ] Prevent manual submissions from silently waiting behind old audio questions.
- [ ] Record transcription time, time to first token, and total generation time.
- [ ] Add concurrency and cancellation tests around the worker.

### Improve transcript confidence

- [ ] Show the detected question before or while an answer is generated.
- [ ] Let the user correct a bad transcript and regenerate.
- [ ] Add a Retry Transcription action.
- [ ] Consider using transcription confidence or no-speech probability to reject uncertain
      results.

## Priority 1: Essential live controls

These are relatively small changes with a large usability benefit.

- [ ] Pause and resume audio listening.
- [ ] Cancel the current answer.
- [ ] Clear the visible session history.
- [ ] Regenerate the last answer.
- [ ] Add Shorter and More Detail actions.
- [ ] Add Copy Answer and Copy Session actions.
- [ ] Add a global shortcut to show or hide the overlay.
- [ ] Add keyboard shortcuts for pause, cancel, and regenerate.
- [ ] Make the overlay width, height, opacity, and font size adjustable.
- [ ] Persist window position and display settings between launches.

### Definition of done

- The user can control a session without returning to the terminal.
- The overlay clearly communicates what the application is doing.
- A slow or incorrect answer can be cancelled without restarting the app.

## Priority 2: Settings and setup wizard

BlackHole, Ollama, and model setup are the largest barriers for new users.

### Setup diagnostics

- [ ] Add an audio input-device selector instead of requiring a device named BlackHole.
- [ ] Show a live audio-level meter.
- [ ] Add a Test Audio Capture button.
- [ ] Add a Test Transcription button with the detected text.
- [ ] Check whether Ollama is reachable.
- [ ] List locally installed Ollama models.
- [ ] Clearly report when the selected model is missing.
- [ ] Add a setup-complete health summary.

### Configurable settings

- [ ] Ollama model.
- [ ] Whisper model and language.
- [ ] Answer length or response style.
- [ ] VAD aggressiveness and silence timeout.
- [ ] Audio input device.
- [ ] Overlay appearance.
- [ ] Session logging on or off.
- [ ] Default application profile.
- [ ] Save settings locally in a versioned configuration file.

### Definition of done

- A user can configure and validate the application without editing Python files.
- Startup errors identify the failing dependency and explain how to fix it.

## Priority 3: Candidate-response capture and coaching

This is the highest-value major feature. It turns the application into a training tool that
helps users improve rather than only supplying an answer.

### Capture the candidate's response

- [ ] Add a separate microphone input for the candidate.
- [ ] Keep interviewer and candidate audio logically separate.
- [ ] Detect when the candidate starts and finishes answering.
- [ ] Transcribe the candidate's response locally.
- [ ] Make audio recording optional; allow transcript-only storage.
- [ ] Obtain clear consent before recording or retaining any audio.

### Analyze each answer

- [ ] Score relevance to the question.
- [ ] Evaluate STAR completeness for behavioral answers.
- [ ] Evaluate clarity, structure, and conciseness.
- [ ] Detect filler words and repeated phrases.
- [ ] Estimate speaking pace and answer duration.
- [ ] Check technical correctness and missing trade-offs.
- [ ] Check whether claims are supported by the selected profile.
- [ ] Identify one or two concrete improvements instead of overwhelming the user.
- [ ] Produce an improved example answer grounded in the candidate's actual experience.

### Definition of done

- Every completed candidate answer can produce actionable feedback.
- Feedback distinguishes facts from suggestions and never invents candidate experience.
- The user can repeat the same question and compare attempts.

## Priority 4: Practice modes

### Learn mode

Show the coached answer immediately, matching the application's current behavior.

- [ ] Stream a concise answer into the overlay.
- [ ] Provide Shorter, More Detail, and Regenerate actions.

### Simulate mode

Create realistic practice without showing an answer before the candidate responds.

- [ ] Hide the coached answer while the candidate is speaking.
- [ ] Show only the question and timer during the attempt.
- [ ] Reveal feedback and an example answer afterward.
- [ ] Allow retrying the question.

### Review mode

- [ ] Browse completed sessions and individual attempts.
- [ ] Compare original and improved answers.
- [ ] Add personal notes and mark questions for future practice.

## Priority 5: Job-specific mock interviews

Use the selected application profile to create a structured interview rather than handling
only ad hoc questions.

- [ ] Generate questions from the résumé and job description.
- [ ] Let the user choose interview length and difficulty.
- [ ] Support recruiter, behavioral, technical, coding, and system-design rounds.
- [ ] Generate realistic follow-up questions based on the candidate's previous response.
- [ ] Avoid repeating questions or STAR stories within a session.
- [ ] Add a timed full-interview mode.
- [ ] Let users maintain a reusable question bank.
- [ ] Allow questions to be tagged by topic, difficulty, and status.

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

- [ ] List previous sessions by date and application profile.
- [ ] Show questions, generated answers, candidate responses, and feedback.
- [ ] Filter by question category and difficulty.
- [ ] Track recurring weaknesses.
- [ ] Track scores and improvement over time.
- [ ] Surface STAR stories that are overused or underdeveloped.
- [ ] Generate a concise end-of-session summary.
- [ ] Recommend the next topics or questions to practice.
- [ ] Export a session to Markdown or PDF.
- [ ] Add delete, retention-period, and auto-cleanup controls.

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

- [ ] Classify the question before building the final prompt.
- [ ] Load only relevant skill modules for the detected question type.
- [ ] Select the most relevant résumé, job-description, and STAR-story passages.
- [ ] Introduce an explicit prompt-size budget.
- [ ] Replace the last-200-words strategy with structured conversation state.
- [ ] Track topics discussed, stories already used, and open follow-ups.
- [ ] Cache unchanged profile files while still detecting edits.
- [ ] Add prompt-inspection tooling for development and troubleshooting.

## Priority 8: Privacy and data controls

- [ ] Let users disable session logging.
- [ ] Let users choose whether candidate audio is retained.
- [ ] Default to deleting raw audio after transcription.
- [ ] Add configurable automatic session deletion.
- [ ] Add a Delete All Practice Data action with an explicit confirmation.
- [ ] Redact common personal identifiers from exported reports when requested.
- [ ] Document exactly what is stored and where.
- [ ] Clearly label any future feature that stops being fully local.

## Priority 9: Distribution and engineering quality

- [ ] Package the project as a signed macOS application.
- [ ] Provide a first-run setup flow inside the application.
- [ ] Add CI that runs the unit tests on every pull request.
- [ ] Configure a formatter and linter.
- [ ] Add type checking for thread, queue, and signal boundaries.
- [ ] Separate unit tests from tests requiring real audio hardware or Ollama.
- [ ] Add integration tests for cancellation, queue pressure, and shutdown.
- [ ] Add a versioned session-data schema and migrations.
- [ ] Add structured application logs with a troubleshooting export.
- [ ] Add a `LICENSE` before opening the repository for reuse or contribution.

## Recommended implementation sequence

### Milestone 1: Reliable live session

- Prompt-purpose corrections.
- Pause, cancel, regenerate, and clear controls.
- Visible pipeline status.
- Stale-question and duplicate handling.
- Transcript correction.

### Milestone 2: Easy setup

- Settings storage.
- Audio-device selector and level meter.
- Ollama/model health checks.
- In-app transcription test.

### Milestone 3: Real practice loop

- Candidate microphone capture.
- Simulate mode.
- Answer evaluation and actionable feedback.
- Retry and attempt comparison.

### Milestone 4: Structured preparation

- Job-specific question generation.
- Follow-up questions.
- Session review dashboard.
- Progress tracking and exports.

### Milestone 5: Shareable product

- Packaged macOS app.
- CI, formatting, type checking, and integration tests.
- Privacy controls, data migrations, documentation, and license.

## Recommended next feature

If only one major feature is selected, implement **Simulate Mode with candidate-response
feedback**. It offers the clearest user value and most strongly differentiates Interview
Helper from a simple local answer generator.

Before that larger feature, complete the smaller live-control and stale-work items in
Milestone 1 so the underlying session pipeline is dependable.
