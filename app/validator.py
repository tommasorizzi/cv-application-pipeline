"""Deterministic provenance checks plus exhaustive semantic-review coverage."""
from __future__ import annotations
from app.models import Bundle, Review


class FactualError(ValueError):
    pass


SECTIONS = ["experience", "education", "skills", "projects", "publications", "conferences", "languages"]


def normalize_section_order(bundle: dict) -> dict:
    """Models may omit empty sections; the renderer still needs a complete order contract."""
    supplied = bundle.get("cv", {}).get("section_order", [])
    if any(section not in SECTIONS for section in supplied):
        raise FactualError("Section order contains an unsupported section")
    bundle["cv"]["section_order"] = list(dict.fromkeys(supplied)) + [section for section in SECTIONS if section not in supplied]
    return bundle


def claim_paths(value, path="") -> list[dict]:
    claims = []
    if isinstance(value, dict):
        if "text" in value and "fact_ids" in value:
            return [{"path": path, **value}]
        for key, item in value.items():
            claims.extend(claim_paths(item, f"{path}.{key}" if path else key))
        if "label" in value and "claim" in value:
            claims.append({"path": path + ".label", "text": value["label"], "fact_ids": value["claim"]["fact_ids"]})
        if "category" in value and "items" in value:
            claims.append({"path": path + ".category", "text": value["category"], "fact_ids": list({fid for item in value["items"] for fid in item["fact_ids"]})})
    elif isinstance(value, list):
        for index, item in enumerate(value):
            claims.extend(claim_paths(item, f"{path}[{index}]"))
    return claims


def eligible_facts(profile: dict) -> list[dict]:
    return [fact for fact in profile["facts"] if fact["status"] == "explicit"]


def validate_bundle(bundle: dict, profile: dict) -> list[dict]:
    Bundle.model_validate(bundle)
    known = {fact["id"] for fact in eligible_facts(profile)}
    claims = claim_paths({"cv": bundle["cv"], "letter": bundle["letter"]})
    for claim in claims:
        if not set(claim["fact_ids"]) <= known:
            raise FactualError(f"Unknown, uncertain or conflicting evidence in {claim['path']}")
    order = bundle["cv"]["section_order"]
    if len(order) != 7 or set(order) != set(SECTIONS):
        raise FactualError("Section order must include each supported section exactly once")
    return claims


def validate_review(review: dict, claims: list[dict]) -> None:
    Review.model_validate(review)
    expected = {claim["path"] for claim in claims}
    checked = review["checked_claim_paths"]
    if len(checked) != len(expected) or set(checked) != expected:
        raise FactualError("Factual review did not cover every rendered claim")
    if not review["approved"] or any(f["severity"] in {"high", "medium"} for f in review["findings"]):
        raise FactualError("Factual/style review requires correction: " + "; ".join(f["explanation"] for f in review["findings"]))


def audit_markdown(review: dict, claims: list[dict], profile: dict, manifest: list[dict]) -> str:
    facts = {fact["id"]: fact for fact in profile["facts"]}
    filenames = {item["id"]: item["file"] for item in manifest}
    lines = ["# Factual audit", "", f"Reviewer approved: {review['approved']}", "", "## Findings"]
    lines += [f"- {f['severity']}: {f['location']}: {f['explanation']}" for f in review["findings"]] or ["- None"]
    lines += ["", "## Claim → fact → source"]
    for claim in claims:
        lines += ["", f"### {claim['path']}", claim["text"]]
        for fid in claim["fact_ids"]:
            fact = facts[fid]
            lines.append(f"- {fid}: {fact['text']}")
            for citation in fact["sources"]:
                lines.append(f"  - {filenames[citation['source_id']]}: {citation['quote']}")
    return "\n".join(lines)
