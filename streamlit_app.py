"""
Streamlit Frontend — Futuristic Glassmorphism Dashboard
Job discovery, LLM matching, and one-click auto-apply.
"""

import os
import time
import json
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

API_BASE = os.getenv("API_URL", "http://localhost:8000")
API_PREFIX = "/api"

st.set_page_config(
    page_title="Job Automation",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Clean Dark Theme (no glassmorphism) ──────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    color-scheme: dark;
    font-family: 'Inter', sans-serif !important;
    background: #08112a !important;
    color: #e6efff !important;
}

html, body, .main, .block-container, [data-testid="stAppViewContainer"], [data-testid="stAppViewBlockContainer"] {
    background: #08112a !important;
    color: #e6efff !important;
}

section[data-testid="stSidebar"] {
    background: #071025 !important;
    color: #e6efff !important;
    border-right: 1px solid #112f6e !important;
    width: 280px !important;
    min-width: 280px !important;
    max-width: 280px !important;
    transform: translateX(0) !important;
    left: 0 !important;
}

section[data-testid="stSidebar"] .stRadio label {
    color: #c9d9f8 !important;
    border-radius: 10px !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background: #0f1f59 !important;
    color: #ffffff !important;
}
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label[data-checked="true"] {
    background: #122d6f !important;
    color: #ffffff !important;
    border-color: #1f4f94 !important;
}

[data-testid="stToolbar"] {
    display: none !important;
}

button[data-testid="stBaseButton-headerNoPadding"], button[data-testid="baseButton-header"] {
    visibility: visible !important;
    opacity: 1 !important;
    display: inline-flex !important;
    font-size: 0.9rem !important;
    min-width: 2.4rem !important;
    width: auto !important;
    padding: 0.3rem 0.55rem !important;
    overflow: visible !important;
    background: transparent !important;
    border: none !important;
    color: #e6efff !important;
}
button[data-testid="stBaseButton-headerNoPadding"] svg,
button[data-testid="baseButton-header"] svg {
    width: 1.2rem !important;
    height: 1.2rem !important;
    fill: #e6efff !important;
}

.stButton button {
    background: #112869 !important;
    border: 1px solid #1f4d95 !important;
    color: #f5faff !important;
    border-radius: 12px !important;
}
.stButton button:hover {
    background: #17438f !important;
    border-color: #2d6be0 !important;
}

input, textarea, select, div[data-baseweb="select"] > div, .stTextInput>div>div>input, .stNumberInput>div>div>input, .stTextArea>div>div>textarea {
    background: #0e1d4b !important;
    border: 1px solid #1f4490 !important;
    color: #eef3ff !important;
    border-radius: 10px !important;
}
input::placeholder, textarea::placeholder {
    color: #9eb0d4 !important;
}

input[type="range"] {
    -webkit-appearance: none !important;
    appearance: none !important;
    width: 100% !important;
    height: 10px !important;
    background: #1c3170 !important;
    border-radius: 999px !important;
    outline: none !important;
}
input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none !important;
    appearance: none !important;
    width: 18px !important;
    height: 18px !important;
    border-radius: 50% !important;
    background: #00f471 !important;
    border: 2px solid #ffffff !important;
    box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.25) !important;
    cursor: pointer !important;
}
input[type="range"]::-moz-range-thumb {
    width: 18px !important;
    height: 18px !important;
    border-radius: 50% !important;
    background: #00f471 !important;
    border: 2px solid #ffffff !important;
    box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.25) !important;
    cursor: pointer !important;
}
input[type="range"]::-ms-thumb {
    width: 18px !important;
    height: 18px !important;
    border-radius: 50% !important;
    background: #00f471 !important;
    border: 2px solid #ffffff !important;
    cursor: pointer !important;
}
input[type="range"]::-webkit-slider-runnable-track {
    height: 10px !important;
    border-radius: 999px !important;
    background: #1c3170 !important;
}
input[type="range"]::-moz-range-track {
    height: 10px !important;
    border-radius: 999px !important;
    background: #1c3170 !important;
}
input[type="range"]::-ms-track {
    height: 10px !important;
    border-radius: 999px !important;
    background: transparent !important;
    color: transparent !important;
}

div[data-testid="metric-container"], .stMetric {
    background: #101f43 !important;
    border: 1px solid #1f4d92 !important;
    border-radius: 14px !important;
}

.streamlit-expanderHeader {
    background: #111f4f !important;
    border: 1px solid #1f4a95 !important;
    color: #eef3ff !important;
}
.streamlit-expanderContent {
    background: #081229 !important;
    border: 1px solid #1f4a95 !important;
}

div[data-testid="stDataFrame"] {
    background: transparent !important;
}
div[data-testid="stDataFrame"] td, div[data-testid="stDataFrame"] th {
    color: #e7f0ff !important;
    border-color: #1a2c5f !important;
}

.stAlert, .stWarning, .stError, .stInfo, .stSuccess {
    background: #0d193f !important;
    border: 1px solid #1f4d90 !important;
    color: #eef3ff !important;
}

h1,h2,h3,h4,h5,h6 {
    color: #f4f9ff !important;
}

p, span, label, div, li, a {
    color: #d8e4ff !important;
}

.status-badge {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0.2rem 0.65rem !important;
    border-radius: 999px !important;
    font-size: 0.75rem !important;
    font-weight: 700 !important;
}

.score-high { color: #00f471 !important; }
.score-mid { color: #f7b744 !important; }
.score-low { color: #ff707f !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #08112a; }
::-webkit-scrollbar-thumb { background: #1c3678; border-radius: 999px; }
</style>
""", unsafe_allow_html=True)


# ── API Helpers ───────────────────────────────────────────────────────────────

def api_get(path):
    try:
        r = requests.get(f"{API_BASE}{API_PREFIX}{path}", timeout=10)
        r.raise_for_status(); return r.json()
    except Exception as e:
        st.error(f"⚠️ {e}")
        return {}

def api_post(path, data=None, files=None):
    try:
        to = 120 if path in ("/jobs/search", "/jobs/match", "/applications/apply") else 30
        if files:
            prepared_files = {}
            for key, value in (files or {}).items():
                if hasattr(value, "read") and hasattr(value, "name"):
                    prepared_files[key] = (value.name, value, getattr(value, "type", "application/octet-stream"))
                else:
                    prepared_files[key] = value
            r = requests.post(f"{API_BASE}{API_PREFIX}{path}", files=prepared_files, timeout=to)
        else:
            r = requests.post(f"{API_BASE}{API_PREFIX}{path}", json=data, timeout=to)
        r.raise_for_status(); return r.json()
    except Exception as e:
        st.error(f"⚠️ {e}")
        return {}

def api_patch(path, data):
    try:
        r = requests.patch(f"{API_BASE}{API_PREFIX}{path}", json=data, timeout=10)
        r.raise_for_status(); return r.json()
    except Exception:
        return {}

def api_delete(path):
    try:
        r = requests.delete(f"{API_BASE}{API_PREFIX}{path}", timeout=10)
        r.raise_for_status(); return r.json()
    except Exception:
        return {}

def health():
    try:
        return requests.get(f"{API_BASE}/health", timeout=3).ok
    except:
        return False

# ── Session State ─────────────────────────────────────────────────────────────

def init_state():
    for k, v in {
        "page": "🚀 Dashboard",
        "resume_id": None, "resume": None,
        "jobs": [], "matched": [], "applications": [],
        "apply_queue": [], "applying_all": False,
        "category": "All", "salary_min": 0, "salary_max": 500,
    }.items():
        st.session_state.setdefault(k, v)

init_state()
backend_ok = health()
st.session_state.backend_ok = backend_ok

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:1rem 0">
        <span style="font-size:2.5rem">🤖</span>
        <h2 style="margin:0;background:linear-gradient(135deg,#00f260,#0575e6);-webkit-background-clip:text;-webkit-text-fill-color:transparent">Job Bot</h2>
        <p style="color:rgba(255,255,255,0.4);font-size:0.8rem;margin:0">DeepSeek-R1 Powered</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:1rem">
        <span style="width:8px;height:8px;border-radius:50%;background:{"#00f260" if backend_ok else "#ff416c"}"></span>
        <span style="color:rgba(255,255,255,0.5);font-size:0.8rem">{"Backend Online" if backend_ok else "Backend Offline"}</span>
    </div>
    """, unsafe_allow_html=True)

    items = ["🚀 Dashboard", "📋 Resume", "🔍 Search", "✅ Applications", "⚙️ Settings"]
    sel = st.radio("Navigate", items, label_visibility="collapsed", index=items.index(st.session_state.page) if st.session_state.page in items else 0)
    st.session_state.page = sel

    if not backend_ok:
        st.code("uvicorn app:app --reload", language="bash")

# ── Job Categorization ────────────────────────────────────────────────────────

JOB_CATEGORY_RULES = {
    "Product-Based": ["product", "saas", "platform", "app", "software engineer", "sde", "full-stack", "frontend", "backend"],
    "Service-Based": ["consultant", "service", "solutions engineer", "support", "tcs", "infosys", "wipro", "accenture", "cognizant", "tech mahindra", "hcl", "capgemini"],
    "Startups": ["startup", "seed", "series", "early-stage", "venture", "founder", "stealth"],
}

def categorize_job(title: str, company: str, desc: str) -> str:
    t = f"{title} {company} {desc}".lower()
    cats = []
    if any(k in t for k in JOB_CATEGORY_RULES["Product-Based"]):
        cats.append("Product-Based")
    if any(k in t for k in JOB_CATEGORY_RULES["Service-Based"]):
        cats.append("Service-Based")
    if any(k in t for k in JOB_CATEGORY_RULES["Startups"]):
        cats.append("Startups")
    return cats[0] if cats else "General"

def format_date(d):
    if not d: return "—"
    try: return datetime.fromisoformat(d.replace("Z","+00:00")).strftime("%d %b %Y")
    except: return str(d)[:10]

def status_badge(s):
    cls = s.lower().replace(" ", "-")
    return f'<span class="status-badge status-{cls}">{s}</span>'

# ── Page: Dashboard ───────────────────────────────────────────────────────────

def page_dashboard():
    st.markdown('<h1 style="font-size:2.2rem">🚀 Dashboard</h1>', unsafe_allow_html=True)

    if not backend_ok:
        st.warning("Backend offline — start with `uvicorn app:app --reload`")
        return

    jobs_data = api_get("/jobs/?limit=100")
    apps_data = api_get("/applications/")
    resumes_data = api_get("/resume/")

    all_jobs = jobs_data.get("jobs", [])
    all_apps = apps_data.get("applications", [])
    total_resumes = resumes_data.get("total", 0)

    submitted = [a for a in all_apps if a["status"] in ("submitted", "interview", "offer")]
    pending = [a for a in all_apps if a["status"] in ("applying", "matched", "discovered")]

    # Metrics row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📄 Resumes", total_resumes)
    c2.metric("💼 Jobs Found", len(all_jobs))
    c3.metric("📨 Submitted", len(submitted))
    c4.metric("⏳ Pending", len(pending))
    c5.metric("🎯 Interviews", len([a for a in all_apps if a["status"] == "interview"]))

    st.markdown("")

    # Apply-to-all bar
    if st.session_state.matched:
        col_apply, col_status = st.columns([1, 3])
        with col_apply:
            if st.button("⚡ Apply to All Matched", type="secondary", use_container_width=True):
                st.session_state.apply_queue = list(st.session_state.matched)
                st.session_state.applying_all = True
                st.rerun()

        with col_status:
            if st.session_state.applying_all:
                q = st.session_state.apply_queue
                total = len(st.session_state.matched)
                done = total - len(q)
                st.progress(done / max(total, 1), text=f"Applying {done}/{total}...")

    st.markdown("")

    # ── Application Timeline ──────────────────────────────────────────────
    st.markdown('<div><h3>📅 Application Timeline</h3>', unsafe_allow_html=True)

    if all_apps:
        rows = []
        for a in sorted(all_apps, key=lambda x: x.get("created_at", ""), reverse=True):
            rows.append({
                "Date": format_date(a.get("applied_at") or a.get("created_at")),
                "Company": a.get("company", "—"),
                "Role": a.get("job_title", "—"),
                "Status": a.get("status", "unknown"),
                "ID": a["id"][:8],
            })
        df = pd.DataFrame(rows)
        # Style the status column
        def style_status(v):
            cls = v.lower().replace(" ", "-")
            return f'<span class="status-badge status-{cls}">{v}</span>'
        df["Status"] = df["Status"].apply(style_status)
        st.write(df.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.info("No applications yet. Upload a resume and search for jobs!")
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Category Breakdown ─────────────────────────────────────────────────
    st.markdown('<div><h3>📊 Category Breakdown</h3>', unsafe_allow_html=True)
    cats = {"Product-Based": 0, "Service-Based": 0, "Startups": 0, "General": 0}
    for j in all_jobs:
        c = categorize_job(j.get("title",""), j.get("company",""), "")
        cats[c] = cats.get(c, 0) + 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🖥️ Product", cats["Product-Based"])
    c2.metric("🏢 Service", cats["Service-Based"])
    c3.metric("🚀 Startups", cats["Startups"])
    c4.metric("📋 General", cats["General"])
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Quick Apply: Top Jobs ──────────────────────────────────────────────
    if st.session_state.matched:
        st.markdown('<div><h3>🏆 Top Matched Jobs — Quick Apply</h3>', unsafe_allow_html=True)

        category_filter = st.segmented_control(
            "Filter", ["All", "Product-Based", "Service-Based", "Startups", "General"],
            default=st.session_state.category, key="dash_cat",
            on_change=lambda: st.session_state.__setitem__("category", st.session_state.dash_cat),
        )
        st.session_state.category = category_filter

        col_sal1, col_sal2 = st.columns(2)
        with col_sal1:
            sal_min = st.slider("Min Salary (k)", 0, 300, st.session_state.salary_min, key="ds_min",
                                on_change=lambda: st.session_state.__setitem__("salary_min", st.session_state.ds_min))
        with col_sal2:
            sal_max = st.slider("Max Salary (k)", 0, 500, st.session_state.salary_max, key="ds_max",
                                on_change=lambda: st.session_state.__setitem__("salary_max", st.session_state.ds_max))

        filtered = []
        for m in st.session_state.matched:
            job = m.get("job", {})
            cat = categorize_job(job.get("title",""), job.get("company",""), "")
            if category_filter != "All" and cat != category_filter:
                continue
            s_min = job.get("salary_min") or 0
            s_max = job.get("salary_max") or 500
            if s_max < sal_min or s_min > sal_max:
                continue
            filtered.append(m)

        for idx, m in enumerate(filtered[:20]):
            job = m.get("job", {})
            score = m.get("score", 0)
            title = job.get("title", "Unknown")
            company = job.get("company", "Unknown")
            loc = job.get("location", "")
            url = job.get("url", "")
            reasoning = m.get("reasoning", "")
            key_matches = m.get("key_matches", [])
            s_min = job.get("salary_min")
            s_max = job.get("salary_max")
            salary_str = f"${s_min}k–${s_max}k" if s_min and s_max else "Not listed"
            cat = categorize_job(title, company, "")

            cls = "score-high" if score >= 80 else "score-mid" if score >= 60 else "score-low"

            st.markdown(f"""
            <div class="glass-job">
                <div style="display:flex;justify-content:space-between;align-items:flex-start">
                    <div style="flex:1">
                        <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.3rem">
                            <strong style="color:#fff;font-size:1.05rem">{title}</strong>
                            <span style="color:rgba(255,255,255,0.4)">@</span>
                            <span style="color:rgba(255,255,255,0.8)">{company}</span>
                            <span style="background:rgba(255,255,255,0.05);padding:0.1rem 0.5rem;border-radius:50px;font-size:0.7rem;color:rgba(255,255,255,0.4)">{cat}</span>
                        </div>
                        <div style="display:flex;gap:1rem;font-size:0.85rem;color:rgba(255,255,255,0.5)">
                            <span>📍 {loc}</span>
                            <span>💰 {salary_str}</span>
                            <span>🔗 {url.split("/")[2] if url else "—"}</span>
                        </div>
                        <div style="margin-top:0.4rem;font-size:0.8rem;color:rgba(255,255,255,0.4)">
                            {reasoning[:120]}...
                        </div>
                        <div style="margin-top:0.3rem;display:flex;gap:0.4rem;flex-wrap:wrap">
                            {''.join(f'<span style="background:rgba(0,242,96,0.08);color:#00f260;padding:0.1rem 0.5rem;border-radius:50px;font-size:0.7rem">{km}</span>' for km in key_matches[:3])}
                        </div>
                    </div>
                    <div style="text-align:right;min-width:100px">
                        <div class="{cls}">{score}/100</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Apply button inline
            col_a, col_b, col_c = st.columns([2, 2, 6])
            job_id_from_url = url.split("/")[-1] if url else ""
            with col_a:
                if st.button(f"⚡ Apply", key=f"dash_apply_{idx}"):
                    with st.spinner(f"Applying to {title}..."):
                        r = api_post("/applications/apply", {
                            "job_id": "",
                            "resume_id": st.session_state.resume_id,
                            "cover_letter": None,
                        })
                    if r.get("status") == "applying":
                        st.toast(f"✅ Applying to {title}!", icon="✅")
                    else:
                        st.toast(f"⚠️ Could not apply — no resume uploaded?", icon="⚠️")
            with col_b:
                if st.button(f"📄 Tailor", key=f"dash_tailor_{idx}"):
                    with st.spinner("Generating tailored resume..."):
                        tr = api_post("/resume/tailor", {"resume_id": st.session_state.resume_id, "job_id": ""})
                    if tr.get("tailored_resume"):
                        st.toast("✅ Tailored resume generated!", icon="✅")

        if not filtered:
            st.info("No jobs match the current filters.")
        st.markdown("</div>", unsafe_allow_html=True)


# ── Page: Resume ──────────────────────────────────────────────────────────────

def page_resume():
    st.markdown('<h1>📋 Resume</h1>', unsafe_allow_html=True)
    if not backend_ok: return

    data = api_get("/resume/")
    resumes = data.get("resumes", [])

    if not resumes:
        st.markdown("### Upload Your Resume")
        uploaded = st.file_uploader("PDF or DOCX", type=["pdf", "docx"], label_visibility="collapsed")
        if uploaded:
            with st.spinner("Uploading & parsing..."):
                r = api_post("/resume/upload", files={"file": uploaded})
            if r.get("id"):
                st.session_state.resume_id = r["id"]
                st.session_state.resume = r
                st.success(f"✅ Uploaded!")
                st.rerun()
    else:
        ids = [r["id"] for r in resumes]
        sel = st.selectbox("Select resume", ids, format_func=lambda x: next((r["filename"] for r in resumes if r["id"]==x), x))
        st.session_state.resume_id = sel
        detail = api_get(f"/resume/{sel}")
        st.session_state.resume = detail

        c1, c2 = st.columns(2)
        if c1.button("📥 Upload New"): st.session_state.resume_id = None; st.session_state.resume = None; st.rerun()
        if c2.button("🗑️ Delete"): api_delete(f"/resume/{sel}"); st.session_state.resume_id = None; st.session_state.resume = None; st.rerun()

        content = detail.get("content") or detail.get("content_preview") or ""
        if content:
            with st.expander("📄 Preview", expanded=True):
                st.text_area("", content, height=300, label_visibility="collapsed")
        else:
            st.info("Resume uploaded, but no preview text could be extracted from this file.")
    st.markdown("</div>", unsafe_allow_html=True)


# ── Page: Search ──────────────────────────────────────────────────────────────

def page_search():
    st.markdown('<h1>🔍 Search Jobs</h1>', unsafe_allow_html=True)
    if not backend_ok: return
    if not st.session_state.resume_id:
        st.warning("Upload a resume first.")
        return

    c1, c2 = st.columns(2)
    with c1:
        kw = st.text_input("Keywords (comma-separated)", "Senior Engineer, Python")
    with c2:
        loc = st.text_input("Location", "Remote")

    c1, c2, c3 = st.columns(3)
    indeed = c1.checkbox("Indeed", True)
    linkedin = c2.checkbox("LinkedIn", False)
    limit = c3.number_input("Max", 5, 50, 20)
    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("🔍 Search", use_container_width=True):
        kws = [k.strip() for k in kw.split(",") if k.strip()]
        if not kws: return st.error("Enter keywords")
        sources = []
        if indeed: sources.append("indeed")
        if linkedin: sources.append("linkedin")

        with st.spinner("Crawling job boards..."):
            r = api_post("/jobs/search", {"keywords": kws, "location": loc, "limit": limit, "sources": sources})
        st.session_state.jobs = r.get("jobs", [])
        st.success(f"Found {r.get('jobs_found',0)} jobs ({r.get('jobs_saved',0)} new)")

        for j in st.session_state.jobs:
            with st.expander(f"{j['title']} @ {j['company']}"):
                st.write(f"📍 {j['location']}  |  📰 {j['source']}")
                if j.get("salary_min"): st.write(f"💰 ${j['salary_min']}k–${j['salary_max']}k")
                st.markdown(f"[View]({j['url']})")

    if st.session_state.jobs and st.button("📊 Match with AI", use_container_width=True):
        with st.spinner("DeepSeek-R1 scoring jobs..."):
            r = api_post("/jobs/match", {"resume_id": st.session_state.resume_id, "limit": limit})
        st.session_state.matched = r.get("matches", [])
        st.success(f"{len(st.session_state.matched)} jobs scored!")
        st.session_state.page = "🚀 Dashboard"
        st.rerun()


# ── Page: Applications ────────────────────────────────────────────────────────

def page_apps():
    st.markdown('<h1>✅ Applications</h1>', unsafe_allow_html=True)
    if not backend_ok: return

    data = api_get("/applications/")
    apps = data.get("applications", [])
    st.session_state.applications = apps

    c1, c2 = st.columns(2)
    statuses = ["All"] + sorted(set(a.get("status","") for a in apps))
    sf = c1.selectbox("Status", statuses)
    cf = c2.text_input("Company")
    st.markdown("</div>", unsafe_allow_html=True)

    filtered = apps
    if sf != "All": filtered = [a for a in filtered if a["status"]==sf]
    if cf: filtered = [a for a in filtered if cf.lower() in (a.get("company") or "").lower()]

    if not filtered:
        st.info("No applications yet.")
        return

    for a in filtered:
        s = a.get("status","unknown")
        emoji = {"submitted":"📨","interview":"🎯","offer":"🎉","rejected":"❌","failed":"⚠️","applying":"⏳"}.get(s,"📋")
        st.markdown(f"""
        <div class="glass-job">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <strong style="color:#fff">{emoji} {a.get('job_title','Unknown')}</strong>
                    <span style="color:rgba(255,255,255,0.5)"> @ {a.get('company','Unknown')}</span>
                </div>
                <div style="text-align:right">
                    {status_badge(s)}
                    <div style="font-size:0.75rem;color:rgba(255,255,255,0.3);margin-top:0.2rem">{format_date(a.get('applied_at') or a.get('created_at'))}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("Update status"):
            col1, col2 = st.columns(2)
            ns = col1.selectbox("New status", ["submitted","under_review","interview","offer","rejected"], key=f"ns_{a['id']}")
            if col2.button("Save", key=f"sv_{a['id']}"):
                api_patch(f"/applications/{a['id']}", {"status": ns})
                st.rerun()


# ── Page: Settings ────────────────────────────────────────────────────────────

def page_settings():
    st.markdown('<h1>⚙️ Settings</h1>', unsafe_allow_html=True)
    st.markdown("### 🔗 Backend")
    st.code(f"{API_BASE}")
    st.markdown("🟢 Connected" if backend_ok else "🔴 Offline")
    st.markdown("---")

    # Read LLM provider from backend health/config
    try:
        cfg = requests.get(f"{API_BASE}/health", timeout=5).json()
    except Exception:
        cfg = {}
    provider = cfg.get("llm_provider", "ollama")
    model = cfg.get("llm_model", "deepseek-r1:8b")
    st.markdown(f"### 🧠 LLM — {model}")
    st.write(f"**Provider:** {provider.upper()}")
    if provider == "groq":
        st.code("https://console.groq.com")
    else:
        st.code("ollama list")
    st.markdown("---")
    st.markdown("### ⚙️ Preferences")
    c1, c2 = st.columns(2)
    c1.slider("Max applications/day", 1, 50, 10)
    c2.slider("Min match score", 0, 100, 60)
    st.markdown("</div>", unsafe_allow_html=True)


# ── Routing ───────────────────────────────────────────────────────────────────

pages = {
    "🚀 Dashboard": page_dashboard,
    "📋 Resume": page_resume,
    "🔍 Search": page_search,
    "✅ Applications": page_apps,
    "⚙️ Settings": page_settings,
}

pages.get(st.session_state.page, lambda: None)()

st.markdown("""
<div style="text-align:center;padding:1rem;color:rgba(255,255,255,0.2);font-size:0.75rem">
    Job Automation Bot • DeepSeek-R1 • Glass UI
</div>
""", unsafe_allow_html=True)
