from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st
from app.pipeline import generate_application
from app.utils import APPLICATIONS_DIR, load_yaml

st.set_page_config(page_title="Application studio", layout="wide")
st.title("Application studio")
st.caption("Tailor your CV and cover letter to the role, using your source documents and preferred layout.")
st.info("Generation uses your authenticated Codex service: professional source text is sent during profile initialization, then relevant facts and the job description during drafting. Original files stay on disk. Profile review items are excluded automatically.")
with st.form("application"):
    description = st.text_area("Job description", height=280)
    left, right = st.columns(2)
    company, role = left.text_input("Company (optional)"), right.text_input("Role title (optional)")
    url = st.text_input("Job URL (optional)")
    language = left.selectbox("Language", ["English", "Italian", "Swedish"])
    length = right.selectbox("Maximum CV pages", ["1", "2"])
    notes = st.text_area("Emphasis or revision instructions", placeholder="For example: emphasize C++ and HPC; reduce fusion-specific terminology.")
    history = sorted([p for p in APPLICATIONS_DIR.glob("*") if p.is_dir() and (p / "status.yaml").exists() and load_yaml(p / "status.yaml").get("stage") == "ready_for_human_review"], reverse=True)
    prior = st.selectbox("Revise a completed application (optional)", [None] + history, format_func=lambda p: "New application" if p is None else p.name)
    analyze = st.form_submit_button("Analyze Job")
    generate = st.form_submit_button("Generate Application", type="primary")
if analyze or generate:
    if not description.strip():
        st.error("Paste a job description first.")
    else:
        try:
            with st.status("Preparing your application…", expanded=True) as status:
                folder = generate_application(description, company, role, url, language, length, notes, revision_of=prior, analyze_only=analyze, progress=st.write)
                status.update(label="Analysis ready" if analyze else "Ready for your review", state="complete")
            st.session_state["application_folder"] = str(folder)
        except Exception as exc:
            st.error(str(exc))
selected = st.session_state.get("application_folder")
if selected:
    folder = Path(selected)
    st.caption(f"Saved in {folder}")
    analysis = load_yaml(folder / "job_analysis.yaml")
    st.write(analysis["strategy"])
    st.dataframe([{k: item[k] for k in ("requirement", "importance", "match", "rationale")} for item in analysis["requirements"]], use_container_width=True)
    if analysis["gaps"]:
        st.warning("Evidence gaps: " + "; ".join(analysis["gaps"]))
    if load_yaml(folder / "status.yaml").get("stage") == "ready_for_human_review":
        for label, name in (("Download CV", "CV.pdf"), ("Download cover letter", "Cover_Letter.pdf")):
            st.download_button(label, (folder / name).read_bytes(), file_name=name, mime="application/pdf")
        st.markdown((folder / "change_summary.md").read_text())
        with st.expander("Claim-by-claim factual audit"):
            st.markdown((folder / "audit.md").read_text())
