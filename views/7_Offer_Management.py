import streamlit as st
from db import supabase
from common import show_logout, show_job_notifications, show_user_profile, render_pagination, fetch_all_from_table, clear_data_cache

try:
    from common import render_paginated_section
except (ImportError, AttributeError):
    def render_paginated_section(
        items,
        render_row_fn,
        page_size_default=25,
        key_prefix="page",
        page_size_options=[25, 50, 100],
        render_header_fn=None,
        empty_message="No records found."
    ):
        total_items = len(items) if items is not None else 0
        if total_items == 0:
            st.info(empty_message)
            return

        page_items, current_page, total_pages = render_pagination(
            items, page_size_default=page_size_default, key_prefix=key_prefix, page_size_options=page_size_options
        )

        if render_header_fn:
            render_header_fn()

        import inspect
        sig = inspect.signature(render_row_fn)
        takes_idx = len(sig.parameters) >= 2

        page_size = page_size_default
        size_key = f"{key_prefix}_size_select"
        if size_key in st.session_state and st.session_state[size_key] in page_size_options:
            page_size = st.session_state[size_key]
        start_num = (current_page - 1) * page_size + 1

        if hasattr(page_items, "iterrows"):
            for offset, (_, row) in enumerate(page_items.iterrows()):
                if takes_idx:
                    render_row_fn(row, start_num + offset)
                else:
                    render_row_fn(row)
        else:
            for offset, item in enumerate(page_items):
                if takes_idx:
                    render_row_fn(item, start_num + offset)
                else:
                    render_row_fn(item)
from datetime import date, datetime
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
    page_title="Offer Management",
    layout="wide"
)

apply_theme()

with st.sidebar:
    show_user_profile()
    show_logout()
    show_job_notifications()

st.markdown(
    "# 📄 ATS Offer Management"
)

# ==========================
# FUNCTIONS
# ==========================

# NO CACHE - Always fetches live data so it reacts to Interview Management instantly!
def get_candidates_for_offer():
    all_data = []
    chunk_size = 1000
    start = 0
    while True:
        try:
            res = (
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
                    created_by_user_id
                    """
                )
                .in_("current_stage", ["Selected", "Offer", "Joined", "Rejected"])
                .order("candidate_id", desc=True)
                .range(start, start + chunk_size - 1)
                .execute()
            )
            data = res.data or []
            all_data.extend(data)
            if len(data) < chunk_size:
                break
            start += chunk_size
        except Exception:
            break
    return all_data


@st.cache_data(ttl=15)
def get_job_titles():
    return (
        supabase
        .table("job_title_master")
        .select("*")
        .execute()
        .data or []
    )

@st.cache_data(ttl=15)
def get_companies():
    return (
        supabase
        .table("company_master")
        .select("*")
        .execute()
        .data or []
    )

@st.cache_data(ttl=15)
def get_jobs():
    return (
        supabase
        .table("job_management")
        .select(
            """
            job_id,
            job_reference_no,
            job_title_id,
            company_id
            """
        )
        .execute()
        .data or []
    )

@st.cache_data(ttl=30)
def get_all_users():
    try:
        return (
            supabase
            .table("users")
            .select("user_id, full_name, role, status")
            .execute()
            .data or []
        )
    except Exception:
        return []

# NO CACHE - Always fetches live data for the right-hand grid!
def get_candidate_lookup():
    all_data = []
    chunk_size = 1000
    start = 0
    while True:
        try:
            res = (
                supabase
                .table("candidate_management")
                .select(
                    """
                    candidate_id,
                    candidate_reference_no,
                    first_name,
                    last_name,
                    current_stage,
                    created_by_name,
                    created_by_user_id
                    """
                )
                .order("candidate_id", desc=True)
                .range(start, start + chunk_size - 1)
                .execute()
            )
            data = res.data or []
            all_data.extend(data)
            if len(data) < chunk_size:
                break
            start += chunk_size
        except Exception:
            break
    return all_data

def update_candidate_stage(
    candidate_id,
    offer_status
):

    if offer_status in [
        "Offer Released",
        "Offer Accepted"
    ]:

        stage = "Offer"

    elif offer_status == "Joined":

        stage = "Joined"

    elif offer_status in [
        "Offer Rejected",
        "No Show"
    ]:

        stage = "Rejected"

    else:

        stage = "Offer"

    # Transform 'Joined' to 'Hired' for the Candidate Grid display
    display_status = "Hired" if offer_status == "Joined" else offer_status

    (
        supabase
        .table("candidate_management")
        .update({
            "current_stage": stage,
            "candidate_status": display_status 
        })
        .eq(
            "candidate_id",
            candidate_id
        )
        .execute()
    )


# --- NEW: SMART SYNC FUNCTION ---
def sync_job_status(job_id):
    """Checks the target openings vs actual joined and auto-closes or auto-opens the job."""
    
    # 1. Fetch target openings and current job status
    job_res = (
        supabase.table("job_management")
        .select("openings, job_status")
        .eq("job_id", job_id)
        .single()
        .execute()
    )
    
    if job_res.data:
        target_openings = int(job_res.data.get("openings", 1))
        current_status = job_res.data.get("job_status")
        
        # 2. Count total candidates who have Joined this specific job
        joined_res = (
            supabase.table("candidate_management")
            .select("candidate_id")
            .eq("job_id", job_id)
            .eq("current_stage", "Joined")
            .execute()
        )
        current_joined_count = len(joined_res.data)
        
        # 3. Two-Way Sync Logic
        # Case A: Target Met -> Auto-Close Job
        if current_joined_count >= target_openings and current_status != "Closed":
            (
                supabase.table("job_management")
                .update({"job_status": "Closed"})
                .eq("job_id", job_id)
                .execute()
            )
            st.toast(f"🎯 Target reached! Job automatically closed ({current_joined_count}/{target_openings} filled).")
            
        # Case B: Target No Longer Met (Candidate backed out/changed) -> Auto-Reopen Job
        elif current_joined_count < target_openings and current_status == "Closed":
            (
                supabase.table("job_management")
                .update({"job_status": "Open"})
                .eq("job_id", job_id)
                .execute()
            )
            st.toast(f"🔄 Candidate status changed. Job automatically reopened ({current_joined_count}/{target_openings} filled).")


def get_offer_by_id(
    offer_id
):

    result = (
        supabase
        .table("offer_management")
        .select("*")
        .eq(
            "offer_id",
            offer_id
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

companies = get_companies()

company_lookup = {
    
    item["company_id"]: 
    item["company_name"]
    
    for item in companies
    
}

jobs = get_jobs()

job_display_lookup = {

    job["job_id"]:
    f"{job_title_lookup.get(job['job_title_id'], 'Unknown Title')} | "
    f"{company_lookup.get(job.get('company_id'), 'Unknown Company')}"

    for job in jobs

}

all_users = get_all_users()
user_name_lookup = {
    u["user_id"]: u["full_name"]
    for u in all_users
}

# ==========================
# SESSION VARIABLES
# ==========================

if "edit_offer_id" not in st.session_state:

    st.session_state.edit_offer_id = None

if "form_reset_offer" not in st.session_state:

    st.session_state.form_reset_offer = 0

# ==========================
# EDIT MODE
# ==========================

editing = False

offer = None

if st.session_state.edit_offer_id:

    offer = get_offer_by_id(
        st.session_state.edit_offer_id
    )

    if offer:
        # SECURITY CHECK: Only Admin, Developer, or the Creator can edit
        if (
            st.session_state.user_role in ["Admin", "Developer", "Admin-Lite"]
            or offer.get("created_by_user_id") == st.session_state.user_id
        ):
            editing = True
        else:
            st.error("You are not authorized to edit this offer.")
            st.session_state.edit_offer_id = None
            st.stop()
    else:

        st.session_state.edit_offer_id = None
        st.rerun()

# ==========================
# DROPDOWN VALUES
# ==========================

offer_status_options = [

    "-- Select Offer Status --",

    "Offer Released",

    "Offer Accepted",

    "Offer Rejected",

    "Joined",

    "No Show"

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

    if st.session_state.get("offer_success_message"):
        st.success(st.session_state.offer_success_message)
        del st.session_state.offer_success_message

    def get_key(base_name):
        if editing:
            return f"{base_name}_{offer['offer_id']}"
        return f"{base_name}_new_{st.session_state.form_reset_offer}"


    st.markdown(
        "## ✏️ Edit Offer"
        if editing
        else
        "## 📄 Create Offer"
    )

    raw_candidates = get_candidates_for_offer()
    
    # Add security filtering for the dropdown (Admin, Developer, Candidate Creator, or Recruiter assigned to the job)
    if st.session_state.user_role not in ["Admin", "Developer", "Admin-Lite"]:
        assigned_job_ids = set()
        try:
            assigned = (
                supabase
                .table("job_assignment")
                .select("job_id")
                .eq("user_id", st.session_state.user_id)
                .execute()
                .data or []
            )
            assigned_job_ids = {a["job_id"] for a in assigned}
        except Exception:
            pass
        raw_candidates = [
            c for c in raw_candidates 
            if c.get("created_by_user_id") == st.session_state.user_id or c.get("job_id") in assigned_job_ids
        ]
    
    # ENHANCEMENT: Only show "Selected" candidates when scheduling new offers. 
    # Once they get an offer, they hide automatically!
    if not editing:
        candidates = [
            c for c in raw_candidates 
            if c.get("current_stage") == "Selected"
        ]
    else:
        # Include all relevant past stages in Edit Mode so the dropdown populates properly
        candidates = [
            c for c in raw_candidates 
            if c.get("current_stage") in ["Selected", "Offer", "Joined", "Rejected"]
        ]

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
            == offer["candidate_id"]
        ):

            selected_candidate_label = (
                label
            )

    if editing:
        # In edit mode, lock the candidate field to prevent accidental reassignment
        # Find the candidate's display label from the lookup
        editing_candidate_label = selected_candidate_label
        if editing_candidate_label == "-- Select Candidate --":
            # Fallback: fetch name directly from offer data
            try:
                cand_res = supabase.table("candidate_management").select("candidate_reference_no, first_name, last_name").eq("candidate_id", offer["candidate_id"]).single().execute()
                if cand_res.data:
                    cd = cand_res.data
                    editing_candidate_label = f"{cd['candidate_reference_no']} | {cd['first_name']} {cd['last_name']}"
            except Exception:
                editing_candidate_label = f"Candidate ID: {offer['candidate_id']}"

        st.text_input(
            "Candidate *",
            value=editing_candidate_label,
            disabled=True,
            help="Candidate cannot be changed when editing an existing offer. Create a new offer for a different candidate.",
            key=get_key("candidate_locked")
        )
        st.caption("🔒 *Candidate is locked in edit mode.*")
        # Set the candidate values from the existing offer
        selected_candidate = editing_candidate_label
        selected_candidate_id = offer["candidate_id"]
    else:
        selected_candidate = st.selectbox(
            "Candidate *",
            candidate_options,
            index=candidate_options.index(
                selected_candidate_label
            ) if selected_candidate_label in candidate_options else 0,
            key=get_key("candidate_select")
        )

    if editing:
        # In edit mode: candidate and job IDs come directly from the existing offer record
        selected_candidate_id = offer["candidate_id"]
        selected_job_id = offer["job_id"]
        selected_job_display = job_display_lookup.get(selected_job_id, "")
    else:
        selected_job_id = None
        selected_candidate_id = None
        selected_job_display = ""

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

    # NO KEY HERE: This allows the Job field to update instantly when candidate changes
    st.text_input(
        "Job",
        value=selected_job_display,
        disabled=True
    )

    st.markdown(
        "### 💰 Compensation"
    )

    offered_ctc = st.number_input(
        "Offered CTC *",
        min_value=0.0,
        value=(
            float(
                offer["offered_ctc"]
            )
            if editing
            and offer["offered_ctc"]
            else 0.0
        ),
        key=get_key("offered_ctc")
    )

    # Date parsing logic to allow None (blank placeholder) by default
    default_date = None
    if editing and offer.get("joining_date"):
        try:
            default_date = datetime.strptime(str(offer["joining_date"]), "%Y-%m-%d").date()
        except:
            default_date = None

    joining_date = st.date_input(
        "Joining Date *",
        value=default_date,
        key=get_key("joining_date")
    )

    offer_status = st.selectbox(
        "Offer Status *",
        offer_status_options,
        index=(
            offer_status_options.index(
                offer["offer_status"]
            )
            if editing
            and offer["offer_status"]
            in offer_status_options
            else 0
        ),
        key=get_key("offer_status")
    )

    st.markdown(
        "### 📝 Offer Remarks"
    )

    remarks = st.text_area(
        "Remarks",
        value=(
            offer["remarks"]
            if editing
            and offer["remarks"]
            else ""
        ),
        height=120,
        key=get_key("remarks")
    )

    # ----------------------
    # BUTTONS
    # ----------------------

    if editing:

        btn1, btn2, btn3 = st.columns(3)

        update_clicked = btn1.button(
            "Update Offer",
            use_container_width=True
        )
        
        delete_clicked = btn2.button(
            "🗑️ Delete Offer",
            use_container_width=True
        )

        cancel_clicked = btn3.button(
            "❌ Cancel Edit",
            use_container_width=True
        )

    else:

        update_clicked = st.button(
            "Save Offer",
            use_container_width=True
        )

        cancel_clicked = False
        delete_clicked = False

    if cancel_clicked:

        st.session_state.edit_offer_id = None
        st.session_state.form_reset_offer += 1
        st.rerun()
        
    if delete_clicked:
        
        try:
            # 1. Delete the offer record from the database
            (
                supabase
                .table("offer_management")
                .delete()
                .eq("offer_id", offer["offer_id"])
                .execute()
            )
            
            # 2. Revert the candidate's master stage back to "Selected"
            (
                supabase
                .table("candidate_management")
                .update({
                    "current_stage": "Selected",
                    "candidate_status": "Selected" # <-- Safely revert candidate manual status
                })
                .eq("candidate_id", selected_candidate_id)
                .execute()
            )
            
            # 3. Make sure the job reverts back to open if they were "Joined" before deletion
            sync_job_status(selected_job_id)
            
            clear_data_cache()
            st.session_state.offer_success_message = "Offer deleted successfully. Candidate reverted to 'Selected' stage."
            st.session_state.edit_offer_id = None
            st.session_state.form_reset_offer += 1
            st.rerun()
            
        except Exception as e:
            st.error(f"Error deleting offer: {str(e)}")

    # ----------------------
    # SAVE / UPDATE
    # ----------------------

    if update_clicked:

        validation_errors = []

        if (
            selected_candidate
            ==
            "-- Select Candidate --"
        ):

            validation_errors.append(
                "Please select Candidate."
            )

        if offered_ctc <= 0:

            validation_errors.append(
                "Please enter Offered CTC."
            )
            
        if joining_date is None:
            
            validation_errors.append(
                "Please select a Joining Date."
            )

        if (
            offer_status
            ==
            "-- Select Offer Status --"
        ):

            validation_errors.append(
                "Please select Offer Status."
            )

        if validation_errors:

            for error in validation_errors:

                st.error(error)

        else:

            offer_data = {

                "candidate_id":
                selected_candidate_id,

                "job_id":
                selected_job_id,

                "offered_ctc":
                offered_ctc,

                "joining_date":
                str(joining_date),

                "offer_status":
                offer_status,

                "remarks":
                remarks.strip()

            }

            try:

                if editing:

                    (
                        supabase
                        .table(
                            "offer_management"
                        )
                        .update(
                            offer_data
                        )
                        .eq(
                            "offer_id",
                            offer["offer_id"]
                        )
                        .execute()
                    )

                    update_candidate_stage(
                        selected_candidate_id,
                        offer_status
                    )

                    st.session_state.offer_success_message = "Offer Updated Successfully."
                    st.session_state.edit_offer_id = None

                else:
                    # Duplicate offer guard: check if an offer already exists for this candidate
                    existing_offer_check = (
                        supabase
                        .table("offer_management")
                        .select("offer_id, offer_status")
                        .eq("candidate_id", selected_candidate_id)
                        .execute()
                        .data or []
                    )
                    if existing_offer_check:
                        existing_offer = existing_offer_check[0]
                        st.error(
                            f"⚠️ An offer already exists for this candidate "
                            f"(Offer ID: {existing_offer['offer_id']}, Status: {existing_offer['offer_status']}). "
                            f"Please search for the existing offer and use **Edit** to update it instead of creating a new one."
                        )
                        st.stop()

                    offer_data["created_by_user_id"] = st.session_state.user_id
                    offer_data["created_by_name"] = st.session_state.user_name

                    (
                        supabase
                        .table(
                            "offer_management"
                        )
                        .insert(
                            offer_data
                        )
                        .execute()
                    )

                    update_candidate_stage(
                        selected_candidate_id,
                        offer_status
                    )

                    st.session_state.offer_success_message = "Offer Saved Successfully."
                
                # ==========================================
                # TWO-WAY SMART AUTO-SYNC JOB LOGIC
                # ==========================================
                sync_job_status(selected_job_id)

                # Advance Reset Tracker to clean the form
                clear_data_cache()
                st.session_state.form_reset_offer += 1
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
        "## 📋 Offer Directory"
    )

    # --------------------------
    # CANDIDATE LOOKUP
    # --------------------------

    all_candidates = get_candidate_lookup()

    candidate_lookup = {
        candidate["candidate_id"]:
        f"{candidate['candidate_reference_no']} | {candidate['first_name']} {candidate['last_name']}"
        for candidate in all_candidates
    }

    candidate_creator_lookup = {
        candidate["candidate_id"]: (
            candidate.get("created_by_name")
            or user_name_lookup.get(candidate.get("created_by_user_id"), "")
        )
        for candidate in all_candidates
    }

    candidate_creator_id_lookup = {
        candidate["candidate_id"]: candidate.get("created_by_user_id")
        for candidate in all_candidates
    }

    # --------------------------
    # OFFER DATA & ROLE ACCESS
    # --------------------------

    offers = fetch_all_from_table("offer_management", select_fields="*", order_by="offer_id", desc=True)

    is_admin = st.session_state.user_role in ["Admin", "Developer", "Admin-Lite"]

    # Security check: Recruiters only see their own offer records
    if not is_admin:
        current_uid = st.session_state.user_id
        current_name = st.session_state.user_name
        offers = [
            item for item in offers
            if item.get("created_by_user_id") == current_uid
            or item.get("created_by_name") == current_name
            or candidate_creator_lookup.get(item.get("candidate_id")) == current_name
            or candidate_creator_id_lookup.get(item.get("candidate_id")) == current_uid
        ]

    # --- Filter layout: 3 columns for Admin/Developer, 2 columns for Recruiter ---
    if is_admin:
        filter_col1, filter_col2, filter_col3 = st.columns(3)
    else:
        filter_col1, filter_col2 = st.columns(2)

    with filter_col1:
        status_filter = st.selectbox(
            "Offer Status",
            [
                "All Status",
                "Offer Released",
                "Offer Accepted",
                "Offer Rejected",
                "Joined",
                "No Show"
            ]
        )

    with filter_col2:
        all_jobs_in_offers = sorted(
            list(
                {
                    job_display_lookup.get(item["job_id"], "Unknown Job")
                    for item in offers
                    if item.get("job_id")
                }
            )
        )
        job_filter = st.selectbox(
            "Job Filter",
            ["All Jobs"] + all_jobs_in_offers
        )

    recruiter_filter = "All Recruiters"
    if is_admin:
        with filter_col3:
            active_recruiters = [
                u["full_name"]
                for u in all_users
                if u.get("role") in ["Recruiter", "Admin-Lite"] and u.get("status") == "Active"
            ]
            offer_recruiters = {
                item["created_by_name"]
                for item in offers
                if item.get("created_by_name")
            }
            all_recruiter_options = sorted(list(set(active_recruiters) | offer_recruiters))
            recruiter_filter = st.selectbox(
                "Recruiter",
                ["All Recruiters"] + all_recruiter_options
            )

    search_text = st.text_input(
        "🔍 Search Offer",
        placeholder=(
            "Candidate, CAN No, Job No or Recruiter"
            if is_admin
            else "Candidate, CAN No or Job No"
        )
    )

    # --------------------------
    # STATUS FILTER
    # --------------------------

    if status_filter != "All Status":
        offers = [
            item
            for item in offers
            if item["offer_status"] == status_filter
        ]

    # --------------------------
    # JOB FILTER
    # --------------------------

    if job_filter != "All Jobs":
        offers = [
            item
            for item in offers
            if job_display_lookup.get(item["job_id"], "") == job_filter
        ]

    # --------------------------
    # RECRUITER FILTER (ADMIN / DEVELOPER ONLY)
    # --------------------------

    if is_admin and recruiter_filter != "All Recruiters":
        offers = [
            item
            for item in offers
            if (
                item.get("created_by_name") == recruiter_filter
                or user_name_lookup.get(item.get("created_by_user_id")) == recruiter_filter
                or candidate_creator_lookup.get(item.get("candidate_id")) == recruiter_filter
            )
        ]

    # --------------------------
    # SEARCH
    # --------------------------

    if search_text:

        filtered = []

        for item in offers:

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

            recruiter_name = (
                item.get("created_by_name")
                or user_name_lookup.get(item.get("created_by_user_id"), "")
                or candidate_creator_lookup.get(item.get("candidate_id"), "")
            )

            searchable_text = (
                f"{candidate_name} {job_name} {recruiter_name} {item.get('offered_ctc', '')} {item.get('joining_date', '')}"
            )

            if (

                search_text.lower()

                in

                searchable_text.lower()

            ):

                filtered.append(
                    item
                )

        offers = filtered

    # --------------------------
    # GRID
    # --------------------------

    if offers:
        def render_offer_header():
            if is_admin:
                header = st.columns([3, 2.5, 1.5, 1.5, 2, 2, 1])
                header[0].markdown("**Candidate**")
                header[1].markdown("**Job**")
                header[2].markdown("**Offered CTC**")
                header[3].markdown("**Joining Date**")
                header[4].markdown("**Recruiter**")
                header[5].markdown("**Status**")
                header[6].markdown("**Edit**")
            else:
                header = st.columns([3, 3, 2, 2, 3, 1])
                header[0].markdown("**Candidate**")
                header[1].markdown("**Job**")
                header[2].markdown("**Offered CTC**")
                header[3].markdown("**Joining Date**")
                header[4].markdown("**Status**")
                header[5].markdown("**Edit**")
            st.divider()

        def render_offer_row(item):
            if is_admin:
                cols = st.columns([3, 2.5, 1.5, 1.5, 2, 2, 1])
            else:
                cols = st.columns([3, 3, 2, 2, 3, 1])

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
                item["offered_ctc"]
            )

            cols[3].write(
                item["joining_date"]
            )

            status = item["offer_status"]
            status_colors = {
                "Offer Released": "#2563EB",
                "Offer Accepted": "#16A34A",
                "Offer Rejected": "#DC2626",
                "Joined": "#22C55E",
                "No Show": "#F59E0B"
            }

            color = status_colors.get(
                status,
                "#64748B"
            )

            status_badge = f"""
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
            """

            if is_admin:
                rec_display = (
                    item.get("created_by_name")
                    or user_name_lookup.get(item.get("created_by_user_id"))
                    or candidate_creator_lookup.get(item.get("candidate_id"))
                    or "-"
                )
                cols[4].write(rec_display)
                cols[5].markdown(status_badge, unsafe_allow_html=True)
                btn_col = cols[6]
            else:
                cols[4].markdown(status_badge, unsafe_allow_html=True)
                btn_col = cols[5]

            # SECURITY CHECK: Determine if user is authorized to edit
            can_edit = False
            if is_admin:
                can_edit = True
            elif item.get("created_by_user_id") == st.session_state.user_id:
                can_edit = True

            if can_edit:
                if btn_col.button(
                    "✏️",
                    key=f"edit_{item['offer_id']}"
                ):
                    st.session_state.edit_offer_id = (
                        item["offer_id"]
                    )
                    st.rerun(scope="app")
            else:
                btn_col.markdown("<div style='margin-top:2px;'>🔒</div>", unsafe_allow_html=True)

        render_paginated_section(
            offers,
            render_offer_row,
            page_size_default=25,
            key_prefix="offers",
            render_header_fn=render_offer_header,
            empty_message="No offers found."
        )

    else:
        st.info(
            "No offers found."
        )