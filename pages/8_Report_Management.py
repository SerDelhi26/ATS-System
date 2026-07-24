import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date, datetime
from db import supabase
from common import show_logout
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
    show_logout()

st.markdown("# 📊 ATS Master Report")

# ==========================
# FUNCTIONS (CACHED)
# ==========================
# We use a short TTL so reports are relatively fresh, but won't crash the DB if 5 recruiters pull reports at once.
@st.cache_data(ttl=60)
def get_report_data():
    try:
        candidates = supabase.table("candidate_management").select("*").execute().data
        jobs = supabase.table("job_management").select("job_id, job_reference_no, job_title_id").execute().data
        job_titles = supabase.table("job_title_master").select("*").execute().data
        
        # We don't necessarily need the full interview/offer tables for the master report 
        # since candidate_management already holds the 'current_stage'. 
        # But if you need specific offer CTCs in the report, we fetch them here.
        offers = supabase.table("offer_management").select("candidate_id, offered_ctc").execute().data
        
        return candidates, jobs, job_titles, offers
    except Exception as e:
        st.error(f"Error loading report data : {e}")
        st.stop()

def parse_date(date_str):
    """Safely converts Supabase timestamps to clean YYYY-MM-DD format."""
    if not date_str:
        return ""
    try:
        # Supabase format: '2026-07-24T10:15:30.123Z' or similar
        clean_time = str(date_str).split(".")[0].split("+")[0].replace("Z", "")
        parsed = datetime.strptime(clean_time, "%Y-%m-%dT%H:%M:%S")
        return parsed.date()
    except:
        return ""

# ==========================
# LOAD DATA
# ==========================
candidates, jobs, job_titles, offers = get_report_data()

# ==========================
# LOOKUPS
# ==========================
job_title_lookup = {row["job_title_id"]: row["job_title_name"] for row in job_titles}

job_lookup = {}
job_options = ["All Jobs"]
for job in jobs:
    title = job_title_lookup.get(job["job_title_id"], "Unknown")
    label = f"{job['job_reference_no']} | {title}"
    job_lookup[job["job_id"]] = label
    job_options.append(label)

# If you want to include Offered CTC in the master report
offer_lookup = {row["candidate_id"]: row.get("offered_ctc", "") for row in offers}

# ==========================
# FILTERS UI
# ==========================
st.markdown("### 🔍 Filter Criteria")

col1, col2, col3, col4, col5 = st.columns(5)

recruiter_options = ["All Recruiters"]
recruiter_options.extend(
    sorted(list({row.get("created_by_name") for row in candidates if row.get("created_by_name")}))
)

status_options = [
    "All Stages", "New", "Screening", "Shortlisted", "Interview", "Selected", "Offer", "Joined", "Rejected"
]

with col1:
    from_date = st.date_input("📅 From Date", value=date.today().replace(day=1))
with col2:
    to_date = st.date_input("📅 To Date", value=date.today())
with col3:
    recruiter_filter = st.selectbox("👤 Recruiter", recruiter_options)
with col4:
    status_filter = st.selectbox("📌 Master Stage", status_options)
with col5:
    job_filter = st.selectbox("💼 Job", job_options)

st.divider()

# ==========================
# BUILD REPORT
# ==========================
report_rows = []

for candidate in candidates:
    
    # 1. Parse the created date for accurate filtering
    raw_date = candidate.get("created_at", "")
    parsed_date = parse_date(raw_date)
    
    # Skip if we couldn't parse the date (failsafe)
    if not parsed_date:
        continue

    # 2. DATE FILTER LOGIC (Fixed!)
    if parsed_date < from_date or parsed_date > to_date:
        continue

    # 3. RECRUITER FILTER
    if recruiter_filter != "All Recruiters" and candidate.get("created_by_name") != recruiter_filter:
        continue

    # 4. STATUS FILTER (Using current_stage instead of just candidate_status)
    master_stage = candidate.get("current_stage", "Unknown")
    if status_filter != "All Stages" and master_stage != status_filter:
        continue

    # 5. JOB FILTER
    job_label = job_lookup.get(candidate.get("job_id"), "Unknown Job")
    if job_filter != "All Jobs" and job_label != job_filter:
        continue

    # Build the flat row for Excel/Dataframe
    row = {
        "Date Added": parsed_date.strftime("%Y-%m-%d"),
        "Candidate No": candidate.get("candidate_reference_no", ""),
        "Candidate Name": f"{candidate.get('first_name','')} {candidate.get('last_name','')}".strip(),
        "Job": job_label,
        "Recruiter": candidate.get("created_by_name", ""),
        "Email": candidate.get("email", ""),
        "Mobile": candidate.get("mobile_no", ""),
        "Experience": f"{candidate.get('experience_years',0)}Y {candidate.get('experience_months',0)}M",
        "Current Company": candidate.get("current_company", ""),
        "Current Designation": candidate.get("current_designation", ""),
        "Current CTC": float(candidate.get("current_ctc", 0.0)),
        "Expected CTC": float(candidate.get("expected_ctc", 0.0)),
        "Offered CTC": float(offer_lookup.get(candidate.get("candidate_id"), 0.0)),
        "Master Stage": master_stage
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
        # Generate Excel in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            report_df.to_excel(writer, index=False, sheet_name="ATS Report")
        excel_data = output.getvalue()
        
        # Add a bit of top margin so the button aligns nicely with the metric
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.download_button(
            label="📥 Download Excel Report",
            data=excel_data,
            file_name=f"ATS_Master_Report_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )


st.markdown("### 📋 Report Preview")

if not report_df.empty:
    # Use st.dataframe with Column Configuration for a beautiful UI
    st.dataframe(
        report_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date Added": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "Candidate No": st.column_config.TextColumn("CAN No"),
            "Candidate Name": st.column_config.TextColumn("Name"),
            "Job": st.column_config.TextColumn("Job Applied", width="medium"),
            "Email": st.column_config.TextColumn("Email", width="medium"),
            "Current CTC": st.column_config.NumberColumn("Current CTC", format="%.2f"),
            "Expected CTC": st.column_config.NumberColumn("Expected CTC", format="%.2f"),
            "Offered CTC": st.column_config.NumberColumn("Offered CTC", format="%.2f"),
            "Master Stage": st.column_config.TextColumn("Stage")
        }
    )
else:
    st.warning("No records found for the selected filters.")