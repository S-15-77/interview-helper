# Personal Knowledge Base

The application reads Markdown and text files from `my_data/` immediately before each
answer. You can update these files while the app is running; no restart is required.
`README.md` files are documentation only and are never sent to the language model.

## Recommended: one profile per application

Keep each job description paired with the exact resume used for that application:

```text
my_data/
  applications/
    acme-compiler-engineer/
      job_description.md
      resume.md
      technical_context.md
      star_stories.md
    example-ml-engineer/
      job_description.md
      resume.md
      technical_context.md
      star_stories.md
```

Create a new profile from the reusable template:

```bash
mkdir -p my_data/applications
cp -R templates/application_profile my_data/applications/acme-compiler-engineer
```

Rename the final directory for the company and role, then edit its four Markdown files.
It will appear in the overlay's **Profile** dropdown the next time the app starts. Only the
selected directory is loaded, so one role's JD, resume, and terminology cannot contaminate
another role's answers. Switching profiles also clears recent conversation context.

## What each profile file does

- `job_description.md`: the company, role, responsibilities, and requirements.
- `resume.md`: the version of your resume submitted for this exact role.
- `technical_context.md`: the role's domain and meanings of ambiguous terminology.
- `star_stories.md`: real behavioral examples, individual actions, and measurable results.

For a compiler role, `technical_context.md` might include:

```markdown
# Technical Context

## Primary Domain

Compilers and programming languages.

## Term Disambiguation

- IR / Intermediate Representation: compiler IR, not information retrieval.
- Pass: a compiler analysis or transformation pass.
- Lowering: converting a high-level IR into a lower-level representation.
- SSA: Static Single Assignment form.
- CFG: Control-Flow Graph.

## Topics to Prioritize

- ASTs, IR design, SSA, data-flow analysis, optimization, lowering,
  code generation, LLVM IR, and MLIR.
```

## Default profile and backward compatibility

Loose files such as `my_data/profile.md` still work and appear as **Default** in the
dropdown. The Default profile intentionally ignores everything inside
`my_data/applications/`; it never loads every saved application at once.

## Privacy and file rules

- Use `.md` or `.txt` files. PDFs, Word documents, and images are not read.
- Keep the selected profile concise—ideally no more than 15-20 pages total.
- `my_data/` is gitignored except for this README, so personal files are not committed.
