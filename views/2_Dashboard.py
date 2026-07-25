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
# DATA FETCHING (Selective Columns)
# ==========================
@st.cache_data(ttl=300)
def get_dashboard_data():
    jobs = supabase.table("job_management").select("job_id, job_reference_no, job_status, openings, company_id, job_title_id").execute().data
    candidates = supabase.table("candidate_management").select("candidate_id, candidate_reference_no, first_name, last_name, job_id, current_stage, candidate_status, created_by_name, created_on").execute().data
    interviews = supabase.table("interview_management").select("interview_id, candidate_id, interview_status, created_by_name").execute().data
    offers = supabase.table("offer_management").select("candidate_id, offer_status, offered_ctc").execute().data
    recruiters = supabase.table("users").select("user_id, full_name").eq("role", "Recruiter").execute().data
    job_titles = supabase.table("job_title_master").select("job_title_id, job_title_name").execute().data
    companies = supabase.table("company_master").select("company_id, company_name").execute().data
    
    return jobs, candidates, interviews, offers, recruiters, job_titles, companies

jobs, candidates, interviews, offers, recruiters, job_titles, companies = get_dashboard_data()

# Lookups
job_title_lookup = {item["job_title_id"]: item["job_title_name"] for item in job_titles}
company_lookup = {item["company_id"]: item["company_name"] for item in companies}

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

st.divider()

# ==========================
# TABLES ROW
# ==========================
table_col1, table_col2 = st.columns([1, 1])

with table_col1:
    st.markdown("### 🏆 Recruiter Leaderboard")
    summary_data = []
    for recruiter in recruiters:
        r_name = recruiter["full_name"]
        r_candidates = [c for c in filtered_candidates if c.get("created_by_name") == r_name]
        
        summary_data.append({
            "Recruiter": r_name,
            "Sourced": len(r_candidates),
            "Interviews": len([i for i in filtered_interviews if i.get("created_by_name") == r_name]),
            "Hires": len([c for c in r_candidates if c.get("current_stage") == "Joined"])
        })
        
    summary_df = pd.DataFrame(summary_data)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(by=["Hires", "Sourced"], ascending=[False, False])
        
    st.dataframe(
        summary_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Recruiter": st.column_config.TextColumn("Recruiter Name", width="medium"),
            "Sourced": st.column_config.NumberColumn("Candidates Sourced"),
            "Interviews": st.column_config.NumberColumn("Interviews Logged"),
            "Hires": st.column_config.ProgressColumn(
                "Total Hires",
                format="%d",
                min_value=0,
                max_value=max(summary_df["Hires"].max(), 1) if not summary_df.empty else 10
            )
        }
    )

with table_col2:
    st.markdown("### 🚀 Active Jobs Pipeline")
    job_summary = []
    for job in jobs:
        if job.get("job_status") != "Open":
            continue
            
        j_id = job["job_id"]
        openings = int(job.get("openings", 1))
        job_cands = [c for c in filtered_candidates if c.get("job_id") == j_id]
        joined_count = len([c for c in job_cands if c.get("current_stage") == "Joined"])
        
        company_name = company_lookup.get(job.get("company_id"), "Unknown")
        title_name = job_title_lookup.get(job.get("job_title_id"), "Unknown")
        
        job_summary.append({
            "Job": f"{job.get('job_reference_no')} | {title_name}",
            "Company": company_name,
            "Candidates": len(job_cands),
            "Openings": openings,
            "Joined": joined_count,
            "Fill Rate": min((joined_count / openings) * 100, 100) if openings > 0 else 0
        })

    job_summary_df = pd.DataFrame(job_summary)
    if not job_summary_df.empty:
        job_summary_df = job_summary_df.sort_values(by="Fill Rate", ascending=False)
        
    st.dataframe(
        job_summary_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Job": st.column_config.TextColumn("Job Requirement", width="medium"),
            "Company": st.column_config.TextColumn("Company"),
            "Candidates": st.column_config.NumberColumn("Pipeline"),
            "Openings": st.column_config.NumberColumn("Target"),
            "Joined": st.column_config.NumberColumn("Hired"),
            "Fill Rate": st.column_config.ProgressColumn("Fill Rate %", format="%d%%", min_value=0, max_value=100)
        }
    )

# ==========================
# KANBAN BOARD ROW
# ==========================
st.divider()

st.markdown("### 🧩 Pipeline Kanban Board")
st.caption("Visualizing active candidates. Use the filters at the top of the dashboard to drill down into specific jobs or recruiters.")

# 1. Define the core active stages you want to visualize
kanban_stages = ["New", "Screening", "Shortlisted", "Interview", "Offer"]

# 2. Create Streamlit columns dynamically based on the stages
k_cols = st.columns(len(kanban_stages))

# 3. Color mapping for the top border of cards to make them visually distinct
stage_colors = {
    "New": "#3B82F6",         # Blue
    "Screening": "#F59E0B",   # Orange
    "Shortlisted": "#8B5CF6", # Purple
    "Interview": "#EC4899",   # Pink
    "Offer": "#10B981"        # Green
}

for idx, stage in enumerate(kanban_stages):
    with k_cols[idx]:
        # Filter the already-fetched dashboard candidates for this specific stage
        stage_cands = [c for c in filtered_candidates if c.get("current_stage") == stage]
        
        # Draw Column Header with Count
        st.markdown(
            f"<div style='background-color: #F1F5F9; padding: 8px; border-radius: 6px; text-align: center; font-weight: bold; color: #334155; margin-bottom: 10px;'>"
            f"{stage} ({len(stage_cands)})"
            f"</div>", 
            unsafe_allow_html=True
        )
        
        # Draw Candidate Cards
        for c in stage_cands:
            full_name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            ref_no = c.get('candidate_reference_no', '')
            
            # Grab just the JR Number (e.g., JR-2026-0001) to keep the card compact
            job_ref_full = job_lookup.get(c.get('job_id'), 'Unknown Job')
            job_ref_short = job_ref_full.split(' | ')[0] 
            
            recruiter = c.get('created_by_name', '')
            color = stage_colors.get(stage, "#64748B")
            
            # Render the Custom HTML Card
            st.markdown(
                f"""
                <div style="
                    background-color: white; 
                    padding: 12px; 
                    border-radius: 8px; 
                    border-top: 4px solid {color}; 
                    margin-bottom: 12px; 
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                    border-left: 1px solid #E2E8F0;
                    border-right: 1px solid #E2E8F0;
                    border-bottom: 1px solid #E2E8F0;
                ">
                    <div style="color: #0F172A; font-size: 14px; font-weight: bold; margin-bottom: 4px;">{full_name}</div>
                    <div style="color: #64748B; font-size: 12px; margin-bottom: 2px;">📄 {ref_no}</div>
                    <div style="color: #64748B; font-size: 12px; margin-bottom: 2px;">💼 {job_ref_short}</div>
                    <div style="color: #94A3B8; font-size: 11px; margin-top: 6px; text-align: right;">👤 {recruiter}</div>
                </div>
                """, 
                unsafe_allow_html=True
            )