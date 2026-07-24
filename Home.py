import streamlit as st
import bcrypt
from db import supabase
from theme import apply_theme

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

# ==========================
# ROUTING & DYNAMIC NAVIGATION
# ==========================
if not st.session_state.logged_in:
    # Hide sidebar navigation completely while logged out
    pg = st.navigation([st.Page("Home.py", title="Login", icon="🔐")], position="hidden")
    
    # Render Login Form UI
    st.markdown("# 🔐 Welcome to ATS Login")
    st.markdown("Please sign in to continue.")
    
    with st.form("login_form"):
        email = st.text_input("Email Address")
        password = st.text_input("Password", type="password")
        
        col1, col2 = st.columns(2)
        submit_login = col1.form_submit_button("🔑 Login", use_container_width=True)
        forgot_password = col2.form_submit_button("🔄 Change Password", use_container_width=True)

    if forgot_password:
        st.session_state.password_reset_mode = True
        st.switch_page("pages/1_Change_Password.py")

    if submit_login:
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
                    st.error("Invalid email or account is inactive.")
                else:
                    user = response.data[0]
                    
                    if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                        st.session_state.logged_in = True
                        st.session_state.user_id = user["user_id"]
                        st.session_state.user_name = user["full_name"]
                        st.session_state.user_role = user["role"]
                        st.success(f"Welcome back, {user['full_name']}!")
                        st.rerun()
                    else:
                        st.error("Incorrect password.")
            except Exception as e:
                st.error(f"Login error: {str(e)}")
                
    pg.run()

else:
    # User is logged in: Build dynamic page list based on role
    pages_list = [
        st.Page("pages/2_Dashboard.py", title="Dashboard", icon="📊"),
        st.Page("pages/5_Candidate_Management.py", title="Candidate Management", icon="👤"),
        st.Page("pages/6_Interview_Management.py", title="Interview Management", icon="📅"),
        st.Page("pages/7_Offer_Management.py", title="Offer Management", icon="📄"),
        st.Page("pages/8_Report_Management.py", title="Report Management", icon="📈"),
    ]

    # Conditionally insert Admin-only pages if user role is Admin
    if st.session_state.user_role == "Admin":
        pages_list.insert(1, st.Page("pages/3_User_Management.py", title="User Management", icon="👥"))
        pages_list.insert(2, st.Page("pages/4_Job_Management.py", title="Job Management", icon="💼"))

    # Add Change Password page for everyone
    pages_list.append(st.Page("pages/1_Change_Password.py", title="Change Password", icon="🔑"))

    # Render sidebar navigation with role-filtered pages
    pg = st.navigation(pages_list, position="sidebar")
    pg.run()