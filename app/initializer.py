"""Complete source inventory and evidence-preserving profile extraction."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import copy
from datetime import datetime, timezone
from pathlib import Path
from app.codex_runner import CodexRunner
from app.models import Profile, ProfileReconciliation
from app.utils import PROFILE_DIR, ROOT, SOURCE_DIR, dump_yaml, extract_text, load_yaml, sha256


def normalize(text: str) -> str:
    return " ".join(text.split())


def inventory(source_dir: Path = SOURCE_DIR) -> tuple[list[dict], list[dict]]:
    manifest, documents = [], []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source_dir).as_posix()
        source_id = "src_" + hashlib.sha256(relative.encode()).hexdigest()[:12]
        entry = {"id": source_id, "file": relative, "sha256": sha256(path), "type": "unknown", "included": False, "reason": "Not identified as a professional evidence document"}
        name = path.name.lower()
        if any(term in name for term in ("passport", "id_rizzi", "profile_picture")):
            entry.update(type="personal_document", reason="Identity scans/photos are not application evidence")
        elif path.suffix.lower() in {".pdf", ".tex", ".txt", ".md", ".docx"}:
            text = extract_text(path)
            if "cover" in name or "dear hiring" in text.lower() or "dear " in text.lower() and "hiring team" in text.lower():
                kind = "cover_letter"
            elif name == "cv_master_context.md":
                kind = "candidate_context"
            elif "written interview" in text.lower() or "written_interview" in name:
                kind = "written_interview"
            elif name == "polimi_tor.pdf":
                kind = "education_transcript"
            elif path.suffix.lower() == ".pdf" and ("nucl" in name or name == "rizzi_nme.pdf"):
                kind = "publication"
            elif path.suffix == ".tex" and "\\section*{Education}" in text or "cvs" in relative.lower().split("/") or name.startswith("cv") and path.suffix.lower() == ".pdf":
                kind = "cv"
            else:
                kind = "other"
            entry["type"] = kind
            if kind in {"cv", "cover_letter", "candidate_context", "written_interview", "education_transcript", "publication"}:
                if not text.strip():
                    raise ValueError(f"Cannot extract professional source {relative}; install pdftotext or provide searchable text.")
                entry.update(included=True, reason="Professional source", text_sha256=hashlib.sha256(normalize(text).encode()).hexdigest())
                documents.append({"source_id": source_id, "file": relative, "type": kind, "text": text})
        manifest.append(entry)
    if not documents:
        raise ValueError("No readable CVs, cover letters or candidate context found.")
    groups, stems = {}, {}
    for entry in manifest:
        if entry["included"]:
            # Exact normalized duplicates and same-stem source/PDF representations share a group.
            key = entry.get("text_sha256")
            stem = str(Path(entry["file"]).with_suffix("")).lower()
            group = groups.get(key) or stems.get(stem) or entry["id"]
            groups[key] = stems[stem] = group
            entry["representation_group"] = group
    return manifest, documents


def fingerprint(manifest: list[dict]) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def validate_profile(profile: dict, documents: list[dict]) -> None:
    Profile.model_validate(profile)
    texts = {item["source_id"]: normalize(item["text"]) for item in documents}
    ids = [fact["id"] for fact in profile["facts"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate fact IDs in profile")
    errors = []
    for fact in profile["facts"]:
        for citation in fact["sources"]:
            if citation["source_id"] not in texts or normalize(citation["quote"]) not in texts[citation["source_id"]]:
                errors.append(f"Unverifiable source quotation for {fact['id']}: {citation}")
    coverage = profile["coverage"]
    if len(coverage) != len(texts) or {item["source_id"] for item in coverage} != set(texts):
        errors.append("Profile completeness check did not account for every professional document")
    for item in coverage:
        if not set(item["fact_ids"]) <= set(ids):
            errors.append("Coverage contains unknown fact IDs")
    if errors:
        raise ValueError("\n".join(errors))


def cache_key(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_cache(data: dict, path: Path) -> None:
    temporary = path.with_suffix(".pending.yaml")
    dump_yaml(data, temporary)
    temporary.replace(path)


def merge_extractions(extractions: list[dict]) -> dict:
    """Namespace per-document IDs, then combine exact duplicates without losing citations."""
    facts, coverage, conflicts, voices = [], [], [], []
    equivalents = {}
    for extraction in extractions:
        source_id = extraction["coverage"][0]["source_id"]
        remap = {}
        for fact in extraction["facts"]:
            fact = copy.deepcopy(fact)
            old_id = fact["id"]
            key = (fact["category"], normalize(fact["text"]), fact["status"])
            if key in equivalents:
                retained = equivalents[key]
                for citation in fact["sources"]:
                    if citation not in retained["sources"]:
                        retained["sources"].append(citation)
                if fact["review_note"] and fact["review_note"] not in retained["review_note"]:
                    retained["review_note"] += " " + fact["review_note"]
            else:
                fact["id"] = source_id + "__" + old_id
                facts.append(fact)
                equivalents[key] = fact
                retained = fact
            remap[old_id] = retained["id"]
        for item in extraction["coverage"]:
            coverage.append({**item, "fact_ids": list(dict.fromkeys(remap[fid] for fid in item["fact_ids"]))})
        conflicts.extend(extraction["conflicts"])
        voices.append(extraction["voice_guide"])
    return {"facts": facts, "coverage": coverage, "conflicts": conflicts, "voice_guide": "\n\n".join(voices)}


def apply_reconciliation(profile: dict, decisions: dict) -> dict:
    ProfileReconciliation.model_validate(decisions)
    profile = copy.deepcopy(profile)
    facts = {f["id"]: f for f in profile["facts"]}
    severity = {"explicit": 0, "derived_safe": 1, "uncertain": 2, "conflicting": 3}
    for flag in decisions["flags"]:
        if flag["fact_id"] not in facts:
            raise ValueError("Reconciliation flagged an unknown fact ID")
        fact = facts[flag["fact_id"]]
        if severity[flag["status"]] > severity[fact["status"]]:
            fact["status"] = flag["status"]
        fact["review_note"] = (fact["review_note"] + " " + flag["reason"]).strip()
    remap, used = {}, set()
    for group in decisions["duplicate_groups"]:
        if len(group) < 2 or len(set(group)) != len(group) or not set(group) <= set(facts) or used.intersection(group):
            raise ValueError("Invalid or overlapping duplicate group in reconciliation")
        if len({facts[fid]["category"] for fid in group}) != 1:
            raise ValueError("Cannot merge facts from different categories")
        retained = facts[group[0]]
        used.update(group)
        for fid in group[1:]:
            other = facts[fid]
            retained["status"] = max((retained["status"], other["status"]), key=severity.get)
            for citation in other["sources"]:
                if citation not in retained["sources"]:
                    retained["sources"].append(citation)
            if other["review_note"]:
                retained["review_note"] += " " + other["review_note"]
            remap[fid] = retained["id"]
    profile["facts"] = [f for f in facts.values() if f["id"] not in remap]
    for item in profile["coverage"]:
        item["fact_ids"] = list(dict.fromkeys(remap.get(fid, fid) for fid in item["fact_ids"]))
    profile["voice_guide"] = decisions["voice_guide"]
    profile["conflicts"] = list(dict.fromkeys(profile["conflicts"] + decisions["conflicts"]))
    return profile


def initialise(source_dir: Path = SOURCE_DIR, profile_dir: Path = PROFILE_DIR, runner=None, progress=print, force=False) -> dict:
    manifest, documents = inventory(source_dir)
    stamp = fingerprint(manifest)
    instruction = (ROOT / "prompts/initialize_profile.md").read_text()
    reconciliation_instruction = (ROOT / "prompts/reconcile_profile.md").read_text()
    extraction_version = cache_key({"prompt": instruction, "schema": Profile.model_json_schema(), "version": 3})
    policy_version = cache_key({"extraction": extraction_version, "reconciliation": reconciliation_instruction, "schema": ProfileReconciliation.model_json_schema()})
    active = profile_dir / "master_profile.yaml"
    if active.exists() and not force:
        prior = load_yaml(active)
        if prior.get("source_fingerprint") == stamp and prior.get("schema_version") == 3 and prior.get("policy_version") == policy_version:
            validate_profile(prior["profile"], documents)
            return prior
    runner = runner or CodexRunner()
    revision = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    work = profile_dir / "versions" / revision
    work.mkdir(parents=True)
    dump_yaml({"sources": manifest}, work / "source_manifest.yaml")
    dump_yaml({"documents": documents}, work / "source_text.yaml")
    progress(f"Processing {len(documents)} selected sources individually; completed documents are cached.")
    extractions = []
    for number, document in enumerate(documents, 1):
        key = cache_key({"document": document, "policy": extraction_version})
        cached = profile_dir / ".cache" / "documents" / f"{key}.yaml"
        extracted = None
        if cached.exists() and not force:
            try:
                extracted = load_yaml(cached)
                validate_profile(extracted, [document])
            except Exception:
                extracted = None
        if extracted is not None:
            progress(f"[{number}/{len(documents)}] Cached: {document['file']}")
        else:
            stage = f"document-{number:02d}"
            progress(f"[{number}/{len(documents)}] Extracting: {document['file']} (live log: {work / 'traces' / (stage + '-0.log-0.txt')})")
            context = {"documents": [document]}
            for attempt in range(2):
                extracted = runner.run(instruction, context, Profile, work / "traces", f"{stage}-{attempt}")
                try:
                    validate_profile(extracted, [document])
                    break
                except ValueError as exc:
                    if attempt: raise
                    context.update(previous_profile=extracted, repair=str(exc))
                    progress(f"Repairing quotation/coverage issues in {document['file']}…")
            write_cache(extracted, cached)
            progress(f"[{number}/{len(documents)}] Saved: {len(extracted['facts'])} facts from {document['file']}")
        extractions.append(extracted)
    profile = merge_extractions(extractions)
    if len(documents) > 1:
        progress(f"Reconciling {len(profile['facts'])} extracted facts across the selected sources…")
        context = {"profile": profile}
        key = cache_key({"profile": profile, "policy": policy_version})
        cached = profile_dir / ".cache" / "reconciliation" / f"{key}.yaml"
        reconciled = None
        if cached.exists() and not force:
            try:
                reconciled = apply_reconciliation(profile, load_yaml(cached))
                validate_profile(reconciled, documents)
                progress("Using cached reconciliation.")
            except Exception:
                reconciled = None
        if reconciled is None:
            for attempt in range(2):
                decisions = runner.run(reconciliation_instruction, context, ProfileReconciliation, work / "traces", f"reconcile-{attempt}")
                try:
                    reconciled = apply_reconciliation(profile, decisions)
                    validate_profile(reconciled, documents)
                    break
                except ValueError as exc:
                    if attempt: raise
                    context.update(previous_decisions=decisions, repair=str(exc))
            write_cache(decisions, cached)
        profile = reconciled
    validate_profile(profile, documents)
    # Verify the immutable originals still match the snapshot before publishing derived data.
    current, _ = inventory(source_dir)
    if fingerprint(current) != stamp:
        raise ValueError("Source corpus changed during extraction; retry initialization")
    result = {"schema_version": 3, "source_fingerprint": stamp, "policy_version": policy_version, "profile_status": "requires_user_review", "revision": revision, "profile": profile}
    dump_yaml(result, work / "master_profile.yaml")
    dump_yaml({"facts": profile["facts"]}, work / "evidence_index.yaml")
    dump_yaml({"projects": [f for f in profile["facts"] if f["category"] == "project"]}, work / "project_library.yaml")
    dump_yaml({"bullets": [f for f in profile["facts"] if f["category"] in {"project", "experience"}]}, work / "bullet_library.yaml")
    (work / "voice_guide.md").write_text(profile["voice_guide"], encoding="utf-8")
    report = ["# Initialization report", "", f"Professional sources: {len(documents)}; facts: {len(profile['facts'])}.", "", "## Conflicts and review items"]
    report += [f"- {f['id']} [{f['status']}]: {f['review_note']}" for f in profile["facts"] if f["status"] != "explicit"]
    report += [f"- {item}" for item in profile["conflicts"]]
    report += ["", "## Source coverage"]
    filenames = {d["source_id"]: d["file"] for d in documents}
    for item in profile["coverage"]:
        report.append(f"- {filenames[item['source_id']]}: {len(item['fact_ids'])} facts; unresolved/omitted: {'; '.join(item['omissions']) or 'none reported'}")
    report += ["", "## Inventory exclusions"]
    report += [f"- {item['file']}: {item['reason']}" for item in manifest if not item["included"]]
    (work / "initialization_report.md").write_text("\n".join(report), encoding="utf-8")
    # Archive all previous derived files, including any user modifications, before promotion.
    archive = work / "previous"
    archive.mkdir()
    for path in work.iterdir():
        if not path.is_file(): continue
        target = profile_dir / path.name
        if target.exists(): shutil.copy2(target, archive / target.name)
        shutil.copy2(path, target)
    progress(f"Profile ready: {len(profile['facts'])} facts. Review {profile_dir / 'initialization_report.md'}")
    return result
