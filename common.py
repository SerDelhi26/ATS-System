import streamlit as st
from db import supabase

def show_user_profile():
    """Displays the logged-in user's name and role at the top of the sidebar."""
    if st.session_state.get("logged_in", False):
        name = st.session_state.get("user_name", "User")
        role = st.session_state.get("user_role", "")
        with st.sidebar:
            st.markdown(f"👤 **{name}**")
            st.caption(f"Role: {role}")
            st.markdown("---")

def show_logout():
    """Renders the standard logout button in the sidebar and safely returns to login."""
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

def show_job_notifications():
    """Renders a notification bell in the sidebar for newly assigned jobs."""
    if not st.session_state.get("logged_in", False):
        return
        
    user_id = st.session_state.get("user_id")
    user_role = st.session_state.get("user_role")
    
    if user_role != "Recruiter":
        return

    try:
        # 1. Get Assigned Jobs
        assignments = supabase.table("job_assignment").select("job_id").eq("user_id", user_id).execute().data
        assigned_job_ids = [a["job_id"] for a in assignments]
        
        if not assigned_job_ids:
            with st.sidebar:
                st.markdown("---")
                st.markdown("🔔 **Notifications:** No jobs assigned.")
            return

        # 2. Get Open Jobs (Fetch full details for the View Details feature)
        jobs = (
            supabase.table("job_management")
            .select("*")
            .in_("job_id", assigned_job_ids)
            .eq("job_status", "Open")
            .execute()
            .data
        )
        
        # 3. Smart Condition: Check which assigned jobs the user HAS submitted candidates for
        candidates_added = (
            supabase.table("candidate_management")
            .select("job_id")
            .eq("created_by_user_id", user_id)
            .in_("job_id", assigned_job_ids)
            .execute()
            .data
        )
        jobs_with_candidates = {c["job_id"] for c in candidates_added}

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
                    
                    # Only fetch lookup tables if there are unseen jobs to render
                    job_titles = supabase.table("job_title_master").select("*").execute().data
                    companies = supabase.table("company_master").select("*").execute().data
                    title_lookup = {t["job_title_id"]: t["job_title_name"] for t in job_titles}
                    company_lookup = {c["company_id"]: c["company_name"] for c in companies}

                    for j in unseen_jobs:
                        col1, col2 = st.columns([0.6, 0.4])
                        col1.markdown(f"<div style='margin-top: 8px;'>📌 <b>{j['job_reference_no']}</b></div>", unsafe_allow_html=True)
                        
                        with col2:
                            # Streamlit popover creates a button that opens a floating container with details
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

    except Exception as e:
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