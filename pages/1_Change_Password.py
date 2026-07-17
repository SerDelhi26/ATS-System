import streamlit as st
import bcrypt
from db import supabase
from theme import apply_theme

if not st.session_state.get(
    "password_reset_mode",
    False
):

    st.switch_page("Home.py")

    st.stop()

st.set_page_config(
    page_title="Change Password",
    layout="centered"
)

apply_theme()

st.markdown(
    "# 🔑 Change Password"
)

st.info(
    "Enter your current password and choose a new password."
)

email = st.text_input("Email")

current_password = st.text_input(
    "Current Password",
    type="password"
)

new_password = st.text_input(
    "New Password",
    type="password"
)

confirm_password = st.text_input(
    "Confirm New Password",
    type="password"
)

change_password = st.button(
    "🔑 Change Password",
    use_container_width=True
)

if change_password:


    response = (
        supabase
        .table("users")
        .select(
            """
            user_id,
            password_hash,
            status
            """
        )
        .eq("email", email)
        .eq("status", "Active")
        .execute()
    )

    if not response.data:

        st.error(
            "User not found."
        )

    else:

        user = response.data[0]

        if not bcrypt.checkpw(
            current_password.encode(),
            user["password_hash"].encode()
        ):

            st.error(
                "Current password is incorrect."
            )

        elif new_password != confirm_password:

            st.error(
                "Passwords do not match."
            )

        elif not new_password.strip():

            st.error(
                "New password cannot be blank."
            )

        elif len(new_password) < 8:

            st.error(
                "Password must contain at least 8 characters."
            )

        else:

            hashed_password = (
                bcrypt.hashpw(
                    new_password.encode(),
                    bcrypt.gensalt()
                )
                .decode()
            )

            (
                supabase
                .table("users")
                .update(
                    {
                        "password_hash":
                        hashed_password
                    }
                )
                .eq(
                    "user_id",
                    user["user_id"]
                )
                .execute()
            )

            st.success(
                "Password changed successfully."
            )
            st.session_state.password_reset_mode = False

back_to_login = st.button(
    "↩ Back to Login",
    use_container_width=True
)

if back_to_login:

    st.session_state.password_reset_mode = False

    st.switch_page("Home.py")