from __future__ import annotations
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from app.utils import ROOT, latex_escape


def _env(directory: Path) -> Environment:
    env = Environment(loader=FileSystemLoader(directory), undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True)
    env.filters["latex"] = latex_escape
    def link_target(text):
        target = text if text.startswith(("https://", "http://")) else "https://" + text
        if re.search(r"[\s{}\\]", target) or not re.match(r"https?://[^/]+", target):
            raise ValueError("Invalid contact URL")
        return latex_escape(target)
    env.filters["url"] = link_target
    def link_label(text):
        text = str(text)
        if "scholar.google." in text.lower():
            return "Google Scholar"
        return re.sub(r"^https?://", "", text).rstrip("/")
    env.filters["link_label"] = link_label
    return env


def render_cv(data: dict, destination: Path) -> Path:
    env = _env(ROOT / "templates/cv")
    style = (ROOT / "templates/cv/style.tex").read_text()
    destination.write_text(env.get_template("main.tex.j2").render(**data, style=style), encoding="utf-8")
    return destination


def render_cover_letter(data: dict, destination: Path, header: dict) -> Path:
    env = _env(ROOT / "templates/cover_letter")
    style = (ROOT / "templates/cover_letter/style.tex").read_text()
    name = header["name"]["text"]
    # The template owns the signature name. Models sometimes include it in the
    # sign-off as well, which would render the name twice.
    signoff = re.sub(rf"\s*{re.escape(name)}\s*$", "", data["signoff"], flags=re.IGNORECASE).rstrip()
    destination.write_text(
        env.get_template("main.tex.j2").render(**data, signoff_text=signoff, header=header, style=style),
        encoding="utf-8",
    )
    return destination
