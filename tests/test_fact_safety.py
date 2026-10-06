import pytest
from app.validator import FactualError, normalize_section_order, validate_bundle, validate_review


def test_missing_and_uncertain_evidence_blocked(bundle, profile):
    bundle["cv"]["skills"][0]["items"].append({"text": "CUDA", "fact_ids": ["invented"]})
    with pytest.raises(FactualError, match="Unknown"):
        validate_bundle(bundle, profile)
    bundle["cv"]["skills"][0]["items"].pop()
    profile["facts"][0]["status"] = "conflicting"
    with pytest.raises(FactualError, match="conflicting"):
        validate_bundle(bundle, profile)


def test_known_id_does_not_override_semantic_rejection(bundle, profile):
    bundle["cv"]["skills"][0]["items"].append({"text": "Expert CUDA developer", "fact_ids": ["layout_reference_main3"]})
    claims = validate_bundle(bundle, profile)
    review = {"approved": False, "checked_claim_paths": [c["path"] for c in claims], "findings": [{"severity": "high", "location": "cv.skills", "explanation": "Cited source does not support CUDA expertise"}]}
    with pytest.raises(FactualError, match="CUDA"):
        validate_review(review, claims)


def test_auditor_must_check_all_rendered_claims(bundle, profile):
    claims = validate_bundle(bundle, profile)
    assert any(c["path"].endswith(".label") for c in claims)
    assert any(c["path"].endswith(".category") for c in claims)
    with pytest.raises(FactualError, match="every rendered"):
        validate_review({"approved": True, "findings": [], "checked_claim_paths": []}, claims)


def test_empty_sections_omitted_by_style_pass_are_restored(bundle, profile):
    bundle["cv"]["section_order"] = ["experience", "skills", "education", "publications", "languages"]
    normalize_section_order(bundle)
    assert bundle["cv"]["section_order"] == ["experience", "skills", "education", "publications", "languages", "projects", "conferences"]
    validate_bundle(bundle, profile)
