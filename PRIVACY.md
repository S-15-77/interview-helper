# Privacy and local data

Interview Helper is designed to run locally. Audio is captured through the selected macOS
inputs, Whisper transcription runs in the local Python process, and language-model requests
are sent only to the configured Ollama URL. The default URL is `localhost`. If you replace it
with a remote URL, the setup value is the boundary where the app stops being fully local.

## What is stored

- `my_data/settings.json`: versioned settings, including local device indexes/names and model
  choices.
- `my_data/applications/`: résumé, job description, STAR stories, and technical context added by
  the user.
- `my_data/question_bank.json`: reusable questions, tags, difficulty, and practice status.
- `sessions/*.jsonl`: when session logging is enabled, generated questions/answers, candidate
  transcripts, measured speech metrics, feedback, comparisons, profile name, mode, and timings.
- `sessions/review_metadata.json`: personal review notes and future-practice markers.
- `sessions/audio/<session-id>/`: candidate WAV files only when audio retention is explicitly
  enabled after consent. Raw candidate audio is otherwise discarded after local transcription.
- `logs/interview-helper.jsonl`: structured diagnostic events. Troubleshooting exports exclude
  application profiles and session content and remove audio-device names from settings.

When run from source, these paths are relative to the repository. The packaged macOS app stores
them under `~/Library/Application Support/Interview Helper/` so it never attempts to write into
the signed application bundle.

The app does not retain interviewer audio. Automatic retention cleanup can delete old session
JSONL and matching retained audio. The Review dashboard can delete one session or all practice
data; both destructive UI actions require explicit confirmation. Files under `my_data/`,
`sessions/`, and `logs/` should remain excluded from source control.

Markdown and PDF exports can redact email addresses, phone numbers, LinkedIn URLs, and GitHub
profile URLs. Redaction is best-effort; review an export before sharing it.
