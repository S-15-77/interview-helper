# Interview Helper — Résumé Project Brief

Use this document when adding Interview Helper to a résumé, portfolio, LinkedIn profile, cover
letter, or AI résumé editor. It separates verified project facts from results that still need real
usage data, so future descriptions remain accurate.

## Quick facts

- **Project:** Interview Helper
- **Repository:** <https://github.com/S-15-77/interview-helper>
- **Type:** Open-source, privacy-focused macOS desktop application
- **Purpose:** Local mock-interview practice and candidate-response coaching
- **Platform:** macOS; the current packaged preview targets Apple Silicon (`arm64`)
- **License:** GPL-3.0-only
- **Primary language:** Python
- **Core technologies:** PyQt6, faster-whisper, Ollama, WebRTC VAD, PyAudio, NumPy, PyInstaller
- **Engineering tools:** pytest, Ruff, Mypy, GitHub Actions
- **Storage:** Versioned local settings and JSONL session data
- **Current release stage:** Public preview; the app is packaged but not yet Developer ID signed or
  notarized

## One-line description

Built a privacy-first macOS mock-interview coach that locally transcribes questions and candidate
responses, streams AI-assisted coaching, evaluates practice attempts, and tracks improvement without
sending interview data to cloud services.

## Short portfolio description

Interview Helper is an open-source macOS practice platform built with Python and PyQt6. It combines
local speech recognition through faster-whisper with local generation through Ollama to provide
mock-interview questions, streamed coaching, candidate-answer feedback, attempt comparison, and a
session-review dashboard. Its bounded, cancellable worker pipeline prevents stale questions from
delaying live sessions, while consent, retention, redaction, and local-storage controls protect
sensitive candidate data.

## Copy-ready résumé entry

**Interview Helper | Python, PyQt6, Whisper, Ollama, PyAudio, PyInstaller**  
Open-source macOS mock-interview coaching application

- Built a fully local mock-interview platform that captures and transcribes interviewer and candidate
  audio separately, streams coached answers, and generates structured feedback without transmitting
  résumé, audio, or session data to cloud services.
- Designed a multithreaded, bounded-queue processing pipeline with cooperative cancellation,
  latest-question replacement, duplicate-transcript detection, confidence filtering, and visible
  listening/transcribing/generating states to keep live interactions responsive.
- Implemented Learn, Simulate, and Review workflows with job-specific question generation, STAR and
  technical-answer evaluation, speaking metrics, retry comparison, progress tracking, Markdown/PDF
  exports, and configurable privacy controls.
- Shipped an Apple Silicon application bundle with PyInstaller and established CI quality gates using
  150+ automated tests, Ruff formatting and linting, Mypy type checking, and GitHub Actions.

## Alternative résumé bullets

Choose three or four bullets that best match the role. Do not use every bullet in one résumé.

### Software engineering emphasis

- Architected thread-safe audio, transcription, and generation workers around bounded queues and Qt
  signals, keeping background processing isolated from GUI updates on the main thread.
- Added cancellation and queue-pressure behavior that prioritizes manual requests, replaces stale
  captured questions, suppresses duplicate transcriptions, and prevents obsolete answers from
  appearing late.
- Created versioned configuration and session schemas with migration support, retention cleanup,
  troubleshooting logs, and recoverable local review workflows.
- Packaged the Python application as a native Apple Silicon `.app` and automated tests, linting,
  formatting, and type checking in a macOS GitHub Actions pipeline.

### Applied AI and machine-learning emphasis

- Integrated faster-whisper and Ollama into a local inference pipeline for speech recognition,
  streaming answer generation, response evaluation, and profile-grounded coaching.
- Calculated transcription confidence and no-speech signals to hold uncertain results for correction
  instead of automatically sending unreliable questions into generation.
- Built question-aware context retrieval with relevant profile and coaching modules, prompt-size
  budgeting, cached source files, and structured conversation state.
- Combined deterministic speech metrics with model-generated analysis to assess relevance, STAR
  completeness, clarity, conciseness, technical correctness, trade-offs, filler words, pace, and
  profile support.

### Product and desktop engineering emphasis

- Delivered three end-to-end practice modes: immediate coaching in Learn mode, answer-first practice
  in Simulate mode, and historical analysis in Review mode.
- Built a configurable always-on-top overlay with global shortcuts, pause/cancel/regenerate controls,
  transcript correction, adjustable appearance, and copy/export actions.
- Created an in-app setup experience with audio-device selection, live level metering, capture and
  transcription tests, Ollama health checks, local model discovery, and actionable dependency errors.
- Designed explicit consent and privacy controls for audio retention, session logging, identifier
  redaction, automatic deletion, and complete practice-data removal.

## Verified technical overview

### Live processing pipeline

1. A selected audio device supplies 16 kHz PCM frames.
2. WebRTC VAD segments speech and discards very short noise events.
3. A bounded worker queue applies latest-wins behavior when captured questions arrive faster than
   local inference can process them.
4. faster-whisper produces local transcriptions with confidence and no-speech metadata.
5. Relevant candidate-profile content and coaching guidance are selected within a prompt budget.
6. Ollama streams a locally generated answer into the PyQt6 overlay.
7. The application records transcription latency, time to first token, generation time, and total
   pipeline time when session logging is enabled.

Candidate-response coaching uses a separate microphone and worker queue. The application transcribes
the attempt locally, measures duration, pace, filler words, and repetition, then produces grounded
feedback and an improved example that is forbidden from inventing candidate experience.

### Reliability and concurrency

- Separate capture, transcription/generation, and candidate-coaching workers
- Thread-safe communication with Qt signals
- Bounded queues rather than unlimited backlogs
- Cooperative generation cancellation
- Priority handling for typed questions and corrections
- Duplicate-transcription suppression
- Stale-question replacement
- Graceful diagnostic and application shutdown

### Privacy and responsible-use design

- Designed only for mock interviews with informed participant consent
- Local speech recognition and local language-model inference
- Candidate audio deleted after transcription by default
- Optional transcript/session logging and optional audio retention
- Configurable retention periods and confirmed deletion actions
- Identifier redaction for exported reports
- Candidate examples grounded in supplied profile data rather than fabricated experience

### User-facing capabilities

- Learn, Simulate, and Review modes
- Recruiter, behavioral, technical, coding, and system-design rounds
- Résumé and job-description-based question generation
- Response-aware follow-up questions and reusable question bank
- Editable transcripts and transcription retry
- Shorter, More Detail, Regenerate, Cancel, Pause, Clear, and Copy controls
- Attempt scoring and comparison
- Session dashboard with filters, trends, notes, and practice recommendations
- Markdown and PDF exports

## Engineering challenges to discuss in interviews

### Preventing stale answers

Local speech and language models can be slower than incoming questions. An unlimited FIFO queue would
eventually display answers that are no longer useful. The solution was a bounded work queue with
latest-question replacement, manual-request priority, duplicate suppression, and cooperative
cancellation.

### Safely updating a Qt interface from worker threads

Audio capture and model inference cannot block the GUI thread, but directly modifying Qt widgets from
background threads is unsafe. Worker components therefore communicate through typed Qt signals, and
only the main thread changes the interface.

### Keeping generated answers grounded

Interview coaching becomes harmful when a model invents candidate experience. Prompt constraints,
profile-aware retrieval, missing-information frameworks, confidence handling, and tests prevent
placeholder stories from being presented as personal facts.

### Separating two audio sources

Interviewer audio and the candidate microphone serve different purposes and must not enter the same
pipeline accidentally. The application uses distinct device selections, capture threads, queues,
transcription paths, consent behavior, and session fields for the two sources.

### Packaging a local AI desktop application

The application bundles Python, Qt, native audio libraries, and local inference dependencies into a
macOS app with PyInstaller. The build includes required templates, coaching modules, and license text,
and is exercised by a packaged smoke test. Developer ID signing, notarization, and an Intel or
universal build remain future release work.

## Suggested interview answer

> I built Interview Helper because most interview-assistance tools either depend on cloud services or
> focus only on generating an answer. I wanted a local practice loop that could capture a mock
> interview question, help the candidate respond, and then show specific ways to improve. The hardest
> engineering problem was keeping a live local-inference pipeline responsive. I implemented bounded
> queues, cancellation, duplicate detection, and latest-question replacement so slow generation could
> not create a stale backlog. I also separated interviewer and candidate audio into independent
> workers and used Qt signals for safe UI updates. The result is a packaged macOS application with
> Learn, Simulate, and Review modes, privacy controls, structured feedback, session analytics, and a
> CI-tested codebase.

## ATS and portfolio keywords

Use only keywords that are relevant to the target role:

`Python`, `PyQt6`, `desktop application`, `macOS`, `multithreading`, `concurrency`, `thread-safe`,
`bounded queue`, `streaming`, `speech recognition`, `Whisper`, `faster-whisper`, `Ollama`, `local
LLM`, `prompt engineering`, `retrieval`, `voice activity detection`, `WebRTC VAD`, `PyAudio`, `NumPy`,
`JSONL`, `schema migration`, `privacy by design`, `PyInstaller`, `pytest`, `Mypy`, `Ruff`, `GitHub
Actions`, `CI/CD`, `PDF export`, `accessibility`, `observability`

## Prompt for an AI résumé editor

Copy the prompt below, then add the target job description and your current résumé.

```text
Act as a technical résumé editor. Tailor my Interview Helper project entry to the job description
without inventing users, revenue, performance improvements, accuracy percentages, download counts,
or technologies that are not listed below.

Project facts:
- Interview Helper is an open-source, privacy-focused macOS mock-interview practice application.
- Built primarily with Python and PyQt6.
- Uses faster-whisper for local transcription, Ollama for local streamed generation, WebRTC VAD for
  speech segmentation, and PyAudio for audio capture.
- Separates interviewer/call audio from candidate microphone audio.
- Uses multithreaded workers, Qt signals, bounded queues, cancellation, stale-work replacement,
  duplicate detection, and confidence filtering.
- Supports Learn, Simulate, and Review modes; job-specific questions; candidate-response scoring;
  retry comparison; session analytics; Markdown/PDF export; and privacy controls.
- Uses versioned settings and JSONL session schemas with migration support.
- Packaged for Apple Silicon macOS with PyInstaller.
- Quality gates include 150+ pytest tests, Ruff, Mypy, and GitHub Actions.
- Licensed GPL-3.0-only.
- Current release is a public preview and is not yet Developer ID signed or notarized.

Instructions:
1. Select the facts most relevant to the job description.
2. Produce one project heading, one concise description, and 3-4 achievement-oriented bullets.
3. Begin bullets with strong action verbs and keep each bullet to no more than two lines.
4. Preserve technical specificity while explaining why each engineering decision mattered.
5. Do not claim measured impact unless I provide the measurement.
6. Return an ATS-friendly version and a more conversational LinkedIn/portfolio version.

Target job description:
[PASTE JOB DESCRIPTION]

My current résumé:
[PASTE CURRENT RÉSUMÉ]
```

## Measurements to add later

These would strengthen future résumé bullets, but they must be measured before being claimed:

- GitHub stars, forks, release downloads, and external contributors
- Number of practice users and completed sessions
- Crash-free session rate
- Median transcription latency and time to first token
- Queue cancellation or stale-work replacement counts
- Application startup time and package size changes
- Candidate score improvement across repeated attempts
- Test coverage percentage
- User feedback or usability-study results

## Accuracy checklist

Before copying a project description into a résumé:

- Confirm the technologies still exist in the current repository.
- Update the supported macOS architectures and release status.
- Recount automated tests if quoting a specific number.
- Add only metrics that were actually measured.
- Do not describe the preview build as signed, notarized, universal, or App Store distributed until
  those release steps are complete.
- Do not claim production users, adoption, accuracy, or performance improvements without evidence.
