import os
import re
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

def _get_storage_base_dir() -> str:
    """
    Single source of truth for the local/OneDrive storage root.
    Reads from environment variable ATS_STORAGE_DIR or LOCAL_STORAGE_PATH.
    Defaults to C:/ATS_Storage (or project local ./storage_data).
    """
    env_dir = os.getenv("ATS_STORAGE_DIR") or os.getenv("LOCAL_STORAGE_PATH")
    if env_dir and env_dir.strip():
        base = env_dir.strip()
    else:
        # Default local storage location
        base = r"C:\ATS_Storage"
    
    try:
        os.makedirs(base, exist_ok=True)
        return os.path.abspath(base)
    except Exception:
        # Fallback to current workspace storage_data if C:\ is not writable
        fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage_data")
        os.makedirs(fallback, exist_ok=True)
        return os.path.abspath(fallback)

STORAGE_BASE_DIR = _get_storage_base_dir()

# Legacy / Flat subdirectories fallback
RESUMES_DIR = os.path.join(STORAGE_BASE_DIR, "resumes")
JOB_DOCS_DIR = os.path.join(STORAGE_BASE_DIR, "job_documents")
LEGACY_RESUMES_DIR = os.path.join(STORAGE_BASE_DIR, "legacy_resumes")

os.makedirs(RESUMES_DIR, exist_ok=True)
os.makedirs(JOB_DOCS_DIR, exist_ok=True)
os.makedirs(LEGACY_RESUMES_DIR, exist_ok=True)


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
    os.makedirs(jd_dir, exist_ok=True)
    os.makedirs(resumes_dir, exist_ok=True)
    return {
        "job_folder": job_folder,
        "job_documents_dir": jd_dir,
        "resumes_dir": resumes_dir
    }


def save_job_document(uploaded_file, category_name: str, sub_category_name: str, job_ref: str, custom_name: str = None) -> str:
    """
    Saves a Job Document inside <Category>/<SubCategory>/<JR>/Job_Documents/
    Returns the relative path from STORAGE_BASE_DIR for database storage.
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
        abs_path = os.path.join(dirs["job_documents_dir"], safe_name)

        with open(abs_path, "wb") as f:
            f.write(file_bytes)

        # Store as standard forward-slash relative path
        rel_path = os.path.relpath(abs_path, STORAGE_BASE_DIR).replace("\\", "/")
        return rel_path
    except Exception as e:
        st.error(f"Storage Save Error (Job Doc): {str(e)}")
        return None


def save_candidate_resume(uploaded_file, category_name: str, sub_category_name: str, job_ref: str, custom_name: str = None) -> str:
    """
    Saves a Candidate Resume inside <Category>/<SubCategory>/<JR>/Resumes/
    Returns the relative path from STORAGE_BASE_DIR for database storage.
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
        abs_path = os.path.join(dirs["resumes_dir"], safe_name)

        with open(abs_path, "wb") as f:
            f.write(file_bytes)

        # Store as standard forward-slash relative path
        rel_path = os.path.relpath(abs_path, STORAGE_BASE_DIR).replace("\\", "/")
        return rel_path
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

    # 3. Check legacy flat category folders
    if category:
        cat_dir = RESUMES_DIR if "resume" in category.lower() else JOB_DOCS_DIR
        flat_path = os.path.join(cat_dir, sanitize_filename(os.path.basename(clean_input)))
        if os.path.exists(flat_path):
            return flat_path

    # 4. Search recursively for filename in STORAGE_BASE_DIR (safety net)
    target_name = os.path.basename(clean_input)
    for root, _, files in os.walk(STORAGE_BASE_DIR):
        if target_name in files:
            return os.path.join(root, target_name)

    return candidate_abs


def read_file_bytes(path_or_filename: str, category: str = None) -> bytes:
    """Reads and returns file bytes from local storage given a relative path or filename."""
    abs_path = resolve_file_path(path_or_filename, category)
    if abs_path and os.path.exists(abs_path):
        try:
            with open(abs_path, "rb") as f:
                return f.read()
        except Exception as e:
            st.error(f"Error reading file '{path_or_filename}': {str(e)}")
            return None
    return None


def file_exists(path_or_filename: str, category: str = None) -> bool:
    """Checks if the file exists in storage."""
    abs_path = resolve_file_path(path_or_filename, category)
    return bool(abs_path and os.path.exists(abs_path))


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
