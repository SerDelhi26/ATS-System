import streamlit as st
from db import supabase
from common import show_logout, show_job_notifications, show_user_profile
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
            current_stage
            """
        )
        .execute()
        .data
    )


def get_job_titles():

    return (
        supabase
        .table("job_title_master")
        .select("*")
        .execute()
        .data
    )

def get_companies():

    return (
        supabase
        .table("company_master")
        .select("*")
        .execute()
        .data
    )


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
        .data
    )

# NO CACHE - Always fetches live data for the right-hand grid!
def get_candidate_lookup():

    return (
        supabase
        .table("candidate_management")
        .select(
            """
            candidate_id,
            candidate_reference_no,
            first_name,
            last_name,
            current_stage
            """
        )
        .execute()
        .data
    )

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

        editing = True

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

    selected_candidate = st.selectbox(
        "Candidate *",
        candidate_options,
        index=candidate_options.index(
            selected_candidate_label
        ) if selected_candidate_label in candidate_options else 0,
        key=get_key("candidate_select")
    )

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
                .update({"current_stage": "Selected"})
                .eq("candidate_id", selected_candidate_id)
                .execute()
            )
            
            st.success("Offer deleted successfully. Candidate reverted to 'Selected' stage.")
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

                    st.success(
                        "Offer Updated Successfully."
                    )

                    st.session_state.edit_offer_id = None

                else:

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

                    st.success(
                        "Offer Saved Successfully."
                    )
                
                # Advance Reset Tracker to clean the form
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
    # OFFER DATA
    # --------------------------

    # Limit the database query to 500 records to prevent RAM overload
    result = (
        supabase
        .table("offer_management")
        .select("*")
        .order(
            "offer_id",
            desc=True
        )
        .limit(500)
        .execute()
    )

    offers = result.data

    # --------------------------
    # FILTERS
    # --------------------------

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

        search_text = st.text_input(
            "🔍 Search Offer",
            placeholder=
            "Candidate, CAN No or Job No"
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

        offers = [

            item

            for item in offers

            if item["offer_status"]
            == status_filter

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

            searchable_text = (

                candidate_name
                + " "
                + job_name

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
        
        # Limit UI rendering to 25 items to stop Streamlit from freezing
        display_offers = offers[:25]
        if len(offers) > 25:
            st.caption(f"⚠️ Showing top 25 of {len(offers)} results to maintain performance. Use the search bar to find specific records.")


        header = st.columns(
            [3, 3, 2, 2, 3, 1]
        )

        header[0].markdown(
            "**Candidate**"
        )

        header[1].markdown(
            "**Job**"
        )

        header[2].markdown(
            "**Offered CTC**"
        )

        header[3].markdown(
            "**Joining Date**"
        )

        header[4].markdown(
            "**Status**"
        )

        header[5].markdown(
            "**Edit**"
        )

        st.divider()

        # Iterate over the sliced list (display_offers) instead of the full list
        for item in display_offers:

            cols = st.columns(
                [3, 3, 2, 2, 3, 1]
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

            cols[4].markdown(
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

            if cols[5].button(
                "✏️",
                key=f"edit_{item['offer_id']}"
            ):

                st.session_state.edit_offer_id = (
                    item["offer_id"]
                )

                st.rerun()

    else:

        st.info(
            "No offers found."
        )