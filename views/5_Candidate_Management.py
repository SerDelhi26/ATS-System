import streamlit as st
import re
import os
import textwrap
from datetime import datetime, date
from db import supabase
from common import show_logout, show_job_notifications, show_user_profile, render_pagination
from theme import apply_theme
import storage
import ai_parser
import semantic_search

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
    show_user_profile()
    show_logout()
    show_job_notifications()

st.markdown(
    "# 👤 ATS Candidate Management"
)


# ==========================
# FUNCTIONS
# ==========================

def sanitize_filename(filename):
    """Removes special characters to prevent filesystem errors."""
    return storage.sanitize_filename(filename)

def normalize_phone(phone):
    """Strips country codes and spaces. Returns only the last 10 digits."""
    if not phone:
        return ""
    digits = re.sub(r'\D', '', str(phone))
    return digits[-10:] if len(digits) >= 10 else digits


def get_jobs_for_user(
    user_id,
    user_role
):

    if user_role == "Admin":
        return (
            supabase
            .table("job_management")
            .select("job_id, job_reference_no, job_title_id, company_id, category_id, sub_category_id")
            .eq("job_status", "Open")
            .execute()
            .data
        )
    else:
        assigned = (
            supabase
            .table("job_assignment")
            .select("job_id")
            .eq("user_id", user_id)
            .execute()
            .data
        )

        job_ids = [
            item["job_id"]
            for item in assigned
        ]

        if not job_ids:
            return []

        return (
            supabase
            .table("job_management")
            .select("job_id, job_reference_no, job_title_id, company_id, category_id, sub_category_id")
            .in_("job_id", job_ids)
            .eq("job_status", "Open")
            .execute()
            .data
        )


@st.cache_data(ttl=10)
def get_categories():
    return supabase.table("category_master").select("*").execute().data

@st.cache_data(ttl=10)
def get_sub_categories():
    return supabase.table("sub_category_master").select("*").execute().data

def upload_resume(uploaded_file, category_name, sub_category_name, job_ref, file_name):
    return storage.save_candidate_resume(uploaded_file, category_name, sub_category_name, job_ref, custom_name=file_name)

def get_resume_url(file_path):
    return storage.get_file_path("resumes", file_path)


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


def get_recruiters():

    return (
        supabase
        .table("users")
        .select("full_name")
        .execute()
        .data
    )

if "parsed_candidate_data" not in st.session_state:
    st.session_state.parsed_candidate_data = {}

if "uploaded_resume_cache" not in st.session_state:
    st.session_state.uploaded_resume_cache = None

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

if "pending_duplicate_type" not in st.session_state:

    st.session_state.pending_duplicate_type = None

if "trigger_save" not in st.session_state:

    st.session_state.trigger_save = False

editing = False
candidate = None

if st.session_state.edit_candidate_id:

    response = (
        supabase
        .table("candidate_management")
        .select(
            """
            *
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
            candidate.get("created_by_user_id")
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

def map_legacy_candidate_to_job(candidate_entry, job_id):
    """
    Promotes and maps a legacy archive candidate to an active job.
    """
    try:
        leg_id = candidate_entry.get("legacy_candidate_id")
        insert_payload = {
            "job_id": job_id,
            "first_name": candidate_entry.get("first_name", "Candidate"),
            "last_name": candidate_entry.get("last_name", "") or "",
            "email": candidate_entry.get("email"),
            "mobile_no": candidate_entry.get("mobile_no"),
            "current_location": candidate_entry.get("current_location"),
            "experience_years": candidate_entry.get("experience_years", 0) or 0,
            "experience_months": candidate_entry.get("experience_months", 0) or 0,
            "current_company": candidate_entry.get("current_company"),
            "current_designation": candidate_entry.get("current_designation"),
            "current_ctc": float(candidate_entry.get("current_ctc", 0.0) or 0.0),
            "expected_ctc": float(candidate_entry.get("expected_ctc", 0.0) or 0.0),
            "notice_period": candidate_entry.get("notice_period", "30 Days"),
            "notice_negotiable": "No",
            "skills": candidate_entry.get("skills", ""),
            "qualification": candidate_entry.get("qualification"),
            "resume_name": candidate_entry.get("resume_name"),
            "resume_path": candidate_entry.get("resume_path"),
            "candidate_status": "Shortlisted",
            "current_stage": "Shortlisted",
            "remarks": f"Promoted from Legacy Archive (Ref: {candidate_entry.get('candidate_reference_no')})",
            "created_by_user_id": st.session_state.get("user_id"),
            "created_by_name": st.session_state.get("user_name", "Recruiter")
        }
        res = supabase.table("candidate_management").insert(insert_payload).execute()
        if res.data:
            new_cand_id = res.data[0]["candidate_id"]
            current_year = datetime.now().year
            candidate_ref = f"CAN-{current_year}-{new_cand_id:06d}"
            supabase.table("candidate_management").update({"candidate_reference_no": candidate_ref}).eq("candidate_id", new_cand_id).execute()
            if leg_id:
                supabase.table("legacy_candidates").update({
                    "is_migrated_to_active": True,
                    "migrated_candidate_id": new_cand_id,
                    "notice_negotiable": "No"
                }).eq("legacy_candidate_id", leg_id).execute()
            st.cache_data.clear()
            return True
    except Exception as e:
        st.error(f"Error mapping legacy candidate: {e}")
        return False

@st.dialog("🚫 Deactivate Candidate Profile")
def deactivate_candidate_dialog(cand_id, full_name, is_legacy=False, legacy_id=None, raw_cand_data=None):
    st.markdown(f"**Candidate:** `{full_name}`")
    st.caption("Deactivating a candidate automatically excludes them from active job matches, searches, and leaderboards.")
    d_reason = st.selectbox("Deactivation Reason", ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"], key=f"cand_dlg_deact_r_{cand_id}")
    d_note = st.text_input("Remarks / Context", placeholder="e.g. Retired in 2026 / Left Industry...", key=f"cand_dlg_deact_n_{cand_id}")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Confirm Deactivate", type="primary", use_container_width=True, key=f"btn_cand_dlg_deact_{cand_id}"):
            audit_str = f"\n[DEACTIVATED: {d_reason} on {datetime.now().strftime('%Y-%m-%d %H:%M')} by {st.session_state.get('full_name', 'Recruiter')}]: {d_note}"
            if is_legacy:
                leg_id = int(str(legacy_id or cand_id).replace("LEG_", ""))
                supabase.table("legacy_candidates").update({
                    "notice_negotiable": f"Deactivated: {d_reason}"
                }).eq("legacy_candidate_id", leg_id).execute()
            else:
                existing_remarks = (raw_cand_data.get("remarks") if raw_cand_data else "") or ""
                supabase.table("candidate_management").update({
                    "candidate_status": d_reason,
                    "current_stage": d_reason,
                    "remarks": (existing_remarks + audit_str).strip()
                }).eq("candidate_id", cand_id).execute()
            st.toast(f"Candidate {full_name} marked as {d_reason}!", icon="🚫")
            st.cache_data.clear()
            st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True, key=f"btn_cand_dlg_cancel_d_{cand_id}"):
            st.rerun()

@st.dialog("🟢 Reactivate Candidate Profile")
def reactivate_candidate_dialog(cand_id, full_name, is_legacy=False, legacy_id=None, raw_cand_data=None):
    st.markdown(f"**Candidate:** `{full_name}`")
    st.caption("Restore candidate back to active matching & hiring pipeline.")
    r_stage = st.selectbox("Restore Stage", ["Screening", "Shortlisted", "Applied", "New"], key=f"cand_dlg_react_s_{cand_id}")
    r_note = st.text_input("Reactivation Note", placeholder="e.g. Mistakenly deactivated / Back in market...", key=f"cand_dlg_react_n_{cand_id}")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Confirm Reactivation", type="primary", use_container_width=True, key=f"btn_cand_dlg_react_{cand_id}"):
            audit_str = f"\n[REACTIVATED: Restored to {r_stage} on {datetime.now().strftime('%Y-%m-%d %H:%M')} by {st.session_state.get('full_name', 'Recruiter')}]: {r_note}"
            if is_legacy:
                leg_id = int(str(legacy_id or cand_id).replace("LEG_", ""))
                supabase.table("legacy_candidates").update({
                    "notice_negotiable": "No"
                }).eq("legacy_candidate_id", leg_id).execute()
            else:
                existing_remarks = (raw_cand_data.get("remarks") if raw_cand_data else "") or ""
                supabase.table("candidate_management").update({
                    "candidate_status": r_stage,
                    "current_stage": r_stage,
                    "remarks": (existing_remarks + audit_str).strip()
                }).eq("candidate_id", cand_id).execute()
            st.toast(f"Candidate {full_name} reactivated to {r_stage}!", icon="🟢")
            st.cache_data.clear()
            st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True, key=f"btn_cand_dlg_cancel_r_{cand_id}"):
            st.rerun()

# ==========================
# LAYOUT
# ==========================

left_col, right_col = st.columns([1, 3])

with left_col:

    if "candidate_form_reset" not in st.session_state:
        st.session_state.candidate_form_reset = 0

    if st.session_state.get("candidate_created_success_msg"):
        st.success(st.session_state.candidate_created_success_msg)
        del st.session_state.candidate_created_success_msg

    if st.session_state.get("candidate_updated_success_msg"):
        st.success(st.session_state.candidate_updated_success_msg)
        del st.session_state.candidate_updated_success_msg

    # Helper function to generate safe, dynamic keys for resetting
    def get_key(base_name):
        if editing:
            return f"{base_name}_{candidate['candidate_id']}"
        ai_tag = "_ai" if st.session_state.get("parsed_candidate_data") else ""
        return f"{base_name}_new_{st.session_state.candidate_form_reset}{ai_tag}"

    parsed = st.session_state.get("parsed_candidate_data", {})
    def get_val(field_name, default=""):
        if editing and candidate:
            return candidate.get(field_name, default)
        if parsed and field_name in parsed and parsed.get(field_name) is not None:
            return parsed.get(field_name)
        return default

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
        item["job_title_id"]: item["job_title_name"]
        for item in job_titles
    }

    companies = get_companies()
    company_lookup = {
        item["company_id"]: item["company_name"]
        for item in companies
    }

    categories = get_categories()
    category_lookup = {
        item["category_id"]: item["category_name"]
        for item in categories
    }

    sub_categories = get_sub_categories()
    sub_category_lookup = {
        item["sub_category_id"]: item["sub_category_name"]
        for item in sub_categories
    }

    all_jobs = (
        supabase
        .table("job_management")
        .select("job_id, job_reference_no, job_title_id, company_id, category_id, sub_category_id")
        .execute()
        .data
    )

    job_display_lookup = {
        job["job_id"]: f"{job['job_reference_no']} | {job_title_lookup.get(job['job_title_id'], '')}"
        for job in all_jobs
    }

    job_options = ["-- Select Job --"]
    job_lookup = {}
    selected_job_label = "-- Select Job --"

    job_widget_key = f"job_{candidate['candidate_id']}" if editing else f"job_new_{st.session_state.candidate_form_reset}"

    for job in jobs:
        title_name = job_title_lookup.get(job["job_title_id"], "Unknown Job Title")
        label = f"{job['job_reference_no']} | {title_name}"
        job_options.append(label)
        job_lookup[label] = job

        if editing and job["job_id"] == candidate["job_id"]:
            selected_job_label = label

    # Preserve selected job across AI imports
    prev_job_val = st.session_state.get(job_widget_key)
    if prev_job_val and prev_job_val in job_options:
        selected_job_label = prev_job_val

    selected_job = st.selectbox(
        "Job *",
        job_options,
        index=job_options.index(selected_job_label) if selected_job_label in job_options else 0,
        key=job_widget_key
    )

    # ==========================
    # SINGLE RESUME UPLOADER (AFTER JOB *)
    # ==========================
    st.markdown("### 📄 Resume Upload")
    resume_uploader_key = f"resume_{candidate['candidate_id']}" if editing else f"resume_new_{st.session_state.candidate_form_reset}"
    resume = st.file_uploader(
        "Upload Resume *" if not editing else "Upload New Resume (Optional)",
        type=["pdf", "docx", "doc", "txt"],
        key=resume_uploader_key
    )

    if resume is not None:
        st.session_state.uploaded_resume_cache = {
            "name": resume.name,
            "bytes": resume.getvalue(),
            "type": getattr(resume, "type", "application/pdf")
        }

    cached_res = st.session_state.get("uploaded_resume_cache")
    if resume is None and cached_res and not editing:
        st.info(f"📎 **Attached Resume:** {cached_res['name']}")

    active_resume_file = resume if resume is not None else cached_res

    if not editing and active_resume_file is not None:
        ai_col1, ai_col2 = st.columns([2, 1])
        if ai_col1.button("📥 Import From Resume", type="primary", use_container_width=True):
            with st.spinner("🤖 Reading & importing candidate details..."):
                f_bytes = active_resume_file.getvalue() if hasattr(active_resume_file, "getvalue") else active_resume_file["bytes"]
                f_name = active_resume_file.name if hasattr(active_resume_file, "name") else active_resume_file["name"]
                f_type = getattr(active_resume_file, "type", None) or active_resume_file.get("type", "application/pdf")
                
                success, parsed_res, msg = ai_parser.parse_resume_with_ai(
                    file_bytes=f_bytes,
                    filename=f_name,
                    mime_type=f_type
                )
                if success:
                    st.session_state.parsed_candidate_data = parsed_res
                    st.session_state.uploaded_resume_cache = {
                        "name": f_name,
                        "bytes": f_bytes,
                        "type": f_type
                    }
                    st.success("✅ Resume imported! Review the auto-filled fields below.")
                    st.rerun()
                else:
                    st.error(f"❌ AI Parsing Failed: {msg}")

        if ai_col2.button("🔄 Clear Form", use_container_width=True):
            st.session_state.parsed_candidate_data = {}
            st.session_state.uploaded_resume_cache = None
            st.session_state.candidate_form_reset += 1
            st.rerun()

    st.markdown("### 👤 Personal Details")
    col1, col2 = st.columns(2)

    with col1:
        first_name = st.text_input(
            "First Name *",
            value=get_val("first_name", ""),
            key=get_key("first_name")
        )

    with col2:
        last_name = st.text_input(
            "Last Name",
            value=get_val("last_name", ""),
            key=get_key("last_name")
        )
        
    email = st.text_input(
        "Email *",
        value=get_val("email", ""),
        key=get_key("email")
    )

    col1, col2 = st.columns(2)

    with col1:
        mobile_no = st.text_input(
            "Mobile Number *",
            value=get_val("mobile_no", ""),
            key=get_key("mobile_no")
        )

    with col2:
        alternate_mobile = st.text_input(
            "Alternate Number",
            value=get_val("alternate_mobile", ""),
            key=get_key("alternate_mobile")
        )

    current_location = st.text_input(
        "Current Location *",
        value=get_val("current_location", ""),
        key=get_key("location")
    )

    st.markdown("### 📈 Experience")
    col1, col2 = st.columns(2)

    with col1:
        years_options = ["-- Select --"] + list(range(41))
        val_years = get_val("experience_years", 0)
        idx_years = years_options.index(val_years) if val_years in years_options else 0

        experience_years = st.selectbox(
            "Experience Years *",
            years_options,
            index=idx_years,
            key=get_key("exp_years")
        )

    with col2:
        months_options = ["-- Select --"] + list(range(12))
        val_months = get_val("experience_months", 0)
        idx_months = months_options.index(val_months) if val_months in months_options else 0

        experience_months = st.selectbox(
            "Experience Months *",
            months_options,
            index=idx_months,
            key=get_key("exp_months")
        )

    st.markdown("### 🎓 Education")

    qualification = st.text_input(
        "Highest Qualification *",
        value=get_val("qualification", ""),
        key=get_key("qual")
    )

    education_details = st.text_area(
        "Educational Details",
        value=get_val("education_details", ""),
        key=get_key("edu")
    )

    st.markdown("### 💼 Employment")

    current_company = st.text_input(
        "Current Company *",
        value=get_val("current_company", ""),
        key=get_key("company")
    )

    current_designation = st.text_input(
        "Current Designation *",
        value=get_val("current_designation", ""),
        key=get_key("designation")
    )

    col1, col2 = st.columns(2)

    with col1:
        current_ctc = st.number_input(
            "Current CTC",
            min_value=0.0,
            value=float(get_val("current_ctc", 0.0) or 0.0),
            key=get_key("current_ctc")
        )

    with col2:
        expected_ctc = st.number_input(
            "Expected CTC",
            min_value=0.0,
            value=float(get_val("expected_ctc", 0.0) or 0.0),
            key=get_key("expected_ctc")
        )

    st.markdown("### ⏳ Notice & Availability")
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
        val_np = candidate["notice_period"] if editing and candidate.get("notice_period") in notice_period_options else "-- Select Notice Period --"
        notice_period = st.selectbox(
            "Notice Period *",
            notice_period_options,
            index=notice_period_options.index(val_np) if val_np in notice_period_options else 0,
            key=get_key("notice_period")
        )

    with col2:
        notice_negotiable_options = [
            "-- Select --",
            "Yes",
            "No",
            "Not Known"
        ]
        val_nn = candidate["notice_negotiable"] if editing and candidate.get("notice_negotiable") in notice_negotiable_options else "-- Select --"
        notice_negotiable = st.selectbox(
            "Notice Negotiable *",
            notice_negotiable_options,
            index=notice_negotiable_options.index(val_nn) if val_nn in notice_negotiable_options else 0,
            key=get_key("notice_negotiable")
        )

    st.markdown("### 🛠 Skills")

    skills = st.text_area(
        "Skills *",
        value=get_val("skills", ""),
        key=get_key("skills")
    )

    candidate_status_options = [
        "New",
        "Screening",
        "Shortlisted",
        "Selected",         
        "Offer Released",   
        "Offer Accepted",   
        "Offer Rejected",   
        "Hired",           
        "No Show",          
        "Hold",
        "Rejected",
        "Retired",
        "Deceased",
        "Inactive / Left Market",
        "Blacklisted"
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
        key=get_key("status")
    )

    remarks = st.text_area(
        "Remarks",
        value=candidate["remarks"] if editing and candidate.get("remarks") else "",
        key=get_key("remarks")
    )

    # ==========================
    # SMART DUPLICATE WARNING UI (3-TIER POLICY)
    # ==========================
    if st.session_state.pending_duplicate:
        existing = st.session_state.pending_duplicate
        dup_type = st.session_state.pending_duplicate_type

        existing_job_id = existing["job_id"]
        existing_job = job_display_lookup.get(existing_job_id, "Unknown Job")

        existing_company_id = next((j["company_id"] for j in all_jobs if j["job_id"] == existing_job_id), None)
        existing_company_name = company_lookup.get(existing_company_id, "Unknown Company") if existing_company_id else "Unknown Company"

        if dup_type == "SAME_JOB":
            st.error(f"🚨 **Exact Duplicate Blocked:** {existing['first_name']} {existing['last_name']} has already applied for this exact job (**{existing_job}**). Direct duplicate applications for the same job are restricted.")
            with st.container(border=True):
                st.markdown(f"**Existing Candidate:** `{existing['candidate_reference_no']}` | **Current Stage:** `{existing.get('current_stage', 'Unknown')}` | **Added By:** `{existing.get('created_by_name', 'Unknown')}`")
                col1, col2 = st.columns(2)
                if col1.button("👁️ View / Edit Existing Application", use_container_width=True):
                    st.session_state.edit_candidate_id = existing["candidate_id"]
                    st.session_state.pending_duplicate = None
                    st.session_state.pending_duplicate_type = None
                    st.rerun()
                if col2.button("❌ Cancel Submission", use_container_width=True):
                    st.session_state.pending_duplicate = None
                    st.session_state.pending_duplicate_type = None
                    st.rerun()

        elif dup_type == "SAME_COMPANY":
            past_date_str = str(existing.get('created_on') or existing.get('created_at', ''))[:10]
            st.warning(f"⚠️ **Same Company Soft-Lock:** Candidate previously applied to **{existing_company_name}** on **{past_date_str}** for Job **{existing_job}** (Stage: **{existing.get('current_stage', 'Unknown')}**).")
            with st.container(border=True):
                st.markdown(f"**Previous Record:** `{existing['candidate_reference_no']}` — {existing['first_name']} {existing['last_name']} ({existing.get('current_designation', '')})")
                soft_lock_confirm = st.checkbox("☑️ I confirm management has approved considering this candidate for this new role at the same company.", value=False, key="soft_lock_confirm")
                
                col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
                if col1.button("✅ Proceed & Save for New Role", disabled=not soft_lock_confirm, use_container_width=True):
                    st.session_state.duplicate_override = True
                    st.session_state.pending_duplicate = None
                    st.session_state.pending_duplicate_type = None
                    st.session_state.trigger_save = True
                    st.rerun()
                if col2.button("👁️ View Previous Record", use_container_width=True):
                    st.session_state.edit_candidate_id = existing["candidate_id"]
                    st.session_state.pending_duplicate = None
                    st.session_state.pending_duplicate_type = None
                    st.rerun()
                if col3.button("❌ Cancel", use_container_width=True):
                    st.session_state.pending_duplicate = None
                    st.session_state.pending_duplicate_type = None
                    st.rerun()

        else:
            # GLOBAL ATS or NAME_MATCH
            st.info(f"ℹ️ **Global ATS Profile Found:** This candidate profile is already registered in your ATS under **{existing_company_name}** for **{existing_job}**.")
            with st.container(border=True):
                st.markdown(f"**Found Profile:** `{existing['candidate_reference_no']}` — `{existing['first_name']} {existing['last_name']}` ({existing.get('current_designation', '')} @ {existing.get('current_company', '')})")
                
                col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
                if col1.button("📋 Auto-Fill Form from Profile", use_container_width=True):
                    st.session_state.parsed_candidate_data = existing
                    st.session_state.candidate_form_reset += 1
                    st.session_state.pending_duplicate = None
                    st.session_state.pending_duplicate_type = None
                    st.success("Candidate profile loaded into form!")
                    st.rerun()
                if col2.button("✅ Save as New Application", use_container_width=True):
                    st.session_state.duplicate_override = True
                    st.session_state.pending_duplicate = None
                    st.session_state.pending_duplicate_type = None
                    st.session_state.trigger_save = True
                    st.rerun()
                if col3.button("❌ Cancel", use_container_width=True):
                    st.session_state.pending_duplicate = None
                    st.session_state.pending_duplicate_type = None
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

        cand_status = candidate.get("candidate_status") or candidate.get("current_stage") or ""
        cand_is_deact = cand_status in ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"]

        if cand_is_deact:
            with st.expander("🟢 Reactivate Candidate Profile", expanded=True):
                st.caption("This candidate is currently deactivated. You can restore them back to the active talent pool.")
                r_stage = st.selectbox("Restore to Stage", ["Screening", "Shortlisted", "Applied", "New"], key="edit_form_react_stage")
                r_note = st.text_input("Reactivation Note", placeholder="e.g. Mistakenly deactivated / Back in market...", key="edit_form_react_note")
                if st.button("🟢 Confirm Reactivate Profile", type="primary", use_container_width=True, key="edit_form_btn_react"):
                    audit_str = f"\n[REACTIVATED: Restored to {r_stage} on {datetime.now().strftime('%Y-%m-%d %H:%M')} by {st.session_state.get('full_name', 'Recruiter')}]: {r_note}"
                    existing_remarks = candidate.get("remarks") or ""
                    supabase.table("candidate_management").update({
                        "candidate_status": r_stage,
                        "current_stage": r_stage,
                        "remarks": (existing_remarks + audit_str).strip()
                    }).eq("candidate_id", candidate["candidate_id"]).execute()
                    st.session_state.edit_candidate_id = None
                    st.session_state.candidate_updated_success_msg = f"Candidate profile successfully reactivated to {r_stage}!"
                    st.rerun()
        else:
            with st.expander("🚫 Deactivate / Archive Candidate Profile", expanded=False):
                st.caption("Deactivating a candidate (e.g. Retirement, Death, Blacklist, Left Market) automatically excludes them from all job matches, searches, and leaderboards.")
                deact_reason = st.selectbox(
                    "Deactivation Reason",
                    ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"],
                    key="edit_form_deact_reason"
                )
                deact_note = st.text_input("Remarks / Context", placeholder="e.g. Retired in 2026 / Left Industry...", key="edit_form_deact_note")
                if st.button("🚫 Confirm Deactivate Profile", type="primary", use_container_width=True, key="edit_form_btn_deact"):
                    audit_str = f"\n[DEACTIVATED: {deact_reason} on {datetime.now().strftime('%Y-%m-%d %H:%M')} by {st.session_state.get('full_name', 'Recruiter')}]: {deact_note}"
                    existing_remarks = candidate.get("remarks") or ""
                    supabase.table("candidate_management").update({
                        "candidate_status": deact_reason,
                        "current_stage": deact_reason,
                        "remarks": (existing_remarks + audit_str).strip()
                    }).eq("candidate_id", candidate["candidate_id"]).execute()
                    st.session_state.edit_candidate_id = None
                    st.session_state.candidate_updated_success_msg = f"Candidate profile marked as {deact_reason}."
                    st.rerun()

    else:

        save_candidate = st.button(
            "Save Candidate",
            use_container_width=True
        )

        cancel_edit = False

    if cancel_edit:

        st.session_state.edit_candidate_id = None

        st.session_state.pending_duplicate = None
        st.session_state.pending_duplicate_type = None

        st.session_state.duplicate_override = False
        st.session_state.trigger_save = False

        st.session_state.candidate_form_reset += 1

        st.rerun()

    # TRIGGER SAVE EITHER BY BUTTON CLICK OR BY OUR MEMORY FLAG
    if save_candidate or st.session_state.get("trigger_save", False):
        
        # Reset the flag immediately so it doesn't loop
        if st.session_state.get("trigger_save", False):
            st.session_state.trigger_save = False

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

        # NORMALIZE PHONES BEFORE VALIDATING LENGTH TO FIX INVISIBLE SPACES
        norm_mobile_val = normalize_phone(mobile_no)
        norm_alt_val = normalize_phone(alternate_mobile)

        if not mobile_no.strip():

            validation_errors.append(
                "Mobile Number is mandatory."
            )

        elif len(norm_mobile_val) != 10:

            validation_errors.append(
                "Please enter a valid 10-digit Mobile Number."
            )

        if (
            alternate_mobile.strip()
            and
            len(norm_alt_val) != 10
        ):

            validation_errors.append(
                "Please enter a valid 10-digit Alternate Mobile Number."
            )

        if (
            mobile_no.strip()
            and
            alternate_mobile.strip()
            and
            norm_mobile_val == norm_alt_val
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
            validation_errors.append("Skills are mandatory.")

        resume_to_save = resume if resume is not None else st.session_state.get("uploaded_resume_cache")
        if not editing and not resume_to_save:
            validation_errors.append("Resume is mandatory.")

        if validation_errors:

            for error in validation_errors:

                st.error(error)

        else:

            # ==========================
            # DUPLICATE CHECK ENGINE
            # ==========================

            selected_job_record = (
                job_lookup[
                    selected_job
                ]
            )
            
            selected_job_id = selected_job_record["job_id"]
            selected_company_id = next((j["company_id"] for j in all_jobs if j["job_id"] == selected_job_id), None)

            norm_email = email.strip().lower()
            norm_mobile = normalize_phone(mobile_no)
            norm_alt = normalize_phone(alternate_mobile)
            norm_first = first_name.strip().lower()
            norm_last = last_name.strip().lower()

            # Build dynamic OR conditions
            or_conditions = []
            
            if norm_email:
                or_conditions.append(f"email.eq.{norm_email}")
                
            if norm_mobile:
                or_conditions.append(f"mobile_no.eq.{norm_mobile}")
                or_conditions.append(f"alternate_mobile.eq.{norm_mobile}")
                
            if norm_alt:
                or_conditions.append(f"mobile_no.eq.{norm_alt}")
                or_conditions.append(f"alternate_mobile.eq.{norm_alt}")
                
            if norm_first and norm_last:
                or_conditions.append(f"and(first_name.ilike.{norm_first},last_name.ilike.{norm_last})")

            or_string = ",".join(or_conditions)

            duplicates = (
                supabase
                .table(
                    "candidate_management"
                )
                .select("*") 
                .or_(
                    or_string
                )
                .execute()
            )

            # Ignore self during edit
            if editing:

                duplicates.data = [

                    item

                    for item in duplicates.data

                    if item["candidate_id"]
                    != candidate["candidate_id"]

                ]


            if duplicates.data and not st.session_state.duplicate_override:
                
                highest_priority_dup = None
                dup_type = None
                priority_map = {"SAME_JOB": 4, "SAME_COMPANY": 3, "GLOBAL": 2, "NAME_MATCH": 1, None: 0}
                
                for d in duplicates.data:
                    d_email = (d.get("email") or "").strip().lower()
                    d_mobile = normalize_phone(d.get("mobile_no"))
                    d_alt = normalize_phone(d.get("alternate_mobile"))
                    d_first = (d.get("first_name") or "").strip().lower()
                    d_last = (d.get("last_name") or "").strip().lower()
                    
                    d_job_id = d["job_id"]
                    d_company_id = next((j["company_id"] for j in all_jobs if j["job_id"] == d_job_id), None)

                    # Cooling-Off Period Logic (180 Days)
                    days_old = 0
                    created_at_str = d.get("created_on") or d.get("created_at")
                    if created_at_str:
                        try:
                            clean_time = created_at_str.split(".")[0].split("+")[0].replace("Z", "")
                            created_at_date = datetime.strptime(clean_time, "%Y-%m-%dT%H:%M:%S")
                            days_old = (datetime.now() - created_at_date).days
                        except:
                            pass
                    
                    # Determine Match Criteria
                    is_contact_match = False
                    if norm_email and norm_email == d_email: is_contact_match = True
                    if norm_mobile and norm_mobile in [d_mobile, d_alt]: is_contact_match = True
                    if norm_alt and norm_alt in [d_mobile, d_alt]: is_contact_match = True
                    
                    current_dup_type = None
                    if is_contact_match:
                        if d_job_id == selected_job_id:
                            current_dup_type = "SAME_JOB"
                        elif d_company_id == selected_company_id:
                            current_dup_type = "SAME_COMPANY"
                        else:
                            current_dup_type = "GLOBAL"
                    elif norm_first == d_first and norm_last == d_last and norm_first != "":
                        current_dup_type = "NAME_MATCH"

                    # Apply Cooling Off Period for non-job matches
                    if current_dup_type in ["SAME_COMPANY", "GLOBAL", "NAME_MATCH"] and days_old > 180:
                        current_dup_type = None
                        
                    # Apply highest threat level
                    if current_dup_type and priority_map[current_dup_type] > priority_map[dup_type]:
                        dup_type = current_dup_type
                        highest_priority_dup = d
                        
                if highest_priority_dup:
                    st.session_state.pending_duplicate = highest_priority_dup
                    st.session_state.pending_duplicate_type = dup_type
                    st.rerun()


            # ==========================
            # SAVE DATA
            # ==========================

            candidate_data = {

                "job_id":
                    selected_job_record["job_id"],

                "first_name":
                    first_name.strip(),

                "last_name":
                    last_name.strip(),

                "email":
                    email.strip().lower(),

                # Save the sanitized phone numbers to ensure a clean database
                "mobile_no":
                    norm_mobile_val,

                "alternate_mobile":
                    norm_alt_val,

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
                    
                "current_stage":
                    candidate_status,   # <-- Keeps stages in sync upon initial creation/edit

                "remarks":
                    remarks.strip()

            }

            # Extract category & job ref for folder hierarchy
            job_ref = selected_job_record.get("job_reference_no", "General_Job")
            job_cat_id = selected_job_record.get("category_id")
            job_subcat_id = selected_job_record.get("sub_category_id")
            category_name = category_lookup.get(job_cat_id, "General")
            sub_category_name = sub_category_lookup.get(job_subcat_id, "General")

            if editing:
                candidate_data["updated_on"] = datetime.now().isoformat()
                if resume_to_save:
                    cand_ref_name = candidate.get("candidate_reference_no") or f"CAN-{candidate['candidate_id']:06d}"
                    res_display_name = resume.name if resume else resume_to_save["name"]
                    unique_file_name = f"{cand_ref_name}_{res_display_name}"
                    new_resume_path = upload_resume(
                        resume_to_save,
                        category_name,
                        sub_category_name,
                        job_ref,
                        unique_file_name
                    )
                    if new_resume_path:
                        candidate_data["resume_name"] = res_display_name
                        candidate_data["resume_path"] = new_resume_path

                (
                    supabase
                    .table("candidate_management")
                    .update(candidate_data)
                    .eq("candidate_id", candidate["candidate_id"])
                    .execute()
                )

                st.success("Candidate Updated Successfully.")
                st.session_state.edit_candidate_id = None
                st.session_state.duplicate_override = False
                st.session_state.pending_duplicate = None
                st.session_state.pending_duplicate_type = None
                st.session_state.parsed_candidate_data = {}
                st.session_state.uploaded_resume_cache = None
                st.session_state.candidate_form_reset += 1
                st.rerun()

            else:
                candidate_data["created_by_user_id"] = st.session_state.user_id
                candidate_data["created_by_name"] = st.session_state.user_name

                insert_result = (
                    supabase
                    .table("candidate_management")
                    .insert(candidate_data)
                    .execute()
                )

                candidate = insert_result.data[0]
                current_year = datetime.now().year
                candidate_ref = f"CAN-{current_year}-{candidate['candidate_id']:06d}"

                resume_path = None
                if resume_to_save:
                    res_display_name = resume.name if resume else resume_to_save["name"]
                    unique_file_name = f"{candidate_ref}_{res_display_name}"
                    resume_path = upload_resume(
                        resume_to_save,
                        category_name,
                        sub_category_name,
                        job_ref,
                        unique_file_name
                    )

                    if not resume_path:
                        st.error("Resume upload failed. Candidate was not saved completely.")
                        st.stop()

                (
                    supabase
                    .table("candidate_management")
                    .update({
                        "candidate_reference_no": candidate_ref,
                        "resume_name": (resume.name if resume else resume_to_save["name"]) if resume_to_save else None,
                        "resume_path": resume_path
                    })
                    .eq("candidate_id", candidate["candidate_id"])
                    .execute()
                )

                st.session_state.candidate_created_success_msg = f"Candidate Created : {candidate_ref}"
                st.session_state.duplicate_override = False
                st.session_state.pending_duplicate = None
                st.session_state.pending_duplicate_type = None
                st.session_state.parsed_candidate_data = {}
                st.session_state.uploaded_resume_cache = None
                st.session_state.candidate_form_reset += 1
                st.rerun()
 # ==========================
# RIGHT PANEL
# ==========================

with right_col:
    tab_dir, tab_legacy, tab_ai_search, tab_merge = st.tabs([
        "📋 Live Candidate Directory",
        "🏛️ Legacy & Deactivated Archive",
        "🔍 AI Candidate Search",
        "🛡️ Duplicate Cleanup & Merge"
    ])

    # ----------------------------------------------------
    # TAB 1: CANDIDATE DIRECTORY (STANDARD VIEW)
    # ----------------------------------------------------
    with tab_dir:
        st.markdown("## 📋 Live Candidate Directory (Active Job Pipeline)")
        st.caption("Candidates submitted for active job openings. To browse or reactivate historical talent and deactivated records, open the **🏛️ Legacy & Deactivated Archive** tab.")
        
        filter_col1, filter_col2, filter_col3 = st.columns(3)

        with filter_col1:
            # Included granular statuses and deactivation states
            status_filter = st.selectbox(
                "Status",
                [
                    "All Status",
                    "New",
                    "Screening",
                    "Shortlisted",
                    "Selected",
                    "Offer Released",
                    "Offer Accepted",
                    "Offer Rejected",
                    "Hired",
                    "Hold",
                    "No Show",
                    "Rejected",
                    "Retired",
                    "Deceased",
                    "Inactive / Left Market",
                    "Blacklisted"
                ]
            )

        if st.session_state.get("resume_path_selected"):
            cv_path = st.session_state.resume_path_selected
            cv_bytes = storage.read_file_bytes(cv_path)
            cv_display_name = os.path.basename(cv_path)
            if cv_bytes:
                st.download_button(
                    label=f"⬇️ Download / Open Selected CV ({cv_display_name})",
                    data=cv_bytes,
                    file_name=cv_display_name,
                    mime=storage.get_mime_type(cv_display_name),
                    use_container_width=True
                )
            else:
                st.warning(f"Resume file '{cv_display_name}' was not found in storage directory ({storage.STORAGE_BASE_DIR}).")

        search_text = st.text_input(
            "🔍 Search Candidate",
            placeholder="CAN No, Name, Email, Mobile or Company",
            key="cand_dir_search"
        )

        job_filter_options = ["All Jobs"]
        for job in jobs:
            title_name = job_title_lookup.get(job["job_title_id"], "Unknown Job Title")
            job_filter_options.append(f"{job['job_reference_no']} | {title_name}")

        with filter_col2:
            job_filter = st.selectbox("Job", job_filter_options, key="cand_dir_job_filter")

        with filter_col3:
            recruiter_filter = "All Recruiters"
            if st.session_state.user_role == "Admin":
                users = get_recruiters()
                recruiter_options = ["All Recruiters"]
                recruiter_options.extend(sorted(list({user["full_name"] for user in users})))
                recruiter_filter = st.selectbox("Recruiter", recruiter_options, key="cand_dir_rec_filter")

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
                current_stage,
                created_by_name,
                created_by_user_id,
                experience_years,
                experience_months,
                resume_path,
                remarks
                """
            )
            .order("candidate_id", desc=True)
            .limit(2000)
            .execute()
        )

        candidates = result.data
        filtered_candidates = candidates

        if status_filter != "All Status":
            filtered_candidates = [
                c for c in filtered_candidates
                if c["candidate_status"] == status_filter or c["current_stage"] == status_filter
            ]

        if job_filter != "All Jobs":
            selected_job_id = job_lookup[job_filter]["job_id"]
            filtered_candidates = [
                c for c in filtered_candidates
                if c["job_id"] == selected_job_id
            ]

        if recruiter_filter != "All Recruiters":
            filtered_candidates = [
                c for c in filtered_candidates
                if c["created_by_name"] == recruiter_filter
            ]

        if search_text:
            search_results = []
            for candidate in filtered_candidates:
                full_name = f"{candidate.get('first_name','')} {candidate.get('last_name','')}".strip()
                searchable_text = (
                    f"{candidate.get('candidate_reference_no','')} "
                    f"{full_name} "
                    f"{candidate.get('email','')} "
                    f"{candidate.get('mobile_no','')} "
                    f"{candidate.get('current_company','')} "
                    f"{candidate.get('skills','')}"
                )
                if search_text.lower() in searchable_text.lower():
                    search_results.append(candidate)
            filtered_candidates = search_results

        candidates = filtered_candidates

        if candidates:
            display_candidates, current_page, total_pages = render_pagination(
                candidates, page_size_default=25, key_prefix="candidates"
            )

            headers = st.columns([1.8, 2.5, 2.5, 2, 1.8, 1.6, 2.2, 1.8, 1.2, 1, 1.2])
            headers[0].markdown("**CAN No**")
            headers[1].markdown("**Job No**")
            headers[2].markdown("**Candidate Name**")
            headers[3].markdown("**Company**")
            headers[4].markdown("**Mobile**")
            headers[5].markdown("**Experience**")
            headers[6].markdown("**Status**")
            headers[7].markdown("**Entered By**")
            headers[8].markdown("**Resume**")
            headers[9].markdown("**Edit**")
            headers[10].markdown("**Action**")

            st.divider()

            for candidate in display_candidates:
                cols = st.columns([1.8, 2.5, 2.5, 2, 1.8, 1.6, 2.2, 1.8, 1.2, 1, 1.2])
                full_name = f"{candidate.get('first_name','')} {candidate.get('last_name','')}".strip()
                experience = f"{candidate.get('experience_years',0)}Y {candidate.get('experience_months',0)}M"

                cols[0].write(candidate.get("candidate_reference_no", ""))
                cols[1].write(job_display_lookup.get(candidate["job_id"], ""))
                cols[2].write(full_name)
                cols[3].write(candidate.get("current_company", ""))
                cols[4].write(candidate.get("mobile_no", ""))
                cols[5].write(experience)

                master_stage = candidate.get("current_stage")
                manual_status = candidate.get("candidate_status", "")
                granular_statuses = ["Offer Released", "Offer Accepted", "Offer Rejected", "No Show", "Hired", "Retired", "Deceased", "Inactive / Left Market", "Blacklisted"]
                if manual_status in granular_statuses:
                    status = manual_status
                else:
                    status = master_stage if master_stage else manual_status

                status_colors = {
                    "New": "#2563EB",
                    "Screening": "#F59E0B",
                    "Shortlisted": "#8B5CF6",
                    "Selected": "#0EA5E9",
                    "Offer Released": "#3B82F6",
                    "Offer Accepted": "#14B8A6",
                    "Offer Rejected": "#DC2626",
                    "Hired": "#10B981",
                    "Joined": "#10B981",
                    "No Show": "#94A3B8",
                    "Hold": "#EAB308",
                    "Rejected": "#DC2626",
                    "Retired": "#475569",
                    "Deceased": "#000000",
                    "Inactive / Left Market": "#94A3B8",
                    "Blacklisted": "#991B1B"
                }
                color = status_colors.get(status, "#64748B")

                cols[6].markdown(
                    f"""
                    <div style="background:{color}; color:white; padding:6px 12px; border-radius:12px; text-align:center; font-size:14px; white-space:nowrap; display:inline-block;">
                    {status}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                cols[7].write(candidate.get("created_by_name", ""))

                if candidate.get("resume_path"):
                    if cols[8].button("📄 CV", key=f"view_{candidate['candidate_id']}"):
                        st.session_state.resume_path_selected = candidate["resume_path"]
                        st.rerun()
                else:
                    cols[8].write("-")

                can_edit = False
                if st.session_state.user_role == "Admin":
                    can_edit = True
                elif candidate.get("created_by_user_id") == st.session_state.user_id:
                    can_edit = True

                if can_edit:
                    if cols[9].button("✏️", key=f"edit_{candidate['candidate_id']}"):
                        st.session_state.edit_candidate_id = candidate["candidate_id"]
                        st.rerun()
                else:
                    cols[9].write("🔒")

                is_row_deact = (status in ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"]) or (manual_status in ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"]) or (master_stage in ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"])
                if is_row_deact:
                    if cols[10].button("🟢", key=f"tbl_btn_react_{candidate['candidate_id']}", help="Reactivate Candidate Profile"):
                        reactivate_candidate_dialog(candidate["candidate_id"], full_name, is_legacy=False, raw_cand_data=candidate)
                else:
                    if cols[10].button("🚫", key=f"tbl_btn_deact_{candidate['candidate_id']}", help="Deactivate or Archive Profile"):
                        deactivate_candidate_dialog(candidate["candidate_id"], full_name, is_legacy=False, raw_cand_data=candidate)
        else:
            st.info("No candidates found.")

    # ----------------------------------------------------
    # TAB 2: LEGACY & DEACTIVATED ARCHIVE (500K+ HISTORICAL TALENT)
    # ----------------------------------------------------
    with tab_legacy:
        st.markdown("## 🏛️ Legacy & Deactivated Candidate Archive")
        st.caption("Search, filter, inspect, and manage historical candidate records, including active archive talent and deactivated profiles (Retired, Deceased, Inactive, Blacklisted).")

        # 1. Fetch legacy candidates
        leg_raw_data = (
            supabase
            .table("legacy_candidates")
            .select(
                "legacy_candidate_id, candidate_reference_no, first_name, last_name, email, mobile_no, alternate_mobile, current_company, current_designation, experience_years, experience_months, current_ctc, expected_ctc, current_location, notice_period, notice_negotiable, skills, qualification, education_details, resume_name, resume_path, created_on, is_migrated_to_active, migrated_candidate_id"
            )
            .order("legacy_candidate_id", desc=False)
            .limit(3000)
            .execute()
            .data or []
        )

        # Compute status for each legacy record
        for lc in leg_raw_data:
            nn = str(lc.get("notice_negotiable") or "").strip()
            if nn.startswith("Deactivated:"):
                lc["status"] = nn.replace("Deactivated:", "").strip()
                lc["is_deactivated"] = True
            else:
                lc["status"] = "Active Archive"
                lc["is_deactivated"] = False

        # Summary Metrics Cards
        total_leg_count = len(leg_raw_data)
        deact_leg_count = sum(1 for lc in leg_raw_data if lc["is_deactivated"])
        active_leg_count = total_leg_count - deact_leg_count

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Total Historical Records", f"{total_leg_count:,}")
        with m2:
            st.metric("Active Archive Talent", f"{active_leg_count:,}")
        with m3:
            st.metric("Deactivated Records", f"{deact_leg_count:,}")

        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

        # Filters Row
        leg_f1, leg_f2, leg_f3 = st.columns([0.35, 0.35, 0.30])
        with leg_f1:
            leg_status_filter = st.selectbox(
                "Archive Status / Lifecycle",
                [
                    "All Archive Records",
                    "🚫 All Deactivated Only",
                    "Retired Only",
                    "Deceased Only",
                    "Inactive / Left Market Only",
                    "Blacklisted Only",
                    "🟢 Active Archive Talent Only"
                ],
                key="leg_status_filter"
            )
        with leg_f2:
            leg_search = st.text_input(
                "🔍 Search Historical Talent",
                placeholder="LEG Ref, Name, Mobile, Email, Company, Skill, Location...",
                key="leg_search_query"
            )
        with leg_f3:
            leg_location_filter = st.selectbox(
                "Filter by Location",
                ["All Locations"] + sorted(list({lc.get("current_location") for lc in leg_raw_data if lc.get("current_location")})),
                key="leg_loc_filter"
            )

        # Filter Logic
        filtered_legacy = leg_raw_data

        if leg_status_filter == "🚫 All Deactivated Only":
            filtered_legacy = [lc for lc in filtered_legacy if lc["is_deactivated"]]
        elif leg_status_filter == "Retired Only":
            filtered_legacy = [lc for lc in filtered_legacy if lc["status"] == "Retired"]
        elif leg_status_filter == "Deceased Only":
            filtered_legacy = [lc for lc in filtered_legacy if lc["status"] == "Deceased"]
        elif leg_status_filter == "Inactive / Left Market Only":
            filtered_legacy = [lc for lc in filtered_legacy if lc["status"] == "Inactive / Left Market"]
        elif leg_status_filter == "Blacklisted Only":
            filtered_legacy = [lc for lc in filtered_legacy if lc["status"] == "Blacklisted"]
        elif leg_status_filter == "🟢 Active Archive Talent Only":
            filtered_legacy = [lc for lc in filtered_legacy if not lc["is_deactivated"]]

        if leg_location_filter != "All Locations":
            filtered_legacy = [lc for lc in filtered_legacy if lc.get("current_location") == leg_location_filter]

        if leg_search:
            s_q = leg_search.lower()
            filtered_legacy = [
                lc for lc in filtered_legacy
                if s_q in f"{lc.get('candidate_reference_no','')} {lc.get('first_name','')} {lc.get('last_name','')} {lc.get('email','')} {lc.get('mobile_no','')} {lc.get('current_company','')} {lc.get('current_designation','')} {lc.get('skills','')} {lc.get('current_location','')}".lower()
            ]

        # Table Display
        if filtered_legacy:
            st.markdown(f"**Showing {len(filtered_legacy):,} candidate record(s)**")
            
            disp_legacy, leg_page, leg_total_pages = render_pagination(
                filtered_legacy,
                page_size_default=25,
                key_prefix="leg_archive_dir"
            )

            # Table Header
            h_cols = st.columns([1.6, 2.0, 1.8, 1.6, 1.3, 1.3, 1.8, 0.9, 1.2, 1.5])
            h_cols[0].markdown("**LEG No**")
            h_cols[1].markdown("**Candidate Name**")
            h_cols[2].markdown("**Company**")
            h_cols[3].markdown("**Mobile**")
            h_cols[4].markdown("**Experience**")
            h_cols[5].markdown("**Location**")
            h_cols[6].markdown("**Status**")
            h_cols[7].markdown("**CV**")
            h_cols[8].markdown("**Action**")
            h_cols[9].markdown("**Map to Job**")

            st.markdown("<hr style='margin:4px 0 10px 0;'>", unsafe_allow_html=True)

            status_colors = {
                "Active Archive": "#4F46E5",
                "Retired": "#475569",
                "Deceased": "#000000",
                "Inactive / Left Market": "#64748B",
                "Blacklisted": "#991B1B"
            }

            for lc in disp_legacy:
                cols = st.columns([1.6, 2.0, 1.8, 1.6, 1.3, 1.3, 1.8, 0.9, 1.2, 1.5])
                full_name = f"{lc.get('first_name', '')} {lc.get('last_name', '')}".strip()
                exp_str = f"{lc.get('experience_years', 0)}Y {lc.get('experience_months', 0)}M"
                c_status = lc["status"]
                c_color = status_colors.get(c_status, "#4F46E5")

                cols[0].write(lc.get("candidate_reference_no", f"LEG-{lc['legacy_candidate_id']}"))
                cols[1].write(full_name)
                cols[2].write(lc.get("current_company", "-"))
                cols[3].write(lc.get("mobile_no", "-"))
                cols[4].write(exp_str)
                cols[5].write(lc.get("current_location", "-"))

                cols[6].markdown(
                    f"""
                    <div style="background:{c_color}; color:white; padding:4px 10px; border-radius:12px; text-align:center; font-size:12px; white-space:nowrap; display:inline-block; font-weight:600;">
                    {c_status}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if lc.get("resume_path"):
                    if cols[7].button("📄", key=f"leg_cv_{lc['legacy_candidate_id']}", help=f"View / Download CV ({lc.get('resume_name', 'Resume')})"):
                        st.session_state.resume_path_selected = lc["resume_path"]
                        st.rerun()
                else:
                    cols[7].write("-")

                # Action Button: Reactivate or Deactivate modal
                if lc["is_deactivated"]:
                    if cols[8].button("🟢", key=f"leg_btn_r_{lc['legacy_candidate_id']}", help="Reactivate Candidate Profile"):
                        reactivate_candidate_dialog(
                            f"LEG_{lc['legacy_candidate_id']}",
                            full_name,
                            is_legacy=True,
                            legacy_id=lc["legacy_candidate_id"],
                            raw_cand_data=lc
                        )
                else:
                    if cols[8].button("🚫", key=f"leg_btn_d_{lc['legacy_candidate_id']}", help="Deactivate or Archive Profile"):
                        deactivate_candidate_dialog(
                            f"LEG_{lc['legacy_candidate_id']}",
                            full_name,
                            is_legacy=True,
                            legacy_id=lc["legacy_candidate_id"],
                            raw_cand_data=lc
                        )

                # Map to Job Action
                if lc.get("is_migrated_to_active"):
                    cols[9].caption("✅ Mapped")
                else:
                    with cols[9].popover("📥 Map", help="Map to Job"):
                        st.markdown(f"**Map `{full_name}` to Job**")
                        target_job_sel = st.selectbox(
                            "Select Target Job Requisition",
                            job_filter_options[1:] if len(job_filter_options) > 1 else ["No Active Jobs"],
                            key=f"leg_map_job_sel_{lc['legacy_candidate_id']}"
                        )
                        if st.button("Confirm Map", key=f"leg_conf_map_btn_{lc['legacy_candidate_id']}", type="primary", use_container_width=True):
                            if target_job_sel in job_lookup:
                                tgt_id = job_lookup[target_job_sel]["job_id"]
                                if map_legacy_candidate_to_job(lc, tgt_id):
                                    st.toast(f"Candidate {full_name} mapped to {target_job_sel}!", icon="📥")
                                    st.rerun()
        else:
            st.info("No legacy candidate records found matching your filter / search criteria.")

    # ----------------------------------------------------
    # TAB 3: AI CANDIDATE SEARCH
    # ----------------------------------------------------
    with tab_ai_search:
        st.markdown("### 🔍 AI Candidate Search")
        st.caption("Search across all candidates and resumes using plain conversational English queries (e.g. skills, experience, location, budget).")

        ai_query = st.text_input(
            "💬 Enter your search prompt:",
            placeholder="e.g. Agri sales manager with 4-8 yrs in Telangana under 9 LPA having pesticide knowledge...",
            key="cand_ai_query"
        )

        s_col1, s_col2, s_col3, s_col4 = st.columns([0.28, 0.24, 0.24, 0.24])
        with s_col1:
            sem_pool_filter = st.selectbox(
                "Candidate Pool",
                ["All Candidates (Live + Legacy Archive)", "Live Pool Only", "Legacy Archive Only"],
                key="sem_pool_select"
            )
        with s_col2:
            sem_min_threshold = st.slider(
                "Minimum Fit Score (%)",
                min_value=20, max_value=90, value=30, step=5,
                key="sem_min_score"
            )
        with s_col3:
            sem_rank_pref = st.selectbox(
                "Prioritization",
                ["⚖️ Balanced Match (Default)", "⚡ Fast-Track / Young First", "🏆 Senior / Leadership First"],
                key="sem_rank_pref_select"
            )
        with s_col4:
            sem_limit = st.selectbox(
                "Max Results",
                [25, 50, 100, 250, "All Matches"],
                index=4,
                key="sem_limit_select"
            )

        if ai_query and ai_query.strip():
            candidate_pool = semantic_search.get_all_candidates_pool()

            if sem_pool_filter == "Live Pool Only":
                candidate_pool = [c for c in candidate_pool if not c.get("is_legacy", False)]
            elif sem_pool_filter == "Legacy Archive Only":
                candidate_pool = [c for c in candidate_pool if c.get("is_legacy", False)]

            actual_limit = None if sem_limit == "All Matches" else int(sem_limit)

            sem_results, parsed_params = semantic_search.search_candidates_semantic(
                ai_query,
                candidate_pool,
                min_score=sem_min_threshold,
                limit=actual_limit,
                ranking_preference=sem_rank_pref
            )

            # Pre-compute display strings for AI criteria
            crit_skills = ', '.join(parsed_params['skills_keywords']) if parsed_params['skills_keywords'] else 'None'
            crit_exp = f"{parsed_params['exp_min']} - {parsed_params['exp_max']} Yrs" if parsed_params['exp_min'] is not None else 'Any'
            crit_loc = parsed_params['target_location'] or 'Any'
            crit_bud = f"< {parsed_params['budget_max']} LPA" if parsed_params['budget_max'] else 'Any'

            st.markdown(
                f"<div style='background:#F1F5F9; border:1px solid #CBD5E1; padding:10px 14px; border-radius:8px; font-size:13px; margin: 10px 0;'>"
                f"<b>🤖 AI Extracted Criteria:</b> &nbsp; "
                f"🛠️ Skills: <span style='color:#2563EB;'>{crit_skills}</span> &nbsp;|&nbsp; "
                f"⏳ Exp: <span style='color:#2563EB;'>{crit_exp}</span> &nbsp;|&nbsp; "
                f"📍 Location: <span style='color:#2563EB;'>{crit_loc}</span> &nbsp;|&nbsp; "
                f"💰 Budget: <span style='color:#2563EB;'>{crit_bud}</span>"
                f"</div>",
                unsafe_allow_html=True
            )

            if sem_results:
                st.markdown(f"#### 🏆 Found {len(sem_results)} Matching Candidate(s)")

                display_sem_results, sem_page, sem_total_pages = render_pagination(
                    sem_results,
                    page_size_default=25,
                    key_prefix="sem_search_results"
                )

                for idx, item in enumerate(display_sem_results, (sem_page - 1) * 25 + 1):
                    cand = item["candidate"]
                    c_name = f"{cand.get('first_name', '')} {cand.get('last_name', '')}".strip()
                    c_ref = cand.get('candidate_reference_no', f"CAN-{cand.get('candidate_id')}")
                    is_legacy = cand.get("is_legacy", False)
                    pool_badge = "<span style='background:#EEF2FF; color:#4F46E5; border:1px solid #C7D2FE; font-size:11px; padding:2px 8px; border-radius:10px; font-weight:bold; margin-right:6px;'>🏛️ Legacy Archive</span>" if is_legacy else "<span style='background:#F0FDF4; color:#15803D; border:1px solid #BBF7D0; font-size:11px; padding:2px 8px; border-radius:10px; font-weight:bold; margin-right:6px;'>🟢 Live Pool</span>"

                    with st.container(border=True):
                        h_col1, h_col2 = st.columns([0.75, 0.25])
                        with h_col1:
                            st.markdown(
                                f"{pool_badge} <span style='font-size:16px; font-weight:700; color:#0F172A;'>#{idx} {c_ref} — {c_name}</span> &nbsp; <span style='color:#64748B; font-size:13px;'>{cand.get('current_designation', 'Candidate')} @ {cand.get('current_company', 'N/A')}</span>",
                                unsafe_allow_html=True
                            )
                        with h_col2:
                            st.markdown(
                                f"<div style='text-align:right;'><span style='background:{item['badge_color']}; color:white; font-weight:700; padding:4px 12px; border-radius:12px; font-size:13px;'>{item['score']}% ({item['tier']})</span></div>",
                                unsafe_allow_html=True
                            )

                        # Match reasons pill box
                        if item["reasons"]:
                            st.markdown(
                                f"<div style='background:#F8FAFC; border:1px solid #E2E8F0; padding:6px 12px; border-radius:6px; font-size:12px; margin-top:6px; color:#334155;'>"
                                f"<b>Fit Analysis:</b> {' &nbsp;•&nbsp; '.join(item['reasons'])}"
                                f"</div>",
                                unsafe_allow_html=True
                            )

                        act_col1, act_col2, act_col3, act_col4 = st.columns([0.28, 0.28, 0.22, 0.22])
                        with act_col1:
                            if is_legacy:
                                if st.button(f"📥 Add to Job Form", key=f"sem_promote_{cand['candidate_id']}", use_container_width=True):
                                    st.session_state.parsed_candidate_data = cand
                                    st.session_state.candidate_form_reset += 1
                                    st.rerun()
                            else:
                                if st.button(f"✏️ Edit Profile", key=f"sem_edit_{cand['candidate_id']}", use_container_width=True):
                                    st.session_state.edit_candidate_id = cand["candidate_id"]
                                    st.rerun()

                        with act_col2:
                            if cand.get("resume_path"):
                                if st.button(f"📄 View CV", key=f"sem_cv_{cand['candidate_id']}", use_container_width=True):
                                    st.session_state.resume_path_selected = cand["resume_path"]
                                    st.rerun()
                            else:
                                st.caption("No CV on file")

                        cand_status_val = cand.get("candidate_status") or cand.get("current_stage") or ""
                        is_cand_deact_val = cand_status_val in ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"]

                        with act_col3:
                            if is_cand_deact_val:
                                if st.button("🟢 Reactivate", key=f"sem_btn_react_{cand['candidate_id']}", use_container_width=True, help="Reactivate Candidate Profile"):
                                    reactivate_candidate_dialog(cand["candidate_id"], c_name, is_legacy=is_legacy, legacy_id=cand.get("legacy_candidate_id"), raw_cand_data=cand)
                            else:
                                if st.button("🚫 Deactivate", key=f"sem_btn_deact_{cand['candidate_id']}", use_container_width=True, help="Deactivate or Archive Profile"):
                                    deactivate_candidate_dialog(cand["candidate_id"], c_name, is_legacy=is_legacy, legacy_id=cand.get("legacy_candidate_id"), raw_cand_data=cand)

                        with act_col4:
                            st.markdown(f"<div style='font-size:12px; color:#475569; padding-top:6px;'>📞 <b>{cand.get('mobile_no', '-')}</b><br/>✉️ {cand.get('email', '-')}</div>", unsafe_allow_html=True)
            else:
                st.info("No candidates matched your search criteria. Try broadening your keywords or lowering the score threshold.")
        else:
            st.info("💡 Type a natural language query above to search candidates (e.g. *'Sales executive with 5+ yrs experience in Telangana'*).")

    # ----------------------------------------------------
    # TAB 3: CANDIDATE DUPLICATE CLEANUP & MERGE ASSISTANT
    # ----------------------------------------------------
    with tab_merge:
        st.markdown("### 🛡️ Candidate Duplicate Cleanup & Merge Assistant")
        st.caption("Automatically detects candidate profiles sharing the same Mobile Number or Email across different jobs, allowing you to merge them into a single unified record.")

        all_cands_resp = (
            supabase
            .table("candidate_management")
            .select("candidate_id, candidate_reference_no, first_name, last_name, email, mobile_no, alternate_mobile, current_company, current_designation, skills, experience_years, expected_ctc, current_location, current_stage, candidate_status, job_id, resume_path, created_on, created_by_name, remarks")
            .order("candidate_id", desc=True)
            .limit(2000)
            .execute()
            .data or []
        )

        phone_groups = {}
        email_groups = {}

        for c in all_cands_resp:
            p = normalize_phone(c.get("mobile_no"))
            if p and len(p) == 10:
                phone_groups.setdefault(p, []).append(c)

            e = (c.get("email") or "").strip().lower()
            if e and "@" in e:
                email_groups.setdefault(e, []).append(c)

        duplicate_clusters = []
        seen_cand_ids = set()

        for p, group in phone_groups.items():
            if len(group) >= 2:
                ids = tuple(sorted([c["candidate_id"] for c in group]))
                if ids not in seen_cand_ids:
                    seen_cand_ids.add(ids)
                    duplicate_clusters.append({
                        "type": f"Phone Match: {p}",
                        "candidates": group
                    })

        for e, group in email_groups.items():
            if len(group) >= 2:
                ids = tuple(sorted([c["candidate_id"] for c in group]))
                if ids not in seen_cand_ids:
                    seen_cand_ids.add(ids)
                    duplicate_clusters.append({
                        "type": f"Email Match: {e}",
                        "candidates": group
                    })

        if not duplicate_clusters:
            st.success("✅ **Clean Database!** No duplicate candidate profiles detected.")
        else:
            st.warning(f"⚠️ Found **{len(duplicate_clusters)} potential duplicate candidate group(s)**.")

            for d_idx, cluster in enumerate(duplicate_clusters, 1):
                c_list = cluster["candidates"]
                with st.container(border=True):
                    st.markdown(f"#### 👥 Duplicate Set #{d_idx} ({cluster['type']})")
                    st.caption(f"Contains {len(c_list)} candidate profiles in your database.")

                    cand_cols = st.columns(len(c_list))
                    for c_i, c_obj in enumerate(c_list):
                        with cand_cols[c_i]:
                            j_name = job_display_lookup.get(c_obj.get("job_id"), "Unknown Job")
                            c_date = str(c_obj.get('created_on') or c_obj.get('created_at', ''))[:10]
                            st.markdown(f"""
                            <div style="background:#F8FAFC; border:1px solid #E2E8F0; padding:10px; border-radius:8px; font-size:13px;">
                                <b>Ref:</b> {c_obj.get('candidate_reference_no')}<br/>
                                <b>Name:</b> {c_obj.get('first_name')} {c_obj.get('last_name')}<br/>
                                <b>Job:</b> {j_name}<br/>
                                <b>Stage:</b> {c_obj.get('current_stage', 'New')}<br/>
                                <b>Mobile:</b> {c_obj.get('mobile_no', '-')}<br/>
                                <b>Email:</b> {c_obj.get('email', '-')}<br/>
                                <b>Exp:</b> {c_obj.get('experience_years', 0)} Yrs<br/>
                                <b>Added By:</b> {c_obj.get('created_by_name', '-')}<br/>
                                <b>Date:</b> {c_date}
                            </div>
                            """, unsafe_allow_html=True)

                    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

                    m_col1, m_col2 = st.columns([0.65, 0.35])
                    with m_col1:
                        primary_choice = st.selectbox(
                            "Select Primary Master Profile to keep:",
                            options=[f"{c['candidate_reference_no']} — {c['first_name']} {c['last_name']} ({job_display_lookup.get(c.get('job_id'), 'Job')})" for c in c_list],
                            key=f"primary_sel_{d_idx}"
                        )
                    
                    with m_col2:
                        primary_ref = primary_choice.split(" — ")[0]
                        primary_cand = next(c for c in c_list if c["candidate_reference_no"] == primary_ref)
                        secondary_cands = [c for c in c_list if c["candidate_reference_no"] != primary_ref]

                        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                        if st.button("🔗 Merge Profiles into Master", key=f"merge_btn_{d_idx}", use_container_width=True, type="primary"):
                            try:
                                primary_id = primary_cand["candidate_id"]
                                merged_notes = []

                                for sec in secondary_cands:
                                    sec_id = sec["candidate_id"]
                                    supabase.table("interview_management").update({"candidate_id": primary_id}).eq("candidate_id", sec_id).execute()
                                    supabase.table("offer_management").update({"candidate_id": primary_id}).eq("candidate_id", sec_id).execute()
                                    merged_notes.append(f"Merged with {sec['candidate_reference_no']} (Job: {job_display_lookup.get(sec.get('job_id'), 'N/A')}) on {date.today()}")
                                    supabase.table("candidate_management").delete().eq("candidate_id", sec_id).execute()

                                existing_rem = primary_cand.get("remarks") or ""
                                new_rem = f"{existing_rem}\n" + "\n".join(merged_notes) if existing_rem else "\n".join(merged_notes)
                                supabase.table("candidate_management").update({"remarks": new_rem.strip()}).eq("candidate_id", primary_id).execute()

                                st.success(f"Successfully merged {len(secondary_cands)} duplicate profile(s) into Master {primary_ref}!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error during merge: {str(e)}")