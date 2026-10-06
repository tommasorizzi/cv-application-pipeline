from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "references" / "source_documents"
PROFILE_DIR = ROOT / "profile"
APPLICATIONS_DIR = ROOT / "applications"


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def dump_yaml(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False, width=100)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_location(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def extract_text(path: Path) -> str:
    """Extract local text and never write to an evidence document."""
    if path.suffix.lower() == ".pdf":
        try:
            return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True, timeout=60).stdout
        except (FileNotFoundError, subprocess.SubprocessError):
            return ""
    if path.suffix.lower() == ".docx":
        try:
            from docx import Document
            return "\n".join(p.text for p in Document(path).paragraphs)
        except Exception:
            return ""
    return path.read_text(encoding="utf-8", errors="replace")


def classify_document(path: Path, text: str) -> str:
    name, sample = path.name.lower(), text.lower()[:5000]
    if "cover" in name or "letter" in name or "dear hiring" in sample:
        return "cover_letter"
    if name.startswith("cv") or "/cvs/" in path.as_posix().lower() or "professional profile" in sample:
        return "cv"
    if any(word in name for word in ("nucl", "publication", "tor")):
        return "publication_or_other_evidence"
    return "unknown"


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha1(value.encode()).hexdigest()[:10]}"


def paragraphize(text: str) -> list[str]:
    return [line for raw in text.splitlines() if len(line := re.sub(r"\s+", " ", raw).strip()) >= 24 and not line.isdigit()]


def slugify(value: str, fallback: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60]
    return result or fallback


def make_application_dir(company: str, role: str) -> Path:
    base = f"{date.today().isoformat()}_{slugify(company, 'company')}_{slugify(role, 'role')}"
    path, suffix = APPLICATIONS_DIR / base, 2
    while path.exists():
        path, suffix = APPLICATIONS_DIR / f"{base}_{suffix}", suffix + 1
    path.mkdir(parents=True)
    return path


_ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def latex_escape(value: object) -> str:
    return "".join(_ESCAPES.get(char, char) for char in str(value))


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None
