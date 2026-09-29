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

    /* Hide the entire Streamlit top-right toolbar
       (Share, Star, Edit/Pencil, GitHub, three-dot menu) */
    [data-testid="stToolbar"],
    [data-testid="stToolbarActions"],
    [data-testid="stDecoration"],
    .stAppDeployButton,
    [data-testid="stAppDeployButton"] {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        overflow: hidden !important;
    }

    /* Make the top header bar transparent so it doesn't take visual space */
    header[data-testid="stHeader"] {
        background: transparent !important;
        pointer-events: none !important;
    }

    /* Hide Streamlit main hamburger / three-dot menu */
    #MainMenu {
        display: none !important;
        visibility: hidden !important;
    }

    /* Suppress Streamlit's transient missing submit button warning in forms */
    div[data-testid="stForm"] .stAlert,
    div[data-testid="stForm"] div:has(> [data-testid="stAlert"]),
    .stForm > div:has(> [data-testid="stAlert"]) {
        display: none !important;
    }

    </style>
    """,
    unsafe_allow_html=True)