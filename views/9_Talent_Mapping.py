import plotly.express as px
import streamlit as st
import pandas as pd
import numpy as np
import html
import io
import json
import re
import textwrap
import streamlit.components.v1 as components
from datetime import datetime
from db import supabase, SUPABASE_URL, SUPABASE_KEY
from common import show_logout, show_job_notifications, show_user_profile
from theme import apply_theme

def clean_phone_number(val):
    """
    Cleans phone/mobile numbers from Excel/database imports.
    Removes trailing decimals like .0 or .00 (e.g. 9876543210.0 -> 9876543210),
    handles scientific notation, and strips extra spaces/nulls.
    """
    if val is None or pd.isna(val):
        return ""
    if isinstance(val, (int, np.integer)):
        return str(val).strip()
    if isinstance(val, (float, np.floating)):
        if np.isnan(val) or np.isinf(val):
            return ""
        if val.is_integer():
            return str(int(val)).strip()
        return str(val).strip()
    
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ["none", "nan", "null", "<na>"]:
        return ""
    
    # Remove trailing .0 or .00 from string representations (e.g. "9876543210.0")
    if re.match(r'^\+?\d+\.0+$', val_str):
        return val_str.split('.')[0]
        
    # Handle scientific notation strings e.g. "9.87654321e+09"
    try:
        f_val = float(val_str)
        if f_val.is_integer() and ("e" in val_str.lower() or val_str.endswith(".0")):
            return str(int(f_val))
    except Exception:
        pass
        
    return val_str

def clean_str_val(val):
    """
    Cleans string values read from Excel rows, stripping float decimals (.0)
    for integers, converting NaNs/Nones to empty strings.
    """
    if val is None or pd.isna(val):
        return ""
    if isinstance(val, (int, np.integer)):
        return str(val).strip()
    if isinstance(val, (float, np.floating)):
        if np.isnan(val) or np.isinf(val):
            return ""
        if val.is_integer():
            return str(int(val)).strip()
        return str(val).strip()
    val_str = str(val).strip()
    if val_str.lower() in ["none", "nan", "null", "<na>"]:
        return ""
    if re.match(r'^\d+\.0+$', val_str):
        return val_str.split('.')[0]
    return val_str

COMPANY_TYPES = ["Chemicals", "Agro-Chemicals", "Seeds", "Fertilizer", "Bio-Agri", "Pharmaceuticals", "Manufacturing", "FMCG", "Renewable Energy", "Others"]

# ==============================================================================
# 1. LOGIN & PAGE CONFIGURATION
# ==============================================================================
if not st.session_state.get("logged_in", False):
    st.switch_page("Home.py")
    st.stop()

st.set_page_config(
    page_title="Talent Mapping",
    page_icon="🗺️",
    layout="wide"
)

apply_theme()

with st.sidebar:
    show_user_profile()
    show_logout()
    show_job_notifications()

# ==============================================================================
# 2. SESSION STATE & QUERY PARAMS INITIALIZATION
# ==============================================================================
if "add_under" in st.query_params:
    try:
        add_id = int(st.query_params["add_under"])
        st.session_state.tm_add_under_id = add_id
        st.query_params.clear()
    except Exception:
        pass

if "tm_edit_node_id" not in st.session_state:
    st.session_state.tm_edit_node_id = None
if "tm_reparent_node_id" not in st.session_state:
    st.session_state.tm_reparent_node_id = None
if "tm_add_under_id" not in st.session_state:
    st.session_state.tm_add_under_id = None
if "tm_selected_company" not in st.session_state:
    st.session_state.tm_selected_company = "All"
if "tm_selected_type" not in st.session_state:
    st.session_state.tm_selected_type = "All"
if "tm_form_reset_counter" not in st.session_state:
    st.session_state.tm_form_reset_counter = 0

COMPANY_TYPES = ["Seeds", "Chemicals", "Fertilizer", "Agro-Chemicals", "Pharmaceuticals", "Manufacturing", "FMCG", "Others"]

# ==============================================================================
# 3. DATABASE ACCESS & SYNCHRONIZATION HELPERS
# ==============================================================================
def check_table_exists():
    """Checks if the talent_mapping table exists in Supabase."""
    try:
        supabase.table("talent_mapping").select("mapping_id").limit(1).execute()
        return True
    except Exception:
        return False

def fetch_talent_mappings():
    """Fetches all talent mapping records from Supabase."""
    try:
        res = (
            supabase.table("talent_mapping")
            .select("*")
            .order("company_name")
            .order("mapping_id")
            .execute()
        )
        return res.data or []
    except Exception as e:
        st.error(f"Error fetching talent mapping: {str(e)}")
        return []

def insert_talent_mapping(record):
    """Inserts a new talent mapping record."""
    try:
        record["created_by"] = st.session_state.get("user_id")
        record["created_by_name"] = st.session_state.get("user_name")
        record["created_on"] = datetime.utcnow().isoformat()
        record["updated_on"] = datetime.utcnow().isoformat()
        res = supabase.table("talent_mapping").insert(record).execute()
        return True, res.data
    except Exception as e:
        return False, str(e)

def update_talent_mapping(mapping_id, updates):
    """Updates an existing talent mapping record."""
    try:
        updates["updated_on"] = datetime.utcnow().isoformat()
        res = supabase.table("talent_mapping").update(updates).eq("mapping_id", mapping_id).execute()
        return True, res.data
    except Exception as e:
        return False, str(e)

def delete_talent_mapping(mapping_id):
    """Deletes a talent mapping record and detaches its children."""
    try:
        # Detach child nodes so they become top-level
        supabase.table("talent_mapping").update({"reports_to_id": None}).eq("reports_to_id", mapping_id).execute()
        # Delete the record
        supabase.table("talent_mapping").delete().eq("mapping_id", mapping_id).execute()
        return True, "Deleted successfully"
    except Exception as e:
        return False, str(e)

@st.cache_data(ttl=15)
def get_all_ats_candidates():
    """Fetches candidate names and profile details for smart auto-fill."""
    candidates = []
    try:
        live = (
            supabase.table("candidate_management")
            .select("candidate_id, first_name, last_name, current_company, current_designation, current_location, experience_years, experience_months, current_ctc, expected_ctc, mobile_no, email, skills")
            .execute()
            .data or []
        )
        for c in live:
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            exp_y = c.get("experience_years") or 0
            exp_m = c.get("experience_months") or 0
            exp_str = f"{exp_y}Y {exp_m}M" if (exp_y or exp_m) else ""
            candidates.append({
                "candidate_id": c.get("candidate_id"),
                "display_name": f"{name} ({c.get('current_designation') or 'Candidate'} - {c.get('current_company') or 'N/A'})",
                "candidate_name": name,
                "company_name": c.get("current_company") or "",
                "designation": c.get("current_designation") or "",
                "location": c.get("current_location") or "",
                "experience": exp_str,
                "current_ctc": c.get("current_ctc"),
                "expected_ctc": c.get("expected_ctc"),
                "contact_number": clean_phone_number(c.get("mobile_no")),
                "email_id": c.get("email") or ""
            })
    except Exception:
        pass
    return candidates

def generate_sample_import_template():
    """Generates a downloadable sample Excel template for bulk talent mapping import."""
    template_data = [
        {
            "Company Type": "Chemicals",
            "Current Company": "UPL",
            "Candidate Name": "Candidate A",
            "Designation": "Head of Production",
            "Location": "Mumbai",
            "Experience": "18 Years",
            "Current CTC": 4500000,
            "Expected CTC": 5200000,
            "Contact Number": "9876543210",
            "Email ID": "candidate.a@example.com",
            "Comments": "Executive leader over all plant sites",
            "Reports To (Manager Name or ID)": ""
        },
        {
            "Company Type": "Chemicals",
            "Current Company": "UPL",
            "Candidate Name": "Candidate B",
            "Designation": "Plant Head - Gujarat",
            "Location": "Ankleshwar",
            "Experience": "14 Years",
            "Current CTC": 3200000,
            "Expected CTC": 3800000,
            "Contact Number": "9876543211",
            "Email ID": "candidate.b@example.com",
            "Comments": "Reports directly to Head of Production",
            "Reports To (Manager Name or ID)": "Candidate A"
        }
    ]
    df_sample = pd.DataFrame(template_data)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_sample.to_excel(writer, index=False, sheet_name="Talent Mapping Template")
    return out.getvalue()

def parse_and_diff_excel(file_bytes, filename, existing_mappings):
    """
    Parses an uploaded Excel or CSV file and performs line-by-line comparison
    against the existing database records.
    Assumes Excel is the latest source of truth.
    """
    try:
        if isinstance(file_bytes, bytes):
            file_obj = io.BytesIO(file_bytes)
        else:
            file_obj = file_bytes

        if filename.lower().endswith(".csv"):
            df_in = pd.read_csv(file_obj)
        else:
            df_in = pd.read_excel(file_obj)
    except Exception as e:
        return None, None, f"Error reading file: {str(e)}"
    
    if df_in.empty:
        return None, None, "The uploaded file is empty."
    
    # Normalize column names with unique target prevention
    col_map = {}
    assigned_targets = set()
    for col in df_in.columns:
        c_clean = str(col).strip().lower().replace("_", " ").replace("-", " ")
        target = None
        if any(k in c_clean for k in ["company type", "type", "sector", "industry"]):
            target = "company_type"
        elif any(k in c_clean for k in ["current company", "company name", "company", "client"]):
            target = "company_name"
        elif any(k in c_clean for k in ["candidate name", "candidate", "employee", "full name", "name"]):
            target = "candidate_name"
        elif any(k in c_clean for k in ["designation", "role", "title", "position"]):
            target = "designation"
        elif any(k in c_clean for k in ["location", "city", "place"]):
            target = "location"
        elif any(k in c_clean for k in ["expected ctc", "exp ctc", "expected salary", "expected"]):
            target = "expected_ctc"
        elif any(k in c_clean for k in ["current ctc", "present ctc", "current salary", "ctc", "salary"]):
            target = "current_ctc"
        elif any(k in c_clean for k in ["experience", "total exp", "exp yrs", "exp years", "experience yrs", "exp"]):
            target = "experience"
        elif any(k in c_clean for k in ["contact", "mobile", "phone"]):
            target = "contact_number"
        elif any(k in c_clean for k in ["email", "mail"]):
            target = "email_id"
        elif any(k in c_clean for k in ["comments", "notes", "remarks", "intel"]):
            target = "comments"
        elif any(k in c_clean for k in ["reports to", "manager", "reporting"]):
            target = "reports_to"
        elif c_clean in ["id", "mapping id", "mapping_id"]:
            target = "mapping_id"
        
        if target and target not in assigned_targets:
            col_map[col] = target
            assigned_targets.add(target)
    
    df_clean = df_in.rename(columns=col_map)
    
    # Build lookups for DB records
    db_by_id = {int(m["mapping_id"]): m for m in existing_mappings if m.get("mapping_id")}
    db_by_comp_cand = {}
    for m in existing_mappings:
        comp_key = (m.get("company_name") or "").strip().lower()
        cand_key = (m.get("candidate_name") or "").strip().lower()
        if comp_key and cand_key:
            db_by_comp_cand[(comp_key, cand_key)] = m

    diff_list = []
    actions_to_execute = []
    
    for idx, row in df_clean.iterrows():
        def get_row_val(field):
            v = row.get(field)
            if isinstance(v, pd.Series):
                v = v.iloc[0] if not v.empty else ""
            return clean_str_val(v)

        comp_name = get_row_val("company_name")
        cand_name = get_row_val("candidate_name")
        desig = get_row_val("designation")
        
        if not comp_name or not cand_name:
            continue
        
        comp_type = get_row_val("company_type") or "Chemicals"
        loc = get_row_val("location")
        exp = get_row_val("experience")
        
        curr_ctc_str = get_row_val("current_ctc")
        try:
            curr_ctc_val = float(curr_ctc_str) if curr_ctc_str else None
        except Exception:
            curr_ctc_val = None
        
        exp_ctc_str = get_row_val("expected_ctc")
        try:
            exp_ctc_val = float(exp_ctc_str) if exp_ctc_str else None
        except Exception:
            exp_ctc_val = None
        
        contact = clean_phone_number(get_row_val("contact_number"))
        email = get_row_val("email_id")
        comments = get_row_val("comments")
        
        # Resolve manager ID (handle numeric float strings like "12.0")
        reports_to_raw = get_row_val("reports_to")
        rep_id_val = None
        if reports_to_raw:
            clean_rep_id = clean_phone_number(reports_to_raw)
            if clean_rep_id.isdigit() and int(clean_rep_id) in db_by_id:
                rep_id_val = int(clean_rep_id)
            else:
                # Name lookup in same company
                comp_lower = comp_name.lower()
                rep_name_lower = reports_to_raw.lower()
                matched_mgr = next((m for m in existing_mappings if m.get("company_name", "").strip().lower() == comp_lower and rep_name_lower in m.get("candidate_name", "").strip().lower()), None)
                if matched_mgr:
                    rep_id_val = matched_mgr.get("mapping_id")
        
        # Check matching record (handle numeric float strings like "5.0")
        mapping_id_in_row = row.get("mapping_id")
        clean_mid = clean_phone_number(mapping_id_in_row)
        matched_db_rec = None
        if clean_mid and clean_mid.isdigit() and int(clean_mid) in db_by_id:
            matched_db_rec = db_by_id[int(clean_mid)]
        elif (comp_name.lower(), cand_name.lower()) in db_by_comp_cand:
            matched_db_rec = db_by_comp_cand[(comp_name.lower(), cand_name.lower())]
            
        payload = {
            "company_type": comp_type,
            "company_name": comp_name,
            "candidate_name": cand_name,
            "designation": desig or (matched_db_rec.get("designation") if matched_db_rec else "Candidate"),
            "location": loc,
            "experience": exp,
            "current_ctc": curr_ctc_val,
            "expected_ctc": exp_ctc_val,
            "contact_number": contact,
            "email_id": email,
            "comments": comments,
            "reports_to_id": rep_id_val if rep_id_val is not None else (matched_db_rec.get("reports_to_id") if matched_db_rec else None)
        }
        
        if not matched_db_rec:
            diff_list.append({
                "Line": idx + 1,
                "Status": "🟢 New Record",
                "Company": comp_name,
                "Candidate": cand_name,
                "Designation": payload["designation"],
                "Diff Summary": "New candidate not in database. Will be inserted."
            })
            actions_to_execute.append(("insert", None, payload))
        else:
            field_changes = []
            if payload["company_type"].lower() != (matched_db_rec.get("company_type") or "").strip().lower():
                field_changes.append(f"Type: '{matched_db_rec.get('company_type')}' ➔ '{payload['company_type']}'")
            if payload["designation"].lower() != (matched_db_rec.get("designation") or "").strip().lower():
                field_changes.append(f"Designation: '{matched_db_rec.get('designation')}' ➔ '{payload['designation']}'")
            if payload["location"].lower() != (matched_db_rec.get("location") or "").strip().lower():
                field_changes.append(f"Location: '{matched_db_rec.get('location')}' ➔ '{payload['location']}'")
            if payload["experience"].lower() != (matched_db_rec.get("experience") or "").strip().lower():
                field_changes.append(f"Exp: '{matched_db_rec.get('experience')}' ➔ '{payload['experience']}'")
            
            db_c_ctc = float(matched_db_rec.get("current_ctc")) if matched_db_rec.get("current_ctc") is not None else None
            if payload["current_ctc"] != db_c_ctc:
                field_changes.append(f"Current CTC: ₹{db_c_ctc or 0:,.0f} ➔ ₹{payload['current_ctc'] or 0:,.0f}")
                
            db_e_ctc = float(matched_db_rec.get("expected_ctc")) if matched_db_rec.get("expected_ctc") is not None else None
            if payload["expected_ctc"] != db_e_ctc:
                field_changes.append(f"Exp CTC: ₹{db_e_ctc or 0:,.0f} ➔ ₹{payload['expected_ctc'] or 0:,.0f}")
                
            db_contact = clean_phone_number(matched_db_rec.get("contact_number"))
            if payload["contact_number"] != db_contact:
                field_changes.append(f"Contact: '{db_contact}' ➔ '{payload['contact_number']}'")
            if payload["email_id"].lower() != (matched_db_rec.get("email_id") or "").strip().lower():
                field_changes.append(f"Email: '{matched_db_rec.get('email_id')}' ➔ '{payload['email_id']}'")
            if payload["comments"] != (matched_db_rec.get("comments") or "").strip() and payload["comments"]:
                field_changes.append(f"Comments updated")
            if payload["reports_to_id"] != matched_db_rec.get("reports_to_id") and payload["reports_to_id"] is not None:
                field_changes.append(f"Manager ID: {matched_db_rec.get('reports_to_id')} ➔ {payload['reports_to_id']}")
                
            if field_changes:
                diff_list.append({
                    "Line": idx + 1,
                    "Status": "🟡 Updated Data",
                    "Company": comp_name,
                    "Candidate": cand_name,
                    "Designation": payload["designation"],
                    "Diff Summary": "; ".join(field_changes)
                })
                actions_to_execute.append(("update", matched_db_rec.get("mapping_id"), payload))
            else:
                diff_list.append({
                    "Line": idx + 1,
                    "Status": "⚪ Identical (In-Sync)",
                    "Company": comp_name,
                    "Candidate": cand_name,
                    "Designation": payload["designation"],
                    "Diff Summary": "Exact match with database record. No changes needed."
                })
                
    return diff_list, actions_to_execute, None

# ==============================================================================
# 4. ENTERPRISE ORG CHART HTML / JS GENERATOR (WITH NATIVE SCROLLBARS)
# ==============================================================================

# ==============================================================================
# 3.1 STREAMLIT DIALOGS FOR QUICK ACTIONS TOOLBAR
# ==============================================================================
@st.dialog("➕ Add Direct Report")
def show_add_direct_report_dialog(mgr_rec):
    st.markdown(f"**Reporting Manager:** `👤 {mgr_rec.get('candidate_name')}` ({mgr_rec.get('designation')}) • `🏢 {mgr_rec.get('company_name')}`")
    
    with st.form("dialog_add_report_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Candidate Full Name *", placeholder="e.g. Rahul Sharma")
            desig = st.text_input("Designation *", placeholder="e.g. Senior Manager - Sales")
            loc = st.text_input("Location", value=mgr_rec.get("location") or "")
            exp = st.text_input("Experience", placeholder="e.g. 10 Years")
        with col2:
            curr_ctc = st.number_input("Current CTC (₹)", min_value=0.0, step=50000.0, format="%.0f")
            exp_ctc = st.number_input("Expected CTC (₹)", min_value=0.0, step=50000.0, format="%.0f")
            contact = st.text_input("Mobile Number", placeholder="e.g. 9876543210")
            email = st.text_input("Email Address", placeholder="e.g. rahul@example.com")
            
        comments = st.text_area("Recruiter Remarks / Intel", placeholder="Key candidate intel, notice period, or notes...")
        
        submitted = st.form_submit_button("💾 Save Direct Report", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("Please enter candidate full name.")
            elif not desig.strip():
                st.error("Please enter designation.")
            else:
                payload = {
                    "company_name": mgr_rec.get("company_name"),
                    "company_type": mgr_rec.get("company_type", "Chemicals"),
                    "candidate_name": name.strip(),
                    "designation": desig.strip(),
                    "location": loc.strip() or "N/A",
                    "experience": exp.strip() or "N/A",
                    "current_ctc": curr_ctc if curr_ctc > 0 else None,
                    "expected_ctc": exp_ctc if exp_ctc > 0 else None,
                    "contact_number": clean_phone_number(contact),
                    "email_id": email.strip(),
                    "comments": comments.strip(),
                    "reports_to_id": mgr_rec.get("mapping_id")
                }
                ok, res = insert_talent_mapping(payload)
                if ok:
                    st.success(f"🎉 Successfully mapped {name} under {mgr_rec.get('candidate_name')}!")
                    st.rerun()
                else:
                    st.error(f"Failed to save record: {res}")


@st.dialog("👁️ Candidate 360 Intel Dossier")
def show_candidate_dossier_dialog(cand_rec, all_records):
    st.markdown(f"### 👤 {cand_rec.get('candidate_name')}")
    st.caption(f"💼 {cand_rec.get('designation')} • 🏢 {cand_rec.get('company_name')} ({cand_rec.get('company_type', 'Chemicals')})")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"📍 **Location:** {cand_rec.get('location') or 'N/A'}")
        st.markdown(f"⏱️ **Experience:** {cand_rec.get('experience') or 'N/A'}")
        c_ctc = f"₹ {float(cand_rec.get('current_ctc')):,.0f}" if cand_rec.get("current_ctc") else "Not Disclosed"
        st.markdown(f"💰 **Current CTC:** {c_ctc}")
    with col2:
        clean_phone = clean_phone_number(cand_rec.get("contact_number"))
        st.markdown(f"📞 **Phone:** {clean_phone or 'Not Available'}")
        st.markdown(f"✉️ **Email:** {cand_rec.get('email_id') or 'Not Available'}")
        e_ctc = f"₹ {float(cand_rec.get('expected_ctc')):,.0f}" if cand_rec.get("expected_ctc") else "N/A"
        st.markdown(f"🎯 **Expected CTC:** {e_ctc}")
        
    st.markdown("---")
    st.markdown("💬 **Recruiter Intel & Remarks:**")
    st.info(cand_rec.get("comments") or "No remarks recorded.")
    
    c_id = cand_rec.get("mapping_id")
    sub_reports = [r for r in all_records if r.get("reports_to_id") == c_id]
    st.markdown(f"👥 **Direct Reports ({len(sub_reports)}):**")
    if sub_reports:
        for r in sub_reports:
            st.write(f"- 👤 **{r.get('candidate_name')}** — {r.get('designation')}")
    else:
        st.caption("No direct reports currently mapped under this leader.")


@st.dialog("🚚 Move / Transfer / Lifecycle Actions")
def show_move_candidate_dialog(cand_rec, all_records):
    st.markdown(f"**Target Candidate:** `👤 {cand_rec.get('candidate_name')}` ({cand_rec.get('designation')}) • `🏢 {cand_rec.get('company_name')}`")
    
    tab_comp, tab_mgr, tab_retire = st.tabs(["🏢 Move to Company", "👑 Reassign Manager", "🏖️ Retired / Left Market"])
    
    with tab_comp:
        with st.form("dialog_move_comp_form"):
            new_comp_type = st.selectbox("Destination Company Type", COMPANY_TYPES, index=0)
            new_comp_name = st.text_input("Destination Company Name *", placeholder="e.g. PI Industries")
            new_desig = st.text_input("New Designation", value=cand_rec.get("designation") or "")
            st.caption("ℹ️ Subordinates in current company will be detached/promoted to avoid cross-company tree conflicts.")
            
            if st.form_submit_button("💾 Save Company Transfer", use_container_width=True):
                if not new_comp_name.strip():
                    st.error("Please enter the destination company name.")
                else:
                    c_id = cand_rec.get("mapping_id")
                    supabase.table("talent_mapping").update({"reports_to_id": cand_rec.get("reports_to_id")}).eq("reports_to_id", c_id).execute()
                    ok, res = update_talent_mapping(c_id, {
                        "company_name": new_comp_name.strip(),
                        "company_type": new_comp_type,
                        "designation": new_desig.strip() or cand_rec.get("designation"),
                        "reports_to_id": None
                    })
                    if ok:
                        st.success(f"🎉 Successfully transferred {cand_rec.get('candidate_name')} to {new_comp_name}!")
                        st.rerun()
                    else:
                        st.error(f"Error: {res}")
                        
    with tab_mgr:
        with st.form("dialog_reassign_mgr_form"):
            c_id = cand_rec.get("mapping_id")
            mgr_candidates = [r for r in all_records if r.get("mapping_id") != c_id and r.get("company_name") == cand_rec.get("company_name")]
            mgr_options = {"None (Top-Level Leader / Root)": None}
            for r in mgr_candidates:
                mgr_options[f"👤 {r.get('candidate_name')} ({r.get('designation')})"] = r.get("mapping_id")
                
            curr_mgr_id = cand_rec.get("reports_to_id")
            default_idx = 0
            for idx, (label, mid) in enumerate(mgr_options.items()):
                if mid == curr_mgr_id:
                    default_idx = idx
                    break
                    
            selected_mgr_label = st.selectbox("Select New Reporting Manager", list(mgr_options.keys()), index=default_idx)
            new_mgr_id = mgr_options[selected_mgr_label]
            
            if st.form_submit_button("👑 Update Reporting Line", use_container_width=True):
                ok, res = update_talent_mapping(c_id, {"reports_to_id": new_mgr_id})
                if ok:
                    st.success(f"✅ Reporting line updated for {cand_rec.get('candidate_name')}!")
                    st.rerun()
                else:
                    st.error(f"Error: {res}")
                    
    with tab_retire:
        with st.form("dialog_retire_form"):
            status_choice = st.selectbox("Lifecycle Status", ["Retired", "Career Break", "Relocated Abroad", "Alumni"])
            retire_notes = st.text_area("Exit Intel / Notes", placeholder="e.g. Retired in 2025. Contactable for advisory.")
            
            if st.form_submit_button("🏖️ Mark Status & Update", use_container_width=True):
                c_id = cand_rec.get("mapping_id")
                supabase.table("talent_mapping").update({"reports_to_id": cand_rec.get("reports_to_id")}).eq("reports_to_id", c_id).execute()
                new_comments = f"[{status_choice.upper()}] {retire_notes.strip() + ' | ' if retire_notes.strip() else ''}{cand_rec.get('comments') or ''}"
                ok, res = update_talent_mapping(c_id, {
                    "reports_to_id": None,
                    "comments": new_comments
                })
                if ok:
                    st.success(f"✅ Marked {cand_rec.get('candidate_name')} as {status_choice}!")
                    st.rerun()
                else:
                    st.error(f"Error: {res}")


def generate_org_hierarchy_chart(comp_name, comp_type, comp_records, available_company_types=None):
    """
    Generates an enterprise-grade interactive Org Chart with:
    - Dedicated Company Header Card anchored at the top of each hierarchy tree
    - Multi-Company Canvas Panorama (view all company trees in one unified canvas or company-wise)
    - Add Direct Report button below every candidate card to quickly map reporting lines
    - In-chart interactive Modal Dialog to save new reporting candidates immediately
    - Hardware-accelerated 2D Transform Pan & Zoom Engine (60 FPS)
    - Top-Down true tree connector lines
    - Zoom In/Out & Pan controls
    - Search & Highlight
    - Collapsible Subtrees
    - Candidate 360 Intel Slide-Over Modal
    """
    # Group records by company
    companies_dict = {}
    for m in comp_records:
        c_name = (m.get("company_name") or "Unknown Company").strip()
        companies_dict.setdefault(c_name, []).append(m)

    def get_initials(name):
        parts = [p for p in str(name).strip().split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        elif parts:
            return parts[0][:2].upper()
        return "TM"

    # Recursive Tree Builder for a given company
    def build_company_tree_html(company_name, records):
        nodes_by_id = {m.get("mapping_id"): m for m in records}
        children_by_parent = {}
        for m in records:
            p_id = m.get("reports_to_id")
            if p_id not in nodes_by_id:
                p_id = None
            children_by_parent.setdefault(p_id, []).append(m)

        def build_node_html(parent_id, depth=0):
            children = children_by_parent.get(parent_id, [])
            if not children:
                return ""

            html_out = "<ul>"
            for child in children:
                c_id = child.get("mapping_id")
                c_name = html.escape(str(child.get("candidate_name") or "Candidate"))
                c_desig = html.escape(str(child.get("designation") or "Role"))
                c_loc = html.escape(str(child.get("location") or "N/A"))
                c_exp = html.escape(str(child.get("experience") or "N/A"))
                c_ctc = f"₹ {float(child.get('current_ctc')):,.0f}" if child.get("current_ctc") else "Not Disclosed"
                c_type = html.escape(str(child.get("company_type") or "Chemicals"))

                sub_count = len(children_by_parent.get(c_id, []))
                initials = get_initials(c_name)

                # Level styling & badges with rich, distinct vibrant gradients
                if depth == 0:
                    level_title = "👑 Level 1"
                    header_bg = "linear-gradient(135deg, #4338ca 0%, #6366f1 50%, #8b5cf6 100%)"
                    avatar_bg = "linear-gradient(135deg, #6366f1 0%, #4338ca 100%)"
                    border_color = "#6366f1"
                    pill_bg = "rgba(99, 102, 241, 0.12)"
                    pill_color = "#4338ca"
                    pill_border = "rgba(99, 102, 241, 0.3)"
                elif depth == 1:
                    level_title = "👔 Level 2"
                    header_bg = "linear-gradient(135deg, #0284c7 0%, #0ea5e9 50%, #06b6d4 100%)"
                    avatar_bg = "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)"
                    border_color = "#0284c7"
                    pill_bg = "rgba(2, 132, 199, 0.12)"
                    pill_color = "#0369a1"
                    pill_border = "rgba(2, 132, 199, 0.3)"
                elif depth == 2:
                    level_title = "👤 Level 3"
                    header_bg = "linear-gradient(135deg, #047857 0%, #059669 50%, #10b981 100%)"
                    avatar_bg = "linear-gradient(135deg, #10b981 0%, #047857 100%)"
                    border_color = "#059669"
                    pill_bg = "rgba(16, 185, 129, 0.12)"
                    pill_color = "#065f46"
                    pill_border = "rgba(16, 185, 129, 0.3)"
                else:
                    level_title = f"🎯 Level {depth + 1}"
                    header_bg = "linear-gradient(135deg, #b45309 0%, #d97706 50%, #f59e0b 100%)"
                    avatar_bg = "linear-gradient(135deg, #f59e0b 0%, #b45309 100%)"
                    border_color = "#d97706"
                    pill_bg = "rgba(245, 158, 11, 0.12)"
                    pill_color = "#92400e"
                    pill_border = "rgba(245, 158, 11, 0.3)"

                # Dynamic type badge styling
                type_lower = c_type.lower()
                if "seed" in type_lower:
                    tag_bg = "rgba(34, 197, 94, 0.35)"
                elif "chem" in type_lower:
                    tag_bg = "rgba(59, 130, 246, 0.35)"
                elif "fert" in type_lower:
                    tag_bg = "rgba(245, 158, 11, 0.35)"
                elif "bio" in type_lower:
                    tag_bg = "rgba(168, 85, 247, 0.35)"
                elif "pharma" in type_lower:
                    tag_bg = "rgba(244, 63, 94, 0.35)"
                else:
                    tag_bg = "rgba(255, 255, 255, 0.28)"

                report_pill = ""
                if sub_count > 0:
                    report_pill = f"""<div class="wd-reports-badge" style="background: {pill_bg}; color: {pill_color}; border: 1px solid {pill_border};" onclick="event.stopPropagation(); toggleNodeChildren(this);">👥 {sub_count} Direct Reports <span class="wd-toggle-icon">▾</span></div>"""

                card_html = f"""
                <li class="wd-node-item" id="node-{c_id}" data-id="{c_id}">
                    <div class="wd-card" style="border-top: 4px solid {border_color};" onclick="showIntelModal({c_id})">
                        <div class="wd-card-header" style="background: {header_bg};">
                            <span>{level_title}</span>
                            <span class="wd-tag" style="background: {tag_bg};">{c_type}</span>
                        </div>
                        <div class="wd-card-body">
                            <div class="wd-profile-row">
                                <div class="wd-avatar" style="background: {avatar_bg}; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">{initials}</div>
                                <div class="wd-profile-text">
                                    <div class="wd-name">{c_name}</div>
                                    <div class="wd-desig" style="color: {border_color};">{c_desig}</div>
                                </div>
                            </div>
                            <div class="wd-meta-grid">
                                <div class="wd-meta-item">📍 <b>{c_loc}</b></div>
                                <div class="wd-meta-item">⏱️ <b>{c_exp}</b></div>
                                <div class="wd-meta-item wd-ctc-item">💰 <b>{c_ctc}</b></div>
                            </div>
                            {report_pill}
                            <div class="wd-card-actions" onclick="event.stopPropagation();">
                                <button type="button" class="wd-btn-intel" onclick="showIntelModal({c_id})" title="View Full 360 Dossier">👁️ Intel</button>
                                <button type="button" class="wd-btn-edit-node" onclick="openEditCandidateModal({c_id})" title="Edit Details">✏️ Edit</button>
                                <button type="button" class="wd-btn-move-node" onclick="openMoveCandidateModal({c_id})" title="Move / Transfer / Retire">🚚 Move</button>
                                <button type="button" class="wd-btn-del-node" onclick="openDeleteCandidateModal({c_id})" title="Delete Candidate">🗑️</button>
                            </div>
                        </div>
                        <div class="wd-card-footer" onclick="event.stopPropagation();">
                            <button type="button" class="wd-btn-footer-add" onclick="openAddReportModal({c_id})" title="Add candidate reporting under {c_name}">
                                ➕ Add Direct Report
                            </button>
                        </div>
                    </div>
                    {build_node_html(c_id, depth + 1)}
                </li>
                """
                html_out += card_html
            html_out += "</ul>"
            return html_out

        c_type = records[0].get("company_type", "Chemicals") if records else "Chemicals"
        headcount = len(records)
        level1_count = len(children_by_parent.get(None, []))

        escaped_comp_name = html.escape(company_name)
        escaped_comp_type = html.escape(c_type)

        company_tree_html = f"""
        <li class="wd-node-item wd-company-root-item" data-company="{escaped_comp_name}">
            <div class="wd-company-card">
                <div class="wd-comp-card-badge">{escaped_comp_type}</div>
                <div class="wd-comp-card-title">🏢 {escaped_comp_name}</div>
                <div class="wd-comp-card-stats">
                    <span>👥 <b>{headcount}</b> Candidates</span>
                    <span>👑 <b>{level1_count}</b> Top Leaders</span>
                </div>
            </div>
            {build_node_html(None, depth=0)}
        </li>
        """
        return company_tree_html

    # Build all company trees inside a single unified container
    all_companies_html = '<div class="wd-tree"><ul>'
    for c_name, c_recs in companies_dict.items():
        all_companies_html += build_company_tree_html(c_name, c_recs)
    all_companies_html += "</ul></div>"

    unique_company_names = sorted(list(companies_dict.keys()))
    comp_options_html = f'<option value="__ALL__">🌐 All Companies ({len(unique_company_names)})</option>'
    for uc in unique_company_names:
        escaped_uc = html.escape(uc)
        selected_attr = 'selected' if (comp_name != "All Companies" and uc == comp_name) else ''
        comp_options_html += f'<option value="{escaped_uc}" {selected_attr}>🏢 {escaped_uc}</option>'

    current_user_id = json.dumps(st.session_state.get("user_id"))
    current_user_name = json.dumps(st.session_state.get("user_name"))
    current_comp_records_json = json.dumps(comp_records)

    # Dynamically gather all existing company types in the database
    types_list = list(COMPANY_TYPES)
    if available_company_types:
        types_list.extend(available_company_types)
    for m in comp_records:
        if m.get("company_type"):
            types_list.append(m.get("company_type"))
    all_comp_types = sorted(list(set(t for t in types_list if t and t not in ["All", "All Types"])))
    all_comp_types_json = json.dumps(all_comp_types)

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            user-select: none;
        }}
        html, body {{
            background: transparent;
            overflow: hidden;
            height: 100%;
            width: 100%;
        }}
        /* Vibrant Translucent / Colorful Mesh Canvas Container with 2D Pan-and-Zoom */
        .wd-canvas-viewport {{
            width: 100%;
            height: 100vh;
            position: relative;
            overflow: hidden !important;
            cursor: grab;
            user-select: none;
            -webkit-user-select: none;
            background: 
                radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.14) 0px, transparent 45%),
                radial-gradient(at 100% 0%, rgba(236, 72, 153, 0.12) 0px, transparent 45%),
                radial-gradient(at 100% 100%, rgba(14, 165, 233, 0.14) 0px, transparent 45%),
                radial-gradient(at 0% 100%, rgba(16, 185, 129, 0.12) 0px, transparent 45%),
                radial-gradient(#6366f1 1.3px, transparent 1.3px),
                rgba(248, 250, 252, 0.78);
            background-size: 100% 100%, 100% 100%, 100% 100%, 100% 100%, 28px 28px, 100% 100%;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1.5px solid rgba(199, 210, 254, 0.7);
            border-radius: 16px;
            box-shadow: 0 12px 36px rgba(99, 102, 241, 0.08), inset 0 1px 2px rgba(255, 255, 255, 0.8);
        }}
        .wd-canvas-viewport.is-dragging {{
            cursor: grabbing !important;
        }}
        .wd-canvas-viewport.is-dragging .wd-card {{
            cursor: grabbing !important;
        }}
        
        .wd-canvas-world {{
            position: absolute;
            top: 0;
            left: 0;
            transform-origin: 0 0;
            padding: 70px 50px 200px 50px;
            display: inline-block;
            white-space: nowrap;
            text-align: center;
            will-change: transform;
        }}
        
        /* Floating Glassmorphic Control Bar */
        .wd-controls-bar {{
            position: fixed;
            top: 12px;
            left: 16px;
            z-index: 100;
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255, 255, 255, 0.92);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            padding: 6px 12px;
            border-radius: 12px;
            box-shadow: 0 8px 28px rgba(99, 102, 241, 0.12);
            border: 1px solid rgba(199, 210, 254, 0.8);
        }}
        .wd-comp-filter-select {{
            padding: 6px 10px;
            border: 1.5px solid #6366f1;
            background: #ffffff;
            color: #1e1b4b;
            font-size: 0.82rem;
            font-weight: 700;
            border-radius: 8px;
            outline: none;
            cursor: pointer;
            box-shadow: 0 2px 6px rgba(99, 102, 241, 0.15);
        }}
        .wd-comp-filter-select:focus {{
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.25);
        }}
        .wd-search-input {{
            padding: 6px 10px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            font-size: 0.82rem;
            outline: none;
            width: 170px;
            background: rgba(255, 255, 255, 0.9);
            transition: all 0.2s ease;
        }}
        .wd-search-input:focus {{
            border-color: #6366f1;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }}
        .wd-ctrl-btn {{
            background: rgba(241, 245, 249, 0.85);
            border: 1px solid #e2e8f0;
            color: #334155;
            padding: 6px 9px;
            border-radius: 8px;
            font-size: 0.80rem;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 4px;
            transition: all 0.15s ease;
        }}
        .wd-ctrl-btn:hover {{
            background: #6366f1;
            color: #ffffff;
            border-color: #6366f1;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
        }}
        .wd-zoom-badge {{
            font-size: 0.78rem;
            font-weight: 700;
            color: #6366f1;
            padding: 0 4px;
            min-width: 42px;
            text-align: center;
        }}
        
        /* Company Master Header Card & Multi-Tree Layout */
        .wd-company-card {{
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            color: #ffffff;
            padding: 12px 20px;
            border-radius: 14px;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.25), 0 0 0 1.5px rgba(255, 255, 255, 0.15);
            display: inline-block;
            min-width: 250px;
            max-width: 340px;
            text-align: center;
            position: relative;
            transition: all 0.25s ease;
            margin-bottom: 2px;
        }}
        .wd-company-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 14px 34px rgba(15, 23, 42, 0.32), 0 0 0 2px rgba(99, 102, 241, 0.6);
        }}
        .wd-comp-card-badge {{
            display: inline-block;
            padding: 2px 9px;
            background: rgba(99, 102, 241, 0.3);
            border: 1px solid rgba(165, 180, 252, 0.4);
            border-radius: 20px;
            font-size: 0.68rem;
            font-weight: 700;
            color: #e0e7ff;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            margin-bottom: 4px;
        }}
        .wd-comp-card-title {{
            font-size: 1.08rem;
            font-weight: 800;
            color: #ffffff;
            margin-bottom: 5px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}
        .wd-comp-card-stats {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            font-size: 0.72rem;
            color: #94a3b8;
            background: rgba(255, 255, 255, 0.07);
            padding: 3px 8px;
            border-radius: 6px;
        }}
        .wd-comp-card-stats b {{
            color: #f8fafc;
        }}

        /* True Top-Down Tree Architecture with Vibrant Indigo Connectors */
        .wd-tree {{
            display: inline-block;
            margin: 0 auto;
            text-align: center;
        }}
        .wd-tree ul {{
            padding-top: 26px;
            position: relative;
            display: flex;
            justify-content: center;
            gap: 36px;
            list-style-type: none;
        }}
        /* Top-level Company Root Items: Clean spacing without horizontal cross-company lines */
        .wd-tree > ul {{
            padding-top: 0;
            gap: 50px;
        }}
        .wd-tree > ul > li.wd-company-root-item {{
            padding-top: 0 !important;
            margin: 0 16px;
        }}
        .wd-tree > ul > li.wd-company-root-item::before,
        .wd-tree > ul > li.wd-company-root-item::after {{
            display: none !important;
        }}
        .wd-tree > ul > li.wd-company-root-item > ul::before {{
            border-left: 2.5px solid #6366f1 !important;
        }}

        .wd-tree li {{
            text-align: center;
            list-style-type: none;
            position: relative;
            padding: 26px 12px 0 12px;
        }}
        /* Connector lines */
        .wd-tree li::before, .wd-tree li::after {{
            content: '';
            position: absolute;
            top: 0;
            right: 50%;
            border-top: 2.5px solid #6366f1;
            width: 50%;
            height: 26px;
        }}
        .wd-tree li::after {{
            right: auto;
            left: 50%;
            border-left: 2.5px solid #6366f1;
        }}
        .wd-tree li:only-child::after, .wd-tree li:only-child::before {{
            display: none;
        }}
        .wd-tree li:only-child {{
            padding-top: 0;
        }}
        .wd-tree li:first-child::before, .wd-tree li:last-child::after {{
            border: 0 none;
        }}
        .wd-tree li:last-child::before {{
            border-right: 2.5px solid #6366f1;
            border-radius: 0 10px 0 0;
        }}
        .wd-tree li:first-child::after {{
            border-radius: 10px 0 0 0;
        }}
        .wd-tree ul ul::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 50%;
            border-left: 2.5px solid #6366f1;
            width: 0;
            height: 26px;
        }}
        
        /* Interactive Node Cards */
        .wd-card {{
            background: #ffffff;
            border-radius: 16px;
            width: 250px;
            box-shadow: 0 10px 25px rgba(99, 102, 241, 0.08), 0 2px 6px rgba(0, 0, 0, 0.04);
            cursor: pointer;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            display: inline-block;
            text-align: left;
            overflow: hidden;
            border: 1px solid rgba(226, 232, 240, 0.9);
        }}
        .wd-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 18px 36px rgba(99, 102, 241, 0.16), 0 4px 12px rgba(0, 0, 0, 0.06);
            border-color: #818cf8;
        }}
        .wd-card.highlighted {{
            box-shadow: 0 0 0 3.5px #6366f1, 0 12px 32px rgba(99, 102, 241, 0.35) !important;
            animation: pulseHighlight 1.5s infinite alternate;
        }}
        @keyframes pulseHighlight {{
            from {{ transform: scale(1.0); }}
            to {{ transform: scale(1.04); }}
        }}
        
        .wd-card-header {{
            padding: 7px 12px;
            color: #ffffff;
            font-size: 0.74rem;
            font-weight: 700;
            display: flex;
            justify-content: space-between;
            align-items: center;
            letter-spacing: 0.3px;
        }}
        .wd-tag {{
            background: rgba(255, 255, 255, 0.28);
            backdrop-filter: blur(4px);
            padding: 2px 7px;
            border-radius: 20px;
            font-size: 0.64rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #ffffff;
        }}
        
        .wd-card-body {{
            padding: 12px 14px 10px 14px;
        }}
        .wd-profile-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }}
        .wd-avatar {{
            width: 38px;
            height: 38px;
            border-radius: 50%;
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 0.85rem;
            flex-shrink: 0;
            letter-spacing: 0.5px;
        }}
        .wd-profile-text {{
            overflow: hidden;
        }}
        .wd-name {{
            font-weight: 700;
            font-size: 0.88rem;
            color: #0f172a;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .wd-desig {{
            font-size: 0.74rem;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-top: 1px;
        }}
        
        .wd-meta-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 5px;
            background: #f8fafc;
            padding: 7px 10px;
            border-radius: 8px;
            font-size: 0.70rem;
            color: #475569;
            margin-bottom: 8px;
            border: 1px solid #f1f5f9;
        }}
        .wd-meta-item {{
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .wd-ctc-item {{
            grid-column: span 2;
            color: #059669;
            font-weight: 700;
        }}
        
        .wd-reports-badge {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 4px 9px;
            border-radius: 6px;
            font-size: 0.70rem;
            font-weight: 700;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .wd-reports-badge:hover {{
            filter: brightness(0.95);
            transform: scale(1.01);
        }}
        .wd-toggle-icon {{
            font-size: 0.75rem;
            font-weight: 900;
        }}
        
        /* Node Quick Actions Row */
        .wd-card-actions {{
            display: flex;
            align-items: center;
            gap: 5px;
            padding-top: 5px;
            border-top: 1px dashed #e2e8f0;
        }}
        .wd-btn-intel {{
            flex: 1;
            background: #f1f5f9;
            color: #334155;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 4px 6px;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 3px;
            transition: all 0.15s ease;
        }}
        .wd-btn-intel:hover {{
            background: #6366f1;
            color: #ffffff;
            border-color: #6366f1;
        }}
        .wd-btn-edit-node {{
            flex: 1;
            background: #eef2ff;
            color: #4338ca;
            border: 1px solid #c7d2fe;
            border-radius: 6px;
            padding: 4px 6px;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 3px;
            transition: all 0.15s ease;
        }}
        .wd-btn-edit-node:hover {{
            background: #4338ca;
            color: #ffffff;
            border-color: #4338ca;
            box-shadow: 0 2px 8px rgba(67, 56, 202, 0.2);
        }}
        .wd-btn-move-node {{
            flex: 1;
            background: #fffbeb;
            color: #b45309;
            border: 1px solid #fde68a;
            border-radius: 6px;
            padding: 4px 6px;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 3px;
            transition: all 0.15s ease;
        }}
        .wd-btn-move-node:hover {{
            background: #d97706;
            color: #ffffff;
            border-color: #d97706;
            box-shadow: 0 2px 8px rgba(217, 119, 6, 0.25);
        }}
        .wd-btn-del-node {{
            flex: 0.55;
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
            border-radius: 6px;
            padding: 4px 4px;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s ease;
        }}
        .wd-btn-del-node:hover {{
            background: #dc2626;
            color: #ffffff;
            border-color: #dc2626;
            box-shadow: 0 2px 8px rgba(220, 38, 38, 0.25);
        }}
        
        /* Dedicated Full-Width Footer 'Add Direct Report' Button */
        .wd-card-footer {{
            padding: 6px 12px 10px 12px;
            background: #ffffff;
            border-top: 1px solid #f1f5f9;
        }}
        .wd-btn-footer-add {{
            width: 100%;
            background: #eef2ff;
            color: #4f46e5;
            border: 1px solid #c7d2fe;
            border-radius: 8px;
            padding: 5px 8px;
            font-size: 0.74rem;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
            transition: all 0.18s ease;
        }}
        .wd-btn-footer-add:hover {{
            background: #4338ca;
            color: #ffffff;
            border-color: #4338ca;
            box-shadow: 0 4px 12px rgba(67, 56, 202, 0.25);
        }}
        
        /* Collapsed sub-tree state */
        .wd-collapsed > ul {{
            display: none !important;
        }}
        
        /* Modal Slide-over for Candidate 360 Intel */
        .wd-modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(15, 23, 42, 0.45);
            backdrop-filter: blur(4px);
            z-index: 1000;
            display: none;
            justify-content: flex-end;
        }}
        .wd-drawer {{
            background: #ffffff;
            width: 440px;
            max-width: 90vw;
            height: 100vh;
            box-shadow: -8px 0 32px rgba(15, 23, 42, 0.2);
            display: flex;
            flex-direction: column;
            animation: slideIn 0.25s ease-out;
            overflow-y: auto;
        }}
        @keyframes slideIn {{
            from {{ transform: translateX(100%); }}
            to {{ transform: translateX(0); }}
        }}
        .wd-drawer-header {{
            background: #0f172a;
            color: #ffffff;
            padding: 22px 24px;
            position: relative;
        }}
        .wd-drawer-close {{
            position: absolute;
            top: 18px;
            right: 18px;
            background: rgba(255, 255, 255, 0.15);
            border: none;
            color: #ffffff;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            font-size: 1rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s ease;
        }}
        .wd-drawer-close:hover {{
            background: rgba(255, 255, 255, 0.3);
        }}
        .wd-drawer-body {{
            padding: 20px 24px 40px 24px;
        }}
        .wd-intel-section {{
            margin-bottom: 18px;
            padding-bottom: 14px;
            border-bottom: 1px solid #f1f5f9;
        }}
        .wd-intel-label {{
            font-size: 0.72rem;
            font-weight: 700;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }}
        .wd-intel-value {{
            font-size: 0.95rem;
            font-weight: 600;
            color: #1e293b;
        }}
        .wd-report-sub-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 10px;
            background: #f8fafc;
            border-radius: 8px;
            margin-bottom: 6px;
            border: 1px solid #e2e8f0;
        }}
        .wd-mini-avatar {{
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: #6366f1;
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.72rem;
            font-weight: 800;
        }}
        .wd-btn-detach {{
            background: #fee2e2;
            color: #b91c1c;
            border: 1px solid #fca5a5;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .wd-btn-detach:hover {{
            background: #dc2626;
            color: #ffffff;
        }}

        /* Universal In-Chart Modal Dialog */
        .wd-modal-dialog-container {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(15, 23, 42, 0.5);
            backdrop-filter: blur(5px);
            z-index: 2000;
            display: none;
            align-items: center;
            justify-content: center;
        }}
        .wd-modal-dialog {{
            background: #ffffff;
            border-radius: 18px;
            width: 520px;
            max-width: 92vw;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 20px 48px rgba(15, 23, 42, 0.25);
            padding: 26px 28px;
            animation: modalFadeIn 0.2s ease-out;
            border: 1px solid #e2e8f0;
        }}
        @keyframes modalFadeIn {{
            from {{ opacity: 0; transform: scale(0.95) translateY(10px); }}
            to {{ opacity: 1; transform: scale(1.0) translateY(0); }}
        }}
        .wd-modal-title {{
            font-size: 1.25rem;
            font-weight: 800;
            color: #1e1b4b;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .wd-modal-subtitle {{
            font-size: 0.85rem;
            color: #64748b;
            margin-bottom: 20px;
        }}
        .wd-form-group {{
            margin-bottom: 14px;
        }}
        .wd-form-label {{
            display: block;
            font-size: 0.80rem;
            font-weight: 700;
            color: #334155;
            margin-bottom: 5px;
        }}
        .wd-form-input, .wd-form-select, .wd-form-textarea {{
            width: 100%;
            padding: 9px 12px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            font-size: 0.88rem;
            outline: none;
            transition: all 0.2s ease;
            box-sizing: border-box;
            background: #ffffff;
        }}
        .wd-form-input:focus, .wd-form-select:focus, .wd-form-textarea:focus {{
            border-color: #6366f1;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.18);
        }}
        .wd-form-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }}
        .wd-btn-submit {{
            background: linear-gradient(135deg, #4338ca 0%, #6366f1 100%);
            color: #ffffff;
            border: none;
            padding: 10px 18px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 0.88rem;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
            transition: all 0.2s ease;
            flex: 1;
        }}
        .wd-btn-submit:hover {{
            box-shadow: 0 6px 18px rgba(99, 102, 241, 0.4);
            transform: translateY(-1px);
        }}
        .wd-btn-cancel {{
            background: #f1f5f9;
            color: #475569;
            border: 1px solid #cbd5e1;
            padding: 10px 16px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.88rem;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .wd-btn-cancel:hover {{
            background: #e2e8f0;
            color: #1e293b;
        }}

        /* Move Tabs */
        .wd-tabs-nav {{
            display: flex;
            gap: 6px;
            margin-bottom: 16px;
            background: #f1f5f9;
            padding: 4px;
            border-radius: 10px;
        }}
        .wd-tab-btn {{
            flex: 1;
            padding: 8px 10px;
            border: none;
            background: transparent;
            font-size: 0.82rem;
            font-weight: 700;
            color: #64748b;
            border-radius: 7px;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .wd-tab-btn.active {{
            background: #ffffff;
            color: #4338ca;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
        }}
    </style>
    </head>
    <body>
        <!-- Floating Canvas Controls -->
        <div class="wd-controls-bar">
            <select id="canvasCompanyFilter" class="wd-comp-filter-select" onchange="filterCanvasByCompany(this.value)" title="Switch Company View">
                {comp_options_html}
            </select>
            <input type="text" class="wd-search-input" id="wdSearch" placeholder="🔍 Search in Org Chart..." oninput="searchOrgChart(this.value)">
            <button type="button" class="wd-ctrl-btn" onclick="zoomIn()" title="Zoom In">➕ Zoom</button>
            <button type="button" class="wd-ctrl-btn" onclick="zoomOut()" title="Zoom Out">➖ Zoom</button>
            <span class="wd-zoom-badge" id="zoomBadge">100%</span>
            <button type="button" class="wd-ctrl-btn" onclick="resetView()" title="Reset Pan & Zoom">🎯 Reset</button>
            <button type="button" class="wd-ctrl-btn" onclick="fitToWidth()" title="Fit Width">↔️ Fit</button>
            <button type="button" class="wd-ctrl-btn" onclick="toggleAllSubtrees()" title="Toggle Branches">📂 Toggle</button>
        </div>

        <!-- Canvas Viewport with 2D Pan-and-Zoom -->
        <div class="wd-canvas-viewport" id="viewport">
            <div class="wd-canvas-world" id="world">
                {all_companies_html}
            </div>
        </div>

        <!-- Candidate 360 Intel Slide-Over Modal -->
        <div class="wd-modal-overlay" id="intelModal" onclick="closeIntelModal(event)">
            <div class="wd-drawer" onclick="event.stopPropagation()">
                <div class="wd-drawer-header">
                    <button class="wd-drawer-close" onclick="closeIntelModal()">✕</button>
                    <div style="font-size: 0.75rem; font-weight: 700; color: #93c5fd; text-transform: uppercase; letter-spacing: 0.5px;" id="mLevel">Level</div>
                    <div style="font-size: 1.4rem; font-weight: 700; margin: 4px 0;" id="mName">Candidate Name</div>
                    <div style="font-size: 0.95rem; color: #cbd5e1;" id="mDesig">Designation</div>
                </div>
                <div class="wd-drawer-body">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 18px;">
                        <button class="wd-btn-submit" style="font-size: 0.78rem; padding: 8px 6px;" onclick="closeIntelModal(); if(window.currentIntelData) openAddReportModal(window.currentIntelData.id);">
                            ➕ Add Report
                        </button>
                        <button class="wd-btn-cancel" style="font-size: 0.78rem; padding: 8px 6px; background: #e0e7ff; color: #4338ca; border-color: #c7d2fe; font-weight: 700;" onclick="closeIntelModal(); if(window.currentIntelData) openEditCandidateModal(window.currentIntelData.id);">
                            ✏️ Edit Details
                        </button>
                        <button class="wd-btn-cancel" style="font-size: 0.78rem; padding: 8px 6px; background: #fef3c7; color: #92400e; border-color: #fde68a; font-weight: 700;" onclick="closeIntelModal(); if(window.currentIntelData) openMoveCandidateModal(window.currentIntelData.id);">
                            🚚 Move / Retire
                        </button>
                        <button class="wd-btn-cancel" style="font-size: 0.78rem; padding: 8px 6px; background: #fee2e2; color: #b91c1c; border-color: #fca5a5; font-weight: 700;" onclick="closeIntelModal(); if(window.currentIntelData) openDeleteCandidateModal(window.currentIntelData.id);">
                            🗑️ Delete
                        </button>
                    </div>
                    <div class="wd-intel-section">
                        <div class="wd-intel-label">🏢 Company & Type</div>
                        <div class="wd-intel-value" id="mCompany">Company Name</div>
                    </div>
                    <div class="wd-intel-section">
                        <div class="wd-intel-label">📍 Location & Experience</div>
                        <div class="wd-intel-value" id="mLocExp">Location | Exp</div>
                    </div>
                    <div class="wd-intel-section">
                        <div class="wd-intel-label">💰 Compensation Details</div>
                        <div class="wd-intel-value" style="color: #059669;" id="mCTC">Current CTC</div>
                        <div style="font-size: 0.85rem; color: #475569; margin-top: 4px;" id="mExpCTC">Expected CTC: -</div>
                    </div>
                    <div class="wd-intel-section">
                        <div class="wd-intel-label">📞 Contact & Communication</div>
                        <div class="wd-intel-value" style="font-size: 0.85rem;" id="mContact">Phone / Email</div>
                    </div>
                    <div class="wd-intel-section">
                        <div class="wd-intel-label">💬 Recruiter Remarks & Intel</div>
                        <div style="font-size: 0.88rem; color: #334155; line-height: 1.4;" id="mComments">No notes entered.</div>
                    </div>
                    <div class="wd-intel-section">
                        <div class="wd-intel-label">👥 Direct Reports (<span id="mReportCount">0</span>)</div>
                        <div id="mReportsList" style="margin-top: 6px;">
                            <!-- Populated dynamically in showIntelModal -->
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- In-Chart Modal: Add Direct Report Under Leader -->
        <div class="wd-modal-dialog-container" id="addReportModal" onclick="closeAddReportModal(event)">
            <div class="wd-modal-dialog" onclick="event.stopPropagation()">
                <div class="wd-modal-title">➕ Add Direct Report</div>
                <div class="wd-modal-subtitle">
                    Adding a subordinate reporting directly under <b id="addMgrName" style="color: #4338ca;">Manager</b>
                </div>

                <form onsubmit="submitAddReport(event)">
                    <input type="hidden" id="addReportsToId">
                    <input type="hidden" id="addCompany">
                    <input type="hidden" id="addCompType">

                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; font-size: 0.82rem; color: #475569;">
                        <b>Hierarchy Target:</b> <span id="addMgrDetails">Company</span>
                    </div>

                    <div class="wd-form-group">
                        <label class="wd-form-label">Candidate Full Name *</label>
                        <input type="text" class="wd-form-input" id="addCandName" placeholder="e.g. Ramesh Chandra" required>
                    </div>

                    <div class="wd-form-group">
                        <label class="wd-form-label">Current Designation *</label>
                        <input type="text" class="wd-form-input" id="addCandDesig" placeholder="e.g. General Manager - Production" required>
                    </div>

                    <div class="wd-form-row">
                        <div class="wd-form-group">
                            <label class="wd-form-label">Location / City</label>
                            <input type="text" class="wd-form-input" id="addCandLoc" placeholder="e.g. Mumbai, Maharashtra">
                        </div>
                        <div class="wd-form-group">
                            <label class="wd-form-label">Total Experience</label>
                            <input type="text" class="wd-form-input" id="addCandExp" placeholder="e.g. 12 Years">
                        </div>
                    </div>

                    <div class="wd-form-row">
                        <div class="wd-form-group">
                            <label class="wd-form-label">Current CTC (₹)</label>
                            <input type="number" class="wd-form-input" id="addCandCurrCTC" placeholder="e.g. 3500000">
                        </div>
                        <div class="wd-form-group">
                            <label class="wd-form-label">Expected CTC (₹)</label>
                            <input type="number" class="wd-form-input" id="addCandExpCTC" placeholder="e.g. 4200000">
                        </div>
                    </div>

                    <div class="wd-form-row">
                        <div class="wd-form-group">
                            <label class="wd-form-label">Mobile Number</label>
                            <input type="text" class="wd-form-input" id="addCandContact" placeholder="e.g. 9876543210">
                        </div>
                        <div class="wd-form-group">
                            <label class="wd-form-label">Email ID</label>
                            <input type="email" class="wd-form-input" id="addCandEmail" placeholder="e.g. candidate@example.com">
                        </div>
                    </div>

                    <div class="wd-form-group">
                        <label class="wd-form-label">Recruiter Notes / Intel</label>
                        <textarea class="wd-form-textarea" id="addCandComments" rows="2" placeholder="Key responsibilities, reporting structure nuances, or notice period..."></textarea>
                    </div>

                    <div id="addErrorMsg" style="color: #dc2626; font-size: 0.82rem; margin-bottom: 10px; display: none;"></div>
                    <div id="addSuccessMsg" style="color: #059669; font-size: 0.85rem; font-weight: 700; margin-bottom: 10px; display: none;"></div>

                    <div style="display: flex; gap: 10px; margin-top: 18px;">
                        <button type="submit" class="wd-btn-submit" id="addSubmitBtn">
                            💾 Save Direct Report
                        </button>
                        <button type="button" class="wd-btn-cancel" onclick="closeAddReportModal()">
                            Cancel
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <!-- In-Chart Modal: Edit Candidate Details -->
        <div class="wd-modal-dialog-container" id="editCandModal" onclick="closeEditCandidateModal(event)">
            <div class="wd-modal-dialog" onclick="event.stopPropagation()">
                <div class="wd-modal-title">✏️ Edit Candidate Details</div>
                <div class="wd-modal-subtitle">Update professional profile, reporting manager, or compensation notes.</div>

                <form onsubmit="submitEditCandidate(event)">
                    <input type="hidden" id="editCandId">

                    <div class="wd-form-group">
                        <label class="wd-form-label">Candidate Full Name *</label>
                        <input type="text" class="wd-form-input" id="editCandName" required>
                    </div>

                    <div class="wd-form-group">
                        <label class="wd-form-label">Current Designation *</label>
                        <input type="text" class="wd-form-input" id="editCandDesig" required>
                    </div>

                    <div class="wd-form-row">
                        <div class="wd-form-group">
                            <label class="wd-form-label">Location / City</label>
                            <input type="text" class="wd-form-input" id="editCandLoc">
                        </div>
                        <div class="wd-form-group">
                            <label class="wd-form-label">Total Experience</label>
                            <input type="text" class="wd-form-input" id="editCandExp">
                        </div>
                    </div>

                    <div class="wd-form-row">
                        <div class="wd-form-group">
                            <label class="wd-form-label">Current CTC (₹)</label>
                            <input type="number" class="wd-form-input" id="editCandCurrCTC">
                        </div>
                        <div class="wd-form-group">
                            <label class="wd-form-label">Expected CTC (₹)</label>
                            <input type="number" class="wd-form-input" id="editCandExpCTC">
                        </div>
                    </div>

                    <div class="wd-form-row">
                        <div class="wd-form-group">
                            <label class="wd-form-label">Mobile Number</label>
                            <input type="text" class="wd-form-input" id="editCandContact">
                        </div>
                        <div class="wd-form-group">
                            <label class="wd-form-label">Email ID</label>
                            <input type="email" class="wd-form-input" id="editCandEmail">
                        </div>
                    </div>

                    <div class="wd-form-group">
                        <label class="wd-form-label">Reporting Manager</label>
                        <select class="wd-form-select" id="editCandReportsTo">
                            <!-- Populated dynamically -->
                        </select>
                    </div>

                    <div class="wd-form-group">
                        <label class="wd-form-label">Recruiter Notes / Intel</label>
                        <textarea class="wd-form-textarea" id="editCandComments" rows="2"></textarea>
                    </div>

                    <div id="editErrorMsg" style="color: #dc2626; font-size: 0.82rem; margin-bottom: 10px; display: none;"></div>
                    <div id="editSuccessMsg" style="color: #059669; font-size: 0.85rem; font-weight: 700; margin-bottom: 10px; display: none;"></div>

                    <div style="display: flex; gap: 10px; margin-top: 18px;">
                        <button type="submit" class="wd-btn-submit" id="editSubmitBtn">
                            💾 Save Changes
                        </button>
                        <button type="button" class="wd-btn-cancel" onclick="closeEditCandidateModal()">
                            Cancel
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <!-- In-Chart Modal: Delete Candidate Confirmation -->
        <div class="wd-modal-dialog-container" id="deleteCandModal" onclick="closeDeleteCandidateModal(event)">
            <div class="wd-modal-dialog" onclick="event.stopPropagation()">
                <div class="wd-modal-title" style="color: #b91c1c;">🗑️ Delete Candidate Record</div>
                <div class="wd-modal-subtitle">Are you sure you want to remove <b id="delCandTitle" style="color: #1e1b4b;">Candidate</b> from Talent Mapping?</div>

                <input type="hidden" id="delCandId">
                <input type="hidden" id="delParentId">

                <div id="delSubReportsAlert" style="background: #fffbeb; border: 1.5px solid #fde68a; border-radius: 10px; padding: 12px 14px; margin-bottom: 16px; display: none;">
                    <div style="font-weight: 700; font-size: 0.86rem; color: #92400e; margin-bottom: 4px;">
                        ⚠️ Direct Reports Detected (<span id="delSubCount">0</span>)
                    </div>
                    <div style="font-size: 0.80rem; color: #78350f; line-height: 1.4;">
                        This candidate currently manages subordinates. Choose how to handle their direct reports:
                    </div>
                    <div style="margin-top: 8px; display: flex; flex-direction: column; gap: 6px; font-size: 0.80rem;">
                        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; color: #78350f;">
                            <input type="radio" name="delStrategy" value="reassign" checked>
                            <span><b>Reassign to Grandparent Manager:</b> <span id="delReassignDesc">Reports will move up.</span></span>
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; color: #78350f;">
                            <input type="radio" name="delStrategy" value="root">
                            <span><b>Promote to Top-Level Leaders:</b> Reports will become independent root heads.</span>
                        </label>
                    </div>
                </div>

                <div id="delErrorMsg" style="color: #dc2626; font-size: 0.82rem; margin-bottom: 10px; display: none;"></div>

                <div style="display: flex; gap: 10px; margin-top: 18px;">
                    <button type="button" class="wd-btn-submit" id="delConfirmBtn" style="background: linear-gradient(135deg, #b91c1c 0%, #dc2626 100%);" onclick="executeDeleteCandidate()">
                        🗑️ Yes, Delete Record
                    </button>
                    <button type="button" class="wd-btn-cancel" onclick="closeDeleteCandidateModal()">
                        Cancel
                    </button>
                </div>
            </div>
        </div>

        <!-- In-Chart Modal: Move / Transfer / Retire Candidate -->
        <div class="wd-modal-dialog-container" id="moveCandModal" onclick="closeMoveCandidateModal(event)">
            <div class="wd-modal-dialog" onclick="event.stopPropagation()">
                <div class="wd-modal-title" style="color: #b45309;">🚚 Move & Lifecycle Actions</div>
                <div class="wd-modal-subtitle" id="moveCandSummary">Candidate Name • Role</div>

                <!-- Tabs: Company Move, Manager Move, Retire / Ex-Employee -->
                <div class="wd-tabs-nav">
                    <button type="button" class="wd-tab-btn active" id="tabBtnComp" onclick="switchMoveTab('company')">🏢 Move to Company</button>
                    <button type="button" class="wd-tab-btn" id="tabBtnMgr" onclick="switchMoveTab('manager')">👑 Reassign Manager</button>
                    <button type="button" class="wd-tab-btn" id="tabBtnRetire" onclick="switchMoveTab('retire')">🏖️ Retired / Left</button>
                </div>

                <form onsubmit="submitMoveCandidate(event)">
                    <input type="hidden" id="moveCandId">
                    <input type="hidden" id="moveActiveTab" value="company">

                    <!-- Tab 1: Company Transfer -->
                    <div id="moveTabCompany">
                        <div class="wd-form-group">
                            <label class="wd-form-label">New Company Type</label>
                            <select class="wd-form-select" id="moveNewCompType" onchange="handleCompTypeChange(this, 'moveNewCompTypeCustom')">
                                <!-- Populated dynamically from ALL_COMPANY_TYPES -->
                            </select>
                            <input type="text" class="wd-form-input" id="moveNewCompTypeCustom" placeholder="Type new company sector (e.g. Agritech, Solar...)" style="display: none; margin-top: 6px;">
                        </div>
                        <div class="wd-form-group">
                            <label class="wd-form-label">New Company Name *</label>
                            <input type="text" class="wd-form-input" id="moveNewCompName" placeholder="e.g. PI Industries">
                        </div>
                        <div class="wd-form-group">
                            <label class="wd-form-label">New Designation in Company</label>
                            <input type="text" class="wd-form-input" id="moveNewDesig" placeholder="e.g. Chief Operating Officer">
                        </div>
                        <div style="font-size: 0.78rem; color: #64748b; margin-top: 4px; line-height: 1.4;">
                            ℹ️ Direct reports in the current company will automatically be reassigned to this candidate's manager.
                        </div>
                    </div>

                    <!-- Tab 2: Reassign Manager -->
                    <div id="moveTabManager" style="display: none;">
                        <div class="wd-form-group">
                            <label class="wd-form-label">Select New Reporting Manager</label>
                            <select class="wd-form-select" id="moveNewReportsTo">
                                <!-- Populated dynamically -->
                            </select>
                        </div>
                        <div style="font-size: 0.78rem; color: #64748b; margin-top: 4px; line-height: 1.4;">
                            ℹ️ Candidate and their subordinate subtree will be re-anchored under the newly chosen manager.
                        </div>
                    </div>

                    <!-- Tab 3: Retired / Left Market -->
                    <div id="moveTabRetire" style="display: none;">
                        <div class="wd-form-group">
                            <label class="wd-form-label">Lifecycle Status</label>
                            <select class="wd-form-select" id="moveRetireStatus">
                                <option value="Retired">🏖️ Retired from Active Workforce</option>
                                <option value="Career Break">⏸️ Sabbatical / Career Break</option>
                                <option value="Relocated Abroad">✈️ Relocated Abroad / International</option>
                                <option value="Alumni">🎓 Company Alumni (Former Employee)</option>
                            </select>
                        </div>
                        <div class="wd-form-group">
                            <label class="wd-form-label">Notes & Exit Intel</label>
                            <textarea class="wd-form-textarea" id="moveRetireNotes" rows="2" placeholder="e.g. Retired in Jan 2025. Contactable for advisory roles."></textarea>
                        </div>
                    </div>

                    <div id="moveErrorMsg" style="color: #dc2626; font-size: 0.82rem; margin-top: 10px; display: none;"></div>
                    <div id="moveSuccessMsg" style="color: #059669; font-size: 0.85rem; font-weight: 700; margin-top: 10px; display: none;"></div>
                    <div style="display: flex; gap: 10px; margin-top: 16px;">
                        <button type="submit" class="wd-btn-submit" id="moveSubmitBtn" style="background: linear-gradient(135deg, #b45309 0%, #d97706 100%);">
                            💾 Save Movement
                        </button>
                        <button type="button" class="wd-btn-cancel" onclick="closeMoveCandidateModal()">
                            Cancel
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <script>
            const SUPABASE_URL = "{SUPABASE_URL}";
            const SUPABASE_KEY = "{SUPABASE_KEY}";
            const CURRENT_USER_ID = {current_user_id};
            const CURRENT_USER_NAME = {current_user_name};
            const ALL_RECORDS = {current_comp_records_json};
            const ALL_COMPANY_TYPES = {all_comp_types_json};
            window.currentIntelData = null;

            // ==========================================
            // 🎯 2D TRANSFORM PAN & ZOOM ENGINE (60 FPS)
            // ==========================================
                        let scale = 1.0;
            let panX = 0;
            let panY = 0;
            let isPanning = false;
            let startMouseX = 0;
            let startMouseY = 0;
            let startPanX = 0;
            let startPanY = 0;
            let hasDragged = false;

            const viewport = document.getElementById("viewport");
            const world = document.getElementById("world");
            const zoomBadge = document.getElementById("zoomBadge");

            // 🛑 Restrict vertical panning past the top Leader / Company Header
            const MAX_PAN_Y = 0;

            function clampPan() {{
                // Lock top boundary: prevent dragging down to reveal blank void above top leader
                if (panY > MAX_PAN_Y) {{
                    panY = MAX_PAN_Y;
                }}
                // Lock bottom boundary: allow full downward scrolling to bottom nodes
                if (world && viewport) {{
                    const worldH = world.offsetHeight * scale;
                    const viewH = viewport.clientHeight;
                    const minPanY = Math.min(0, viewH - worldH - 40);
                    if (panY < minPanY) {{
                        panY = minPanY;
                    }}
                }}
            }}

            function updateTransform() {{
                clampPan();
                world.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
                zoomBadge.textContent = `${{Math.round(scale * 100)}}%`;
            }}

            // Mouse wheel handles smooth zoom & 2D trackpad panning
            viewport.addEventListener("wheel", (e) => {{
                e.preventDefault();
                if (e.ctrlKey || e.metaKey) {{
                    if (e.deltaY < 0) {{
                        zoomIn();
                    }} else {{
                        zoomOut();
                    }}
                }} else {{
                    panX -= e.deltaX;
                    panY -= e.deltaY;
                    updateTransform();
                }}
            }}, {{ passive: false }});

            // Mouse Down -> Start Canvas Pan
            viewport.addEventListener("mousedown", (e) => {{
                // Ignore clicks on buttons, form controls, top toolbar, or active modal dialogs
                if (e.target.closest("button") || e.target.closest("input") || e.target.closest("select") || e.target.closest(".wd-controls-bar") || e.target.closest(".wd-modal-overlay") || e.target.closest(".wd-modal-dialog-container")) {{
                    return;
                }}
                isPanning = true;
                hasDragged = false;
                startMouseX = e.clientX;
                startMouseY = e.clientY;
                startPanX = panX;
                startPanY = panY;
                viewport.classList.add("is-dragging");
            }});

            window.addEventListener("mousemove", (e) => {{
                if (!isPanning) return;
                const dx = e.clientX - startMouseX;
                const dy = e.clientY - startMouseY;
                if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {{
                    hasDragged = true;
                }}
                panX = startPanX + dx;
                panY = startPanY + dy;
                updateTransform();
            }});

            window.addEventListener("mouseup", () => {{
                if (isPanning) {{
                    isPanning = false;
                    viewport.classList.remove("is-dragging");
                }}
            }});

            // Touch support for touchscreen / trackpads
            let touchStartX = 0;
            let touchStartY = 0;
            viewport.addEventListener("touchstart", (e) => {{
                if (e.touches.length === 1) {{
                    const touch = e.touches[0];
                    if (touch.target.closest("button") || touch.target.closest("input") || touch.target.closest("select") || touch.target.closest(".wd-controls-bar") || touch.target.closest(".wd-modal-overlay") || touch.target.closest(".wd-modal-dialog-container")) {{
                        return;
                    }}
                    isPanning = true;
                    hasDragged = false;
                    touchStartX = touch.clientX;
                    touchStartY = touch.clientY;
                    startPanX = panX;
                    startPanY = panY;
                }}
            }}, {{ passive: true }});

            viewport.addEventListener("touchmove", (e) => {{
                if (!isPanning || e.touches.length !== 1) return;
                const touch = e.touches[0];
                const dx = touch.clientX - touchStartX;
                const dy = touch.clientY - touchStartY;
                if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {{
                    hasDragged = true;
                }}
                panX = startPanX + dx;
                panY = startPanY + dy;
                updateTransform();
            }}, {{ passive: true }});

            viewport.addEventListener("touchend", () => {{
                isPanning = false;
            }});

            function zoomIn() {{
                scale = Math.min(2.0, scale * 1.15);
                updateTransform();
            }}

            function zoomOut() {{
                scale = Math.max(0.3, scale / 1.15);
                updateTransform();
            }}

            function resetView() {{
                scale = 1.0;
                const treeEl = world.querySelector(".wd-tree");
                if (treeEl && viewport) {{
                    const treeW = treeEl.offsetWidth;
                    const viewW = viewport.clientWidth;
                    panX = Math.max(30, (viewW - treeW) / 2);
                    panY = 0;
                }} else {{
                    panX = 40;
                    panY = 0;
                }}
                updateTransform();
            }}

            function fitToWidth() {{
                const treeEl = world.querySelector(".wd-tree");
                if (treeEl && viewport) {{
                    const treeW = treeEl.offsetWidth;
                    const viewW = viewport.clientWidth - 60;
                    if (treeW > 0 && viewW > 0) {{
                        scale = Math.min(1.0, Math.max(0.32, viewW / treeW));
                        panX = 30;
                        panY = 0;
                        updateTransform();
                    }}
                }}
            }}

            // Company Filter in Canvas Toolbar
            function filterCanvasByCompany(compName) {{
                const companyItems = document.querySelectorAll(".wd-company-root-item");
                companyItems.forEach(item => {{
                    const itemComp = item.getAttribute("data-company");
                    if (compName === "__ALL__" || itemComp === compName) {{
                        item.style.display = "";
                    }} else {{
                        item.style.display = "none";
                    }}
                }});
                setTimeout(resetView, 60);
            }}

            // Search in Org Chart
            function searchOrgChart(query) {{
                query = query.toLowerCase().trim();
                const cards = document.querySelectorAll(".wd-card, .wd-company-card");
                let firstMatch = null;
                cards.forEach(card => {{
                    if (!query) {{
                        card.classList.remove("highlighted");
                    }} else {{
                        const text = card.textContent.toLowerCase();
                        if (text.includes(query)) {{
                            card.classList.add("highlighted");
                            if (!firstMatch) firstMatch = card;
                        }} else {{
                            card.classList.remove("highlighted");
                        }}
                    }}
                }});
                if (firstMatch) {{
                    firstMatch.scrollIntoView({{ behavior: "smooth", block: "center", inline: "center" }});
                }}
            }}

            // Expand / Collapse Subtree
            function toggleNodeChildren(badgeElement) {{
                const li = badgeElement.closest("li");
                li.classList.toggle("wd-collapsed");
                const icon = badgeElement.querySelector(".wd-toggle-icon");
                if (li.classList.contains("wd-collapsed")) {{
                    icon.textContent = "▸";
                }} else {{
                    icon.textContent = "▾";
                }}
            }}

            let allCollapsed = false;
            function toggleAllSubtrees() {{
                allCollapsed = !allCollapsed;
                document.querySelectorAll(".wd-node-item").forEach(li => {{
                    if (li.querySelector("ul")) {{
                        if (allCollapsed) {{
                            li.classList.add("wd-collapsed");
                            const icon = li.querySelector(".wd-toggle-icon");
                            if (icon) icon.textContent = "▸";
                        }} else {{
                            li.classList.remove("wd-collapsed");
                            const icon = li.querySelector(".wd-toggle-icon");
                            if (icon) icon.textContent = "▾";
                        }}
                    }}
                }});
            }}

            // Helper to get full candidate object by ID
            function getNodeData(param) {{
                if (typeof param === "object" && param !== null) {{
                    return param;
                }}
                const id = parseInt(param);
                const rec = ALL_RECORDS.find(r => r.mapping_id == id);
                if (!rec) return null;

                const count = ALL_RECORDS.filter(r => r.reports_to_id == id).length;
                return {{
                    id: rec.mapping_id,
                    name: rec.candidate_name || "Candidate",
                    designation: rec.designation || "Role",
                    company: rec.company_name || "",
                    type: rec.company_type || "Chemicals",
                    location: rec.location || "N/A",
                    experience: rec.experience || "N/A",
                    current_ctc: rec.current_ctc ? `₹ ${{parseFloat(rec.current_ctc).toLocaleString()}}` : "Not Disclosed",
                    expected_ctc: rec.expected_ctc ? `₹ ${{parseFloat(rec.expected_ctc).toLocaleString()}}` : "N/A",
                    current_ctc_num: rec.current_ctc ? parseFloat(rec.current_ctc) : null,
                    expected_ctc_num: rec.expected_ctc ? parseFloat(rec.expected_ctc) : null,
                    contact: rec.contact_number || "",
                    email: rec.email_id || "",
                    comments: rec.comments || "",
                    reports_to_id: rec.reports_to_id,
                    reports_count: count
                }};
            }}

            // Candidate 360 Intel Modal
            function showIntelModal(param) {{
                const data = getNodeData(param);
                if (!data) return;
                window.currentIntelData = data;

                document.getElementById("mLevel").textContent = data.level || "Candidate";
                document.getElementById("mName").textContent = data.name;
                document.getElementById("mDesig").textContent = `💼 ${{data.designation}}`;
                document.getElementById("mCompany").textContent = `🏢 ${{data.company}} (${{data.type}})`;
                document.getElementById("mLocExp").textContent = `📍 ${{data.location}}  |  ⏱️ ${{data.experience}}`;
                document.getElementById("mCTC").textContent = `💰 Current: ${{data.current_ctc}}`;
                document.getElementById("mExpCTC").textContent = `🎯 Expected: ${{data.expected_ctc}}`;
                
                const cleanPhone = (data.contact || "").toString().replace(/\\.0+$/, "");
                const phoneHtml = cleanPhone && cleanPhone !== "N/A" ? `<a href="tel:${{cleanPhone}}" style="color: #6366f1; text-decoration: none;">📞 ${{cleanPhone}}</a>` : `<span>📞 Not Available</span>`;
                const emailHtml = data.email && data.email !== "N/A" ? `<a href="mailto:${{data.email}}" style="color: #6366f1; text-decoration: none;">✉️ ${{data.email}}</a>` : `<span>✉️ Not Available</span>`;
                document.getElementById("mContact").innerHTML = `${{phoneHtml}}<br>${{emailHtml}}`;
                
                document.getElementById("mComments").textContent = data.comments || "No specific comments recorded.";
                
                // Populate direct reports list
                const subReports = ALL_RECORDS.filter(r => r.reports_to_id == data.id);
                document.getElementById("mReportCount").textContent = subReports.length;
                const reportsContainer = document.getElementById("mReportsList");
                reportsContainer.innerHTML = "";
                if (subReports.length === 0) {{
                    reportsContainer.innerHTML = '<div style="font-size: 0.8rem; color: #94a3b8; font-style: italic; padding: 4px 0;">No direct reports currently mapped under this leader.</div>';
                }} else {{
                    subReports.forEach(r => {{
                        const row = document.createElement("div");
                        row.className = "wd-report-sub-item";
                        row.innerHTML = `
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div class="wd-mini-avatar">${{getInitials(r.candidate_name)}}</div>
                                <div>
                                    <div style="font-weight: 700; font-size: 0.84rem; color: #1e1b4b;">${{r.candidate_name}}</div>
                                    <div style="font-size: 0.74rem; color: #64748b;">${{r.designation}}</div>
                                </div>
                            </div>
                            <button type="button" class="wd-btn-detach" onclick="detachDirectReport(${{r.mapping_id}}, ${{data.id}})" title="Detach from this manager (Make Root)">✂️ Detach</button>
                        `;
                        reportsContainer.appendChild(row);
                    }});
                }}

                document.getElementById("intelModal").style.display = "flex";
            }}

            function closeIntelModal(e) {{
                document.getElementById("intelModal").style.display = "none";
            }}

            async function detachDirectReport(subordinateId, managerId) {{
                if (!confirm("Are you sure you want to detach this direct report? They will become an independent top-level root candidate.")) {{
                    return;
                }}

                try {{
                    const response = await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping?mapping_id=eq.${{subordinateId}}`, {{
                        method: "PATCH",
                        headers: {{
                            "apikey": SUPABASE_KEY,
                            "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                            "Content-Type": "application/json",
                            "Prefer": "return=representation"
                        }},
                        body: JSON.stringify({{
                            reports_to_id: null,
                            updated_on: new Date().toISOString()
                        }})
                    }});

                    if (!response.ok) {{
                        const errText = await response.text();
                        throw new Error(`Failed to detach: ${{errText}}`);
                    }}

                    // Move subordinate <li> in DOM
                    const subLi = document.getElementById("node-" + subordinateId);
                    const treeRootUl = document.querySelector(".wd-tree > ul");
                    if (subLi && treeRootUl) {{
                        treeRootUl.appendChild(subLi);
                        const headerSpan = subLi.querySelector(".wd-card-header span");
                        if (headerSpan) headerSpan.textContent = "👑 Level 1";
                    }}

                    // Update ALL_RECORDS
                    const subRec = ALL_RECORDS.find(r => r.mapping_id == subordinateId);
                    if (subRec) {{
                        subRec.reports_to_id = null;
                    }}

                    // Refresh 360 modal list if open
                    if (window.currentIntelData && window.currentIntelData.id == managerId) {{
                        showIntelModal(managerId);
                    }}

                    showToast("✂️ Direct report unlinked! Promoted to Top-Level Leader.");
                }} catch (err) {{
                    alert(err.message || "Failed to detach direct report.");
                }}
            }}

            // Delete Candidate Modal Functions
            let candidateToDelete = null;

            function openDeleteCandidateModal(param) {{
                const nodeData = getNodeData(param);
                if (!nodeData) return;
                candidateToDelete = nodeData;

                document.getElementById("delCandId").value = nodeData.id;
                document.getElementById("delParentId").value = nodeData.reports_to_id || "";
                document.getElementById("delCandTitle").textContent = `${{nodeData.name}} (${{nodeData.designation}})`;

                const subReports = ALL_RECORDS.filter(r => r.reports_to_id == nodeData.id);
                const alertBox = document.getElementById("delSubReportsAlert");
                if (subReports.length > 0) {{
                    alertBox.style.display = "block";
                    document.getElementById("delSubCount").textContent = subReports.length;
                    
                    const parentRec = ALL_RECORDS.find(r => r.mapping_id == nodeData.reports_to_id);
                    const parentName = parentRec ? parentRec.candidate_name : "Top-Level Root";
                    document.getElementById("delReassignDesc").textContent = `Reports will now report to ${{parentName}}.`;
                }} else {{
                    alertBox.style.display = "none";
                }}

                document.getElementById("delErrorMsg").style.display = "none";
                const btn = document.getElementById("delConfirmBtn");
                btn.disabled = false;
                btn.textContent = "🗑️ Yes, Delete Record";

                document.getElementById("deleteCandModal").style.display = "flex";
            }}

            function closeDeleteCandidateModal(e) {{
                document.getElementById("deleteCandModal").style.display = "none";
            }}

            async function executeDeleteCandidate() {{
                if (!candidateToDelete) return;
                const id = parseInt(document.getElementById("delCandId").value);
                const parentIdVal = document.getElementById("delParentId").value;
                const parentId = parentIdVal ? parseInt(parentIdVal) : null;
                const btn = document.getElementById("delConfirmBtn");
                const errorDiv = document.getElementById("delErrorMsg");
                errorDiv.style.display = "none";

                btn.disabled = true;
                btn.textContent = "Deleting Record...";

                const subReports = ALL_RECORDS.filter(r => r.reports_to_id == id);
                const strategyRadio = document.querySelector('input[name="delStrategy"]:checked');
                const strategy = strategyRadio ? strategyRadio.value : "reassign";

                try {{
                    // Handle direct reports if any exist
                    if (subReports.length > 0) {{
                        const targetReportsTo = (strategy === "reassign") ? parentId : null;
                        const patchRes = await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping?reports_to_id=eq.${{id}}`, {{
                            method: "PATCH",
                            headers: {{
                                "apikey": SUPABASE_KEY,
                                "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                                "Content-Type": "application/json",
                                "Prefer": "return=representation"
                            }},
                            body: JSON.stringify({{
                                reports_to_id: targetReportsTo,
                                updated_on: new Date().toISOString()
                            }})
                        }});

                        if (!patchRes.ok) {{
                            const errText = await patchRes.text();
                            throw new Error(`Failed to update direct reports: ${{errText}}`);
                        }}

                        // Reparent DOM children
                        const currentLi = document.getElementById("node-" + id);
                        const childrenUl = currentLi ? currentLi.querySelector(":scope > ul") : null;
                        if (childrenUl) {{
                            const targetUl = targetReportsTo ? (document.getElementById("node-" + targetReportsTo)?.querySelector(":scope > ul") || document.querySelector(".wd-tree > ul")) : document.querySelector(".wd-tree > ul");
                            if (targetUl) {{
                                while (childrenUl.firstChild) {{
                                    targetUl.appendChild(childrenUl.firstChild);
                                }}
                            }}
                        }}

                        // Update local ALL_RECORDS for subordinates
                        subReports.forEach(r => {{
                            r.reports_to_id = targetReportsTo;
                        }});
                    }}

                    // Delete the candidate record
                    const delRes = await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping?mapping_id=eq.${{id}}`, {{
                        method: "DELETE",
                        headers: {{
                            "apikey": SUPABASE_KEY,
                            "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                            "Content-Type": "application/json"
                        }}
                    }});

                    if (!delRes.ok) {{
                        const errText = await delRes.text();
                        throw new Error(`Failed to delete candidate: ${{errText}}`);
                    }}

                    // Remove node from DOM
                    const nodeLi = document.getElementById("node-" + id);
                    if (nodeLi) {{
                        nodeLi.remove();
                    }}

                    // Update parent's badge count
                    if (parentId) {{
                        const parentLi = document.getElementById("node-" + parentId);
                        if (parentLi) {{
                            const pBadge = parentLi.querySelector(":scope > .wd-card .wd-reports-badge");
                            const pUl = parentLi.querySelector(":scope > ul");
                            const pCount = pUl ? pUl.children.length : 0;
                            if (pBadge) {{
                                if (pCount > 0) {{
                                    pBadge.innerHTML = `👥 ${{pCount}} Direct Reports <span class="wd-toggle-icon">▾</span>`;
                                }} else {{
                                    pBadge.remove();
                                }}
                            }}
                        }}
                    }}

                    // Remove from ALL_RECORDS
                    const idx = ALL_RECORDS.findIndex(r => r.mapping_id == id);
                    if (idx !== -1) {{
                        ALL_RECORDS.splice(idx, 1);
                    }}

                    closeDeleteCandidateModal();
                    closeIntelModal();
                    showToast(`🗑️ Deleted ${{candidateToDelete.name}} from Talent Mapping`);
                }} catch (err) {{
                    errorDiv.textContent = err.message || "Failed to delete record.";
                    errorDiv.style.display = "block";
                    btn.disabled = false;
                    btn.textContent = "🗑️ Yes, Delete Record";
                }}
            }}

            // Company Type Selector Helpers
            function populateCompTypeSelect(selectId, selectedValue) {{
                const select = document.getElementById(selectId);
                if (!select) return;
                select.innerHTML = "";
                ALL_COMPANY_TYPES.forEach(t => {{
                    const opt = document.createElement("option");
                    opt.value = t;
                    opt.textContent = t;
                    if (t.toLowerCase() === (selectedValue || "").toLowerCase()) {{
                        opt.selected = true;
                    }}
                    select.appendChild(opt);
                }});
                const customOpt = document.createElement("option");
                customOpt.value = "__custom__";
                customOpt.textContent = "➕ Add New Company Type...";
                select.appendChild(customOpt);
            }}

            function handleCompTypeChange(selectEl, customInputId) {{
                const customInput = document.getElementById(customInputId);
                if (!customInput) return;
                if (selectEl.value === "__custom__") {{
                    customInput.style.display = "block";
                    customInput.focus();
                }} else {{
                    customInput.style.display = "none";
                    customInput.value = "";
                }}
            }}

            function getEffectiveCompType(selectId, customInputId) {{
                const select = document.getElementById(selectId);
                const customInput = document.getElementById(customInputId);
                if (select && select.value === "__custom__") {{
                    return (customInput ? customInput.value.trim() : "") || "Others";
                }}
                return (select ? select.value : "") || "Chemicals";
            }}

            // Move / Transfer Candidate Modal Functions
            let candidateToMove = null;

            function switchMoveTab(tabName) {{
                document.getElementById("moveActiveTab").value = tabName;
                document.getElementById("tabBtnComp").className = tabName === "company" ? "wd-tab-btn active" : "wd-tab-btn";
                document.getElementById("tabBtnMgr").className = tabName === "manager" ? "wd-tab-btn active" : "wd-tab-btn";
                document.getElementById("tabBtnRetire").className = tabName === "retire" ? "wd-tab-btn active" : "wd-tab-btn";

                document.getElementById("moveTabCompany").style.display = tabName === "company" ? "block" : "none";
                document.getElementById("moveTabManager").style.display = tabName === "manager" ? "block" : "none";
                document.getElementById("moveTabRetire").style.display = tabName === "retire" ? "block" : "none";
            }}

            function openMoveCandidateModal(param) {{
                const nodeData = getNodeData(param);
                if (!nodeData) return;
                candidateToMove = nodeData;

                document.getElementById("moveCandId").value = nodeData.id;
                document.getElementById("moveCandSummary").textContent = `👤 ${{nodeData.name}} • 💼 ${{nodeData.designation}}`;
                
                populateCompTypeSelect("moveNewCompType", nodeData.type || "Chemicals");
                document.getElementById("moveNewCompTypeCustom").style.display = "none";
                document.getElementById("moveNewCompTypeCustom").value = "";
                document.getElementById("moveNewCompName").value = "";
                document.getElementById("moveNewDesig").value = nodeData.designation || "";
                document.getElementById("moveRetireNotes").value = "";

                // Populate Manager Dropdown in Move modal with company indicators
                const mgrSelect = document.getElementById("moveNewReportsTo");
                mgrSelect.innerHTML = '<option value="">None (Top-Level Leader / Root)</option>';
                ALL_RECORDS.forEach(rec => {{
                    if (rec.mapping_id != nodeData.id) {{
                        const opt = document.createElement("option");
                        opt.value = rec.mapping_id;
                        const compTag = rec.company_name ? ` • 🏢 ${{rec.company_name}}` : '';
                        opt.textContent = `👤 ${{rec.candidate_name}} (${{rec.designation}})${{compTag}}`;
                        if (rec.mapping_id == nodeData.reports_to_id) {{
                            opt.selected = true;
                        }}
                        mgrSelect.appendChild(opt);
                    }}
                }});

                switchMoveTab("company");
                document.getElementById("moveErrorMsg").style.display = "none";
                document.getElementById("moveSuccessMsg").style.display = "none";
                const btn = document.getElementById("moveSubmitBtn");
                btn.disabled = false;
                btn.textContent = "💾 Save Movement";

                document.getElementById("moveCandModal").style.display = "flex";
            }}

            function closeMoveCandidateModal(e) {{
                document.getElementById("moveCandModal").style.display = "none";
            }}

            async function submitMoveCandidate(event) {{
                event.preventDefault();
                if (!candidateToMove) return;

                const id = parseInt(document.getElementById("moveCandId").value);
                const activeTab = document.getElementById("moveActiveTab").value;
                const btn = document.getElementById("moveSubmitBtn");
                const errorDiv = document.getElementById("moveErrorMsg");
                const successDiv = document.getElementById("moveSuccessMsg");
                errorDiv.style.display = "none";
                successDiv.style.display = "none";

                btn.disabled = true;
                btn.textContent = "Saving Movement...";

                try {{
                    if (activeTab === "company") {{
                        const newCompType = getEffectiveCompType("moveNewCompType", "moveNewCompTypeCustom");
                        const newCompName = document.getElementById("moveNewCompName").value.trim();
                        const newDesig = document.getElementById("moveNewDesig").value.trim() || candidateToMove.designation;
                        if (!newCompName) {{
                            throw new Error("Please enter destination company name.");
                        }}

                        // Reassign direct reports to grandparent
                        const subReports = ALL_RECORDS.filter(r => r.reports_to_id == id);
                        if (subReports.length > 0) {{
                            await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping?reports_to_id=eq.${{id}}`, {{
                                method: "PATCH",
                                headers: {{
                                    "apikey": SUPABASE_KEY,
                                    "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                                    "Content-Type": "application/json"
                                }},
                                body: JSON.stringify({{ reports_to_id: candidateToMove.reports_to_id || null }})
                            }});
                        }}

                        // Transfer candidate to new company
                        const res = await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping?mapping_id=eq.${{id}}`, {{
                            method: "PATCH",
                            headers: {{
                                "apikey": SUPABASE_KEY,
                                "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                                "Content-Type": "application/json",
                                "Prefer": "return=representation"
                            }},
                            body: JSON.stringify({{
                                company_type: newCompType,
                                company_name: newCompName,
                                designation: newDesig,
                                reports_to_id: null,
                                updated_on: new Date().toISOString()
                            }})
                        }});

                        if (!res.ok) {{
                            const errText = await res.text();
                            throw new Error(`Failed to move company: ${{errText}}`);
                        }}

                        // Remove from DOM since transferred
                        const nodeLi = document.getElementById("node-" + id);
                        if (nodeLi) nodeLi.remove();

                        // Remove from local ALL_RECORDS
                        const idx = ALL_RECORDS.findIndex(r => r.mapping_id == id);
                        if (idx !== -1) ALL_RECORDS.splice(idx, 1);

                        successDiv.textContent = `🎉 Successfully transferred ${{candidateToMove.name}} to ${{newCompName}}!`;
                        successDiv.style.display = "block";

                        setTimeout(() => {{
                            closeMoveCandidateModal();
                            closeIntelModal();
                            showToast(`🚚 Transferred ${{candidateToMove.name}} to ${{newCompName}}`);
                        }}, 500);

                    }} else if (activeTab === "manager") {{
                        const newReportsToVal = document.getElementById("moveNewReportsTo").value;
                        const newReportsToId = newReportsToVal ? parseInt(newReportsToVal) : null;

                        const targetMgr = ALL_RECORDS.find(r => r.mapping_id == newReportsToId);
                        const updatePayload = {{
                            reports_to_id: newReportsToId,
                            updated_on: new Date().toISOString()
                        }};
                        if (targetMgr && targetMgr.company_name && targetMgr.company_name !== candidateToMove.company) {{
                            updatePayload.company_name = targetMgr.company_name;
                            updatePayload.company_type = targetMgr.company_type || candidateToMove.type;
                        }}

                        const res = await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping?mapping_id=eq.${{id}}`, {{
                            method: "PATCH",
                            headers: {{
                                "apikey": SUPABASE_KEY,
                                "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                                "Content-Type": "application/json",
                                "Prefer": "return=representation"
                            }},
                            body: JSON.stringify(updatePayload)
                        }});

                        if (!res.ok) {{
                            const errText = await res.text();
                            throw new Error(`Failed to reassign manager: ${{errText}}`);
                        }}

                        // Move node in DOM
                        const nodeLi = document.getElementById("node-" + id);
                        if (nodeLi) {{
                            if (newReportsToId) {{
                                const parentLi = document.getElementById("node-" + newReportsToId);
                                if (parentLi) {{
                                    let pUl = parentLi.querySelector(":scope > ul");
                                    if (!pUl) {{
                                        pUl = document.createElement("ul");
                                        parentLi.appendChild(pUl);
                                    }}
                                    pUl.appendChild(nodeLi);
                                }}
                            }} else {{
                                const topUl = document.querySelector(".wd-tree > ul");
                                if (topUl) topUl.appendChild(nodeLi);
                            }}
                        }}

                        // Update ALL_RECORDS
                        const localRec = ALL_RECORDS.find(r => r.mapping_id == id);
                        if (localRec) localRec.reports_to_id = newReportsToId;

                        successDiv.textContent = "✅ Reporting line reassigned!";
                        successDiv.style.display = "block";

                        setTimeout(() => {{
                            closeMoveCandidateModal();
                            closeIntelModal();
                            showToast(`👑 Reassigned reporting manager for ${{candidateToMove.name}}`);
                        }}, 450);

                    }} else if (activeTab === "retire") {{
                        const statusVal = document.getElementById("moveRetireStatus").value;
                        const notes = document.getElementById("moveRetireNotes").value.trim();
                        const updatedComments = `[${{statusVal.toUpperCase()}}] ${{notes ? notes + ' | ' : ''}}${{candidateToMove.comments || ''}}`;

                        // Reassign direct reports to grandparent
                        const subReports = ALL_RECORDS.filter(r => r.reports_to_id == id);
                        if (subReports.length > 0) {{
                            await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping?reports_to_id=eq.${{id}}`, {{
                                method: "PATCH",
                                headers: {{
                                    "apikey": SUPABASE_KEY,
                                    "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                                    "Content-Type": "application/json"
                                }},
                                body: JSON.stringify({{ reports_to_id: candidateToMove.reports_to_id || null }})
                            }});
                        }}

                        // Update candidate comments and detach from active reporting
                        const res = await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping?mapping_id=eq.${{id}}`, {{
                            method: "PATCH",
                            headers: {{
                                "apikey": SUPABASE_KEY,
                                "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                                "Content-Type": "application/json",
                                "Prefer": "return=representation"
                            }},
                            body: JSON.stringify({{
                                reports_to_id: null,
                                comments: updatedComments,
                                updated_on: new Date().toISOString()
                            }})
                        }});

                        if (!res.ok) {{
                            const errText = await res.text();
                            throw new Error(`Failed to update status: ${{errText}}`);
                        }}

                        // Move node to top root row with status badge
                        const nodeLi = document.getElementById("node-" + id);
                        if (nodeLi) {{
                            const topUl = document.querySelector(".wd-tree > ul");
                            if (topUl) topUl.appendChild(nodeLi);
                            const tag = nodeLi.querySelector(".wd-tag");
                            if (tag) tag.textContent = statusVal;
                        }}

                        // Update local record
                        const localRec = ALL_RECORDS.find(r => r.mapping_id == id);
                        if (localRec) {{
                            localRec.reports_to_id = null;
                            localRec.comments = updatedComments;
                        }}

                        successDiv.textContent = `✅ Marked as ${{statusVal}}!`;
                        successDiv.style.display = "block";

                        setTimeout(() => {{
                            closeMoveCandidateModal();
                            closeIntelModal();
                            showToast(`🏖️ Marked ${{candidateToMove.name}} as ${{statusVal}}`);
                        }}, 450);
                    }}
                }} catch (err) {{
                    errorDiv.textContent = err.message || "Failed to process movement.";
                    errorDiv.style.display = "block";
                    btn.disabled = false;
                    btn.textContent = "💾 Save Movement";
                }}
            }}

            // Add Direct Report Modal Functions
            function openAddReportModal(param) {{
                const nodeData = getNodeData(param);
                if (!nodeData) return;

                document.getElementById("addReportsToId").value = nodeData.id;
                document.getElementById("addCompany").value = nodeData.company;
                document.getElementById("addCompType").value = nodeData.type || "Chemicals";
                
                document.getElementById("addMgrName").textContent = `👤 ${{nodeData.name}} (ID: ${{nodeData.id}})`;
                document.getElementById("addMgrDetails").textContent = `💼 ${{nodeData.designation}} • 🏢 ${{nodeData.company}} (${{nodeData.type}})`;
                
                // Reset form fields
                document.getElementById("addCandName").value = "";
                document.getElementById("addCandDesig").value = "";
                document.getElementById("addCandLoc").value = nodeData.location !== "N/A" ? nodeData.location : "";
                document.getElementById("addCandExp").value = "";
                document.getElementById("addCandCurrCTC").value = "";
                document.getElementById("addCandExpCTC").value = "";
                document.getElementById("addCandContact").value = "";
                document.getElementById("addCandEmail").value = "";
                document.getElementById("addCandComments").value = "";
                
                document.getElementById("addErrorMsg").style.display = "none";
                document.getElementById("addSuccessMsg").style.display = "none";
                const btn = document.getElementById("addSubmitBtn");
                btn.disabled = false;
                btn.textContent = "💾 Save Direct Report";
                
                document.getElementById("addReportModal").style.display = "flex";
                setTimeout(() => {{
                    document.getElementById("addCandName").focus();
                }}, 150);
            }}

            function closeAddReportModal(e) {{
                document.getElementById("addReportModal").style.display = "none";
            }}

            // Edit Candidate Modal Functions
            function openEditCandidateModal(param) {{
                const nodeData = getNodeData(param);
                if (!nodeData) return;

                document.getElementById("editCandId").value = nodeData.id;
                document.getElementById("editCandName").value = nodeData.name || "";
                document.getElementById("editCandDesig").value = nodeData.designation || "";
                document.getElementById("editCandLoc").value = nodeData.location !== "N/A" ? (nodeData.location || "") : "";
                document.getElementById("editCandExp").value = nodeData.experience !== "N/A" ? (nodeData.experience || "") : "";
                
                let currCTC = nodeData.current_ctc_num !== undefined && nodeData.current_ctc_num !== null ? nodeData.current_ctc_num : (parseFloat(String(nodeData.current_ctc).replace(/[^0-9.]/g, '')) || "");
                let expCTC = nodeData.expected_ctc_num !== undefined && nodeData.expected_ctc_num !== null ? nodeData.expected_ctc_num : (parseFloat(String(nodeData.expected_ctc).replace(/[^0-9.]/g, '')) || "");
                document.getElementById("editCandCurrCTC").value = currCTC || "";
                document.getElementById("editCandExpCTC").value = expCTC || "";
                
                document.getElementById("editCandContact").value = nodeData.contact || "";
                document.getElementById("editCandEmail").value = nodeData.email || "";
                document.getElementById("editCandComments").value = (nodeData.comments && nodeData.comments !== "No specific comments recorded.") ? nodeData.comments : "";
                
                // Populate manager dropdown ONLY for candidates belonging to the SAME company (excluding self)
                const select = document.getElementById("editCandReportsTo");
                select.innerHTML = '<option value="">None (Top-Level Leader / Root)</option>';
                ALL_RECORDS.forEach(rec => {{
                    const isSameComp = (rec.company_name || "").trim().toLowerCase() === (nodeData.company || "").trim().toLowerCase();
                    if (rec.mapping_id != nodeData.id && isSameComp) {{
                        const opt = document.createElement("option");
                        opt.value = rec.mapping_id;
                        opt.textContent = `👤 ${{rec.candidate_name}} (${{rec.designation}})`;
                        if (rec.mapping_id == nodeData.reports_to_id) {{
                            opt.selected = true;
                        }}
                        select.appendChild(opt);
                    }}
                }});

                document.getElementById("editErrorMsg").style.display = "none";
                document.getElementById("editSuccessMsg").style.display = "none";
                const btn = document.getElementById("editSubmitBtn");
                btn.disabled = false;
                btn.textContent = "💾 Save Changes";

                document.getElementById("editCandModal").style.display = "flex";
                setTimeout(() => {{
                    document.getElementById("editCandName").focus();
                }}, 150);
            }}

            function closeEditCandidateModal(e) {{
                document.getElementById("editCandModal").style.display = "none";
            }}

            async function submitEditCandidate(event) {{
                event.preventDefault();
                const btn = document.getElementById("editSubmitBtn");
                const errorDiv = document.getElementById("editErrorMsg");
                const successDiv = document.getElementById("editSuccessMsg");
                
                errorDiv.style.display = "none";
                successDiv.style.display = "none";

                const id = parseInt(document.getElementById("editCandId").value);
                const name = document.getElementById("editCandName").value.trim();
                const desig = document.getElementById("editCandDesig").value.trim();
                if (!name || !desig) {{
                    errorDiv.textContent = "Please fill in Candidate Name and Designation.";
                    errorDiv.style.display = "block";
                    return;
                }}

                const loc = document.getElementById("editCandLoc").value.trim() || "N/A";
                const exp = document.getElementById("editCandExp").value.trim() || "N/A";
                const currCTCVal = document.getElementById("editCandCurrCTC").value.trim();
                const expCTCVal = document.getElementById("editCandExpCTC").value.trim();
                const currCTC = currCTCVal ? parseFloat(currCTCVal) : null;
                const expCTC = expCTCVal ? parseFloat(expCTCVal) : null;
                
                let contact = document.getElementById("editCandContact").value.trim();
                if (contact.endsWith(".0")) {{
                    contact = contact.slice(0, -2);
                }}
                const email = document.getElementById("editCandEmail").value.trim();
                const comments = document.getElementById("editCandComments").value.trim();
                const reportsToVal = document.getElementById("editCandReportsTo").value;
                const reportsToId = reportsToVal ? parseInt(reportsToVal) : null;

                btn.disabled = true;
                btn.textContent = "Saving Changes...";

                const payload = {{
                    candidate_name: name,
                    designation: desig,
                    location: loc,
                    experience: exp,
                    current_ctc: currCTC,
                    expected_ctc: expCTC,
                    contact_number: contact,
                    email_id: email,
                    comments: comments,
                    reports_to_id: reportsToId,
                    updated_on: new Date().toISOString()
                }};

                try {{
                    const response = await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping?mapping_id=eq.${{id}}`, {{
                        method: "PATCH",
                        headers: {{
                            "apikey": SUPABASE_KEY,
                            "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                            "Content-Type": "application/json",
                            "Prefer": "return=representation"
                        }},
                        body: JSON.stringify(payload)
                    }});

                    if (!response.ok) {{
                        const errText = await response.text();
                        throw new Error(`Failed to update candidate: ${{errText}}`);
                    }}

                    // Update live node in DOM
                    const nodeLi = document.getElementById("node-" + id);
                    if (nodeLi) {{
                        const nameEl = nodeLi.querySelector(".wd-name");
                        if (nameEl) nameEl.textContent = name;
                        const desigEl = nodeLi.querySelector(".wd-desig");
                        if (desigEl) desigEl.textContent = desig;
                        const avatarEl = nodeLi.querySelector(".wd-avatar");
                        if (avatarEl) avatarEl.textContent = getInitials(name);
                        
                        const metaItems = nodeLi.querySelectorAll(".wd-meta-item");
                        if (metaItems.length >= 3) {{
                            metaItems[0].innerHTML = `📍 <b>${{loc}}</b>`;
                            metaItems[1].innerHTML = `⏱️ <b>${{exp}}</b>`;
                            metaItems[2].innerHTML = `💰 <b>${{currCTC ? '₹ ' + currCTC.toLocaleString() : 'Not Disclosed'}}</b>`;
                        }}

                        // Check if parent manager was changed
                        const localRec = ALL_RECORDS.find(r => r.mapping_id == id);
                        const oldReportsTo = localRec ? localRec.reports_to_id : null;
                        if (oldReportsTo != reportsToId) {{
                            if (reportsToId) {{
                                const parentLi = document.getElementById("node-" + reportsToId);
                                if (parentLi) {{
                                    let pUl = parentLi.querySelector(":scope > ul");
                                    if (!pUl) {{
                                        pUl = document.createElement("ul");
                                        parentLi.appendChild(pUl);
                                    }}
                                    pUl.appendChild(nodeLi);
                                }}
                            }} else {{
                                const topUl = document.querySelector(".wd-tree > ul");
                                if (topUl) topUl.appendChild(nodeLi);
                            }}
                        }}

                        // Update local object in ALL_RECORDS
                        if (localRec) {{
                            localRec.candidate_name = name;
                            localRec.designation = desig;
                            localRec.location = loc;
                            localRec.experience = exp;
                            localRec.current_ctc = currCTC;
                            localRec.expected_ctc = expCTC;
                            localRec.contact_number = contact;
                            localRec.email_id = email;
                            localRec.comments = comments;
                            localRec.reports_to_id = reportsToId;
                        }}
                    }}

                    successDiv.textContent = "✅ Updated successfully!";
                    successDiv.style.display = "block";

                    setTimeout(() => {{
                        closeEditCandidateModal();
                        showToast(`✅ ${{name}}'s details updated!`);
                    }}, 400);
                }} catch (err) {{
                    errorDiv.textContent = err.message || "Failed to update record.";
                    errorDiv.style.display = "block";
                    btn.disabled = false;
                    btn.textContent = "💾 Save Changes";
                }}
            }}

            function getInitials(name) {{
                const parts = (name || "").trim().split(/\\s+/).filter(Boolean);
                if (parts.length >= 2) {{
                    return (parts[0][0] + parts[-1][0]).toUpperCase();
                }} else if (parts.length === 1) {{
                    return parts[0].slice(0, 2).toUpperCase();
                }}
                return "TM";
            }}

            function showToast(msg) {{
                let t = document.getElementById("wdToast");
                if (!t) {{
                    t = document.createElement("div");
                    t.id = "wdToast";
                    t.style.cssText = "position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #1e1b4b; color: #ffffff; padding: 12px 24px; border-radius: 12px; font-weight: 700; font-size: 0.9rem; z-index: 9999; box-shadow: 0 10px 30px rgba(0,0,0,0.35); border: 1.5px solid #818cf8; transition: all 0.3s ease; opacity: 0; pointer-events: none;";
                    document.body.appendChild(t);
                }}
                t.textContent = msg;
                t.style.opacity = "1";
                setTimeout(() => {{
                    t.style.opacity = "0";
                }}, 3500);
            }}

            function insertNodeIntoDOM(parentId, data) {{
                const parentLi = document.getElementById("node-" + parentId);
                if (!parentLi) return;

                let ul = parentLi.querySelector(":scope > ul");
                if (!ul) {{
                    ul = document.createElement("ul");
                    parentLi.appendChild(ul);
                }}

                // Update parent's direct reports badge count
                const existingBadge = parentLi.querySelector(":scope > .wd-card .wd-reports-badge");
                const childCount = ul.children.length + 1;
                if (existingBadge) {{
                    existingBadge.innerHTML = `👥 ${{childCount}} Direct Reports <span class="wd-toggle-icon">▾</span>`;
                }} else {{
                    const metaGrid = parentLi.querySelector(":scope > .wd-card .wd-meta-grid");
                    if (metaGrid) {{
                        const badge = document.createElement("div");
                        badge.className = "wd-reports-badge";
                        badge.style.cssText = "background: rgba(99, 102, 241, 0.12); color: #4338ca; border: 1px solid rgba(99, 102, 241, 0.3);";
                        badge.setAttribute("onclick", "event.stopPropagation(); toggleNodeChildren(this);");
                        badge.innerHTML = `👥 1 Direct Reports <span class="wd-toggle-icon">▾</span>`;
                        metaGrid.parentNode.insertBefore(badge, metaGrid.nextSibling);
                    }}
                }}

                // If parent was collapsed, expand it
                parentLi.classList.remove("wd-collapsed");

                // Calculate child level from parent
                let parentLevel = 1;
                const parentLevelSpan = parentLi.querySelector(":scope > .wd-card .wd-card-header > span");
                if (parentLevelSpan) {{
                    const match = parentLevelSpan.textContent.match(/\\d+/);
                    if (match) {{
                        parentLevel = parseInt(match[0]);
                    }}
                }}
                const childLevel = parentLevel + 1;
                const childLevelTitle = childLevel === 2 ? "👔 Level 2" : (childLevel === 3 ? "👤 Level 3" : `🎯 Level ${{childLevel}}`);
                data.level = childLevelTitle;

                const initials = getInitials(data.name);
                const border_color = childLevel === 2 ? "#0284c7" : (childLevel === 3 ? "#059669" : "#d97706");
                const header_bg = childLevel === 2 ? "linear-gradient(135deg, #0284c7 0%, #0ea5e9 50%, #06b6d4 100%)" : (childLevel === 3 ? "linear-gradient(135deg, #047857 0%, #059669 50%, #10b981 100%)" : "linear-gradient(135deg, #b45309 0%, #d97706 50%, #f59e0b 100%)");
                const avatar_bg = childLevel === 2 ? "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)" : (childLevel === 3 ? "linear-gradient(135deg, #10b981 0%, #047857 100%)" : "linear-gradient(135deg, #f59e0b 0%, #b45309 100%)");
                const tag_bg = "rgba(255, 255, 255, 0.28)";

                const li = document.createElement("li");
                li.className = "wd-node-item";
                li.id = "node-" + data.id;
                li.setAttribute("data-id", data.id);
                li.innerHTML = `
                    <div class="wd-card highlighted" style="border-top: 4px solid ${{border_color}};" onclick="showIntelModal(${{data.id}})">
                        <div class="wd-card-header" style="background: ${{header_bg}};">
                            <span>${{data.level}}</span>
                            <span class="wd-tag" style="background: ${{tag_bg}};">${{data.type}}</span>
                        </div>
                        <div class="wd-card-body">
                            <div class="wd-profile-row">
                                <div class="wd-avatar" style="background: ${{avatar_bg}}; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">${{initials}}</div>
                                <div class="wd-profile-text">
                                    <div class="wd-name">${{data.name}}</div>
                                    <div class="wd-desig" style="color: ${{border_color}};">${{data.designation}}</div>
                                </div>
                            </div>
                            <div class="wd-meta-grid">
                                <div class="wd-meta-item">📍 <b>${{data.location}}</b></div>
                                <div class="wd-meta-item">⏱️ <b>${{data.experience}}</b></div>
                                <div class="wd-meta-item wd-ctc-item">💰 <b>${{data.current_ctc}}</b></div>
                            </div>
                            <div class="wd-card-actions" onclick="event.stopPropagation();">
                                <button type="button" class="wd-btn-intel" onclick="showIntelModal(${{data.id}})" title="View Full 360 Dossier">👁️ Intel</button>
                                <button type="button" class="wd-btn-edit-node" onclick="openEditCandidateModal(${{data.id}})" title="Edit Details">✏️ Edit</button>
                                <button type="button" class="wd-btn-move-node" onclick="openMoveCandidateModal(${{data.id}})" title="Move / Transfer / Retire">🚚 Move</button>
                                <button type="button" class="wd-btn-del-node" onclick="openDeleteCandidateModal(${{data.id}})" title="Delete Candidate">🗑️</button>
                            </div>
                        </div>
                        <div class="wd-card-footer" onclick="event.stopPropagation();">
                            <button type="button" class="wd-btn-footer-add" onclick="openAddReportModal(${{data.id}})" title="Add candidate reporting under ${{data.name}}">
                                ➕ Add Direct Report
                            </button>
                        </div>
                    </div>
                `;
                ul.appendChild(li);

                // Add to ALL_RECORDS list
                ALL_RECORDS.push({{
                    mapping_id: data.id,
                    candidate_name: data.name,
                    designation: data.designation,
                    company_name: data.company,
                    company_type: data.type,
                    location: data.location,
                    experience: data.experience,
                    current_ctc: data.current_ctc_num || null,
                    expected_ctc: data.expected_ctc_num || null,
                    contact_number: data.contact || null,
                    email_id: data.email || null,
                    comments: data.comments || null,
                    reports_to_id: parentId
                }});

                setTimeout(() => {{
                    li.scrollIntoView({{ behavior: "smooth", block: "center", inline: "center" }});
                    setTimeout(() => {{
                        const c = li.querySelector(".wd-card");
                        if (c) c.classList.remove("highlighted");
                    }}, 3000);
                }}, 200);
            }}

            async function submitAddReport(event) {{
                event.preventDefault();
                const btn = document.getElementById("addSubmitBtn");
                const errorDiv = document.getElementById("addErrorMsg");
                const successDiv = document.getElementById("addSuccessMsg");
                
                errorDiv.style.display = "none";
                successDiv.style.display = "none";

                const name = document.getElementById("addCandName").value.trim();
                const desig = document.getElementById("addCandDesig").value.trim();
                if (!name || !desig) {{
                    errorDiv.textContent = "Please fill in Candidate Name and Designation.";
                    errorDiv.style.display = "block";
                    return;
                }}

                const reportsToId = parseInt(document.getElementById("addReportsToId").value);
                const company = document.getElementById("addCompany").value;
                const compType = document.getElementById("addCompType").value || "Chemicals";
                const loc = document.getElementById("addCandLoc").value.trim() || "N/A";
                const exp = document.getElementById("addCandExp").value.trim() || "N/A";
                const currCTCVal = document.getElementById("addCandCurrCTC").value.trim();
                const expCTCVal = document.getElementById("addCandExpCTC").value.trim();
                const currCTC = currCTCVal ? parseFloat(currCTCVal) : null;
                const expCTC = expCTCVal ? parseFloat(expCTCVal) : null;
                
                // Clean contact number (strip any decimals if entered)
                let contact = document.getElementById("addCandContact").value.trim();
                if (contact.endsWith(".0")) {{
                    contact = contact.slice(0, -2);
                }}
                const email = document.getElementById("addCandEmail").value.trim();
                const comments = document.getElementById("addCandComments").value.trim();

                btn.disabled = true;
                btn.textContent = "Saving to Database...";

                const payload = {{
                    company_type: compType,
                    company_name: company,
                    candidate_name: name,
                    designation: desig,
                    location: loc,
                    experience: exp,
                    current_ctc: currCTC,
                    expected_ctc: expCTC,
                    contact_number: contact,
                    email_id: email,
                    comments: comments,
                    reports_to_id: reportsToId,
                    created_by: CURRENT_USER_ID || null,
                    created_by_name: CURRENT_USER_NAME || null,
                    created_on: new Date().toISOString(),
                    updated_on: new Date().toISOString()
                }};

                try {{
                    const response = await fetch(`${{SUPABASE_URL}}/rest/v1/talent_mapping`, {{
                        method: "POST",
                        headers: {{
                            "apikey": SUPABASE_KEY,
                            "Authorization": `Bearer ${{SUPABASE_KEY}}`,
                            "Content-Type": "application/json",
                            "Prefer": "return=representation"
                        }},
                        body: JSON.stringify(payload)
                    }});

                    if (!response.ok) {{
                        const errText = await response.text();
                        throw new Error(`Failed to save candidate: ${{errText}}`);
                    }}

                    const insertedData = await response.json();
                    const newRecord = (Array.isArray(insertedData) && insertedData.length > 0) ? insertedData[0] : payload;
                    const newId = newRecord.mapping_id || ("tmp_" + Date.now());

                    successDiv.textContent = `🎉 Successfully added ${{name}} under manager!`;
                    successDiv.style.display = "block";

                    // Dynamically insert into live org chart tree without page refresh
                    insertNodeIntoDOM(reportsToId, {{
                        id: newId,
                        name: name,
                        designation: desig,
                        company: company,
                        type: compType,
                        location: loc,
                        experience: exp,
                        current_ctc: currCTC ? `₹ ${{currCTC.toLocaleString()}}` : "Not Disclosed",
                        expected_ctc: expCTC ? `₹ ${{expCTC.toLocaleString()}}` : "N/A",
                        current_ctc_num: currCTC,
                        expected_ctc_num: expCTC,
                        contact: contact,
                        email: email,
                        comments: comments,
                        reports_to_id: reportsToId,
                        level: "🎯 Level (Direct Report)",
                        reports_count: 0
                    }});

                    setTimeout(() => {{
                        closeAddReportModal();
                        showToast(`🎉 ${{name}} mapped under reporting manager!`);
                    }}, 500);
                }} catch (err) {{
                    errorDiv.textContent = err.message || "Failed to save record.";
                    errorDiv.style.display = "block";
                    btn.disabled = false;
                    btn.textContent = "💾 Save Direct Report";
                }}
            }}

            // Auto-center canvas on initial load
            window.addEventListener("DOMContentLoaded", () => {{
                setTimeout(() => {{
                    resetView();
                }}, 120);
            }});
        </script>
    </body>
    </html>
    """
    return full_html

# ==============================================================================
# 5. HEADER & PAGE BANNER
# ==============================================================================
st.markdown(
    textwrap.dedent("""
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">
        <div>
            <h1 style="margin: 0; font-size: 2rem; color: #1e293b;">🗺️ Talent Mapping & Org Hierarchy</h1>
            <p style="margin: 4px 0 0 0; color: #64748b; font-size: 0.95rem;">
                Enterprise interactive organizational chart, competitor reporting lines, and market intelligence company-wise.
            </p>
        </div>
    </div>
    """).strip(),
    unsafe_allow_html=True
)

# Check table readiness
table_exists = check_table_exists()
if not table_exists:
    st.error("⚠️ The `talent_mapping` table is not yet detected in your Supabase database.")
    with st.expander("🛠️ Click here to view the SQL script to create the table in Supabase SQL Editor", expanded=True):
        st.code(
            """
CREATE TABLE IF NOT EXISTS public.talent_mapping (
    mapping_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    company_type TEXT NOT NULL DEFAULT 'Chemicals',
    company_name TEXT NOT NULL,
    candidate_name TEXT NOT NULL,
    designation TEXT NOT NULL,
    location TEXT,
    experience TEXT,
    current_ctc NUMERIC,
    expected_ctc NUMERIC,
    contact_number TEXT,
    email_id TEXT,
    comments TEXT,
    reports_to_id BIGINT REFERENCES public.talent_mapping(mapping_id) ON DELETE SET NULL,
    candidate_id BIGINT REFERENCES public.candidate_management(candidate_id) ON DELETE SET NULL,
    created_by BIGINT,
    created_by_name TEXT,
    created_on TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_on TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_talent_company ON public.talent_mapping(company_name);
CREATE INDEX IF NOT EXISTS idx_talent_company_type ON public.talent_mapping(company_type);
CREATE INDEX IF NOT EXISTS idx_talent_reports_to ON public.talent_mapping(reports_to_id);

ALTER TABLE public.talent_mapping ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow public select talent_mapping') THEN
        CREATE POLICY "Allow public select talent_mapping" ON public.talent_mapping FOR SELECT TO public USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow public insert talent_mapping') THEN
        CREATE POLICY "Allow public insert talent_mapping" ON public.talent_mapping FOR INSERT TO public WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow public update talent_mapping') THEN
        CREATE POLICY "Allow public update talent_mapping" ON public.talent_mapping FOR UPDATE TO public USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Allow public delete talent_mapping') THEN
        CREATE POLICY "Allow public delete talent_mapping" ON public.talent_mapping FOR DELETE TO public USING (true);
    END IF;
END $$;
            """,
            language="sql"
        )
    st.info("Once you execute this in your Supabase SQL editor, refresh this page to begin saving data.")
    st.stop()

# ==============================================================================
# 6. DATA LOADING & FILTERING
# ==============================================================================
raw_mappings = fetch_talent_mappings()
ats_candidates = get_all_ats_candidates()

# Unique companies and company types
all_companies = sorted(list(set(item.get("company_name", "").strip() for item in raw_mappings if item.get("company_name"))))
all_types_in_db = sorted(list(set(item.get("company_type", "").strip() for item in raw_mappings if item.get("company_type"))))
available_types = sorted(list(set(COMPANY_TYPES + all_types_in_db)))

# Filter Toolbar
col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2.5, 3, 1.5])

with col_f1:
    type_filter_options = ["All Types"] + available_types
    sel_type = st.selectbox("🏷️ Company Type", type_filter_options, index=0)

with col_f2:
    if sel_type != "All Types":
        filtered_by_type = [c for c in all_companies if any(m.get("company_name") == c and m.get("company_type") == sel_type for m in raw_mappings)]
    else:
        filtered_by_type = all_companies
    
    company_options = ["All Companies"] + filtered_by_type
    sel_company = st.selectbox("🏢 Select Company", company_options, index=0)

with col_f3:
    search_query = st.text_input("🔍 Search Candidate / Designation / Location", placeholder="e.g. Production, Mumbai, Candidate A").strip().lower()

with col_f4:
    st.write("")
    st.write("")
    refresh_btn = st.button("🔄 Refresh", use_container_width=True)
    if refresh_btn:
        st.rerun()

# Apply Filters
filtered_mappings = raw_mappings
if sel_type != "All Types":
    filtered_mappings = [m for m in filtered_mappings if m.get("company_type") == sel_type]
if sel_company != "All Companies":
    filtered_mappings = [m for m in filtered_mappings if m.get("company_name") == sel_company]
if search_query:
    filtered_mappings = [
        m for m in filtered_mappings
        if (search_query in str(m.get("candidate_name", "")).lower() or
            search_query in str(m.get("designation", "")).lower() or
            search_query in str(m.get("location", "")).lower() or
            search_query in str(m.get("company_name", "")).lower())
    ]

# Summary Metrics
m_col1, m_col2, m_col3, m_col4 = st.columns(4)
total_mapped = len(filtered_mappings)
unique_companies_count = len(set(m.get("company_name") for m in filtered_mappings if m.get("company_name")))
root_heads_count = len([m for m in filtered_mappings if not m.get("reports_to_id")])
subordinates_count = total_mapped - root_heads_count

m_col1.metric("👥 Total Mapped Candidates", total_mapped)
m_col2.metric("🏢 Companies", unique_companies_count)
m_col3.metric("👑 Top-Level Leaders", root_heads_count)
m_col4.metric("👔 Reporting Subordinates", subordinates_count)

st.markdown("---")

# ==============================================================================
# 7. "➕ MAP NEW CANDIDATE" FORM SECTION
# ==============================================================================
with st.expander("➕ **Map New Candidate into Hierarchy**", expanded=(total_mapped == 0 or st.session_state.tm_add_under_id is not None)):
    
    # Pre-selection if user clicked "Add Direct Report"
    preset_manager_id = st.session_state.tm_add_under_id
    preset_manager_name = ""
    preset_company = ""
    preset_type = "Chemicals"
    
    if preset_manager_id:
        parent_rec = next((m for m in raw_mappings if m.get("mapping_id") == preset_manager_id), None)
        if parent_rec:
            preset_manager_name = f"{parent_rec.get('candidate_name')} ({parent_rec.get('designation')})"
            preset_company = parent_rec.get("company_name", "")
            preset_type = parent_rec.get("company_type", "Chemicals")
            st.info(f"🎯 Mapping a direct report under: **{preset_manager_name}** at **{preset_company}**")

    # Smart ATS Auto-Fill Option
    st.markdown("##### ⚡ Quick Auto-Fill from ATS Database (Optional)")
    ats_cand_map = {c["display_name"]: c for c in ats_candidates}
    selected_ats_key = st.selectbox(
        "Search existing ATS candidate to auto-populate fields",
        ["-- Or type details manually below --"] + list(ats_cand_map.keys()),
        index=0,
        key=f"ats_fill_selector_{st.session_state.tm_form_reset_counter}"
    )

    autofill_data = {}
    if selected_ats_key != "-- Or type details manually below --":
        autofill_data = ats_cand_map[selected_ats_key]

    st.markdown("##### 📝 Candidate & Position Details")
    
    form_company_type = preset_type if preset_company else (autofill_data.get("company_type") or (sel_type if sel_type != "All Types" else "Chemicals"))
    form_company_name = preset_company if preset_company else (autofill_data.get("company_name") or (sel_company if sel_company != "All Companies" else ""))

    form_types_list = sorted(list(set(available_types)))
    type_options = form_types_list + ["➕ Add New Custom Type..."]
    default_type = form_company_type if form_company_type in form_types_list else ("Chemicals" if "Chemicals" in form_types_list else form_types_list[0])
    type_idx = form_types_list.index(default_type) if default_type in form_types_list else 0

    c_row1_1, c_row1_2, c_row1_3 = st.columns([1.8, 2, 2.5])
    with c_row1_1:
        sel_type_choice = st.selectbox("Company Type *", type_options, index=type_idx)
        if sel_type_choice == "➕ Add New Custom Type...":
            new_comp_type = st.text_input("Enter New Type *", placeholder="e.g. Bio-Tech, Renewable")
        else:
            new_comp_type = sel_type_choice
    
    with c_row1_2:
        new_comp_name = st.text_input("Current Company *", value=form_company_name, placeholder="e.g. UPL, PI Industries")
    
    with c_row1_3:
        new_cand_name = st.text_input("Candidate Name *", value=autofill_data.get("candidate_name", ""), placeholder="e.g. Candidate A")

    c_row2_1, c_row2_2, c_row2_3 = st.columns([2, 2, 2])
    with c_row2_1:
        new_designation = st.text_input("Designation *", value=autofill_data.get("designation", ""), placeholder="e.g. Head of Production, VP Operations")
    with c_row2_2:
        new_location = st.text_input("Location", value=autofill_data.get("location", ""), placeholder="e.g. Mumbai, Vapi, Hyderabad")
    with c_row2_3:
        new_experience = st.text_input("Experience", value=str(autofill_data.get("experience", "")), placeholder="e.g. 15 Years")

    c_row3_1, c_row3_2, c_row3_3, c_row3_4 = st.columns(4)
    with c_row3_1:
        new_curr_ctc = st.number_input("Current CTC (₹)", min_value=0.0, value=float(autofill_data.get("current_ctc") or 0.0), step=50000.0, format="%.2f")
    with c_row3_2:
        new_exp_ctc = st.number_input("Expected CTC (₹) [Optional]", min_value=0.0, value=float(autofill_data.get("expected_ctc") or 0.0), step=50000.0, format="%.2f")
    with c_row3_3:
        new_contact = st.text_input("Contact Number", value=clean_phone_number(autofill_data.get("contact_number", "")), placeholder="e.g. 9876543210")
    with c_row3_4:
        new_email = st.text_input("Email ID", value=autofill_data.get("email_id", ""), placeholder="e.g. candidate@example.com")

    # Hierarchy: Reports To selector for this company
    current_company_candidates = [m for m in raw_mappings if m.get("company_name", "").strip().lower() == new_comp_name.strip().lower()]
    manager_options = [("None (Top-Level Leader / Root)", None)]
    preset_manager_idx = 0
    
    for idx, cand in enumerate(current_company_candidates):
        display_label = f"👤 {cand.get('candidate_name')} - {cand.get('designation')} (ID: {cand.get('mapping_id')})"
        manager_options.append((display_label, cand.get("mapping_id")))
        if preset_manager_id and cand.get("mapping_id") == preset_manager_id:
            preset_manager_idx = idx + 1

    c_row4_1, c_row4_2 = st.columns([2, 3])
    with c_row4_1:
        sel_manager_tuple = st.selectbox(
            "👑 Reports To (Reporting Manager)",
            manager_options,
            index=preset_manager_idx,
            format_func=lambda x: x[0]
        )
        new_reports_to_id = sel_manager_tuple[1]

    with c_row4_2:
        new_comments = st.text_input("Comments / Recruiter Notes", placeholder="e.g. Key decision maker, open to relocation, leading 4 plant sites")

    col_btn1, col_btn2 = st.columns([1.5, 4])
    with col_btn1:
        submit_add = st.button("💾 Save & Add to Map", type="primary", use_container_width=True)
    with col_btn2:
        if preset_manager_id:
            if st.button("Cancel Direct Report Mode"):
                st.session_state.tm_add_under_id = None
                st.rerun()

    if submit_add:
        if not new_comp_name.strip():
            st.error("Please enter the Company Name.")
        elif not new_cand_name.strip():
            st.error("Please enter the Candidate Name.")
        elif not new_designation.strip():
            st.error("Please enter the Designation.")
        else:
            payload = {
                "company_type": new_comp_type.strip(),
                "company_name": new_comp_name.strip(),
                "candidate_name": new_cand_name.strip(),
                "designation": new_designation.strip(),
                "location": new_location.strip(),
                "experience": new_experience.strip(),
                "current_ctc": new_curr_ctc if new_curr_ctc > 0 else None,
                "expected_ctc": new_exp_ctc if new_exp_ctc > 0 else None,
                "contact_number": clean_phone_number(new_contact),
                "email_id": new_email.strip(),
                "comments": new_comments.strip(),
                "reports_to_id": new_reports_to_id,
                "candidate_id": autofill_data.get("candidate_id")
            }
            success, res = insert_talent_mapping(payload)
            if success:
                st.success(f"✅ Successfully mapped **{new_cand_name}** under **{new_comp_name}**!")
                st.session_state.tm_add_under_id = None
                st.session_state.tm_form_reset_counter += 1
                st.rerun()
            else:
                st.error(f"Error saving candidate: {res}")

st.markdown("---")

# ==============================================================================
# 8. EDIT / RE-PARENT FORM (IF TRIGGERED)
# ==============================================================================
if st.session_state.tm_edit_node_id is not None:
    edit_id = st.session_state.tm_edit_node_id
    edit_record = next((m for m in raw_mappings if m.get("mapping_id") == edit_id), None)
    
    if edit_record:
        st.markdown(f"### ✏️ Edit Candidate Details: **{edit_record.get('candidate_name')}** (ID: {edit_id})")
        with st.form("edit_node_form"):
            e_col1, e_col2, e_col3 = st.columns([1.8, 2, 2.5])
            with e_col1:
                cur_type = edit_record.get("company_type", "Chemicals")
                e_type_list = sorted(list(set(available_types + [cur_type])))
                e_type_options = e_type_list + ["➕ Add New Custom Type..."]
                e_type_idx = e_type_list.index(cur_type) if cur_type in e_type_list else 0
                e_sel_choice = st.selectbox("Company Type", e_type_options, index=e_type_idx)
                if e_sel_choice == "➕ Add New Custom Type...":
                    e_type = st.text_input("Enter Custom Type", placeholder="e.g. Bio-Tech")
                else:
                    e_type = e_sel_choice
            with e_col2:
                e_comp = st.text_input("Company Name", value=edit_record.get("company_name", ""))
            with e_col3:
                e_name = st.text_input("Candidate Name", value=edit_record.get("candidate_name", ""))

            e_col4, e_col5, e_col6 = st.columns(3)
            with e_col4:
                e_desig = st.text_input("Designation", value=edit_record.get("designation", ""))
            with e_col5:
                e_loc = st.text_input("Location", value=edit_record.get("location", ""))
            with e_col6:
                e_exp = st.text_input("Experience", value=str(edit_record.get("experience", "")))

            e_col7, e_col8, e_col9, e_col10 = st.columns(4)
            with e_col7:
                e_c_ctc = st.number_input("Current CTC (₹)", min_value=0.0, value=float(edit_record.get("current_ctc") or 0.0), step=50000.0, format="%.2f")
            with e_col8:
                e_e_ctc = st.number_input("Expected CTC (₹)", min_value=0.0, value=float(edit_record.get("expected_ctc") or 0.0), step=50000.0, format="%.2f")
            with e_col9:
                e_contact = st.text_input("Contact Number", value=clean_phone_number(edit_record.get("contact_number", "")))
            with e_col10:
                e_email = st.text_input("Email ID", value=edit_record.get("email_id", ""))

            # Manager selection (prevent choosing oneself)
            e_comp_cands = [m for m in raw_mappings if m.get("company_name", "").strip().lower() == e_comp.strip().lower() and m.get("mapping_id") != edit_id]
            e_manager_options = [("None (Top-Level Leader / Root)", None)]
            e_curr_mgr_idx = 0
            for idx, cand in enumerate(e_comp_cands):
                display_label = f"👤 {cand.get('candidate_name')} - {cand.get('designation')} (ID: {cand.get('mapping_id')})"
                e_manager_options.append((display_label, cand.get("mapping_id")))
                if cand.get("mapping_id") == edit_record.get("reports_to_id"):
                    e_curr_mgr_idx = idx + 1

            e_col11, e_col12 = st.columns([2, 3])
            with e_col11:
                e_sel_manager = st.selectbox(
                    "👑 Reports To (Reporting Manager)",
                    e_manager_options,
                    index=e_curr_mgr_idx,
                    format_func=lambda x: x[0]
                )
            with e_col12:
                e_comments = st.text_input("Comments", value=edit_record.get("comments", ""))

            e_btn_col1, e_btn_col2, e_btn_col3 = st.columns([1.5, 1.5, 4])
            with e_btn_col1:
                save_edit = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)
            with e_btn_col2:
                cancel_edit = st.form_submit_button("❌ Cancel", use_container_width=True)

            if cancel_edit:
                st.session_state.tm_edit_node_id = None
                st.rerun()

            if save_edit:
                updates = {
                    "company_type": e_type.strip(),
                    "company_name": e_comp.strip(),
                    "candidate_name": e_name.strip(),
                    "designation": e_desig.strip(),
                    "location": e_loc.strip(),
                    "experience": e_exp.strip(),
                    "current_ctc": e_c_ctc if e_c_ctc > 0 else None,
                    "expected_ctc": e_e_ctc if e_e_ctc > 0 else None,
                    "contact_number": clean_phone_number(e_contact),
                    "email_id": e_email.strip(),
                    "comments": e_comments.strip(),
                    "reports_to_id": e_sel_manager[1]
                }
                success, res = update_talent_mapping(edit_id, updates)
                if success:
                    st.success("✅ Changes saved successfully!")
                    st.session_state.tm_edit_node_id = None
                    st.rerun()
                else:
                    st.error(f"Failed to update: {res}")
        st.markdown("---")

# ==============================================================================
# 9. DUAL SYNCHRONIZED VIEWS: TABS (MASTER SHEET vs ORG CHART vs EXPORT)
# ==============================================================================
view_tab_table, view_tab_graph, view_tab_export = st.tabs([
    "📋 Talent Mapping Master Sheet",
    "🌳 Visual Org Hierarchy Chart",
    "📥 Export & Intelligence Report"
])

# ------------------------------------------------------------------------------
# TAB 1: TALENT MAPPING MASTER SHEET (EXACT DB COLUMNS + SAVE SYNC)
# ------------------------------------------------------------------------------
with view_tab_table:
    st.markdown("### 📋 Talent Mapping Master Sheet")
    st.caption("You can edit cells directly, add new rows, or import from an Excel sheet below. Click **'💾 Save Changes to Database'** to save your updates.")

    # --------------------------------------------------------------------------
    # SMART EXCEL IMPORT & DIFFERENTIAL SYNCHRONIZATION EXPANDER
    # --------------------------------------------------------------------------
    with st.expander("📤 **Import & Sync from Excel File (Line-by-Line Differential Update)**", expanded=False):
        imp_col1, imp_col2 = st.columns([1.5, 2.5])
        with imp_col1:
            template_bytes = generate_sample_import_template()
            st.download_button(
                label="📥 Download Standard Import Template (.xlsx)",
                data=template_bytes,
                file_name="Talent_Mapping_Import_Template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            st.caption("Use this template to prepare or format candidate records in Excel.")

        with imp_col2:
            uploaded_excel = st.file_uploader(
                "Choose Excel or CSV file to import & sync",
                type=["xlsx", "xls", "csv"],
                key="talent_excel_uploader"
            )

        if uploaded_excel is not None:
            diff_list, actions, err = parse_and_diff_excel(uploaded_excel.getvalue(), uploaded_excel.name, raw_mappings)
            
            if err:
                st.error(f"❌ {err}")
            elif not diff_list:
                st.warning("No valid candidate rows detected in the uploaded file.")
            else:
                new_count = len([d for d in diff_list if "New" in d["Status"]])
                update_count = len([d for d in diff_list if "Updated" in d["Status"]])
                identical_count = len([d for d in diff_list if "Identical" in d["Status"]])
                total_in_file = len(diff_list)

                st.markdown("#### 📊 Line-by-Line Inspection Summary")
                sum_c1, sum_c2, sum_c3, sum_c4 = st.columns(4)
                sum_c1.metric("📄 Total Lines in File", total_in_file)
                sum_c2.metric("🟢 New Records (To Insert)", new_count)
                sum_c3.metric("🟡 Updates (Excel Newer)", update_count)
                sum_c4.metric("⚪ In-Sync (Identical)", identical_count)

                # Review Table
                df_diff_view = pd.DataFrame(diff_list)
                st.dataframe(df_diff_view, use_container_width=True, hide_index=True)

                if new_count > 0 or update_count > 0:
                    st.markdown("##### 🚀 Ready to synchronize updates?")
                    apply_sync_btn = st.button(
                        f"🚀 Apply & Sync {new_count + update_count} Changes to Database",
                        type="primary",
                        use_container_width=True,
                        key="apply_excel_sync_btn"
                    )

                    if apply_sync_btn:
                        sync_success = 0
                        sync_errors = []
                        with st.spinner("Synchronizing changes with database..."):
                            for action_type, m_id, payload in actions:
                                if action_type == "insert":
                                    ok, res = insert_talent_mapping(payload)
                                    if ok:
                                        sync_success += 1
                                    else:
                                        sync_errors.append(f"Insert {payload.get('candidate_name')}: {res}")
                                elif action_type == "update" and m_id:
                                    ok, res = update_talent_mapping(m_id, payload)
                                    if ok:
                                        sync_success += 1
                                    else:
                                        sync_errors.append(f"Update ID {m_id}: {res}")

                        if sync_errors:
                            st.error(f"Encountered {len(sync_errors)} errors during import:")
                            for e in sync_errors[:5]:
                                st.write(f"- {e}")
                        else:
                            st.success(f"🎉 Successfully synchronized {sync_success} records from Excel into the database!")
                            st.rerun()
                else:
                    st.info("✅ All records in your uploaded Excel file are already 100% up-to-date and identical with the database.")

    st.markdown("---")

    # --------------------------------------------------------------------------
    # MASTER SPREADSHEET TABLE (INLINE EDITING + AUTO-ID ASSIGNMENT)
    # --------------------------------------------------------------------------
    if not raw_mappings:
        st.info("No talent records in database yet. Add records using the form above or enter them in the table below.")

    # Build DataFrame matching exact DB fields + Reports To Name
    table_rows = []
    for m in filtered_mappings:
        rep_id = m.get("reports_to_id")
        table_rows.append({
            "mapping_id": m.get("mapping_id"),
            "company_type": m.get("company_type") or "Chemicals",
            "company_name": m.get("company_name") or "",
            "candidate_name": m.get("candidate_name") or "",
            "designation": m.get("designation") or "",
            "location": m.get("location") or "",
            "experience": m.get("experience") or "",
            "current_ctc": float(m.get("current_ctc")) if m.get("current_ctc") is not None else None,
            "expected_ctc": float(m.get("expected_ctc")) if m.get("expected_ctc") is not None else None,
            "contact_number": clean_phone_number(m.get("contact_number")),
            "email_id": m.get("email_id") or "",
            "comments": m.get("comments") or "",
            "reports_to_id": rep_id
        })

    df_talent = pd.DataFrame(table_rows)
    if df_talent.empty:
        df_talent = pd.DataFrame(columns=[
            "mapping_id", "company_type", "company_name", "candidate_name",
            "designation", "location", "experience", "current_ctc",
            "expected_ctc", "contact_number", "email_id", "comments", "reports_to_id"
        ])

    # Data Editor Configuration
    column_config = {
        "mapping_id": st.column_config.NumberColumn("ID (Auto)", help="Auto-generated sequential ID assigned on save", disabled=True, width="small"),
        "company_type": st.column_config.TextColumn("Type *", help="Company type/sector (e.g. Seeds, Chemicals, Fertilizer, Bio-Tech, Renewable, Logistics)", required=True, width="medium"),
        "company_name": st.column_config.TextColumn("Current Company *", required=True, width="medium"),
        "candidate_name": st.column_config.TextColumn("Candidate Name *", required=True, width="medium"),
        "designation": st.column_config.TextColumn("Designation *", required=True, width="medium"),
        "location": st.column_config.TextColumn("Location", width="medium"),
        "experience": st.column_config.TextColumn("Experience", width="small"),
        "current_ctc": st.column_config.NumberColumn("Current CTC (₹)", format="₹ %.2f", width="medium"),
        "expected_ctc": st.column_config.NumberColumn("Expected CTC (₹)", format="₹ %.2f", width="medium"),
        "contact_number": st.column_config.TextColumn("Contact Number", width="medium"),
        "email_id": st.column_config.TextColumn("Email ID", width="medium"),
        "comments": st.column_config.TextColumn("Comments", width="large"),
        "reports_to_id": st.column_config.NumberColumn("Reports To (Manager ID)", width="small")
    }

    # Render Interactive Data Editor
    edited_df = st.data_editor(
        df_talent,
        column_config=column_config,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="talent_mapping_data_editor"
    )

    t_save_col1, t_save_col2 = st.columns([2, 5])
    with t_save_col1:
        save_table_btn = st.button("💾 Save Changes to Database", type="primary", use_container_width=True)

    if save_table_btn:
        save_errors = []
        save_success_count = 0
        
        # 1. Detect Deleted Rows
        orig_ids = set(df_talent["mapping_id"].dropna().astype(int))
        edited_ids = set(edited_df["mapping_id"].dropna().astype(int)) if not edited_df.empty and "mapping_id" in edited_df.columns else set()
        deleted_ids = orig_ids - edited_ids
        
        for d_id in deleted_ids:
            ok, msg = delete_talent_mapping(d_id)
            if not ok:
                save_errors.append(f"Failed to delete ID {d_id}: {msg}")

        # 2. Iterate and Save / Update rows
        if not edited_df.empty:
            for _, row in edited_df.iterrows():
                m_id = row.get("mapping_id")
                comp_name = str(row.get("company_name") or "").strip()
                cand_name = str(row.get("candidate_name") or "").strip()
                desig = str(row.get("designation") or "").strip()

                if not comp_name or not cand_name or not desig:
                    continue  # Skip incomplete blank rows

                rep_id_val = row.get("reports_to_id")
                if pd.isna(rep_id_val) or rep_id_val == 0 or rep_id_val == "":
                    rep_id_val = None
                else:
                    try:
                        rep_id_val = int(rep_id_val)
                    except Exception:
                        rep_id_val = None

                curr_ctc_val = row.get("current_ctc")
                exp_ctc_val = row.get("expected_ctc")

                row_payload = {
                    "company_type": str(row.get("company_type") or "Chemicals").strip(),
                    "company_name": comp_name,
                    "candidate_name": cand_name,
                    "designation": desig,
                    "location": str(row.get("location") or "").strip(),
                    "experience": str(row.get("experience") or "").strip(),
                    "current_ctc": float(curr_ctc_val) if pd.notna(curr_ctc_val) and float(curr_ctc_val) > 0 else None,
                    "expected_ctc": float(exp_ctc_val) if pd.notna(exp_ctc_val) and float(exp_ctc_val) > 0 else None,
                    "contact_number": clean_phone_number(row.get("contact_number")),
                    "email_id": str(row.get("email_id") or "").strip(),
                    "comments": str(row.get("comments") or "").strip(),
                    "reports_to_id": rep_id_val
                }

                if pd.notna(m_id) and int(m_id) > 0:
                    # Update existing record
                    ok, res = update_talent_mapping(int(m_id), row_payload)
                    if ok:
                        save_success_count += 1
                    else:
                        save_errors.append(f"Row {cand_name}: {res}")
                else:
                    # New Insert -> Database auto-generates sequential ID
                    ok, res = insert_talent_mapping(row_payload)
                    if ok:
                        save_success_count += 1
                    else:
                        save_errors.append(f"New Row {cand_name}: {res}")

        if save_errors:
            st.error(f"Encountered {len(save_errors)} errors during save:")
            for err in save_errors[:5]:
                st.write(f"- {err}")
        else:
            st.success(f"✅ Successfully synchronized all changes with the database!")
            st.rerun()

# ------------------------------------------------------------------------------
# TAB 2: VISUAL ORG HIERARCHY CHART
# ------------------------------------------------------------------------------
@st.dialog("➕ Add Direct Report", width="large")
def show_add_direct_report_dialog(manager_record):
    st.markdown(f"**👑 Reporting Manager:** `👤 {manager_record.get('candidate_name')}` ({manager_record.get('designation')}) • `🏢 {manager_record.get('company_name')}`")
    
    with st.form("dialog_add_direct_report_form"):
        d_c1, d_c2 = st.columns(2)
        with d_c1:
            d_name = st.text_input("Candidate Name *", placeholder="e.g. Candidate D")
        with d_c2:
            d_desig = st.text_input("Designation / Role *", placeholder="e.g. Assistant Plant Manager")
            
        d_c3, d_c4 = st.columns(2)
        with d_c3:
            d_loc = st.text_input("Location", value=manager_record.get("location") or "", placeholder="e.g. Mumbai, Ankleshwar")
        with d_c4:
            d_exp = st.text_input("Experience", placeholder="e.g. 10 Years")
            
        d_c5, d_c6 = st.columns(2)
        with d_c5:
            d_curr_ctc = st.number_input("Current CTC (₹)", min_value=0.0, step=50000.0, format="%.2f")
        with d_c6:
            d_exp_ctc = st.number_input("Expected CTC (₹) [Optional]", min_value=0.0, step=50000.0, format="%.2f")
            
        d_c7, d_c8 = st.columns(2)
        with d_c7:
            d_contact = st.text_input("Contact Number", placeholder="e.g. 9876543210")
        with d_c8:
            d_email = st.text_input("Email ID", placeholder="e.g. candidate@example.com")
            
        d_comments = st.text_input("Comments / Notes", placeholder="e.g. Key technical hire reporting directly to manager")
        
        save_d_btn = st.form_submit_button("💾 Save Direct Report", type="primary", use_container_width=True)
            
        if save_d_btn:
            if not d_name.strip():
                st.error("Please enter Candidate Name.")
            elif not d_desig.strip():
                st.error("Please enter Designation.")
            else:
                payload = {
                    "company_type": manager_record.get("company_type") or "Chemicals",
                    "company_name": manager_record.get("company_name") or "",
                    "candidate_name": d_name.strip(),
                    "designation": d_desig.strip(),
                    "location": d_loc.strip(),
                    "experience": d_exp.strip(),
                    "current_ctc": d_curr_ctc if d_curr_ctc > 0 else None,
                    "expected_ctc": d_exp_ctc if d_exp_ctc > 0 else None,
                    "contact_number": clean_phone_number(d_contact),
                    "email_id": d_email.strip(),
                    "comments": d_comments.strip(),
                    "reports_to_id": manager_record.get("mapping_id"),
                    "created_by": st.session_state.get("user_id"),
                    "created_by_name": st.session_state.get("user_name")
                }
                ok, res = insert_talent_mapping(payload)
                if ok:
                    st.success(f"✅ Successfully added {d_name} under {manager_record.get('candidate_name')}!")
                    st.rerun()
                else:
                    st.error(f"Error: {res}")


@st.dialog("✏️ Edit Candidate Details", width="large")
def show_edit_candidate_dialog(edit_record, comp_records):
    st.markdown(f"### ✏️ Edit Candidate: **{edit_record.get('candidate_name')}**")
    
    with st.form("dialog_edit_candidate_form"):
        e_c1, e_c2 = st.columns(2)
        with e_c1:
            e_name = st.text_input("Candidate Name *", value=edit_record.get("candidate_name") or "")
        with e_c2:
            e_desig = st.text_input("Designation / Role *", value=edit_record.get("designation") or "")
            
        e_c3, e_c4 = st.columns(2)
        with e_c3:
            e_loc = st.text_input("Location", value=edit_record.get("location") or "")
        with e_c4:
            e_exp = st.text_input("Experience", value=edit_record.get("experience") or "")
            
        e_c5, e_c6 = st.columns(2)
        with e_c5:
            e_curr_ctc = st.number_input("Current CTC (₹)", min_value=0.0, value=float(edit_record.get("current_ctc") or 0.0), step=50000.0, format="%.2f")
        with e_c6:
            e_exp_ctc = st.number_input("Expected CTC (₹)", min_value=0.0, value=float(edit_record.get("expected_ctc") or 0.0), step=50000.0, format="%.2f")
            
        e_c7, e_c8 = st.columns(2)
        with e_c7:
            e_contact = st.text_input("Contact Number", value=clean_phone_number(edit_record.get("contact_number") or ""))
        with e_c8:
            e_email = st.text_input("Email ID", value=edit_record.get("email_id") or "")
            
        # Manager selector
        eligible_mgrs = [m for m in comp_records if m.get("mapping_id") != edit_record.get("mapping_id")]
        mgr_opts = [("None (Top-Level Leader / Root)", None)]
        curr_mgr_idx = 0
        for idx, cand in enumerate(eligible_mgrs):
            mgr_opts.append((f"👤 {cand.get('candidate_name')} ({cand.get('designation')})", cand.get("mapping_id")))
            if cand.get("mapping_id") == edit_record.get("reports_to_id"):
                curr_mgr_idx = idx + 1
                
        e_mgr_tuple = st.selectbox("👑 Reports To", mgr_opts, index=curr_mgr_idx, format_func=lambda x: x[0])
        e_comments = st.text_input("Comments / Notes", value=edit_record.get("comments") or "")
        
        save_e_btn = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)
            
        if save_e_btn:
            if not e_name.strip():
                st.error("Please enter Candidate Name.")
            elif not e_desig.strip():
                st.error("Please enter Designation.")
            else:
                payload = {
                    "candidate_name": e_name.strip(),
                    "designation": e_desig.strip(),
                    "location": e_loc.strip(),
                    "experience": e_exp.strip(),
                    "current_ctc": e_curr_ctc if e_curr_ctc > 0 else None,
                    "expected_ctc": e_exp_ctc if e_exp_ctc > 0 else None,
                    "contact_number": clean_phone_number(e_contact),
                    "email_id": e_email.strip(),
                    "comments": e_comments.strip(),
                    "reports_to_id": e_mgr_tuple[1]
                }
                ok, res = update_talent_mapping(edit_record.get("mapping_id"), payload)
                if ok:
                    st.success("✅ Updated successfully!")
                    st.rerun()
                else:
                    st.error(f"Error: {res}")


with view_tab_graph:
    if not filtered_mappings:
        st.info("No talent records found matching the selected filters. Use the form above to map candidates!")
    else:
        # Unique companies present in current view
        companies_in_view = sorted(list(set(m.get("company_name") for m in filtered_mappings if m.get("company_name"))))
        
        company_view_options = ["🌐 All Companies (Unified Canvas)"] + companies_in_view
        
        selected_org_company = st.selectbox(
            "🏢 Select Company Org Chart to View",
            company_view_options,
            index=0,
            key="org_chart_company_selector"
        )
        
        if selected_org_company == "🌐 All Companies (Unified Canvas)":
            comp_records = filtered_mappings
            comp_type = "Multi-Sector"
            display_title = "All Companies"
        else:
            comp_records = [m for m in filtered_mappings if m.get("company_name") == selected_org_company]
            comp_type = comp_records[0].get("company_type", "Chemicals") if comp_records else "Chemicals"
            display_title = selected_org_company

        # Render Interactive Org Canvas with 2D Pan-and-Zoom
        org_chart_html = generate_org_hierarchy_chart(display_title, comp_type, comp_records, available_types)
        components.html(org_chart_html, height=760, scrolling=True)

        # Quick Actions Toolbar for Selected Company / View
        st.markdown("#### ⚡ Quick Actions on Candidates")
        act_col_sel, act_col_b1, act_col_b2, act_col_b3 = st.columns([3, 1.5, 1.5, 1.5])
        
        cand_choice_map = {f"👤 {m['candidate_name']} ({m['designation']}) - {m.get('company_name', '')}": m['mapping_id'] for m in comp_records}
        
        with act_col_sel:
            selected_cand_label = st.selectbox("Select Candidate", list(cand_choice_map.keys()), key="wd_cand_action_selector")
            target_mapping_id = cand_choice_map[selected_cand_label] if selected_cand_label else None

        with act_col_b1:
            st.write("")
            st.write("")
            if st.button("➕ Add Direct Report", use_container_width=True):
                if target_mapping_id:
                    mgr_rec = next((m for m in comp_records if m.get("mapping_id") == target_mapping_id), None)
                    if mgr_rec:
                        show_add_direct_report_dialog(mgr_rec)
                    else:
                        st.warning("Candidate not found.")
                else:
                    st.warning("Please select a candidate first.")

        with act_col_b2:
            st.write("")
            st.write("")
            if st.button("👁️ View 360 Intel", use_container_width=True):
                if target_mapping_id:
                    cand_rec = next((m for m in comp_records if m.get("mapping_id") == target_mapping_id), None)
                    if cand_rec:
                        show_candidate_dossier_dialog(cand_rec, comp_records)
                    else:
                        st.warning("Candidate not found.")
                else:
                    st.warning("Please select a candidate first.")

        with act_col_b3:
            st.write("")
            st.write("")
            if st.button("🚚 Move / Transfer", use_container_width=True):
                if target_mapping_id:
                    cand_rec = next((m for m in comp_records if m.get("mapping_id") == target_mapping_id), None)
                    if cand_rec:
                        show_move_candidate_dialog(cand_rec, comp_records)
                    else:
                        st.warning("Candidate not found.")
                else:
                    st.warning("Please select a candidate first.")



# ------------------------------------------------------------------------------
# TAB 3: EXPORT & BUSINESS INTELLIGENCE REPORT
# ------------------------------------------------------------------------------
with view_tab_export:
    st.markdown("### 📥 Talent & Business Intelligence Reports")
    st.caption("Generate, visualize, and export market talent intelligence, competitor hierarchies, and executive compensation dossiers.")

    if not raw_mappings:
        st.info("No talent mapping records found in the database. Add candidates via Master Sheet or Org Chart to generate reports!")
    else:
        # Export Filters
        all_export_companies = sorted(list(set(m.get("company_name") for m in raw_mappings if m.get("company_name"))))
        all_export_types = sorted(list(set(m.get("company_type") for m in raw_mappings if m.get("company_type"))))

        f_col1, f_col2, f_col3 = st.columns([1.5, 1.5, 2])
        with f_col1:
            exp_sel_comp = st.selectbox("🏢 Filter Company", ["All Companies"] + all_export_companies, key="exp_report_company_sel")
        with f_col2:
            exp_sel_type = st.selectbox("🏷️ Filter Sector / Type", ["All Sectors"] + all_export_types, key="exp_report_type_sel")
        with f_col3:
            exp_search_q = st.text_input("🔍 Search Keyword (Name / Role / City)", placeholder="e.g. Operations, Mumbai, Vice President", key="exp_report_search_q")

        # Filter the dataset
        export_dataset = raw_mappings
        if exp_sel_comp != "All Companies":
            export_dataset = [m for m in export_dataset if m.get("company_name") == exp_sel_comp]
        if exp_sel_type != "All Sectors":
            export_dataset = [m for m in export_dataset if m.get("company_type") == exp_sel_type]
        if exp_search_q.strip():
            sq = exp_search_q.strip().lower()
            export_dataset = [
                m for m in export_dataset
                if sq in (m.get("candidate_name") or "").lower()
                or sq in (m.get("designation") or "").lower()
                or sq in (m.get("location") or "").lower()
                or sq in (m.get("company_name") or "").lower()
                or sq in (m.get("comments") or "").lower()
            ]

        # Top Executive Metrics
        total_exp_cands = len(export_dataset)
        unique_exp_comps = len(set(m.get("company_name") for m in export_dataset if m.get("company_name")))
        top_leaders_count = len([m for m in export_dataset if not m.get("reports_to_id")])
        cands_with_ctc = len([m for m in export_dataset if m.get("current_ctc") and float(m.get("current_ctc")) > 0])

        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        m_c1.metric("👥 Candidates in Report", total_exp_cands)
        m_c2.metric("🏢 Companies Covered", unique_exp_comps)
        m_c3.metric("👑 Top-Level Leaders", top_leaders_count)
        m_c4.metric("💰 CTC Disclosed Headcount", cands_with_ctc)

        st.markdown("---")

        # Build Export DataFrame with reporting manager names
        id_to_name_map = {r["mapping_id"]: f"{r['candidate_name']} ({r.get('designation', '')})" for r in raw_mappings if r.get("mapping_id")}
        
        table_rows = []
        for idx, r in enumerate(export_dataset, 1):
            mgr_label = id_to_name_map.get(r.get("reports_to_id"), "👑 Top-Level Leader / Root") if r.get("reports_to_id") else "👑 Top-Level Leader / Root"
            c_ctc = float(r.get("current_ctc")) if r.get("current_ctc") is not None else None
            e_ctc = float(r.get("expected_ctc")) if r.get("expected_ctc") is not None else None
            
            table_rows.append({
                "S.No": idx,
                "Candidate ID": r.get("mapping_id"),
                "Candidate Name": r.get("candidate_name", ""),
                "Designation": r.get("designation", ""),
                "Company Name": r.get("company_name", ""),
                "Sector / Type": r.get("company_type", "Chemicals"),
                "Reporting Manager": mgr_label,
                "Location": r.get("location", "N/A"),
                "Experience": r.get("experience", "N/A"),
                "Current CTC (₹)": c_ctc,
                "Expected CTC (₹)": e_ctc,
                "Contact Number": clean_phone_number(r.get("contact_number")),
                "Email Address": r.get("email_id", ""),
                "Recruiter Remarks / Intel": r.get("comments", ""),
                "Mapped Date": str(r.get("created_on", ""))[:10] if r.get("created_on") else ""
            })

        df_export = pd.DataFrame(table_rows)

        # Download Action Bar
        st.markdown("#### ⚡ Download Intelligence Reports")
        d_col1, d_col2, d_col3 = st.columns([2, 2, 2])

        # 1. Excel Export Generation (.xlsx)
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Talent Mapping Intel")
        excel_bytes = excel_buffer.getvalue()

        with d_col1:
            st.download_button(
                label="📥 Download Excel Report (.xlsx)",
                data=excel_bytes,
                file_name=f"Talent_Mapping_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

        # 2. CSV Export (.csv)
        csv_bytes = df_export.to_csv(index=False).encode("utf-8")
        with d_col2:
            st.download_button(
                label="📄 Download CSV (.csv)",
                data=csv_bytes,
                file_name=f"Talent_Mapping_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        with d_col3:
            sample_template_bytes = generate_sample_import_template()
            st.download_button(
                label="📋 Download Standard Template (.xlsx)",
                data=sample_template_bytes,
                file_name="Talent_Mapping_Import_Template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        st.markdown("---")

        # Visual Market Intelligence Charts
        if total_exp_cands > 0:
            st.markdown("#### 📊 Market Intelligence & Talent Distribution Analytics")
            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                # Company-wise talent distribution
                comp_counts = df_export["Company Name"].value_counts().reset_index()
                comp_counts.columns = ["Company Name", "Mapped Candidates"]
                fig_comp = px.bar(
                    comp_counts,
                    x="Company Name",
                    y="Mapped Candidates",
                    title="🏢 Talent Headcount by Competitor / Company",
                    color="Mapped Candidates",
                    color_continuous_scale="Viridis",
                    text="Mapped Candidates"
                )
                fig_comp.update_layout(
                    template="plotly_dark",
                    margin=dict(l=20, r=20, t=40, b=20),
                    height=320
                )
                fig_comp.update_traces(textposition="outside")
                st.plotly_chart(fig_comp, use_container_width=True)

            with chart_col2:
                # Sector / Type Breakdown
                type_counts = df_export["Sector / Type"].value_counts().reset_index()
                type_counts.columns = ["Sector", "Count"]
                fig_type = px.pie(
                    type_counts,
                    names="Sector",
                    values="Count",
                    title="🏷️ Talent Concentration by Sector / Industry",
                    hole=0.45,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_type.update_layout(
                    template="plotly_dark",
                    margin=dict(l=20, r=20, t=40, b=20),
                    height=320
                )
                st.plotly_chart(fig_type, use_container_width=True)

        # Live Data Table Preview
        st.markdown("#### 👁️ Report Preview & Detailed Talent Roster")
        st.dataframe(
            df_export,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Current CTC (₹)": st.column_config.NumberColumn("Current CTC", format="₹%d"),
                "Expected CTC (₹)": st.column_config.NumberColumn("Expected CTC", format="₹%d"),
                "Contact Number": st.column_config.TextColumn("Phone"),
                "Email Address": st.column_config.TextColumn("Email"),
                "Candidate ID": st.column_config.NumberColumn("ID", width="small")
            }
        )
