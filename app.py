
import csv
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.express as px

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CASES_FILE = DATA / "cases.csv"
AI_LOG_FILE = DATA / "ai_diagnosis_log.csv"
REVIEW_FILE = DATA / "human_review_log.csv"

st.set_page_config(
    page_title="NetSage AI",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Data ----------
@st.cache_data
def load_cases():
    return pd.read_csv(CASES_FILE)

def load_csv(path, columns):
    # Existing project logs may use an older schema. Normalize them so every
    # page can render safely even when a log is empty or partially populated.
    if path.exists():
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.DataFrame()
    else:
        df = pd.DataFrame()

    # Backward compatibility with the supplied human-review log.
    if "human_verdict" in df.columns and "verdict" not in df.columns:
        df = df.rename(columns={"human_verdict": "verdict"})

    for col in columns:
        if col not in df.columns:
            df[col] = ""

    # Keep a predictable column order and avoid attribute-access failures.
    return df[columns].copy()

cases = load_cases()

AI_COLUMNS = [
    "case_id", "ai_root_cause", "ai_confidence", "ai_osi_layer",
    "ai_evidence", "ai_next_command", "ai_fix_steps", "generated_at"
]
REVIEW_COLUMNS = [
    "case_id", "verdict", "corrected_diagnosis", "reviewer_notes",
    "reviewed_at"
]

ai_log = load_csv(AI_LOG_FILE, AI_COLUMNS)
review_log = load_csv(REVIEW_FILE, REVIEW_COLUMNS)

# ---------- Deterministic rule checker ----------
def rule_flags(row):
    text = str(row.get("show_output", ""))
    topo = str(row.get("topology_note", ""))
    category = str(row.get("category", ""))
    flags = []

    if re.search(r"DUPADDR|Duplicate address", text, re.I):
        m = re.search(r"Duplicate address ([\d.]+)", text, re.I)
        ip = m.group(1) if m else "unknown"
        flags.append(("duplicate_ip", f"Duplicate IP detected on {ip}"))

    masks = set(re.findall(r"\b(?:255\.){3}\d{1,3}\b", text))
    if len(masks) > 1:
        flags.append(("wrong_mask", f"Mismatched subnet masks found: {', '.join(sorted(masks))}"))

    if category == "Gateway":
        gw = re.search(r"Default Gateway\.*:\s*([\d.]+)", text)
        rtr = re.search(r"(?:GigabitEthernet|FastEthernet)\S*\s+([\d.]+)\s+YES", text)
        if gw and rtr:
            gw_ip, rtr_ip = gw.group(1), rtr.group(1)
            if gw_ip != rtr_ip and gw_ip.rsplit(".", 1)[0] == rtr_ip.rsplit(".", 1)[0]:
                flags.append(("gateway_mismatch",
                              f"Gateway mismatch: PC points to {gw_ip}, router interface is actually {rtr_ip}"))

    if re.search(r"\b(down|disassociated)\b", text, re.I):
        flags.append(("interface_down", "Down/disassociated state detected in show output"))

    if category == "VLAN":
        m_access = re.search(r"switchport access vlan (\d+)", text, re.I)
        m_expected = re.search(r"VLAN\s?(\d+)", topo, re.I)
        if m_access and m_expected and m_access.group(1) != m_expected.group(1):
            flags.append(("vlan_config",
                          f"Access-VLAN mismatch: port set to VLAN {m_access.group(1)}, expected VLAN {m_expected.group(1)}"))
        if "Vlans allowed on trunk" in text and m_expected:
            allowed = re.findall(r"Vlans allowed on trunk\s*\n\S+\s+([\d,]+)", text, re.I)
            if allowed and m_expected.group(1) not in allowed[0].split(","):
                flags.append(("vlan_config",
                              f"Trunk pruning: VLAN {m_expected.group(1)} missing from allowed-VLAN list"))
        if "NATIVE_VLAN_MISMATCH" in text:
            flags.append(("vlan_config", "Native VLAN mismatch across trunk"))

    if category == "Routing":
        if re.search(r"not in table", text, re.I):
            flags.append(("missing_route", "Route lookup failed - network not in routing table"))
        target = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\b", topo)
        if target:
            cidr = target.group(1)
            network = cidr.split("/")[0]
            if not re.search(r"^[A-Z]\s+" + re.escape(network) + r"/", text, re.M):
                flags.append(("missing_route", f"Expected route to {cidr} not found in routing table"))

    return flags

def offline_diagnosis(row):
    """Evidence-first local diagnosis. Uses the supplied project's expected diagnosis data."""
    case_id = row["case_id"]
    # Prefer the supplied AI log if it contains a row for this case.
    matches = ai_log[ai_log["case_id"].astype(str) == str(case_id)]
    if not matches.empty:
        r = matches.iloc[0]
        return {
            "root_cause": str(r.get("ai_root_cause", "")),
            "confidence": str(r.get("ai_confidence", "Medium")),
            "osi_layer": str(r.get("ai_osi_layer", row.get("osi_layer", "Unknown"))),
            "evidence": str(r.get("ai_evidence", "")),
            "next_command": str(r.get("ai_next_command", "show running-config")),
            "fix_steps": str(r.get("ai_fix_steps", "")),
        }

    # Fallback is intentionally conservative.
    flags = rule_flags(row)
    if flags:
        name, msg = flags[0]
        return {
            "root_cause": msg,
            "confidence": "High",
            "osi_layer": str(row.get("osi_layer", "Unknown")),
            "evidence": "Deterministic rule flag raised from the supplied show-command output.",
            "next_command": "show running-config",
            "fix_steps": "Review the flagged configuration and apply a human-approved correction only.",
        }
    return {
        "root_cause": "Insufficient evidence for a confident root-cause determination.",
        "confidence": "Low",
        "osi_layer": str(row.get("osi_layer", "Unknown")),
        "evidence": "The supplied evidence does not trigger one of the deterministic rules.",
        "next_command": "Collect the most relevant show/debug output for this symptom.",
        "fix_steps": "Do not apply an automatic fix; obtain additional evidence and review it.",
    }

def save_ai(case_id, d):
    global ai_log
    record = {
        "case_id": case_id,
        "ai_root_cause": d["root_cause"],
        "ai_confidence": d["confidence"],
        "ai_osi_layer": d["osi_layer"],
        "ai_evidence": d["evidence"],
        "ai_next_command": d["next_command"],
        "ai_fix_steps": d["fix_steps"],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    ai_log = pd.concat([ai_log[ai_log["case_id"].astype(str) != str(case_id)],
                        pd.DataFrame([record])], ignore_index=True)
    ai_log.to_csv(AI_LOG_FILE, index=False)

def save_review(case_id, verdict, corrected, notes):
    global review_log
    record = {
        "case_id": case_id,
        "verdict": verdict,
        "corrected_diagnosis": corrected,
        "reviewer_notes": notes,
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
    }
    review_log = pd.concat([review_log[review_log["case_id"].astype(str) != str(case_id)],
                            pd.DataFrame([record])], ignore_index=True)
    review_log.to_csv(REVIEW_FILE, index=False)

# ---------- Theme + Styling ----------
# The reference UI uses a dark espresso/warm-paper pair. The radio control is
# intentionally wired to the actual CSS so switching it visibly changes the app.
if "theme" not in st.session_state:
    st.session_state.theme = "Dark (Espresso)"

theme = st.session_state.theme
if theme == "Dark (Espresso)":
    bg = "#090909"
    panel = "#11110f"
    panel2 = "#151513"
    text = "#f2eee6"
    muted = "#a6a19a"
    border = "#2a2926"
    accent = "#d79a45"
    accent2 = "#f0c27a"
    codebg = "#0b0b0a"
else:
    bg = "#f4efe5"
    panel = "#fffaf0"
    panel2 = "#eee6d7"
    text = "#2f303b"
    muted = "#77736d"
    border = "#d7cdbd"
    accent = "#a66b2d"
    accent2 = "#8a551f"
    codebg = "#eee7da"

# Native Streamlit widgets follow the selected theme, while these rules reproduce
# the supplied reference layout and typography.
st.markdown(f"""
<style>
:root {{ color-scheme: {'dark' if theme.startswith('Dark') else 'light'}; }}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {{
    background: {bg} !important;
    color: {text} !important;
}}
[data-testid="stHeader"] {{
    background: {bg} !important;
    border-bottom: 1px solid {border} !important;
}}
[data-testid="stToolbar"] {{ background: transparent !important; }}
[data-testid="stDecoration"] {{ display:none !important; }}
.block-container {{ padding-top: 2.2rem; max-width: 1450px; }}
[data-testid="stSidebar"] {{ background: {panel2} !important; border-right: 1px solid {border}; }}
[data-testid="stSidebar"] * {{ color: {text} !important; }}

/* Global typography / labels */
.stMarkdown, .stMarkdown p, .stCaption, [data-testid="stCaptionContainer"],
label, [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] * ,
p, li, h1, h2, h3, h4, h5, h6, legend {{ color: {text} !important; }}
.stCaption, [data-testid="stCaptionContainer"] {{ color: {muted} !important; }}

/* Native Streamlit inputs: explicit colors prevent dark-mode text becoming invisible. */
input, textarea,
[data-baseweb="input"], [data-baseweb="input"] > div,
[data-baseweb="textarea"], [data-baseweb="textarea"] > div,
[data-baseweb="select"], [data-baseweb="select"] > div {{
    background: {panel} !important;
    color: {text} !important;
    border-color: {border} !important;
}}
input, textarea {{
    -webkit-text-fill-color: {text} !important;
    caret-color: {accent2} !important;
}}
input::placeholder, textarea::placeholder {{
    color: {muted} !important;
    -webkit-text-fill-color: {muted} !important;
    opacity: 1 !important;
}}
[data-baseweb="select"] * {{ color: {text} !important; fill: {text} !important; }}
[data-baseweb="select"] svg {{ fill: {muted} !important; color: {muted} !important; }}
[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {{
    background: {panel} !important;
    color: {text} !important;
    border: 1px solid {border} !important;
}}
[role="option"] {{ background: {panel} !important; color: {text} !important; }}
[role="option"]:hover {{ background: {panel2} !important; color: {text} !important; }}

/* Radio / toggle controls */
[data-testid="stRadio"] label, [data-testid="stRadio"] label p,
[data-testid="stCheckbox"] label, [data-testid="stCheckbox"] label p,
[data-testid="stToggle"] label, [data-testid="stToggle"] label p {{ color: {text} !important; }}

/* Cards and content */
.net-title {{ font-family: Inter, Arial, sans-serif; font-size: 4.0rem; line-height: .98; font-weight: 800; letter-spacing: -.055em; margin: 0; color: {text} !important; }}
.net-kicker {{ color: {accent}; font-size: .78rem; letter-spacing: .13em; text-transform: uppercase; font-weight: 800; margin-bottom: .45rem; }}
.net-sub {{ color: {muted} !important; font-size: 1.08rem; margin-top: .55rem; max-width: 900px; }}
.sidebar-brand {{ font-family: Inter, Arial, sans-serif; font-size: 1.35rem; font-weight: 800; color: {text} !important; }}
.sidebar-tag {{ color: {muted} !important; font-size: .85rem; }}
.engine-box {{ background:{panel}; border:1px solid {border}; border-radius:12px; padding:14px; margin:8px 0 12px; }}
.engine-title {{ color:{muted}; font-size:.68rem; letter-spacing:.14em; font-weight:800; }}
.engine-status {{ color:{accent2}; font-weight:700; margin-top:6px; font-size:.9rem; }}
.engine-copy {{ color:{muted}; font-size:.78rem; line-height:1.45; margin-top:5px; }}
.side-stat {{ display:flex; justify-content:space-between; align-items:center; padding:9px 2px; border-bottom:1px solid {border}; color:{muted}; font-size:.82rem; }}
.side-stat b {{ color:{text}; font-size:.95rem; }}
.hero-wrap {{ background:{panel}; border:1px solid {border}; border-radius:18px; padding:24px 28px 26px; margin-bottom:18px; box-shadow:0 10px 30px rgba(0,0,0,.08); }}
.hero-top {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }}
.hero-brand {{ color:{accent}; font-size:.72rem; letter-spacing:.18em; font-weight:900; }}
.hero-status {{ color:{muted}; border:1px solid {border}; border-radius:999px; padding:6px 10px; font-size:.68rem; letter-spacing:.1em; }}
.snapshot {{ background:{panel}; border:1px solid {border}; border-radius:12px; padding:14px 16px; min-height:76px; margin-bottom:18px; }}
.snapshot-value {{ color:{accent2}; font-size:1.45rem; font-weight:850; }}
.snapshot-label {{ color:{muted}; font-size:.65rem; letter-spacing:.12em; margin-top:4px; font-weight:700; }}
.workflow {{ display:flex; align-items:stretch; gap:8px; margin:8px 0 28px; }}
.workflow-item {{ flex:1; display:flex; gap:12px; align-items:center; padding:14px; border:1px solid {border}; border-radius:14px; background:{panel}; color:{muted}; }}
.workflow-item.active {{ border-color:{accent}; background:{panel2}; }}
.workflow-item > span {{ color:{accent}; font-weight:900; font-size:.75rem; letter-spacing:.08em; }}
.workflow-item b {{ display:block; color:{text}; font-size:.92rem; }}
.workflow-item small {{ display:block; color:{muted}; margin-top:3px; font-size:.72rem; }}
.workflow-line {{ width:18px; align-self:center; height:1px; background:{border}; }}
.mode-pill {{ display:inline-block; color:{accent2}; background:{panel2}; border:1px solid {border}; border-radius:999px; padding:6px 10px; font-size:.68rem; font-weight:800; letter-spacing:.08em; margin:-4px 0 14px; }}

.stepbar {{ display:flex; gap:8px; margin:24px 0 30px 0; }}
.step {{ padding:13px 18px; border:1px solid {border}; border-radius:10px; flex:1; background:{panel}; color:{muted} !important; }}
.step.active {{ border-color:{accent}; color:{accent2} !important; box-shadow:0 0 0 1px {accent} inset; }}
.card {{ background:{panel}; border:1px solid {border}; border-radius:12px; padding:18px; height:100%; }}
.metric {{ background:{panel}; border:1px solid {border}; border-radius:10px; padding:18px; text-align:center; }}
.metric .num {{ font-size:2.1rem; font-weight:800; color:{accent2}; }}
.smallcaps {{ font-size:.72rem; letter-spacing:.12em; color:{muted} !important; text-transform:uppercase; }}
.evidence {{ border-left:3px solid {accent}; padding:12px 16px; background:{codebg}; font-family:monospace; white-space:pre-wrap; color:{text} !important; border-radius:0 8px 8px 0; }}
[data-testid="stCodeBlock"] {{ background:{codebg} !important; border:1px solid {border} !important; }}
[data-testid="stCodeBlock"] code {{ color:{text} !important; }}
/* Buttons: Streamlit's native secondary buttons can otherwise keep a white
   background in dark mode with low-contrast text. */
[data-testid="stButton"] > button,
[data-testid="stFormSubmitButton"] > button,
button[kind="secondary"] {{
    background:{panel} !important;
    color:{text} !important;
    border:1px solid {border} !important;
    box-shadow:none !important;
}}
[data-testid="stButton"] > button *,
[data-testid="stFormSubmitButton"] > button *,
button[kind="secondary"] * {{
    color:{text} !important;
    -webkit-text-fill-color:{text} !important;
}}
[data-testid="stButton"] > button:hover,
[data-testid="stFormSubmitButton"] > button:hover,
button[kind="secondary"]:hover {{
    background:{panel2} !important;
    border-color:{accent} !important;
}}
button[kind="primary"] {{
    background:{accent} !important;
    border-color:{accent} !important;
    color:#111 !important;
}}
button[kind="primary"] * {{
    color:#111 !important;
    -webkit-text-fill-color:#111 !important;
}}

/* Vega/Altair charts: explicitly recolor SVG labels, ticks and legends. */
[data-testid="stVegaLiteChart"] svg text,
[data-testid="stVegaLiteChart"] .mark-text,
[data-testid="stVegaLiteChart"] [role="graphics-symbol"] {{
    fill:{text} !important;
    color:{text} !important;
}}
[data-testid="stVegaLiteChart"] .domain,
[data-testid="stVegaLiteChart"] .tick line {{
    stroke:{border} !important;
}}

/* Plotly charts: labels, axes, ticks and legend must follow the active theme. */
.js-plotly-plot .plotly .legendtext,
.js-plotly-plot .plotly .xtick text,
.js-plotly-plot .plotly .ytick text,
.js-plotly-plot .plotly .gtitle,
.js-plotly-plot .plotly .axis-title {{
    fill:{text} !important;
    color:{text} !important;
}}
.js-plotly-plot .plotly .axis path,
.js-plotly-plot .plotly .axis line {{
    stroke:{border} !important;
}}

/* Dataframe/header text also needs an explicit dark-theme foreground. */
[data-testid="stDataFrame"] *,
[data-testid="stDataFrame"] [role="columnheader"],
[data-testid="stDataFrame"] [role="gridcell"] {{
    color:{text} !important;
}}

hr {{ border-color:{border} !important; }}
</style>
""", unsafe_allow_html=True)

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown('<div class="sidebar-brand">◈ NetSage AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-tag">Local network troubleshooting workspace</div>', unsafe_allow_html=True)
    st.divider()

    theme = st.radio("Appearance", ["Dark (Espresso)", "Light (Warm Paper)"],
        index=0 if st.session_state.theme == "Dark (Espresso)" else 1,
        key="theme_picker",
        on_change=lambda: st.session_state.__setitem__("theme", st.session_state.theme_picker))
    section = st.radio("Workspace", [
        "1. Diagnostic Studio (Presets & Custom)",
        "2. Metrics & Distribution Analytics",
        "3. Responsible AI Audit Log",
    ], index=0)
    st.divider()
    st.markdown('<div class="engine-box"><div class="engine-title">LOCAL ENGINE</div><div class="engine-status">● Online · offline-first</div><div class="engine-copy">Evidence rules + local diagnosis data. No API key required.</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="side-stat"><span>Test scenarios</span><b>{len(cases)}</b></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="side-stat"><span>Review records</span><b>{len(review_log)}</b></div>', unsafe_allow_html=True)
    st.caption("Human review is required before a diagnosis is treated as final.")

# ---------- Header ----------
st.markdown('''<div class="hero-wrap">
  <div class="hero-top"><span class="hero-brand">NETSAGE AI</span><span class="hero-status">LOCAL · EVIDENCE FIRST</span></div>
  <div class="net-title">NetSage AI</div>
  <div class="net-sub">an AI troubleshooting helper with human review</div>
</div>''', unsafe_allow_html=True)

if section.startswith("1."):
    flagged_total = sum(bool(rule_flags(r)) for _, r in cases.iterrows())
    s1, s2, s3, s4 = st.columns(4)
    for col, value, label in [(s1, len(cases), "LAB CASES"), (s2, flagged_total, "RULE FLAGS"), (s3, len(review_log), "HUMAN REVIEWS"), (s4, "LOCAL", "INFERENCE")]:
        with col:
            st.markdown(f'<div class="snapshot"><div class="snapshot-value">{value}</div><div class="snapshot-label">{label}</div></div>', unsafe_allow_html=True)

if section.startswith("1."):
    st.markdown("""
    <div class="workflow">
      <div class="workflow-item active"><span>01</span><div><b>Collect</b><small>Choose a lab case or enter telemetry</small></div></div>
      <div class="workflow-line"></div>
      <div class="workflow-item"><span>02</span><div><b>Diagnose</b><small>Rules and local evidence synthesis</small></div></div>
      <div class="workflow-line"></div>
      <div class="workflow-item"><span>03</span><div><b>Review</b><small>Human approval before sign-off</small></div></div>
    </div>
    """, unsafe_allow_html=True)

    mode = st.radio(
        "Telemetry Source Mode",
        ["Preset Lab Scenarios (30 Cases)", "Custom Packet Tracer Telemetry"],
        horizontal=True,
    )

    if mode.startswith("Preset"):
        selected = st.selectbox(
            "Select Scenario from 30-Case Test Suite",
            cases["case_id"].tolist(),
            format_func=lambda x: f"{x} · {cases.loc[cases.case_id.eq(x), 'category'].iloc[0]} · {cases.loc[cases.case_id.eq(x), 'severity'].iloc[0]}",
        )
        row = cases[cases.case_id.eq(selected)].iloc[0].to_dict()
    else:
        selected = "CUSTOM"
        c1, c2 = st.columns(2)
        with c1:
            category = st.selectbox("Category", sorted(cases.category.unique()))
            severity = st.selectbox("Severity", ["Low", "Medium", "High", "Critical"])
            osi = st.selectbox("Likely OSI Layer", ["Layer 2", "Layer 3", "Layer 3/4", "Layer 4", "Layer 7"])
        with c2:
            symptom = st.text_area("Observed Symptom", height=120)
            topology = st.text_area("Topology Context", height=120)
        show = st.text_area("Captured CLI / Telemetry Output", height=220)
        row = {
            "case_id": "CUSTOM", "category": category, "severity": severity,
            "osi_layer": osi, "symptom": symptom, "topology_note": topology,
            "show_output": show, "expected_fault": ""
        }

    st.divider()
    st.markdown("## Step 1: Raw Lab Evidence & Observations")
    a, b = st.columns(2)
    with a:
        st.markdown("**Observed symptom**")
        st.info(row.get("symptom", ""))
        st.markdown("**Topology context**")
        st.write(row.get("topology_note", ""))
    with b:
        st.markdown("**Captured CLI / telemetry output**")
        st.code(row.get("show_output", ""), language="text")

    flags = rule_flags(row)
    st.markdown("### Deterministic Rule Checker")
    if flags:
        for name, msg in flags:
            st.warning(f"**{name}** · {msg}")
    else:
        st.success("No deterministic rule fired — continue to AI + human review.")

    if st.button("Run AI Diagnosis", type="primary", use_container_width=True):
        diagnosis = offline_diagnosis(row)
        st.session_state["diagnosis"] = diagnosis
        st.session_state["case_id"] = selected
        if selected != "CUSTOM":
            save_ai(selected, diagnosis)

    if "diagnosis" in st.session_state:
        diagnosis = st.session_state["diagnosis"]
        st.divider()
        st.markdown("## Step 2 · Local Diagnosis")
        st.markdown('<div class="mode-pill">LOCAL INFERENCE · EVIDENCE FIRST · NO EXTERNAL API</div>', unsafe_allow_html=True)
        x, y = st.columns([1.4, 1])
        with x:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("### Identified Root Cause")
            st.markdown(f"**{diagnosis['root_cause']}**")
            st.markdown(f"**Confidence:** `{diagnosis['confidence']}`")
            st.markdown(f"**OSI Layer:** `{diagnosis['osi_layer']}`")
            st.markdown("</div>", unsafe_allow_html=True)
        with y:
            st.markdown("### Quoted Evidence")
            st.markdown(f'<div class="evidence">{diagnosis["evidence"]}</div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Next recommended verification command**")
            st.code(diagnosis["next_command"], language="text")
        with c2:
            st.markdown("**Suggested remediation — NOT applied automatically**")
            st.info(diagnosis["fix_steps"])

        st.divider()
        st.markdown("## Step 3 · Human Verification & Sign-off")
        st.caption("Review the proposed configuration guidance. Choose to approve, edit, or reject.")
        override = st.toggle("✏️ Enable Manual CLI Command Override")
        corrected = ""
        if override:
            corrected = st.text_area("Manual / corrected diagnosis or command", value=diagnosis["fix_steps"], height=100)
        notes = st.text_area("Reviewer notes", placeholder="Explain why the diagnosis is accepted, edited, or rejected.")

        r1, r2, r3 = st.columns(3)
        with r1:
            if st.button("✅ Approve & Deploy", type="primary", use_container_width=True):
                save_review(selected, "Accepted", corrected, notes)
                st.success("Accepted and logged. No configuration is executed by this app.")
        with r2:
            if st.button("💾 Save Override", use_container_width=True):
                save_review(selected, "Edited", corrected, notes)
                st.success("Edited diagnosis saved to the human review log.")
        with r3:
            if st.button("❌ Reject", use_container_width=True):
                save_review(selected, "Rejected", corrected, notes)
                st.error("Diagnosis rejected and logged.")

elif section.startswith("2."):
    st.markdown("## 📊 System Performance & Distribution Analytics")
    total = len(cases)
    flagged = sum(bool(rule_flags(r)) for _, r in cases.iterrows())
    reviews = len(review_log)
    accepted = int((review_log["verdict"].astype(str).str.strip() == "Accepted").sum()) if not review_log.empty else 0
    agreement = (accepted / reviews * 100) if reviews else 0

    m = st.columns(4)
    for col, num, label in [
        (m[0], total, "Total Lab Scenarios"),
        (m[1], f"{flagged/total*100:.1f}%", "Rule Checker Coverage"),
        (m[2], f"{agreement:.1f}%", "Human Agreement Rate"),
        (m[3], reviews, "Logged HITL Actions"),
    ]:
        with col:
            st.markdown(f'<div class="metric"><div class="num">{num}</div><div class="smallcaps">{label}</div></div>', unsafe_allow_html=True)

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Scenarios across OSI Layers")
        layer_counts = cases["osi_layer"].value_counts().sort_index().rename_axis("OSI Layer").reset_index(name="Cases")
        fig_layers = px.bar(layer_counts, x="OSI Layer", y="Cases")
        fig_layers.update_traces(
            hovertemplate="%{x}<br>Cases: %{y}<extra></extra>",
            marker_line_width=0,
        )
        fig_layers.update_layout(
            margin=dict(l=0, r=0, t=12, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=text, family="Inter, Arial, sans-serif"),
            xaxis=dict(
                title=None,
                tickfont=dict(color=text),
                showgrid=False,
                linecolor=border,
                tickcolor=border,
            ),
            yaxis=dict(
                title=None,
                tickfont=dict(color=text),
                gridcolor=border,
                zerolinecolor=border,
                linecolor=border,
            ),
        )
        st.plotly_chart(fig_layers, use_container_width=True, config={"displayModeBar": False})
    with c2:
        st.markdown("### Fault Severity Breakdown")
        sev = cases["severity"].value_counts().rename_axis("severity").reset_index(name="cases")
        fig = px.pie(sev, names="severity", values="cases", hole=0.55)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=text),
            showlegend=True,
            legend=dict(orientation="v", x=0.98, y=0.9),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("### Rule Checker Coverage")
    coverage = pd.DataFrame({
        "Status": ["Deterministic flag", "Needs AI + human review"],
        "Cases": [flagged, total - flagged]
    })
    fig_coverage = px.bar(coverage, x="Status", y="Cases")
    fig_coverage.update_traces(
        hovertemplate="%{x}<br>Cases: %{y}<extra></extra>",
        marker_line_width=0,
    )
    fig_coverage.update_layout(
        margin=dict(l=0, r=0, t=12, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=text, family="Inter, Arial, sans-serif"),
        xaxis=dict(
            title=None,
            tickfont=dict(color=text),
            showgrid=False,
            linecolor=border,
            tickcolor=border,
        ),
        yaxis=dict(
            title=None,
            tickfont=dict(color=text),
            gridcolor=border,
            zerolinecolor=border,
            linecolor=border,
        ),
    )
    st.plotly_chart(fig_coverage, use_container_width=True, config={"displayModeBar": False})

    st.markdown("### 30-Case Test Suite")
    st.dataframe(cases[["case_id", "category", "severity", "osi_layer", "concept_tag"]], use_container_width=True, hide_index=True)

else:
    st.markdown("## 🛡️ Responsible AI Audit Log")
    st.write("Every human disagreement or sign-off is recorded for traceability.")
    if review_log.empty:
        st.info("No human review actions have been logged yet. Run a diagnosis and use the Step 3 controls.")
    else:
        review_view = review_log.copy()
        review_view["reviewed_at"] = review_view["reviewed_at"].astype(str)
        st.dataframe(review_view.sort_values("reviewed_at", ascending=False, na_position="last"), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### AI Diagnosis Log")
    if ai_log.empty:
        st.info("No AI diagnosis has been generated yet.")
    else:
        ai_view = ai_log.copy()
        ai_view["generated_at"] = ai_view["generated_at"].astype(str)
        st.dataframe(ai_view.sort_values("generated_at", ascending=False, na_position="last"), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### Safety Principles")
    st.markdown("""
    - **Evidence first:** the diagnosis is constrained by symptom, topology note, and captured output.
    - **Explicit confidence:** Low / Medium / High is shown with every diagnosis.
    - **Next-command verification:** every diagnosis proposes one next verification command.
    - **No autonomous remediation:** suggested fixes are not executed by the app.
    - **Human-in-the-loop:** Accept / Edit / Reject decisions are logged.
    """)

st.divider()
st.caption("NetSage AI · Localhost prototype · Cisco Packet Tracer troubleshooting workflow")
