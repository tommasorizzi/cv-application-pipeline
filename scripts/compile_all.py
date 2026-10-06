#!/usr/bin/env python3
"""Verify saved LaTeX in a temporary directory; never overwrite completed runs."""
import sys
import shutil
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.latex import compile_pdf
from app.utils import APPLICATIONS_DIR

if __name__ == "__main__":
    for cv in APPLICATIONS_DIR.glob("*/CV.tex"):
        with tempfile.TemporaryDirectory(prefix="cv-verify-") as directory:
            for name in ("CV.tex", "Cover_Letter.tex"):
                source = cv.with_name(name)
                if source.exists():
                    target = Path(directory) / name
                    shutil.copy2(source, target)
                    compile_pdf(target)
                    print(f"Verified {source}")
