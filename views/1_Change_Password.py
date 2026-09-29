import streamlit as st
import bcrypt
try:
    from db import supabase_admin
except (ImportError, AttributeError):
    from db import supabase as supabase_admin
import time
from theme import apply_theme
from common import show_logout, show_job_notifications, show_user_profile
try:
    from common import check_login_lockout, record_login_result
except (ImportError, AttributeError):
    import importlib
    import common
    try:
        importlib.reload(common)
        from common import check_login_lockout, record_login_result
    except (ImportError, AttributeError):
        def check_login_lockout(email: str):
            clean_email = email.strip().lower()
            now_ts = time.time()
            if st.session_state.get("login_lockout_until", 0.0) > now_ts:
                return True, int(st.session_state.login_lockout_until - now_ts)
            return False, 0

        def record_login_result(email: str, success: bool):
            if success:
                st.session_state.login_failed_attempts = 0
                st.session_state.login_lockout_until = 0.0
                return False, 0, 0
            st.session_state.login_failed_attempts = st.session_state.get("login_failed_attempts", 0) + 1
            new_failed = st.session_state.login_failed_attempts
            if new_failed >= 5:
                st.session_state.login_lockout_until = time.time() + 180
                return True, 180, new_failed
            return False, 0, new_failed

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

clean_email = user_email.strip().lower()

# Check for active account-level or session-level lockout
is_locked, rem_sec = check_login_lockout(clean_email)
if is_locked:
    st.error(f"🔒 Account temporarily locked due to consecutive failed attempts. Please wait {rem_sec} seconds before trying again.")
    st.stop()

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
        # Re-verify lockout status before checking password
        is_locked, rem_sec = check_login_lockout(clean_email)
        if is_locked:
            st.error(f"⏳ Account temporarily locked due to consecutive failed attempts. Please wait {rem_sec} seconds before trying again.")
            st.stop()

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
                is_locked, rem_sec, failed_cnt = record_login_result(clean_email, success=False)
                if is_locked:
                    st.error("🚨 5 consecutive failed attempts. Account temporarily locked for 3 minutes.")
                else:
                    remaining = max(1, 5 - failed_cnt)
                    st.error(f"Current password is incorrect. ({remaining} attempts remaining before 3-minute lockout)")
            else:
                record_login_result(clean_email, success=True)
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