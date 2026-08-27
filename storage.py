import os
import re
import io
from dotenv import load_dotenv
import streamlit as st
from db import supabase

load_dotenv()

def _get_storage_base_dir() -> str:
    """
    Single source of truth for the local/OneDrive storage root.
    Reads from environment variable ATS_STORAGE_DIR or LOCAL_STORAGE_PATH.
    Defaults to C:/ATS_Storage (or project local ./storage_data).
    """
    env_dir = os.getenv("ATS_STORAGE_DIR") or os.getenv("LOCAL_STORAGE_PATH")
    if not env_dir:
        try:
            env_dir = st.secrets.get("ATS_STORAGE_DIR") or st.secrets.get("LOCAL_STORAGE_PATH")
        except Exception:
            pass

    if env_dir and str(env_dir).strip():
        base = str(env_dir).strip()
    else:
        # Default local storage location
        base = r"C:\Users\dell\Documents\OneDrive\Apps\ATS_Storage"
    
    try:
        os.makedirs(base, exist_ok=True)
        return os.path.abspath(base)
    except Exception:
        # Fallback to local temporary storage if Windows path is not accessible (e.g. Streamlit Cloud Linux)
        fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage_data")
        os.makedirs(fallback, exist_ok=True)
        return os.path.abspath(fallback)

STORAGE_BASE_DIR = _get_storage_base_dir()

# Flat subdirectories
RESUMES_DIR = os.path.join(STORAGE_BASE_DIR, "resumes")
JOB_DOCS_DIR = os.path.join(STORAGE_BASE_DIR, "job_documents")
LEGACY_RESUMES_DIR = os.path.join(STORAGE_BASE_DIR, "legacy_resumes")

try:
    os.makedirs(RESUMES_DIR, exist_ok=True)
    os.makedirs(JOB_DOCS_DIR, exist_ok=True)
    os.makedirs(LEGACY_RESUMES_DIR, exist_ok=True)
except Exception:
    pass


def sanitize_filename(filename: str) -> str:
    """Removes special characters to ensure clean filesystem and cross-platform compatibility."""
    if not filename:
        return "document.dat"
    name, ext = os.path.splitext(filename)
    clean_name = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
    return f"{clean_name}{ext}"


def sanitize_folder_name(name: str) -> str:
    """Cleans names for safe folder creation (Category, SubCategory, JR Number)."""
    if not name or not str(name).strip():
        return "General"
    clean = re.sub(r'[/\\:*?"<>|]', '_', str(name).strip())
    clean = re.sub(r'\s+', '_', clean)
    return clean


def get_job_folder(category_name: str, sub_category_name: str, job_ref: str) -> str:
    """Returns the absolute path to a specific JR folder."""
    cat = sanitize_folder_name(category_name)
    sub = sanitize_folder_name(sub_category_name)
    jr = sanitize_folder_name(job_ref)
    folder = os.path.join(STORAGE_BASE_DIR, cat, sub, jr)
    return folder


def create_job_folder_structure(category_name: str, sub_category_name: str, job_ref: str) -> dict:
    """
    Creates the dedicated folder hierarchy for a job:
    <STORAGE_BASE_DIR>/<Category>/<SubCategory>/<JR_Number>/
        ├── Job_Documents/
        └── Resumes/
    """
    job_folder = get_job_folder(category_name, sub_category_name, job_ref)
    jd_dir = os.path.join(job_folder, "Job_Documents")
    resumes_dir = os.path.join(job_folder, "Resumes")
    try:
        os.makedirs(jd_dir, exist_ok=True)
        os.makedirs(resumes_dir, exist_ok=True)
    except Exception:
        pass
    return {
        "job_folder": job_folder,
        "job_documents_dir": jd_dir,
        "resumes_dir": resumes_dir
    }


def save_job_document(uploaded_file, category_name: str, sub_category_name: str, job_ref: str, custom_name: str = None) -> str:
    """
    Saves a Job Document both locally/OneDrive AND uploads to Supabase Cloud Storage.
    Returns the relative path for database storage.
    """
    if uploaded_file is None:
        return None
    try:
        dirs = create_job_folder_structure(category_name, sub_category_name, job_ref)
        if isinstance(uploaded_file, dict):
            original_name = custom_name or uploaded_file.get("name", "document.pdf")
            file_bytes = uploaded_file.get("bytes", b"")
        else:
            original_name = custom_name if custom_name else getattr(uploaded_file, "name", "document.pdf")
            file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()

        safe_name = sanitize_filename(original_name)
        
        # 1. Cloud Upload to Supabase Storage
        try:
            supabase.storage.from_("job_documents").upload(
                safe_name, file_bytes, {"upsert": "true"}
            )
        except Exception as cloud_err:
            pass # Non-blocking if cloud upload fails or already exists

        # 2. Local / OneDrive Save
        try:
            abs_path = os.path.join(dirs["job_documents_dir"], safe_name)
            with open(abs_path, "wb") as f:
                f.write(file_bytes)
                
            # Also save to flat folder
            flat_path = os.path.join(JOB_DOCS_DIR, safe_name)
            with open(flat_path, "wb") as f:
                f.write(file_bytes)
                
            rel_path = os.path.relpath(abs_path, STORAGE_BASE_DIR).replace("\\", "/")
            return rel_path
        except Exception:
            # If local filesystem is read-only (Streamlit Cloud), return relative cloud path
            cat = sanitize_folder_name(category_name)
            sub = sanitize_folder_name(sub_category_name)
            jr = sanitize_folder_name(job_ref)
            return f"{cat}/{sub}/{jr}/Job_Documents/{safe_name}"

    except Exception as e:
        st.error(f"Storage Save Error (Job Doc): {str(e)}")
        return None


def save_candidate_resume(uploaded_file, category_name: str, sub_category_name: str, job_ref: str, custom_name: str = None) -> str:
    """
    Saves a Candidate Resume both locally/OneDrive AND uploads to Supabase Cloud Storage.
    Returns the relative path for database storage.
    """
    if uploaded_file is None:
        return None
    try:
        dirs = create_job_folder_structure(category_name, sub_category_name, job_ref)
        if isinstance(uploaded_file, dict):
            original_name = custom_name or uploaded_file.get("name", "document.pdf")
            file_bytes = uploaded_file.get("bytes", b"")
        else:
            original_name = custom_name if custom_name else getattr(uploaded_file, "name", "document.pdf")
            file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()

        safe_name = sanitize_filename(original_name)
        
        # 1. Cloud Upload to Supabase Storage (so all cloud users can access immediately)
        try:
            supabase.storage.from_("Resume").upload(
                safe_name, file_bytes, {"upsert": "true"}
            )
        except Exception as cloud_err:
            pass

        # 2. Local / OneDrive Save
        try:
            abs_path = os.path.join(dirs["resumes_dir"], safe_name)
            with open(abs_path, "wb") as f:
                f.write(file_bytes)
                
            # Also save to flat folder
            flat_path = os.path.join(RESUMES_DIR, safe_name)
            with open(flat_path, "wb") as f:
                f.write(file_bytes)
                
            rel_path = os.path.relpath(abs_path, STORAGE_BASE_DIR).replace("\\", "/")
            return rel_path
        except Exception:
            cat = sanitize_folder_name(category_name)
            sub = sanitize_folder_name(sub_category_name)
            jr = sanitize_folder_name(job_ref)
            return f"{cat}/{sub}/{jr}/Resumes/{safe_name}"

    except Exception as e:
        st.error(f"Storage Save Error (Resume): {str(e)}")
        return None


def resolve_file_path(path_or_filename: str, category: str = None) -> str:
    """
    Resolves an absolute file path whether given a relative hierarchical path,
    an absolute path, or a legacy flat filename.
    """
    if not path_or_filename:
        return None
    
    clean_input = str(path_or_filename).strip()

    # 1. Check direct relative path from base dir
    candidate_abs = os.path.join(STORAGE_BASE_DIR, clean_input.replace("/", os.sep))
    if os.path.exists(candidate_abs):
        return candidate_abs

    # 2. Check if already an existing absolute path
    if os.path.isabs(clean_input) and os.path.exists(clean_input):
        return clean_input

    # 3. Check flat folders (resumes, job_documents, legacy_resumes)
    target_name = os.path.basename(clean_input)
    for folder in [RESUMES_DIR, JOB_DOCS_DIR, LEGACY_RESUMES_DIR]:
        flat_p = os.path.join(folder, target_name)
        if os.path.exists(flat_p):
            return flat_p

    # 4. Search recursively for filename in STORAGE_BASE_DIR (safety net)
    for root, _, files in os.walk(STORAGE_BASE_DIR):
        if target_name in files:
            return os.path.join(root, target_name)

    return candidate_abs


def read_file_bytes(path_or_filename: str, category: str = None) -> bytes:
    """
    Reads and returns file bytes. 
    First checks local disk / OneDrive. If not found (e.g. running on Cloud or unsynced PC),
    automatically downloads directly from Supabase Cloud Storage.
    """
    if not path_or_filename:
        return None
        
    # 1. Check Local / OneDrive
    abs_path = resolve_file_path(path_or_filename, category)
    if abs_path and os.path.exists(abs_path):
        try:
            with open(abs_path, "rb") as f:
                return f.read()
        except Exception:
            pass

    # 2. Hybrid Cloud Fallback: Download from Supabase Storage
    target_name = os.path.basename(str(path_or_filename).strip())
    
    # Determine bucket
    if "job_doc" in str(path_or_filename).lower() or (category and "job" in str(category).lower()):
        bucket = "job_documents"
    else:
        bucket = "Resume"

    try:
        data = supabase.storage.from_(bucket).download(target_name)
        if data:
            # Cache locally if possible
            try:
                if abs_path:
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    with open(abs_path, "wb") as f:
                        f.write(data)
            except Exception:
                pass
            return data
    except Exception:
        # Fallback to alternative bucket
        alt_bucket = "job_documents" if bucket == "Resume" else "Resume"
        try:
            data = supabase.storage.from_(alt_bucket).download(target_name)
            if data:
                return data
        except Exception:
            pass

    return None


def file_exists(path_or_filename: str, category: str = None) -> bool:
    """Checks if the file exists locally or in Supabase cloud storage."""
    if not path_or_filename:
        return False
    abs_path = resolve_file_path(path_or_filename, category)
    if abs_path and os.path.exists(abs_path):
        return True
    return bool(str(path_or_filename).strip())


def get_mime_type(filename: str) -> str:
    """Returns standard MIME type based on file extension."""
    ext = os.path.splitext(filename or "")[1].lower()
    mime_map = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    return mime_map.get(ext, "application/octet-stream")
