import streamlit as st
import bcrypt
from db import supabase

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

st.title("Change Password")

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

if st.button("Change Password"):

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

if st.button("Back to Login"):

    st.session_state.password_reset_mode = False

    st.switch_page("Home.py")