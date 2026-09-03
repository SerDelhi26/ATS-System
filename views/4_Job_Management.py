import streamlit as st
import pandas as pd
from db import supabase
from datetime import datetime
import os
import re
import textwrap
from common import show_logout, show_job_notifications, show_user_profile, render_pagination, fetch_all_legacy_candidates, fetch_all_live_candidates, fetch_all_from_table
from theme import apply_theme
import storage
from matcher import calculate_candidate_match, get_top_matched_candidates

# ==========================
# LOGIN CHECK
# ==========================
if not st.session_state.get("logged_in", False):
    st.switch_page("Home.py")
    st.stop()

# Determine user access level
is_admin = str(st.session_state.get("user_role", "")).lower() == "admin"

st.set_page_config(
    page_title="Job Management",
    layout="wide"
)

apply_theme()

with st.sidebar:
    show_user_profile()
    show_logout()
    show_job_notifications()

st.markdown("# 💼 ATS Job Management")

if "success_message" not in st.session_state:
    st.session_state.success_message = None

if "edit_job_id" not in st.session_state:
    st.session_state.edit_job_id = None

if "selected_job_doc" not in st.session_state:
    st.session_state.selected_job_doc = None

if "form_reset_job" not in st.session_state:
    st.session_state.form_reset_job = 0

if "pop_reset_ver" not in st.session_state:
    st.session_state.pop_reset_ver = 0

if st.session_state.get("success_message"):
    st.success(st.session_state.get("success_message"))
    st.session_state.success_message = None

# ==========================
# FUNCTIONS
# ==========================

@st.cache_data(ttl=300)
def get_job_titles():
    return supabase.table("job_title_master").select("*").execute().data

@st.cache_data(ttl=300)
def get_companies():
    return supabase.table("company_master").select("*").execute().data

@st.cache_data(ttl=300)
def get_categories():
    return supabase.table("category_master").select("*").execute().data

@st.cache_data(ttl=300)
def get_sub_categories(category_id):
    return supabase.table("sub_category_master").select("*").eq("category_id", category_id).execute().data

# NEW: Fetch all subcategories for the global filter lookup
@st.cache_data(ttl=300)
def get_all_sub_categories():
    return supabase.table("sub_category_master").select("*").execute().data

@st.cache_data(ttl=300)
def get_recruiters():
    return supabase.table("users").select("*").eq("role", "Recruiter").eq("status", "Active").execute().data

@st.cache_data(ttl=300)
def get_all_candidates_for_matching():
    """
    Fetches both Live active candidates from candidate_management 
    and Historical candidates from legacy_candidates for unified matching.
    Uses paginated fetching to load 100% of candidates (5,000+).
    """
    all_pool = []
    
    # 1. Fetch live candidates
    live_candidate_ids = set()
    try:
        fields_live = "candidate_id, candidate_reference_no, first_name, last_name, gender, approx_dob, email, mobile_no, current_company, current_designation, skills, experience_years, experience_months, current_ctc, expected_ctc, current_location, candidate_status, current_stage, resume_path, job_id, created_by_name, created_by_user_id, created_on, remarks"
        live_data = fetch_all_live_candidates(fields_live)
        for c in live_data:
            c["source_pool"] = "Live Pool"
            c["is_legacy"] = False
            live_candidate_ids.add(c["candidate_id"])
            all_pool.append(c)
    except Exception:
        pass

    # 2. Fetch all legacy candidates via pagination
    try:
        fields_legacy = "legacy_candidate_id, candidate_reference_no, first_name, last_name, gender, approx_dob, email, mobile_no, current_company, current_designation, skills, experience_years, experience_months, current_ctc, expected_ctc, current_location, notice_period, notice_negotiable, qualification, education_details, resume_name, resume_path, is_migrated_to_active, migrated_candidate_id"
        legacy_data = fetch_all_legacy_candidates(fields_legacy)
        for c in legacy_data:
            if c.get("is_migrated_to_active") and c.get("migrated_candidate_id") in live_candidate_ids:
                continue
            c["candidate_id"] = f"LEG_{c['legacy_candidate_id']}"
            c["source_pool"] = "Legacy Pool"
            c["is_legacy"] = True
            
            # Check if candidate has been deactivated in the legacy pool
            nn = str(c.get("notice_negotiable") or "").strip()
            if nn.startswith("Deactivated:"):
                deact_status = nn.replace("Deactivated:", "").strip()
                c["candidate_status"] = deact_status
                c["current_stage"] = deact_status
            else:
                c["candidate_status"] = "Archived"
                c["current_stage"] = "Legacy Archive"
                
            c["job_id"] = None
            all_pool.append(c)
    except Exception:
        pass

    return all_pool

@st.cache_data(ttl=60)
def get_cached_job_assignments():
    return supabase.table("job_assignment").select("*").execute().data or []

@st.cache_data(ttl=60)
def get_cached_jobs_data(is_admin, user_id):
    select_query = """
        job_id, job_reference_no, job_title_id, company_id, category_id, sub_category_id, location, openings, job_status, job_document_path,
        experience_min_year, experience_max_year, pay_min, pay_max, currency, skills_required, job_description
    """
    if is_admin:
        return fetch_all_from_table("job_management", select_fields=select_query, order_by="job_id", desc=True)
    else:
        assignments = supabase.table("job_assignment").select("job_id").eq("user_id", user_id).execute().data or []
        my_job_ids = [a["job_id"] for a in assignments]
        if my_job_ids:
            res = (
                supabase.table("job_management")
                .select(select_query)
                .in_("job_id", my_job_ids)
                .eq("job_status", "Open")
                .order("job_id", desc=True)
                .execute()
            )
            return res.data or []
        return []

@st.cache_data(ttl=300, show_spinner=False)
def get_inline_top_matches_cached(job_dict, pool_type, limit=10, min_score=35, exp_leeway=1, budget_stretch=15):
    all_cands = get_all_candidates_for_matching()
    if pool_type == "Live Only":
        pool_cands = [c for c in all_cands if not c.get("is_legacy", False)]
    elif pool_type == "Legacy Only":
        pool_cands = [c for c in all_cands if c.get("is_legacy", False)]
    else:
        pool_cands = all_cands

    return get_top_matched_candidates(
        job_dict,
        pool_cands,
        limit=limit,
        min_score=min_score,
        exp_leeway_years=exp_leeway,
        budget_stretch_pct=budget_stretch
    )

@st.cache_data(ttl=60)
def get_cached_open_jobs(is_admin, user_id):
    open_jobs = supabase.table("job_management").select("job_id, job_reference_no, job_title_id, company_id, location, skills_required, experience_min_year, experience_max_year, pay_min, pay_max, currency").eq("job_status", "Open").order("job_id", desc=True).execute().data or []
    if not is_admin:
        assignments = get_cached_job_assignments()
        my_job_ids = {a["job_id"] for a in assignments if a["user_id"] == user_id}
        open_jobs = [j for j in open_jobs if j["job_id"] in my_job_ids]
    return open_jobs

@st.cache_data(ttl=300, show_spinner=False)
def get_global_ranked_matches_cached(
    selected_job_id,
    selected_job_dict,
    pool_filter,
    gender_filter,
    stage_filter,
    min_threshold,
    exp_min,
    exp_max,
    exp_leeway,
    budget_stretch,
    skills_boost,
    ranking_preference,
    recency_choice
):
    all_cands = get_all_candidates_for_matching()

    filtered_cands = all_cands
    if pool_filter == "Live Pool Only":
        filtered_cands = [c for c in filtered_cands if not c.get("is_legacy", False)]
    elif pool_filter == "Legacy Archive Only":
        filtered_cands = [c for c in filtered_cands if c.get("is_legacy", False)]

    if gender_filter == "👩 Female Only":
        filtered_cands = [c for c in filtered_cands if str(c.get("gender") or "").strip().lower() == "female"]
    elif gender_filter == "👨 Male Only":
        filtered_cands = [c for c in filtered_cands if str(c.get("gender") or "").strip().lower() == "male"]
    elif gender_filter == "Other / Not Specified":
        filtered_cands = [c for c in filtered_cands if str(c.get("gender") or "").strip().lower() not in ["male", "female"]]

    if stage_filter == "Deactivated / Inactive Only":
        filtered_cands = [c for c in filtered_cands if (c.get("candidate_status") or "") in ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"] or (c.get("current_stage") or "") in ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"]]
    elif stage_filter != "All Active Stages":
        filtered_cands = [c for c in filtered_cands if c.get("current_stage") == stage_filter or c.get("candidate_status") == stage_filter]

    recency_map = {
        "Active / Added within Last 1 Year": 1.0,
        "Active / Added within Last 3 Years": 3.0,
        "Active / Added within Last 5 Years": 5.0,
        "All Time Archive (500K+ Scale)": None
    }
    recency_val = recency_map.get(recency_choice)

    return get_top_matched_candidates(
        selected_job_dict,
        filtered_cands,
        limit=None,
        min_score=min_threshold,
        exp_min_override=exp_min,
        exp_max_override=exp_max,
        exp_leeway_years=exp_leeway,
        budget_stretch_pct=budget_stretch,
        skills_boost=skills_boost,
        ranking_preference=ranking_preference,
        recency_years=recency_val,
        include_inactive=(stage_filter == "Deactivated / Inactive Only")
    )

def map_candidate_to_job(candidate_entry, job_id):
    """
    Maps a candidate to a specific job. If the candidate is from the Legacy Archive,
    promotes them into the active candidate_management table under this Job.
    """
    try:
        if isinstance(candidate_entry, dict) and candidate_entry.get("is_legacy"):
            # Promote legacy candidate to active candidate_management
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
                "notice_negotiable": candidate_entry.get("notice_negotiable", "No"),
                "skills": candidate_entry.get("skills", ""),
                "qualification": candidate_entry.get("qualification"),
                "education_details": candidate_entry.get("education_details"),
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
                cand_ref = f"CAN-{datetime.now().year}-{new_cand_id:06d}"
                supabase.table("candidate_management").update({"candidate_reference_no": cand_ref}).eq("candidate_id", new_cand_id).execute()
                
                # Mark legacy record as migrated
                leg_id = candidate_entry.get("legacy_candidate_id")
                if leg_id:
                    supabase.table("legacy_candidates").update({
                        "is_migrated_to_active": True,
                        "migrated_candidate_id": new_cand_id
                    }).eq("legacy_candidate_id", leg_id).execute()
            st.cache_data.clear()
            return True
        else:
            # Active candidate direct mapping
            cand_id = candidate_entry.get("candidate_id") if isinstance(candidate_entry, dict) else candidate_entry
            supabase.table("candidate_management").update({
                "job_id": job_id,
                "candidate_status": "Shortlisted",
                "current_stage": "Shortlisted",
                "updated_on": datetime.now().isoformat()
            }).eq("candidate_id", cand_id).execute()
            st.cache_data.clear()
            return True
    except Exception as e:
        st.error(f"Error mapping candidate: {e}")
        return False

@st.dialog("🚫 Deactivate Candidate Profile")
def deactivate_candidate_dialog(cand_id, full_name, is_legacy=False, legacy_id=None, raw_cand_data=None):
    st.markdown(f"**Candidate:** `{full_name}`")
    st.caption("Deactivating a candidate automatically excludes them from active job matches, searches, and leaderboards.")
    d_reason = st.selectbox("Deactivation Reason", ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"], key=f"dlg_deact_r_{cand_id}")
    d_note = st.text_input("Remarks / Context", placeholder="e.g. Retired in 2026 / Left Industry...", key=f"dlg_deact_n_{cand_id}")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Confirm Deactivate", type="primary", use_container_width=True, key=f"btn_dlg_deact_{cand_id}"):
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
        if st.button("Cancel", use_container_width=True, key=f"btn_dlg_cancel_d_{cand_id}"):
            st.rerun()

@st.dialog("🟢 Reactivate Candidate Profile")
def reactivate_candidate_dialog(cand_id, full_name, is_legacy=False, legacy_id=None, raw_cand_data=None):
    st.markdown(f"**Candidate:** `{full_name}`")
    st.caption("Restore candidate back to active matching & hiring pipeline.")
    r_stage = st.selectbox("Restore Stage", ["Screening", "Shortlisted", "Applied", "New"], key=f"dlg_react_s_{cand_id}")
    r_note = st.text_input("Reactivation Note", placeholder="e.g. Mistakenly deactivated / Back in market...", key=f"dlg_react_n_{cand_id}")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Confirm Reactivation", type="primary", use_container_width=True, key=f"btn_dlg_react_{cand_id}"):
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
        if st.button("Cancel", use_container_width=True, key=f"btn_dlg_cancel_r_{cand_id}"):
            st.rerun()

def sanitize_filename(filename):
    return storage.sanitize_filename(filename)

def get_document_url(file_path):
    return storage.get_file_path("job_documents", file_path)

def upload_job_document(uploaded_file, category_name, sub_category_name, job_ref, file_name):
    return storage.save_job_document(uploaded_file, category_name, sub_category_name, job_ref, custom_name=file_name)

def get_job_by_id(job_id):
    result = supabase.table("job_management").select("*").eq("job_id", job_id).single().execute()
    return result.data

@st.dialog("✏️ Master Records Spelling Correction", width="large")
def master_data_editor_dialog():
    st.markdown("### ✏️ Master Data Spelling & Name Correction")
    st.info("ℹ️ **Edit-Only Mode:** Deletion is permanently disabled to maintain relational database integrity across historical jobs, candidates, and reports.")

    tab_jt, tab_co = st.tabs([
        "💼 Job Titles",
        "🏢 Companies"
    ])

    # TAB 1: JOB TITLES
    with tab_jt:
        curr_titles = supabase.table("job_title_master").select("*").order("job_title_name").execute().data or []
        if not curr_titles:
            st.info("No job titles registered yet.")
        else:
            jt_options = {f"{item['job_title_name']} (ID: {item['job_title_id']})": item for item in curr_titles}
            selected_label = st.selectbox("Select Job Title to Correct", list(jt_options.keys()), key="dlg_sel_jt_master")
            selected_item = jt_options[selected_label]
            corrected_val = st.text_input("Corrected Job Title Name", value=selected_item["job_title_name"], key="dlg_val_jt_master")

            if st.button("💾 Save Job Title Correction", type="primary", use_container_width=True, key="dlg_btn_save_jt_master"):
                clean = corrected_val.strip()
                if not clean:
                    st.error("Job title name cannot be empty.")
                elif clean == selected_item["job_title_name"]:
                    st.info("No changes made.")
                else:
                    dup = supabase.table("job_title_master").select("*").ilike("job_title_name", clean).neq("job_title_id", selected_item["job_title_id"]).execute()
                    if dup.data:
                        st.warning(f"A job title named '{clean}' already exists.")
                    else:
                        supabase.table("job_title_master").update({
                            "job_title_name": clean,
                            "modified_date": datetime.now().isoformat()
                        }).eq("job_title_id", selected_item["job_title_id"]).execute()
                        st.cache_data.clear()
                        st.toast(f"Job Title successfully corrected to '{clean}'!", icon="✅")
                        st.rerun()

    # TAB 2: COMPANIES
    with tab_co:
        curr_companies = supabase.table("company_master").select("*").order("company_name").execute().data or []
        if not curr_companies:
            st.info("No companies registered yet.")
        else:
            co_options = {f"{item['company_name']} (ID: {item['company_id']})": item for item in curr_companies}
            selected_co_label = st.selectbox("Select Company to Correct", list(co_options.keys()), key="dlg_sel_co_master")
            selected_co_item = co_options[selected_co_label]
            corrected_co_val = st.text_input("Corrected Company Name", value=selected_co_item["company_name"], key="dlg_val_co_master")

            if st.button("💾 Save Company Correction", type="primary", use_container_width=True, key="dlg_btn_save_co_master"):
                clean = corrected_co_val.strip()
                if not clean:
                    st.error("Company name cannot be empty.")
                elif clean == selected_co_item["company_name"]:
                    st.info("No changes made.")
                else:
                    dup = supabase.table("company_master").select("*").ilike("company_name", clean).neq("company_id", selected_co_item["company_id"]).execute()
                    if dup.data:
                        st.warning(f"A company named '{clean}' already exists.")
                    else:
                        supabase.table("company_master").update({
                            "company_name": clean
                        }).eq("company_id", selected_co_item["company_id"]).execute()
                        st.cache_data.clear()
                        st.toast(f"Company successfully corrected to '{clean}'!", icon="✅")
                        st.rerun()

# Fetch core dependencies for lookup tables
job_titles = get_job_titles()
companies = get_companies()
categories = get_categories()
recruiters = get_recruiters()
all_sub_categories = get_all_sub_categories()

# ==========================
# LAYOUT
# ==========================
# If Admin: Show creation form on left, grid on right. 
# If Recruiter: Show grid taking up full width.
if is_admin:
    left_col, right_col = st.columns([1, 3])
else:
    right_col = st.container()

# ==========================
# LEFT PANEL (ADMIN ONLY)
# ==========================
if is_admin:
    with left_col:
        editing_job = None
        job_defaults = {}

        if st.session_state.edit_job_id:
            editing_job = get_job_by_id(st.session_state.edit_job_id)
            if editing_job:
                job_defaults = editing_job

        def get_key(base_name):
            if editing_job:
                return f"{base_name}_{editing_job['job_id']}"
            return f"{base_name}_new_{st.session_state.form_reset_job}"

        if st.session_state.get("success_message"):
            st.success(st.session_state.success_message)
            del st.session_state.success_message

        # Admin Master Data Correction Quick-Access
        if st.button("⚙️ Correct Master Data (Titles / Companies)", use_container_width=True, help="Correct spelling mistakes in Master Records (Edit only, deletion disabled)"):
            master_data_editor_dialog()

        st.subheader("Edit Job" if editing_job else "Create Job")

        assigned_recruiters = []
        if editing_job:
            assignments = supabase.table("job_assignment").select("*").eq("job_id", editing_job["job_id"]).execute()
            assigned_user_ids = [item["user_id"] for item in assignments.data]
            assigned_recruiters = [r["full_name"] for r in recruiters if r["user_id"] in assigned_user_ids]

        recruiter_names = [r["full_name"] for r in recruiters]

        selected_recruiters = st.multiselect(
            "Assign Recruiters",
            recruiter_names,
            default=assigned_recruiters if editing_job else [],
            key=get_key("selected_recruiters")
        )

        # --- PRE-WIDGET PENDING SELECTION HANDLER ---
        if "pending_job_title" in st.session_state:
            st.session_state[get_key("job_title")] = st.session_state.pop("pending_job_title")
        if "pending_company" in st.session_state:
            st.session_state[get_key("company")] = st.session_state.pop("pending_company")
        if "pending_category" in st.session_state:
            st.session_state[get_key("category")] = st.session_state.pop("pending_category")
        if "pending_sub_category" in st.session_state:
            st.session_state[get_key("sub_category")] = st.session_state.pop("pending_sub_category")

        # --- JOB TITLE WITH QUICK-ADD & QUICK-EDIT POPOVERS ---
        col_jt, col_btn_jt, col_btn_edit_jt = st.columns([0.74, 0.13, 0.13])
        job_title_names = ["-- Select Job Title --"] + [item["job_title_name"] for item in job_titles]
        if editing_job:
            default_job_title = next((item["job_title_name"] for item in job_titles if item["job_title_id"] == editing_job["job_title_id"]), job_title_names[0])
            jt_idx = job_title_names.index(default_job_title) if default_job_title in job_title_names else 0
        else:
            sel_jt_val = st.session_state.get(get_key("job_title"))
            jt_idx = job_title_names.index(sel_jt_val) if sel_jt_val in job_title_names else 0

        with col_jt:
            selected_job_title = st.selectbox(
                "Job Title",
                job_title_names,
                index=jt_idx,
                key=get_key("job_title")
            )
        with col_btn_jt:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            with st.popover("➕", help="Add New Job Title", key=f"pop_jt_add_{st.session_state.pop_reset_ver}"):
                st.markdown("**Add New Job Title**")
                new_jt_name = st.text_input("Title Name", key=get_key("pop_new_jt"))
                if st.button("Save Title", key=get_key("pop_btn_save_jt"), type="primary", use_container_width=True):
                    if not new_jt_name.strip():
                        st.error("Cannot be empty")
                    else:
                        existing = supabase.table("job_title_master").select("*").ilike("job_title_name", new_jt_name.strip()).execute()
                        if existing.data:
                            st.warning("Already exists")
                        else:
                            supabase.table("job_title_master").insert({"job_title_name": new_jt_name.strip()}).execute()
                            st.cache_data.clear()
                            st.session_state["pending_job_title"] = new_jt_name.strip()
                            st.session_state.pop_reset_ver += 1
                            st.toast(f"Job Title '{new_jt_name.strip()}' added & selected!", icon="✅")
                            st.rerun()
        with col_btn_edit_jt:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            with st.popover("✏️", help="Edit Selected Job Title", key=f"pop_jt_edit_{st.session_state.pop_reset_ver}"):
                if not selected_job_title or selected_job_title == "-- Select Job Title --":
                    st.info("Select a Job Title from the dropdown to edit.")
                else:
                    st.markdown("**✏️ Edit Job Title**")
                    sel_jt_rec = next((item for item in job_titles if item["job_title_name"] == selected_job_title), None)
                    edit_jt_name = st.text_input("Correct Title Name", value=selected_job_title, key=get_key("pop_edit_jt"))
                    if st.button("Update Title", key=get_key("pop_btn_update_jt"), type="primary", use_container_width=True):
                        clean_jt = edit_jt_name.strip()
                        if not clean_jt:
                            st.error("Cannot be empty")
                        elif clean_jt == selected_job_title:
                            st.info("No changes made")
                        elif sel_jt_rec:
                            existing = supabase.table("job_title_master").select("*").ilike("job_title_name", clean_jt).neq("job_title_id", sel_jt_rec["job_title_id"]).execute()
                            if existing.data:
                                st.warning("Another job title with this name already exists")
                            else:
                                supabase.table("job_title_master").update({
                                    "job_title_name": clean_jt,
                                    "modified_date": datetime.now().isoformat()
                                }).eq("job_title_id", sel_jt_rec["job_title_id"]).execute()
                                st.cache_data.clear()
                                st.session_state["pending_job_title"] = clean_jt
                                st.session_state.pop_reset_ver += 1
                                st.toast(f"Job Title corrected to '{clean_jt}'!", icon="✅")
                                st.rerun()

        # --- COMPANY WITH QUICK-ADD & QUICK-EDIT POPOVERS ---
        col_co, col_btn_co, col_btn_edit_co = st.columns([0.74, 0.13, 0.13])
        company_names = ["-- Select Company --"] + [item["company_name"] for item in companies]
        if editing_job:
            default_company = next((item["company_name"] for item in companies if item["company_id"] == editing_job["company_id"]), company_names[0])
            co_idx = company_names.index(default_company) if default_company in company_names else 0
        else:
            sel_co_val = st.session_state.get(get_key("company"))
            co_idx = company_names.index(sel_co_val) if sel_co_val in company_names else 0

        with col_co:
            selected_company = st.selectbox(
                "Company",
                company_names,
                index=co_idx,
                key=get_key("company")
            )
        with col_btn_co:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            with st.popover("➕", help="Add New Company", key=f"pop_co_add_{st.session_state.pop_reset_ver}"):
                st.markdown("**Add New Company**")
                new_co_name = st.text_input("Company Name", key=get_key("pop_new_co"))
                if st.button("Save Company", key=get_key("pop_btn_save_co"), type="primary", use_container_width=True):
                    if not new_co_name.strip():
                        st.error("Cannot be empty")
                    else:
                        existing = supabase.table("company_master").select("*").ilike("company_name", new_co_name.strip()).execute()
                        if existing.data:
                            st.warning("Already exists")
                        else:
                            supabase.table("company_master").insert({"company_name": new_co_name.strip()}).execute()
                            st.cache_data.clear()
                            st.session_state["pending_company"] = new_co_name.strip()
                            st.session_state.pop_reset_ver += 1
                            st.toast(f"Company '{new_co_name.strip()}' added & selected!", icon="✅")
                            st.rerun()
        with col_btn_edit_co:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            with st.popover("✏️", help="Edit Selected Company", key=f"pop_co_edit_{st.session_state.pop_reset_ver}"):
                if not selected_company or selected_company == "-- Select Company --":
                    st.info("Select a Company from the dropdown to edit.")
                else:
                    st.markdown("**✏️ Edit Company**")
                    sel_co_rec = next((item for item in companies if item["company_name"] == selected_company), None)
                    edit_co_name = st.text_input("Correct Company Name", value=selected_company, key=get_key("pop_edit_co"))
                    if st.button("Update Company", key=get_key("pop_btn_update_co"), type="primary", use_container_width=True):
                        clean_co = edit_co_name.strip()
                        if not clean_co:
                            st.error("Cannot be empty")
                        elif clean_co == selected_company:
                            st.info("No changes made")
                        elif sel_co_rec:
                            existing = supabase.table("company_master").select("*").ilike("company_name", clean_co).neq("company_id", sel_co_rec["company_id"]).execute()
                            if existing.data:
                                st.warning("Another company with this name already exists")
                            else:
                                supabase.table("company_master").update({
                                    "company_name": clean_co
                                }).eq("company_id", sel_co_rec["company_id"]).execute()
                                st.cache_data.clear()
                                st.session_state["pending_company"] = clean_co
                                st.session_state.pop_reset_ver += 1
                                st.toast(f"Company corrected to '{clean_co}'!", icon="✅")
                                st.rerun()

        # --- CATEGORY WITH QUICK-ADD POPOVER ---
        col_cat, col_btn_cat = st.columns([0.82, 0.18])
        category_names = ["-- Select Category --"] + [item["category_name"] for item in categories]
        if editing_job:
            default_category = next((item["category_name"] for item in categories if item["category_id"] == editing_job["category_id"]), category_names[0])
            cat_idx = category_names.index(default_category) if default_category in category_names else 0
        else:
            sel_cat_val = st.session_state.get(get_key("category"))
            cat_idx = category_names.index(sel_cat_val) if sel_cat_val in category_names else 0

        with col_cat:
            selected_category_name = st.selectbox(
                "Category",
                category_names,
                index=cat_idx,
                key=get_key("category")
            )
        with col_btn_cat:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            with st.popover("➕", help="Add New Category", key=f"pop_cat_add_{st.session_state.pop_reset_ver}"):
                st.markdown("**Add New Category**")
                new_cat_name = st.text_input("Category Name", key=get_key("pop_new_cat"))
                if st.button("Save Category", key=get_key("pop_btn_save_cat"), type="primary", use_container_width=True):
                    if not new_cat_name.strip():
                        st.error("Cannot be empty")
                    else:
                        existing = supabase.table("category_master").select("*").ilike("category_name", new_cat_name.strip()).execute()
                        if existing.data:
                            st.warning("Already exists")
                        else:
                            supabase.table("category_master").insert({"category_name": new_cat_name.strip()}).execute()
                            st.cache_data.clear()
                            st.session_state["pending_category"] = new_cat_name.strip()
                            st.session_state.pop_reset_ver += 1
                            st.toast(f"Category '{new_cat_name.strip()}' added & selected!", icon="✅")
                            st.rerun()

        # --- SUB CATEGORY WITH QUICK-ADD POPOVER ---
        category_record = next((c for c in categories if c["category_name"] == selected_category_name), None)
        sub_categories = []
        if category_record:
            sub_categories = get_sub_categories(category_record["category_id"])

        col_sc, col_btn_sc = st.columns([0.82, 0.18])
        sub_category_names = ["-- Select Sub Category --"] + [item["sub_category_name"] for item in sub_categories]
        if editing_job:
            default_sub_category = next((item["sub_category_name"] for item in sub_categories if item["sub_category_id"] == editing_job["sub_category_id"]), sub_category_names[0] if sub_category_names else "")
            sc_idx = sub_category_names.index(default_sub_category) if default_sub_category in sub_category_names else 0
        else:
            sel_sc_val = st.session_state.get(get_key("sub_category"))
            sc_idx = sub_category_names.index(sel_sc_val) if sel_sc_val in sub_category_names else 0

        with col_sc:
            selected_sub_category = st.selectbox(
                "Sub Category",
                sub_category_names,
                index=sc_idx,
                key=get_key("sub_category")
            )
        with col_btn_sc:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            with st.popover("➕", help="Add New Sub Category", key=f"pop_sc_add_{st.session_state.pop_reset_ver}"):
                st.markdown("**Add New Sub Category**")
                new_sc_name = st.text_input("Sub Category Name", key=get_key("pop_new_sc"))
                if st.button("Save Sub Category", key=get_key("pop_btn_save_sc"), type="primary", use_container_width=True):
                    if not new_sc_name.strip():
                        st.error("Cannot be empty")
                    elif not category_record:
                        st.error("Select Category first")
                    else:
                        supabase.table("sub_category_master").insert({"category_id": category_record["category_id"], "sub_category_name": new_sc_name.strip()}).execute()
                        st.cache_data.clear()
                        st.session_state["pending_sub_category"] = new_sc_name.strip()
                        st.session_state.pop_reset_ver += 1
                        st.toast(f"Sub Category '{new_sc_name.strip()}' added & selected!", icon="✅")
                        st.rerun()

        location = st.text_input("Location", value=job_defaults.get("location", ""), placeholder="-- Enter Location --", key=get_key("location"))

        st.markdown("### 🎓 Experience")
        min_year = st.selectbox("Minimum Year", list(range(41)), index=job_defaults.get("experience_min_year", 0), key=get_key("min_year"))
        min_month = st.selectbox("Minimum Month", list(range(12)), index=job_defaults.get("experience_min_month", 0), key=get_key("min_month"))
        max_year = st.selectbox("Maximum Year", list(range(41)), index=job_defaults.get("experience_max_year", 0), key=get_key("max_year"))
        max_month = st.selectbox("Maximum Month", list(range(12)), index=job_defaults.get("experience_max_month", 0), key=get_key("max_month"))

        job_type_options = ["-- Select Job Type --", "Permanent", "Contract", "C2H", "Internship"]
        job_type = st.selectbox("Job Type", job_type_options, index=(job_type_options.index(job_defaults.get("job_type", "Permanent")) if editing_job and job_defaults.get("job_type") in job_type_options else 0), key=get_key("job_type"))

        openings = st.number_input("Openings", min_value=1, value=job_defaults.get("openings", 1), key=get_key("openings"))

        st.markdown("### 💰 Compensation")
        pay_min = st.number_input("Pay Min", min_value=0.0, value=float(job_defaults.get("pay_min", 0)), key=get_key("pay_min"))
        pay_max = st.number_input("Pay Max", min_value=0.0, value=float(job_defaults.get("pay_max", 0)), key=get_key("pay_max"))
        
        currency_options = ["-- Select Currency --", "INR", "USD", "EUR"]
        currency = st.selectbox("Currency", currency_options, index=(currency_options.index(job_defaults.get("currency", "INR")) if editing_job and job_defaults.get("currency") in currency_options else 0), key=get_key("currency"))

        pay_unit_options = ["-- Select Pay Unit --", "Per Annum", "Per Month", "Per Day", "Per Hour"]
        pay_unit = st.selectbox("Pay Unit", pay_unit_options, index=(pay_unit_options.index(job_defaults.get("pay_unit", "Per Annum")) if editing_job and job_defaults.get("pay_unit") in pay_unit_options else 0), key=get_key("pay_unit"))

        st.markdown("### 📝 Job Details")
        skills_required = st.text_area("Skills Required", value=job_defaults.get("skills_required", ""), height=120, key=get_key("skills_required"))
        job_description = st.text_area("Job Description", value=job_defaults.get("job_description", ""), height=250, key=get_key("job_description"))
        
        job_document = st.file_uploader("Upload Job Document", type=["pdf", "doc", "docx", "xlsx", "xls"], key=get_key("job_document"))

        st.markdown("### 🧾 Invoice Information")
        performa_invoice_no = st.text_input("Performa Invoice No", value=job_defaults.get("performa_invoice_no", ""), key=get_key("performa_invoice_no"))
        performa_status_options = ["-- Select Performa Invoice Status --", "Pending", "In Progress", "Completed"]
        performa_invoice_status = st.selectbox("Performa Invoice Status", performa_status_options, index=(performa_status_options.index(job_defaults.get("performa_invoice_status", "Pending")) if editing_job and job_defaults.get("performa_invoice_status") in performa_status_options else 0), key=get_key("performa_invoice_status"))

        invoice_no = st.text_input("Invoice No", value=job_defaults.get("invoice_no", ""), key=get_key("invoice_no"))
        invoice_status_options = ["-- Select Invoice Status --", "Pending", "In Progress", "Completed"]
        invoice_status = st.selectbox("Invoice Status", invoice_status_options, index=(invoice_status_options.index(job_defaults.get("invoice_status", "Pending")) if editing_job and job_defaults.get("invoice_status") in invoice_status_options else 0), key=get_key("invoice_status"))

        remark = st.text_area("Remarks", value=job_defaults.get("remark", ""), height=100, key=get_key("remark"))
        
        job_status_options = ["-- Select Job Status --", "Open", "On Hold", "Closed", "Cancelled"]
        job_status = st.selectbox("Job Status", job_status_options, index=(job_status_options.index(job_defaults.get("job_status", "Open")) if editing_job and job_defaults.get("job_status") in job_status_options else 0), key=get_key("job_status"))

        if editing_job:
            btn1, btn2 = st.columns(2)
            update_clicked = btn1.button("Update Job", use_container_width=True)
            if btn2.button("❌ Cancel Edit", use_container_width=True):
                st.session_state.edit_job_id = None
                st.rerun()
        else:
            update_clicked = st.button("Save Job", use_container_width=True)

        if update_clicked:
            try:
                validation_errors = []
                if not selected_recruiters: validation_errors.append("Please assign at least one recruiter.")
                if selected_job_title == "-- Select Job Title --": validation_errors.append("Please select Job Title.")
                if selected_company == "-- Select Company --": validation_errors.append("Please select Company.")
                if selected_category_name == "-- Select Category --": validation_errors.append("Please select Category.")
                if selected_sub_category == "-- Select Sub Category --": validation_errors.append("Please select Sub Category.")
                if not location.strip(): validation_errors.append("Please enter Location.")
                if min_year == 0 and min_month == 0: validation_errors.append("Please select Minimum Experience.")
                if max_year == 0 and max_month == 0: validation_errors.append("Please select Maximum Experience.")
                min_exp = (min_year * 12) + min_month
                max_exp = (max_year * 12) + max_month
                if max_exp < min_exp: validation_errors.append("Maximum Experience cannot be less than Minimum Experience.")
                if job_type == "-- Select Job Type --": validation_errors.append("Please select Job Type.")
                if openings <= 0: validation_errors.append("Openings must be greater than 0.")
                if pay_min <= 0: validation_errors.append("Pay Min must be greater than 0.")
                if pay_max <= 0: validation_errors.append("Pay Max must be greater than 0.")
                if float(pay_max) < float(pay_min): validation_errors.append("Pay Max cannot be less than Pay Min.")
                if currency == "-- Select Currency --": validation_errors.append("Please select Currency.")
                if pay_unit == "-- Select Pay Unit --": validation_errors.append("Please select Pay Unit.")
                if not skills_required.strip(): validation_errors.append("Please enter Skills Required.")
                if job_status == "-- Select Job Status --": validation_errors.append("Please select Job Status.")

                if validation_errors:
                    for error in validation_errors: st.error(error)
                    st.stop()

                selected_job_title_record = next(item for item in job_titles if item["job_title_name"] == selected_job_title)
                selected_company_record = next(item for item in companies if item["company_name"] == selected_company)

                job_data = {
                    "job_title_id": selected_job_title_record["job_title_id"],
                    "company_id": selected_company_record["company_id"],
                    "category_id": category_record["category_id"],
                    "sub_category_id": next(item["sub_category_id"] for item in sub_categories if item["sub_category_name"] == selected_sub_category),
                    "location": location,
                    "experience_min_year": min_year,
                    "experience_min_month": min_month,
                    "experience_max_year": max_year,
                    "experience_max_month": max_month,
                    "job_type": job_type,
                    "openings": openings,
                    "job_status": job_status,
                    "pay_min": pay_min,
                    "pay_max": pay_max,
                    "currency": currency,
                    "pay_unit": pay_unit,
                    "skills_required": skills_required,
                    "job_description": job_description,
                    "performa_invoice_no": performa_invoice_no,
                    "performa_invoice_status": performa_invoice_status,
                    "invoice_no": invoice_no,
                    "invoice_status": invoice_status,
                    "remark": remark
                }

                if editing_job:
                    job_data["modified_date"] = datetime.now().isoformat()
                    supabase.table("job_management").update(job_data).eq("job_id", editing_job["job_id"]).execute()
                    supabase.table("job_assignment").delete().eq("job_id", editing_job["job_id"]).execute()
                    
                    for recruiter_name in selected_recruiters:
                        recruiter = next(r for r in recruiters if r["full_name"] == recruiter_name)
                        supabase.table("job_assignment").insert({"job_id": editing_job["job_id"], "user_id": recruiter["user_id"]}).execute()

                    st.session_state.success_message = "Job Updated Successfully"
                    st.session_state.edit_job_id = None
                    st.rerun()

                else:
                    job_data["created_by"] = st.session_state.user_id
                    insert_result = supabase.table("job_management").insert(job_data).execute()
                    job = insert_result.data[0]
                    current_year = datetime.now().year
                    job_ref = f"JR-{current_year}-{job['job_id']:06d}"

                    # Ensure the folder hierarchy is automatically created on disk
                    storage.create_job_folder_structure(
                        selected_category_name,
                        selected_sub_category,
                        job_ref
                    )

                    job_document_path = None
                    if job_document:
                        unique_file_name = f"{job_ref}_{job_document.name}"
                        job_document_path = upload_job_document(
                            job_document,
                            selected_category_name,
                            selected_sub_category,
                            job_ref,
                            unique_file_name
                        )

                    supabase.table("job_management").update({"job_reference_no": job_ref, "job_document_name": job_document.name if job_document else None, "job_document_path": job_document_path}).eq("job_id", job["job_id"]).execute()

                    for recruiter_name in selected_recruiters:
                        recruiter = next(r for r in recruiters if r["full_name"] == recruiter_name)
                        supabase.table("job_assignment").insert({"job_id": job["job_id"], "user_id": recruiter["user_id"]}).execute()

                    st.session_state.success_message = f"Job Created : {job_ref}"
                    st.session_state.form_reset_job += 1
                    st.rerun()

            except Exception as e:
                st.error(str(e))

# ==========================
# RIGHT PANEL (JOB MANAGEMENT & MATCHING)
# ==========================
with right_col:
    all_candidates_db = get_all_candidates_for_matching()

    # Recruiter & Admin KPI Banner
    if not is_admin:
        my_assignments = supabase.table("job_assignment").select("job_id").eq("user_id", st.session_state.user_id).execute().data
        my_job_ids = [a["job_id"] for a in my_assignments]
        assigned_open_count = len(my_job_ids)
        my_assigned_candidates = [c for c in all_candidates_db if c.get("job_id") in my_job_ids]
        
        kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
        kpi_col1.metric("📌 Assigned Open Jobs", f"{assigned_open_count}")
        kpi_col2.metric("👥 Candidates in Pipeline", f"{len(my_assigned_candidates)}")
        kpi_col3.metric("🎯 Total Candidate Pool", f"{len(all_candidates_db)}")
    else:
        kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
        kpi_col1.metric("💼 Active Recruiters", f"{len(recruiters)}")
        kpi_col2.metric("🏢 Client Companies", f"{len(companies)}")
        kpi_col3.metric("🎯 Total Candidate Pool", f"{len(all_candidates_db)}")

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    
    tab_dir, tab_matcher = st.tabs(["📋 Job Directory", "🎯 Smart Candidate Matcher"])

    with tab_dir:
        st.markdown("### 📋 Job Directory")

        if st.session_state.get("selected_job_doc"):
            doc_path = st.session_state.selected_job_doc
            doc_bytes = storage.read_file_bytes(doc_path)
            doc_display_name = os.path.basename(doc_path)
            if doc_bytes:
                st.download_button(
                    label=f"⬇️ Download / Open Selected Job Document ({doc_display_name})",
                    data=doc_bytes,
                    file_name=doc_display_name,
                    mime=storage.get_mime_type(doc_display_name),
                    use_container_width=True
                )
            else:
                st.warning(f"Job document file '{doc_display_name}' was not found in storage directory ({storage.STORAGE_BASE_DIR}).")

        job_titles_lookup = {item["job_title_id"]: item["job_title_name"] for item in job_titles}
        companies_lookup = {item["company_id"]: item["company_name"] for item in companies}
        categories_lookup = {item["category_id"]: item["category_name"] for item in categories}
        sub_categories_lookup = {item["sub_category_id"]: item["sub_category_name"] for item in all_sub_categories}
        recruiter_lookup = {user["user_id"]: user["full_name"] for user in recruiters}

        search_text = st.text_input("🔍 Search Job", placeholder="JR Number, Job Title, Company or Location", key="job_search_input")

        # Filter Setup
        if is_admin:
            filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns(5)
            
            with filter_col1:
                company_filter = st.selectbox("Company Filter", ["All"] + sorted(list(companies_lookup.values())), key="adm_comp_filter")

            with filter_col2:
                status_filter = st.selectbox("Status Filter", ["All", "Open", "Closed", "On Hold", "Cancelled"], key="adm_status_filter")

            with filter_col3:
                category_filter = st.selectbox("Category Filter", ["All"] + sorted([c["category_name"] for c in categories]), key="adm_cat_filter")
                
            with filter_col4:
                sub_category_filter = st.selectbox("Sub Category Filter", ["All"] + sorted(list(sub_categories_lookup.values())), key="adm_subcat_filter")

            with filter_col5:
                recruiter_filter = st.selectbox("Recruiter Filter", ["All"] + sorted([r["full_name"] for r in recruiters]), key="adm_rec_filter")
                
        else:
            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
            
            with filter_col1:
                company_filter = st.selectbox("Company Filter", ["All"] + sorted(list(companies_lookup.values())), key="rec_comp_filter")
                
            with filter_col2:
                category_filter = st.selectbox("Category Filter", ["All"] + sorted([c["category_name"] for c in categories]), key="rec_cat_filter")
                
            with filter_col3:
                sub_category_filter = st.selectbox("Sub Category Filter", ["All"] + sorted(list(sub_categories_lookup.values())), key="rec_subcat_filter")
                
            with filter_col4:
                recruiter_filter = st.selectbox("Recruiter Filter", ["All"] + sorted([r["full_name"] for r in recruiters]), key="rec_rec_filter")
                
            status_filter = "Open"  # Hardcoded backend logic for recruiters

        assignments_data = get_cached_job_assignments()
        all_jobs_list = get_cached_jobs_data(is_admin, st.session_state.get("user_id"))
        jobs_df = pd.DataFrame(all_jobs_list)

        # Apply Search & Dropdown Filters
        if not jobs_df.empty and search_text:
            matching_job_titles = [jid for jid, title in job_titles_lookup.items() if search_text.lower() in title.lower()]
            matching_companies = [cid for cid, company in companies_lookup.items() if search_text.lower() in company.lower()]
            jobs_df = jobs_df[
                jobs_df["job_reference_no"].fillna("").str.contains(search_text, case=False, na=False) |
                jobs_df["location"].fillna("").str.contains(search_text, case=False, na=False) |
                jobs_df["skills_required"].fillna("").str.contains(search_text, case=False, na=False) |
                jobs_df["job_title_id"].isin(matching_job_titles) |
                jobs_df["company_id"].isin(matching_companies)
            ]

        if not jobs_df.empty and company_filter != "All":
            company_ids = [cid for cid, cname in companies_lookup.items() if cname == company_filter]
            jobs_df = jobs_df[jobs_df["company_id"].isin(company_ids)]

        if not jobs_df.empty and status_filter != "All":
            jobs_df = jobs_df[jobs_df["job_status"] == status_filter]

        if not jobs_df.empty and category_filter != "All":
            category_ids = [cid for cid, cname in categories_lookup.items() if cname == category_filter]
            jobs_df = jobs_df[jobs_df["category_id"].isin(category_ids)]
            
        if not jobs_df.empty and sub_category_filter != "All":
            subcat_ids = [sid for sid, sname in sub_categories_lookup.items() if sname == sub_category_filter]
            jobs_df = jobs_df[jobs_df["sub_category_id"].isin(subcat_ids)]

        if not jobs_df.empty and recruiter_filter != "All":
            recruiter_ids = [uid for uid, name in recruiter_lookup.items() if name == recruiter_filter]
            assigned_job_ids = [item["job_id"] for item in assignments_data if item["user_id"] in recruiter_ids]
            jobs_df = jobs_df[jobs_df["job_id"].isin(assigned_job_ids)]

        # Draw Grid
        if not jobs_df.empty:
            display_jobs_df, current_page, total_pages = render_pagination(jobs_df.fillna(""), page_size_default=25, key_prefix="jobs")

            if is_admin:
                col_widths = [2, 3, 3, 3, 2, 2, 2, 2.5, 1.5, 1.5]
            else:
                col_widths = [2, 3, 3, 3, 2, 2, 2, 2.5]

            header = st.columns(col_widths)
            header[0].markdown("**JR Number**")
            header[1].markdown("**Job Title**")
            header[2].markdown("**Company**")
            header[3].markdown("**Recruiters**")
            header[4].markdown("**Location**")
            header[5].markdown("**Openings**")
            header[6].markdown("**Status**")
            header[7].markdown("**Doc**")
            if is_admin:
                header[8].markdown("**Edit**")
                header[9].markdown("**Status**")
            st.divider()

            for _, row in display_jobs_df.iterrows():
                with st.container():
                    cols = st.columns(col_widths)
                    cols[0].write(row["job_reference_no"])
                    cols[1].write(job_titles_lookup.get(row["job_title_id"], ""))
                    cols[2].write(companies_lookup.get(row["company_id"], ""))

                    job_recruiters = [recruiter_lookup.get(a["user_id"]) for a in assignments_data if a["job_id"] == row["job_id"] and recruiter_lookup.get(a["user_id"])]
                    cols[3].write(", ".join(job_recruiters) if job_recruiters else "Unassigned")

                    cols[4].write(row["location"])
                    cols[5].write(row["openings"])

                    job_status = row["job_status"]
                    bg_color = {"Open": "#16A34A", "Closed": "#DC2626", "On Hold": "#F59E0B"}.get(job_status, "#64748B")
                    cols[6].markdown(f"<span style='background:{bg_color}; color:white; padding:4px 10px; border-radius:10px;'>{job_status}</span>", unsafe_allow_html=True)

                    if row["job_document_path"]:
                        if cols[7].button("📄 View", key=f"doc_{row['job_id']}"):
                            st.session_state.selected_job_doc = row["job_document_path"]
                            st.rerun()
                    else:
                        cols[7].write("-")

                    if is_admin:
                        if cols[8].button("✏️", key=f"edit_{row['job_id']}"):
                            st.session_state.edit_job_id = row["job_id"]
                            st.rerun()
                        if row["job_status"] == "Open":
                            if cols[9].button("🔒", key=f"close_{row['job_id']}"):
                                supabase.table("job_management").update({"job_status": "Closed"}).eq("job_id", row["job_id"]).execute()
                                st.success("Job Closed Successfully")
                                st.rerun()
                        else:
                            if cols[9].button("🔓", key=f"reopen_{row['job_id']}"):
                                supabase.table("job_management").update({"job_status": "Open"}).eq("job_id", row["job_id"]).execute()
                                st.success("Job Reopened Successfully")
                                st.rerun()

                    # Expander 1: Job Description
                    with st.expander("👁️ View Job Requirements & Description"):
                        e_col1, e_col2 = st.columns(2)
                        e_col1.markdown(f"**Target Experience:** {row.get('experience_min_year', 0)} to {row.get('experience_max_year', 0)} Years")
                        e_col2.markdown(f"**Budget/Salary:** {row.get('pay_min', 0)} - {row.get('pay_max', 0)} {row.get('currency', '')}")
                        
                        st.markdown(f"**Required Skills:** {row.get('skills_required', '-')}")
                        st.markdown(f"**Job Description:**")
                        st.info(row.get('job_description') if str(row.get('job_description')).strip() else 'No description provided.')

                    # Expander 2: Smart Candidate Suggestions
                    with st.expander(f"🎯 Suggested Candidates for {row['job_reference_no']} (Smart Match)"):
                        job_dict = row.to_dict()
                        
                        # Quick Flexibility Controls for Inline Matcher
                        q_col1, q_col2, q_col3 = st.columns([0.35, 0.35, 0.3])
                        with q_col1:
                            inl_leeway = st.selectbox("⏳ Exp Leeway", [0, 1, 2, 3], index=1, format_func=lambda x: "Strict Exp (0 Yrs)" if x == 0 else f"+/- {x} Yrs Leeway", key=f"inl_leeway_{row['job_id']}")
                        with q_col2:
                            inl_stretch = st.selectbox("💰 Budget Stretch", [0, 15, 30, 50], index=1, format_func=lambda x: "Exact Budget" if x == 0 else f"+{x}% Budget Headroom", key=f"inl_stretch_{row['job_id']}")
                        with q_col3:
                            inl_pool = st.selectbox("👥 Pool", ["All (Live + Legacy)", "Live Only", "Legacy Only"], key=f"inl_pool_{row['job_id']}")

                        top_matches = get_inline_top_matches_cached(
                            job_dict,
                            inl_pool,
                            limit=10,
                            min_score=35,
                            exp_leeway=inl_leeway,
                            budget_stretch=inl_stretch
                        )
                        
                        if top_matches:
                            st.markdown(f"Found **{len(top_matches)} candidate(s)** matching this job (with +/-{inl_leeway} Yrs exp leeway & +{inl_stretch}% budget stretch):")
                            
                            for item in top_matches:
                                cand = item["candidate"]
                                match = item["match"]
                                
                                c_fullname = f"{cand.get('first_name', '')} {cand.get('last_name', '')}".strip()
                                cand_ref = cand.get('candidate_reference_no', f"CAN-{cand.get('candidate_id')}")
                                is_legacy_cand = cand.get("is_legacy", False)
                                pool_badge = "<span style='background:rgba(99, 102, 241, 0.15); color:#818CF8; border:1px solid rgba(99, 102, 241, 0.35); font-size:11px; padding:2px 8px; border-radius:10px; font-weight:bold; margin-right:6px;'>🏛️ Legacy Archive</span>" if is_legacy_cand else "<span style='background:rgba(34, 197, 94, 0.15); color:#4ADE80; border:1px solid rgba(34, 197, 94, 0.35); font-size:11px; padding:2px 8px; border-radius:10px; font-weight:bold; margin-right:6px;'>🟢 Live Pool</span>"
                                
                                with st.container(border=True):
                                    t1_h1, t1_h2 = st.columns([0.7, 0.3])
                                    with t1_h1:
                                        st.markdown(
                                            f"{pool_badge} <span style='font-weight:700; font-size:15px;'>{cand_ref} | {c_fullname}</span> &nbsp; <span style='opacity:0.8; font-size:13px;'>{cand.get('current_designation', 'Candidate')} at {cand.get('current_company', 'N/A')}</span>",
                                            unsafe_allow_html=True
                                        )
                                    with t1_h2:
                                        st.markdown(
                                            f"<div style='text-align:right;'><span style='background:{match['badge_color']}; color:white; padding:4px 12px; border-radius:12px; font-weight:bold; font-size:13px;'>{match['total_match_pct']}% Match ({match['match_tier']})</span></div>",
                                            unsafe_allow_html=True
                                        )

                                    mc1, mc2, mc3, mc4 = st.columns(4)
                                    with mc1:
                                        st.caption(f"🛠️ **Skills:** {match['skill_score']}/40 pts ({len(match['matched_skills'])} matched)")
                                    with mc2:
                                        st.caption(f"⏳ **Exp:** {match['exp_msg']}")
                                    with mc3:
                                        st.caption(f"💰 **CTC:** {match['budget_msg']}")
                                    with mc4:
                                        st.caption(f"📍 **Location:** {match['loc_msg']}")

                                    m_col1, m_col2, m_col3 = st.columns([0.38, 0.32, 0.3])
                                    
                                    is_already_on_job = cand.get("job_id") == row["job_id"]
                                    if is_already_on_job:
                                        m_col1.caption("✅ Already assigned to this job")
                                    else:
                                        map_btn_label = f"📥 Promote & Map to Job" if is_legacy_cand else f"📥 Map to this Job"
                                        if m_col1.button(map_btn_label, key=f"map_{row['job_id']}_{cand['candidate_id']}", use_container_width=True):
                                            if map_candidate_to_job(cand, row["job_id"]):
                                                st.success(f"Candidate {c_fullname} mapped to {row['job_reference_no']}!")
                                                st.rerun()
                                                
                                    if cand.get("resume_path"):
                                        if m_col2.button(f"📄 View CV", key=f"cv_{row['job_id']}_{cand['candidate_id']}", use_container_width=True):
                                            st.session_state.selected_job_doc = cand["resume_path"]
                                            st.rerun()
                                    else:
                                        m_col2.caption("No CV uploaded")
                                        
                                    m_col3.caption(f"📞 {cand.get('mobile_no', '-')} | ✉️ {cand.get('email', '-')}")
                        else:
                            st.info("No candidates in the database currently match this job's criteria. Try adjusting the Leeway or Budget Stretch options above.")
                    
                    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
        else:
            st.info("No jobs found.")

    # ==========================
    # TAB 2: SMART CANDIDATE MATCHER (GLOBAL LEADERBOARD)
    # ==========================
    with tab_matcher:
        st.markdown("### 🎯 Smart Candidate Suggestion Engine")
        st.caption("Automatically ranks candidates from your entire database (Live Candidates + Legacy Archive) against any job with customizable Experience and Budget flexibility.")
        
        open_jobs_list = get_cached_open_jobs(is_admin, st.session_state.get("user_id"))
            
        if not open_jobs_list:
            st.warning("No open jobs available to match candidates against.")
        else:
            job_select_options = {}
            for j in open_jobs_list:
                t_name = job_titles_lookup.get(j["job_title_id"], "Job")
                c_name = companies_lookup.get(j["company_id"], "Company")
                label = f"{j['job_reference_no']} | {t_name} at {c_name} ({j.get('location', 'N/A')})"
                job_select_options[label] = j
                
            selected_match_job_label = st.selectbox("Select Target Job for Candidate Matching:", list(job_select_options.keys()))
            selected_match_job = job_select_options.get(selected_match_job_label)
            if not selected_match_job:
                st.info("Please select a job to view candidate matches.")
                st.stop()
            
            # Job Summary Card
            with st.container(border=True):
                st.markdown(f"**🎯 Target Requirements for {selected_match_job['job_reference_no']}**")
                s_col1, s_col2, s_col3, s_col4 = st.columns(4)
                s_col1.caption(f"📍 **Location:** {selected_match_job.get('location', 'N/A')}")
                s_col2.caption(f"⏳ **Exp:** {selected_match_job.get('experience_min_year', 0)} - {selected_match_job.get('experience_max_year', 0)} Yrs")
                s_col3.caption(f"💰 **Budget:** {selected_match_job.get('pay_min', 0)} - {selected_match_job.get('pay_max', 0)} {selected_match_job.get('currency', 'INR')}")
                s_col4.caption(f"🛠️ **Skills:** {selected_match_job.get('skills_required', '-')}")

            # Recruiter Search Extension Controls (Experience & Budget Flexibility)
            with st.expander("🎛️ Adjust Experience Range, Extended Budget & Search Leeway (Recruiter Controls)", expanded=True):
                c_row1_col1, c_row1_col2 = st.columns(2)
                
                job_min_e = int(selected_match_job.get("experience_min_year", 0) or 0)
                job_max_e = int(selected_match_job.get("experience_max_year", 0) or 0)
                if job_max_e == 0:
                    job_max_e = max(job_min_e + 5, 10)
                if job_max_e < job_min_e:
                    job_max_e = job_min_e + 3

                with c_row1_col1:
                    exp_range = st.slider(
                        "🎯 Target Experience Range (Years)",
                        min_value=0,
                        max_value=35,
                        value=(max(0, job_min_e - 1), job_max_e + 2),
                        step=1,
                        help="Drag to expand target experience lower or higher to see more junior or senior candidates.",
                        key=f"match_exp_range_{selected_match_job['job_id']}"
                    )
                with c_row1_col2:
                    exp_leeway = st.selectbox(
                        "⏳ Experience Leeway (+/- Years)",
                        options=[0, 1, 2, 3],
                        index=1,
                        format_func=lambda x: "Strict (0 Years Leeway)" if x == 0 else f"+/- {x} Year(s) Extra Leeway",
                        help="Gives extra tolerance to candidates who are slightly above or below the target years.",
                        key=f"match_exp_leeway_{selected_match_job['job_id']}"
                    )

                c_row2_col1, c_row2_col2 = st.columns(2)
                with c_row2_col1:
                    budget_stretch = st.selectbox(
                        "💰 Budget / Salary Stretch Allowance",
                        options=[0, 15, 25, 40, 60, 100],
                        index=1,
                        format_func=lambda x: "Strict (Exact Job Budget Max)" if x == 0 else f"+{x}% Budget Stretch (Headroom)",
                        help="Allows management flexibility to consider candidates asking for slightly higher CTC.",
                        key=f"match_budget_stretch_{selected_match_job['job_id']}"
                    )
                with c_row2_col2:
                    skills_boost = st.text_input(
                        "🔍 Extra Skill / Keyword Boost (Optional)",
                        placeholder="e.g. Pesticides, Chemical, Sales, Agriculture, Team Lead...",
                        help="Boost scores for candidates having these additional skills or keywords.",
                        key=f"match_skills_boost_{selected_match_job['job_id']}"
                    )

                c_row3_col1, c_row3_col2 = st.columns(2)
                with c_row3_col1:
                    ranking_preference = st.selectbox(
                        "⚡ Candidate Prioritization / Sort",
                        options=[
                            "⚖️ Balanced Match (Default)",
                            "⚡ Fast-Track / Young High-Growth First",
                            "🏆 Senior / Leadership First"
                        ],
                        index=0,
                        help="Prioritize younger high-potential candidates within target experience or senior leaders.",
                        key=f"match_rank_pref_{selected_match_job['job_id']}"
                    )
                with c_row3_col2:
                    recency_choice = st.selectbox(
                        "📅 Profile Recency Filter",
                        options=["All Time Archive (500K+ Scale)", "Active / Added within Last 1 Year", "Active / Added within Last 3 Years", "Active / Added within Last 5 Years"],
                        index=0,
                        help="Narrow down matches to recently active candidates or search historical depth.",
                        key=f"match_recency_{selected_match_job['job_id']}"
                    )

            # Matcher Filters (Threshold, Pool, Gender, Stage)
            f_col1, f_col2, f_col3, f_col4 = st.columns([0.28, 0.24, 0.24, 0.24])
            with f_col1:
                min_threshold = st.slider("Minimum Match Threshold (%)", min_value=15, max_value=90, value=35, step=5)
            with f_col2:
                pool_filter = st.selectbox("Candidate Pool", ["All Pools (Live + Legacy)", "Live Pool Only", "Legacy Archive Only"])
            with f_col3:
                gender_matcher_filter = st.selectbox("Gender Diversity Filter", ["All Genders", "👩 Female Only", "👨 Male Only", "Other / Not Specified"])
            with f_col4:
                stage_filter = st.selectbox("Filter by Candidate Stage", ["All Active Stages", "New", "Screening", "Shortlisted", "Applied", "Selected", "Deactivated / Inactive Only"])

            ranked_matches = get_global_ranked_matches_cached(
                selected_match_job["job_id"],
                selected_match_job,
                pool_filter,
                gender_matcher_filter,
                stage_filter,
                min_threshold,
                exp_range[0],
                exp_range[1],
                exp_leeway,
                budget_stretch,
                skills_boost,
                ranking_preference,
                recency_choice
            )
            
            if ranked_matches:
                st.markdown(f"#### 🏆 Top Matched Candidate(s) ({len(ranked_matches)} matches found)")
                
                # Pagination over smart matches
                display_ranked_matches, m_curr_page, m_total_pages = render_pagination(
                    ranked_matches,
                    page_size_default=25,
                    key_prefix=f"smart_match_{selected_match_job['job_id']}"
                )
                
                for idx, match_item in enumerate(display_ranked_matches, (m_curr_page - 1) * 25 + 1):
                    c = match_item["candidate"]
                    m = match_item["match"]
                    
                    full_name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
                    c_ref = c.get('candidate_reference_no', f"CAN-{c.get('candidate_id')}")
                    is_legacy_cand = c.get("is_legacy", False)
                    cand_raw_status = c.get("candidate_status") or c.get("current_stage") or ""
                    is_cand_deact = cand_raw_status in ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"]
                    
                    if is_cand_deact:
                        status_badge = f"<span style='background:#475569; color:white; border:1px solid #334155; font-size:11px; padding:2px 8px; border-radius:10px; font-weight:bold; margin-right:6px;'>🚫 {cand_raw_status}</span>"
                    elif is_legacy_cand:
                        status_badge = "<span style='background:rgba(99, 102, 241, 0.15); color:#818CF8; border:1px solid rgba(99, 102, 241, 0.35); font-size:11px; padding:2px 8px; border-radius:10px; font-weight:bold; margin-right:6px;'>🏛️ Legacy Archive</span>"
                    else:
                        status_badge = "<span style='background:rgba(34, 197, 94, 0.15); color:#4ADE80; border:1px solid rgba(34, 197, 94, 0.35); font-size:11px; padding:2px 8px; border-radius:10px; font-weight:bold; margin-right:6px;'>🟢 Live Pool</span>"
                    
                    cand_gender = c.get("gender") or "Not Specified"
                    gender_icon = "👨" if cand_gender == "Male" else ("👩" if cand_gender == "Female" else "⚧")
                    gender_badge = f"<span style='background:rgba(128, 128, 128, 0.12); color:#475569; border:1px solid rgba(128, 128, 128, 0.25); font-size:11px; padding:2px 8px; border-radius:10px; font-weight:600; margin-right:6px;'>{gender_icon} {cand_gender}</span>"

                    with st.container(border=True):
                        head_col1, head_col2 = st.columns([0.7, 0.3])
                        with head_col1:
                            st.markdown(
                                f"{status_badge} {gender_badge} <span style='font-size:16px; font-weight:700;'>#{idx} {c_ref} — {full_name}</span> &nbsp; <span style='opacity:0.8; font-size:13px;'>{c.get('current_designation', 'Candidate')} @ {c.get('current_company', 'N/A')}</span>",
                                unsafe_allow_html=True
                            )
                        with head_col2:
                            st.markdown(
                                f"<div style='text-align:right;'><span style='background:{m['badge_color']}; color:white; font-weight:700; padding:5px 14px; border-radius:15px; font-size:13px;'>{m['total_match_pct']}% Match ({m['match_tier']})</span></div>",
                                unsafe_allow_html=True
                            )

                        if m.get("is_high_seniority"):
                            st.warning(f"👴 **High Seniority Advisory:** Candidate is estimated at ~{m['approx_age']} Yrs approx age / ~{m['dynamic_exp']} Yrs career experience (Base {m['base_exp']} Yrs + {m['elapsed_years']} Yrs progression). Verify active seeking status or retirement.")

                        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

                        met_c1, met_c2, met_c3, met_c4 = st.columns(4)
                        matched_str = ', '.join(m['matched_skills'][:4]) if m['matched_skills'] else 'None'
                        missing_str = ', '.join(m['missing_skills'][:3]) if m['missing_skills'] else 'None'

                        box_style = "background:rgba(128, 128, 128, 0.08); border:1px solid rgba(128, 128, 128, 0.2); padding:8px 10px; border-radius:6px; font-size:12px; min-height:85px;"

                        with met_c1:
                            st.markdown(
                                f"<div style='{box_style}'><b>🛠️ Skills ({m['skill_score']}/40 pts)</b><br/><span style='color:#16A34A;'>✓ {matched_str}</span><br/><span style='color:#EF4444;'>✗ {missing_str}</span></div>",
                                unsafe_allow_html=True
                            )
                        with met_c2:
                            st.markdown(
                                f"<div style='{box_style}'><b>⏳ Experience ({m['exp_score']}/25 pts)</b><br/>{m['exp_msg']}</div>",
                                unsafe_allow_html=True
                            )
                        with met_c3:
                            st.markdown(
                                f"<div style='{box_style}'><b>💰 Budget/CTC ({m['budget_score']}/20 pts)</b><br/>{m['budget_msg']}</div>",
                                unsafe_allow_html=True
                            )
                        with met_c4:
                            st.markdown(
                                f"<div style='{box_style}'><b>📍 Location ({m['loc_score']}/15 pts)</b><br/>{m['loc_msg']}</div>",
                                unsafe_allow_html=True
                            )

                        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

                        btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([0.30, 0.28, 0.22, 0.20])
                        
                        is_on_job = c.get("job_id") == selected_match_job["job_id"]
                        if is_on_job:
                            btn_col1.button("✅ Already on this Job", key=f"mapped_badge_{c['candidate_id']}", disabled=True, use_container_width=True)
                        else:
                            map_label = f"📥 Promote & Map to {selected_match_job['job_reference_no']}" if is_legacy_cand else f"📥 Map Candidate to {selected_match_job['job_reference_no']}"
                            if btn_col1.button(map_label, key=f"global_map_{c['candidate_id']}", use_container_width=True):
                                if map_candidate_to_job(c, selected_match_job["job_id"]):
                                    st.success(f"Candidate {full_name} successfully mapped to {selected_match_job['job_reference_no']}!")
                                    st.rerun()
                                    
                        if c.get("resume_path"):
                            if btn_col2.button(f"📄 Download CV ({full_name})", key=f"global_cv_{c['candidate_id']}", use_container_width=True):
                                st.session_state.selected_job_doc = c["resume_path"]
                                st.rerun()
                        else:
                            btn_col2.caption("No CV on file")

                        cand_raw_status = c.get("candidate_status") or c.get("current_stage") or ""
                        is_cand_deact = cand_raw_status in ["Retired", "Deceased", "Inactive / Left Market", "Blacklisted"]

                        with btn_col3:
                            if is_cand_deact:
                                if st.button("🟢 Reactivate", key=f"job_btn_react_{c['candidate_id']}", use_container_width=True, help="Reactivate Candidate Profile"):
                                    reactivate_candidate_dialog(c["candidate_id"], full_name, is_legacy=is_legacy_cand, legacy_id=c.get("legacy_candidate_id"), raw_cand_data=c)
                            else:
                                if st.button("🚫 Deactivate", key=f"job_btn_deact_{c['candidate_id']}", use_container_width=True, help="Deactivate or Archive Profile"):
                                    deactivate_candidate_dialog(c["candidate_id"], full_name, is_legacy=is_legacy_cand, legacy_id=c.get("legacy_candidate_id"), raw_cand_data=c)
                            
                        btn_col4.markdown(f"<div style='font-size:12px; opacity:0.85; padding-top:6px;'>📞 <b>{c.get('mobile_no', '-')}</b><br/>✉️ {c.get('email', '-')}</div>", unsafe_allow_html=True)
                        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            else:
                st.info(f"No candidates found matching with >= {min_threshold}% threshold. Try extending the Experience range or Budget stretch in the controls above.")