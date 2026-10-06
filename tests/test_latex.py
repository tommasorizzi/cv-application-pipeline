import pytest

from app.latex import compile_pdf
from app.utils import tool_available


@pytest.mark.skipif(not (tool_available("latexmk") or tool_available("lualatex")), reason="LaTeX compiler not installed")
def test_compiler_reports_pdf_for_minimal_document(tmp_path):
    source = tmp_path / "tiny.tex"
    source.write_text("\\documentclass{article}\\begin{document}Test\\end{document}", encoding="utf-8")
    assert compile_pdf(source).exists()
