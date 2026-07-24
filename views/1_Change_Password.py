import streamlit as st
import bcrypt
from db import supabase
from theme import apply_theme
from common import show_logout, show_job_notifications, show_user_profile

# ==========================
# LOGIN CHECK
# ==========================
if not st.session_state.get("logged_in", False):
    st.error("You must be logged in to view this page.")
    st.stop()

# ==========================
# PAGE CONFIG
# ==========================
st.set_page_config(
    page_title="Change Password",
    layout="wide"
)

apply_theme()

# ==========================
# SIDEBAR
# ==========================
with st.sidebar:
    show_user_profile()
    show_logout()
    show_job_notifications()

# ==========================
# MAIN LAYOUT
# ==========================
st.markdown("# 🔑 Change Password")
st.info("Enter your current password and choose a new password.")

# Pre-fill email automatically since the user is logged in
user_email = ""
if st.session_state.get("user_id"):
    try:
        res = supabase.table("users").select("email").eq("user_id", st.session_state.user_id).single().execute()
        if res.data:
            user_email = res.data.get("email", "")
    except:
        pass

email = st.text_input("Email", value=user_email)
current_password = st.text_input("Current Password", type="password")
new_password = st.text_input("New Password", type="password")
confirm_password = st.text_input("Confirm New Password", type="password")

change_password = st.button("🔑 Change Password", use_container_width=True)

if change_password:
    
    if not email.strip():
        st.error("Email is required.")
    elif not current_password.strip():
        st.error("Current password is required.")
    elif not new_password.strip():
        st.error("New password cannot be blank.")
    elif new_password != confirm_password:
        st.error("Passwords do not match.")
    elif len(new_password) < 8:
        st.error("Password must contain at least 8 characters.")
    else:
        response = (
            supabase
            .table("users")
            .select("user_id, password_hash, status")
            .eq("email", email.strip())
            .eq("status", "Active")
            .execute()
        )

        if not response.data:
            st.error("User not found or account inactive.")
        else:
            user = response.data[0]

            if not bcrypt.checkpw(current_password.encode(), user["password_hash"].encode()):
                st.error("Current password is incorrect.")
            else:
                hashed_password = (
                    bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                )

                (
                    supabase
                    .table("users")
                    .update({"password_hash": hashed_password})
                    .eq("user_id", user["user_id"])
                    .execute()
                )

                st.success("Password changed successfully!")