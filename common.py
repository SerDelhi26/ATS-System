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
        assignments = supabase.table("job_assignment").select("job_id").eq("user_id", user_id).execute().data
        assigned_job_ids = [a["job_id"] for a in assignments]
        
        if not assigned_job_ids:
            with st.sidebar:
                st.markdown("---")
                st.markdown("🔔 **Notifications:** No jobs assigned.")
            return

        jobs = supabase.table("job_management").select("job_id, job_reference_no, job_status").in_("job_id", assigned_job_ids).execute().data
        open_assigned_jobs = [j for j in jobs if j["job_status"] == "Open"]
        
        if "seen_job_ids" not in st.session_state:
            st.session_state.seen_job_ids = []
            
        unseen_jobs = [
            j for j in open_assigned_jobs 
            if j["job_id"] not in st.session_state.seen_job_ids
        ]
        
        count = len(unseen_jobs)
        
        with st.sidebar:
            st.markdown("---")
            if count > 0:
                with st.expander(f"🔔 New Jobs ({count})", expanded=True):
                    st.markdown(f"**You have {count} newly assigned job(s):**")
                    for j in unseen_jobs:
                        st.markdown(f"📌 **{j['job_reference_no']}**")
                    
                    if st.button("Mark as Read", use_container_width=True):
                        st.session_state.seen_job_ids = [j["job_id"] for j in open_assigned_jobs]
                        st.rerun()
            else:
                st.markdown("🔔 **Notifications:** All caught up!")

    except Exception as e:
        pass