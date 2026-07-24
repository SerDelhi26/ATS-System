import streamlit as st
from db import supabase
from common import show_logout
from datetime import date
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
    page_title="Interview Management",
    layout="wide"
)

apply_theme()

with st.sidebar:

    show_logout()

st.markdown(
    "# 📅 ATS Interview Management"
)

# ==========================
# FUNCTIONS
# ==========================

@st.cache_data(ttl=300)
def get_candidates_for_interview():

    return (
        supabase
        .table("candidate_management")
        .select(
            """
            candidate_id,
            candidate_reference_no,
            first_name,
            last_name,
            job_id,
            current_stage,
            candidate_status
            """
        )
        .or_(
            "candidate_status.eq.Shortlisted,current_stage.eq.Interview,current_stage.eq.Shortlisted"
        )
        .execute()
        .data
    )


@st.cache_data(ttl=3600)
def get_job_titles():

    return (
        supabase
        .table("job_title_master")
        .select("*")
        .execute()
        .data
    )


@st.cache_data(ttl=300)
def get_jobs():

    return (
        supabase
        .table("job_management")
        .select(
            """
            job_id,
            job_reference_no,
            job_title_id
            """
        )
        .execute()
        .data
    )

@st.cache_data(ttl=300)
def get_candidate_lookup():

    return (
        supabase
        .table("candidate_management")
        .select(
            """
            candidate_id,
            candidate_reference_no,
            first_name,
            last_name
            """
        )
        .execute()
        .data
    )

def update_candidate_stage(
    candidate_id,
    interview_status
):

    response = (
        supabase
        .table("candidate_management")
        .select("current_stage")
        .eq(
            "candidate_id",
            candidate_id
        )
        .single()
        .execute()
    )

    current_stage = (
        response.data["current_stage"]
    )

    # Do not allow rollback
    if current_stage in [
        "Selected",
        "Rejected"
    ]:

        return

    if interview_status in [
        "Scheduled",
        "Completed",
        "Rescheduled",
        "On Hold"
    ]:

        stage = "Interview"

    elif interview_status == "Selected":

        stage = "Selected"

    elif interview_status == "Rejected":

        stage = "Rejected"

    else:

        stage = "Interview"

    (
        supabase
        .table("candidate_management")
        .update({
            "current_stage": stage
        })
        .eq(
            "candidate_id",
            candidate_id
        )
        .execute()
    )


def get_interview_by_id(
    interview_id
):

    result = (
        supabase
        .table("interview_management")
        .select("*")
        .eq(
            "interview_id",
            interview_id
        )
        .single()
        .execute()
    )

    return result.data


# ==========================
# MASTER LOOKUPS
# ==========================

job_titles = get_job_titles()

job_title_lookup = {

    item["job_title_id"]:
    item["job_title_name"]

    for item in job_titles

}

jobs = get_jobs()

job_display_lookup = {

    job["job_id"]:
    f"{job['job_reference_no']} | "
    f"{job_title_lookup.get(job['job_title_id'], '')}"

    for job in jobs

}


# ==========================
# SESSION VARIABLES
# ==========================

if "edit_interview_id" not in st.session_state:

    st.session_state.edit_interview_id = None

if "form_reset_interview" not in st.session_state:

    st.session_state.form_reset_interview = 0


# ==========================
# EDIT MODE
# ==========================

editing = False

interview = None

if st.session_state.edit_interview_id:

    interview = get_interview_by_id(
        st.session_state.edit_interview_id
    )

    if interview:

        editing = True

    else:

        st.session_state.edit_interview_id = None

        st.rerun()


# ==========================
# DROPDOWN VALUES
# ==========================

interview_mode_options = [
    "-- Select Mode --",
    "MS Teams",
    "Google Meet",
    "Zoom",
    "Telephonic",
    "Face To Face"
]

interview_status_options = [
    "-- Select Interview Status --",
    "Scheduled",
    "Completed",
    "Rescheduled",
    "On Hold",
    "Selected",
    "Rejected"
]


# ==========================
# LAYOUT
# ==========================

left_col, right_col = st.columns(
    [1, 3]
)

# ==========================
# LEFT PANEL
# ==========================

with left_col:

    # Helper function to generate safe, dynamic keys for resetting
    def get_key(base_name):
        if editing:
            return f"{base_name}_{interview['interview_id']}"
        return f"{base_name}_new_{st.session_state.form_reset_interview}"

    st.markdown(
        "## ✏️ Edit Interview"
        if editing
        else
        "## 📅 Schedule Interview"
    )

    candidates = get_candidates_for_interview()

    candidate_lookup = {}

    candidate_options = [
        "-- Select Candidate --"
    ]

    selected_candidate_label = (
        "-- Select Candidate --"
    )

    for c in candidates:

        full_name = (
            f"{c['first_name']} "
            f"{c['last_name']}"
        ).strip()

        label = (
            f"{c['candidate_reference_no']} | "
            f"{full_name}"
        )

        candidate_options.append(
            label
        )

        candidate_lookup[label] = c

        if (
            editing
            and
            c["candidate_id"]
            == interview["candidate_id"]
        ):

            selected_candidate_label = (
                label
            )

    selected_candidate = st.selectbox(
        "Candidate *",
        candidate_options,
        index=candidate_options.index(
            selected_candidate_label
        ),
        key=get_key("candidate")
    )

    selected_job_display = ""

    selected_job_id = None

    selected_candidate_id = None

    if (
        selected_candidate
        != "-- Select Candidate --"
    ):

        selected_candidate_record = (
            candidate_lookup[
                selected_candidate
            ]
        )

        selected_candidate_id = (
            selected_candidate_record[
                "candidate_id"
            ]
        )

        selected_job_id = (
            selected_candidate_record[
                "job_id"
            ]
        )

        selected_job_display = (
            job_display_lookup.get(
                selected_job_id,
                ""
            )
        )

    st.text_input(
        "Job",
        value=selected_job_display,
        disabled=True,
        key=get_key("job_display")
    )

    st.markdown(
        "### 🎯 Interview Details"
    )

    interview_round = st.text_input(
        "Interview Round *",
        value=(
            interview["interview_round"]
            if editing
            else ""
        ),
        placeholder="-- Enter Round --",
        key=get_key("round")
    )

    interview_date = st.date_input(
        "Interview Date *",
        value=(
            datetime.strptime(interview["interview_date"], "%Y-%m-%d").date()
            if editing and isinstance(interview["interview_date"], str)
            else interview["interview_date"]
            if editing
            else date.today()
        ),
        key=get_key("date")
    )

    time_options = [

        "-- Select Time --",
        
        "08:00",
        "08:30",

        "09:00",
        "09:30",

        "10:00",
        "10:30",

        "11:00",
        "11:30",

        "12:00",
        "12:30",

        "13:00",
        "13:30",

        "14:00",
        "14:30",

        "15:00",
        "15:30",

        "16:00",
        "16:30",

        "17:00",
        "17:30",

        "18:00"

    ]

    interview_time = st.selectbox(
        "Interview Time *",
        time_options,
        index=(
            time_options.index(
                str(
                    interview["interview_time"]
                )[:5]
            )
            if editing
            and interview["interview_time"]
            and str(interview["interview_time"])[:5]
            in time_options
            else 0
        ),
        key=get_key("time")
    )

    interviewer_name = st.text_input(
        "Interviewer Name",
        value=(
            interview["interviewer_name"]
            if editing
            else ""
        ),
        key=get_key("interviewer")
    )

    interview_mode = st.selectbox(
        "Interview Mode *",
        interview_mode_options,
        index=(
            interview_mode_options.index(
                interview["interview_mode"]
            )
            if editing
            and interview["interview_mode"]
            in interview_mode_options
            else 0
        ),
        key=get_key("mode")
    )

    interview_status = st.selectbox(
        "Interview Status *",
        interview_status_options,
        index=(
            interview_status_options.index(
                interview["interview_status"]
            )
            if editing
            and interview["interview_status"]
            in interview_status_options
            else 0
        ),
        key=get_key("status")
    )

    st.markdown(
        "### 📝 Feedback & Remarks"
    )

    feedback = st.text_area(
        "Feedback",
        value=(
            interview["feedback"]
            if editing
            and interview["feedback"]
            else ""
        ),
        height=100,
        key=get_key("feedback")
    )

    remarks = st.text_area(
        "Remarks",
        value=(
            interview["remarks"]
            if editing
            and interview["remarks"]
            else ""
        ),
        height=100,
        key=get_key("remarks")
    )

    # ----------------------
    # BUTTONS
    # ----------------------

    if editing:

        btn1, btn2 = st.columns(2)

        update_clicked = btn1.button(
            "Update Interview",
            use_container_width=True
        )

        cancel_clicked = btn2.button(
            "❌ Cancel Edit",
            use_container_width=True
        )

    else:

        update_clicked = st.button(
            "Schedule Interview",
            use_container_width=True
        )

        cancel_clicked = False

    if cancel_clicked:

        st.session_state.edit_interview_id = None

        st.session_state.form_reset_interview += 1

        st.rerun()

    # ----------------------
    # SAVE / UPDATE
    # ----------------------

    if update_clicked:

        validation_errors = []

        if not interview_round.strip():

            validation_errors.append(
                "Please enter Interview Round."
            )

        if interview_time == "-- Select Time --":

            validation_errors.append(
                "Please select Interview Time."
            )

        if interview_mode == "-- Select Mode --":

            validation_errors.append(
                "Please select Interview Mode."
            )

        if interview_status == "-- Select Interview Status --":

            validation_errors.append(
                "Please select Interview Status."
            )

        if (
            selected_candidate
            ==
            "-- Select Candidate --"
        ):

            validation_errors.append(
                "Please select Candidate."
            )

        if validation_errors:

            for error in validation_errors:

                st.error(error)

        else:

            interview_data = {

                "candidate_id":
                selected_candidate_id,

                "job_id":
                selected_job_id,

                "interview_round":
                interview_round,

                "interview_date":
                str(interview_date),

                "interview_time":
                str(interview_time),

                "interviewer_name":
                interviewer_name.strip(),

                "interview_mode":
                interview_mode,

                "interview_status":
                interview_status,

                "feedback":
                feedback.strip(),

                "remarks":
                remarks.strip(),

                "created_by_user_id":
                st.session_state.user_id,

                "created_by_name":
                st.session_state.user_name

            }

            try:

                if editing:

                    (
                        supabase
                        .table(
                            "interview_management"
                        )
                        .update(
                            interview_data
                        )
                        .eq(
                            "interview_id",
                            interview[
                                "interview_id"
                            ]
                        )
                        .execute()
                    )

                    update_candidate_stage(
                        selected_candidate_id,
                        interview_status
                    )

                    # Performance Fix 1: Specific cache clear instead of global clear
                    get_candidates_for_interview.clear()

                    st.success(
                        "Interview Updated Successfully."
                    )

                    st.session_state.edit_interview_id = None

                else:

                    (
                        supabase
                        .table(
                            "interview_management"
                        )
                        .insert(
                            interview_data
                        )
                        .execute()
                    )

                    update_candidate_stage(
                        selected_candidate_id,
                        interview_status
                    )

                    # Performance Fix 1: Specific cache clear instead of global clear
                    get_candidates_for_interview.clear()

                    st.success(
                        "Interview Scheduled Successfully."
                    )

                st.session_state.form_reset_interview += 1
                
                st.rerun()

            except Exception as e:

                st.error(
                    str(e)
                )
# ==========================
# RIGHT PANEL
# ==========================

with right_col:

    st.markdown(
        "## 📋 Interview Directory"
    )

    # --------------------------
    # INTERVIEW DATA
    # --------------------------

    # Performance Fix 2: Limit the database query to 500 records to prevent RAM overload
    result = (
        supabase
        .table("interview_management")
        .select("*")
        .order(
            "interview_id",
            desc=True
        )
        .limit(500)
        .execute()
    )

    interviews = result.data

    filter_col1, filter_col2 = st.columns(2)

    with filter_col1:

        status_filter = st.selectbox(
            "Status",
            [
                "All Status",
                "Scheduled",
                "Completed",
                "Rescheduled",
                "On Hold",
                "Selected",
                "Rejected"
            ]
        )

    with filter_col2:

        all_rounds = sorted(
            list(
                {
                    item["interview_round"]
                    for item in interviews
                    if item["interview_round"]
                }
            )
        )

        round_filter = st.selectbox(
            "Interview Round",
            ["All Rounds"] + all_rounds
        )

    search_text = st.text_input(
        "🔍 Search Interview",
        placeholder=
        "Candidate, CAN No, Job No or Interviewer"
    )

    # --------------------------
    # CANDIDATE LOOKUP
    # --------------------------

    all_candidates = get_candidate_lookup()

    candidate_lookup = {

        candidate["candidate_id"]:

        f"{candidate['candidate_reference_no']} | "
        f"{candidate['first_name']} "
        f"{candidate['last_name']}"

        for candidate in all_candidates

    }

    # --------------------------
    # STATUS FILTER
    # --------------------------

    if status_filter != "All Status":

        interviews = [

            item

            for item in interviews

            if item["interview_status"]
            == status_filter

        ]

    # --------------------------
    # ROUND FILTER
    # --------------------------

    if round_filter != "All Rounds":

        interviews = [

            item

            for item in interviews

            if item["interview_round"]
            == round_filter

        ]

    # --------------------------
    # SEARCH
    # --------------------------

    if search_text:

        filtered = []

        for item in interviews:

            candidate_name = (
                candidate_lookup.get(
                    item["candidate_id"],
                    ""
                )
            )

            job_name = (
                job_display_lookup.get(
                    item["job_id"],
                    ""
                )
            )

            searchable_text = (

                candidate_name
                + " "
                + job_name
                + " "
                + str(
                    item.get(
                        "interviewer_name",
                        ""
                    )
                )

            )

            if (

                search_text.lower()

                in

                searchable_text.lower()

            ):

                filtered.append(
                    item
                )

        interviews = filtered

    # --------------------------
    # GRID
    # --------------------------

    if interviews:

        # Performance Fix 3: Limit UI rendering to 25 items to stop Streamlit from freezing
        display_interviews = interviews[:25]
        if len(interviews) > 25:
            st.caption(f"⚠️ Showing top 25 of {len(interviews)} results to maintain performance. Use the search bar to find specific records.")

        header = st.columns(
            [3, 3, 2, 2, 2, 3, 1]
        )

        header[0].markdown(
            "**Candidate**"
        )

        header[1].markdown(
            "**Job**"
        )

        header[2].markdown(
            "**Round**"
        )

        header[3].markdown(
            "**Date**"
        )

        header[4].markdown(
            "**Interviewer**"
        )

        header[5].markdown(
            "**Status**"
        )

        header[6].markdown(
            "**Edit**"
        )

        st.divider()

        # Iterate over the sliced list instead of the full list
        for item in display_interviews:

            cols = st.columns(
                [3, 3, 2, 2, 2, 3, 1]
            )

            cols[0].write(

                candidate_lookup.get(
                    item["candidate_id"],
                    ""
                )

            )

            cols[1].write(

                job_display_lookup.get(
                    item["job_id"],
                    ""
                )

            )

            cols[2].write(
                item["interview_round"]
            )

            cols[3].write(
                item["interview_date"]
            )

            cols[4].write(
                item["interviewer_name"]
                if item["interviewer_name"]
                else "-"
            )

            status = item["interview_status"]

            status_colors = {

                "Scheduled": "#2563EB",
                "Completed": "#16A34A",
                "Rescheduled": "#F59E0B",
                "On Hold": "#EAB308",
                "Selected": "#22C55E",
                "Rejected": "#DC2626"

            }

            color = status_colors.get(
                status,
                "#64748B"
            )

            cols[5].markdown(
                f"""
                <div style="
                background:{color};
                color:white;
                padding:6px 12px;
                border-radius:10px;
                display:inline-block;
                white-space:nowrap;
                ">
                {status}
                </div>
                """,
                unsafe_allow_html=True
            )

            if cols[6].button(
                "✏️",
                key=f"edit_{item['interview_id']}"
            ):

                st.session_state.edit_interview_id = (
                    item["interview_id"]
                )

                st.rerun()

    else:

        st.info(
            "No interviews found."
        )