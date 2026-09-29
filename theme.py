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

    /* =======================================================
       TOP-RIGHT TOOLBAR: Keep ONLY the 3-dot menu (⋮) visible.
       Hide Share, Star (☆), Edit (✏️), GitHub (⊙), and Deploy.
       ======================================================= */

    /* Ensure header bar and toolbar container are visible */
    header[data-testid="stHeader"] {
        background: transparent !important;
        display: block !important;
        visibility: visible !important;
    }

    [data-testid="stToolbar"] {
        display: flex !important;
        visibility: visible !important;
    }

    /* Keep ONLY the 3-dot menu button visible, styled, and clickable */
    #MainMenu,
    [data-testid="stMainMenu"],
    [data-testid="stMainMenu"] button,
    [data-testid="stMainMenuButton"],
    button[aria-label="Main menu"] {
        display: inline-flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
    }

    #MainMenu *,
    [data-testid="stMainMenu"] * {
        visibility: visible !important;
    }

    /* Popover menu items when 3-dot menu is opened */
    [data-baseweb="popover"],
    [data-testid="stMainMenuPopover"],
    [data-testid="stMainMenuList"],
    [data-testid="stMainMenuList"] * {
        visibility: visible !important;
        pointer-events: auto !important;
    }

    /* Hide the Share, Star, Edit, GitHub, and Deploy buttons */
    [data-testid="stToolbarActions"],
    [data-testid="stToolbarActions"] *,
    [data-testid="stDecoration"],
    .stAppDeployButton,
    [data-testid="stAppDeployButton"],
    #GithubIcon,
    [data-testid="GithubIcon"],
    a[href*="github.com"],
    button[title="Share"],
    button[aria-label="Share"],
    button[title="Star"],
    button[aria-label="Star this app"],
    button[aria-label="Star"],
    button[title="Edit this app"],
    button[aria-label="Edit this app"],
    button[title="Edit"],
    button[title="Open GitHub repository"],
    button[aria-label="View source code on GitHub"],
    button[title="Fork this app"],
    div[class*="viewerBadge"],
    div[class*="viewerActions"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
        overflow: hidden !important;
        pointer-events: none !important;
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