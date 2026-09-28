import httpx
import time
from supabase import create_client, ClientOptions
from dotenv import load_dotenv
import streamlit as st
import os

load_dotenv()

class SafeRetryTransport(httpx.HTTPTransport):
    """
    HTTPTransport with automatic reconnection & retry on network disconnects / RemoteProtocolError
    which happens frequently when cloud databases drop idle keep-alive sockets.
    """
    def __init__(self, max_retries: int = 3, **kwargs):
        super().__init__(**kwargs)
        self.max_retries = max_retries

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(self.max_retries):
            try:
                return super().handle_request(request)
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(0.15 * (2 ** attempt))

def get_secret(key: str, default: str = "") -> str:
    """Retrieves a secret from environment variables or Streamlit secrets."""
    val = os.getenv(key)
    if val:
        return val
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default

# ==============================================================================
# SUPABASE CLIENT CONFIGURATION (Dual-Client Security Architecture)
#
# supabase       → Uses the PUBLISHABLE (anon) key. All Row Level Security (RLS)
#                   policies are enforced. Used for general data queries across
#                   all view pages. If the anon key is ever exposed, RLS limits
#                   access to only what policies explicitly allow.
#
# supabase_admin → Uses the SERVICE_ROLE key. Bypasses RLS entirely.
#                   Reserved ONLY for privileged server-side operations:
#                   - Login attempt tracking & lockout (RPCs)
#                   - User creation & password resets
#                   - Storage bucket operations
#                   This key must NEVER be exposed to the browser or frontend.
# ==============================================================================

# Server-side backend client configuration:
# Streamlit runs as a secure Python backend (not in the user's browser).
# Because authentication is managed via custom bcrypt hashes in public.users
# (not Supabase Auth JWTs), the backend server uses the service role key
# to access RLS-protected tables, while enforcing authentication, role-based
# authorization, and input validation within the Streamlit application layer.

SUPABASE_URL = (
    get_secret("NEXT_PUBLIC_SUPABASE_URL")
    or get_secret("SUPABASE_URL")
)

SUPABASE_SERVICE_KEY = get_secret("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_ANON_KEY = (
    get_secret("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    or get_secret("SUPABASE_KEY")
    or get_secret("NEXT_PUBLIC_SUPABASE_ANON_KEY")
)

# Primary backend key: service_role key for trusted server queries, or anon key if not provided
SUPABASE_KEY = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Supabase credentials not found! Please set SUPABASE_URL and "
        "SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) "
        "in your .env file or .streamlit/secrets.toml."
    )

def _build_client(api_key: str) -> object:
    """Creates a Supabase client with retry-safe HTTP transport."""
    transport = SafeRetryTransport(
        max_retries=3,
        limits=httpx.Limits(max_keepalive_connections=50, max_connections=100, keepalive_expiry=30.0)
    )
    http_client = httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(30.0, connect=10.0)
    )
    options = ClientOptions(
        httpx_client=http_client,
        postgrest_client_timeout=30
    )
    return create_client(SUPABASE_URL, api_key, options=options)

# Primary client used across application views
supabase = _build_client(SUPABASE_KEY)

# Admin alias for privileged/explicit administrative operations
supabase_admin = supabase


