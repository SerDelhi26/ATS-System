import streamlit as st
from login import authenticate_user

st.set_page_config(
    page_title="ATS Login",
    layout="centered"
)

st.markdown("""
<style>
[data-testid="stSidebarNav"] {
    display: none;
}
</style>
""", unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in:

    st.switch_page(
        "pages/2_Dashboard.py"
    )

st.title("ATS Login")

email = st.text_input(
    "Email"
)

password = st.text_input(
    "Password",
    type="password"
)

col1, col2, col3 = st.columns([1, 3, 4])

with col1:

    if st.button(
        "Login"
    ):

        if authenticate_user(
            email,
            password
        ):

            st.success(
                "Login Successful"
            )

            st.rerun()

        else:

            st.error(
                "Invalid Email or Password"
            )

with col2:

    if st.button(
        "🔑 Change Password"
    ):

        st.session_state.password_reset_mode = True

        st.switch_page(
            "pages/1_Change_Password.py"
        )