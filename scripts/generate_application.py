#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import generate_application


def main():
    parser = argparse.ArgumentParser(description="Tailor and audit an application with your authenticated Codex CLI.")
    parser.add_argument("job_description", type=Path)
    parser.add_argument("--company", default="")
    parser.add_argument("--role", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--language", default="English")
    parser.add_argument("--cv-length", choices=["1", "2"], default="1")
    parser.add_argument("--notes", default="")
    parser.add_argument("--revision-of", type=Path)
    parser.add_argument("--analyze-only", action="store_true")
    args = parser.parse_args()
    try:
        print(generate_application(args.job_description.read_text(encoding="utf-8"), args.company, args.role, args.url, args.language, args.cv_length, args.notes, revision_of=args.revision_of, analyze_only=args.analyze_only))
    except KeyboardInterrupt:
        parser.exit(130, "\nInterrupted. Completed profile extractions are cached; rerun this command to resume.\n")
    except Exception as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
