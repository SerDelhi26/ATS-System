import streamlit as st
from common import show_logout, show_job_notifications, show_user_profile
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
st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ==========================
# DATA FETCHING
# ==========================
def get_dashboard_data():
    jobs = supabase.table("job_management").select("job_id, job_reference_no, job_status, openings, company_id, job_title_id").execute().data
    candidates = supabase.table("candidate_management").select("candidate_id, candidate_reference_no, first_name, last_name, job_id, current_stage, candidate_status, created_by_name, created_on").execute().data
    interviews = supabase.table("interview_management").select("interview_id, candidate_id, interview_status, created_by_name").execute().data
    offers = supabase.table("offer_management").select("candidate_id, offer_status, offered_ctc").execute().data
    recruiters = supabase.table("users").select("user_id, full_name").eq("role", "Recruiter").execute().data
    job_titles = supabase.table("job_title_master").select("job_title_id, job_title_name").execute().data
    companies = supabase.table("company_master").select("company_id, company_name").execute().data
    job_assignments = supabase.table("job_assignment").select("job_id, user_id").execute().data
    
    return jobs, candidates, interviews, offers, recruiters, job_titles, companies, job_assignments

jobs, candidates, interviews, offers, recruiters, job_titles, companies, job_assignments = get_dashboard_data()

# Lookups
job_title_lookup = {item["job_title_id"]: item["job_title_name"] for item in job_titles}
company_lookup = {item["company_id"]: item["company_name"] for item in companies}
offer_map = {o["candidate_id"]: o for o in offers if o.get("candidate_id")}

job_lookup = {}
job_options = ["All Jobs"]
for job in jobs:
    title = job_title_lookup.get(job["job_title_id"], "Unknown")
    label = f"{job['job_reference_no']} | {title}"
    job_lookup[job["job_id"]] = label
    job_options.append(label)

def parse_date(date_str):
    if not date_str:
        return None
    try:
        clean_time = str(date_str).split(".")[0].split("+")[0].replace("Z", "")
        return datetime.strptime(clean_time, "%Y-%m-%dT%H:%M:%S").date()
    except:
        return None

# ==========================
# FILTERS UI
# ==========================
st.markdown("### 🔍 Dashboard Filters")

f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([1.5, 2, 2, 2, 2.5])

with f_col1:
    use_date_filter = st.checkbox("📅 Date Filter", value=False)
with f_col2:
    from_date = st.date_input("From Date", value=date(2026, 1, 1), disabled=not use_date_filter)
with f_col3:
    to_date = st.date_input("To Date", value=date.today(), disabled=not use_date_filter)
with f_col4:
    recruiter_options = ["All Recruiters"] + sorted(list({r["full_name"] for r in recruiters}))
    recruiter_filter = st.selectbox("👤 Recruiter", recruiter_options)
with f_col5:
    job_filter = st.selectbox("💼 Job", job_options)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ==========================
# FILTER CANDIDATES & RELATED DATA
# ==========================
filtered_candidates = []
for c in candidates:
    parsed_date = parse_date(c.get("created_on", ""))
    if use_date_filter:
        if not parsed_date or parsed_date < from_date or parsed_date > to_date:
            continue
    if recruiter_filter != "All Recruiters" and c.get("created_by_name") != recruiter_filter:
        continue
    job_label = job_lookup.get(c.get("job_id"), "Unknown Job")
    if job_filter != "All Jobs" and job_label != job_filter:
        continue
    filtered_candidates.append(c)

filtered_candidate_ids = {c["candidate_id"] for c in filtered_candidates}
filtered_interviews = [i for i in interviews if i.get("candidate_id") in filtered_candidate_ids]
filtered_offers = [o for o in offers if o.get("candidate_id") in filtered_candidate_ids]

# ==========================
# TOP LEVEL METRICS (5 CARDS)
# ==========================
open_jobs = len([j for j in jobs if j.get("job_status") == "Open"])
total_candidates = len(filtered_candidates)
active_interviews = len([i for i in filtered_interviews if i.get("interview_status") in ["Scheduled", "Rescheduled"]])
offer_released_count = len([c for c in filtered_candidates if c.get("current_stage") == "Offer"])
total_hired = len([c for c in filtered_candidates if c.get("current_stage") == "Joined"])

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
        stage = c.get("current_stage")
        if stage in pipeline_counts:
            pipeline_counts[stage] += 1
            
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
    for j in jobs:
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
st.caption("Overview of team productivity and pipeline conversion metrics.")

performance_data = []
for recruiter in recruiters:
    r_name = recruiter["full_name"]
    
    # Respect the global dropdown filter for recruiters
    if recruiter_filter != "All Recruiters" and r_name != recruiter_filter:
        continue
        
    r_cands = [c for c in filtered_candidates if c.get("created_by_name") == r_name]
    
    sourced = len(r_cands)
    shortlisted = len([c for c in r_cands if c.get("current_stage") == "Shortlisted" or c.get("candidate_status") == "Shortlisted"])
    interviews = len([c for c in r_cands if c.get("current_stage") == "Interview"])
    offers = len([c for c in r_cands if c.get("current_stage") == "Offer" or c.get("candidate_status") in ["Offer Released", "Offer Accepted"]])
    hires = len([c for c in r_cands if c.get("current_stage") == "Joined" or c.get("candidate_status") in ["Joined", "Hired"]])
    
    conversion = (hires / sourced * 100) if sourced > 0 else 0
    
    # Append to table (we keep 0s here because in performance tracking, a 0 is an important metric)
    if sourced > 0 or recruiter_filter == "All Recruiters":
        performance_data.append({
            "Recruiter": r_name,
            "Sourced": sourced,
            "Shortlisted": shortlisted,
            "In Interview": interviews,
            "Offered": offers,
            "Hired": hires,
            "Conversion Rate": conversion
        })

perf_df = pd.DataFrame(performance_data)

if not perf_df.empty:
    perf_df = perf_df.sort_values(by=["Hired", "Sourced"], ascending=[False, False])
    st.dataframe(
        perf_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Recruiter": st.column_config.TextColumn("Recruiter Name"),
            "Sourced": st.column_config.NumberColumn("Candidates Sourced"),
            "Shortlisted": st.column_config.NumberColumn("Shortlisted"),
            "In Interview": st.column_config.NumberColumn("In Interview"),
            "Offered": st.column_config.NumberColumn("Offered"),
            "Hired": st.column_config.NumberColumn("Total Hires"),
            "Conversion Rate": st.column_config.ProgressColumn(
                "Hire/Sourced %",
                format="%d%%",
                min_value=0,
                max_value=100
            )
        }
    )
else:
    st.info("No recruiter performance data found for the selected filters.")


# ==========================
# USER WORKPLAN SECTION
# ==========================
st.divider()
st.markdown("### 📋 User Workplan")
st.caption("Active job requirements assigned to you and their current candidate pipeline breakdown.")

current_user_id = st.session_state.get("user_id")
current_user_role = st.session_state.get("user_role")

# Determine job assignments based on role
assigned_job_ids = [a["job_id"] for a in job_assignments if a.get("user_id") == current_user_id]

if current_user_role == "Admin":
    workplan_jobs = [j for j in jobs if j.get("job_status") == "Open"]
else:
    workplan_jobs = [j for j in jobs if j.get("job_status") == "Open" and j.get("job_id") in assigned_job_ids]

workplan_data = []

# Helper function to convert 0 to None for cleaner UI rendering
def clean_zero(val):
    return val if val > 0 else None

for job in workplan_jobs:
    j_id = job["job_id"]
    title_name = job_title_lookup.get(job.get("job_title_id"), "Unknown Title")
    company_name = company_lookup.get(job.get("company_id"), "Unknown Company")
    job_label = f"{job.get('job_reference_no', '')} | {title_name}"
    
    openings = int(job.get("openings", 1))

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
        
        if effective_status == "Offer Released" or (stage == "Offer" and not off_status):
            offer_released_cnt += 1
        elif effective_status == "Offer Accepted":
            offer_accepted_cnt += 1
        elif effective_status == "Offer Rejected":
            offer_rejected_cnt += 1
        elif effective_status in ["Joined", "Hired"] or stage == "Joined":
            joined_cnt += 1
        elif effective_status == "No Show":
            no_show_cnt += 1

        # Track last activity date
        c_date = parse_date(c.get("created_on", ""))
        if c_date:
            if not latest_date or c_date > latest_date:
                latest_date = c_date

    workplan_data.append({
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