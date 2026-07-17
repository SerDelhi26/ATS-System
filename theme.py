import streamlit as st

def apply_theme():

    st.markdown("""
    <style>

    div.stButton > button {
        background-color: #1F4E79;
        color: white;
        border-radius: 8px;
        border: none;
    }

    div.stButton > button:hover {
        background-color: #2563EB;
        color: white;
    }

    </style>
    """,
    unsafe_allow_html=True)