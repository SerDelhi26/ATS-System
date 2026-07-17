from db import supabase
import streamlit as st
import bcrypt

def authenticate_user(email, password):

    response = (
        supabase.table("users")
        .select(
            """
            user_id,
            full_name,
            email,
            role,
            password_hash,
            status
            """
        )
        .eq("email", email)
        .eq("status", "Active")
        .execute()
    )

    if response.data:

        user = response.data[0]

        if bcrypt.checkpw(
            password.encode(),
            user["password_hash"].encode()
        ):

            st.session_state.logged_in = True
            st.session_state.user_id = user["user_id"]
            st.session_state.user_name = user["full_name"]
            st.session_state.user_role = user["role"]

            return True

    return False