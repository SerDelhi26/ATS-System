import streamlit as st
import bcrypt
try:
    from db import supabase_admin
except (ImportError, AttributeError):
    from db import supabase as supabase_admin
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

# Pre-fill email automatically from the logged-in session user
user_id = st.session_state.get("user_id")
user_email = ""
if user_id:
    try:
        res = supabase_admin.table("users").select("email").eq("user_id", user_id).single().execute()
        if res.data:
            user_email = res.data.get("email", "")
    except Exception:
        pass

st.text_input("Account Email", value=user_email, disabled=True, help="Password changes apply strictly to your active logged-in account.")
current_password = st.text_input("Current Password", type="password")
new_password = st.text_input("New Password", type="password")
confirm_password = st.text_input("Confirm New Password", type="password")

change_password = st.button("🔑 Change Password", use_container_width=True)

if change_password:
    if not user_id:
        st.error("Authentication session expired. Please re-login.")
        st.stop()
    elif not current_password.strip():
        st.error("Current password is required.")
    elif not new_password.strip():
        st.error("New password cannot be blank.")
    elif new_password != confirm_password:
        st.error("Passwords do not match.")
    elif len(new_password) < 8:
        st.error("Password must contain at least 8 characters.")
    elif not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
        st.error("Password must contain at least one letter and one number.")
    else:
        response = (
            supabase_admin
            .table("users")
            .select("user_id, password_hash, status")
            .eq("user_id", user_id)
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
                    supabase_admin
                    .table("users")
                    .update({"password_hash": hashed_password})
                    .eq("user_id", user["user_id"])
                    .execute()
                )

                st.success("Password changed successfully!")