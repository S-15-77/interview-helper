import json
from collections.abc import Iterator

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

SYSTEM_PROMPT = (
    "You are a calm, concise interview coach helping someone practice mock "
    "interviews out loud with a friend. You'll be given the last part of the "
    "conversation for context and the question just asked. Respond with a "
    "short spoken-style answer the user can read and say naturally: use a "
    "STAR structure (Situation, Task, Action, Result) for behavioral "
    "questions, and a clear structured explanation (with a short code "
    "snippet only if truly needed) for technical questions. Keep it under "
    "150 words. Do not restate the question."
)


def build_prompt(context: str, question: str) -> str:
    context = context.strip()
    context_block = f"Recent conversation:\n{context}\n\n" if context else ""
    return f"{SYSTEM_PROMPT}\n\n{context_block}Question: {question}\n\nAnswer:"


def stream_answer(question: str, context: str = "", model: str = "llama3.2") -> Iterator[str]:
    payload = {
        "model": model,
        "prompt": build_prompt(context, question),
        "stream": True,
    }
    with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=30) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("response"):
                yield chunk["response"]
            if chunk.get("done"):
                break
