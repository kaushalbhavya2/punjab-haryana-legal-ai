import os
import streamlit as st
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

st.set_page_config(
    page_title="PH Legal AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.stApp { background-color: #f4f6f9; }

.app-header {
    background: #1a237e;
    color: white;
    padding: 24px 32px;
    border-radius: 12px;
    margin-bottom: 24px;
}
.app-header h1 { color: white; margin: 0; font-size: 1.6rem; font-weight: 700; }
.app-header p  { color: #c5cae9; margin: 6px 0 0 0; font-size: 0.9rem; }

.case-card {
    background: white;
    border: 1px solid #e3e7ef;
    border-radius: 10px;
    padding: 18px 22px;
    margin-bottom: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    transition: box-shadow 0.15s;
}
.case-card:hover { box-shadow: 0 4px 12px rgba(26,35,126,0.12); border-color: #9fa8da; }
.case-number { font-weight: 700; font-size: 0.95rem; color: #1a237e; }
.case-title  { font-size: 0.85rem; color: #555; margin-top: 3px; }
.meta-row    { font-size: 0.8rem; color: #888; margin-top: 10px; }
.why-useful  { font-size: 0.82rem; color: #666; margin-top: 8px; font-style: italic; }

.badge { display:inline-block; padding:3px 12px; border-radius:20px; font-size:0.75rem; font-weight:600; }
.badge-granted   { background:#e8f5e9; color:#2e7d32; border:1px solid #a5d6a7; }
.badge-dismissed { background:#ffebee; color:#c62828; border:1px solid #ef9a9a; }
.badge-disposed  { background:#fff8e1; color:#f57f17; border:1px solid #ffe082; }
.badge-allowed   { background:#e8f5e9; color:#2e7d32; border:1px solid #a5d6a7; }
.badge-other     { background:#f5f5f5; color:#757575; border:1px solid #e0e0e0; }

#MainMenu { visibility: hidden; }
footer     { visibility: hidden; }
header     { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_supabase():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

supabase = get_supabase()

CATEGORIES = {
    "": "All Categories",
    "bail_regular": "Regular Bail",
    "bail_anticipatory": "Anticipatory Bail",
    "bail_ndps": "NDPS Bail",
    "cwp": "Civil Writ Petition",
    "cwp_service": "Service Matter",
    "crr": "Criminal Revision",
    "cra": "Criminal Appeal",
    "rsa": "Regular Second Appeal",
    "rfa": "Regular First Appeal",
    "fao": "First Appeal from Order",
    "matrimonial": "Matrimonial",
    "contempt": "Contempt",
}

OUTCOMES = ["", "Granted", "Dismissed", "Disposed Of", "Allowed", "Partly Allowed",
            "Interim Protection Granted", "Notice Issued", "Withdrawn", "Other"]

OUTCOME_BADGE = {
    "Granted":      "badge-granted",
    "Allowed":      "badge-allowed",
    "Partly Allowed": "badge-disposed",
    "Dismissed":    "badge-dismissed",
    "Disposed Of":  "badge-disposed",
}

def outcome_badge(outcome):
    if not outcome or outcome in ("Unknown", "Other", ""):
        return ""
    cls = OUTCOME_BADGE.get(outcome, "badge-other")
    return f'<span class="badge {cls}">{outcome}</span>'


def search_page():
    st.markdown("""
    <div class="app-header">
        <h1>⚖️ Punjab & Haryana High Court — Legal AI</h1>
        <p>Search 1,052+ judgments with AI-powered summaries</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Search + filters ──────────────────────────────────────────────────────
    query = st.text_input("", placeholder="🔍  Search by keyword, section, party name, judge...",
                          label_visibility="collapsed")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        category = st.selectbox("Category", options=list(CATEGORIES.keys()),
                                format_func=lambda x: CATEGORIES[x])
    with col2:
        outcome = st.selectbox("Outcome", options=OUTCOMES)
    with col3:
        judge = st.text_input("Judge", placeholder="e.g. Sandeep Moudgil")
    with col4:
        section = st.text_input("Section", placeholder="e.g. 302 IPC")

    col5, col6, _ = st.columns([1, 1, 2])
    with col5:
        from_date = st.date_input("From date", value=None)
    with col6:
        to_date = st.date_input("To date", value=None)

    st.divider()

    # ── Pagination ────────────────────────────────────────────────────────────
    if "page_num" not in st.session_state:
        st.session_state.page_num = 0
    PAGE_SIZE = 20

    filter_key = f"{query}{category}{outcome}{judge}{section}{from_date}{to_date}"
    if st.session_state.get("last_filter_key") != filter_key:
        st.session_state.page_num = 0
        st.session_state.last_filter_key = filter_key

    params = {
        "query": query or None,
        "p_category": category or None,
        "p_outcome": outcome or None,
        "p_judge": judge or None,
        "p_section": section or None,
        "p_from_date": from_date.isoformat() if from_date else None,
        "p_to_date": to_date.isoformat() if to_date else None,
        "p_limit": PAGE_SIZE + 1,
        "p_offset": st.session_state.page_num * PAGE_SIZE,
    }

    try:
        results = supabase.rpc("search_cases", params).execute()
        data = results.data
    except Exception as e:
        st.error(f"Search error: {e}")
        return

    has_next = len(data) > PAGE_SIZE
    data = data[:PAGE_SIZE]

    if not data and st.session_state.page_num == 0:
        if any([query, category, outcome, judge, section]):
            st.info("No cases found. Try broadening your search.")
        else:
            st.markdown("<p style='color:#aaa; text-align:center; padding:48px 0'>Enter a search term or select a category to browse cases</p>",
                        unsafe_allow_html=True)
        return

    # ── Results bar ───────────────────────────────────────────────────────────
    start = st.session_state.page_num * PAGE_SIZE + 1
    end = start + len(data) - 1
    col_info, col_prev, col_next = st.columns([5, 1, 1])
    with col_info:
        st.markdown(f"<p style='color:#666; font-size:0.9rem; margin:6px 0'><b>Showing {start}–{end}</b></p>",
                    unsafe_allow_html=True)
    with col_prev:
        if st.button("← Prev", disabled=st.session_state.page_num == 0):
            st.session_state.page_num -= 1
            st.rerun()
    with col_next:
        if st.button("Next →", disabled=not has_next):
            st.session_state.page_num += 1
            st.rerun()

    # ── Cards ─────────────────────────────────────────────────────────────────
    for case in data:
        sections_str = "  ·  ".join(case['sections'][:2]) if case['sections'] else "—"
        badge        = outcome_badge(case.get('outcome'))
        why          = case.get('summary_why_useful', '')
        why_html     = f'<div class="why-useful">💡 {why[:220]}{"..." if len(why) > 220 else ""}</div>' if why else ""

        st.markdown(f"""
        <div class="case-card">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px">
                <div>
                    <div class="case-number">{case['case_number']}</div>
                    <div class="case-title">{case.get('case_title') or ''}</div>
                </div>
                <div style="flex-shrink:0">{badge}</div>
            </div>
            <div class="meta-row">
                📅 {case.get('decision_date') or '—'} &nbsp;&nbsp;
                👨‍⚖️ {case.get('judge') or '—'} &nbsp;&nbsp;
                📁 {case.get('case_category') or '—'} &nbsp;&nbsp;
                ⚖️ {sections_str}
            </div>
            {why_html}
        </div>
        """, unsafe_allow_html=True)

        if st.button("View →", key=f"view_{case['id']}"):
            st.session_state.selected_case = case['id']
            st.session_state.page = "detail"
            st.rerun()


def detail_page(case_id):
    if st.button("← Back to search"):
        st.session_state.page = "search"
        st.session_state.selected_case = None
        st.rerun()

    try:
        result = supabase.table("cases").select("*").eq("id", case_id).single().execute()
        case = result.data
    except Exception as e:
        st.error(f"Could not load case: {e}")
        return

    badge = outcome_badge(case.get('outcome'))

    st.markdown(f"""
    <div class="app-header">
        <h1>{case.get('case_number', '')}</h1>
        <p>{case.get('case_title', '')}</p>
    </div>
    """, unsafe_allow_html=True)

    if badge:
        st.markdown(badge, unsafe_allow_html=True)
        st.markdown("")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Decision Date", case.get('decision_date') or '—')
    col2.metric("Judge", case.get('judge') or '—')
    col3.metric("Category", case.get('case_category') or '—')
    col4.metric("Court", "PHHC Chandigarh")

    st.divider()

    col_p, col_r = st.columns(2)
    with col_p:
        st.markdown("**Petitioner**")
        st.write(case.get('petitioner') or '—')
        st.caption(f"Advocate: {case.get('advocate_petitioner') or '—'}")
    with col_r:
        st.markdown("**Respondent**")
        st.write(case.get('respondent') or '—')
        st.caption(f"Advocate: {case.get('advocate_respondent') or '—'}")

    if case.get('fir_number'):
        with st.expander("FIR Details"):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("FIR No.", case.get('fir_number') or '—')
            c2.metric("Date", case.get('fir_date') or '—')
            c3.metric("Police Station", case.get('police_station') or '—')
            c4.metric("District", case.get('district') or '—')

    if case.get('sections'):
        st.markdown("**Sections**")
        st.write("  ·  ".join(case['sections']))

    st.divider()
    st.markdown("### 🤖 AI Summary")

    if case.get('summary_facts'):
        st.markdown("**Facts**")
        st.write(case['summary_facts'])

    if case.get('summary_legal_issue'):
        st.markdown("**Legal Issue**")
        st.write(case['summary_legal_issue'])

    col_pet, col_res = st.columns(2)
    with col_pet:
        if case.get('petitioners_arguments'):
            st.markdown("**Petitioner's Arguments**")
            for arg in case['petitioners_arguments']:
                st.markdown(f"- {arg}")
    with col_res:
        if case.get('respondents_arguments'):
            st.markdown("**Respondent's Arguments**")
            for arg in case['respondents_arguments']:
                st.markdown(f"- {arg}")

    if case.get('courts_reasoning'):
        st.markdown("**Court's Reasoning**")
        for r in case['courts_reasoning']:
            st.markdown(f"- {r}")

    if case.get('summary_final_outcome'):
        st.markdown("**Final Outcome**")
        st.info(case['summary_final_outcome'])

    if case.get('directions'):
        st.markdown("**Directions**")
        for d in case['directions']:
            st.markdown(f"- {d}")

    if case.get('summary_why_useful'):
        st.markdown("**Why This Case Is Useful**")
        st.success(case['summary_why_useful'])

    if case.get('search_tags'):
        st.divider()
        st.markdown("**Search Tags**")
        st.write("  ·  ".join(case['search_tags']))


# ── Router ────────────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "search"
if "selected_case" not in st.session_state:
    st.session_state.selected_case = None

if st.session_state.page == "search":
    search_page()
elif st.session_state.page == "detail":
    detail_page(st.session_state.selected_case)
