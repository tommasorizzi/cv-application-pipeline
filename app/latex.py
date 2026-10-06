from __future__ import annotations
import re
import subprocess
from pathlib import Path
from app.utils import tool_available


class LatexError(RuntimeError):
    pass


def compile_pdf(tex_path: Path) -> Path:
    if tool_available("latexmk"):
        command = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", tex_path.name]
    elif tool_available("lualatex"):
        command = ["lualatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", tex_path.name]
    else:
        raise LatexError("LaTeX compiler unavailable: install latexmk or lualatex.")
    result = subprocess.run(command, cwd=tex_path.parent, capture_output=True, text=True, timeout=120)
    (tex_path.with_suffix(".build.txt")).write_text(result.stdout + result.stderr, encoding="utf-8")
    pdf = tex_path.with_suffix(".pdf")
    if result.returncode or not pdf.exists():
        raise LatexError(f"LaTeX compilation failed for {tex_path.name}: {(result.stdout + result.stderr)[-1800:]}")
    log = tex_path.with_suffix(".log").read_text(errors="replace")
    if "Missing character:" in log:
        raise LatexError("Missing glyph detected in " + tex_path.name)
    return pdf


def ats_text(pdf_path: Path) -> str:
    if not tool_available("pdftotext"):
        raise LatexError("pdftotext is required for PDF QA")
    result = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf_path), "-"], capture_output=True, text=True, timeout=30)
    if result.returncode or not result.stdout.strip():
        raise LatexError(f"Cannot extract PDF text: {pdf_path.name}")
    return result.stdout


def pdf_page_count(pdf_path: Path) -> int:
    if not tool_available("pdfinfo"):
        raise LatexError("pdfinfo is required for page-count QA")
    result = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, timeout=30)
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.M)
    if result.returncode or not match:
        raise LatexError("Unable to determine PDF page count")
    return int(match.group(1))


def check_pdf(pdf: Path, max_pages: int, required: list[str]) -> dict:
    pages, text = pdf_page_count(pdf), ats_text(pdf)
    compact = re.sub(r"\s+", "", text).casefold()
    for phrase in required:
        if re.sub(r"\s+", "", phrase).casefold() not in compact:
            raise LatexError(f"ATS extraction missing required text in {pdf.name}: {phrase}")
    if any(token in text for token in ("{{", "}}", "[INSERT", "TODO")):
        raise LatexError("Unresolved placeholder in PDF")
    if pages > max_pages:
        raise LatexError(f"{pdf.name} has {pages} pages; maximum is {max_pages}")
    log = pdf.with_suffix(".log").read_text(errors="replace")
    overflows = re.findall(r"Overfull \\hbox \((\d+(?:\.\d+)?)pt too wide\)", log)
    if any(float(size) > 5 for size in overflows):
        raise LatexError(f"Text extends past the margin in {pdf.name}; shorten long fields")
    pdf.with_suffix(".txt").write_text(text, encoding="utf-8")
    return {"pages": pages, "text_extraction": "passed", "required_text": required}
