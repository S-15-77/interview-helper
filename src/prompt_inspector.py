"""Inspect local prompt assembly without calling Ollama."""

import argparse
import json

from src.llm_client import build_prompt, inspect_prompt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--profile")
    parser.add_argument("--context", default="")
    parser.add_argument("--full", action="store_true", help="Print the assembled prompt")
    args = parser.parse_args()
    inspection = inspect_prompt(args.context, args.question, args.profile)
    if args.full:
        inspection["prompt"] = build_prompt(args.context, args.question, args.profile)
    print(json.dumps(inspection, indent=2))


if __name__ == "__main__":
    main()
