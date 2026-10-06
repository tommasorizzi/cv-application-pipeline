"""Strict contracts shared by extraction, drafting, review and rendering."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Citation(StrictModel):
    source_id: str
    quote: str = Field(min_length=3)


class Fact(StrictModel):
    id: str
    category: Literal["identity", "education", "experience", "project", "skill", "publication", "conference", "language", "motivation"]
    text: str = Field(min_length=1, max_length=1500)
    status: Literal["explicit", "derived_safe", "uncertain", "conflicting"]
    sources: list[Citation] = Field(min_length=1)
    review_note: str


class Coverage(StrictModel):
    source_id: str
    fact_ids: list[str]
    omissions: list[str]


class Profile(StrictModel):
    facts: list[Fact] = Field(min_length=1)
    coverage: list[Coverage]
    voice_guide: str
    conflicts: list[str]


class FactFlag(StrictModel):
    fact_id: str
    status: Literal["uncertain", "conflicting"]
    reason: str


class ProfileReconciliation(StrictModel):
    duplicate_groups: list[list[str]]
    flags: list[FactFlag]
    voice_guide: str
    conflicts: list[str]


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=1800)
    fact_ids: list[str] = Field(min_length=1)


class Requirement(StrictModel):
    requirement: str
    importance: Literal["mandatory", "preferred", "context"]
    match: Literal["direct_match", "transferable_match", "weak_match", "no_evidence"]
    fact_ids: list[str]
    rationale: str
    terminology: list[str]
    cv_location: str


class JobAnalysis(StrictModel):
    company: str
    role: str
    role_family: str
    seniority: str
    responsibilities: list[str]
    requirements: list[Requirement]
    ats_terms: list[str]
    gaps: list[str]
    dangerous_claims_to_avoid: list[str]
    strategy: str


class Header(StrictModel):
    name: Claim
    location: Claim
    email: Claim
    links: list[Claim]


class Bullet(StrictModel):
    label: str = Field(max_length=65)
    claim: Claim


class Experience(StrictModel):
    title: Claim
    organisation: Claim
    period: Claim
    bullets: list[Bullet] = Field(min_length=1, max_length=7)


class Education(StrictModel):
    degree: Claim
    institution: Claim
    period: Claim
    details: list[Claim]


class SkillGroup(StrictModel):
    category: str = Field(max_length=45)
    items: list[Claim] = Field(min_length=1)


class CV(StrictModel):
    header: Header
    headline: Claim
    summary: Claim
    section_order: list[Literal["experience", "education", "skills", "publications", "conferences", "languages", "projects"]]
    experience: list[Experience] = Field(min_length=1)
    education: list[Education] = Field(min_length=1)
    skills: list[SkillGroup] = Field(min_length=1)
    projects: list[Bullet]
    publications: list[Claim]
    conferences: list[Claim]
    languages: list[Claim]


class Paragraph(StrictModel):
    text: str = Field(min_length=1, max_length=2200)
    fact_ids: list[str]


class Letter(StrictModel):
    salutation: str
    paragraphs: list[Paragraph] = Field(min_length=3, max_length=6)
    signoff: str


class Bundle(StrictModel):
    cv: CV
    letter: Letter
    change_summary: list[str]


class Finding(StrictModel):
    severity: Literal["high", "medium", "low"]
    location: str
    explanation: str


class Review(StrictModel):
    approved: bool
    findings: list[Finding]
    checked_claim_paths: list[str]


SCHEMAS = {"profile": Profile, "profile_reconciliation": ProfileReconciliation, "job_analysis": JobAnalysis, "tailored_cv": CV, "cover_letter": Letter, "application": Bundle, "review": Review}
