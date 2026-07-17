import streamlit as st


def show_logout():

    st.divider()

    st.success(
        f"Welcome {st.session_state.get('user_name', '')}"
    )

    if st.button(
        "Logout",
        use_container_width=True
    ):

        for key in list(
            st.session_state.keys()
        ):
            del st.session_state[key]

        st.switch_page("Home.py")