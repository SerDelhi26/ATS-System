import streamlit as st

def apply_theme():

    st.markdown("""
    <style>

    .main {
        background-color: #F8FAFC;
    }

    h1, h2, h3 {
        color: #1F4E79;
    }

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

    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
    }

    </style>
    """,
    unsafe_allow_html=True)