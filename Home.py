import streamlit as st
import bcrypt
from db import supabase
from theme import apply_theme

# ==========================
# PAGE CONFIG
# ==========================
st.set_page_config(
    page_title="ATS Login",
    layout="centered"
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

# If already logged in, redirect straight to the dashboard
if st.session_state.logged_in:
    st.switch_page("pages/2_Dashboard.py")

st.markdown("# 🔐 Welcome to ATS Login")
st.markdown("Please sign in to continue.")

# ==========================
# LOGIN FORM
# ==========================
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
                
                # Verify password hash using bcrypt
                if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                    st.session_state.logged_in = True
                    st.session_state.user_id = user["user_id"]
                    st.session_state.user_name = user["full_name"]  # Populates username correctly
                    st.session_state.user_role = user["role"]        # Populates role correctly
                    
                    st.success(f"Welcome back, {user['full_name']}!")
                    st.switch_page("pages/2_Dashboard.py")
                else:
                    st.error("Incorrect password.")
        except Exception as e:
            st.error(f"Login error: {str(e)}")