import os
import re
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
import streamlit as st
from db import supabase

logger = logging.getLogger("ats.notifications")


@st.cache_resource
def get_cached_logo_b64() -> str:
    """Reads and encodes the company logo once, caching the base64 string in memory."""
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")
    if not os.path.exists(logo_path):
        return ""
    try:
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""

def render_logo(width=220, align="left"):
    """
    Renders the unified 1 Point Solution company logo with 100% alpha transparency.
    Uses cached in-memory base64 to avoid repetitive disk I/O on every page click/rerun.
    """
    b64 = get_cached_logo_b64()
    if not b64:
        return
        
    st.markdown(
        f"""
        <div class="ats-logo-wrapper" style="text-align: {align}; margin-bottom: 12px;">
            <img src="data:image/png;base64,{b64}" style="width: {width}px; max-width: 100%; height: auto;" />
        </div>
        """,
        unsafe_allow_html=True
    )

def show_user_profile():
    """Displays company logo and the logged-in user's name and role at the top of the sidebar."""
    # Check 30-minute idle session timeout
    if st.session_state.get("logged_in", False):
        import time
        now = time.time()
        last_act = st.session_state.get("last_activity", now)
        if now - last_act > 30 * 60:
            st.session_state.clear()
            st.session_state["session_timeout_msg"] = "🔒 Session expired due to 30 minutes of inactivity. Please log in again."
            st.rerun()
        st.session_state["last_activity"] = now

    with st.sidebar:
        render_logo(width=200, align="center")

        if st.session_state.get("logged_in", False):
            name = st.session_state.get("user_name", "User")
            role = st.session_state.get("user_role", "")
            st.markdown(f"👤 **{name}**")
            st.caption(f"Role: {role}")
            st.markdown("---")

def show_logout():
    """Renders the standard logout and refresh buttons in the sidebar and safely returns to login."""
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    if st.button("🔄 Refresh Page", use_container_width=True, help="Clear cache and reload the latest data from database"):
        clear_data_cache(None)
        st.rerun()

@st.cache_data(ttl=120)
def get_master_lookups():
    """Fetches and caches master table lookups concurrently using ThreadPoolExecutor."""
    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            fut_comp = executor.submit(lambda: supabase.table("company_master").select("*").order("company_name").execute().data or [])
            fut_jt = executor.submit(lambda: supabase.table("job_title_master").select("*").order("job_title_name").execute().data or [])
            fut_cat = executor.submit(lambda: supabase.table("category_master").select("*").order("category_name").execute().data or [])
            fut_scat = executor.submit(lambda: supabase.table("sub_category_master").select("*").order("sub_category_name").execute().data or [])
            fut_users = executor.submit(lambda: supabase.table("users").select("user_id, full_name, email, role, status").execute().data or [])
            
        return {
            "companies": fut_comp.result(),
            "job_titles": fut_jt.result(),
            "categories": fut_cat.result(),
            "sub_categories": fut_scat.result(),
            "users": fut_users.result()
        }
    except Exception as e:
        logger.warning(f"Error fetching master lookups: {e}")
        return {"companies": [], "job_titles": [], "categories": [], "sub_categories": [], "users": []}


@st.cache_data(ttl=60)
def get_recruiter_notification_data(user_id):
    """Cached helper to fetch assigned open jobs, candidate submissions, and lookups for notifications."""
    assignments = supabase.table("job_assignment").select("job_id").eq("user_id", user_id).execute().data or []
    assigned_job_ids = list({a["job_id"] for a in assignments if a.get("job_id")})
    if not assigned_job_ids:
        return [], set(), {}, {}
    
    jobs = (
        supabase.table("job_management")
        .select("job_id, job_reference_no, job_status, job_title_id, company_id, location, experience_min_year, experience_max_year, pay_min, pay_max, currency, skills_required, job_description")
        .in_("job_id", assigned_job_ids)
        .eq("job_status", "Open")
        .execute()
        .data or []
    )
    
    candidates_added = (
        supabase.table("candidate_management")
        .select("job_id")
        .eq("created_by_user_id", user_id)
        .in_("job_id", assigned_job_ids)
        .execute()
        .data or []
    )
    jobs_with_candidates = {c["job_id"] for c in candidates_added if c.get("job_id")}
    
    lookups = get_master_lookups()
    title_lookup = {t["job_title_id"]: t["job_title_name"] for t in lookups.get("job_titles", [])}
    company_lookup = {c["company_id"]: c["company_name"] for c in lookups.get("companies", [])}
    
    return jobs, jobs_with_candidates, title_lookup, company_lookup


@st.fragment
def show_job_notifications():
    """Renders a notification bell in the sidebar for newly assigned jobs."""
    if not st.session_state.get("logged_in", False):
        return
        
    user_id = st.session_state.get("user_id")
    user_role = st.session_state.get("user_role")
    
    if user_role not in ["Recruiter", "Admin-Lite"]:
        return

    try:
        jobs, jobs_with_candidates, title_lookup, company_lookup = get_recruiter_notification_data(user_id)
        
        if not jobs:
            st.markdown("---")
            st.markdown("🔔 **Notifications:** No jobs assigned.")
            return

        if "seen_job_ids" not in st.session_state:
            st.session_state.seen_job_ids = []

        # Filter out jobs that are already "seen" temporarily OR have candidates added by this user
        unseen_jobs = [
            j for j in jobs 
            if j["job_id"] not in st.session_state.seen_job_ids
            and j["job_id"] not in jobs_with_candidates
        ]

        count = len(unseen_jobs)

        st.markdown("---")
        if count > 0:
            with st.expander(f"🔔 New Jobs ({count})", expanded=True):
                st.markdown(f"**You have {count} newly assigned job(s):**")

                for j in unseen_jobs:
                    col1, col2 = st.columns([0.6, 0.4])
                    col1.markdown(f"<div style='margin-top: 8px;'>📌 <b>{j['job_reference_no']}</b></div>", unsafe_allow_html=True)

                    with col2:
                        with st.popover("👁️ View", use_container_width=True, key=f"notif_view_{j['job_id']}"):
                            st.markdown(f"**Job No:** {j['job_reference_no']}")
                            st.markdown(f"**Title:** {title_lookup.get(j.get('job_title_id'), 'N/A')}")
                            st.markdown(f"**Company:** {company_lookup.get(j.get('company_id'), 'N/A')}")
                            st.markdown(f"**Location:** {j.get('location', 'N/A')}")
                            st.markdown(f"**Experience:** {j.get('experience_min_year', 0)} - {j.get('experience_max_year', 0)} Yrs")
                            st.markdown(f"**Budget:** {j.get('pay_min', 0)} - {j.get('pay_max', 0)} {j.get('currency', '')}")
                            st.markdown(f"**Skills:** {j.get('skills_required', 'N/A')}")
                            st.info(j.get('job_description', 'No description provided.'))

                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Mark All as Read", use_container_width=True, key="btn_notif_mark_all_read"):
                    st.session_state.seen_job_ids.extend([j["job_id"] for j in unseen_jobs])
                    try:
                        st.rerun(scope="fragment")
                    except TypeError:
                        st.rerun()
        else:
            st.markdown("🔔 **Notifications:** All caught up!")

    except Exception as e:
        logger.warning(f"Error rendering job notifications: {e}")



def render_pagination(items, page_size_default=25, key_prefix="page", page_size_options=[25, 50, 100]):
    """
    Renders clean Previous/Next pagination controls for lists or DataFrames.
    Returns (page_items, current_page, total_pages).
    """
    total_items = len(items) if items is not None else 0
    if total_items == 0:
        return items, 1, 1

    page_key = f"{key_prefix}_current_page"

    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    # Selector for page size and status indicator
    col_info, col_size, col_prev, col_page, col_next = st.columns([3.5, 1.8, 1.2, 1.8, 1.2])

    page_size = col_size.selectbox(
        "Rows per page",
        options=page_size_options,
        index=page_size_options.index(page_size_default) if page_size_default in page_size_options else 0,
        key=f"{key_prefix}_size_select",
        label_visibility="collapsed"
    )

    total_pages = max(1, (total_items + page_size - 1) // page_size)

    # Ensure page is within valid range
    if st.session_state[page_key] > total_pages:
        st.session_state[page_key] = total_pages
    if st.session_state[page_key] < 1:
        st.session_state[page_key] = 1

    current_page = st.session_state[page_key]
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)

    col_info.markdown(
        f"<div style='padding-top: 6px; color: #475569; font-size: 13px;'>"
        f"Showing <b>{start_idx + 1}–{end_idx}</b> of <b>{total_items}</b> records"
        f"</div>",
        unsafe_allow_html=True
    )

    if col_prev.button("◀ Prev", key=f"{key_prefix}_prev_btn", disabled=(current_page <= 1), use_container_width=True):
        st.session_state[page_key] -= 1
        try:
            st.rerun(scope="fragment")
        except TypeError:
            st.rerun()

    col_page.markdown(
        f"<div style='text-align: center; padding-top: 6px; font-weight: 600; font-size: 13px; color: #1E293B;'>"
        f"Page {current_page} of {total_pages}"
        f"</div>",
        unsafe_allow_html=True
    )

    if col_next.button("Next ▶", key=f"{key_prefix}_next_btn", disabled=(current_page >= total_pages), use_container_width=True):
        st.session_state[page_key] += 1
        try:
            st.rerun(scope="fragment")
        except TypeError:
            st.rerun()

    # Slice items (works for list or pandas DataFrame)
    if hasattr(items, "iloc"):
        page_items = items.iloc[start_idx:end_idx]
    else:
        page_items = items[start_idx:end_idx]

    return page_items, current_page, total_pages


@st.fragment
def render_paginated_section(
    items,
    render_row_fn,
    page_size_default=25,
    key_prefix="page",
    page_size_options=[25, 50, 100],
    render_header_fn=None,
    empty_message="No records found."
):
    """
    Renders pagination controls and iterates rows inside an isolated @st.fragment.
    When users click Prev/Next or change page size, only this fragment re-renders,
    keeping page switches instant without triggering full-page reruns.
    """
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

    # Calculate starting index (1-based) for row numbering
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



def clear_data_cache(entity: str = None):
    """
    Selectively clears Streamlit data cache for mutated entities without wiping unaffected caches.
    entity options: 'jobs', 'candidates', 'lookups', or None (clears all operational data).
    """
    try:
        if entity == "lookups":
            get_master_lookups.clear()
        elif entity == "jobs":
            fetch_all_from_table.clear()
            get_recruiter_notification_data.clear()
            if "get_dashboard_data" in globals():
                get_dashboard_data.clear()
        elif entity == "candidates":
            fetch_all_live_candidates.clear()
            fetch_all_legacy_candidates.clear()
            get_unified_candidate_pool.clear()
            get_recruiter_notification_data.clear()
            if "get_dashboard_data" in globals():
                get_dashboard_data.clear()
            fetch_all_from_table.clear()
        else:
            get_master_lookups.clear()
            fetch_all_from_table.clear()
            fetch_all_live_candidates.clear()
            fetch_all_legacy_candidates.clear()
            get_unified_candidate_pool.clear()
            get_recruiter_notification_data.clear()
            if "get_dashboard_data" in globals():
                get_dashboard_data.clear()
    except Exception:
        pass



@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_legacy_candidates(select_fields: str):
    """
    Paginates through legacy_candidates table in Supabase to fetch ALL rows,
    bypassing PostgREST default 1000 row REST query cap. Cached for performance.
    """
    all_data = []
    chunk_size = 1000
    start = 0
    while True:
        try:
            data = (
                supabase.table("legacy_candidates")
                .select(select_fields)
                .order("legacy_candidate_id", desc=False)
                .range(start, start + chunk_size - 1)
                .execute()
                .data or []
            )
            all_data.extend(data)
            if len(data) < chunk_size:
                break
            start += chunk_size
        except Exception:
            break
    return all_data


@st.cache_data(ttl=120, show_spinner=False)
def fetch_all_live_candidates(select_fields: str):
    """
    Paginates through candidate_management table in Supabase to fetch ALL live candidate rows. Cached for performance.
    """
    return fetch_all_from_table("candidate_management", select_fields=select_fields, order_by="candidate_id", desc=True)


@st.cache_data(ttl=120)
def get_unified_candidate_pool():
    """
    Single source of truth for unified active + legacy candidate pool.
    Used concurrently across Job Matching (4_Job_Management) and AI Semantic Search (5_Candidate_Management).
    Eliminates duplicated in-memory fetches and reduces RAM usage.
    """
    inactive_statuses = {"retired", "deceased", "blacklisted", "inactive", "inactive / left market"}
    all_pool = []
    live_ids = set()

    try:
        fields_live = "candidate_id, candidate_reference_no, first_name, last_name, gender, approx_dob, email, mobile_no, current_company, current_designation, skills, experience_years, experience_months, current_ctc, expected_ctc, current_location, candidate_status, current_stage, resume_path, job_id, created_by_name, created_by_user_id, created_on, remarks"
        live_data = fetch_all_live_candidates(fields_live)
        for c in live_data:
            c_status = (c.get("candidate_status") or "").strip().lower()
            c_stage = (c.get("current_stage") or "").strip().lower()
            if c_status in inactive_statuses or c_stage in inactive_statuses:
                continue
            c["source_pool"] = "Live Pool"
            c["is_legacy"] = False
            live_ids.add(c["candidate_id"])
            all_pool.append(c)
    except Exception:
        pass

    try:
        fields_legacy = "legacy_candidate_id, candidate_reference_no, first_name, last_name, gender, approx_dob, email, mobile_no, current_company, current_designation, skills, experience_years, experience_months, current_ctc, expected_ctc, current_location, notice_period, notice_negotiable, qualification, education_details, resume_name, resume_path, is_migrated_to_active, migrated_candidate_id"
        legacy_data = fetch_all_legacy_candidates(fields_legacy)
        for c in legacy_data:
            if c.get("is_migrated_to_active") and c.get("migrated_candidate_id") in live_ids:
                continue
            c["candidate_id"] = f"LEG_{c['legacy_candidate_id']}"
            c["source_pool"] = "Legacy Pool"
            c["is_legacy"] = True

            nn = str(c.get("notice_negotiable") or "").strip()
            if nn.startswith("Deactivated:"):
                deact_status = nn.replace("Deactivated:", "").strip()
                if deact_status.lower() in inactive_statuses:
                    continue
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


@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_from_table(table_name: str, select_fields: str = "*", order_by: str = None, desc: bool = False):
    """
    Paginates through any Supabase table to fetch ALL records cleanly,
    bypassing the PostgREST default 1000-row limit per request. Cached for performance.
    """
    all_data = []
    chunk_size = 1000
    start = 0
    while True:
        try:
            q = supabase.table(table_name).select(select_fields)
            if order_by:
                q = q.order(order_by, desc=desc)
            res = q.range(start, start + chunk_size - 1).execute()
            data = res.data or []
            all_data.extend(data)
            if len(data) < chunk_size:
                break
            start += chunk_size
        except Exception:
            break
    return all_data


@st.cache_data(ttl=180, show_spinner=False)
def get_dashboard_data(user_id: int = None, user_role: str = "Admin"):
    """
    Fetches dashboard metrics dataset with intelligent role-based scoping:
    - If user_role == 'Recruiter': Queries only assigned jobs and associated candidates/interviews/offers via SQL,
      reducing data egress and load time by 10x+.
    - If user_role in ['Admin', 'Developer', 'Admin-Lite']: Concurrently fetches company-wide dataset for full visibility.
    """
    lookups = get_master_lookups()
    all_users = lookups.get("users", [])
    job_titles = lookups.get("job_titles", [])
    companies = lookups.get("companies", [])

    if not all_users:
        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                fut_users = executor.submit(lambda: supabase.table("users").select("user_id, full_name, email, role, status").execute().data or [])
                fut_titles = executor.submit(lambda: supabase.table("job_title_master").select("job_title_id, job_title_name").execute().data or [])
                fut_comps = executor.submit(lambda: supabase.table("company_master").select("company_id, company_name").execute().data or [])
                all_users = fut_users.result()
                job_titles = fut_titles.result()
                companies = fut_comps.result()
        except Exception:
            pass

    if user_role == "Recruiter" and user_id is not None:
        rec_assignments = (
            supabase.table("job_assignment")
            .select("job_id, user_id")
            .eq("user_id", user_id)
            .execute()
            .data or []
        )
        assigned_job_ids = list({ja["job_id"] for ja in rec_assignments if ja.get("job_id")})

        with ThreadPoolExecutor(max_workers=4) as executor:
            if assigned_job_ids:
                jids_str = ",".join(map(str, assigned_job_ids))
                fut_jobs = executor.submit(
                    lambda: supabase.table("job_management")
                    .select("job_id, job_reference_no, job_status, openings, company_id, job_title_id, created_date, modified_date, created_by")
                    .or_(f"job_id.in.({jids_str}),created_by.eq.{user_id}")
                    .execute().data or []
                )
            else:
                fut_jobs = executor.submit(
                    lambda: supabase.table("job_management")
                    .select("job_id, job_reference_no, job_status, openings, company_id, job_title_id, created_date, modified_date, created_by")
                    .eq("created_by", user_id)
                    .execute().data or []
                )

            cand_fields = "candidate_id, candidate_reference_no, first_name, last_name, job_id, current_stage, candidate_status, created_by_name, created_by_user_id, created_on, updated_on, mobile_no, email, current_company, current_designation, experience_years, experience_months, current_ctc, expected_ctc, notice_period, remarks"
            if assigned_job_ids:
                fut_candidates = executor.submit(
                    lambda: supabase.table("candidate_management")
                    .select(cand_fields)
                    .or_(f"created_by_user_id.eq.{user_id},job_id.in.({jids_str})")
                    .order("candidate_id", desc=True)
                    .execute().data or []
                )
            else:
                fut_candidates = executor.submit(
                    lambda: supabase.table("candidate_management")
                    .select(cand_fields)
                    .eq("created_by_user_id", user_id)
                    .order("candidate_id", desc=True)
                    .execute().data or []
                )

            if assigned_job_ids:
                fut_interviews = executor.submit(
                    lambda: supabase.table("interview_management")
                    .select("interview_id, candidate_id, job_id, interview_round, interview_date, interview_status, feedback, created_by_name, created_on")
                    .in_("job_id", assigned_job_ids)
                    .execute().data or []
                )
                fut_offers = executor.submit(
                    lambda: supabase.table("offer_management")
                    .select("offer_id, candidate_id, job_id, offer_status, offered_ctc, joining_date, remarks, created_by_name, created_on")
                    .in_("job_id", assigned_job_ids)
                    .execute().data or []
                )
            else:
                fut_interviews = executor.submit(lambda: [])
                fut_offers = executor.submit(lambda: [])

        return (
            fut_jobs.result(),
            fut_candidates.result(),
            fut_interviews.result(),
            fut_offers.result(),
            all_users,
            job_titles,
            companies,
            rec_assignments
        )

    # Org-wide fetch for Admin, Developer, Admin-Lite
    with ThreadPoolExecutor(max_workers=5) as executor:
        fut_jobs = executor.submit(
            fetch_all_from_table,
            "job_management",
            select_fields="job_id, job_reference_no, job_status, openings, company_id, job_title_id, created_date, modified_date, created_by"
        )
        fut_candidates = executor.submit(
            fetch_all_from_table,
            "candidate_management",
            select_fields="candidate_id, candidate_reference_no, first_name, last_name, job_id, current_stage, candidate_status, created_by_name, created_by_user_id, created_on, updated_on, mobile_no, email, current_company, current_designation, experience_years, experience_months, current_ctc, expected_ctc, notice_period, remarks",
            order_by="candidate_id",
            desc=True
        )
        fut_interviews = executor.submit(
            fetch_all_from_table,
            "interview_management",
            select_fields="interview_id, candidate_id, job_id, interview_round, interview_date, interview_status, feedback, created_by_name, created_on"
        )
        fut_offers = executor.submit(
            fetch_all_from_table,
            "offer_management",
            select_fields="offer_id, candidate_id, job_id, offer_status, offered_ctc, joining_date, remarks, created_by_name, created_on"
        )
        fut_assigns = executor.submit(lambda: supabase.table("job_assignment").select("job_id, user_id").execute().data or [])

    return (
        fut_jobs.result(),
        fut_candidates.result(),
        fut_interviews.result(),
        fut_offers.result(),
        all_users,
        job_titles,
        companies,
        fut_assigns.result()
    )



def fetch_candidates_server_side(
    page: int = 1,
    page_size: int = 25,
    search_text: str = "",
    status_filter: str = "All Status",
    gender_filter: str = "All Genders",
    selected_job_id: int = None,
    recruiter_filter: str = "All Recruiters",
    select_fields: str = "*"
):
    """
    Executes database-level server-side filtering, searching, and pagination in Postgres SQL.
    Returns (candidate_records, total_count). Scalable to 100,000+ candidate profiles.
    """
    try:
        q = supabase.table("candidate_management").select(select_fields, count="exact")
        
        if status_filter != "All Status":
            if status_filter in ["Joined / Hired", "Joined", "Hired"]:
                q = q.or_("candidate_status.in.(Joined,Hired),current_stage.in.(Joined,Hired)")
            else:
                q = q.or_(f"candidate_status.eq.{status_filter},current_stage.eq.{status_filter}")
            
        if gender_filter != "All Genders":
            q = q.eq("gender", gender_filter)
            
        if selected_job_id:
            q = q.eq("job_id", selected_job_id)
            
        if recruiter_filter != "All Recruiters":
            q = q.eq("created_by_name", recruiter_filter)
            
        if search_text and search_text.strip():
            # Sanitize search text: strip PostgREST structural delimiter characters (, and parentheses)
            st_clean = re.sub(r'[,()]', '', search_text.strip())
            if st_clean:
                q = q.or_(
                    f"candidate_reference_no.ilike.%{st_clean}%,"
                    f"first_name.ilike.%{st_clean}%,"
                    f"last_name.ilike.%{st_clean}%,"
                    f"email.ilike.%{st_clean}%,"
                    f"mobile_no.ilike.%{st_clean}%,"
                    f"current_company.ilike.%{st_clean}%,"
                    f"skills.ilike.%{st_clean}%"
                )
            
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size - 1
        
        res = q.order("candidate_id", desc=True).range(start_idx, end_idx).execute()
        return res.data or [], res.count or 0
    except Exception:
        return [], 0


def render_server_pagination_controls(total_items: int, page_size_default=25, key_prefix="server_page", page_size_options=[25, 50, 100]):
    """
    Renders Previous/Next controls for server-side SQL paginated queries.
    Returns (current_page, page_size).
    """
    page_key = f"{key_prefix}_current_page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    col_info, col_size, col_prev, col_page, col_next = st.columns([3.5, 1.8, 1.2, 1.8, 1.2])

    page_size = col_size.selectbox(
        "Rows per page",
        options=page_size_options,
        index=page_size_options.index(page_size_default) if page_size_default in page_size_options else 0,
        key=f"{key_prefix}_size_select",
        label_visibility="collapsed"
    )

    total_pages = max(1, (total_items + page_size - 1) // page_size)

    if st.session_state[page_key] > total_pages:
        st.session_state[page_key] = total_pages
    if st.session_state[page_key] < 1:
        st.session_state[page_key] = 1

    current_page = st.session_state[page_key]
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)

    col_info.markdown(
        f"<div style='padding-top: 6px; color: #475569; font-size: 13px;'>"
        f"Showing <b>{start_idx + 1 if total_items > 0 else 0}–{end_idx}</b> of <b>{total_items}</b> records (Server-side)"
        f"</div>",
        unsafe_allow_html=True
    )

    if col_prev.button("◀ Prev", key=f"{key_prefix}_prev_btn", disabled=(current_page <= 1), use_container_width=True):
        st.session_state[page_key] -= 1
        st.rerun()

    col_page.markdown(
        f"<div style='text-align: center; padding-top: 6px; font-weight: 600; font-size: 13px; color: #1E293B;'>"
        f"Page {current_page} of {total_pages}"
        f"</div>",
        unsafe_allow_html=True
    )

    if col_next.button("Next ▶", key=f"{key_prefix}_next_btn", disabled=(current_page >= total_pages), use_container_width=True):
        st.session_state[page_key] += 1
        st.rerun()

    return current_page, page_size



