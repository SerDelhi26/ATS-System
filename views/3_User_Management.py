import streamlit as st
import pandas as pd
import re
from db import supabase
from datetime import date
from common import (
    show_logout,
    show_job_notifications,
    show_user_profile,
    render_pagination,
    render_paginated_section,
    get_master_lookups,
    clear_data_cache
)
import bcrypt
from theme import apply_theme

@st.cache_data(ttl=10)
def get_all_users():
    return (
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
        .data or []
    )

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
) not in ["Admin", "Developer", "Admin-Lite"]:

    st.error(
        "Access Denied. Admin, Admin-Lite and Developer Only."
    )

    st.stop()

current_user_role = st.session_state.get("user_role", "")
is_developer = current_user_role == "Developer"
is_admin = current_user_role == "Admin"
is_admin_lite = current_user_role == "Admin-Lite"
   
st.set_page_config(
    page_title="ATS System",
    layout="wide"
)

apply_theme()

st.markdown("""
<style>
.block-container {
    max-width: 100%;
}
</style>
""", unsafe_allow_html=True)

if "edit_user_id" not in st.session_state:
    st.session_state.edit_user_id = None

if "reset_user_id" not in st.session_state:
    st.session_state.reset_user_id = None

with st.sidebar:
    show_user_profile()
    show_logout()
    show_job_notifications()
    
st.markdown(
    "# 👥 ATS User Management"
)

if st.session_state.get("reset_user_id"):

    # Security check: Privilege escalation prevention
    target_pwd_user = (
        supabase.table("users")
        .select("role")
        .eq("user_id", st.session_state.reset_user_id)
        .execute()
        .data
    )
    target_pwd_role = target_pwd_user[0].get("role") if target_pwd_user else ""
    if target_pwd_role == "Developer" and not is_developer:
        st.session_state.reset_user_id = None
        st.error("⛔ Unauthorized: Only a Developer can reset passwords for Developer accounts.")
        st.stop()
    if target_pwd_role in ["Admin", "Developer"] and is_admin_lite:
        st.session_state.reset_user_id = None
        st.error("⛔ Unauthorized: Admin-Lite cannot reset passwords for Admin or Developer accounts.")
        st.stop()

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
                st.error("Password cannot be blank.")
            elif len(new_password) < 8 or not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
                st.error("Password must contain at least 8 characters with both letters and numbers.")

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
                get_all_users.clear()
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

        target_user = response.data[0]
        target_role = target_user.get("role")
        if target_role == "Developer" and not is_developer:
            st.session_state.edit_user_id = None
            st.error("⛔ Unauthorized: Only a Developer can modify a Developer account.")
            st.rerun()
        elif target_role in ["Admin", "Developer"] and is_admin_lite:
            st.session_state.edit_user_id = None
            st.error("⛔ Unauthorized: Admin-Lite cannot modify Admin or Developer accounts.")
            st.rerun()
        else:
            editing = True
            user = target_user

# ==============================
# PAGE LAYOUT
# ==============================

left_col, right_col = st.columns([1, 3])

# ==============================
# LEFT PANEL
# ==============================

with left_col:

    if st.session_state.get("user_success_msg"):
        st.success(st.session_state.user_success_msg)
        del st.session_state.user_success_msg

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
            value="",
            type="password",
            help="Leave blank to keep existing password" if editing else "Enter a strong password (min 8 chars, letters and numbers)",
            placeholder="•••••••• (leave blank to keep current password)" if editing else ""
        )

        if is_developer:
            role_options = ["Recruiter", "Admin-Lite", "Admin", "Developer"]
        elif is_admin:
            role_options = ["Recruiter", "Admin-Lite", "Admin"]
        else:
            role_options = ["Recruiter", "Admin-Lite"]

        is_self_edit = editing and user.get("user_id") == st.session_state.get("user_id")

        if editing and user.get("role") in role_options:
            default_role_idx = role_options.index(user["role"])
        else:
            default_role_idx = 0

        role = st.selectbox(
            "Role",
            role_options if not is_self_edit else [user.get("role")],
            index=default_role_idx if not is_self_edit else 0,
            disabled=is_self_edit,
            help="You cannot alter your own administrative role." if is_self_edit else None
        )
        if is_self_edit:
            role = user.get("role")

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

        submit_btn = st.form_submit_button(
            "Update User"
            if editing
            else "Add User",
            use_container_width=True,
            type="primary"
        )

        # ==========================
        # SAVE
        # ==========================

        if submit_btn:

            # 1. Role & Privilege Escalation Checks (Admin-Lite / Admin / Developer)
            if role == "Developer" and not is_developer:
                st.error("⛔ Unauthorized: Only a Developer can assign the Developer role.")
                st.stop()
            if role in ["Admin", "Developer"] and is_admin_lite:
                st.error("⛔ Unauthorized: Admin-Lite cannot assign Admin or Developer roles.")
                st.stop()
            if editing and user.get("user_id") == st.session_state.get("user_id"):
                if role != user.get("role"):
                    st.error("⛔ Unauthorized: You cannot alter your own administrative role.")
                    st.stop()
            if editing and user.get("role") in ["Admin", "Developer"] and is_admin_lite:
                st.error("⛔ Unauthorized: Admin-Lite cannot modify Admin or Developer accounts.")
                st.stop()
            if editing and user.get("role") == "Developer" and not is_developer:
                st.error("⛔ Unauthorized: Only a Developer can modify a Developer account.")
                st.stop()

            email_pattern = (
                r'^[\w\.-]+@[\w\.-]+\.\w+$'
            )

            if not full_name.strip():
                st.error(
                    "Full Name is mandatory."
                )
                st.stop()

            # 2. Password validation (Issue 1: Blank password on edit keeps current password)
            if not editing:
                if not password.strip():
                    st.error("Password is mandatory for new employees.")
                    st.stop()
                elif len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
                    st.error("Password must contain at least 8 characters with both letters and numbers.")
                    st.stop()
            else:
                if password.strip():
                    if len(password.strip()) < 8 or not any(c.isalpha() for c in password.strip()) or not any(c.isdigit() for c in password.strip()):
                        st.error("New password must contain at least 8 characters with both letters and numbers.")
                        st.stop()

            if not re.match(
                email_pattern,
                email
            ):
                st.error(
                    "Please enter a valid email."
                )
                st.stop()

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
                        full_name.strip(),

                    "email":
                        email.strip(),

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

                # Only include password_hash if adding user or providing a new password on edit
                if not editing:
                    data["password_hash"] = bcrypt.hashpw(
                        password.strip().encode(),
                        bcrypt.gensalt()
                    ).decode()
                elif password.strip():
                    data["password_hash"] = bcrypt.hashpw(
                        password.strip().encode(),
                        bcrypt.gensalt()
                    ).decode()

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

                    st.session_state.user_success_msg = "User updated successfully."
                    st.session_state.edit_user_id = None

                else:

                    (
                        supabase
                        .table("users")
                        .insert(data)
                        .execute()
                    )

                    st.session_state.user_success_msg = "User added successfully."

                get_all_users.clear()
                get_master_lookups.clear()
                st.rerun()

            except Exception as e:

                st.error(str(e))
    
    if editing:
        if st.button("❌ Cancel Edit", use_container_width=True):
            st.session_state.edit_user_id = None
            st.rerun()



# ==============================
# RIGHT PANEL
# ==============================

with right_col:
    st.markdown("## 📋 Employee Directory")

    search_text = st.text_input(
        "🔍 Search Employee",
        placeholder="Search by employee name..."
    )

    col1, col2 = st.columns(2)
    with col1:
        role_filter = st.selectbox(
            "Role Filter",
            ["All", "Admin", "Admin-Lite", "Recruiter", "Developer"]
        )
    with col2:
        status_filter = st.selectbox(
            "Status Filter",
            ["All", "Active", "Inactive"]
        )

    try:
        users_data = get_all_users()
        df = pd.DataFrame(users_data)

        if not df.empty:
            if search_text:
                df = df[
                    df["full_name"].str.contains(search_text, case=False, na=False) |
                    df["email"].str.contains(search_text, case=False, na=False)
                ]

            if role_filter != "All":
                df = df[df["role"] == role_filter]

            if status_filter != "All":
                df = df[df["status"] == status_filter]

            def render_user_header():
                header = st.columns([0.5, 2, 3, 1.5, 1.5, 1, 1, 1])
                header[0].markdown("**ID**")
                header[1].markdown("**Name**")
                header[2].markdown("**Email**")
                header[3].markdown("**Role**")
                header[4].markdown("**Status**")
                header[5].markdown("**Edit**")
                header[6].markdown("**Reset**")
                header[7].markdown("**Status**")
                st.divider()

            def render_user_row(row):
                cols = st.columns([0.5, 2, 3, 1.5, 1.5, 1, 1, 1])
                cols[0].write(row["user_id"])
                cols[1].write(row["full_name"])
                cols[2].write(row["email"])
                cols[3].write(row["role"])

                status = row["status"]
                if status == "Active":
                    cols[4].markdown(
                        "<span style='background:#16A34A; color:white; padding:4px 10px; border-radius:10px; font-weight:600;'>Active</span>",
                        unsafe_allow_html=True
                    )
                else:
                    cols[4].markdown(
                        "<span style='background:#DC2626; color:white; padding:4px 10px; border-radius:10px; font-weight:600;'>Inactive</span>",
                        unsafe_allow_html=True
                    )

                is_row_dev = row.get("role") == "Developer"
                is_row_admin = row.get("role") == "Admin"

                if is_developer:
                    can_manage_row = True
                    lock_reason = ""
                elif is_admin:
                    can_manage_row = not is_row_dev
                    lock_reason = "Only a Developer can manage Developer accounts"
                else:  # Admin-Lite
                    can_manage_row = (not is_row_dev) and (not is_row_admin)
                    lock_reason = "Admin-Lite cannot manage Admin or Developer accounts"

                # Edit Button
                if can_manage_row:
                    if cols[5].button("✏️", key=f"edit_{row['user_id']}", help="Edit User"):
                        st.session_state.edit_user_id = row["user_id"]
                        st.rerun(scope="app")
                else:
                    cols[5].markdown(f"<div title='{lock_reason}' style='margin-top:2px; font-size:16px; cursor:help;'>🔒</div>", unsafe_allow_html=True)

                # Reset Password
                if can_manage_row:
                    if cols[6].button("🔑", key=f"reset_{row['user_id']}", help="Reset Password"):
                        st.session_state.reset_user_id = row["user_id"]
                        st.rerun(scope="app")
                else:
                    cols[6].markdown(f"<div title='{lock_reason}' style='margin-top:2px; font-size:16px; cursor:help;'>🔒</div>", unsafe_allow_html=True)

                # Active / Inactive User
                if can_manage_row:
                    if row["status"] == "Active":
                        if cols[7].button("🔒", key=f"deactivate_{row['user_id']}", help="Deactivate User"):
                            (
                                supabase
                                .table("users")
                                .update({
                                    "status": "Inactive",
                                    "relieving_date": str(date.today())
                                })
                                .eq("user_id", row["user_id"])
                                .execute()
                            )
                            st.success(f"{row['full_name']} deactivated successfully.")
                            get_all_users.clear()
                            get_master_lookups.clear()
                            st.rerun(scope="app")
                    else:
                        if cols[7].button("🔓", key=f"activate_{row['user_id']}", help="Activate User"):
                            (
                                supabase
                                .table("users")
                                .update({
                                    "status": "Active",
                                    "relieving_date": None
                                })
                                .eq("user_id", row["user_id"])
                                .execute()
                            )
                            st.success(f"{row['full_name']} activated successfully.")
                            get_all_users.clear()
                            get_master_lookups.clear()
                            st.rerun(scope="app")
                else:
                    cols[7].markdown(f"<div title='{lock_reason}' style='margin-top:2px; font-size:16px; cursor:help;'>🔒</div>", unsafe_allow_html=True)

            render_paginated_section(
                df,
                render_user_row,
                page_size_default=25,
                key_prefix="users",
                render_header_fn=render_user_header,
                empty_message="No employees found."
            )
        else:
            st.info("No employees found.")

    except Exception as e:
        st.error(str(e))