import os
import sys
import time
import base64
import streamlit as st
import bcrypt
from db import supabase
try:
    from db import supabase_admin
except (ImportError, AttributeError):
    supabase_admin = supabase
from theme import apply_theme
from common import render_logo

# ==========================
# PAGE CONFIG
# ==========================
st.set_page_config(
    page_title="ATS System",
    layout="wide"
)

apply_theme()

# Check Session Inactivity Timeout (30 minutes)
IDLE_TIMEOUT_SECONDS = 30 * 60
if st.session_state.get("logged_in", False):
    now = time.time()
    last_act = st.session_state.get("last_activity", now)
    if now - last_act > IDLE_TIMEOUT_SECONDS:
        st.session_state.clear()
        st.session_state["session_timeout_msg"] = "🔒 Session expired due to 30 minutes of inactivity. Please log in again."
        st.rerun()
    st.session_state["last_activity"] = now

# Initialize Session State Variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "password_reset_mode" not in st.session_state:
    st.session_state.password_reset_mode = False
if "login_failed_attempts" not in st.session_state:
    st.session_state.login_failed_attempts = 0
if "login_lockout_until" not in st.session_state:
    st.session_state.login_lockout_until = 0.0
if "last_activity" not in st.session_state:
    st.session_state.last_activity = time.time()


def check_login_lockout(email: str) -> tuple[bool, int]:
    """Checks account-scoped server-side lockout (login_attempts table) and session-scoped fallback."""
    clean_email = email.strip().lower()
    now_ts = time.time()
    if st.session_state.get("login_lockout_until", 0.0) > now_ts:
        return True, int(st.session_state.login_lockout_until - now_ts)

    if not clean_email:
        return False, 0

    try:
        res = supabase_admin.table("login_attempts").select("failed_count, locked_until").eq("email", clean_email).execute()
        if res.data:
            rec = res.data[0]
            locked_until_str = rec.get("locked_until")
            if locked_until_str:
                from datetime import datetime, timezone
                clean_dt_str = str(locked_until_str).replace("Z", "+00:00")
                lock_dt = datetime.fromisoformat(clean_dt_str)
                now_dt = datetime.now(timezone.utc)
                if lock_dt > now_dt:
                    rem = int((lock_dt - now_dt).total_seconds())
                    return True, rem
    except Exception:
        pass

    return False, 0


def record_login_result(email: str, success: bool) -> tuple[bool, int, int]:
    """
    Updates failed_count & locked_until server-side atomically via Postgres RPC (record_login_failure).
    Eliminates race conditions under parallel bot brute-force attacks.
    Falls back gracefully to client-level upsert if the RPC is not yet created.
    """
    clean_email = email.strip().lower()
    if not clean_email:
        return False, 0, 0

    if success:
        st.session_state.login_failed_attempts = 0
        st.session_state.login_lockout_until = 0.0
        try:
            supabase_admin.rpc("clear_login_attempts", {"target_email": clean_email}).execute()
        except Exception:
            try:
                supabase_admin.table("login_attempts").delete().eq("email", clean_email).execute()
            except Exception:
                pass
        return False, 0, 0

    # 1. Primary: Atomic server-side increment & lockout via Postgres RPC
    try:
        rpc_res = supabase_admin.rpc("record_login_failure", {"target_email": clean_email}).execute()
        if rpc_res.data:
            row = rpc_res.data[0] if isinstance(rpc_res.data, list) else rpc_res.data
            server_failed = row.get("failed_count", 1)
            is_locked = bool(row.get("is_locked", False))
            rem_sec = int(row.get("remaining_seconds", 0))

            st.session_state.login_failed_attempts = server_failed
            if is_locked:
                st.session_state.login_lockout_until = time.time() + rem_sec
            return is_locked, rem_sec, server_failed
    except Exception:
        pass

    # 2. Resilient Fallback: Standard upsert if RPC is not yet deployed
    from datetime import datetime, timezone, timedelta
    now_dt = datetime.now(timezone.utc)
    st.session_state.login_failed_attempts = st.session_state.get("login_failed_attempts", 0) + 1
    new_failed = st.session_state.login_failed_attempts
    locked_until_iso = None
    is_locked = False
    rem_sec = 0

    try:
        res = supabase_admin.table("login_attempts").select("failed_count, locked_until").eq("email", clean_email).execute()
        server_count = (res.data[0].get("failed_count", 0) if res.data else 0) + 1
        new_failed = max(server_count, new_failed)

        if new_failed >= 5:
            lock_until_dt = now_dt + timedelta(seconds=180)
            locked_until_iso = lock_until_dt.isoformat()
            is_locked = True
            rem_sec = 180
            st.session_state.login_lockout_until = time.time() + 180

        supabase_admin.table("login_attempts").upsert({
            "email": clean_email,
            "failed_count": new_failed,
            "locked_until": locked_until_iso
        }).execute()
    except Exception:
        if new_failed >= 5:
            st.session_state.login_lockout_until = time.time() + 180
            is_locked = True
            rem_sec = 180

    return is_locked, rem_sec, new_failed


# ==========================
# LOGIN & RESET VIEW FUNCTION
# ==========================
def login_view():
    """Encapsulates the login and password reset UI to work seamlessly with the router."""
    if st.session_state.password_reset_mode:
        render_logo(width=220, align="left")
            
        st.markdown("# 🔑 Change Password")
        st.info("Enter your current password and choose a new password.")
        
        def on_reset_enter():
            st.session_state.reset_triggered = True

        email = st.text_input("Email", key="reset_email")
        current_password = st.text_input("Current Password", type="password", key="reset_curr_pwd")
        new_password = st.text_input("New Password", type="password", key="reset_new_pwd")
        confirm_password = st.text_input("Confirm New Password", type="password", key="reset_conf_pwd", on_change=on_reset_enter)

        col1, col2 = st.columns([1, 1])
        with col1:
            submit_change = st.button("🔑 Change Password", use_container_width=True, type="primary")
        with col2:
            if st.button("↩ Back to Login", use_container_width=True):
                st.session_state.password_reset_mode = False
                st.rerun()
            
        do_change = submit_change or st.session_state.pop("reset_triggered", False)
        if do_change:
            if not email.strip() or not current_password.strip() or not new_password.strip():
                st.error("All fields are required.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            elif len(new_password) < 8:
                st.error("Password must contain at least 8 characters.")
            elif not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
                st.error("Password must contain at least one letter and one number.")
            else:
                try:
                    response = (
                        supabase_admin
                        .table("users")
                        .select("user_id, password_hash, status")
                        .eq("email", email.strip())
                        .eq("status", "Active")
                        .execute()
                    )
                    
                    if not response.data:
                        st.error("Invalid email, password, or account is inactive.")
                    else:
                        user = response.data[0]
                        if not bcrypt.checkpw(current_password.encode(), user["password_hash"].encode()):
                            st.error("Invalid email, password, or account is inactive.")
                        else:
                            hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                            supabase_admin.table("users").update({"password_hash": hashed_password}).eq("user_id", user["user_id"]).execute()
                            st.success("Password changed successfully. Please log in.")
                            st.session_state.password_reset_mode = False
                            st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        return

    if st.session_state.get("session_timeout_msg"):
        st.warning(st.session_state.pop("session_timeout_msg"))

    render_logo(width=240, align="left")

    st.markdown("# 🔐 Welcome to ATS Login")
    st.markdown("Please sign in to continue.")

    # Check for active session-level brute-force lockout
    now = time.time()
    if st.session_state.login_lockout_until > now:
        remaining_sec = int(st.session_state.login_lockout_until - now)
        st.error(f"🔒 Account temporarily locked due to 5 consecutive failed login attempts. Please wait {remaining_sec} seconds before trying again.")
        st.stop()
    
    def on_password_enter():
        st.session_state.submit_triggered = True

    email = st.text_input("Email Address", key="login_email")
    password = st.text_input("Password", type="password", key="login_password", on_change=on_password_enter)

    col1, col2 = st.columns([1, 1])
    with col1:
        submit_login = st.button("🔑 Login", use_container_width=True, type="primary")
    with col2:
        if st.button("🔄 Change Password", use_container_width=True):
            st.session_state.password_reset_mode = True
            st.rerun()

    do_submit = submit_login or st.session_state.pop("submit_triggered", False)

    if do_submit:
        clean_email = email.strip().lower()
        if not clean_email or not password.strip():
            st.error("Please enter both email and password.")
        else:
            # Check server-side account-scoped lockout
            is_locked, rem_sec = check_login_lockout(clean_email)
            if is_locked:
                st.error(f"⏳ Account temporarily locked due to 5 consecutive failed login attempts. Please wait {rem_sec} seconds before trying again.")
                st.stop()

            try:
                response = (
                    supabase_admin
                    .table("users")
                    .select("user_id, full_name, role, password_hash, status")
                    .eq("email", clean_email)
                    .eq("status", "Active")
                    .execute()
                )

                if not response.data:
                    is_locked, rem_sec, failed_cnt = record_login_result(clean_email, success=False)
                    if is_locked:
                        st.error("🚨 5 consecutive failed attempts. Account temporarily locked for 3 minutes.")
                    else:
                        remaining = max(1, 5 - failed_cnt)
                        st.error(f"Invalid email or password. ({remaining} attempts remaining before 3-minute lockout)")
                else:
                    user = response.data[0]
                    
                    if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                        record_login_result(clean_email, success=True)
                        st.session_state.logged_in = True
                        st.session_state.user_id = user["user_id"]
                        st.session_state.user_name = user["full_name"]
                        st.session_state.user_role = user["role"]
                        st.session_state.last_activity = time.time()
                        st.success(f"Welcome back, {user['full_name']}!")
                        st.rerun()
                    else:
                        is_locked, rem_sec, failed_cnt = record_login_result(clean_email, success=False)
                        if is_locked:
                            st.error("🚨 5 consecutive failed attempts. Account temporarily locked for 3 minutes.")
                        else:
                            remaining = max(1, 5 - failed_cnt)
                            st.error(f"Invalid email or password. ({remaining} attempts remaining before 3-minute lockout)")
            except Exception as e:
                st.error(f"Login error: {str(e)}")

# ==========================
# ROUTING & NAVIGATION
# ==========================
if not st.session_state.logged_in:
    pg = st.navigation([st.Page(login_view, title="Login", icon="🔐")], position="hidden")
    pg.run()

else:
    # Build dynamic page list: Job Management is now available to ALL users
    pages_list = [
        st.Page("views/2_Dashboard.py", title="Dashboard", icon="📊"),
        st.Page("views/4_Job_Management.py", title="Job Management", icon="💼"),
        st.Page("views/5_Candidate_Management.py", title="Candidate Management", icon="👤"),
        st.Page("views/6_Interview_Management.py", title="Interview Management", icon="📅"),
        st.Page("views/7_Offer_Management.py", title="Offer Management", icon="📄"),
    ]

    # Admins, Admin-Lite and Developers get User Management, Report Management, and Talent Mapping (Hidden completely for Recruiters)
    if st.session_state.user_role in ["Admin", "Developer", "Admin-Lite"]:
        pages_list.insert(1, st.Page("views/3_User_Management.py", title="User Management", icon="👥"))
        pages_list.insert(2, st.Page("views/8_Report_Management.py", title="Report Management", icon="📈"))
        pages_list.insert(5, st.Page("views/9_Talent_Mapping.py", title="Talent Mapping", icon="🗺️"))

    # Future Developer-exclusive modules hook
    if st.session_state.user_role == "Developer":
        # Future developer-exclusive modules will be attached here
        pass

    pages_list.append(st.Page("views/1_Change_Password.py", title="Change Password", icon="🔑"))

    pg = st.navigation(pages_list, position="sidebar")
    pg.run()