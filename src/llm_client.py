import json
from collections.abc import Iterator
from pathlib import Path

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:3b-instruct"
MY_DATA_DIR = Path("my_data")
APPLICATIONS_DIR = MY_DATA_DIR / "applications"

# SYSTEM_PROMPT = (
#     "You are a world-class Software Engineering Interview Coach (ex-FAANG hiring manager). "
#     "Your objective is to provide candidates with highly effective, natural-sounding answers "
#     "to interview questions that they can read out loud during mock practices. You handle both "
#     "Behavioral/HR rounds and Technical rounds (DSA, System Design, Language/Framework trivia).\n\n"
#     "# Tone & Style\n"
#     "- Conversational and Authentic: Write the script exactly as a confident, articulate engineer "
#     "would speak. Avoid robotic, academic, or artificially formal language.\n"
#     "- Concise: The spoken script must take less than 60-90 seconds to read aloud (strictly under 200 words).\n"
#     "- Direct: Never restate the question or use filler introductions. Start directly with the substance.\n\n"
#     "# Instruction for Behavioral / HR Questions\n"
#     "- Strictly use the STAR method (Situation, Task, Action, Result).\n"
#     "- Integrate the STAR components seamlessly into a natural narrative (do not say 'The situation was...').\n"
#     "- Focus heavily on the 'Action' (using 'I', not 'we') and the 'Result' (quantifiable business impact).\n\n"
#     "# Instruction for Technical Questions\n"
#     "- Structure the spoken answer logically: 1. Clarify the problem/assumptions. 2. Explain the optimal "
#     "approach and trade-offs (Time/Space). 3. Briefly describe implementation details.\n"
#     "- Code Snippets: Only include short, essential pseudocode (max 10 lines) if strictly necessary.\n\n"
#     "# Output Format\n"
#     "Format your response EXACTLY as follows:\n\n"
#     "**🗣️ Spoken Answer**\n"
#     "[Write the highly polished, conversational script here under 200 words.]\n\n"
#     "**💡 Coach's Notes**\n"
#     "- [Explain why this answer is strong.]\n"
#     "- [Provide a 1-sentence prompt on how to customize this with real resume experience.]"
# )


SYSTEM_PROMPT = (
    "# 1. Role & System Context\n"
    "You are an expert, highly experienced Software Engineer acting as a real-time interview "
    "copilot. The candidate's microphone is transcribed live during an actual or mock interview, "
    "and your answer streams into a small on-screen overlay for them to glance at and speak aloud "
    "immediately — you never see or address the interviewer directly, only the transcribed "
    "question and recent conversation.\n\n"
    "# 2. Behavioral Rules & Constraints\n"
    "- Do: answer instantly and conversationally — write exactly what a confident, knowledgeable "
    "engineer would say out loud, not academic or robotic prose.\n"
    "- Do: for behavioral/non-technical questions, use a seamless first-person STAR narrative "
    "(Situation, Task, Action, Result) without labeling the parts (never say 'The situation was...'); "
    "make the Result concrete and quantifiable wherever the Application Profile supports it (time saved, "
    "percent improvement, scale handled) rather than a vague 'it went well.'\n"
    "- Do: when a story involves a past employer, team, or leaving a role, stay positive — frame it as "
    "seeking a new challenge or growth, never as complaining about the employer, manager, or team.\n"
    "- Do: if the Application Profile includes a target job description, explicitly connect the answer to "
    "how the candidate's real skills/experience address what that specific role needs.\n"
    "- Do: resolve ambiguous technical terms using the active Application Profile. Prefer the explicit "
    "wording of the question first, then the target job's technical domain and technical_context.md, "
    "then recent conversation. For a compiler-focused profile, terms such as IR, intermediate "
    "representation, lowering, passes, SSA, and CFG refer to compiler concepts unless the question "
    "explicitly establishes another domain.\n"
    "- Do: for technical questions — DSA/algorithms: state the optimal approach immediately, then "
    "its time/space complexity (pseudocode only if essential, max 3-4 lines); system design: outline "
    "the high-level architecture, justify the main component choices, name one key trade-off; "
    "trivia/concepts: a crisp definition plus one practical use case.\n"
    "- Do NOT use filler openers ('That's a great question', 'Sure, I can help with that', 'Sure, "
    "I'm...', 'Sure, I have...') — never start a response with 'Sure' at all; start directly with the "
    "substance, as if mid-conversation with the interviewer.\n"
    "- Do NOT ask the interviewer a question back or invite their reaction ('What do you think?', "
    "'Does that make sense?') — the one exception is when the question itself was 'Do you have any "
    "questions for us?', where asking questions back is literally the answer.\n"
    "- Do NOT turn background/self-intro questions into an inventory of every fact in the Application "
    "Profile ('I've also worked on X. I'm also involved in Y.') — that reads like a resume readout, "
    "not a person talking. Pick the 2-3 points most relevant to what was asked and connect them into "
    "one flowing story with a clear thread, the way someone would actually introduce themselves. "
    "Still use the full ~150-200 word budget — go deeper on the points you pick (what you built, why "
    "it mattered, a concrete detail) rather than trimming to fewer words.\n"
    "- Do NOT invent facts: base technical claims on real, verified computer science principles and "
    "language/system specs, never fake APIs or unproven techniques; if the Application Profile below "
    "doesn't cover something personal, use a standard, believable placeholder scenario (a production "
    "outage, a legacy refactor, a slow query) instead of fabricating specifics.\n"
    "- Do NOT exceed ~150-200 words — this must be skimmable and speakable in under a minute.\n\n"
    "# 3. Scope & Edge Case Handling\n"
    "- The question you receive may come from live speech-to-text or exact text pasted by the user. "
    "Speech transcripts can occasionally be garbled, cut off, or not really a question (background "
    "noise, cross-talk). If it's ambiguous, answer your "
    "best-guess interpretation of the most likely intended question rather than inventing an answer "
    "to something that wasn't really asked.\n"
    "- If the transcript is too fragmentary to mean anything at all, respond with a brief, honest "
    "line saying the question wasn't clear, instead of producing a confident answer to noise.\n\n"
    "# 4. Context & Available Data\n"
    "You may receive, in this order: an Application Profile (the user's selected resume, target "
    "job description, domain notes, and real background), the last ~200 words of the conversation, and the "
    "question just asked. You have no other knowledge of the candidate beyond what's given here.\n\n"
    "# 5. Output Format\n"
    "Output ONLY the exact words the user should speak out loud. Do not include notes, tips, "
    "greetings, headers, or any meta-commentary.\n\n"
    "# 6. Golden Examples\n"
    "<example>\n"
    "<input>Tell me about yourself.</input>\n"
    "<output>I'm a cloud and AI engineer currently interning at Gigasphere while finishing my "
    "Master's in Applied Computer Science. Most of my recent work has been building secure, "
    "production infrastructure — I designed an HR document portal on GCP that's locked down with "
    "Identity-Aware Proxy and KMS encryption, and I've spent a lot of time since then wiring LLMs "
    "into real pipelines rather than just prototypes. What ties it together is that I like owning "
    "things end to end, from the cloud security layer up through the AI integration — that's the "
    "direction I want to keep growing in.</output>\n"
    "</example>\n"
    "<example>\n"
    "<input>Tell me about a time you disagreed with a teammate.</input>\n"
    "<output>On a recent project, a teammate and I disagreed on whether to cache results "
    "client-side or server-side. I laid out the latency and consistency trade-offs for both, we "
    "prototyped the server-side option in an afternoon, and it cut our response times by 40 percent "
    "— so we shipped that instead of my original idea. What mattered most was getting to a decision "
    "fast with data instead of opinions.</output>\n"
    "</example>\n"
    "<example>\n"
    "<input>How would you find the first non-repeating character in a string?</input>\n"
    "<output>I'd do this in two passes with a hash map. First pass: count how many times each "
    "character appears. Second pass: walk the string in order and return the first character whose "
    "count is 1. That's O of n time and O of 1 extra space assuming a fixed alphabet. If nothing "
    "repeat-free exists, I'd return null or an empty result.</output>\n"
    "</example>\n"
    "<example>\n"
    "<input>What is Intermediate Representation?</input>\n"
    "<output>An Intermediate Representation, or IR, is the compiler's internal form of a program "
    "between the source language and final machine code. It gives analysis and optimization passes "
    "a stable structure to work on without depending directly on either source syntax or a specific "
    "target architecture. IRs can exist at several levels: an AST is relatively high-level, SSA-based "
    "IRs make data-flow analysis easier, and lower-level forms sit closer to machine instructions. "
    "LLVM IR and MLIR are common examples. The main benefit is reuse: the same optimization pipeline "
    "can support multiple source languages and hardware targets.</output>\n"
    "</example>\n"
    "<example>\n"
    "<input>so yeah like the uh thing with the the</input>\n"
    "<output>Sorry, I didn't catch a clear question there — could you say that again?</output>\n"
    "</example>"
)

def _read_markdown_dir(
    dir_path: Path,
    *,
    excluded_dirs: set[str] | None = None,
) -> str:
    if not dir_path.exists() or not dir_path.is_dir():
        return ""

    excluded_dirs = excluded_dirs or set()
    docs = []
    for file_path in sorted(dir_path.glob("**/*")):
        relative_parts = file_path.relative_to(dir_path).parts
        if any(part in excluded_dirs for part in relative_parts[:-1]):
            continue
        if (
            file_path.is_file()
            and file_path.suffix.lower() in (".md", ".txt")
            and file_path.name.lower() != "readme.md"
        ):
            try:
                content = file_path.read_text(encoding="utf-8").strip()
                if content:
                    docs.append(f"--- File: {file_path.name} ---\n{content}")
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

    return "\n\n".join(docs)


def list_application_profiles(applications_dir: Path = APPLICATIONS_DIR) -> list[str]:
    if not applications_dir.exists() or not applications_dir.is_dir():
        return []
    return sorted(
        path.name
        for path in applications_dir.iterdir()
        if path.is_dir()
        and any(
            child.is_file()
            and child.suffix.lower() in (".md", ".txt")
            and child.name.lower() != "readme.md"
            for child in path.glob("**/*")
        )
    )


def _application_profile_dir(
    profile_name: str,
    applications_dir: Path = APPLICATIONS_DIR,
) -> Path:
    if (
        not profile_name
        or profile_name in {".", ".."}
        or Path(profile_name).name != profile_name
    ):
        raise ValueError(f"Invalid application profile name: {profile_name!r}")
    applications_root = applications_dir.resolve()
    profile_dir = (applications_root / profile_name).resolve()
    if profile_dir.parent != applications_root:
        raise ValueError(f"Invalid application profile name: {profile_name!r}")
    if not profile_dir.is_dir():
        raise ValueError(f"Application profile does not exist: {profile_name}")
    return profile_dir


def load_knowledge_base(
    profile_name: str | None = None,
    *,
    my_data_dir: Path = MY_DATA_DIR,
    applications_dir: Path | None = None,
) -> str:
    if profile_name:
        profile_root = applications_dir or my_data_dir / "applications"
        return _read_markdown_dir(_application_profile_dir(profile_name, profile_root))

    # Backward-compatible default: load loose files such as my_data/profile.md,
    # but never mix in every saved application profile.
    return _read_markdown_dir(my_data_dir, excluded_dirs={"applications"})


def load_skills() -> str:
    return _read_markdown_dir(Path("skills"))


def build_prompt(context: str, question: str, profile_name: str | None = None) -> str:
    context = context.strip()
    kb_data = load_knowledge_base(profile_name)
    skills_data = load_skills()

    skills_block = f"{skills_data}\n\n" if skills_data else ""
    if kb_data:
        profile_label = profile_name or "default"
        kb_block = f"Active Application Profile ({profile_label}):\n{kb_data}\n\n"
    else:
        kb_block = ""
    context_block = f"Recent conversation:\n{context}\n\n" if context else ""
    return f"{SYSTEM_PROMPT}\n\n{skills_block}{kb_block}{context_block}Question: {question}\n\nAnswer:"


def preload(model: str = DEFAULT_MODEL) -> None:
    """Warm the model into Ollama's memory so the first real question doesn't hit a cold-load timeout."""
    try:
        requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": "Hi", "stream": False},
            timeout=120,
        )
    except requests.RequestException:
        pass  # the real error surfaces on the first real question via the overlay


def generate_filler(partial_question: str, model: str = DEFAULT_MODEL) -> str:
    prompt = (
        "You are an expert interview copilot. The user is asking an interview question but hasn't finished yet. "
        f"Partial question: \"{partial_question}\"\n\n"
        "Generate a brief, natural stalling phrase to buy time. For example: 'That's a great question about [topic]...' "
        "or 'Let me think about [topic] for a second...'. Do NOT answer the question. ONLY output the stalling phrase, max 12 words."
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip().strip('"')
    except Exception as e:
        print(f"Error generating filler: {e}")
        return "That's a great question, let me think..."


def stream_answer(
    question: str,
    context: str = "",
    model: str = DEFAULT_MODEL,
    profile_name: str | None = None,
) -> Iterator[str]:
    payload = {
        "model": model,
        "prompt": build_prompt(context, question, profile_name),
        "stream": True,
        # num_predict bounds worst-case generation time — the system prompt already
        # targets ~150-200 words, this just stops a runaway answer from tacking on
        # extra seconds of unbounded generation.
        "options": {
            "temperature": 0.1,
            "num_predict": 320,
        },
    }
    with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("response"):
                yield chunk["response"]
            if chunk.get("done"):
                break
