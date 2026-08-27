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
@st.cache_data(ttl=15)
def get_dashboard_data():
    jobs = supabase.table("job_management").select("job_id, job_reference_no, job_status, openings, company_id, job_title_id, created_date, created_by").execute().data or []
    candidates = supabase.table("candidate_management").select("candidate_id, candidate_reference_no, first_name, last_name, job_id, current_stage, candidate_status, created_by_name, created_on, updated_on, mobile_no, email, current_company, current_designation, experience_years, experience_months, current_ctc, expected_ctc, notice_period, remarks").execute().data or []
    interviews = supabase.table("interview_management").select("interview_id, candidate_id, job_id, interview_round, interview_date, interview_status, feedback, created_by_name, created_on").execute().data or []
    offers = supabase.table("offer_management").select("offer_id, candidate_id, job_id, offer_status, offered_ctc, joining_date, remarks, created_by_name, created_on").execute().data or []
    recruiters = supabase.table("users").select("user_id, full_name").eq("role", "Recruiter").execute().data or []
    job_titles = supabase.table("job_title_master").select("job_title_id, job_title_name").execute().data or []
    companies = supabase.table("company_master").select("company_id, company_name").execute().data or []
    job_assignments = supabase.table("job_assignment").select("job_id, user_id").execute().data or []
    
    return jobs, candidates, interviews, offers, recruiters, job_titles, companies, job_assignments

jobs, candidates, interviews, offers, recruiters, job_titles, companies, job_assignments = get_dashboard_data()

# Lookups
job_title_lookup = {item["job_title_id"]: item["job_title_name"] for item in job_titles}
company_lookup = {item["company_id"]: item["company_name"] for item in companies}
recruiter_user_map = {r["full_name"]: r["user_id"] for r in recruiters}
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
    clean_time = str(date_str).split(".")[0].split("+")[0].replace("Z", "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(clean_time, fmt).date()
        except Exception:
            pass
    return None

# Helper function to convert 0 to None for cleaner UI rendering in tables
def clean_zero(val):
    return val if val > 0 else None

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
# FILTER DATA ACROSS JOBS, CANDIDATES, INTERVIEWS & OFFERS
# ==========================
# 1. Filter Jobs
filtered_jobs = []
for j in jobs:
    job_created_date = parse_date(j.get("created_date"))
    if use_date_filter and job_created_date:
        if job_created_date < from_date or job_created_date > to_date:
            continue
    if job_filter != "All Jobs":
        selected_job_id = next((jid for jid, lbl in job_lookup.items() if lbl == job_filter), None)
        if j["job_id"] != selected_job_id:
            continue
    if recruiter_filter != "All Recruiters":
        rec_user_id = recruiter_user_map.get(recruiter_filter)
        assigned_job_ids = {ja["job_id"] for ja in job_assignments if ja.get("user_id") == rec_user_id}
        if j["job_id"] not in assigned_job_ids and j.get("created_by") != rec_user_id:
            continue
    filtered_jobs.append(j)

# 2. Filter Candidates
filtered_candidates = []
for c in candidates:
    parsed_date = parse_date(c.get("created_on", ""))
    if use_date_filter:
        if not parsed_date or parsed_date < from_date or parsed_date > to_date:
            continue
    if job_filter != "All Jobs":
        job_label = job_lookup.get(c.get("job_id"), "Unknown Job")
        if job_label != job_filter:
            continue
    if recruiter_filter != "All Recruiters":
        rec_user_id = recruiter_user_map.get(recruiter_filter)
        assigned_job_ids = {ja["job_id"] for ja in job_assignments if ja.get("user_id") == rec_user_id}
        if c.get("created_by_name") != recruiter_filter and c.get("job_id") not in assigned_job_ids:
            continue
    filtered_candidates.append(c)

filtered_candidate_ids = {c["candidate_id"] for c in filtered_candidates}
filtered_interviews = [i for i in interviews if i.get("candidate_id") in filtered_candidate_ids]
filtered_offers = [o for o in offers if o.get("candidate_id") in filtered_candidate_ids]

# ==========================
# TOP LEVEL METRICS (5 CARDS)
# ==========================
open_jobs = len([j for j in filtered_jobs if j.get("job_status") == "Open"])
total_candidates = len(filtered_candidates)
active_interviews = len(filtered_interviews)
offer_released_count = len([c for c in filtered_candidates if c.get("current_stage") in ["Offer", "Offer Released", "Offer Accepted", "Offer Rejected", "Joined", "Hired"] or c.get("candidate_status") in ["Offer", "Offer Released", "Offer Accepted", "Offer Rejected", "Joined", "Hired"]])
total_hired = len([c for c in filtered_candidates if c.get("current_stage") in ["Joined", "Hired"] or c.get("candidate_status") in ["Joined", "Hired"]])

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
        
    # Map performance by Candidate Creator (Ownership)
    r_cands = [c for c in filtered_candidates if c.get("created_by_name") == r_name]
    
    pipeline_total = len(r_cands)
    shortlisted = len([c for c in r_cands if c.get("current_stage") == "Shortlisted" or c.get("candidate_status") == "Shortlisted"])
    interviews_cnt = len([c for c in r_cands if c.get("current_stage") == "Interview"])
    offers_cnt = len([c for c in r_cands if c.get("current_stage") == "Offer" or c.get("candidate_status") in ["Offer Released", "Offer Accepted"]])
    hires = len([c for c in r_cands if c.get("current_stage") == "Joined" or c.get("candidate_status") in ["Joined", "Hired"]])
    
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

radar_tab1, radar_tab2, radar_tab3 = st.tabs([
    "👑 Ready for Offer",
    "⏳ Pending Acceptance & Joining",
    "🚨 Stagnant / At-Risk Talent (>7 Days)"
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
        
        cand_offer = offer_map.get(cid)
        off_status = (cand_offer.get("offer_status") or "").strip() if cand_offer else ""
        
        is_selected = (c_stage in ["Selected", "Final Round", "Shortlisted"] or c_status in ["Selected", "Shortlisted"] or has_selected_interview)
        is_not_offered_yet = off_status not in ["Offered", "Offer Released", "Offer Accepted", "Joined", "Hired"]
        is_not_rejected = c_status not in ["Rejected", "Offer Rejected", "Declined", "Cancelled", "Joined", "Hired"]
        
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
            
            ready_candidates.append({
                "Recruiter": c.get("created_by_name") or "Unassigned",
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
        is_not_joined = c_stage not in ["Joined", "Hired"] and c_status not in ["Joined", "Hired"]
        is_not_declined = off_status not in ["Offer Rejected", "Declined", "Revoked"] and c_status not in ["Offer Rejected", "Declined"]
        
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
            
            pending_offers.append({
                "Recruiter": c.get("created_by_name") or "Unassigned",
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
        is_not_terminal = c_status not in ["Rejected", "Joined", "Hired", "Offer Rejected", "Declined", "Cancelled"]
        
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
                    
                stagnant_candidates.append({
                    "Recruiter": c.get("created_by_name") or "Unassigned",
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
        stuck_recruiters = len(set(s["Recruiter"] for s in stagnant_candidates))
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