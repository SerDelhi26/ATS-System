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
# LOGIN & RESET VIEW FUNCTION
# ==========================
def login_view():
    """Encapsulates the login and password reset UI to work seamlessly with the router."""
    
    # VIEW 1: PASSWORD RESET MODE
    if st.session_state.password_reset_mode:
        st.markdown("# 🔑 Change Password")
        st.info("Enter your current password and choose a new password.")
        
        with st.form("reset_form"):
            email = st.text_input("Email")
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            col1, col2 = st.columns(2)
            submit_change = col1.form_submit_button("🔑 Change Password", use_container_width=True)
            back_btn = col2.form_submit_button("↩ Back to Login", use_container_width=True)
            
        if back_btn:
            st.session_state.password_reset_mode = False
            st.rerun()
            
        if submit_change:
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
        
        return # Stop execution of the login form if in reset mode

    # VIEW 2: STANDARD LOGIN FORM
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
        st.rerun()

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

# ==========================
# ROUTING & NAVIGATION
# ==========================
if not st.session_state.logged_in:
    # Explicitly enforce a hidden navigation menu pointing to the function above
    pg = st.navigation([st.Page(login_view, title="Login", icon="🔐")], position="hidden")
    pg.run()

else:
    # User is logged in: Build dynamic page list based on role
    pages_list = [
        st.Page("views/2_Dashboard.py", title="Dashboard", icon="📊"),
        st.Page("views/5_Candidate_Management.py", title="Candidate Management", icon="👤"),
        st.Page("views/6_Interview_Management.py", title="Interview Management", icon="📅"),
        st.Page("views/7_Offer_Management.py", title="Offer Management", icon="📄"),
        st.Page("views/8_Report_Management.py", title="Report Management", icon="📈"),
    ]

    # Conditionally insert Admin-only pages
    if st.session_state.user_role == "Admin":
        pages_list.insert(1, st.Page("views/3_User_Management.py", title="User Management", icon="👥"))
        pages_list.insert(2, st.Page("views/4_Job_Management.py", title="Job Management", icon="💼"))

    # Add Change Password page for when logged in
    pages_list.append(st.Page("views/1_Change_Password.py", title="Change Password", icon="🔑"))

    pg = st.navigation(pages_list, position="sidebar")
    pg.run()