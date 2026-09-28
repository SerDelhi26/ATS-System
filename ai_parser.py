import os
import re
import io
import json
import base64
import time
import threading
from datetime import datetime, date
import requests
from dotenv import load_dotenv
import streamlit as st

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import docx
except ImportError:
    docx = None

load_dotenv()

def get_gemini_keys() -> list[str]:
    """Retrieves all configured Gemini API keys (supports individual user keys & pool)."""
    keys = []
    # Check individual user variables first
    for i in range(1, 10):
        k = os.getenv(f"GEMINI_API_KEY_USER{i}")
        if not k:
            try:
                k = st.secrets.get(f"GEMINI_API_KEY_USER{i}")
            except Exception:
                pass
        if k and str(k).strip() and str(k).strip() not in keys:
            keys.append(str(k).strip())
            
    # Check pool string
    env_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or ""
    if not env_keys:
        try:
            env_keys = st.secrets.get("GEMINI_API_KEYS", "") or st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            pass

    for k in str(env_keys).split(","):
        k_clean = k.strip()
        if k_clean and k_clean not in keys:
            keys.append(k_clean)
    return keys


def get_groq_keys() -> list[str]:
    """Retrieves all configured Groq API keys (supports individual user keys & pool)."""
    keys = []
    for i in range(1, 10):
        k = os.getenv(f"GROQ_API_KEY_USER{i}")
        if not k:
            try:
                k = st.secrets.get(f"GROQ_API_KEY_USER{i}")
            except Exception:
                pass
        if k and str(k).strip() and str(k).strip() not in keys:
            keys.append(str(k).strip())

    env_keys = os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY") or ""
    if not env_keys:
        try:
            env_keys = st.secrets.get("GROQ_API_KEYS", "") or st.secrets.get("GROQ_API_KEY", "")
        except Exception:
            pass

    for k in str(env_keys).split(","):
        k_clean = k.strip()
        if k_clean and k_clean not in keys:
            keys.append(k_clean)
    return keys


def get_openrouter_keys() -> list[str]:
    """Retrieves all configured OpenRouter API keys (supports individual user keys & pool)."""
    keys = []
    for i in range(1, 10):
        k = os.getenv(f"OPENROUTER_API_KEY_USER{i}")
        if not k:
            try:
                k = st.secrets.get(f"OPENROUTER_API_KEY_USER{i}")
            except Exception:
                pass
        if k and str(k).strip() and str(k).strip() not in keys:
            keys.append(str(k).strip())

    env_keys = os.getenv("OPENROUTER_API_KEYS") or os.getenv("OPENROUTER_API_KEY") or ""
    if not env_keys:
        try:
            env_keys = st.secrets.get("OPENROUTER_API_KEYS", "") or st.secrets.get("OPENROUTER_API_KEY", "")
        except Exception:
            pass

    for k in str(env_keys).split(","):
        k_clean = k.strip()
        if k_clean and k_clean not in keys:
            keys.append(k_clean)
    return keys


# -------------------------------------------------------------
# Round-Robin Key Load Balancer & Cooldown Tracker
# -------------------------------------------------------------
_gemini_key_counter = 0
_groq_key_counter = 0
_openrouter_key_counter = 0
_counter_lock = threading.Lock()
_key_cooldowns: dict[str, float] = {}

def mark_key_rate_limited(api_key: str, cooldown_seconds: float = 60.0):
    """Marks an API key as rate-limited until now + cooldown_seconds."""
    with _counter_lock:
        _key_cooldowns[api_key] = time.time() + cooldown_seconds

def get_ordered_key_pool(keys: list[str], provider: str) -> list[tuple[int, str]]:
    """
    Returns a circular round-robin list of (1_based_index, key) for the provider.
    Distributes requests evenly across all available accounts, prioritizing keys
    that are not currently in a rate-limit cooldown.
    """
    global _gemini_key_counter, _groq_key_counter, _openrouter_key_counter
    if not keys:
        return []
    
    n = len(keys)
    with _counter_lock:
        if provider == "gemini":
            start_idx = _gemini_key_counter % n
            _gemini_key_counter += 1
        elif provider == "groq":
            start_idx = _groq_key_counter % n
            _groq_key_counter += 1
        else:
            start_idx = _openrouter_key_counter % n
            _openrouter_key_counter += 1

    # Form circular sequence of all configured keys
    circular = [((start_idx + i) % n + 1, keys[(start_idx + i) % n]) for i in range(n)]
    now = time.time()
    active_keys = [item for item in circular if _key_cooldowns.get(item[1], 0) <= now]
    cooling_keys = [item for item in circular if _key_cooldowns.get(item[1], 0) > now]
    return active_keys + cooling_keys


def extract_phone_numbers(text: str) -> list[str]:
    """
    Extracts all distinct valid 10-digit mobile numbers from text or phone string.
    Handles international codes (+91, 0091), spaces, dashes, slashes, and combined lists.
    """
    if not text:
        return []
    
    found = []
    # Split text by common multi-number delimiters
    chunks = re.split(r'[/,;|\\n\r]|(?:\s+or\s+)|\band\b|&', str(text))
    for c in chunks:
        # Strip country code (+91, 91, 0)
        c_clean = re.sub(r'^\s*(\+?91[\s\-]*)?|^0', '', c.strip())
        digits = re.sub(r'\D', '', c_clean)
        if len(digits) >= 10:
            p = digits[-10:]
            if p not in found:
                found.append(p)
                
    # If chunks didn't extract at least 2 numbers, scan globally across text
    if len(found) < 2:
        raw_matches = re.findall(r'(?:(?:\+?91[\s\-]*)?|(?:\b0))?([6-9]\d{4}[\s\-]?\d{5}|[6-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{4}|[6-9]\d{9})\b', str(text))
        for m in raw_matches:
            digits = re.sub(r'\D', '', m)
            if len(digits) >= 10:
                p = digits[-10:]
                if p not in found:
                    found.append(p)
    return found


def clean_phone(phone_str: str) -> str:
    """Extracts the first valid 10-digit mobile number from a phone string."""
    phones = extract_phone_numbers(phone_str)
    return phones[0] if phones else ""


def extract_emails(text: str) -> list[str]:
    """Extracts valid email addresses from text."""
    if not text:
        return []
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    matches = re.findall(pattern, str(text))
    valid = []
    for m in matches:
        e = m.strip().strip('.').lower()
        if e and not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.pdf', '.webp')) and e not in valid:
            valid.append(e)
    return valid


def find_company_fallback(text: str) -> str:
    """Extracts company name from text using robust heuristic patterns."""
    if not text:
        return ""
    patterns = [
        r'(?:Current\s+(?:Company|Organization|Employer)|Present\s+(?:Company|Employer|Organization)|Company(?:\s+Name)?|Current\s+Employer|Organization|Employer|Firm)\s*[:\-\–]\s*([A-Za-z0-9&.,\s\'\-]{3,60})',
        r'Working (?:at|with)\s+([A-Za-z0-9&.,\s\'\-]{3,60}?)(?:\s+as\s+|\s*[,|\n])',
        r'(?:WORK EXPERIENCE|EXPERIENCE|EMPLOYMENT HISTORY)\s*[:\n]\s*([A-Za-z0-9&.,\s\'\-]{3,60}?)(?:\s*[|\-\–]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4}|Present|Till)|\n)',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            val = m.group(1).split('\n')[0].strip(' ,-–|:')
            val = re.sub(r'^(?:is|at|in|with|for)\s+', '', val, flags=re.I).strip()
            if len(val) >= 3 and not re.match(r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Present|Till|Date|Experience|Education|Profile|Summary|Details)$', val, re.I):
                return val
    return ""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts text content directly from PDF bytes in milliseconds."""
    try:
        if pypdf is None:
            return ""
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        extracted_pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted_pages.append(t)
        return "\n".join(extracted_pages).strip()
    except Exception:
        return ""


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extracts text content directly from Word .docx bytes."""
    try:
        if docx is None:
            return ""
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text:
                        paragraphs.append(cell.text)
        return "\n".join(paragraphs).strip()
    except Exception:
        return ""


def normalize_dob(dob_raw) -> str:
    """Attempts to parse varied date strings into YYYY-MM-DD."""
    if not dob_raw:
        return ""
    dob_str = str(dob_raw).strip()
    if not dob_str or dob_str.lower() in ["none", "null", "n/a", "0"]:
        return ""
    
    formats = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
        "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
        "%d-%b-%Y", "%d-%B-%Y", "%Y/%m/%d"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(dob_str, fmt)
            curr_year = datetime.now().year
            if 1940 <= dt.year <= curr_year:
                return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    
    match = re.search(r'\b(19\d\d|20\d\d)\b', dob_str)
    if match:
        year = int(match.group(1))
        curr_year = datetime.now().year
        if 1940 <= year <= curr_year:
            return f"{year}-01-01"
            
    return ""


def compute_approx_dob(parsed: dict) -> str:
    """
    Computes candidate approx_dob (YYYY-MM-DD).
    If exact date_of_birth is present on resume, standardizes and returns it.
    Otherwise, determines birth year from 10th (-15), 12th (-17), Graduation (-22), PG (-24),
    or fallback via total experience, returning f"{inferred_year}-01-01".
    """
    # 1. Check explicit date_of_birth from resume
    raw_dob = parsed.get("date_of_birth") or parsed.get("dob")
    norm_dob = normalize_dob(raw_dob)
    if norm_dob:
        return norm_dob
        
    curr_year = datetime.now().year
    
    # 2. Check 10th / SSC year (completed at age ~15)
    tenth = int(parsed.get("tenth_passing_year", 0) or 0)
    if 1950 <= tenth <= curr_year:
        inferred_year = max(1945, min(curr_year - 15, tenth - 15))
        return f"{inferred_year}-01-01"
        
    # 3. Check 12th / HSC year (completed at age ~17)
    twelfth = int(parsed.get("twelfth_passing_year", 0) or 0)
    if 1950 <= twelfth <= curr_year:
        inferred_year = max(1945, min(curr_year - 17, twelfth - 17))
        return f"{inferred_year}-01-01"
        
    # 4. Check Graduation year (completed at age ~21-22)
    grad = int(parsed.get("graduation_year", 0) or 0)
    if 1950 <= grad <= curr_year:
        inferred_year = max(1945, min(curr_year - 20, grad - 22))
        return f"{inferred_year}-01-01"
        
    # 5. Check PG year (completed at age ~24)
    pg = int(parsed.get("pg_passing_year", 0) or 0)
    if 1950 <= pg <= curr_year:
        inferred_year = max(1945, min(curr_year - 22, pg - 24))
        return f"{inferred_year}-01-01"
        
    # 6. Fallback via total experience (Career started at approx age 22)
    exp_y = int(parsed.get("experience_years", 0) or 0)
    inferred_year = max(1945, min(curr_year - 18, curr_year - (22 + exp_y)))
    return f"{inferred_year}-01-01"


def compute_approx_age(parsed: dict) -> int:
    """
    Computes candidate dynamic age based on approx_dob.
    """
    dob_str = compute_approx_dob(parsed)
    try:
        dt = datetime.strptime(dob_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
    except Exception:
        return 25


def sanitize_parsed_output(parsed: dict, raw_text: str = "") -> dict:
    """Sanitizes and normalizes extracted fields with fallback recovery from raw text."""
    raw_gender = str(parsed.get("gender", "")).strip().capitalize()
    if raw_gender not in ["Male", "Female", "Other"]:
        raw_gender = "Not Specified"

    approx_dob = compute_approx_dob(parsed)

    # 1. Clean & enrich Email
    email = str(parsed.get("email", "")).strip().lower()
    email = re.sub(r'^(?:mailto:|email:\s*|e-mail:\s*)', '', email).strip()
    if not email or "@" not in email:
        raw_emails = extract_emails(raw_text)
        if raw_emails:
            email = raw_emails[0]

    # 2. Clean & enrich Mobile & Alternate Mobile
    raw_mobile = str(parsed.get("mobile_no", "")).strip()
    raw_alt = str(parsed.get("alternate_mobile", "")).strip()

    extracted_from_mobile = extract_phone_numbers(raw_mobile)
    extracted_from_alt = extract_phone_numbers(raw_alt)

    mobile_no = ""
    alternate_mobile = ""

    if extracted_from_mobile:
        mobile_no = extracted_from_mobile[0]
        if len(extracted_from_mobile) > 1:
            alternate_mobile = extracted_from_mobile[1]

    if not alternate_mobile and extracted_from_alt:
        alt_candidate = extracted_from_alt[0]
        if alt_candidate != mobile_no:
            alternate_mobile = alt_candidate
        elif len(extracted_from_alt) > 1:
            alternate_mobile = extracted_from_alt[1]

    # If alternate_mobile is still empty, scan raw resume text for any secondary number
    if not alternate_mobile and raw_text:
        text_phones = extract_phone_numbers(raw_text)
        for tp in text_phones:
            if tp != mobile_no:
                alternate_mobile = tp
                break

    # If mobile_no was empty but alternate exists, promote it
    if not mobile_no and alternate_mobile:
        mobile_no = alternate_mobile
        alternate_mobile = ""

    # 3. Clean & enrich Current Company
    company = str(parsed.get("current_company", "")).strip()
    company = re.sub(r'^(?:Current (?:Company|Organization)|Present (?:Company|Employer)|Company Name|Organization|Employer|Working at|Working with)\s*[:\-\–]\s*', '', company, flags=re.I).strip()
    if company.lower() in ["none", "null", "n/a", "not specified", "nil", "0", "-", "na"]:
        company = ""

    if not company and raw_text:
        fallback_comp = find_company_fallback(raw_text)
        if fallback_comp:
            company = fallback_comp

    return {
        "first_name": str(parsed.get("first_name", "")).strip(),
        "last_name": str(parsed.get("last_name", "")).strip(),
        "gender": raw_gender,
        "approx_dob": approx_dob,
        "email": email,
        "mobile_no": mobile_no,
        "alternate_mobile": alternate_mobile,
        "current_location": str(parsed.get("current_location", "")).strip(),
        "experience_years": max(0, min(40, int(parsed.get("experience_years", 0) or 0))),
        "experience_months": max(0, min(11, int(parsed.get("experience_months", 0) or 0))),
        "qualification": str(parsed.get("qualification", "")).strip(),
        "education_details": str(parsed.get("education_details", "")).strip(),
        "current_company": company,
        "current_designation": str(parsed.get("current_designation", "")).strip(),
        "current_ctc": float(parsed.get("current_ctc", 0.0) or 0.0),
        "expected_ctc": float(parsed.get("expected_ctc", 0.0) or 0.0),
        "skills": str(parsed.get("skills", "")).strip(),
    }


def _call_gemini_api(api_key: str, model: str, payload: dict, timeout: int = 15, resume_text: str = "") -> tuple[bool, dict, str]:
    """Makes a single call to the Google Gemini generateContent API with tight timeout."""
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 429:
            mark_key_rate_limited(api_key, cooldown_seconds=60.0)
            return False, {}, "RATE_LIMIT_429"
        if response.status_code == 503:
            mark_key_rate_limited(api_key, cooldown_seconds=30.0)
            return False, {}, "SERVICE_UNAVAILABLE_503"
        if response.status_code != 200:
            return False, {}, f"Gemini Error ({response.status_code}): {response.text[:200]}"

        res_json = response.json()
        candidates = res_json.get("candidates", [])
        if not candidates:
            return False, {}, "No candidates returned"

        raw_text = candidates[0]["content"]["parts"][0]["text"].strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        parsed = json.loads(raw_text.strip())
        return True, sanitize_parsed_output(parsed, raw_text=resume_text), "Success"
    except requests.exceptions.Timeout:
        return False, {}, "TIMEOUT"
    except Exception as e:
        return False, {}, str(e)


def _call_groq_api(api_key: str, model: str, system_prompt: str, resume_text: str, timeout: int = 15) -> tuple[bool, dict, str]:
    """Makes a call to Groq Cloud OpenAI-compatible chat API with tight timeout."""
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"RESUME TEXT:\n{resume_text}"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 429:
            mark_key_rate_limited(api_key, cooldown_seconds=60.0)
            return False, {}, "RATE_LIMIT_429"
        if response.status_code == 503:
            mark_key_rate_limited(api_key, cooldown_seconds=30.0)
            return False, {}, "SERVICE_UNAVAILABLE_503"
        if response.status_code != 200:
            return False, {}, f"Groq Error ({response.status_code}): {response.text[:200]}"

        res_json = response.json()
        content = res_json["choices"][0]["message"]["content"].strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        parsed = json.loads(content.strip())
        return True, sanitize_parsed_output(parsed), "Success"
    except requests.exceptions.Timeout:
        return False, {}, "TIMEOUT"
    except Exception as e:
        return False, {}, str(e)


def _call_openrouter_api(api_key: str, model: str, system_prompt: str, resume_text: str, timeout: int = 15) -> tuple[bool, dict, str]:
    """Makes a call to OpenRouter OpenAI-compatible chat API with tight timeout."""
    endpoint = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost:8501",
        "X-Title": "ATS Resume Parser"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"RESUME TEXT:\n{resume_text}"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 429:
            mark_key_rate_limited(api_key, cooldown_seconds=60.0)
            return False, {}, "RATE_LIMIT_429"
        if response.status_code != 200:
            return False, {}, f"OpenRouter Error ({response.status_code}): {response.text[:200]}"

        res_json = response.json()
        content = res_json["choices"][0]["message"]["content"].strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        parsed = json.loads(content.strip())
        return True, sanitize_parsed_output(parsed), "Success"
    except requests.exceptions.Timeout:
        return False, {}, "TIMEOUT"
    except Exception as e:
        return False, {}, str(e)


def parse_resume_with_ai(file_bytes: bytes, filename: str, mime_type: str = None) -> tuple[bool, dict, str]:
    """
    Parses a candidate resume with Multi-Key & Multi-Provider load balancing and failover:
    Groq Key Pool (Priority 1) -> Gemini Key Pool (Priority 2) -> OpenRouter Key Pool (Priority 3).
    """
    if not file_bytes:
        return False, {}, "No file content provided."

    gemini_keys = get_gemini_keys()
    groq_keys = get_groq_keys()
    openrouter_keys = get_openrouter_keys()

    if not gemini_keys and not groq_keys and not openrouter_keys:
        return False, {}, "No AI API keys configured. Please add GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY in .env or secrets.toml."

    system_prompt = """You are an expert AI Resume Parser for an enterprise ATS.
Extract candidate information from the resume into this exact JSON structure:
{
  "first_name": "Candidate's First name",
  "last_name": "Candidate's Last name (or empty string if none)",
  "gender": "Male, Female, Other, or Not Specified (inferred from salutations like Mr./Ms., pronouns, or explicitly stated personal details)",
  "date_of_birth": "Explicit Date of Birth if mentioned on resume (e.g. YYYY-MM-DD or DD/MM/YYYY or DD-Mon-YYYY) or empty string if not mentioned",
  "tenth_passing_year": 0,
  "twelfth_passing_year": 0,
  "graduation_year": 0,
  "pg_passing_year": 0,
  "email": "Email address or empty string",
  "mobile_no": "10-digit primary mobile number or empty string",
  "alternate_mobile": "Secondary contact number or empty string",
  "current_location": "Current city / state or location",
  "experience_years": 0,
  "experience_months": 0,
  "qualification": "Highest degree/qualification (e.g. B.Tech, MCA, MBA, B.Sc, Diploma, M.Tech, Graduate)",
  "education_details": "Summary of education, degrees, colleges and years",
  "current_company": "Current or most recent employer/company name",
  "current_designation": "Current or most recent job title/designation",
  "current_ctc": 0.0,
  "expected_ctc": 0.0,
  "skills": "Comma-separated key skills, frameworks, and technologies"
}

Important Rules:
1. Extract first and last names cleanly (remove titles like Mr., Ms., Dr.).
2. Extract explicit Date of Birth (DOB) if present in personal details / biodata section.
3. Extract 4-digit passing years for 10th (SSC), 12th (HSC), Graduation, or PG if mentioned in education history.
4. Determine gender accurately from salutations (Mr. -> Male, Ms./Mrs. -> Female) or resume personal section. If unknown, set "Not Specified".
5. Calculate total professional experience accurately in full years (integer) and remaining months (0-11 integer).
6. If CTC is not explicitly stated, return 0.0.
7. Extract Email accurately: Thoroughly search the header, contact info, personal details, or biodata for the candidate's email address (e.g. name@domain.com). Do not leave empty if an email exists.
8. Extract Phone & Alternate Mobile accurately: Extract primary mobile number into 'mobile_no'. If a second phone, WhatsApp number, residence telephone, or alternate number is present (or if multiple numbers are separated by '/', ',', or '&'), extract the second number into 'alternate_mobile'. Return exactly 10 digits without country code or leading 0.
9. Extract Current Company accurately: Look at the top-most or most recent position in Experience / Employment / Career History / Work History / Projects. Look for keywords like 'Present', 'Till Date', 'Current', 'Organization:', 'Company:', 'Employer:', 'Working at/with'. If not currently working, provide their most recent past employer name. Never leave 'current_company' empty if any company/organization is mentioned in work history. Return only the clean company name.
10. Output valid JSON only.
"""

    ext = os.path.splitext(filename or "")[1].lower()

    # 1. Fast Local Text Extraction
    extracted_text = ""
    if ext == ".pdf" or (mime_type and "pdf" in mime_type.lower()):
        extracted_text = extract_text_from_pdf(file_bytes)
    elif ext in [".docx", ".doc"]:
        extracted_text = extract_text_from_docx(file_bytes)
    else:
        try:
            extracted_text = file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            extracted_text = ""

    # Build Gemini Payload
    gemini_parts = [{"text": system_prompt}]
    if len(extracted_text) >= 20:
        gemini_parts.append({"text": f"DOCUMENT FILENAME: {filename}\n\nRESUME CONTENT:\n{extracted_text[:20000]}"})
    elif ext == ".pdf" or (mime_type and "pdf" in mime_type.lower()):
        b64_data = base64.b64encode(file_bytes).decode("utf-8")
        gemini_parts.append({
            "inlineData": {
                "mimeType": "application/pdf",
                "data": b64_data
            }
        })
    else:
        gemini_parts.append({"text": f"DOCUMENT: {filename}\n{file_bytes.decode('latin-1', errors='ignore')[:15000]}"})

    gemini_payload = {
        "contents": [{"parts": gemini_parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }

    errors = []
    start_time = time.time()
    MAX_OVERALL_BUDGET = 35.0  # Max total seconds before bailing out to keep UI snappy
    MAX_TOTAL_ATTEMPTS = 15    # Guaranteed budget across all configured keys
    total_attempts = 0

    def time_left():
        return max(1.0, MAX_OVERALL_BUDGET - (time.time() - start_time))

    # -------------------------------------------------------------
    # 1. PRIORITY 1: Groq Key Pool (ALL 4 keys in round-robin order)
    # -------------------------------------------------------------
    if groq_keys and extracted_text and time_left() > 2.0 and total_attempts < MAX_TOTAL_ATTEMPTS:
        env_groq_model = (os.getenv("GROQ_MODEL") or "").strip()
        if not env_groq_model:
            try:
                env_groq_model = str(st.secrets.get("GROQ_MODEL", "")).strip()
            except Exception:
                pass

        groq_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        if env_groq_model:
            if env_groq_model in groq_models:
                groq_models.remove(env_groq_model)
            groq_models.insert(0, env_groq_model)

        groq_key_pool = get_ordered_key_pool(groq_keys, "groq")

        for idx, key in groq_key_pool:
            if time_left() <= 2.0 or total_attempts >= MAX_TOTAL_ATTEMPTS:
                break
            for model in groq_models[:2]:
                rem_timeout = min(10, int(time_left()))
                if rem_timeout < 2 or total_attempts >= MAX_TOTAL_ATTEMPTS:
                    break
                total_attempts += 1
                success, data, msg = _call_groq_api(key, model, system_prompt, extracted_text, timeout=rem_timeout)
                if success:
                    return True, data, f"Resume parsed successfully via Groq AI (Key #{idx})!"
                if msg in ["RATE_LIMIT_429", "SERVICE_UNAVAILABLE_503"]:
                    errors.append(f"Groq Key #{idx} rate-limited.")
                    break  # Failover immediately to next Groq key in pool
                elif "404" in msg:
                    continue  # Try next model
                else:
                    errors.append(f"Groq Key #{idx} ({model}): {msg}")

    # -------------------------------------------------------------
    # 2. PRIORITY 2: Gemini Key Pool (ALL 4 keys - if Groq failed or non-text PDF)
    # -------------------------------------------------------------
    if gemini_keys and time_left() > 2.0 and total_attempts < MAX_TOTAL_ATTEMPTS:
        env_gemini_model = (os.getenv("GEMINI_MODEL") or "").strip()
        if not env_gemini_model:
            try:
                env_gemini_model = str(st.secrets.get("GEMINI_MODEL", "")).strip()
            except Exception:
                pass

        gemini_models = ["gemini-flash-lite-latest", "gemini-3.6-flash", "gemini-flash-latest"]
        if env_gemini_model:
            if env_gemini_model in gemini_models:
                gemini_models.remove(env_gemini_model)
            gemini_models.insert(0, env_gemini_model)

        gemini_key_pool = get_ordered_key_pool(gemini_keys, "gemini")

        for idx, key in gemini_key_pool:
            if time_left() <= 2.0 or total_attempts >= MAX_TOTAL_ATTEMPTS:
                break
            # Try primary model first, fallback to next if 503 or 404
            for model in gemini_models[:2]:
                rem_timeout = min(10, int(time_left()))
                if rem_timeout < 2 or total_attempts >= MAX_TOTAL_ATTEMPTS:
                    break
                total_attempts += 1
                success, data, msg = _call_gemini_api(key, model, gemini_payload, timeout=rem_timeout, resume_text=extracted_text)
                if success:
                    return True, data, f"Resume parsed successfully via Gemini AI (Key #{idx})!"
                if msg in ["RATE_LIMIT_429", "SERVICE_UNAVAILABLE_503"]:
                    errors.append(f"Gemini Key #{idx} rate-limited.")
                    break  # Failover immediately to next Gemini key in pool
                elif "404" in msg:
                    continue  # Model not found, try fallback model
                else:
                    errors.append(f"Gemini Key #{idx} ({model}): {msg}")

    # -------------------------------------------------------------
    # 3. PRIORITY 3: OpenRouter Key Pool (ALL 4 keys - if Groq & Gemini both failed)
    # -------------------------------------------------------------
    if openrouter_keys and extracted_text and time_left() > 2.0 and total_attempts < MAX_TOTAL_ATTEMPTS:
        openrouter_models = [
            "liquid/lfm-2.5-2.6b:free",
            "inclusionai/ling-3.0-flash-sante:free"
        ]
        openrouter_key_pool = get_ordered_key_pool(openrouter_keys, "openrouter")

        for idx, key in openrouter_key_pool:
            if time_left() <= 2.0 or total_attempts >= MAX_TOTAL_ATTEMPTS:
                break
            for model in openrouter_models[:1]:
                rem_timeout = min(12, int(time_left()))
                if rem_timeout < 2 or total_attempts >= MAX_TOTAL_ATTEMPTS:
                    break
                total_attempts += 1
                success, data, msg = _call_openrouter_api(key, model, system_prompt, extracted_text, timeout=rem_timeout)
                if success:
                    return True, data, f"Resume parsed successfully via OpenRouter AI (Key #{idx})!"
                if msg == "RATE_LIMIT_429":
                    errors.append(f"OpenRouter Key #{idx} rate-limited.")
                    break
                else:
                    errors.append(f"OpenRouter Key #{idx} ({model}): {msg}")

    err_summary = " | ".join(errors[-4:]) if errors else "AI parse timeout or provider unavailable."
    return False, {}, err_summary
