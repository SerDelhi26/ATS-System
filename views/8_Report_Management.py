import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date, datetime
from db import supabase
from common import show_logout, show_job_notifications, show_user_profile
from theme import apply_theme

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
    page_title="ATS Reports",
    layout="wide"
)

apply_theme()

with st.sidebar:
    show_user_profile()
    show_logout()
    show_job_notifications()

st.markdown("# 📊 ATS Master Report")

# ==========================
# OPTIMIZED FUNCTIONS (Targeted Columns)
# ==========================
def get_report_data():
    try:
        # Fetch only necessary columns to keep network payloads lightweight
        candidates = supabase.table("candidate_management").select("candidate_id, candidate_reference_no, first_name, last_name, job_id, created_by_name, email, mobile_no, experience_years, experience_months, current_stage, created_on").execute().data
        jobs = supabase.table("job_management").select("job_id, job_reference_no, job_title_id").execute().data
        job_titles = supabase.table("job_title_master").select("job_title_id, job_title_name").execute().data
        interviews = supabase.table("interview_management").select("candidate_id, interview_round, interview_status, interview_date").execute().data
        offers = supabase.table("offer_management").select("candidate_id, offer_status, offered_ctc, joining_date").execute().data
        
        return candidates, jobs, job_titles, interviews, offers
    except Exception as e:
        st.error(f"Error loading report data: {e}")
        return [], [], [], [], []

def parse_date(date_str):
    if not date_str:
        return None
    try:
        clean_time = str(date_str).split(".")[0].split("+")[0].replace("Z", "")
        parsed = datetime.strptime(clean_time, "%Y-%m-%dT%H:%M:%S")
        return parsed.date()
    except:
        return None

# ==========================
# LOAD DATA
# ==========================
candidates, jobs, job_titles, interviews, offers = get_report_data()

if candidates:
    st.caption(f"Total candidates in database: {len(candidates)}")
else:
    st.warning("No candidate data found in the database. Please check your Supabase connection.")

# ==========================
# LOOKUPS & MAPPINGS
# ==========================
job_title_lookup = {row["job_title_id"]: row["job_title_name"] for row in job_titles}

job_lookup = {}
job_options = ["All Jobs"]
for job in jobs:
    title = job_title_lookup.get(job["job_title_id"], "Unknown")
    label = f"{job['job_reference_no']} | {title}"
    job_lookup[job["job_id"]] = label
    job_options.append(label)

# Group interviews by candidate_id
interview_map = {}
for inv in interviews:
    cid = inv.get("candidate_id")
    if cid:
        if cid not in interview_map:
            interview_map[cid] = []
        interview_map[cid].append(inv)

# Map offers by candidate_id
offer_map = {}
for off in offers:
    cid = off.get("candidate_id")
    if cid:
        offer_map[cid] = off

# ==========================
# FILTERS UI
# ==========================
st.markdown("### 🔍 Filter Criteria")

col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 2, 1])

recruiter_options = ["All Recruiters"]
recruiter_options.extend(
    sorted(list({row.get("created_by_name") for row in candidates if row.get("created_by_name")}))
)

status_options = [
    "All Stages", "New", "Screening", "Shortlisted", "Interview", "Selected", "Offer", "Joined", "Rejected"
]

with col1:
    use_date_filter = st.checkbox("📅 Enable Date Filter", value=True)
with col2:
    from_date = st.date_input("From Date", value=date(2026, 1, 1), disabled=not use_date_filter)
with col3:
    to_date = st.date_input("To Date", value=date.today(), disabled=not use_date_filter)
with col4:
    recruiter_filter = st.selectbox("👤 Recruiter", recruiter_options)
with col5:
    status_filter = st.selectbox("📌 Stage", status_options)
with col6:
    job_filter = st.selectbox("💼 Job", job_options)

st.divider()

# ==========================
# BUILD REPORT
# ==========================
report_rows = []

for candidate in candidates:
    candidate_id = candidate.get("candidate_id")
    parsed_date = parse_date(candidate.get("created_on", ""))
    
    if use_date_filter:
        if not parsed_date or parsed_date < from_date or parsed_date > to_date:
            continue

    if recruiter_filter != "All Recruiters" and candidate.get("created_by_name") != recruiter_filter:
        continue

    master_stage = candidate.get("current_stage", "Unknown")
    if status_filter != "All Stages" and master_stage != status_filter:
        continue

    job_label = job_lookup.get(candidate.get("job_id"), "Unknown Job")
    if job_filter != "All Jobs" and job_label != job_filter:
        continue

    # Compile Interview Details
    cand_interviews = interview_map.get(candidate_id, [])
    interview_history_list = []
    for inv in cand_interviews:
        round_name = inv.get("interview_round", "Round")
        inv_status = inv.get("interview_status", "N/A")
        inv_date = inv.get("interview_date", "N/A")
        interview_history_list.append(f"{round_name}: {inv_status} ({inv_date})")
    
    interview_history_str = " | ".join(interview_history_list) if interview_history_list else "No Interviews"

    # Compile Offer Details
    cand_offer = offer_map.get(candidate_id)
    if cand_offer:
        offer_status = cand_offer.get("offer_status", "N/A")
        offered_ctc = cand_offer.get("offered_ctc", "N/A")
        joining_date = cand_offer.get("joining_date", "N/A")
        offer_details_str = f"Status: {offer_status} | CTC: {offered_ctc} | Joining: {joining_date}"
    else:
        offer_details_str = "No Offer"

    row = {
        "Date Added": parsed_date.strftime("%Y-%m-%d") if parsed_date else "N/A",
        "Candidate No": candidate.get("candidate_reference_no", ""),
        "Candidate Name": f"{candidate.get('first_name','')} {candidate.get('last_name','')}".strip(),
        "Job": job_label,
        "Recruiter": candidate.get("created_by_name", ""),
        "Email": candidate.get("email", ""),
        "Mobile": candidate.get("mobile_no", ""),
        "Experience": f"{candidate.get('experience_years',0)}Y {candidate.get('experience_months',0)}M",
        "Master Stage": master_stage,
        "Interview History": interview_history_str,
        "Offer Details": offer_details_str
    }
    report_rows.append(row)

# ==========================
# DATAFRAME & DISPLAY
# ==========================
report_df = pd.DataFrame(report_rows)

colA, colB = st.columns([1, 4])
with colA:
    st.metric("Total Records Found", len(report_df))

with colB:
    if not report_df.empty:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            report_df.to_excel(writer, index=False, sheet_name="ATS Report")
        
        output.seek(0)
        excel_data = output.getvalue()
        
        st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
        st.download_button(
            label="📥 Download Excel Report",
            data=excel_data,
            file_name=f"ATS_Master_Report_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

st.markdown("### 📋 Report Preview")

if not report_df.empty:
    st.dataframe(
        report_df,
        use_container_width=True,
        hide_index=True
    )
else:
    st.warning("No records found for the selected filters.")