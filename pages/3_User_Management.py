import streamlit as st
import pandas as pd
import re
from db import supabase
from datetime import date
from common import show_logout
import bcrypt
from theme import apply_theme

# ==========================
# LOGIN CHECK
# ==========================

if not st.session_state.get(
    "logged_in",
    False
):

    st.switch_page("Home.py")

    st.stop()

# ==========================
# ADMIN SECURITY
# ==========================

if st.session_state.get(
    "user_role"
) != "Admin":

    st.error(
        "Access Denied. Admin Only."
    )

    st.stop()
   
st.set_page_config(
    page_title="ATS System",
    layout="wide"
)

apply_theme()

if "edit_user_id" not in st.session_state:
    st.session_state.edit_user_id = None

if "reset_user_id" not in st.session_state:
    st.session_state.reset_user_id = None

with st.sidebar:

    show_logout()

st.markdown(
    "# 👥 ATS User Management"
)

if st.session_state.get("reset_user_id"):

    with st.expander(
        "Reset Password",
        expanded=True
    ):

        new_password = st.text_input(
            "New Password",
            type="password"
        )

        confirm_password = st.text_input(
            "Confirm Password",
            type="password"
        )

        col1, col2 = st.columns(2)

        if col1.button(
            "Save Password"
        ):

            if new_password != confirm_password:

                st.error(
                    "Passwords do not match."
                )

            elif not new_password.strip():

                st.error(
                    "Password cannot be blank."
                )

            else:

                import bcrypt

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
                    .update({
                        "password_hash":
                        hashed_password
                    })
                    .eq(
                        "user_id",
                        st.session_state.reset_user_id
                    )
                    .execute()
                )

                st.success(
                    "Password reset successfully."
                )

                st.session_state.reset_user_id = None

                st.rerun()

        if col2.button(
            "Cancel"
        ):

            st.session_state.reset_user_id = None

            st.rerun()

# ==============================
# SESSION VARIABLES
# ==============================

editing = False
user = None

if st.session_state.edit_user_id:

    response = (
        supabase.table("users")
        .select("*")
        .eq(
            "user_id",
            st.session_state.edit_user_id
        )
        .execute()
    )

    if response.data:

        editing = True
        user = response.data[0]

# ==============================
# PAGE LAYOUT
# ==============================

left_col, right_col = st.columns([1, 3])

st.markdown("""
<div style="
background:white;
padding:15px;
border-radius:12px;
box-shadow:0px 2px 8px rgba(0,0,0,0.08);
">
""",
unsafe_allow_html=True)

# ==============================
# LEFT PANEL
# ==============================

with left_col:

    st.subheader(
        "Edit Employee"
        if editing
        else "Add Employee"
    )

    with st.form(
        "employee_form",
        clear_on_submit=not editing
    ):

        full_name = st.text_input(
            "Full Name",
            value=user["full_name"] if editing else ""
        )

        email = st.text_input(
            "Email",
            value=user["email"] if editing else ""
        )

        password = st.text_input(
            "Password",
            value=(
                user.get("password_hash", "")
                if editing
                else ""
            ),
            type="password"
        )

        role = st.selectbox(
            "Role",
            ["Recruiter", "Admin"],
            index=(
                0
                if not editing
                else (
                    0
                    if user["role"] == "Recruiter"
                    else 1
                )
            )
        )

        joining_date = st.date_input(
            "Joining Date",
            value=(
                pd.to_datetime(
                    user["joining_date"]
                ).date()
                if editing and user["joining_date"]
                else date.today()
            )
        )

        qualification = st.text_input(
            "Qualification",
            value=(
                user.get(
                    "qualification",
                    ""
                )
                if editing
                else ""
            )
        )

        experience_years = st.selectbox(
            "Experience Years",
            list(range(0, 21)),
            index=(
                user.get(
                    "experience_years",
                    0
                )
                if editing
                else 0
            )
        )

        experience_months = st.selectbox(
            "Experience Months",
            list(range(0, 12)),
            index=(
                user.get(
                    "experience_months",
                    0
                )
                if editing
                else 0
            )
        )

        status = st.selectbox(
            "Status",
            ["Active", "Inactive"],
            index=(
                0
                if not editing
                else (
                    0
                    if user["status"] == "Active"
                    else 1
                )
            )
        )

        relieving_date = None

        if status == "Inactive":

            relieving_date = st.date_input(
                "Relieving Date",
                value=date.today()
            )

        col1, col2 = st.columns(2)

        submit_btn = col1.form_submit_button(
            "Update User"
            if editing
            else "Add User"
        )

        cancel_btn = False

        if editing:

            cancel_btn = col2.form_submit_button(
                "Cancel Edit"
            )

        # ==========================
        # CANCEL EDIT
        # ==========================

        if cancel_btn:

            st.session_state.edit_user_id = None
            st.rerun()

        # ==========================
        # SAVE
        # ==========================

        if submit_btn:

            email_pattern = (
                r'^[\w\.-]+@[\w\.-]+\.\w+$'
            )

            if not full_name.strip():

                st.error(
                    "Full Name is mandatory."
                )
            elif not password.strip():
                st.error(
                    "Password is mandatory."
                )

            elif not re.match(
                email_pattern,
                email
            ):

                st.error(
                    "Please enter a valid email."
                )

            else:

                duplicate_user = (
                    supabase
                    .table("users")
                    .select(
                        "user_id"
                    )
                    .eq(
                        "email",
                        email.strip()
                    )
                    .execute()
                )

                if editing:

                    duplicate_user.data = [

                        row

                        for row in duplicate_user.data

                        if row["user_id"]
                        != user["user_id"]

                    ]

                if duplicate_user.data:

                    st.error(
                        "User already exists with this Email."
                    )

                    st.stop()

                try:

                    data = {

                        "full_name":
                            full_name,

                        "email":
                            email,
                        
                        "password_hash":
                            bcrypt.hashpw(
                                password.encode(),
                                bcrypt.gensalt()
                            ).decode(),

                        "role":
                            role,

                        "joining_date":
                            str(joining_date),

                        "qualification":
                            qualification,

                        "experience_years":
                            experience_years,

                        "experience_months":
                            experience_months,

                        "status":
                            status,

                        "relieving_date":
                            (
                                str(relieving_date)
                                if status == "Inactive"
                                else None
                            )
                    }

                    if editing:

                        (
                            supabase
                            .table("users")
                            .update(data)
                            .eq(
                                "user_id",
                                user["user_id"]
                            )
                            .execute()
                        )

                        st.success(
                            "User updated successfully."
                        )

                        st.session_state.edit_user_id = None

                    else:

                        (
                            supabase
                            .table("users")
                            .insert(data)
                            .execute()
                        )

                        st.success(
                            "User added successfully."
                        )

                    st.rerun()

                except Exception as e:

                    st.error(str(e))

st.markdown(
    "</div>",
    unsafe_allow_html=True
)

# ==============================
# RIGHT PANEL
# ==============================

with right_col:

    st.markdown(
        "## 📋 Employee Directory"
    )

    search_text = st.text_input(
        "🔍 Search Employee",
        placeholder="Search by employee name..."
    )

    col1, col2 = st.columns(2)

    with col1:

        role_filter = st.selectbox(
            "Role Filter",
            ["All",
             "Admin",
             "Recruiter"]
        )

    with col2:

        status_filter = st.selectbox(
            "Status Filter",
            ["All",
             "Active",
             "Inactive"]
        )

    try:

        result = (
            supabase
            .table("users")
            .select(
                """
                user_id,
                full_name,
                email,
                role,
                status
                """
            )
            .order("user_id")
            .execute()
        )

        df = pd.DataFrame(result.data)

        if not df.empty:

            if search_text:

                df = df[
                    df["full_name"]
                    .str.contains(
                        search_text,
                        case=False,
                        na=False
                    )
                ]

            if role_filter != "All":

                df = df[
                    df["role"]
                    == role_filter
                ]

            if status_filter != "All":

                df = df[
                    df["status"]
                    == status_filter
                ]

            header = st.columns(
                [0.5,2,3,1.5,1.5,1,1,1]
            )

            header[0].markdown("**ID**")
            header[1].markdown("**Name**")
            header[2].markdown("**Email**")
            header[3].markdown("**Role**")
            header[4].markdown("**Status**")
            header[5].markdown("**Edit**")
            header[6].markdown("**Reset**")
            header[7].markdown("**Status**")

            st.divider()

            for _, row in df.iterrows():

                cols = st.columns(
                    [0.5,2,3,1.5,1.5,1,1,1]
                )

                cols[0].write(
                    row["user_id"]
                )

                cols[1].write(
                    row["full_name"]
                )

                cols[2].write(
                    row["email"]
                )

                cols[3].write(
                    row["role"]
                )

                status = row["status"]

                if status == "Active":

                    cols[4].markdown(
                        """
                        <span style="
                        background:#16A34A;
                        color:white;
                        padding:4px 10px;
                        border-radius:10px;
                        ">
                        Active
                        </span>
                        """,
                        unsafe_allow_html=True
                    )

                else:

                    cols[4].markdown(
                        """
                        <span style="
                        background:#DC2626;
                        color:white;
                        padding:4px 10px;
                        border-radius:10px;
                        ">
                        Inactive
                        </span>
                        """,
                        unsafe_allow_html=True
                    )


                # Edit Button
                if cols[5].button(
                    "✏️",
                    key=f"edit_{row['user_id']}"
                ):
                    st.session_state.edit_user_id = row["user_id"]

                    st.rerun()
                # Reset Password
                if cols[6].button(
                    "🔑",
                    key=f"reset_{row['user_id']}"
                ):
                    st.session_state.reset_user_id = (
                        row["user_id"]
                    )
                    st.rerun()

                # Active User
                if row["status"] == "Active":

                    if cols[7].button(
                        "🔒",
                        key=f"deactivate_{row['user_id']}"
                    ):

                        (
                            supabase
                            .table("users")
                            .update({
                                "status": "Inactive",
                                "relieving_date": str(date.today())
                            })
                            .eq(
                                "user_id",
                                row["user_id"]
                            )
                            .execute()
                        )

                        st.success(
                            f"{row['full_name']} deactivated successfully."
                        )

                        st.rerun()

                # Inactive User
                else:

                    if cols[7].button(
                        "🔓",
                        key=f"activate_{row['user_id']}"
                    ):

                        (
                            supabase
                            .table("users")
                            .update({
                                "status": "Active",
                                "relieving_date": None
                            })
                            .eq(
                                "user_id",
                                row["user_id"]
                            )
                            .execute()
                        )

                        st.success(
                            f"{row['full_name']} activated successfully."
                        )

                        st.rerun()

        else:

            st.info(
                "No employees found."
            )

    except Exception as e:

        st.error(str(e))