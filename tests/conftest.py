import pytest
from scripts.preview_layout import reference_cv


@pytest.fixture
def bundle():
    cv = reference_cv()
    # All application integration tests below use a fake model; no source text leaves this machine.
    return {"cv": cv, "letter": {"salutation": "Dear Hiring Team,", "paragraphs": [{"text": "I am applying for the simulation role.", "fact_ids": []}, {"text": cv["summary"]["text"], "fact_ids": ["layout_reference_main3"]}, {"text": "I would welcome the opportunity to discuss the position.", "fact_ids": []}], "signoff": "Kind regards,"}, "change_summary": ["Test renderer and claim validation only."]}


@pytest.fixture
def profile():
    return {"facts": [{"id": "layout_reference_main3", "category": "experience", "text": "Local renderer test fixture", "status": "explicit", "sources": [{"source_id": "s1", "quote": "Test fixture only"}], "review_note": ""}], "coverage": [{"source_id": "s1", "fact_ids": ["layout_reference_main3"], "omissions": []}], "voice_guide": "Technical, restrained.", "conflicts": []}
