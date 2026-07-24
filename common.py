import streamlit as st
from db import supabase

def show_job_notifications():
    # Only run for logged-in recruiters
    if not st.session_state.get("logged_in", False):
        return
        
    user_id = st.session_state.get("user_id")
    user_role = st.session_state.get("user_role")
    
    # Typically notifications are for recruiters, but you can include admins if needed
    if user_role != "Recruiter":
        return

    try:
        # 1. Get job IDs assigned to this recruiter
        assignments = supabase.table("job_assignment").select("job_id").eq("user_id", user_id).execute().data
        assigned_job_ids = [a["job_id"] for a in assignments]
        
        if not assigned_job_ids:
            return

        # 2. Fetch the actual job details for those IDs
        jobs = supabase.table("job_management").select("job_id, job_reference_no, job_status").in_("job_id", assigned_job_ids).execute().data
        
        # 3. Initialize seen jobs in session state if not present
        if "seen_job_ids" not in st.session_state:
            # On first login, mark current jobs as seen so it doesn't trigger a flood of past alerts
            st.session_state.seen_job_ids = [j["job_id"] for j in jobs]
            
        # 4. Filter for unseen open jobs
        unseen_jobs = [
            j for j in jobs 
            if j["job_id"] not in st.session_state.seen_job_ids and j["job_status"] == "Open"
        ]
        
        count = len(unseen_jobs)
        
        # 5. Render the Notification Widget in the Sidebar
        with st.sidebar:
            st.markdown("---")
            if count >  0:
                # Highlighted notification box when new jobs arrive
                with st.expander(f"🔔 New Jobs ({count})", expanded=True):
                    st.markdown(f"**You have {count} newly assigned job(s):**")
                    for j in unseen_jobs:
                        st.markdown(f"📌 **{j['job_reference_no']}**")
                    
                    if st.button("Mark as Read", use_container_width=True):
                        # Update seen IDs to include all current job IDs
                        st.session_state.seen_job_ids = [j["job_id"] for j in jobs]
                        st.rerun()
            else:
                st.markdown("🔔 **Notifications:** All caught up!")

    except Exception as e:
        # Fail silently in the UI so a network blip doesn't crash the sidebar
        pass