import os
import re
import io
import time
import requests
from dotenv import load_dotenv
import streamlit as st
from db import supabase

try:
    import msal
except ImportError:
    msal = None

load_dotenv()

# ==============================================================================
# MICROSOFT GRAPH ONEDRIVE CONFIGURATION (1 TB CLOUD STORAGE)
# ==============================================================================
def get_secret_val(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if val:
        return val
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default

MICROSOFT_CLIENT_ID = get_secret_val("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = get_secret_val("MICROSOFT_CLIENT_SECRET", "")
MICROSOFT_TENANT_ID = get_secret_val("MICROSOFT_TENANT_ID", "common")
MICROSOFT_REFRESH_TOKEN = get_secret_val("MICROSOFT_REFRESH_TOKEN", "")

# In-memory token cache to minimize network calls
_cached_msal_token = None
_cached_token_expiry = 0

def get_onedrive_access_token() -> str:
    """
    Returns a valid Microsoft Graph access token using the long-lived refresh token.
    Caches the token in memory until 5 minutes before expiry.
    """
    global _cached_msal_token, _cached_token_expiry
    now = time.time()
    if _cached_msal_token and now < _cached_token_expiry - 300:
        return _cached_msal_token

    if not msal or not MICROSOFT_REFRESH_TOKEN:
        return None

    try:
        app = msal.ConfidentialClientApplication(
            MICROSOFT_CLIENT_ID,
            client_credential=MICROSOFT_CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}"
        )
        res = app.acquire_token_by_refresh_token(
            MICROSOFT_REFRESH_TOKEN,
            scopes=["Files.ReadWrite.All", "User.Read"]
        )
        if "access_token" in res:
            _cached_msal_token = res["access_token"]
            _cached_token_expiry = now + int(res.get("expires_in", 3600))
            return _cached_msal_token
    except Exception:
        pass
    return None


def _get_storage_base_dir() -> str:
    """
    Single source of truth for the local/OneDrive storage root.
    Reads from environment variable ATS_STORAGE_DIR or LOCAL_STORAGE_PATH.
    Defaults to C:/Users/dell/Documents/OneDrive/Apps/ATS_Storage.
    """
    env_dir = get_secret_val("ATS_STORAGE_DIR") or get_secret_val("LOCAL_STORAGE_PATH")
    if env_dir and str(env_dir).strip():
        base = str(env_dir).strip()
    else:
        # Default local storage location
        base = r"C:\Users\dell\Documents\OneDrive\Apps\ATS_Storage"
    
    try:
        os.makedirs(base, exist_ok=True)
        return os.path.abspath(base)
    except Exception:
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


def _upload_to_onedrive_cloud(rel_path: str, file_bytes: bytes) -> bool:
    """Uploads file content directly to Apps/ATS_Storage in Admin OneDrive via Microsoft Graph API."""
    token = get_onedrive_access_token()
    if not token:
        return False
    try:
        clean_path = rel_path.replace("\\", "/").strip("/")
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/Apps/ATS_Storage/{clean_path}:/content"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": get_mime_type(clean_path)
        }
        res = requests.put(url, headers=headers, data=file_bytes, timeout=30)
        return res.status_code in [200, 201]
    except Exception:
        return False


def _download_from_onedrive_cloud(rel_path: str) -> bytes:
    """Downloads file content directly from Apps/ATS_Storage in Admin OneDrive via Microsoft Graph API."""
    token = get_onedrive_access_token()
    if not token:
        return None
    try:
        clean_path = rel_path.replace("\\", "/").strip("/")
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/Apps/ATS_Storage/{clean_path}:/content"
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(url, headers=headers, timeout=30)
        if res.status_code == 200:
            return res.content
    except Exception:
        pass
    return None


def save_job_document(uploaded_file, category_name: str, sub_category_name: str, job_ref: str, custom_name: str = None) -> str:
    """
    Saves a Job Document directly to Admin OneDrive Cloud (Apps/ATS_Storage) and local storage.
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
        cat = sanitize_folder_name(category_name)
        sub = sanitize_folder_name(sub_category_name)
        jr = sanitize_folder_name(job_ref)
        rel_path = f"{cat}/{sub}/{jr}/Job_Documents/{safe_name}"

        # 1. Upload to Admin OneDrive Cloud at Apps/ATS_Storage (1 TB Storage)
        _upload_to_onedrive_cloud(rel_path, file_bytes)

        # 2. Upload to Supabase Storage Backup
        try:
            supabase.storage.from_("job_documents").upload(safe_name, file_bytes, {"upsert": "true"})
        except Exception:
            pass

        # 3. Save to Local Disk if writable
        try:
            abs_path = os.path.join(dirs["job_documents_dir"], safe_name)
            with open(abs_path, "wb") as f:
                f.write(file_bytes)
            flat_path = os.path.join(JOB_DOCS_DIR, safe_name)
            with open(flat_path, "wb") as f:
                f.write(file_bytes)
        except Exception:
            pass

        return rel_path

    except Exception as e:
        st.error(f"Storage Save Error (Job Doc): {str(e)}")
        return None


def save_candidate_resume(uploaded_file, category_name: str, sub_category_name: str, job_ref: str, custom_name: str = None) -> str:
    """
    Saves a Candidate Resume directly to Admin OneDrive Cloud (Apps/ATS_Storage) and local storage.
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
        cat = sanitize_folder_name(category_name)
        sub = sanitize_folder_name(sub_category_name)
        jr = sanitize_folder_name(job_ref)
        rel_path = f"{cat}/{sub}/{jr}/Resumes/{safe_name}"

        # 1. Upload to Admin OneDrive Cloud at Apps/ATS_Storage (1 TB Storage)
        _upload_to_onedrive_cloud(rel_path, file_bytes)

        # 2. Upload to Supabase Storage Backup
        try:
            supabase.storage.from_("Resume").upload(safe_name, file_bytes, {"upsert": "true"})
        except Exception:
            pass

        # 3. Save to Local Disk if writable
        try:
            abs_path = os.path.join(dirs["resumes_dir"], safe_name)
            with open(abs_path, "wb") as f:
                f.write(file_bytes)
            flat_path = os.path.join(RESUMES_DIR, safe_name)
            with open(flat_path, "wb") as f:
                f.write(file_bytes)
        except Exception:
            pass

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
    Reads and returns file bytes:
    1. Checks local disk / OneDrive folder (C:/Users/dell/Documents/OneDrive/Apps/ATS_Storage).
    2. If not found locally (Streamlit Cloud or non-synced machine), downloads directly from Admin OneDrive Cloud (Apps/ATS_Storage).
    3. Fallback to Supabase Cloud Storage.
    """
    if not path_or_filename:
        return None
        
    # 1. Check Local / OneDrive Disk
    abs_path = resolve_file_path(path_or_filename, category)
    if abs_path and os.path.exists(abs_path):
        try:
            with open(abs_path, "rb") as f:
                return f.read()
        except Exception:
            pass

    # 2. Download from Admin OneDrive Cloud at Apps/ATS_Storage (1 TB Storage)
    clean_rel = str(path_or_filename).replace("\\", "/").strip("/")
    data = _download_from_onedrive_cloud(clean_rel)
    if not data:
        # Try with basename in flat OneDrive folders
        target_name = os.path.basename(clean_rel)
        if "job" in clean_rel.lower() or (category and "job" in str(category).lower()):
            data = _download_from_onedrive_cloud(f"job_documents/{target_name}")
        elif "legacy" in clean_rel.lower():
            data = _download_from_onedrive_cloud(f"legacy_resumes/{target_name}")
        else:
            data = _download_from_onedrive_cloud(f"resumes/{target_name}")

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

    # 3. Fallback: Download from Supabase Storage
    target_name = os.path.basename(clean_rel)
    bucket = "job_documents" if "job" in clean_rel.lower() else "Resume"
    try:
        data = supabase.storage.from_(bucket).download(target_name)
        if data:
            return data
    except Exception:
        pass

    return None


def file_exists(path_or_filename: str, category: str = None) -> bool:
    """Checks if the file exists locally, in OneDrive, or in Supabase."""
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
