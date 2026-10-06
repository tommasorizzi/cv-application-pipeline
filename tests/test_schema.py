import pytest
from pydantic import ValidationError
from app.models import Bundle
from app.initializer import inventory, validate_profile
from app.initializer import initialise
from app.initializer import apply_reconciliation
from app.utils import dump_yaml, load_yaml


def test_schema_rejects_unstructured_content():
    with pytest.raises(ValidationError):
        Bundle.model_validate({"cv": {"summary": "invented"}, "letter": {}, "change_summary": []})


def test_inventory_reads_nested_cover_letters_excludes_identity_scan(tmp_path):
    nested = tmp_path / "old"
    nested.mkdir()
    (nested / "CoverLetter.txt").write_text("Dear hiring team, I implemented Python simulation workflows.")
    (tmp_path / "passport.txt").write_text("sensitive identity number")
    manifest, documents = inventory(tmp_path)
    assert len(manifest) == 2 and len(documents) == 1
    assert documents[0]["file"] == "old/CoverLetter.txt"
    assert "sensitive" not in str(documents)


def test_profile_rejects_fabricated_quotes_and_missing_coverage():
    documents = [{"source_id": "s1", "text": "Used Python for simulation."}]
    profile = {"facts": [{"id": "f1", "category": "skill", "text": "Python", "status": "explicit", "sources": [{"source_id": "s1", "quote": "Used CUDA"}], "review_note": ""}], "coverage": [{"source_id": "s1", "fact_ids": ["f1"], "omissions": []}], "voice_guide": "", "conflicts": []}
    with pytest.raises(ValueError, match="Unverifiable"):
        validate_profile(profile, documents)
    profile["facts"][0]["sources"][0]["quote"] = "Used Python"
    profile["coverage"] = []
    with pytest.raises(ValueError, match="every professional"):
        validate_profile(profile, documents)


def test_initialization_archives_existing_profile_and_reuses_unchanged_corpus(tmp_path):
    source = tmp_path / "sources"
    source.mkdir()
    document = source / "CoverLetter.txt"
    document.write_text("Dear hiring team, I used Python for simulation.")
    before = document.read_bytes()
    profile_dir = tmp_path / "profile"
    dump_yaml({"user_notes": "preserve me"}, profile_dir / "master_profile.yaml")
    class Extractor:
        calls = 0
        def run(self, instruction, context, model, output_dir, stage):
            self.calls += 1
            sid = context["documents"][0]["source_id"]
            return {"facts": [{"id": "python", "category": "skill", "text": "Python", "status": "explicit", "sources": [{"source_id": sid, "quote": "I used Python for simulation."}], "review_note": ""}], "coverage": [{"source_id": sid, "fact_ids": ["python"], "omissions": []}], "voice_guide": "Direct", "conflicts": []}
    runner = Extractor()
    first = initialise(source, profile_dir, runner=runner)
    second = initialise(source, profile_dir, runner=runner)
    assert runner.calls == 1 and first == second
    assert document.read_bytes() == before
    old = profile_dir / "versions" / first["revision"] / "previous/master_profile.yaml"
    assert load_yaml(old)["user_notes"] == "preserve me"


def test_per_document_cache_resumes_and_excludes_removed_sources(tmp_path):
    source = tmp_path / "sources"
    source.mkdir()
    (source / "CoverLetter_A.txt").write_text("Dear hiring team, I used Python.")
    second = source / "CoverLetter_B.txt"
    second.write_text("Dear hiring team, I used Fortran.")
    profile_dir = tmp_path / "profile"
    class Extractor:
        calls = []
        interrupt = True
        def run(self, instruction, context, model, output_dir, stage):
            if stage.startswith("reconcile"):
                return {"duplicate_groups": [], "flags": [], "voice_guide": "Direct", "conflicts": []}
            document = context["documents"][0]
            self.calls.append(document["file"])
            if self.interrupt and document["file"].endswith("B.txt"):
                raise KeyboardInterrupt
            sid = document["source_id"]
            language = "Python" if document["file"].endswith("A.txt") else "Fortran"
            return {"facts": [{"id": "skill", "category": "skill", "text": language, "status": "explicit", "sources": [{"source_id": sid, "quote": "I used " + language + "."}], "review_note": ""}], "coverage": [{"source_id": sid, "fact_ids": ["skill"], "omissions": []}], "voice_guide": "Direct", "conflicts": []}
    runner = Extractor()
    with pytest.raises(KeyboardInterrupt):
        initialise(source, profile_dir, runner=runner)
    assert len(list((profile_dir / ".cache/documents").glob("*.yaml"))) == 1
    runner.interrupt = False
    result = initialise(source, profile_dir, runner=runner)
    assert runner.calls.count("CoverLetter_A.txt") == 1
    assert {f["text"] for f in result["profile"]["facts"]} == {"Python", "Fortran"}
    second.unlink()
    result = initialise(source, profile_dir, runner=runner)
    assert {f["text"] for f in result["profile"]["facts"]} == {"Python"}
    assert runner.calls.count("CoverLetter_A.txt") == 1


def test_reconciliation_cannot_upgrade_uncertain_coursework():
    fact = {"id": "course", "category": "education", "text": "University coursework in numerical methods", "status": "uncertain", "sources": [{"source_id": "s1", "quote": "NUMERICAL METHODS"}], "review_note": "Completion unclear"}
    profile = {"facts": [fact], "coverage": [{"source_id": "s1", "fact_ids": ["course"], "omissions": []}], "voice_guide": "", "conflicts": []}
    decisions = {"duplicate_groups": [], "flags": [], "voice_guide": "", "conflicts": []}
    assert apply_reconciliation(profile, decisions)["facts"][0]["status"] == "uncertain"
    decisions["duplicate_groups"] = [["course", "invented"]]
    with pytest.raises(ValueError, match="duplicate group"):
        apply_reconciliation(profile, decisions)
