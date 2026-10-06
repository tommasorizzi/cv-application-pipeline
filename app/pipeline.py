"""Job analysis → drafting → style → independent audit → rendering → PDF QA."""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from app.codex_runner import CodexRunner
from app.initializer import initialise
from app.latex import LatexError, check_pdf, compile_pdf
from app.models import Bundle, JobAnalysis, Review
from app.renderer import render_cover_letter, render_cv
from app.utils import PROFILE_DIR, ROOT, dump_yaml, load_yaml, make_application_dir, sha256
from app.validator import FactualError, audit_markdown, eligible_facts, normalize_section_order, validate_bundle, validate_review


def instruction(name: str) -> str:
    return (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def analyze_job(description: str, profile: dict, *, runner=None, output_dir: Path, metadata=None) -> dict:
    if not description.strip():
        raise ValueError("Job description is required")
    runner = runner or CodexRunner()
    analysis = runner.run(instruction("analyze_job"), {"job_description": description, "metadata": metadata or {}, "eligible_facts": eligible_facts(profile)}, JobAnalysis, output_dir, "job-analysis")
    JobAnalysis.model_validate(analysis)
    known = {f["id"] for f in eligible_facts(profile)}
    for requirement in analysis["requirements"]:
        ids = set(requirement["fact_ids"])
        if not ids <= known or requirement["match"] == "no_evidence" and ids or requirement["match"] != "no_evidence" and not ids:
            raise FactualError("Invalid requirement-to-evidence mapping: " + requirement["requirement"])
    return analysis


def generate_application(job_description: str, company="", role="", url="", language="English", cv_length="1", notes="", *, runner=None, progress=print, profile_dir: Path = PROFILE_DIR, revision_of: Path | None = None, analyze_only=False) -> Path:
    if not job_description.strip():
        raise ValueError("Job description is required")
    if str(cv_length) not in {"1", "2"}:
        raise ValueError("CV length must be 1 or 2 pages")
    runner = runner or CodexRunner()
    folder = make_application_dir(company, role)
    traces = folder / "traces"
    traces.mkdir()
    (folder / "job_description.md").write_text(job_description, encoding="utf-8")
    metadata = {"company": company, "role": role, "url": url, "language": language, "cv_length": str(cv_length), "notes": notes, "revision_of": str(revision_of) if revision_of else None}
    dump_yaml(metadata, folder / "request.yaml")
    def state(name, **extra):
        dump_yaml({"stage": name, **extra}, folder / "status.yaml")
        progress(name.replace("_", " ").capitalize())
    try:
        state("initializing_profile")
        record = initialise(profile_dir=profile_dir, runner=runner, progress=progress)
        profile = record["profile"]
        manifest = load_yaml(profile_dir / "source_manifest.yaml")["sources"]
        dump_yaml(record, folder / "profile_snapshot.yaml")
        dump_yaml({"sources": manifest}, folder / "source_manifest.yaml")
        state("analyzing_job")
        analysis = analyze_job(job_description, profile, runner=runner, output_dir=traces, metadata=metadata)
        dump_yaml(analysis, folder / "job_analysis.yaml")
        if analyze_only:
            state("analysis_complete")
            return folder
        context = {"job_description": job_description, "metadata": metadata, "job_analysis": analysis, "eligible_facts": eligible_facts(profile), "voice_guide": profile["voice_guide"], "layout": "User templates: large left-aligned name; teal headline and ruled headings; labelled bullets; skill table; compact education; selected publications/conferences; languages. 10pt, A4, 1.3cm margins."}
        if revision_of:
            if load_yaml(revision_of / "status.yaml").get("stage") != "ready_for_human_review":
                raise ValueError("Revisions require a completed application")
            context["previous_bundle"] = load_yaml(revision_of / "application.yaml")
        state("drafting_application")
        bundle = normalize_section_order(runner.run(instruction("tailor_cv"), context, Bundle, traces, "draft"))
        validate_bundle(bundle, profile)
        state("reviewing_style")
        bundle = normalize_section_order(runner.run(instruction("style_review"), {**context, "bundle": bundle, "feedback": "Review natural voice, 300–400 word letter, concise technical CV; no unsupported enrichment. Preserve all seven section_order entries even when their content arrays are empty."}, Bundle, traces, "style"))
        for attempt in range(3):
            state("auditing_claims", attempt=attempt + 1)
            claims = validate_bundle(bundle, profile)
            dump_yaml(bundle, folder / "application.yaml")
            dump_yaml(bundle["cv"], folder / "tailored_cv.yaml")
            dump_yaml(bundle["letter"], folder / "cover_letter.yaml")
            review = runner.run(instruction("factual_audit"), {**context, "bundle": bundle, "claims": claims}, Review, traces, f"audit-{attempt}")
            (folder / "audit.md").write_text(audit_markdown(review, claims, profile, manifest), encoding="utf-8")
            try:
                validate_review(review, claims)
                # Failed/incomplete runs keep working files away from the final download paths.
                build = folder / "build" / str(attempt)
                build.mkdir(parents=True)
                state("compiling_documents")
                render_cv(bundle["cv"], build / "CV.tex")
                render_cover_letter(bundle["letter"], build / "Cover_Letter.tex", bundle["cv"]["header"])
                compile_pdf(build / "CV.tex")
                compile_pdf(build / "Cover_Letter.tex")
                state("checking_pdf_quality")
                cv = bundle["cv"]
                contact = [cv["header"][key]["text"] for key in ("name", "email")]
                selected_skills = [item["text"] for group in cv["skills"] for item in group["items"][:1]]
                qa = {"cv": check_pdf(build / "CV.pdf", int(cv_length), contact + ["Professional Profile", "Experience", "Education", "Technical Skills"] + selected_skills), "letter": check_pdf(build / "Cover_Letter.pdf", 1, contact)}
                break
            except (FactualError, LatexError) as exc:
                if attempt == 2:
                    raise
                state("correcting_content", reason=str(exc))
                bundle = normalize_section_order(runner.run(instruction("style_review"), {**context, "bundle": bundle, "feedback": str(exc) + " Preserve all seven section_order entries.", "review": review}, Bundle, traces, f"correction-{attempt}"))
        for name in ("CV", "Cover_Letter"):
            for extension in (".pdf", ".tex", ".txt"):
                shutil.copy2(build / (name + extension), folder / (name + extension))
        dump_yaml(qa, folder / "pdf_qa.yaml")
        summary_items = [
            item for item in bundle["change_summary"]
            if "not been rendered or verified" not in item.lower()
            and "added the full name to the signoff" not in item.lower()
        ]
        summary_items.append(
            f"PDF QA verified the {qa['cv']['pages']}-page CV and "
            f"{qa['letter']['pages']}-page cover letter, including ATS text extraction and page geometry."
        )
        (folder / "change_summary.md").write_text("# Change summary\n\n" + "\n".join("- " + item for item in summary_items) + "\n\n## Evidence gaps\n" + "\n".join("- " + item for item in analysis["gaps"]), encoding="utf-8")
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        versioned = [p for directory in ("app", "templates", "prompts", "schemas") for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        dump_yaml({"pipeline_version": "0.2.0", "git_commit": revision.stdout.strip() if revision.returncode == 0 else "uncommitted", "source_fingerprint": record["source_fingerprint"], "profile_revision": record["revision"], "file_hashes": {str(p.relative_to(ROOT)): sha256(p) for p in versioned}}, folder / "provenance.yaml")
        state("ready_for_human_review")
        return folder
    except KeyboardInterrupt:
        state("interrupted", error="Cancelled by user; completed profile extractions are cached")
        raise
    except Exception as exc:
        state("failed", error=str(exc))
        raise RuntimeError(f"{exc}\nSaved run: {folder}") from exc
