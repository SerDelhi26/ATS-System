import streamlit as st
import pandas as pd
from db import supabase
from datetime import datetime
from common import show_logout
from theme import apply_theme


# ==========================
# LOGIN CHECK
# ==========================

if not st.session_state.get("logged_in", False):
    st.switch_page("Home.py")
    st.stop()


# ==========================
# ROLE CHECK
# ==========================

if str(
    st.session_state.get(
        "user_role",
        ""
    )
).lower() != "admin":

    st.error(
        "You are not authorized to access this page."
    )

    st.stop()


st.set_page_config(
    page_title="Job Management",
    layout="wide"
)

apply_theme()

with st.sidebar:

    show_logout()

st.markdown(
    "# 💼 ATS Job Management"
)


if "success_message" not in st.session_state:
    st.session_state.success_message = None

if "edit_job_id" not in st.session_state:
    st.session_state.edit_job_id = None

if "job_document_url" not in st.session_state:

    st.session_state.job_document_url = None

if st.session_state.get("success_message"):

    st.success(
        st.session_state.get("success_message")
    )

    st.session_state.success_message = None

# ==========================
# FUNCTIONS
# ==========================
@st.cache_data(ttl=3600)
def get_job_titles():
    return supabase.table(
        "job_title_master"
    ).select("*").execute().data

@st.cache_data(ttl=3600)
def get_companies():
    return supabase.table(
        "company_master"
    ).select("*").execute().data

@st.cache_data(ttl=3600)
def get_categories():
    return supabase.table(
        "category_master"
    ).select("*").execute().data


def get_sub_categories(category_id):
    return (
        supabase
        .table("sub_category_master")
        .select("*")
        .eq("category_id", category_id)
        .execute()
        .data
    )

@st.cache_data(ttl=300)
def get_recruiters():
    return (
        supabase
        .table("users")
        .select("*")
        .eq("role", "Recruiter")
        .eq("status", "Active")
        .execute()
        .data
    )

def get_document_url(file_path):

    try:

        response = (
            supabase.storage
            .from_("job_documents")
            .create_signed_url(
                file_path,
                3600
            )
        )

        return response["signedURL"]

    except:

        return None

def upload_job_document(
    uploaded_file,
    file_name
):

    try:

        file_bytes = uploaded_file.getvalue()

        supabase.storage \
            .from_("job_documents") \
            .upload(
                file_name,
                file_bytes
            )

        return file_name

    except Exception as e:

        st.error(
            f"Upload Error: {str(e)}"
        )

        return None


def get_job_by_id(job_id):

    result = (
        supabase
        .table("job_management")
        .select("*")
        .eq("job_id", job_id)
        .single()
        .execute()
    )

    return result.data

# ==========================
# LAYOUT
# ==========================

left_col, right_col = st.columns([1, 3])

# ==========================
# LEFT PANEL
# ==========================
with left_col:

    editing_job = None
    job_defaults = {}

    if st.session_state.edit_job_id:

        editing_job = get_job_by_id(
            st.session_state.edit_job_id
        )

        if editing_job:

            job_defaults = editing_job

    st.subheader(
        "Edit Job"
        if editing_job
        else "Create Job"
    )

    # -----------------------------
    # Recruiter Assignment
    # -----------------------------

    recruiters = get_recruiters()

    assigned_recruiters = []

    if editing_job:

        assignments = (
            supabase
            .table("job_assignment")
            .select("*")
            .eq(
                "job_id",
                editing_job["job_id"]
            )
            .execute()
        )

        assigned_user_ids = [
            item["user_id"]
            for item in assignments.data
        ]

        assigned_recruiters = [
            r["full_name"]
            for r in recruiters
            if r["user_id"] in assigned_user_ids
        ]


    recruiter_names = [
        r["full_name"]
        for r in recruiters
    ]

    selected_recruiters = st.multiselect(
        "Assign Recruiters",
        recruiter_names,
        default=assigned_recruiters
        if editing_job
        else [],
        key=f"selected_recruiters_{editing_job['job_id']}"
        if editing_job
        else "selected_recruiters_new"
    )

    # -----------------------------
    # Job Title
    # -----------------------------

    job_titles = get_job_titles()

    job_title_names = [
        "-- Select Job Title --"
    ] + [
        item["job_title_name"]
        for item in job_titles
    ]

    if editing_job:

        default_job_title = next(
            (
                item["job_title_name"]
                for item in job_titles
                if item["job_title_id"]
                == editing_job["job_title_id"]
            ),
            job_title_names[0]
        )

    selected_job_title = st.selectbox(
        "Job Title",
        job_title_names,
        index=0 if not editing_job
        else job_title_names.index(default_job_title),
        key=f"job_title_{editing_job['job_id']}"
        if editing_job
        else "job_title_new"
    )

    if st.checkbox("Add New Job Title"):

        new_job_title = st.text_input(
            "New Job Title"
        )

        if st.button("Save Job Title"):

            existing = (
                supabase
                .table("job_title_master")
                .select("*")
                .ilike(
                    "job_title_name",
                    new_job_title
                )
                .execute()
            )

            if existing.data:

                st.warning(
                    "Job Title already exists."
                )

            else:

                (
                    supabase
                    .table("job_title_master")
                    .insert({
                        "job_title_name":
                        new_job_title
                    })
                    .execute()
                )
                
                # Performance Fix 1: Specific cache clear to ensure new items show immediately
                get_job_titles.clear()

                st.success(
                    "Job Title created."
                )

                st.rerun()

    # -----------------------------
    # Company
    # -----------------------------

    companies = get_companies()

    company_names = [
        "-- Select Company --"
    ] + [
        item["company_name"]
        for item in companies
    ]

    if editing_job:

        default_company = next(
            (
                item["company_name"]
                for item in companies
                if item["company_id"]
                == editing_job["company_id"]
            ),
            company_names[0]
        )

    selected_company = st.selectbox(
        "Company",
        company_names,
        index=company_names.index(default_company)
        if editing_job
        else 0,
        key=f"company_{editing_job['job_id']}"
        if editing_job
        else "company_new"
    )

    if st.checkbox("Add New Company"):

        new_company = st.text_input(
            "New Company"
        )

        if st.button("Save Company"):

            existing = (
                supabase
                .table("company_master")
                .select("*")
                .ilike(
                    "company_name",
                    new_company
                )
                .execute()
            )

            if existing.data:

                st.warning(
                    "Company already exists."
                )

            else:

                (
                    supabase
                    .table("company_master")
                    .insert({
                        "company_name":
                        new_company
                    })
                    .execute()
                )
                
                # Performance Fix 1: Specific cache clear to ensure new items show immediately
                get_companies.clear()

                st.success(
                    "Company created."
                )

                st.rerun()

    # -----------------------------
    # Category
    # -----------------------------

    categories = get_categories()

    category_names = [
        "-- Select Category --"
    ] + [
        item["category_name"]
        for item in categories
    ]

    if editing_job:

        default_category = next(
            (
                item["category_name"]
                for item in categories
                if item["category_id"]
                == editing_job["category_id"]
            ),
            category_names[0]
        )

    selected_category_name = st.selectbox(
        "Category",
        category_names,
        index=category_names.index(default_category)
        if editing_job
        else 0,
        key=f"category_{editing_job['job_id']}"
        if editing_job
        else "category_new"
    )

    if st.checkbox("Add New Category"):

        new_category = st.text_input(
            "New Category"
        )

        if st.button("Save Category"):

            existing = (
                supabase
                .table("category_master")
                .select("*")
                .ilike(
                    "category_name",
                    new_category
                )
                .execute()
            )

            if existing.data:

                st.warning(
                    "Category already exists."
                )

            else:

                (
                    supabase
                    .table("category_master")
                    .insert({
                        "category_name":
                        new_category
                    })
                    .execute()
                )
                
                # Performance Fix 1: Specific cache clear to ensure new items show immediately
                get_categories.clear()

                st.success(
                    "Category created."
                )

                st.rerun()

    category_record = next(
        (
            c
            for c in categories
            if c["category_name"]
            == selected_category_name
        ),
        None
    )

    # -----------------------------
    # Sub Category
    # -----------------------------

    sub_categories = []

    if category_record:

        sub_categories = get_sub_categories(
            category_record["category_id"]
        )

    sub_category_names = [
        "-- Select Sub Category --"
    ] + [
        item["sub_category_name"]
        for item in sub_categories
    ]

    if editing_job:

        default_sub_category = next(
            (
                item["sub_category_name"]
                for item in sub_categories
                if item["sub_category_id"]
                == editing_job["sub_category_id"]
            ),
            sub_category_names[0]
            if sub_category_names
            else ""
        )

    selected_sub_category = st.selectbox(
        "Sub Category",
        sub_category_names,
        index=sub_category_names.index(default_sub_category)
        if editing_job and default_sub_category in sub_category_names
        else 0,
        key=f"sub_category_{editing_job['job_id']}"
        if editing_job
        else "sub_category_new"
    )

    if st.checkbox("Add New Sub Category"):

        new_sub_category = st.text_input(
            "New Sub Category"
        )

        if st.button("Save Sub Category"):

            (
                supabase
                .table("sub_category_master")
                .insert({
                    "category_id":
                    category_record["category_id"],
                    "sub_category_name":
                    new_sub_category
                })
                .execute()
            )

            st.success(
                "Sub Category created."
            )

            st.rerun()

    location = st.text_input(
        "Location",
        value=job_defaults.get(
            "location",
            ""
        ),
        placeholder="-- Enter Location --",
        key=f"location_{editing_job['job_id']}"
        if editing_job
        else "location_new"
    )

    st.markdown(
        "### 🎓 Experience"
    )

    min_year = st.selectbox(
        "Minimum Year",
        list(range(41)),
        index=job_defaults.get(
            "experience_min_year",
            0
        ),
        key=f"min_year_{editing_job['job_id']}"
        if editing_job
        else "min_year_new"
    )

    min_month = st.selectbox(
        "Minimum Month",
        list(range(12)),
        index=job_defaults.get(
            "experience_min_month",
            0
        ),
        key=f"min_month_{editing_job['job_id']}"
        if editing_job
        else "min_month_new"
    )

    max_year = st.selectbox(
        "Maximum Year",
        list(range(41)),
        index=job_defaults.get(
            "experience_max_year",
            0
        ),
        key=f"max_year_{editing_job['job_id']}"
        if editing_job
        else "max_year_new"
    )

    max_month = st.selectbox(
        "Maximum Month",
        list(range(12)),
        index=job_defaults.get(
            "experience_max_month",
            0
        ),
        key=f"max_month_{editing_job['job_id']}"
        if editing_job
        else "max_month_new"
    )

    job_type_options = [
        "-- Select Job Type --",
        "Permanent",
        "Contract",
        "C2H",
        "Internship"
    ]

    job_type = st.selectbox(
        "Job Type",
        job_type_options,
        index=(
            job_type_options.index(
                job_defaults.get(
                    "job_type",
                    "Permanent"
                )
            )
            if editing_job
            else 0
        ),
        key=f"job_type_{editing_job['job_id']}"
        if editing_job
        else "job_type_new"
    )

    openings = st.number_input(
        "Openings",
        min_value=1,
        value=job_defaults.get(
            "openings",
            1
        ),
        key=f"openings_{editing_job['job_id']}"
        if editing_job
        else "openings_new"
    )

    # -----------------------------
    # Compensation
    # -----------------------------

    st.markdown(
        "### 💰 Compensation"
    )

    pay_min = st.number_input(
        "Pay Min",
        min_value=0.0,
        value=float(
            job_defaults.get(
                "pay_min",
                0
            )
        ),
        key=f"pay_min_{editing_job['job_id']}"
        if editing_job
        else "pay_min_new"
    )

    pay_max = st.number_input(
        "Pay Max",
        min_value=0.0,
        value=float(
            job_defaults.get(
                "pay_max",
                0
            )
        ),
        key=f"pay_max_{editing_job['job_id']}"
        if editing_job
        else "pay_max_new"
    )

    currency_options = [
        "-- Select Currency --",
        "INR",
        "USD",
        "EUR"
    ]

    currency = st.selectbox(
        "Currency",
        currency_options,
        index=(
            currency_options.index(
                job_defaults.get(
                    "currency",
                    "INR"
                )
            )
            if editing_job
            else 0
        ),
        key=f"currency_{editing_job['job_id']}"
        if editing_job
        else "currency_new"
    )

    pay_unit_options = [
        "-- Select Pay Unit --",
        "Per Annum",
        "Per Month",
        "Per Day",
        "Per Hour"
    ]

    pay_unit = st.selectbox(
        "Pay Unit",
        pay_unit_options,
        index=(
            pay_unit_options.index(
                job_defaults.get(
                    "pay_unit",
                    "Per Annum"
                )
            )
            if editing_job
            else 0
        ),
        key=f"pay_unit_{editing_job['job_id']}"
        if editing_job
        else "pay_unit_new"
    )

    # -----------------------------
    # Skills & JD
    # -----------------------------

    st.markdown(
        "### 📝 Job Details"
    )

    skills_required = st.text_area(
        "Skills Required",
        value=job_defaults.get(
            "skills_required",
            ""
        ),
        height=120,
        key=f"skills_required_{editing_job['job_id']}"
        if editing_job
        else "skills_required_new"
    )

    job_description = st.text_area(
        "Job Description",
        value=job_defaults.get(
            "job_description",
            ""
        ),
        height=250,
        key=f"job_description_{editing_job['job_id']}"
        if editing_job
        else "job_description_new"
    )

    job_document = st.file_uploader(
        "Upload Job Document",
        type=[
            "pdf",
            "doc",
            "docx",
            "xlsx",
            "xls"
        ],
        key="job_document"
    )

    # -----------------------------
    # Invoice Information
    # -----------------------------

    st.markdown(
        "### 🧾 Invoice Information"
    )

    performa_invoice_no = st.text_input(
        "Performa Invoice No",
        value=job_defaults.get(
            "performa_invoice_no",
            ""
        ),
        key=f"performa_invoice_no_{editing_job['job_id']}"
        if editing_job
        else "performa_invoice_no_new"
    )

    performa_status_options = [
        "-- Select Performa Invoice Status --",
        "Pending",
        "In Progress",
        "Completed"
    ]

    performa_invoice_status = st.selectbox(
        "Performa Invoice Status",
        performa_status_options,
        index=(
            performa_status_options.index(
                job_defaults.get(
                    "performa_invoice_status",
                    "Pending"
                )
            )
            if editing_job
            else 0
        ),
        key=f"performa_invoice_status_{editing_job['job_id']}"
        if editing_job
        else "performa_invoice_status_new"
    )

    invoice_no = st.text_input(
        "Invoice No",
        value=job_defaults.get(
            "invoice_no",
            ""
        ),
        key=f"invoice_no_{editing_job['job_id']}"
        if editing_job
        else "invoice_no_new"
    )

    invoice_status_options = [
        "-- Select Invoice Status --",
        "Pending",
        "In Progress",
        "Completed"
    ]

    invoice_status = st.selectbox(
        "Invoice Status",
        invoice_status_options,
        index=(
            invoice_status_options.index(
                job_defaults.get(
                    "invoice_status",
                    "Pending"
                )
            )
            if editing_job
            else 0
        ),
        key=f"invoice_status_{editing_job['job_id']}"
        if editing_job
        else "invoice_status_new"
    )

    remark = st.text_area(
        "Remarks",
        value=job_defaults.get(
            "remark",
            ""
        ),
        height=100,
        key=f"remark_{editing_job['job_id']}"
        if editing_job
        else "remark_new"
    )

    job_status_options = [
        "-- Select Job Status --",
        "Open",
        "On Hold",
        "Closed",
        "Cancelled"
    ]

    job_status = st.selectbox(
        "Job Status",
        job_status_options,
        index=(
            job_status_options.index(
                job_defaults.get(
                    "job_status",
                    "Open"
                )
            )
            if editing_job
            else 0
        ),
        key=f"job_status_{editing_job['job_id']}"
        if editing_job
        else "job_status_new"
    )

    if editing_job:

        btn1, btn2 = st.columns(2)

        update_clicked = btn1.button(
            "Update Job",
            use_container_width=True
        )

        if btn2.button(
            "❌ Cancel Edit",
            use_container_width=True
        ):

            st.session_state.edit_job_id = None

            st.rerun()

    else:

        update_clicked = st.button(
            "Save Job",
            use_container_width=True
        )

    if update_clicked:

        try:
            # -----------------------------
            # Validation
            # -----------------------------

            validation_errors = []

            if not selected_recruiters:
                validation_errors.append(
                    "Please assign at least one recruiter."
                )

            if selected_job_title == "-- Select Job Title --":
                validation_errors.append(
                    "Please select Job Title."
                )

            if selected_company == "-- Select Company --":
                validation_errors.append(
                    "Please select Company."
                )

            if selected_category_name == "-- Select Category --":
                validation_errors.append(
                    "Please select Category."
                )

            if selected_sub_category == "-- Select Sub Category --":
                validation_errors.append(
                    "Please select Sub Category."
                )

            if not location.strip():
                validation_errors.append(
                    "Please enter Location."
                )

            if min_year == 0 and min_month == 0:
                validation_errors.append(
                    "Please select Minimum Experience."
                )

            if max_year == 0 and max_month == 0:
                validation_errors.append(
                    "Please select Maximum Experience."
                )

            min_exp = (min_year * 12) + min_month
            max_exp = (max_year * 12) + max_month

            if max_exp < min_exp:

                validation_errors.append(
                    "Maximum Experience cannot be less than Minimum Experience."
                )

            if job_type == "-- Select Job Type --":
                validation_errors.append(
                    "Please select Job Type."
                )

            if openings <= 0:
                validation_errors.append(
                    "Openings must be greater than 0."
                )

            if pay_min <= 0:
                validation_errors.append(
                    "Pay Min must be greater than 0."
                )

            if pay_max <= 0:
                validation_errors.append(
                    "Pay Max must be greater than 0."
                )

            if float(pay_max) < float(pay_min):
                validation_errors.append(
                    "Pay Max cannot be less than Pay Min."
                )

            if currency == "-- Select Currency --":
                validation_errors.append(
                    "Please select Currency."
                )

            if pay_unit == "-- Select Pay Unit --":
                validation_errors.append(
                    "Please select Pay Unit."
                )

            if not skills_required.strip():
                validation_errors.append(
                    "Please enter Skills Required."
                )

            if job_status == "-- Select Job Status --":
                validation_errors.append(
                    "Please select Job Status."
                )

            if validation_errors:

                for error in validation_errors:

                    st.error(error)

                st.stop()

            selected_job_title_record = next(
                item
                for item in job_titles
                if item["job_title_name"]
                == selected_job_title
            )

            selected_company_record = next(
                item
                for item in companies
                if item["company_name"]
                == selected_company
            )

            job_data = {

                "job_title_id":
                selected_job_title_record["job_title_id"],

                "company_id":
                selected_company_record["company_id"],

                "category_id":
                category_record["category_id"],

                "sub_category_id":
                next(
                    item["sub_category_id"]
                    for item in sub_categories
                    if item["sub_category_name"]
                    == selected_sub_category
                ),

                "location": location,

                "experience_min_year": min_year,

                "experience_min_month": min_month,

                "experience_max_year": max_year,

                "experience_max_month": max_month,

                "job_type": job_type,

                "openings": openings,

                "job_status": job_status,

                "pay_min": pay_min,

                "pay_max": pay_max,

                "currency": currency,

                "pay_unit": pay_unit,

                "skills_required": skills_required,

                "job_description": job_description,

                "performa_invoice_no":
                performa_invoice_no,

                "performa_invoice_status":
                performa_invoice_status,

                "invoice_no": invoice_no,

                "invoice_status":
                invoice_status,

                "remark": remark
            }

            if editing_job:

                (
                    supabase
                    .table("job_management")
                    .update(job_data)
                    .eq(
                        "job_id",
                        editing_job["job_id"]
                    )
                    .execute()
                )

                (
                    supabase
                    .table("job_assignment")
                    .delete()
                    .eq(
                        "job_id",
                        editing_job["job_id"]
                    )
                    .execute()
                )

                for recruiter_name in selected_recruiters:

                    recruiter = next(
                        r
                        for r in recruiters
                        if r["full_name"]
                        == recruiter_name
                    )

                    (
                        supabase
                        .table("job_assignment")
                        .insert({
                            "job_id":
                            editing_job["job_id"],

                            "user_id":
                            recruiter["user_id"]
                        })
                        .execute()
                    )

                st.session_state.success_message = (
                    "Job Updated Successfully"
                )

                st.session_state.edit_job_id = None

                st.rerun()

            else:

                insert_result = (
                    supabase
                    .table("job_management")
                    .insert(job_data)
                    .execute()
                )

                job = insert_result.data[0]


            current_year = datetime.now().year

            job_ref = (
                f"JR-{current_year}-{job['job_id']:06d}"
            )

            job_document_path = None

            if job_document:

                unique_file_name = (
                    f"{job_ref}_{job_document.name}"
                )

                job_document_path = upload_job_document(
                    job_document,
                    unique_file_name
                )

            (
                supabase
                .table("job_management")
                .update({

                    "job_reference_no":
                    job_ref,

                    "job_document_name":
                    job_document.name
                    if job_document
                    else None,

                    "job_document_path":
                    job_document_path

                })
                .eq(
                    "job_id",
                    job["job_id"]
                )
                .execute()
            )

            for recruiter_name in selected_recruiters:

                recruiter = next(
                    r
                    for r in recruiters
                    if r["full_name"]
                    == recruiter_name
                )

                (
                    supabase
                    .table("job_assignment")
                    .insert({
                        "job_id":
                        job["job_id"],

                        "user_id":
                        recruiter["user_id"]
                    })
                    .execute()
                )

            st.session_state.success_message = (
                f"Job Created : {job_ref}"
            )

            for key in [
                #"selected_recruiters",
                "location",
                "job_title",
                "company",
                "category",
                "sub_category",
                "min_year",
                "min_month",
                "max_year",
                "max_month",
                "job_type",
                "openings",
                "pay_min",
                "pay_max",
                "currency",
                "pay_unit",
                "skills_required",
                "job_description",
                "performa_invoice_no",
                "performa_invoice_status",
                "invoice_no",
                "invoice_status",
                "job_status",
                "remark",
                "job_document"
            ]:

                if key in st.session_state:
                    del st.session_state[key]

            st.rerun()

        except Exception as e:

            st.error(str(e))

# ==========================
# RIGHT PANEL
# ==========================

with right_col:

    st.markdown(
        "## 📋 Job Directory"
    )

    if st.session_state.job_document_url:

        st.link_button(
            "📄 Open Selected Job Document",
            st.session_state.job_document_url,
            use_container_width=True
        )

    job_titles_lookup = {
        item["job_title_id"]: item["job_title_name"]
        for item in job_titles
    }

    companies_lookup = {
        item["company_id"]: item["company_name"]
        for item in companies
    }

    categories_lookup = {
        item["category_id"]: item["category_name"]
        for item in categories
    }

    recruiter_lookup = {
        user["user_id"]: user["full_name"]
        for user in recruiters
    }

    search_text = st.text_input(
        "🔍 Search Job",
        placeholder=
        "JR Number, Job Title, Company or Location"
    )

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

    with filter_col1:

        company_filter = st.selectbox(
            "Company Filter",
            ["All"] + sorted(
                list(companies_lookup.values())
            )
        )

    with filter_col2:

        status_filter = st.selectbox(
            "Status Filter",
            [
                "All",
                "Open",
                "Closed",
                "On Hold",
                "Cancelled"
            ]
        )

    with filter_col3:

        category_filter = st.selectbox(
            "Category Filter",
            ["All"] + sorted(
                [c["category_name"] for c in categories]
            )
        )

    with filter_col4:

        recruiter_filter = st.selectbox(
            "Recruiter Filter",
            ["All"] + sorted(
                recruiter_names
            )
        )


    assignments = (
        supabase
        .table("job_assignment")
        .select("*")
        .execute()
    )

    assignments_data = assignments.data

    # Performance Fix 2: Added .limit(500) and order desc to prevent DB query overload
    jobs = (
        supabase
        .table("job_management")
        .select(
            """
            job_id,
            job_reference_no,
            job_title_id,
            company_id,
            category_id,
            location,
            openings,
            job_status,
            job_document_path
            """
        )
        .order("job_id", desc=True)
        .limit(500) 
        .execute()
    )

    jobs_df = pd.DataFrame(
        jobs.data
    )

    # -------------------------
    # SEARCH
    # -------------------------

    if not jobs_df.empty and search_text:

        matching_job_titles = []

        for job_id, title in job_titles_lookup.items():

            if search_text.lower() in title.lower():

                matching_job_titles.append(job_id)

        matching_companies = []

        for company_id, company in companies_lookup.items():

            if search_text.lower() in company.lower():

                matching_companies.append(company_id)

        jobs_df = jobs_df[

            jobs_df["job_reference_no"]
            .fillna("")
            .str.contains(
                search_text,
                case=False,
                na=False
            )

            |

            jobs_df["location"]
            .fillna("")
            .str.contains(
                search_text,
                case=False,
                na=False
            )

            |

            jobs_df["job_title_id"]
            .isin(matching_job_titles)

            |

            jobs_df["company_id"]
            .isin(matching_companies)

        ]

    # -------------------------
    # COMPANY FILTER
    # -------------------------

    if company_filter != "All":

        company_ids = [
            cid
            for cid, cname
            in companies_lookup.items()
            if cname == company_filter
        ]

        jobs_df = jobs_df[
            jobs_df["company_id"]
            .isin(company_ids)
        ]

    # -------------------------
    # STATUS FILTER
    # -------------------------

    if status_filter != "All":

        jobs_df = jobs_df[
            jobs_df["job_status"]
            == status_filter
        ]

    # -------------------------
    # CATEGORY FILTER
    # -------------------------

    if category_filter != "All":

        category_ids = [
            cid
            for cid, cname
            in categories_lookup.items()
            if cname == category_filter
        ]

        jobs_df = jobs_df[
            jobs_df["category_id"]
            .isin(category_ids)
        ]

    if recruiter_filter != "All":

        recruiter_ids = [
            uid
            for uid, name
            in recruiter_lookup.items()
            if name == recruiter_filter
        ]

        assigned_job_ids = [
            item["job_id"]
            for item in assignments_data
            if item["user_id"]
            in recruiter_ids
        ]

        jobs_df = jobs_df[
            jobs_df["job_id"]
            .isin(assigned_job_ids)
        ]

    if not jobs_df.empty:

        # Performance Fix 3: Slicing DataFrame to limit UI rendering to 25 rows max
        total_jobs = len(jobs_df)
        display_jobs_df = jobs_df.head(25)
        
        if total_jobs > 25:
            st.caption(f"⚠️ Showing top 25 of {total_jobs} results to maintain performance. Use the search bar to find specific records.")

        header = st.columns(
            [2, 3, 3, 3, 2, 2, 2, 2.5, 1.5, 1.5]
        )

        header[0].markdown("**JR Number**")
        header[1].markdown("**Job Title**")
        header[2].markdown("**Company**")
        header[3].markdown("**Recruiters**")
        header[4].markdown("**Location**")
        header[5].markdown("**Openings**")
        header[6].markdown("**Status**")
        header[7].markdown("**Doc**")
        header[8].markdown("**Edit**")
        header[9].markdown("**Status**")

        st.divider()

        # Render only the limited DataFrame rows
        for _, row in display_jobs_df.iterrows():

            cols = st.columns(
                [2, 3, 3, 3, 2, 2, 2, 2.5, 1.5, 1.5]
            )

            cols[0].write(
                row["job_reference_no"]
            )

            cols[1].write(
                job_titles_lookup.get(
                    row["job_title_id"],
                    ""
                )
            )

            cols[2].write(
                companies_lookup.get(
                    row["company_id"],
                    ""
                )
            )

            job_recruiters = []

            for assignment in assignments_data:

                if assignment["job_id"] == row["job_id"]:

                    recruiter_name = recruiter_lookup.get(
                        assignment["user_id"]
                    )

                    if recruiter_name:

                        job_recruiters.append(
                            recruiter_name
                        )

            cols[3].write(
                ", ".join(job_recruiters)
            )

            cols[4].write(
                row["location"]
            )

            cols[5].write(
                row["openings"]
            )

            job_status = row["job_status"]

            if job_status == "Open":

                cols[6].markdown(
                    """
                    <span style="
                    background:#16A34A;
                    color:white;
                    padding:4px 10px;
                    border-radius:10px;
                    ">
                    Open
                    </span>
                    """,
                    unsafe_allow_html=True
                )

            elif job_status == "Closed":

                cols[6].markdown(
                    """
                    <span style="
                    background:#DC2626;
                    color:white;
                    padding:4px 10px;
                    border-radius:10px;
                    ">
                    Closed
                    </span>
                    """,
                    unsafe_allow_html=True
                )

            elif job_status == "On Hold":

                cols[6].markdown(
                    """
                    <span style="
                    background:#F59E0B;
                    color:white;
                    padding:4px 10px;
                    border-radius:10px;
                    ">
                    On Hold
                    </span>
                    """,
                    unsafe_allow_html=True
                )

            else:

                cols[6].markdown(
                    """
                    <span style="
                    background:#64748B;
                    color:white;
                    padding:4px 10px;
                    border-radius:10px;
                    ">
                    Cancelled
                    </span>
                    """,
                    unsafe_allow_html=True
                )

            if row["job_document_path"]:

                if cols[7].button(
                    "📄 View",
                    key=f"doc_{row['job_id']}"
                ):

                    st.session_state.job_document_url = (
                        get_document_url(
                            row["job_document_path"]
                        )
                    )

                    st.rerun()

            else:

                cols[7].write("-")


            # -------------------------
            # EDIT BUTTON
            # -------------------------

            if cols[8].button(
                "✏️",
                key=f"edit_{row['job_id']}"
            ):

                st.session_state.edit_job_id = (
                    row["job_id"]
                )

                for field in [

                    "sub_category",

                    "location",

                    "min_year",
                    "min_month",

                    "max_year",
                    "max_month",

                    "job_type",

                    "openings",

                    "pay_min",
                    "pay_max",

                    "currency",
                    "pay_unit",

                    "skills_required",
                    "job_description",

                    "performa_invoice_no",
                    "performa_invoice_status",

                    "invoice_no",
                    "invoice_status",

                    "job_status",

                    "remark"

                ]:

                    if field in st.session_state:

                        del st.session_state[field]

                st.rerun()

            # -------------------------
            # CLOSE / REOPEN BUTTON
            # -------------------------

            if row["job_status"] == "Open":

                if cols[9].button(
                    "🔒",
                    key=f"close_{row['job_id']}"
                ):

                    (
                        supabase
                        .table("job_management")
                        .update({
                            "job_status": "Closed"
                        })
                        .eq(
                            "job_id",
                            row["job_id"]
                        )
                        .execute()
                    )

                    st.success(
                        "Job Closed Successfully"
                    )

                    st.rerun()

            else:

                if cols[9].button(
                    "🔓",
                    key=f"reopen_{row['job_id']}"
                ):

                    (
                        supabase
                        .table("job_management")
                        .update({
                            "job_status": "Open"
                        })
                        .eq(
                            "job_id",
                            row["job_id"]
                        )
                        .execute()
                    )

                    st.success(
                        "Job Reopened Successfully"
                    )

                    st.rerun()

    else:

        st.info(
            "No jobs found."
        )