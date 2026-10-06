#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.initializer import initialise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile all professional sources using the authenticated Codex CLI.")
    parser.add_argument("--force", action="store_true", help="Extract again even if the corpus is unchanged; previous profiles are archived")
    args = parser.parse_args()
    try:
        result = initialise(force=args.force)
        print(f"Profile revision {result['revision']}: {len(result['profile']['facts'])} facts")
    except KeyboardInterrupt:
        parser.exit(130, "\nInterrupted. Completed document extractions are cached; rerun this command to resume.\n")
    except Exception as exc:
        parser.exit(1, str(exc) + "\n")
