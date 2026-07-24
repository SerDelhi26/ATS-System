import streamlit as st
from db import supabase

def show_logout():
    """Renders the standard logout button in the sidebar."""
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        st.switch_page("Home.py")

def show_job_notifications():
    """Renders a notification bell in the sidebar for newly assigned jobs."""
    if not st.session_state.get("logged_in", False):
        return
        
    user_id = st.session_state.get("user_id")
    user_role = st.session_state.get("user_role")
    
    # Notifications are meant for recruiters
    if user_role != "Recruiter":
        return

    try:
        # 1. Fetch job assignments for this specific user ID
        assignments = supabase.table("job_assignment").select("job_id").eq("user_id", user_id).execute().data
        assigned_job_ids = [a["job_id"] for a in assignments]
        
        if not assigned_job_ids:
            with st.sidebar:
                st.markdown("---")
                st.markdown("🔔 **Notifications:** No jobs assigned.")
            return

        # 2. Fetch the actual open job details for those IDs
        jobs = supabase.table("job_management").select("job_id, job_reference_no, job_status").in_("job_id", assigned_job_ids).execute().data
        
        open_assigned_jobs = [j for j in jobs if j["job_status"] == "Open"]
        
        # 3. Initialize seen jobs in session state if not present
        if "seen_job_ids" not in st.session_state:
            st.session_state.seen_job_ids = []
            
        # 4. Filter for unseen open jobs
        unseen_jobs = [
            j for j in open_assigned_jobs 
            if j["job_id"] not in st.session_state.seen_job_ids
        ]
        
        count = len(unseen_jobs)
        
        # 5. Render Notification Widget in Sidebar
        with st.sidebar:
            st.markdown("---")
            if count > 0:
                with st.expander(f"🔔 New Jobs ({count})", expanded=True):
                    st.markdown(f"**You have {count} newly assigned job(s):**")
                    for j in unseen_jobs:
                        st.markdown(f"📌 **{j['job_reference_no']}**")
                    
                    if st.button("Mark as Read", use_container_width=True):
                        # Mark all currently assigned open jobs as seen
                        st.session_state.seen_job_ids = [j["job_id"] for j in open_assigned_jobs]
                        st.rerun()
            else:
                st.markdown("🔔 **Notifications:** All caught up!")

    except Exception as e:
        pass