import os
import sys
import importlib
import time
import base64
import streamlit as st
import bcrypt
from db import supabase
from theme import apply_theme
import common
importlib.reload(common)
from common import render_logo

# ==========================
# PAGE CONFIG
# ==========================
st.set_page_config(
    page_title="ATS System",
    layout="wide"
)

apply_theme()

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
            else:
                try:
                    response = (
                        supabase
                        .table("users")
                        .select("user_id, password_hash, status")
                        .eq("email", email.strip())
                        .eq("status", "Active")
                        .execute()
                    )
                    
                    if not response.data:
                        st.error("User not found or inactive.")
                    else:
                        user = response.data[0]
                        if not bcrypt.checkpw(current_password.encode(), user["password_hash"].encode()):
                            st.error("Current password is incorrect.")
                        else:
                            hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                            supabase.table("users").update({"password_hash": hashed_password}).eq("user_id", user["user_id"]).execute()
                            st.success("Password changed successfully. Please log in.")
                            st.session_state.password_reset_mode = False
                            st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        return

    render_logo(width=240, align="left")

    st.markdown("# 🔐 Welcome to ATS Login")
    st.markdown("Please sign in to continue.")

    # Check for active brute-force lockout
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
        now = time.time()
        if st.session_state.login_lockout_until > now:
            remaining_sec = int(st.session_state.login_lockout_until - now)
            st.error(f"⏳ Please wait {remaining_sec} seconds before attempting to login again.")
            st.stop()

        if not email.strip() or not password.strip():
            st.error("Please enter both email and password.")
        else:
            try:
                response = (
                    supabase
                    .table("users")
                    .select("user_id, full_name, role, password_hash, status")
                    .eq("email", email.strip())
                    .eq("status", "Active")
                    .execute()
                )

                if not response.data:
                    st.session_state.login_failed_attempts += 1
                    if st.session_state.login_failed_attempts >= 5:
                        st.session_state.login_lockout_until = time.time() + 180  # 3-minute lockout
                        st.error("🚨 5 consecutive failed attempts. Login temporarily locked for 3 minutes.")
                    else:
                        remaining = 5 - st.session_state.login_failed_attempts
                        st.error(f"Invalid email or account is inactive. ({remaining} attempts remaining)")
                else:
                    user = response.data[0]
                    
                    if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                        # Reset failed attempt counter on success
                        st.session_state.login_failed_attempts = 0
                        st.session_state.login_lockout_until = 0.0
                        st.session_state.logged_in = True
                        st.session_state.user_id = user["user_id"]
                        st.session_state.user_name = user["full_name"]
                        st.session_state.user_role = user["role"]
                        st.success(f"Welcome back, {user['full_name']}!")
                        st.rerun()
                    else:
                        st.session_state.login_failed_attempts += 1
                        if st.session_state.login_failed_attempts >= 5:
                            st.session_state.login_lockout_until = time.time() + 180  # 3-minute lockout
                            st.error("🚨 5 consecutive failed attempts. Login temporarily locked for 3 minutes.")
                        else:
                            remaining = 5 - st.session_state.login_failed_attempts
                            st.error(f"Incorrect password. ({remaining} attempts remaining)")
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
        st.Page("views/9_Talent_Mapping.py", title="Talent Mapping", icon="🗺️"),
        st.Page("views/6_Interview_Management.py", title="Interview Management", icon="📅"),
        st.Page("views/7_Offer_Management.py", title="Offer Management", icon="📄"),
    ]

    # Admins and Developers get User Management and Report Management (Hidden completely for Recruiters)
    if st.session_state.user_role in ["Admin", "Developer"]:
        pages_list.insert(1, st.Page("views/3_User_Management.py", title="User Management", icon="👥"))
        pages_list.insert(2, st.Page("views/8_Report_Management.py", title="Report Management", icon="📈"))

    # Future Developer-exclusive modules hook
    if st.session_state.user_role == "Developer":
        # Future developer-exclusive modules will be attached here
        pass

    pages_list.append(st.Page("views/1_Change_Password.py", title="Change Password", icon="🔑"))

    pg = st.navigation(pages_list, position="sidebar")
    pg.run()