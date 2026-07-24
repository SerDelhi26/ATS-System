import streamlit as st
from common import show_logout
from db import supabase
import pandas as pd
import plotly.express as px
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
                <div style="color: #64748B; font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">
                    {title}
                </div>
                <div style="color: #0F172A; font-size: 28px; font-weight: bold; margin-top: 5px;">
                    {value}
                </div>
            </div>
            <div style="font-size: 32px; color: {color}; opacity: 0.8;">
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
    show_logout()

st.markdown("# 📊 ATS Analytics Dashboard")
st.caption(f"Welcome back, **{st.session_state.user_name}** ({st.session_state.user_role})")
st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ==========================
# DATA FETCHING (CACHED)
# ==========================
@st.cache_data(ttl=300)
def get_dashboard_data():
    jobs = supabase.table("job_management").select("*").execute().data
    candidates = supabase.table("candidate_management").select("*").execute().data
    interviews = supabase.table("interview_management").select("*").execute().data
    offers = supabase.table("offer_management").select("*").execute().data
    assignments = supabase.table("job_assignment").select("*").execute().data
    recruiters = supabase.table("users").select("*").eq("role", "Recruiter").execute().data
    job_titles = supabase.table("job_title_master").select("*").execute().data
    companies = supabase.table("company_master").select("*").execute().data
    
    return jobs, candidates, interviews, offers, assignments, recruiters, job_titles, companies

# Load all data
jobs, candidates, interviews, offers, assignments, recruiters, job_titles, companies = get_dashboard_data()

# Lookups
job_title_lookup = {item["job_title_id"]: item["job_title_name"] for item in job_titles}
company_lookup = {item["company_id"]: item["company_name"] for item in companies}


# ==========================
# TOP LEVEL METRICS
# ==========================
# Calculate Metrics
open_jobs = len([j for j in jobs if j.get("job_status") == "Open"])
total_candidates = len(candidates)
active_interviews = len([i for i in interviews if i.get("interview_status") in ["Scheduled", "Rescheduled"]])
total_hired = len([c for c in candidates if c.get("current_stage") == "Joined"])

col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card("Open Jobs", open_jobs, "💼", "#2563EB") # Blue
with col2:
    kpi_card("Total Candidates", total_candidates, "👥", "#8B5CF6") # Purple
with col3:
    kpi_card("Upcoming Interviews", active_interviews, "📅", "#F59E0B") # Orange
with col4:
    kpi_card("Total Hired", total_hired, "🎉", "#10B981") # Green

st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)

# ==========================
# CHARTS ROW
# ==========================
chart_col1, chart_col2 = st.columns([3, 2])

# 1. Candidate Pipeline Funnel Chart
with chart_col1:
    st.markdown("### 🎯 Recruitment Pipeline")
    
    stages = ["New", "Screening", "Shortlisted", "Interview", "Selected", "Offer", "Joined"]
    pipeline_counts = {stage: 0 for stage in stages}
    
    for c in candidates:
        stage = c.get("current_stage")
        if stage in pipeline_counts:
            pipeline_counts[stage] += 1
            
    funnel_df = pd.DataFrame({
        "Stage": list(pipeline_counts.keys()),
        "Count": list(pipeline_counts.values())
    })
    
    # Plotly Funnel Chart
    fig_funnel = px.funnel(
        funnel_df, 
        x='Count', 
        y='Stage',
        color_discrete_sequence=['#3B82F6']
    )
    fig_funnel.update_layout(margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_funnel, use_container_width=True)

# 2. Job Status Donut Chart
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
    
    fig_pie = px.pie(
        pie_df, 
        names='Status', 
        values='Count', 
        hole=0.5,
        color='Status',
        color_discrete_map=color_map
    )
    fig_pie.update_layout(margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor="rgba(0,0,0,0)", showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# ==========================
# TABLES ROW
# ==========================
table_col1, table_col2 = st.columns([1, 1])

# 1. Recruiter Leaderboard
with table_col1:
    st.markdown("### 🏆 Recruiter Leaderboard")
    
    summary_data = []
    for recruiter in recruiters:
        r_name = recruiter["full_name"]
        
        # Candidates entered by this recruiter
        r_candidates = [c for c in candidates if c.get("created_by_name") == r_name]
        
        summary_data.append({
            "Recruiter": r_name,
            "Sourced": len(r_candidates),
            "Interviews": len([i for i in interviews if i.get("created_by_name") == r_name]),
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
            "Sourced": st.column_config.NumberColumn("Candidates Sourced", help="Total candidates added to ATS"),
            "Interviews": st.column_config.NumberColumn("Interviews Logged"),
            "Hires": st.column_config.ProgressColumn(
                "Total Hires",
                help="Candidates who successfully joined",
                format="%d",
                min_value=0,
                max_value=max(summary_df["Hires"].max(), 1) if not summary_df.empty else 10
            )
        }
    )

# 2. Active Jobs Pipeline
with table_col2:
    st.markdown("### 🚀 Active Jobs Pipeline")
    
    job_summary = []
    for job in jobs:
        if job.get("job_status") != "Open":
            continue # Only show open jobs in the pipeline table
            
        j_id = job["job_id"]
        openings = int(job.get("openings", 1))
        
        # Count candidates for this job
        job_cands = [c for c in candidates if c.get("job_id") == j_id]
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
            "Candidates": st.column_config.NumberColumn("Pipeline", help="Total candidates in flow"),
            "Openings": st.column_config.NumberColumn("Target"),
            "Joined": st.column_config.NumberColumn("Hired"),
            "Fill Rate": st.column_config.ProgressColumn(
                "Fill Rate %",
                help="Percentage of openings filled",
                format="%d%%",
                min_value=0,
                max_value=100
            )
        }
    )