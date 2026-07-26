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