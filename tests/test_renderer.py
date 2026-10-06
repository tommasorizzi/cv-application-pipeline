from app.renderer import render_cover_letter, render_cv


def test_template_matches_reference_and_escapes_content(tmp_path, bundle):
    bundle["cv"]["summary"]["text"] = r"A & B: 100% \input{secret}"
    text = render_cv(bundle["cv"], tmp_path / "CV.tex").read_text()
    assert r"\definecolor{accent}{RGB}{0,82,105}" in text
    assert r"\Huge\bfseries" in text
    assert r"\section*{Selected Publications}" in text
    assert r"\section*{Languages}" in text
    assert r"\textbackslash{}input\{secret\}" in text
    assert r"\input{" not in text
    assert "linkedin.com/in/ada-example" in text
    assert ">https://linkedin" not in text
    letter = render_cover_letter(bundle["letter"], tmp_path / "Letter.tex", bundle["cv"]["header"]).read_text()
    assert "ada@example.com" in letter



def test_cover_letter_does_not_repeat_name_in_signoff(tmp_path, bundle):
    name = bundle["cv"]["header"]["name"]["text"]
    bundle["letter"]["signoff"] = f"Kind regards, {name}"
    letter = render_cover_letter(bundle["letter"], tmp_path / "Letter.tex", bundle["cv"]["header"]).read_text()
    assert letter.count(name) == 2  # header plus the single template-owned signature
    assert "Kind regards," in letter
