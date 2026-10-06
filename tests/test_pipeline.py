from pathlib import Path
import pytest
from app import pipeline
from app.utils import dump_yaml, load_yaml, tool_available


class FakeRunner:
    def __init__(self, bundle, reject=False):
        self.bundle, self.reject, self.stages = bundle, reject, []

    def run(self, instruction, context, model, output_dir, stage):
        self.stages.append(stage)
        if stage == "job-analysis":
            return {"company": "Test", "role": "Engineer", "role_family": "Simulation", "seniority": "unspecified", "responsibilities": ["Simulation"], "requirements": [{"requirement": "CUDA", "importance": "preferred", "match": "no_evidence", "fact_ids": [], "rationale": "Missing", "terminology": ["CUDA"], "cv_location": "omit"}], "ats_terms": [], "gaps": ["CUDA"], "dangerous_claims_to_avoid": ["CUDA"], "strategy": "Use supported simulation evidence"}
        if stage.startswith("audit-"):
            return {"approved": not self.reject, "checked_claim_paths": [c["path"] for c in context["claims"]], "findings": [{"severity": "high", "location": "cv", "explanation": "Unsupported claim"}] if self.reject else []}
        return self.bundle


def configure(monkeypatch, tmp_path, profile):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    dump_yaml({"sources": [{"id": "s1", "file": "fixture.txt"}]}, profile_dir / "source_manifest.yaml")
    monkeypatch.setattr(pipeline, "initialise", lambda **kwargs: {"profile": profile, "source_fingerprint": "test", "revision": "fixture"})
    def directory(company, role):
        path = tmp_path / f"application-{len(list(tmp_path.glob('application-*')))}"
        path.mkdir()
        return path
    monkeypatch.setattr(pipeline, "make_application_dir", directory)
    return profile_dir


@pytest.mark.skipif(not tool_available("latexmk"), reason="LaTeX not installed")
def test_complete_pipeline_compiles_both_pdfs_and_preserves_runs(tmp_path, monkeypatch, bundle, profile):
    profile_dir = configure(monkeypatch, tmp_path, profile)
    runner = FakeRunner(bundle)
    first = pipeline.generate_application("A test role with CUDA preferred", cv_length="2", runner=runner, profile_dir=profile_dir)
    assert load_yaml(first / "status.yaml")["stage"] == "ready_for_human_review"
    assert (first / "CV.pdf").exists() and (first / "Cover_Letter.pdf").exists()
    assert "job-analysis" in runner.stages and "style" in runner.stages and "audit-0" in runner.stages
    original = (first / "CV.pdf").read_bytes()
    second = pipeline.generate_application("Another test role", cv_length="2", runner=runner, profile_dir=profile_dir, revision_of=first)
    assert second != first and original == (first / "CV.pdf").read_bytes()


def test_failed_audit_never_publishes_pdfs(tmp_path, monkeypatch, bundle, profile):
    profile_dir = configure(monkeypatch, tmp_path, profile)
    with pytest.raises(RuntimeError, match="Unsupported claim"):
        pipeline.generate_application("test job", runner=FakeRunner(bundle, reject=True), profile_dir=profile_dir)
    run = next(tmp_path.glob("application-*"))
    assert not list(run.glob("*.pdf"))
    assert load_yaml(run / "status.yaml")["stage"] == "failed"
