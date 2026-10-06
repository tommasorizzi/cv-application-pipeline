#!/usr/bin/env python3
"""Local layout preview from uploaded main(3).tex. Makes no model/network calls."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models import CV
from app.renderer import render_cv, render_cover_letter
from app.latex import compile_pdf, ats_text, pdf_page_count
from app.utils import ROOT, dump_yaml


def plain(text):
    text = re.sub(r"%[^\n]*", "", text)
    text = re.sub(r"\\(?:textbf|emph)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:enspace|hfill|small)\b", " ", text)
    text = re.sub(r"\\\\(?:\[[^\]]*\])?", " ", text)
    text = text.replace(r"\&", "&").replace(r"$\bullet$", "•").replace("--", "–")
    return " ".join(text.replace("{", "").replace("}", "").split())


def reference_cv():
    source = ROOT / "references/source_documents/main/main(3).tex"
    raw = source.read_text()
    sections = re.split(r"\\section\*\{([^}]+)\}", raw)
    sections = dict(zip(sections[1::2], sections[2::2]))
    def claim(text):
        return {"text": text, "fact_ids": ["layout_reference_main3"]}
    header = {"name": claim("Ada Example"), "location": claim("Stockholm, Sweden"), "email": claim("ada@example.com"), "links": [claim("linkedin.com/in/ada-example"), claim("github.com/ada-example")]}
    experience = sections[r"Research \& Multiphysics Experience"]
    bullets = []
    for item in re.findall(r"\\item (.*?)(?=\\item|\\end\{itemize\})", experience, re.S):
        label, text = plain(item).split(":", 1)
        bullets.append({"label": label, "claim": claim(text.strip())})
    education = []
    pattern = r"\\textbf\{([^}]+)\}\s*\\hfill\s*([^\n]+)\n(.*?)(?=\\textbf|\Z)"
    for degree, period, details in re.findall(pattern, sections["Education"], re.S):
        bits = plain(details).split(" | ")
        education.append({"degree": claim(plain(degree)), "period": claim(plain(period)), "institution": claim(bits[0]), "details": [claim(bit) for bit in bits[1:]]})
    skills = []
    for label, text in re.findall(r"\\textbf\{([^}]+)\}\s*&\s*(.*?)(?:\\\\|\\end\{tabularx\})", sections["Technical Skills"], re.S):
        skills.append({"category": plain(label), "items": [claim(item.strip()) for item in plain(text).split(",")]})
    publications = [claim(plain(item)) for item in re.findall(r"\\item (.*?)(?=\\item|\\end\{itemize\})", sections["Selected Publications"], re.S)]
    conferences = [claim(plain(item)) for item in re.split(r"\\\\(?:\[[^\]]*\])?", sections["Selected Conference Contributions"].strip()) if plain(item)]
    languages = [claim(plain(item)) for item in sections["Languages"].split(r"\end{document}")[0].strip().split(r"$\bullet$")]
    cv = {"header": header, "headline": claim("Plasma Physics & Multiphysics Simulation"), "summary": claim(plain(sections["Professional Profile"])), "section_order": ["experience", "education", "skills", "publications", "conferences", "languages", "projects"], "experience": [{"title": claim("Doctoral Researcher – Electromagnetic and Plasma Physics"), "organisation": claim("KTH Royal Institute of Technology, Stockholm, Sweden"), "period": claim("2023–Present"), "bullets": bullets}], "education": education, "skills": skills, "publications": publications, "conferences": conferences, "languages": languages, "projects": []}
    CV.model_validate(cv)
    return cv


if __name__ == "__main__":
    folder = ROOT / "staging/layout_preview"
    folder.mkdir(parents=True, exist_ok=True)
    cv = reference_cv()
    dump_yaml(cv, folder / "reference_content.yaml")
    render_cv(cv, folder / "CV.tex")
    compile_pdf(folder / "CV.tex")
    (folder / "CV.txt").write_text(ats_text(folder / "CV.pdf"))
    (folder / "README.md").write_text("# Layout preview\n\nContent locally transcribed from references/source_documents/main/main(3).tex. This is a renderer preview, not a generated application or audited job match. No private text was sent to any service.\n")
    print(f"Preview: {folder / 'CV.pdf'} ({pdf_page_count(folder / 'CV.pdf')} pages)")
