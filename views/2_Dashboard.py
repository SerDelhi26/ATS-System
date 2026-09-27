import streamlit as st
from common import show_logout, show_job_notifications, show_user_profile, fetch_all_live_candidates, fetch_all_from_table
from db import supabase
import pandas as pd
import plotly.express as px
from datetime import date, datetime
from theme import apply_theme

# ==========================
# CUSTOM KPI CARD CSS
# ==========================
def kpi_card(title, value, icon, color):
    st.markdown(
        f"""
        <div style="
            background: white;
            padding: 20px;
            border-radius: 12px;
            text-align: left;
            box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.05);
            border-left: 6px solid {color};
            display: flex;
            align-items: center;
            justify-content: space-between;
        ">
            <div>
                <div style="color: #64748B; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">
                    {title}
                </div>
                <div style="color: #0F172A; font-size: 26px; font-weight: bold; margin-top: 5px;">
                    {value}
                </div>
            </div>
            <div style="font-size: 28px; color: {color}; opacity: 0.8;">
                {icon}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ==========================
# LOGIN CHECK
# ==========================
if not st.session_state.get("logged_in", False):
    st.switch_page("Home.py")
    st.stop()

# ==========================
# PAGE CONFIG
# ==========================
st.set_page_config(
    page_title="ATS Dashboard",
    layout="wide"
)
apply_theme()

with st.sidebar:
    show_user_profile()
    show_logout()
    show_job_notifications()

st.markdown("# 📊 ATS Analytics Dashboard")
st.caption(f"Welcome back, **{st.session_state.user_name}** ({st.session_state.user_role})")

# Data Protection: Hide table download buttons & toolbars for non-Admin/Developer users
if st.session_state.get("user_role") not in ["Admin", "Developer", "Admin-Lite"]:
    st.markdown(
        """
        <style>
        [data-testid="stElementToolbar"],
        [data-testid="stDataFrameToolbar"],
        button[title="Download as CSV"],
        button[title="Download data as CSV"],
        div[data-testid="stElementToolbarButton"],
        .stDownloadButton,
        [data-testid="stDownloadButton"] {
            display: none !important;
            visibility: hidden !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

from concurrent.futures import ThreadPoolExecutor

# ==========================
# DATA FETCHING
# ==========================
@st.cache_data(ttl=180, show_spinner=False)
def get_dashboard_data():
    with ThreadPoolExecutor(max_workers=8) as executor:
        fut_jobs = executor.submit(
            fetch_all_from_table,
            "job_management",
            select_fields="job_id, job_reference_no, job_status, openings, company_id, job_title_id, created_date, modified_date, created_by"
        )
        # Fetch ALL candidates regardless of job status for accurate KPI counting (hired on closed jobs must still count)
        fut_candidates = executor.submit(
            fetch_all_from_table,
            "candidate_management",
            select_fields="candidate_id, candidate_reference_no, first_name, last_name, job_id, current_stage, candidate_status, created_by_name, created_by_user_id, created_on, updated_on, mobile_no, email, current_company, current_designation, experience_years, experience_months, current_ctc, expected_ctc, notice_period, remarks",
            order_by="candidate_id",
            desc=True
        )
        fut_interviews = executor.submit(
            fetch_all_from_table,
            "interview_management",
            select_fields="interview_id, candidate_id, job_id, interview_round, interview_date, interview_status, feedback, created_by_name, created_on"
        )
        fut_offers = executor.submit(
            fetch_all_from_table,
            "offer_management",
            select_fields="offer_id, candidate_id, job_id, offer_status, offered_ctc, joining_date, remarks, created_by_name, created_on"
        )
        fut_users = executor.submit(lambda: supabase.table("users").select("user_id, full_name, role").execute().data or [])
        fut_titles = executor.submit(lambda: supabase.table("job_title_master").select("job_title_id, job_title_name").execute().data or [])
        fut_comps = executor.submit(lambda: supabase.table("company_master").select("company_id, company_name").execute().data or [])
        fut_assigns = executor.submit(lambda: supabase.table("job_assignment").select("job_id, user_id").execute().data or [])

    return (
        fut_jobs.result(),
        fut_candidates.result(),
        fut_interviews.result(),
        fut_offers.result(),
        fut_users.result(),
        fut_titles.result(),
        fut_comps.result(),
        fut_assigns.result()
    )

jobs, candidates, interviews, offers, all_users, job_titles, companies, job_assignments = get_dashboard_data()

with st.sidebar:
    if st.button("🔄 Refresh Metrics", use_container_width=True, help="Fetch fresh data from database"):
        get_dashboard_data.clear()
        st.rerun()

# Lookups
admin_uids = {u["user_id"] for u in all_users if u.get("role") in ["Admin", "Developer"]}
admin_names = {u["full_name"].strip().lower() for u in all_users if u.get("role") in ["Admin", "Developer"]} | {"admin", "system admin", "administrator", "developer"}
recruiters = [u for u in all_users if u.get("role") in ["Recruiter", "Admin-Lite"]]
recruiter_uids = {u["user_id"] for u in recruiters}
recruiter_names_lower = {r["full_name"].strip().lower() for r in recruiters}
job_title_lookup = {item["job_title_id"]: item["job_title_name"] for item in job_titles}
company_lookup = {item["company_id"]: item["company_name"] for item in companies}
recruiter_user_map = {r["full_name"]: r["user_id"] for r in recruiters}
recruiter_id_to_name = {r["user_id"]: r["full_name"] for r in recruiters}
job_status_lookup = {j["job_id"]: str(j.get("job_status") or "Open").strip() for j in jobs}
offer_map = {o["candidate_id"]: o for o in offers if o.get("candidate_id")}

job_lookup = {}
all_job_labels_map = {}
all_label_to_job_id = {}
for job in jobs:
    title = job_title_lookup.get(job["job_title_id"], "Unknown")
    label = f"{job['job_reference_no']} | {title}"
    job_lookup[job["job_id"]] = label
    all_job_labels_map[job["job_id"]] = label
    all_label_to_job_id[label] = job["job_id"]

# Build reciprocal mappings between Jobs and Recruiters (strictly only Recruiters, exclude Admins)
job_id_to_rec_uids = {}
for j in jobs:
    jid = j["job_id"]
    uids = {ja["user_id"] for ja in job_assignments if ja.get("job_id") == jid and ja.get("user_id") in recruiter_uids}
    if j.get("created_by") and j.get("created_by") in recruiter_uids:
        uids.add(j["created_by"])
    job_id_to_rec_uids[jid] = uids

rec_uid_to_job_ids = {}
for r in recruiters:
    uid = r["user_id"]
    jids = {j["job_id"] for j in jobs if (j.get("created_by") == uid or any(ja.get("job_id") == j["job_id"] and ja.get("user_id") == uid for ja in job_assignments))}
    rec_uid_to_job_ids[uid] = jids

def get_candidate_recruiter_display(c):
    # Strictly only return Recruiter name(s). Never return Admin names.
    c_uid = safe_int(c.get("created_by_user_id"))
    if not (c_uid and c_uid in admin_uids):
        rec_name = (c.get("created_by_name") or "").strip()
        if rec_name and rec_name.lower() in recruiter_names_lower and rec_name.lower() not in admin_names:
            return rec_name
    
    # Fallback to recruiters assigned to the candidate's job
    c_jid = safe_int(c.get("job_id"))
    if c_jid:
        assigned_recs = [recruiter_id_to_name[u] for u in job_id_to_rec_uids.get(c_jid, set()) if u in recruiter_id_to_name]
        if assigned_recs:
            return ", ".join(sorted(assigned_recs))
            
    return "Unassigned"

def parse_date(date_val):
    if not date_val:
        return None
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    val_str = str(date_val).strip()
    if not val_str or val_str.lower() in ["none", "nan", "null"]:
        return None
    clean_time = val_str.split(".")[0].split("+")[0].replace("Z", "").replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(clean_time, fmt).date()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(clean_time).date()
    except Exception:
        return None

def safe_int(val):
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None

# Helper function to convert 0 to None for cleaner UI rendering in tables
def clean_zero(val):
    return val if val > 0 else None

# ==========================
# FILTERS UI
# ==========================
st.markdown("### 🔍 Dashboard Filters")

# Read current selections from session state for dynamic options
cur_rec_filter = st.session_state.get("dash_recruiter_select", "All Recruiters")
cur_job_filter = st.session_state.get("dash_job_select", "All Jobs")

# Dynamic options for Recruiters based on selected Job
if cur_job_filter != "All Jobs" and cur_job_filter in all_label_to_job_id:
    target_job_id = all_label_to_job_id[cur_job_filter]
    allowed_rec_uids = job_id_to_rec_uids.get(target_job_id, set())
    recruiter_options = ["All Recruiters"] + sorted([recruiter_id_to_name[uid] for uid in allowed_rec_uids if uid in recruiter_id_to_name])
else:
    recruiter_options = ["All Recruiters"] + sorted([r["full_name"] for r in recruiters])

if cur_rec_filter not in recruiter_options:
    cur_rec_filter = "All Recruiters"
    st.session_state["dash_recruiter_select"] = "All Recruiters"

# Dynamic options for Jobs based on selected Recruiter
if cur_rec_filter != "All Recruiters" and cur_rec_filter in recruiter_user_map:
    target_rec_uid = recruiter_user_map[cur_rec_filter]
    allowed_job_ids = rec_uid_to_job_ids.get(target_rec_uid, set())
    job_options = ["All Jobs"] + [all_job_labels_map[jid] for jid in allowed_job_ids if jid in all_job_labels_map]
else:
    job_options = ["All Jobs"] + [all_job_labels_map[j["job_id"]] for j in jobs if j["job_id"] in all_job_labels_map]

if cur_job_filter not in job_options:
    cur_job_filter = "All Jobs"
    st.session_state["dash_job_select"] = "All Jobs"

f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([1.5, 2, 2, 2, 2.5])

with f_col1:
    use_date_filter = st.checkbox("📅 Date Filter", value=False)
with f_col2:
    from_date = st.date_input("From Date", value=date(date.today().year, 1, 1), disabled=not use_date_filter)
with f_col3:
    to_date = st.date_input("To Date", value=date.today(), disabled=not use_date_filter)
with f_col4:
    recruiter_filter = st.selectbox("👤 Recruiter", recruiter_options, key="dash_recruiter_select")
with f_col5:
    job_filter = st.selectbox("💼 Job", job_options, key="dash_job_select")

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ==========================
# FILTER DATA ACROSS JOBS, CANDIDATES, INTERVIEWS & OFFERS
# ==========================
selected_job_id = all_label_to_job_id.get(job_filter) if job_filter != "All Jobs" else None
selected_rec_uid = recruiter_user_map.get(recruiter_filter) if recruiter_filter != "All Recruiters" else None
rec_associated_job_ids = rec_uid_to_job_ids.get(selected_rec_uid, set()) if selected_rec_uid else set()

# 1. Filter Jobs
filtered_jobs = []
for j in jobs:
    jid = j.get("job_id")
    job_created_date = parse_date(j.get("created_date"))
    
    if use_date_filter and job_created_date:
        if job_created_date < from_date or job_created_date > to_date:
            continue
            
    if selected_job_id is not None and jid != selected_job_id:
        continue
        
    if recruiter_filter != "All Recruiters":
        if jid not in rec_associated_job_ids and j.get("created_by") != selected_rec_uid:
            continue
            
    filtered_jobs.append(j)

filtered_job_ids = {j["job_id"] for j in filtered_jobs}

# 2. Filter Candidates
filtered_candidates = []
for c in candidates:
    c_jid = safe_int(c.get("job_id"))
    cand_date = parse_date(c.get("created_on")) or parse_date(c.get("updated_on"))
    
    if use_date_filter and cand_date:
        if cand_date < from_date or cand_date > to_date:
            continue
            
    if selected_job_id is not None and c_jid != selected_job_id:
        continue
        
    if recruiter_filter != "All Recruiters":
        cand_rec = get_candidate_recruiter_display(c)
        req_rec_name = recruiter_filter.strip().lower()
        cand_rec_list = [r.strip().lower() for r in cand_rec.split(",")]
        
        if req_rec_name not in cand_rec_list:
            continue
            
    filtered_candidates.append(c)

filtered_candidate_ids = {c["candidate_id"] for c in filtered_candidates}
filtered_interviews = [i for i in interviews if i.get("candidate_id") in filtered_candidate_ids]
filtered_offers = [o for o in offers if o.get("candidate_id") in filtered_candidate_ids]

# Helpers for offer & hired status evaluation
def is_candidate_hired(c):
    cid = c.get("candidate_id")
    off = offer_map.get(cid)
    off_status = (off.get("offer_status") or "").strip() if off else ""
    stage = (c.get("current_stage") or "").strip()
    status = (c.get("candidate_status") or "").strip()
    return off_status in ["Joined", "Hired"] or stage in ["Joined", "Hired"] or status in ["Joined", "Hired"]

def is_candidate_offer_released(c):
    cid = c.get("candidate_id")
    off = offer_map.get(cid)
    off_status = (off.get("offer_status") or "").strip() if off else ""
    stage = (c.get("current_stage") or "").strip()
    status = (c.get("candidate_status") or "").strip()
    
    # If candidate is already joined/hired, they are Hired, not pending Offer Released
    if is_candidate_hired(c):
        return False
        
    # If offer was rejected or candidate no-showed, they are not in active Offer Released
    if off_status in ["Offer Rejected", "Declined", "Revoked", "No Show"] or status in ["Offer Rejected", "Declined", "Rejected", "No Show"] or stage in ["Offer Rejected", "Declined", "Rejected"]:
        return False
        
    # Active released offer awaiting candidate response or joining
    if off_status in ["Offer Released", "Offered", "Offer Sent", "Sent to Candidate"]:
        return True
    if not off_status and (stage in ["Offer", "Offer Released"] or status in ["Offer Released", "Offered"]):
        return True
    return False

# ==========================
# TOP LEVEL METRICS (5 CARDS)
# ==========================
# KPI counts for Hired & Offer Released use ALL candidates (including those on closed jobs)
# so that auto-closed jobs don't hide real hiring data. Other counts respect the filter.
open_jobs = len([j for j in filtered_jobs if str(j.get("job_status") or "").strip().lower() == "open"])
total_candidates = len(filtered_candidates)
active_interviews = len(filtered_interviews)

# For Hired & Offer Released: apply only recruiter/job filter (not job-status filter)
# so candidates on auto-closed jobs are still counted correctly.
kpi_candidate_pool = []
for c in candidates:
    c_jid = safe_int(c.get("job_id"))
    cand_date = parse_date(c.get("created_on")) or parse_date(c.get("updated_on"))
    if use_date_filter and cand_date:
        if cand_date < from_date or cand_date > to_date:
            continue
    if selected_job_id is not None and c_jid != selected_job_id:
        continue
    if recruiter_filter != "All Recruiters":
        cand_rec = get_candidate_recruiter_display(c)
        req_rec_name = recruiter_filter.strip().lower()
        cand_rec_list = [r.strip().lower() for r in cand_rec.split(",")]
        if req_rec_name not in cand_rec_list:
            continue
    kpi_candidate_pool.append(c)

# KPI offer map covers all offers (not just open-job candidates)
kpi_offer_map = {o["candidate_id"]: o for o in offers if o.get("candidate_id")}

def is_kpi_candidate_hired(c):
    cid = c.get("candidate_id")
    off = kpi_offer_map.get(cid)
    off_status = (off.get("offer_status") or "").strip() if off else ""
    stage = (c.get("current_stage") or "").strip()
    status = (c.get("candidate_status") or "").strip()
    return off_status in ["Joined", "Hired"] or stage in ["Joined", "Hired"] or status in ["Joined", "Hired"]

def is_kpi_offer_released(c):
    cid = c.get("candidate_id")
    off = kpi_offer_map.get(cid)
    off_status = (off.get("offer_status") or "").strip() if off else ""
    stage = (c.get("current_stage") or "").strip()
    status = (c.get("candidate_status") or "").strip()
    if is_kpi_candidate_hired(c):
        return False
    if off_status in ["Offer Rejected", "Declined", "Revoked", "No Show"] or status in ["Offer Rejected", "Declined", "Rejected", "No Show"] or stage in ["Offer Rejected", "Declined", "Rejected"]:
        return False
    if off_status in ["Offer Released", "Offered", "Offer Sent", "Sent to Candidate"]:
        return True
    if not off_status and (stage in ["Offer", "Offer Released"] or status in ["Offer Released", "Offered"]):
        return True
    return False

offer_released_count = len([c for c in kpi_candidate_pool if is_kpi_offer_released(c)])
total_hired = len([c for c in kpi_candidate_pool if is_kpi_candidate_hired(c)])

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    kpi_card("Jobs", open_jobs, "💼", "#2563EB")
with col2:
    kpi_card("Candidates", total_candidates, "👥", "#8B5CF6")
with col3:
    kpi_card("Interviews", active_interviews, "📅", "#F59E0B")
with col4:
    kpi_card("Offer Released", offer_released_count, "📄", "#0EA5E9")
with col5:
    kpi_card("Total Hired", total_hired, "🎉", "#10B981")

st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)

# ==========================
# CHARTS ROW
# ==========================
chart_col1, chart_col2 = st.columns([3, 2])

with chart_col1:
    st.markdown("### 🎯 Recruitment Pipeline")
    stages = ["New", "Screening", "Shortlisted", "Interview", "Selected", "Offer", "Joined"]
    pipeline_counts = {stage: 0 for stage in stages}
    
    for c in filtered_candidates:
        if is_candidate_hired(c):
            effective_stage = "Joined"
        elif is_candidate_offer_released(c):
            effective_stage = "Offer"
        else:
            effective_stage = c.get("current_stage")
            
        if effective_stage in pipeline_counts:
            pipeline_counts[effective_stage] += 1
            
    funnel_df = pd.DataFrame({
        "Stage": list(pipeline_counts.keys()),
        "Count": list(pipeline_counts.values())
    })
    
    fig_funnel = px.funnel(funnel_df, x='Count', y='Stage', color_discrete_sequence=['#3B82F6'])
    fig_funnel.update_layout(margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_funnel, use_container_width=True)

with chart_col2:
    st.markdown("### 💼 Job Status Breakdown")
    status_counts = {}
    for j in filtered_jobs:
        status = j.get("job_status", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        
    pie_df = pd.DataFrame({
        "Status": list(status_counts.keys()),
        "Count": list(status_counts.values())
    })
    
    color_map = {"Open": "#10B981", "Closed": "#EF4444", "On Hold": "#F59E0B", "Cancelled": "#64748B"}
    fig_pie = px.pie(pie_df, names='Status', values='Count', hole=0.5, color='Status', color_discrete_map=color_map)
    fig_pie.update_layout(margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor="rgba(0,0,0,0)", showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    st.plotly_chart(fig_pie, use_container_width=True)


# ==========================
# RECRUITER PERFORMANCE TABLE
# ==========================
st.divider()
st.markdown("### 🏆 Recruiter Performance")
st.caption("Overview of team productivity based on their assigned candidates.")

performance_data = []
for recruiter in recruiters:
    r_name = recruiter["full_name"]
    r_id = recruiter["user_id"]
    
    # Respect the global dropdown filter for recruiters
    if recruiter_filter != "All Recruiters" and r_name != recruiter_filter:
        continue
        
    # Map performance by Candidate Creator or Assigned Job (only Recruiters)
    r_cands = [
        c for c in filtered_candidates 
        if c.get("created_by_name") == r_name 
        or (c.get("created_by_name", "").strip().lower() in admin_names and r_name in get_candidate_recruiter_display(c).split(", "))
    ]
    
    pipeline_total = len(r_cands)
    shortlisted = len([c for c in r_cands if c.get("current_stage") == "Shortlisted" or c.get("candidate_status") == "Shortlisted"])
    interviews_cnt = len([c for c in r_cands if c.get("current_stage") == "Interview"])
    offers_cnt = len([c for c in r_cands if is_candidate_offer_released(c)])
    hires = len([c for c in r_cands if is_candidate_hired(c)])
    
    conversion = (hires / pipeline_total * 100) if pipeline_total > 0 else 0
    
    # Apply clean_zero so zeroes appear as blanks
    performance_data.append({
        "Recruiter": r_name,
        "Total Pipeline": clean_zero(pipeline_total),
        "Shortlisted": clean_zero(shortlisted),
        "In Interview": clean_zero(interviews_cnt),
        "Offered": clean_zero(offers_cnt),
        "Hired": clean_zero(hires),
        "Conversion Rate": conversion
    })

perf_df = pd.DataFrame(performance_data)

if not perf_df.empty:
    perf_df = perf_df.sort_values(by=["Hired", "Total Pipeline"], ascending=[False, False])
    st.dataframe(
        perf_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Recruiter": st.column_config.TextColumn("Recruiter Name"),
            "Total Pipeline": st.column_config.NumberColumn("Total Pipeline", format="%d"),
            "Shortlisted": st.column_config.NumberColumn("Shortlisted", format="%d"),
            "In Interview": st.column_config.NumberColumn("In Interview", format="%d"),
            "Offered": st.column_config.NumberColumn("Offered", format="%d"),
            "Hired": st.column_config.NumberColumn("Total Hires", format="%d"),
            "Conversion Rate": st.column_config.ProgressColumn(
                "Hire/Pipeline %",
                format="%d%%",
                min_value=0,
                max_value=100
            )
        }
    )
else:
    st.info("No recruiter performance data found for the selected filters.")



# ==============================================================================
# 🔥 HOT PIPELINE RADAR (High-Priority Candidates Nearing Offer / Joining)
# ==============================================================================
st.divider()
st.markdown("### 🔥 Hot Pipeline Radar")
st.caption("High-priority talent close to conversion, active offers in-flight, and stalled candidates requiring immediate recruiter intervention.")

# Lookup maps for jobs and companies
job_obj_map = {j["job_id"]: j for j in jobs}
interview_cand_map = {}
for iv in interviews:
    cid = iv.get("candidate_id")
    if cid:
        if cid not in interview_cand_map:
            interview_cand_map[cid] = []
        interview_cand_map[cid].append(iv)

# Pre-map candidate and interview activity per job for fast stagnancy evaluation
cand_dates_by_job = {}
cand_active_by_job = {}
cand_total_by_job = {}
for c in filtered_candidates:
    c_jid = safe_int(c.get("job_id"))
    if c_jid:
        c_d = parse_date(c.get("updated_on") or c.get("created_on"))
        if c_d:
            cand_dates_by_job.setdefault(c_jid, []).append(c_d)
        cand_total_by_job[c_jid] = cand_total_by_job.get(c_jid, 0) + 1
        if (c.get("current_stage") or "").strip() in ["New", "Screening", "Shortlisted", "Interview", "Selected"]:
            cand_active_by_job[c_jid] = cand_active_by_job.get(c_jid, 0) + 1

iv_dates_by_job = {}
for iv in interviews:
    iv_jid = safe_int(iv.get("job_id"))
    if iv_jid:
        iv_d = parse_date(iv.get("interview_date") or iv.get("created_on"))
        if iv_d:
            iv_dates_by_job.setdefault(iv_jid, []).append(iv_d)

radar_tab1, radar_tab2, radar_tab3, radar_tab4 = st.tabs([
    "👑 Ready for Offer",
    "⏳ Pending Acceptance & Joining",
    "🚨 Stagnant / At-Risk Talent (>7 Days)",
    "💼 Stagnant / At-Risk Jobs (>7 Days)"
])

# ------------------------------------------------------------------------------
# TAB 1: READY FOR OFFER
# ------------------------------------------------------------------------------
with radar_tab1:
    ready_candidates = []
    
    for c in filtered_candidates:
        cid = c.get("candidate_id")
        c_stage = (c.get("current_stage") or "").strip()
        c_status = (c.get("candidate_status") or "").strip()
        
        # Check if candidate is marked as Selected or cleared final interviews
        c_interviews = interview_cand_map.get(cid, [])
        has_selected_interview = any(iv.get("interview_status") == "Selected" for iv in c_interviews)
        has_rejected_interview = any(iv.get("interview_status") == "Rejected" for iv in c_interviews)
        
        cand_offer = offer_map.get(cid)
        off_status = (cand_offer.get("offer_status") or "").strip() if cand_offer else ""
        
        is_selected = (c_stage in ["Selected", "Final Round", "Shortlisted"] or c_status in ["Selected", "Shortlisted"] or has_selected_interview)
        is_not_offered_yet = off_status not in ["Offered", "Offer Released", "Offer Accepted", "Joined", "Hired"]
        is_rejected = (
            c_status in ["Rejected", "Offer Rejected", "Declined", "Cancelled"]
            or c_stage in ["Rejected", "Offer Rejected", "Declined", "Cancelled"]
            or off_status in ["Offer Rejected", "Declined", "Revoked"]
            or has_rejected_interview
        )
        is_not_rejected = not is_rejected and c_status not in ["Joined", "Hired"] and c_stage not in ["Joined", "Hired"]
        
        # Ensure candidate belongs to an active Open job
        if str(job_status_lookup.get(c.get("job_id"), "")).strip().lower() != "open":
            continue
            
        if is_selected and is_not_offered_yet and is_not_rejected:
            # Calculate days since last update / creation
            act_date = parse_date(c.get("updated_on") or c.get("created_on"))
            days_waiting = (date.today() - act_date).days if act_date else 0
            
            job_obj = job_obj_map.get(c.get("job_id"), {})
            title_name = job_title_lookup.get(job_obj.get("job_title_id"), "Role N/A")
            comp_name = company_lookup.get(job_obj.get("company_id"), "Client N/A")
            
            exp_y = c.get("experience_years") or 0
            exp_m = c.get("experience_months") or 0
            exp_str = f"{exp_y}Y {exp_m}M" if (exp_y or exp_m) else "N/A"
            
            c_ctc = float(c.get("current_ctc")) if c.get("current_ctc") else None
            e_ctc = float(c.get("expected_ctc")) if c.get("expected_ctc") else None
            
            rec_display = get_candidate_recruiter_display(c)
            if recruiter_filter != "All Recruiters":
                req_name = recruiter_filter.strip().lower()
                c_recs = [r.strip().lower() for r in rec_display.split(",")]
                if req_name not in c_recs:
                    continue
                rec_display = recruiter_filter

            ready_candidates.append({
                "Recruiter": rec_display,
                "Candidate Name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "Unnamed",
                "Target Role & Client": f"💼 {title_name} ({comp_name})",
                "Current Stage": f"🌟 {c_stage or 'Selected'}",
                "Experience": exp_str,
                "Notice Period": c.get("notice_period") or "Standard",
                "Current CTC": c_ctc,
                "Expected CTC": e_ctc,
                "Mobile": c.get("mobile_no") or "N/A",
                "Days in Stage": f"⏱️ {days_waiting} days ago" if days_waiting > 0 else "Today",
                "_days_num": days_waiting
            })

    if ready_candidates:
        df_ready = pd.DataFrame(ready_candidates).sort_values(by="_days_num", ascending=False).drop(columns=["_days_num"])
        
        r_c1, r_c2, r_c3 = st.columns(3)
        r_c1.metric("👑 Candidates Awaiting Offer", len(ready_candidates))
        immediate_cnt = len([r for r in ready_candidates if "immediate" in str(r.get("Notice Period", "")).lower() or "0" in str(r.get("Notice Period", ""))])
        r_c2.metric("⚡ Immediate / Short Notice Joiners", immediate_cnt)
        avg_exp_ctc = sum(r["Expected CTC"] for r in ready_candidates if r["Expected CTC"]) / max(1, len([r for r in ready_candidates if r["Expected CTC"]]))
        r_c3.metric("💰 Avg Expected CTC", f"₹{avg_exp_ctc:,.0f}" if avg_exp_ctc > 0 else "N/A")
        
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        st.dataframe(
            df_ready,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Current CTC": st.column_config.NumberColumn("Current CTC", format="₹%d"),
                "Expected CTC": st.column_config.NumberColumn("Expected CTC", format="₹%d"),
                "Candidate Name": st.column_config.TextColumn("Candidate Name", width="medium"),
                "Target Role & Client": st.column_config.TextColumn("Target Role & Client", width="large")
            }
        )
    else:
        st.info("🌟 No candidates currently waiting for an offer release.")

# ------------------------------------------------------------------------------
# TAB 2: PENDING ACCEPTANCE & JOINING
# ------------------------------------------------------------------------------
with radar_tab2:
    pending_offers = []
    
    for c in filtered_candidates:
        cid = c.get("candidate_id")
        cand_offer = offer_map.get(cid)
        c_stage = (c.get("current_stage") or "").strip()
        c_status = (c.get("candidate_status") or "").strip()
        
        off_status = (cand_offer.get("offer_status") or "").strip() if cand_offer else ""
        if not off_status and c_stage in ["Offer", "Offer Released", "Offer Accepted"]:
            off_status = c_stage
            
        is_in_offer_flight = off_status in ["Offered", "Offer Released", "Sent to Candidate", "Offer Sent", "Offer Accepted", "Offer"]
        is_not_joined = not is_candidate_hired(c)
        is_not_declined = (
            off_status not in ["Offer Rejected", "Declined", "Revoked"]
            and c_status not in ["Offer Rejected", "Declined", "Rejected"]
            and c_stage not in ["Offer Rejected", "Declined", "Rejected"]
        )
        
        # Ensure candidate belongs to an active Open job
        if str(job_status_lookup.get(c.get("job_id"), "")).strip().lower() != "open":
            continue
            
        if is_in_offer_flight and is_not_joined and is_not_declined:
            job_obj = job_obj_map.get(c.get("job_id"), {})
            title_name = job_title_lookup.get(job_obj.get("job_title_id"), "Role N/A")
            comp_name = company_lookup.get(job_obj.get("company_id"), "Client N/A")
            
            offered_ctc_val = float(cand_offer.get("offered_ctc")) if (cand_offer and cand_offer.get("offered_ctc")) else (float(c.get("expected_ctc")) if c.get("expected_ctc") else None)
            
            join_date_raw = cand_offer.get("joining_date") if cand_offer else None
            join_date_parsed = parse_date(join_date_raw)
            
            if join_date_parsed:
                days_to_join = (join_date_parsed - date.today()).days
                if days_to_join > 0:
                    join_label = f"📅 {join_date_parsed.strftime('%d %b %Y')} (in {days_to_join}d)"
                elif days_to_join == 0:
                    join_label = f"🚨 Joining Today! ({join_date_parsed.strftime('%d %b')})"
                else:
                    join_label = f"⚠️ Overdue ({abs(days_to_join)}d ago)"
            else:
                join_label = "⏳ To be Confirmed"
                
            status_badge = "🟢 Offer Accepted (Joining Soon)" if "Accepted" in off_status else "🟡 Offer Released (Awaiting Response)"
            
            rec_display = get_candidate_recruiter_display(c)
            if recruiter_filter != "All Recruiters":
                req_name = recruiter_filter.strip().lower()
                c_recs = [r.strip().lower() for r in rec_display.split(",")]
                if req_name not in c_recs:
                    continue
                rec_display = recruiter_filter

            pending_offers.append({
                "Recruiter": rec_display,
                "Candidate Name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "Unnamed",
                "Job & Client": f"💼 {title_name} ({comp_name})",
                "Offer Stage": status_badge,
                "Offered CTC": offered_ctc_val,
                "Expected Joining Date": join_label,
                "Mobile": c.get("mobile_no") or "N/A",
                "Email": c.get("email") or "N/A"
            })

    if pending_offers:
        df_offers = pd.DataFrame(pending_offers)
        
        o_c1, o_c2, o_c3 = st.columns(3)
        o_c1.metric("📄 Active Offers in Flight", len(pending_offers))
        accepted_cnt = len([o for o in pending_offers if "Accepted" in o["Offer Stage"]])
        o_c2.metric("🟢 Accepted & Awaiting Joining", accepted_cnt)
        total_offered_val = sum(o["Offered CTC"] for o in pending_offers if o["Offered CTC"])
        o_c3.metric("💼 Pipeline CTC Value", f"₹{total_offered_val:,.0f}" if total_offered_val > 0 else "N/A")
        
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        st.dataframe(
            df_offers,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Offered CTC": st.column_config.NumberColumn("Offered CTC", format="₹%d"),
                "Candidate Name": st.column_config.TextColumn("Candidate Name", width="medium"),
                "Job & Client": st.column_config.TextColumn("Job & Client", width="large")
            }
        )
    else:
        st.info("📄 No active offers currently pending acceptance or joining.")

# ------------------------------------------------------------------------------
# TAB 3: STAGNANT / AT-RISK TALENT (>7 DAYS)
# ------------------------------------------------------------------------------
with radar_tab3:
    stagnant_candidates = []
    
    for c in filtered_candidates:
        cid = c.get("candidate_id")
        c_stage = (c.get("current_stage") or "").strip()
        c_status = (c.get("candidate_status") or "").strip()
        
        # Only active in-progress candidates
        is_in_pipeline = c_stage in ["New", "Screening", "Shortlisted", "Interview", "Selected"]
        is_not_terminal = (
            c_status not in ["Rejected", "Joined", "Hired", "Offer Rejected", "Declined", "Cancelled"]
            and c_stage not in ["Rejected", "Joined", "Hired", "Offer Rejected", "Declined", "Cancelled"]
            and not any(iv.get("interview_status") == "Rejected" for iv in interview_cand_map.get(cid, []))
        )
        
        # Ensure candidate belongs to an active Open job
        if str(job_status_lookup.get(c.get("job_id"), "")).strip().lower() != "open":
            continue
            
        if is_in_pipeline and is_not_terminal:
            act_date = parse_date(c.get("updated_on") or c.get("created_on"))
            days_inactive = (date.today() - act_date).days if act_date else 0
            
            if days_inactive >= 7:
                job_obj = job_obj_map.get(c.get("job_id"), {})
                title_name = job_title_lookup.get(job_obj.get("job_title_id"), "Role N/A")
                comp_name = company_lookup.get(job_obj.get("company_id"), "Client N/A")
                
                if days_inactive >= 14:
                    delay_badge = f"🔴 {days_inactive} Days Stalled"
                    action_suggest = "🚨 Urgent: Follow-up or reassign"
                else:
                    delay_badge = f"🟡 {days_inactive} Days Inactive"
                    action_suggest = "⚠️ Schedule Interview / Log Feedback"
                    
                rec_display = get_candidate_recruiter_display(c)
                if recruiter_filter != "All Recruiters":
                    req_name = recruiter_filter.strip().lower()
                    c_recs = [r.strip().lower() for r in rec_display.split(",")]
                    if req_name not in c_recs:
                        continue
                    rec_display = recruiter_filter

                stagnant_candidates.append({
                    "Recruiter": rec_display,
                    "Candidate Name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "Unnamed",
                    "Job & Client": f"💼 {title_name} ({comp_name})",
                    "Current Stage": c_stage or "Applied",
                    "Stagnancy": delay_badge,
                    "Recommended Action": action_suggest,
                    "Mobile": c.get("mobile_no") or "N/A",
                    "_days_num": days_inactive
                })

    if stagnant_candidates:
        df_stagnant = pd.DataFrame(stagnant_candidates).sort_values(by="_days_num", ascending=False).drop(columns=["_days_num"])
        
        s_c1, s_c2, s_c3 = st.columns(3)
        s_c1.metric("🚨 Stagnant Candidates (>7d)", len(stagnant_candidates))
        crit_count = len([s for s in stagnant_candidates if "🔴" in s["Stagnancy"]])
        s_c2.metric("🔴 Critical Delays (>14d)", crit_count)
        stuck_recruiters = len(set(s["Recruiter"] for s in stagnant_candidates if s["Recruiter"] != "Unassigned"))
        s_c3.metric("👥 Recruiters with Bottlenecks", stuck_recruiters)
        
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        st.dataframe(
            df_stagnant,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Candidate Name": st.column_config.TextColumn("Candidate Name", width="medium"),
                "Job & Client": st.column_config.TextColumn("Job & Client", width="large"),
                "Recommended Action": st.column_config.TextColumn("Action Required", width="large")
            }
        )
    else:
        st.success("🌟 Great job! No candidates are currently stagnant or delayed past 7 days.")

# ------------------------------------------------------------------------------
# TAB 4: STAGNANT / AT-RISK JOBS (>7 DAYS)
# ------------------------------------------------------------------------------
with radar_tab4:
    stagnant_jobs = []
    
    for j in filtered_jobs:
        # Strictly evaluate only Open jobs (not Closed, not Hold, not On Hold)
        if str(j.get("job_status") or "").strip().lower() != "open":
            continue
            
        jid = j.get("job_id")
        
        # Calculate days since last activity (job creation, modification, candidate submission, or interview)
        job_dates = [
            d for d in [parse_date(j.get("modified_date")), parse_date(j.get("created_date"))]
            + cand_dates_by_job.get(jid, [])
            + iv_dates_by_job.get(jid, [])
            if d
        ]
        latest_act = max(job_dates) if job_dates else parse_date(j.get("created_date"))
        days_inactive = (date.today() - latest_act).days if latest_act else 0
        
        if days_inactive >= 7:
            title_name = job_title_lookup.get(j.get("job_title_id"), "Role N/A")
            comp_name = company_lookup.get(j.get("company_id"), "Client N/A")
            openings_val = safe_int(j.get("openings")) or 1
            active_cnt = cand_active_by_job.get(jid, 0)
            total_cand_cnt = cand_total_by_job.get(jid, 0)
            
            rec_names = [recruiter_id_to_name[u] for u in job_id_to_rec_uids.get(jid, set()) if u in recruiter_id_to_name]
            
            if recruiter_filter != "All Recruiters":
                req_name = recruiter_filter.strip().lower()
                rec_names_lower_list = [r.strip().lower() for r in rec_names]
                if req_name not in rec_names_lower_list and j.get("created_by") != selected_rec_uid:
                    continue
                rec_display = recruiter_filter
            else:
                rec_display = ", ".join(sorted(rec_names)) if rec_names else "Unassigned"
            
            if days_inactive >= 14:
                delay_badge = f"🔴 {days_inactive} Days Stalled"
                if active_cnt == 0:
                    action_suggest = "🚨 Critical: 0 Active Candidates - Urgent Sourcing"
                else:
                    action_suggest = "🚨 Urgent: Pipeline Stalled - Follow up with Client / Review Shortlist"
            else:
                delay_badge = f"🟡 {days_inactive} Days Inactive"
                if active_cnt == 0:
                    action_suggest = "⚠️ No Active Sourcing - Add Candidates"
                else:
                    action_suggest = "⚠️ Advance Candidates / Schedule Interviews"
                    
            stagnant_jobs.append({
                "Recruiter(s)": rec_display,
                "Job Ref No": j.get("job_reference_no", "N/A"),
                "Target Role & Client": f"💼 {title_name} ({comp_name})",
                "Openings": openings_val,
                "Active Pipeline": f"👥 {active_cnt} Active ({total_cand_cnt} Total)",
                "Stagnancy": delay_badge,
                "Recommended Action": action_suggest,
                "Last Activity": f"⏱️ {days_inactive} days ago" if days_inactive > 0 else "Today",
                "_days_num": days_inactive,
                "_openings": openings_val
            })

    if stagnant_jobs:
        df_stagnant_jobs = pd.DataFrame(stagnant_jobs).sort_values(by="_days_num", ascending=False).drop(columns=["_days_num", "_openings"])
        
        j_c1, j_c2, j_c3 = st.columns(3)
        j_c1.metric("🚨 Stagnant Jobs (>7d)", len(stagnant_jobs))
        crit_job_count = len([sj for sj in stagnant_jobs if "🔴" in sj["Stagnancy"]])
        j_c2.metric("🔴 Critical Delays (>14d)", crit_job_count)
        vacancies_at_risk = sum(sj["_openings"] for sj in stagnant_jobs)
        j_c3.metric("🎯 Total Vacancies at Risk", vacancies_at_risk)
        
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        st.dataframe(
            df_stagnant_jobs,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Job Ref No": st.column_config.TextColumn("Job Ref No", width="small"),
                "Target Role & Client": st.column_config.TextColumn("Target Role & Client", width="large"),
                "Openings": st.column_config.NumberColumn("Openings", format="%d", width="small"),
                "Active Pipeline": st.column_config.TextColumn("Pipeline", width="medium"),
                "Recommended Action": st.column_config.TextColumn("Action Required", width="large"),
                "Last Activity": st.column_config.TextColumn("Last Activity", width="medium")
            }
        )
    else:
        st.success("🌟 Outstanding! No open jobs are currently stagnant or delayed past 7 days.")


# ==========================
# USER WORKPLAN SECTION
# ==========================
st.divider()
st.markdown("### 📋 User Workplan")

if recruiter_filter != "All Recruiters":
    st.caption(f"Active job requirements and candidate pipeline breakdown for **{recruiter_filter}**.")
else:
    st.caption("Active job requirements assigned to you and their current candidate pipeline breakdown.")

current_user_id = st.session_state.get("user_id")
current_user_role = st.session_state.get("user_role")

# Determine job assignments based on role or selected recruiter filter
if recruiter_filter != "All Recruiters":
    target_rec_uid = recruiter_user_map.get(recruiter_filter)
    target_job_ids = rec_uid_to_job_ids.get(target_rec_uid, set()) | {c.get("job_id") for c in filtered_candidates if c.get("job_id")}
    workplan_jobs = [j for j in filtered_jobs if str(j.get("job_status") or "").strip().lower() == "open" and j.get("job_id") in target_job_ids]
elif current_user_role in ["Admin", "Developer", "Admin-Lite"]:
    workplan_jobs = [j for j in filtered_jobs if str(j.get("job_status") or "").strip().lower() == "open"]
else:
    assigned_job_ids = [a["job_id"] for a in job_assignments if a.get("user_id") == current_user_id]
    workplan_jobs = [j for j in filtered_jobs if str(j.get("job_status") or "").strip().lower() == "open" and j.get("job_id") in assigned_job_ids]

workplan_data = []

for job in workplan_jobs:
    j_id = job["job_id"]
    title_name = job_title_lookup.get(job.get("job_title_id"), "Unknown Title")
    company_name = company_lookup.get(job.get("company_id"), "Unknown Company")
    job_label = f"{job.get('job_reference_no', '')} | {title_name}"
    
    openings = int(job.get("openings", 1))

    # Recruiter display for this job
    rec_names = [recruiter_id_to_name[u] for u in job_id_to_rec_uids.get(j_id, set()) if u in recruiter_id_to_name]
    if recruiter_filter != "All Recruiters":
        rec_display = recruiter_filter
    else:
        rec_display = ", ".join(sorted(rec_names)) if rec_names else "Unassigned"

    # Filter candidate data per job
    job_cands = [c for c in filtered_candidates if c.get("job_id") == j_id]

    candidate_cnt = len(job_cands)
    shortlisted_cnt = 0
    interview_cnt = 0
    offer_released_cnt = 0
    offer_accepted_cnt = 0
    offer_rejected_cnt = 0
    joined_cnt = 0
    no_show_cnt = 0

    latest_date = None

    for c in job_cands:
        c_id = c.get("candidate_id")
        stage = c.get("current_stage")
        status = c.get("candidate_status")
        
        cand_offer = offer_map.get(c_id, {})
        off_status = cand_offer.get("offer_status") if cand_offer else None

        # Stage aggregations
        if stage == "Shortlisted" or status == "Shortlisted":
            shortlisted_cnt += 1

        if stage == "Interview":
            interview_cnt += 1

        # Offer & Joining aggregations
        effective_status = off_status or status
        
        if is_candidate_hired(c):
            joined_cnt += 1
        elif is_candidate_offer_released(c):
            offer_released_cnt += 1
        elif effective_status == "Offer Accepted":
            offer_accepted_cnt += 1
        elif effective_status == "Offer Rejected" or stage == "Offer Rejected":
            offer_rejected_cnt += 1
        elif effective_status == "No Show":
            no_show_cnt += 1

        # Track last activity date
        c_date = parse_date(c.get("created_on", ""))
        if c_date:
            if not latest_date or c_date > latest_date:
                latest_date = c_date

    workplan_data.append({
        "Recruiter": rec_display,
        "Job Requirement": job_label,
        "Company": company_name,
        "No Of Opening": openings,
        "Candidate": clean_zero(candidate_cnt),
        "Shortlisted": clean_zero(shortlisted_cnt),
        "In Interview": clean_zero(interview_cnt),
        "Offer Released": clean_zero(offer_released_cnt),
        "Offer Accepted": clean_zero(offer_accepted_cnt),
        "Offer Rejected": clean_zero(offer_rejected_cnt),
        "Joined": clean_zero(joined_cnt),
        "No Show": clean_zero(no_show_cnt),
        "Last Activity": latest_date.strftime("%Y-%m-%d") if latest_date else "-"
    })

workplan_df = pd.DataFrame(workplan_data)

if not workplan_df.empty:
    st.dataframe(
        workplan_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Recruiter": st.column_config.TextColumn("Recruiter", width="small"),
            "Job Requirement": st.column_config.TextColumn("Job Requirement", width="medium"),
            "Company": st.column_config.TextColumn("Company", width="small"),
            "No Of Opening": st.column_config.NumberColumn("No Of Opening", format="%d"),
            "Candidate": st.column_config.NumberColumn("Candidate", format="%d"),
            "Shortlisted": st.column_config.NumberColumn("Shortlisted", format="%d"),
            "In Interview": st.column_config.NumberColumn("In Interview", format="%d"),
            "Offer Released": st.column_config.NumberColumn("Offer Released", format="%d"),
            "Offer Accepted": st.column_config.NumberColumn("Offer Accepted", format="%d"),
            "Offer Rejected": st.column_config.NumberColumn("Offer Rejected", format="%d"),
            "Joined": st.column_config.NumberColumn("Joined", format="%d"),
            "No Show": st.column_config.NumberColumn("No Show", format="%d"),
            "Last Activity": st.column_config.TextColumn("Last Activity")
        }
    )
else:
    st.info("No active assigned jobs found.")