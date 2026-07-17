import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date
from db import supabase
from common import show_logout
from theme import apply_theme

# ==========================
# LOGIN CHECK
# ==========================

if not st.session_state.get(
    "logged_in",
    False
):
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

st.markdown(
    "# 📊 ATS Master Report"
)

# ==========================
# LOAD DATA
# ==========================

try:

    candidates = (
        supabase
        .table("candidate_management")
        .select("*")
        .execute()
        .data
    )

    jobs = (
        supabase
        .table("job_management")
        .select("*")
        .execute()
        .data
    )

    interviews = (
        supabase
        .table("interview_management")
        .select("*")
        .execute()
        .data
    )

    offers = (
        supabase
        .table("offer_management")
        .select("*")
        .execute()
        .data
    )

except Exception as e:

    st.error(
        f"Error loading report data : {e}"
    )

    st.stop()

# ==========================
# LOOKUPS
# ==========================

job_lookup = {

    row["job_id"]: row

    for row in jobs

}

interview_lookup = {}

for row in interviews:

    candidate_id = row.get(
        "candidate_id"
    )

    if candidate_id:

        interview_lookup[
            candidate_id
        ] = row

offer_lookup = {}

for row in offers:

    candidate_id = row.get(
        "candidate_id"
    )

    if candidate_id:

        offer_lookup[
            candidate_id
        ] = row

# ==========================
# FILTERS
# ==========================

recruiter_options = [

    "All Recruiters"

]

recruiter_options.extend(

    sorted(

        list(

            {
                row.get(
                    "created_by_name",
                    ""
                )

                for row in candidates

                if row.get(
                    "created_by_name"
                )
            }

        )

    )

)

status_options = [

    "All Status",

    "New",
    "Screening",
    "Shortlisted",
    "Hold",
    "Rejected",
    "Selected",
    "Joined"

]

job_options = [

    "All Jobs"

]

job_lookup_filter = {}

for job in jobs:

    label = job.get(
        "job_reference_no",
        ""
    )

    job_options.append(
        label
    )

    job_lookup_filter[
        label
    ] = job["job_id"]

col1, col2, col3, col4, col5 = st.columns(5)

with col1:

    recruiter_filter = st.selectbox(
        "👤 Recruiter",
        recruiter_options
    )

with col2:

    from_date = st.date_input(
        "📅 From Date",
        value=date.today().replace(day=1)
    )

with col3:

    to_date = st.date_input(
        "📅 To Date",
        value=date.today()
    )

with col4:

    status_filter = st.selectbox(
        "📌 Candidate Status",
        status_options
    )

with col5:

    job_filter = st.selectbox(
        "💼 Job",
        job_options
    )

# ==========================
# BUILD REPORT
# ==========================

report_rows = []

for candidate in candidates:

    job = job_lookup.get(
        candidate.get("job_id"),
        {}
    )

    interview = interview_lookup.get(
        candidate.get(
            "candidate_id"
        ),
        {}
    )

    offer = offer_lookup.get(
        candidate.get(
            "candidate_id"
        ),
        {}
    )

    row = {

        "Candidate No":
            candidate.get(
                "candidate_reference_no",
                ""
            ),

        "Candidate Name":
            (
                f"{candidate.get('first_name','')} "
                f"{candidate.get('last_name','')}"
            ).strip(),

        "Job No":
            job.get(
                "job_reference_no",
                ""
            ),

        "Recruiter":
            candidate.get(
                "created_by_name",
                ""
            ),

        "Email":
            candidate.get(
                "email",
                ""
            ),

        "Mobile":
            candidate.get(
                "mobile_no",
                ""
            ),

        "Experience":
            (
                f"{candidate.get('experience_years',0)}Y "
                f"{candidate.get('experience_months',0)}M"
            ),

        "Current Company":
            candidate.get(
                "current_company",
                ""
            ),

        "Current Designation":
            candidate.get(
                "current_designation",
                ""
            ),

        "Candidate Status":
            candidate.get(
                "candidate_status",
                ""
            ),

        "Interview Status":
            interview.get(
                "interview_status",
                ""
            ),

        "Offer Status":
            offer.get(
                "offer_status",
                ""
            ),

        "Created Date":
            str(
                candidate.get(
                    "created_at",
                    ""
                )
            )

    }

    # ------------------
    # FILTERS
    # ------------------

    if (
        recruiter_filter
        !=
        "All Recruiters"
    ):

        if (
            row["Recruiter"]
            !=
            recruiter_filter
        ):

            continue

    if (
        status_filter
        !=
        "All Status"
    ):

        if (
            row["Candidate Status"]
            !=
            status_filter
        ):

            continue

    if (
        job_filter
        !=
        "All Jobs"
    ):

        if (
            row["Job No"]
            !=
            job_filter
        ):

            continue

    report_rows.append(
        row
    )

# ==========================
# DATAFRAME
# ==========================

report_df = pd.DataFrame(
    report_rows
)

st.info(
    f"📋 Total Records Found : {len(report_df)}"
)

# ==========================
# DOWNLOAD EXCEL
# ==========================

output = BytesIO()

with pd.ExcelWriter(
    output,
    engine="openpyxl"
) as writer:

    report_df.to_excel(
        writer,
        index=False,
        sheet_name="ATS Report"
    )

excel_data = output.getvalue()

download_col1, download_col2 = st.columns([1,5])

with download_col1:

    st.download_button(

    "📥 Download Excel",

    data=excel_data,

    file_name="ATS_Master_Report.xlsx",

    mime=
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

)

# ==========================
# REPORT TABLE
# ==========================
st.markdown(
    "## 📋 Report Results"
)

st.dataframe(

    report_df,

    use_container_width=True,

    hide_index=True

)