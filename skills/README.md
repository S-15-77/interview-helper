# Interview Skills

Every `.md`/`.txt` file in this folder (recursively) is read fresh on each question and
injected into the prompt right after the core system instructions — before your Candidate
Profile and the conversation context. Add a new file here instead of editing
`SYSTEM_PROMPT` in `src/llm_client.py` when you want to teach the bot a new rule or
question-type playbook.

## Adding a skill

Create a `.md` file and write plain instructions, the same way `hr_playbook.md` does — e.g.
"When asked X, do Y." No special format required; it's concatenated as-is into the prompt.

## Important: this doesn't save tokens

Everything in here still gets sent to the model on every request, same as if it were typed
directly into `SYSTEM_PROMPT`. The benefit is not having to edit Python — it's not a smaller
prompt.

## Keep it lean

Every file in here is injected into *every* question, technical or behavioral. Unlike
`my_data/` (facts about you), skills are instructions the model has to actually follow. A
weaker/faster local model has a limited budget for how many rules it can reliably obey at
once — piling on more skill files can make it *less* consistent, not more. Curate rather than
accumulate.

Unlike `my_data/`, this folder is **not** gitignored — skills are general interview strategy,
not personal data, so they're safe (and useful) to commit and share.
