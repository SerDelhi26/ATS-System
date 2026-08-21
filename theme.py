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

    /* Hide Streamlit auto-injected page search bar in sidebar */
    [data-testid="stSidebarNavSearch"],
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] input,
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] > div:has(input),
    div[data-testid="stSidebarNavItems"] + div {
        display: none !important;
    }

    </style>
    """,
    unsafe_allow_html=True)