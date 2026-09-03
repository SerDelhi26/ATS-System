import os
import base64
import streamlit as st
from db import supabase

def render_logo(width=220, align="left"):
    """
    Renders the unified 1 Point Solution company logo with 100% alpha transparency.
    """
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")
    if not os.path.exists(logo_path):
        return
        
    try:
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            
        st.markdown(
            f"""
            <div class="ats-logo-wrapper" style="text-align: {align}; margin-bottom: 12px;">
                <img src="data:image/png;base64,{b64}" style="width: {width}px; max-width: 100%; height: auto;" />
            </div>
            """,
            unsafe_allow_html=True
        )
    except Exception:
        pass

def show_user_profile():
    """Displays company logo and the logged-in user's name and role at the top of the sidebar."""
    with st.sidebar:
        render_logo(width=200, align="center")

        if st.session_state.get("logged_in", False):
            name = st.session_state.get("user_name", "User")
            role = st.session_state.get("user_role", "")
            st.markdown(f"👤 **{name}**")
            st.caption(f"Role: {role}")
            st.markdown("---")

def show_logout():
    """Renders the standard logout button in the sidebar and safely returns to login."""
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

@st.cache_data(ttl=20)
def get_recruiter_notification_data(user_id):
    """Cached helper to fetch assigned open jobs, candidate submissions, and lookups for notifications."""
    assignments = supabase.table("job_assignment").select("job_id").eq("user_id", user_id).execute().data or []
    assigned_job_ids = [a["job_id"] for a in assignments]
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
    jobs_with_candidates = {c["job_id"] for c in candidates_added}
    
    job_titles = supabase.table("job_title_master").select("job_title_id, job_title_name").execute().data or []
    companies = supabase.table("company_master").select("company_id, company_name").execute().data or []
    title_lookup = {t["job_title_id"]: t["job_title_name"] for t in job_titles}
    company_lookup = {c["company_id"]: c["company_name"] for c in companies}
    
    return jobs, jobs_with_candidates, title_lookup, company_lookup

def show_job_notifications():
    """Renders a notification bell in the sidebar for newly assigned jobs."""
    if not st.session_state.get("logged_in", False):
        return
        
    user_id = st.session_state.get("user_id")
    user_role = st.session_state.get("user_role")
    
    if user_role != "Recruiter":
        return

    try:
        jobs, jobs_with_candidates, title_lookup, company_lookup = get_recruiter_notification_data(user_id)
        
        if not jobs:
            with st.sidebar:
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
        
        with st.sidebar:
            st.markdown("---")
            if count > 0:
                with st.expander(f"🔔 New Jobs ({count})", expanded=True):
                    st.markdown(f"**You have {count} newly assigned job(s):**")

                    for j in unseen_jobs:
                        col1, col2 = st.columns([0.6, 0.4])
                        col1.markdown(f"<div style='margin-top: 8px;'>📌 <b>{j['job_reference_no']}</b></div>", unsafe_allow_html=True)
                        
                        with col2:
                            with st.popover("👁️ View", use_container_width=True):
                                st.markdown(f"**Job No:** {j['job_reference_no']}")
                                st.markdown(f"**Title:** {title_lookup.get(j.get('job_title_id'), 'N/A')}")
                                st.markdown(f"**Company:** {company_lookup.get(j.get('company_id'), 'N/A')}")
                                st.markdown(f"**Location:** {j.get('location', 'N/A')}")
                                st.markdown(f"**Experience:** {j.get('experience_min_year', 0)} - {j.get('experience_max_year', 0)} Yrs")
                                st.markdown(f"**Budget:** {j.get('pay_min', 0)} - {j.get('pay_max', 0)} {j.get('currency', '')}")
                                st.markdown(f"**Skills:** {j.get('skills_required', 'N/A')}")
                                st.info(j.get('job_description', 'No description provided.'))
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("Mark All as Read", use_container_width=True):
                        st.session_state.seen_job_ids.extend([j["job_id"] for j in unseen_jobs])
                        st.rerun()
            else:
                st.markdown("🔔 **Notifications:** All caught up!")

    except Exception:
        pass


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

    # Slice items (works for list or pandas DataFrame)
    if hasattr(items, "iloc"):
        page_items = items.iloc[start_idx:end_idx]
    else:
        page_items = items[start_idx:end_idx]

    return page_items, current_page, total_pages


def fetch_all_legacy_candidates(select_fields: str):
    """
    Paginates through legacy_candidates table in Supabase to fetch ALL rows,
    bypassing PostgREST default 1000 row REST query cap.
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


def fetch_all_live_candidates(select_fields: str):
    """
    Paginates through candidate_management table in Supabase to fetch ALL live candidate rows.
    """
    return fetch_all_from_table("candidate_management", select_fields=select_fields, order_by="candidate_id", desc=True)


def fetch_all_from_table(table_name: str, select_fields: str = "*", order_by: str = None, desc: bool = False):
    """
    Paginates through any Supabase table to fetch ALL records cleanly,
    bypassing the PostgREST default 1000-row limit per request.
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
