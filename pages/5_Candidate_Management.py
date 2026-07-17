import streamlit as st
import re
from datetime import datetime
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
    page_title="Candidate Management",
    layout="wide"
)

apply_theme()

with st.sidebar:

    show_logout()

st.markdown(
    "# 👤 ATS Candidate Management"
)


# ==========================
# FUNCTIONS
# ==========================
@st.cache_data(ttl=300)
def get_jobs_for_user(
    user_id,
    user_role
):

    if user_role == "Admin":

        return (
            supabase
            .table("job_management")
            .select(
                """
                job_id,
                job_reference_no,
                job_title_id,
                job_status
                """
            )
            .eq(
                "job_status",
                "Open"
            )
            .execute()
            .data
        )

    assignments = (
        supabase
        .table("job_assignment")
        .select("*")
        .eq(
            "user_id",
            user_id
        )
        .execute()
    )

    assigned_job_ids = [
        item["job_id"]
        for item in assignments.data
    ]

    if not assigned_job_ids:

        return []

    jobs = (
        supabase
        .table("job_management")
        .select(
            """
            job_id,
            job_reference_no,
            job_title_id,
            job_status
            """
        )
        .eq(
            "job_status",
            "Open"
        )
        .execute()
    )

    return [
        job
        for job in jobs.data
        if job["job_id"] in assigned_job_ids
    ]

def upload_resume(
    uploaded_file,
    file_name
):

    try:

        file_bytes = uploaded_file.getvalue()

        supabase.storage \
            .from_("Resume") \
            .upload(
                file_name,
                file_bytes
            )

        return file_name

    except Exception as e:

        st.error(
            f"Resume Upload Error: {str(e)}"
        )

        return None

def get_resume_url(file_path):

    try:

        response = (
            supabase.storage
            .from_("Resume")
            .create_signed_url(
                file_path,
                3600
            )
        )

        return response["signedURL"]

    except:

        return None

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
def get_recruiters():

    return (
        supabase
        .table("users")
        .select("full_name")
        .execute()
        .data
    )

if "edit_candidate_id" not in st.session_state:

    st.session_state.edit_candidate_id = None

if "resume_url" not in st.session_state:

    st.session_state.resume_url = None

if "duplicate_override" not in st.session_state:

    st.session_state.duplicate_override = False

if "candidate_form_reset" not in st.session_state:

    st.session_state.candidate_form_reset = 0

if "pending_duplicate" not in st.session_state:

    st.session_state.pending_duplicate = None

editing = False
candidate = None

if st.session_state.edit_candidate_id:

    response = (
        supabase
        .table("candidate_management")
        .select(
            """
            candidate_id,
            job_id,
            first_name,
            last_name,
            email,
            mobile_no,
            alternate_mobile,
            current_location,
            experience_years,
            experience_months,
            qualification,
            education_details,
            current_company,
            current_designation,
            current_ctc,
            expected_ctc,
            notice_period,
            notice_negotiable,
            skills,
            candidate_status,
            remarks,
            created_by_user_id
            """
        )
        .eq(
            "candidate_id",
            st.session_state.edit_candidate_id
        )
        .execute()
    )

    if response.data:

        candidate = response.data[0]

        if (
            st.session_state.user_role == "Admin"
            or
            candidate["created_by_user_id"]
            ==
            st.session_state.user_id
        ):

            editing = True

        else:

            st.error(
                "You are not authorized to edit this candidate."
            )

            st.session_state.edit_candidate_id = None

            st.stop()

# ==========================
# LAYOUT
# ==========================

left_col, right_col = st.columns([1, 3])

with left_col:

    st.markdown(
        "## ✏️ Edit Candidate"
        if editing
        else
        "## ➕ Candidate Entry"
    )


    jobs = get_jobs_for_user(
        st.session_state.user_id,
        st.session_state.user_role
    )

    job_titles = get_job_titles()

    job_title_lookup = {

        item["job_title_id"]:
        item["job_title_name"]

        for item in job_titles

    }

    all_jobs = (
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

    job_display_lookup = {

        job["job_id"]:
        f"{job['job_reference_no']} | "
        f"{job_title_lookup.get(job['job_title_id'], '')}"

        for job in all_jobs

    }

    job_options = [
        "-- Select Job --"
    ]

    job_lookup = {}

    selected_job_label = "-- Select Job --"

    for job in jobs:

        title_name = job_title_lookup.get(
            job["job_title_id"],
            "Unknown Job Title"
        )

        label = (
            f"{job['job_reference_no']} | {title_name}"
        )

        job_options.append(label)

        job_lookup[label] = job

        if (
            editing
            and
            job["job_id"] == candidate["job_id"]
        ):

            selected_job_label = label

    selected_job = st.selectbox(
        "Job *",
        job_options,
        index=job_options.index(
            selected_job_label
        ),
        key=f"job_{st.session_state.candidate_form_reset}"
    )

    col1, col2 = st.columns(2)

    with col1:

        first_name = st.text_input(
            "First Name *",
            value=
            candidate["first_name"]
            if editing
            else "",
            key=f"first_name_{st.session_state.candidate_form_reset}"
        )

    with col2:

        last_name = st.text_input(
            "Last Name",
            value=
            candidate["last_name"]
            if editing
            else "",
            key=f"last_name_{st.session_state.candidate_form_reset}"
        )
        
    email = st.text_input(
        "Email *",
        value=
        candidate["email"]
        if editing
        else "",
        key=f"email_{st.session_state.candidate_form_reset}"
    )

    col1, col2 = st.columns(2)

    with col1:

        mobile_no = st.text_input(
            "Mobile Number *",
            value=
            candidate["mobile_no"]
            if editing
            else "",
            key=f"mobile_no_{st.session_state.candidate_form_reset}"
        )

    with col2:

        alternate_mobile = st.text_input(
            "Alternate Number",
            value=
            candidate["alternate_mobile"]
            if editing
            else "",
            key=f"alternate_mobile_{st.session_state.candidate_form_reset}"
        )

    current_location = st.text_input(
        "Current Location *",
        value=
        candidate["current_location"]
        if editing
        else "",
        key=f"current_location_{st.session_state.candidate_form_reset}"
    )

    col1, col2 = st.columns(2)

    with col1:

        years_options = [
            "-- Select --"
        ] + list(range(41))

        experience_years = st.selectbox(
            "Experience Years *",
            years_options,
            index=(
                years_options.index(
                    candidate["experience_years"]
                )
                if editing
                and candidate["experience_years"] in years_options
                else 0
            ),
            key=f"experience_years_{st.session_state.candidate_form_reset}"
        )

    with col2:

        months_options = [
            "-- Select --"
        ] + list(range(12))

        experience_months = st.selectbox(
            "Experience Months *",
            months_options,
            index=(
                months_options.index(
                    candidate["experience_months"]
                )
                if editing
                and candidate["experience_months"] in months_options
                else 0
            ),
            key=f"experience_months_{st.session_state.candidate_form_reset}"
        )

    st.markdown(
        "### 🎓 Education"
    )

    qualification = st.text_input(
        "Highest Qualification *",
        value=
        candidate["qualification"]
        if editing
        else "",
        key=f"qualification_{st.session_state.candidate_form_reset}"
    )

    education_details = st.text_area(
        "Educational Details",
        value=
        candidate["education_details"]
        if editing
        else "",
        key=f"education_details_{st.session_state.candidate_form_reset}"
    )

    st.markdown(
        "### 💼 Employment"
    )

    current_company = st.text_input(
        "Current Company *",
        value=
        candidate["current_company"]
        if editing
        else "",
        key=f"current_company_{st.session_state.candidate_form_reset}"
    )

    current_designation = st.text_input(
        "Current Designation *",
        value=
        candidate["current_designation"]
        if editing
        else "",
        key=f"current_designation_{st.session_state.candidate_form_reset}"
    )

    col1, col2 = st.columns(2)

    with col1:

        current_ctc = st.number_input(
            "Current CTC",
            min_value=0.0,
            value=float(
                candidate["current_ctc"]
            )
            if editing
            and candidate["current_ctc"]
            else 0.0,
            key=f"current_ctc_{st.session_state.candidate_form_reset}"
        )

    with col2:

        expected_ctc = st.number_input(
            "Expected CTC",
            min_value=0.0,
            value=float(
                candidate["expected_ctc"]
            )
            if editing
            and candidate["expected_ctc"]
            else 0.0,
            key=f"expected_ctc_{st.session_state.candidate_form_reset}"
        )

    col1, col2 = st.columns(2)

    with col1:

        notice_period_options = [
            "-- Select Notice Period --",
            "Immediate",
            "15 Days",
            "30 Days",
            "45 Days",
            "60 Days",
            "90 Days",
            "Above 90 Days",
            "Not Known"
        ]

        notice_period = st.selectbox(
            "Notice Period *",
            notice_period_options,
            index=(
                notice_period_options.index(
                    candidate["notice_period"]
                )
                if editing
                and candidate["notice_period"] in notice_period_options
                else 0
            ),
            key=f"notice_period_{st.session_state.candidate_form_reset}"
        )

    with col2:

        notice_negotiable_options = [
            "-- Select --",
            "Yes",
            "No",
            "Not Known"
        ]

        notice_negotiable = st.selectbox(
            "Notice Negotiable *",
            notice_negotiable_options,
            index=(
                notice_negotiable_options.index(
                    candidate["notice_negotiable"]
                )
                if editing
                and candidate["notice_negotiable"] in notice_negotiable_options
                else 0
            ),
            key=f"notice_negotiable_{st.session_state.candidate_form_reset}"
        )

    st.markdown(
        "### 🛠 Skills & Resume"
    )

    skills = st.text_area(
        "Skills *",
        value=
        candidate["skills"]
        if editing
        else "",
        key=f"skills_{st.session_state.candidate_form_reset}"
    )

    resume = st.file_uploader(
        "Upload Resume *",
        type=[
            "pdf",
            "doc",
            "docx"
        ],
        key=f"resume_{st.session_state.candidate_form_reset}"
    )

    candidate_status_options = [
        "New",
        "Screening",
        "Shortlisted",
        "Hold",
        "Rejected"
    ]

    candidate_status = st.selectbox(
        "Candidate Status",
        candidate_status_options,
        index=(
            candidate_status_options.index(
                candidate["candidate_status"]
            )
            if editing
            and candidate["candidate_status"] in candidate_status_options
            else 0
        ),
        key=f"candidate_status_{st.session_state.candidate_form_reset}"
    )

    remarks = st.text_area(
        "Remarks",
        value=
        candidate["remarks"]
        if editing
        else "",
        key=f"remarks_{st.session_state.candidate_form_reset}"
    )

    if st.session_state.pending_duplicate:

        existing = (
            st.session_state.pending_duplicate
        )

        existing_job = (
            job_display_lookup.get(
                existing["job_id"],
                ""
            )
        )

        st.warning(

            f"Candidate already exists in ATS.\n\n"

            f"Candidate No : "
            f"{existing['candidate_reference_no']}\n\n"

            f"Name : "
            f"{existing['first_name']} "
            f"{existing['last_name']}\n\n"

            f"Current Job : "
            f"{existing_job}\n\n"

            f"Stage : "
            f"{existing.get('current_stage','')}\n\n"

            f"Entered By : "
            f"{existing.get('created_by_name','')}"

        )

        col1, col2 = st.columns(2)

        if col1.button(
            "👁 View Existing Candidate",
            use_container_width=True
        ):

            st.session_state.edit_candidate_id = (
                existing["candidate_id"]
            )

            st.session_state.pending_duplicate = None

            st.rerun()

        if col2.button(
            "✅ Create New Submission",
            use_container_width=True
        ):

            st.session_state.duplicate_override = True

            st.session_state.pending_duplicate = None

            st.rerun()

        st.stop()

    if editing:

        btn1, btn2 = st.columns(2)

        with btn1:

            save_candidate = st.button(
                "Update Candidate",
                use_container_width=True
            )

        with btn2:

            cancel_edit = st.button(
                "❌ Cancel Edit",
                use_container_width=True
            )

    else:

        save_candidate = st.button(
            "Save Candidate",
            use_container_width=True
        )

        cancel_edit = False

    if cancel_edit:

        st.session_state.edit_candidate_id = None

        st.session_state.pending_duplicate = None

        st.session_state.duplicate_override = False

        st.session_state.candidate_form_reset += 1

        st.rerun()

    if save_candidate:

        validation_errors = []

        email_pattern = (
            r'^[\w\.-]+@[\w\.-]+\.\w+$'
        )

        if (
            email.strip()
            and
            not re.match(
                email_pattern,
                email
            )
        ):
            validation_errors.append(
                "Please enter a valid Email."
            )

        if selected_job == "-- Select Job --":
            validation_errors.append(
                "Please select Job."
            )

        if not first_name.strip():
            validation_errors.append(
                "First Name is mandatory."
            )

        elif len(first_name.strip()) < 2:

            validation_errors.append(
                "First Name must contain at least 2 characters."
            )

        if not email.strip():

            validation_errors.append(
                "Email is mandatory."
            )

        if not mobile_no.strip():

            validation_errors.append(
                "Mobile Number is mandatory."
            )

        elif (
            not mobile_no.isdigit()
            or
            len(mobile_no) != 10
        ):

            validation_errors.append(
                "Please enter a valid 10-digit Mobile Number."
            )

        if (
            alternate_mobile.strip()
            and
            (
                not alternate_mobile.isdigit()
                or
                len(alternate_mobile) != 10
            )
        ):

            validation_errors.append(
                "Please enter a valid 10-digit Alternate Mobile Number."
            )

        if (
            mobile_no.strip()
            and
            alternate_mobile.strip()
            and
            mobile_no.strip()
            ==
            alternate_mobile.strip()
        ):

            validation_errors.append(
                "Mobile Number and Alternate Number cannot be same."
            )


        if not current_location.strip():
            validation_errors.append(
                "Current Location is mandatory."
            )

        if experience_years == "-- Select --":

            validation_errors.append(
                "Please select Experience Years."
            )

        if experience_months == "-- Select --":

            validation_errors.append(
                "Please select Experience Months."
            )

        if not qualification.strip():

            validation_errors.append(
                "Highest Qualification is mandatory."
            )

        if not current_company.strip():

            validation_errors.append(
                "Current Company is mandatory."
            )

        if not current_designation.strip():

            validation_errors.append(
                "Current Designation is mandatory."
            )


        if notice_period == "-- Select Notice Period --":

            validation_errors.append(
                "Please select Notice Period."
            )

        if notice_negotiable == "-- Select --":

            validation_errors.append(
                "Please select Notice Negotiable."
            )


        if (
            current_ctc > 0
            and
            expected_ctc > 0
            and
            expected_ctc < current_ctc
        ):

            validation_errors.append(
                "Expected CTC cannot be less than Current CTC."
            )


        if not skills.strip():
            validation_errors.append(
                "Skills are mandatory."
            )

        if (
            not editing
            and
            not resume
        ):
            validation_errors.append(
                "Resume is mandatory."
            )

        if validation_errors:

            for error in validation_errors:

                st.error(error)

        else:

            selected_job_record = (
                job_lookup[
                    selected_job
                ]
            )

            duplicate_candidate = (
                supabase
                .table(
                    "candidate_management"
                )
                .select(
                    """
                    candidate_id,
                    candidate_reference_no
                    """
                )
                .eq(
                    "job_id",
                    selected_job_record["job_id"]
                )
                .or_(
                    f"email.eq.{email.strip().lower()},"
                    f"mobile_no.eq.{mobile_no.strip()},"
                    f"alternate_mobile.eq.{mobile_no.strip()},"
                    f"mobile_no.eq.{alternate_mobile.strip()},"
                    f"alternate_mobile.eq.{alternate_mobile.strip()}"
                )
                .execute()
            )

            # Ignore self during edit
            if editing:

                duplicate_candidate.data = [

                    item

                    for item in duplicate_candidate.data

                    if item["candidate_id"]
                    != candidate["candidate_id"]

                ]

            if duplicate_candidate.data:

                existing_candidate = (
                    duplicate_candidate.data[0]
                )

                st.error(

                    f"Candidate already exists "
                    f"for this Job. "
                    f"Candidate No : "
                    f"{existing_candidate['candidate_reference_no']}"

                )

                st.stop()

            soft_duplicate = (
                supabase
                .table(
                    "candidate_management"
                )
                .select(
                    """
                    candidate_id,
                    candidate_reference_no,
                    first_name,
                    last_name,
                    email,
                    mobile_no,
                    alternate_mobile,
                    current_stage,
                    job_id,
                    created_by_name
                    """
                )
                .execute()
            )

            normalized_email = (
                email.strip().lower()
            )

            normalized_mobile = (
                mobile_no.strip()
            )

            normalized_alternate = (
                alternate_mobile.strip()
            )

            soft_matches = []

            for existing in soft_duplicate.data:

                if (
                    editing
                    and
                    existing["candidate_id"]
                    ==
                    candidate["candidate_id"]
                ):

                    continue

                match_found = False

                if (
                    normalized_email
                    and
                    str(
                        existing.get(
                            "email",
                            ""
                        )
                    ).lower()
                    ==
                    normalized_email
                ):

                    match_found = True

                elif (
                    normalized_mobile
                    and
                    (
                        existing.get(
                            "mobile_no",
                            ""
                        )
                        ==
                        normalized_mobile

                        or

                        existing.get(
                            "alternate_mobile",
                            ""
                        )
                        ==
                        normalized_mobile
                    )
                ):

                    match_found = True

                elif (
                    normalized_alternate
                    and
                    (
                        existing.get(
                            "mobile_no",
                            ""
                        )
                        ==
                        normalized_alternate

                        or

                        existing.get(
                            "alternate_mobile",
                            ""
                        )
                        ==
                        normalized_alternate
                    )
                ):

                    match_found = True

                if match_found:

                    soft_matches.append(
                        existing
                    )

            if (
                soft_matches
                and
                not st.session_state.duplicate_override
            ):

                st.session_state.pending_duplicate = (
                    soft_matches[0]
                )

                st.rerun()

            candidate_data = {

                "job_id":
                    selected_job_record["job_id"],

                "first_name":
                    first_name.strip(),

                "last_name":
                    last_name.strip(),

                "email":
                    email.strip().lower(),

                "mobile_no":
                    mobile_no.strip(),

                "alternate_mobile":
                    alternate_mobile.strip(),

                "current_location":
                    current_location.strip(),

                "experience_years":
                    experience_years,

                "experience_months":
                    experience_months,

                "qualification":
                    qualification.strip(),

                "education_details":
                    education_details.strip(),

                "current_company":
                    current_company.strip(),

                "current_designation":
                    current_designation.strip(),

                "current_ctc":
                    current_ctc,

                "expected_ctc":
                    expected_ctc,

                "notice_period":
                    notice_period,

                "notice_negotiable":
                    notice_negotiable,

                "skills":
                    skills.strip(),

                "candidate_status":
                    candidate_status,

                "remarks":
                    remarks.strip(),

                "created_by_user_id":
                    st.session_state.user_id,

                "created_by_name":
                    st.session_state.user_name

            }

            if editing:

                (
                    supabase
                    .table(
                        "candidate_management"
                    )
                    .update(
                        candidate_data
                    )
                    .eq(
                        "candidate_id",
                        candidate["candidate_id"]
                    )
                    .execute()
                )

                st.success(
                    "Candidate Updated Successfully."
                )

                st.session_state.edit_candidate_id = None

                st.session_state.duplicate_override = False

                st.session_state.pending_duplicate = None

                st.session_state.candidate_form_reset += 1

                st.rerun()

            else:

                insert_result = (
                    supabase
                    .table(
                        "candidate_management"
                    )
                    .insert(
                        candidate_data
                    )
                    .execute()
                )

                candidate = (
                    insert_result.data[0]
                )

                current_year = (
                    datetime.now().year
                )

                candidate_ref = (

                    f"CAN-{current_year}-{candidate['candidate_id']:06d}"

                )

                resume_path = None

                if resume:

                    unique_file_name = (

                        f"{candidate_ref}_{resume.name}"

                    )

                    resume_path = upload_resume(

                        resume,
                        unique_file_name

                    )

                    if not resume_path:

                        st.error(
                            "Resume upload failed. Candidate was not saved completely."
                        )

                        st.stop()

                (
                    supabase

                    .table(
                        "candidate_management"
                    )

                    .update({

                        "candidate_reference_no":
                            candidate_ref,

                        "resume_name":
                            resume.name,

                        "resume_path":
                            resume_path

                    })

                    .eq(
                        "candidate_id",
                        candidate["candidate_id"]
                    )

                    .execute()

                )

                st.success(
                    f"Candidate Created : {candidate_ref}"
                )

                st.session_state.duplicate_override = False

                st.session_state.pending_duplicate = None

                st.session_state.candidate_form_reset += 1

                st.rerun()

# ==========================
# RIGHT PANEL
# ==========================

with right_col:

    st.markdown(
        "## 📋 Candidate Directory"
    )
    
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:

        status_filter = st.selectbox(
            "Status",
            [
                "All Status",
                "New",
                "Screening",
                "Submitted",
                "Hold",
                "Rejected"
            ]
        )

    if st.session_state.resume_url:

        st.link_button(
            "📄 Open Selected CV",
            st.session_state.resume_url,
            use_container_width=True
        )

    search_text = st.text_input(
        "🔍 Search Candidate",
        placeholder=
        "CAN No, Name, Email, Mobile or Company"
    )

    job_filter_options = [
        "All Jobs"
    ]

    for job in jobs:

        title_name = job_title_lookup.get(
            job["job_title_id"],
            "Unknown Job Title"
        )

        label = (
            f"{job['job_reference_no']} | {title_name}"
        )

        job_filter_options.append(
            label
        )

    with filter_col2:

        job_filter = st.selectbox(
            "Job",
            job_filter_options
        )

    with filter_col3:

        recruiter_filter = "All Recruiters"

        if (
            st.session_state.user_role
            ==
            "Admin"
        ):

            users = get_recruiters()

            recruiter_options = [
                "All Recruiters"
            ]

            recruiter_options.extend(
                sorted(
                    list(
                        {
                            user["full_name"]
                            for user in users
                        }
                    )
                )
            )

            recruiter_filter = st.selectbox(
                "Recruiter",
                recruiter_options
            )

    result = (
        supabase
        .table("candidate_management")
        .select(
            """
            candidate_id,
            job_id,
            candidate_reference_no,
            first_name,
            last_name,
            mobile_no,
            email,
            current_company,
            skills,
            candidate_status,
            created_by_name,
            created_by_user_id,
            experience_years,
            experience_months,
            resume_path
            """
        )
        .order(
            "candidate_id",
            desc=True
        )
        .execute()
    )

    candidates = result.data
    
    filtered_candidates = candidates

    if status_filter != "All Status":

        filtered_candidates = [

            candidate

            for candidate
            in filtered_candidates

            if candidate["candidate_status"]
            ==
            status_filter

        ]

    if job_filter != "All Jobs":

        selected_job_id = (
            job_lookup[job_filter]["job_id"]
        )

        filtered_candidates = [

            candidate

            for candidate
            in filtered_candidates

            if candidate["job_id"]
            ==
            selected_job_id

        ]

    if recruiter_filter != "All Recruiters":

        filtered_candidates = [

            candidate

            for candidate
            in filtered_candidates

            if candidate["created_by_name"]
            ==
            recruiter_filter

        ]

    if search_text:

        search_results = []

        for candidate in filtered_candidates:

            full_name = (
                f"{candidate.get('first_name','')} "
                f"{candidate.get('last_name','')}"
            ).strip()

            searchable_text = (
                f"{candidate.get('candidate_reference_no','')} "
                f"{full_name} "
                f"{candidate.get('email','')} "
                f"{candidate.get('mobile_no','')} "
                f"{candidate.get('current_company','')} "
                f"{candidate.get('skills','')}"
            )

            if (
                search_text.lower()
                in
                searchable_text.lower()
            ):

                search_results.append(
                    candidate
                )

        filtered_candidates = search_results
    
    candidates = filtered_candidates

    if candidates:

        headers = st.columns(
            [2,3,3,2,2,2,3,2,2,2]
        )

        headers[0].markdown(
            "**CAN No**"
        )
        headers[1].markdown(
            "**Job No**"
        )

        headers[2].markdown(
            "**Candidate Name**"
        )

        headers[3].markdown(
            "**Company**"
        )

        headers[4].markdown(
            "**Mobile**"
        )

        headers[5].markdown(
            "**Experience**"
        )

        headers[6].markdown(
            "**Status**"
        )

        headers[7].markdown(
            "**Entered By**"
        )

        headers[8].markdown(
            "**Resume**"
        )

        headers[9].markdown(
            "**Edit**"
        )

        st.divider()

        for candidate in candidates:

            cols = st.columns(
                [2,3,2,2,2,2,3,2,2,2]
            )

            full_name = (
                f"{candidate.get('first_name','')} "
                f"{candidate.get('last_name','')}"
            ).strip()

            experience = (
                f"{candidate.get('experience_years',0)}Y "
                f"{candidate.get('experience_months',0)}M"
            )

            cols[0].write(
                candidate.get(
                    "candidate_reference_no",
                    ""
                )
            )

            cols[1].write(
                job_display_lookup.get(
                    candidate["job_id"],
                    ""
                )
            )

            cols[2].write(
                full_name
            )

            cols[3].write(
                candidate.get(
                    "current_company",
                    ""
                )
            )

            cols[4].write(
                candidate.get(
                    "mobile_no",
                    ""
                )
            )

            cols[5].write(
                experience
            )

            status = candidate.get(
                "candidate_status",
                ""
            )

            status_colors = {

                "New": "#2563EB",
                "Screening": "#F59E0B",
                "Shortlisted": "#8B5CF6",
                "Hold": "#EAB308",
                "Rejected": "#DC2626"

            }

            color = status_colors.get(
                status,
                "#64748B"
            )

            cols[6].markdown(
                f"""
                <div style="
                background:{color};
                color:white;
                padding:6px 12px;
                border-radius:12px;
                text-align:center;
                font-size:14px;
                white-space:nowrap;
                display:inline-block;
                ">
                {status}
                </div>
                """,
                unsafe_allow_html=True
            )


            cols[7].write(
                candidate.get(
                    "created_by_name",
                    ""
                )
            )

            if candidate.get(
                "resume_path"
            ):

                if cols[8].button(
                    "📄 CV",
                    key=f"view_{candidate['candidate_id']}"
                ):

                    st.session_state.resume_url = (
                        get_resume_url(
                            candidate["resume_path"]
                        )
                    )

                    st.rerun()

            else:

                cols[8].write("-")

            can_edit = False

            if st.session_state.user_role == "Admin":

                can_edit = True

            elif (
                candidate["created_by_user_id"]
                ==
                st.session_state.user_id
            ):

                can_edit = True

            if can_edit:

                if cols[9].button(
                    "✏️",
                    key=f"edit_{candidate['candidate_id']}"
                ):

                    st.session_state.edit_candidate_id = (
                        candidate["candidate_id"]
                    )

                    st.rerun()

            else:

                cols[9].write("🔒")

    else:

        st.info(
            "No candidates found."
        )