import streamlit as st
from common import show_logout
from db import supabase
import pandas as pd


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
    page_title="ATS Dashboard",
    layout="wide"
)

with st.sidebar:

    show_logout()

st.title("ATS Dashboard")

st.caption(
    f"Logged in as "
    f"{st.session_state.user_name}"
    f" ({st.session_state.user_role})"
)

# ==========================
# FUNCTIONS
# ==========================

@st.cache_data(ttl=300)
def get_jobs():

    return (
        supabase
        .table("job_management")
        .select("*")
        .execute()
        .data
    )

@st.cache_data(ttl=300)
def get_offers():

    return (
        supabase
        .table("offer_management")
        .select("*")
        .execute()
        .data
    )

@st.cache_data(ttl=300)
def get_candidates():

    return (
        supabase
        .table("candidate_management")
        .select("*")
        .execute()
        .data
    )


@st.cache_data(ttl=300)
def get_interviews():

    return (
        supabase
        .table("interview_management")
        .select("*")
        .execute()
        .data
    )


@st.cache_data(ttl=300)
def get_assignments():

    return (
        supabase
        .table("job_assignment")
        .select("*")
        .execute()
        .data
    )


@st.cache_data(ttl=300)
def get_users():

    return (
        supabase
        .table("users")
        .select("*")
        .eq("role", "Recruiter")
        .execute()
        .data
    )


@st.cache_data(ttl=300)
def get_job_titles():

    return (
        supabase
        .table("job_title_master")
        .select("*")
        .execute()
        .data
    )


# ==========================
# LOAD DATA
# ==========================

jobs = get_jobs()

candidates = get_candidates()

interviews = get_interviews()

offers = get_offers()

assignments = get_assignments()

recruiters = get_users()

job_titles = get_job_titles()

job_title_lookup = {

    item["job_title_id"]:
    item["job_title_name"]

    for item in job_titles

}

# ==========================
# SUMMARY METRICS
# ==========================

open_jobs = len(
    [
        job
        for job in jobs
        if job.get("job_status") == "Open"
    ]
)

candidate_count = len(
    candidates
)

shortlisted_count = len(
    [
        c
        for c in candidates
        if c.get("current_stage") == "Shortlisted"
    ]
)

interview_count = len(
    interviews
)

selected_count = len(
    [
        c
        for c in candidates
        if c.get("current_stage") == "Selected"
    ]
)

rejected_count = len(
    [
        c
        for c in candidates
        if c.get("current_stage") == "Rejected"
    ]
)

offer_count = len(

    [
        c

        for c in candidates

        if c.get("current_stage")
        == "Offer"

    ]

)

joined_count = len(

    [
        c

        for c in candidates

        if c.get("current_stage")
        == "Joined"

    ]

)

# ==========================
# SUMMARY CARDS
# ==========================

card1, card2, card3, card4 = st.columns(4)

card5, card6, card7, card8 = st.columns(4)

card1.metric(
    "Open Jobs",
    open_jobs
)

card2.metric(
    "Candidates",
    candidate_count
)

card3.metric(
    "Shortlisted",
    shortlisted_count
)

card4.metric(
    "Interviews",
    interview_count
)

card5.metric(
    "Selected",
    selected_count
)

card6.metric(
    "Offers",
    offer_count
)

card7.metric(
    "Joined",
    joined_count
)

card8.metric(
    "Rejected",
    rejected_count
)

# ==========================
# RECRUITER WORK SUMMARY
# ==========================

st.divider()

st.subheader(
    "Recruiter Work Summary"
)

summary_data = []

for recruiter in recruiters:

    recruiter_name = recruiter["full_name"]

    assigned_jobs = len(
        [
            a
            for a in assignments
            if a["user_id"]
            == recruiter["user_id"]
        ]
    )

    recruiter_candidates = [

        c

        for c in candidates

        if c.get("created_by_name")
        == recruiter_name

    ]

    recruiter_interviews = [

        i

        for i in interviews

        if i.get("created_by_name")
        == recruiter_name

    ]

    recruiter_offers = [

        o

        for o in offers

        if o.get("created_by_name")
        == recruiter_name

    ]

    selected_candidates = [

        c

        for c in recruiter_candidates

        if c.get("current_stage")
        == "Selected"

    ]

    joined_candidates = [

        c

        for c in recruiter_candidates

        if c.get("current_stage")
        == "Joined"

    ]

    summary_data.append({

        "Recruiter":
        recruiter_name,

        "Jobs":
        assigned_jobs,

        "Candidates":
        len(recruiter_candidates),

        "Interviews":
        len(recruiter_interviews),

        "Offers":
        len(recruiter_offers),

        "Selected":
        len(selected_candidates),

        "Joined":
        len(joined_candidates)

    })

summary_df = pd.DataFrame(
    summary_data
)

if not summary_df.empty:

    summary_df = summary_df.sort_values(
        by="Candidates",
        ascending=False
    )

st.dataframe(
    summary_df,
    use_container_width=True,
    hide_index=True
)

# ==========================
# CANDIDATE PIPELINE
# ==========================

st.divider()

st.subheader(
    "Candidate Pipeline"
)

pipeline_col1, pipeline_col2, \
pipeline_col3, pipeline_col4 = st.columns(4)

pipeline_col5, pipeline_col6, \
pipeline_col7, pipeline_col8 = st.columns(4)

pipeline_col1.metric(
    "New",
    len(
        [
            c
            for c in candidates
            if c.get("current_stage") == "New"
        ]
    )
)

pipeline_col2.metric(
    "Screening",
    len(
        [
            c
            for c in candidates
            if c.get("current_stage") == "Screening"
        ]
    )
)

pipeline_col3.metric(
    "Shortlisted",
    len(
        [
            c
            for c in candidates
            if c.get("current_stage") == "Shortlisted"
        ]
    )
)

pipeline_col4.metric(
    "Interview",
    len(
        [
            c
            for c in candidates
            if c.get("current_stage") == "Interview"
        ]
    )
)

pipeline_col5.metric(
    "Selected",
    len(
        [
            c
            for c in candidates
            if c.get("current_stage") == "Selected"
        ]
    )
)


pipeline_col6.metric(
    "Offer",
    len(
        [
            c
            for c in candidates
            if c.get("current_stage")
            == "Offer"
        ]
    )
)

pipeline_col7.metric(
    "Joined",
    len(
        [
            c
            for c in candidates
            if c.get("current_stage")
            == "Joined"
        ]
    )
)

pipeline_col8.metric(
    "Rejected",
    len(
        [
            c
            for c in candidates
            if c.get("current_stage")
            == "Rejected"
        ]
    )
)

# ==========================
# JOB SUMMARY
# ==========================

st.divider()

st.subheader(
    "Job Summary"
)

job_summary = []

for job in jobs:

    job_candidate_count = len(

        [
            c

            for c in candidates

            if c.get("job_id")
            == job["job_id"]

        ]

    )

    job_summary.append({

        "Job Number":
        job.get("job_reference_no"),

        "Job Title":
        job_title_lookup.get(
            job.get("job_title_id"),
            ""
        ),

        "Candidates":
        job_candidate_count,

        "Status":
        job.get("job_status")

    })

job_summary_df = pd.DataFrame(
    job_summary
)

if not job_summary_df.empty:

    job_summary_df = job_summary_df.sort_values(
        by="Candidates",
        ascending=False
    )

st.dataframe(
    job_summary_df,
    use_container_width=True,
    hide_index=True
)