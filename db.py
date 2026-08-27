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
    val = os.getenv(key)
    if val:
        return val
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default

SUPABASE_URL = (
    get_secret("NEXT_PUBLIC_SUPABASE_URL")
    or get_secret("SUPABASE_URL")
    or "https://ztxnpkzcftpgnkipvqrg.supabase.co"
)
SUPABASE_KEY = (
    get_secret("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    or get_secret("SUPABASE_KEY")
    or get_secret("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    or "sb_publishable_XzS4PpHaNykCvX_jON_UTQ_N7TtYzxR"
)

_transport = SafeRetryTransport(
    max_retries=3,
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=5.0)
)
_http_client = httpx.Client(
    transport=_transport,
    timeout=httpx.Timeout(30.0, connect=10.0)
)
_options = ClientOptions(
    httpx_client=_http_client,
    postgrest_client_timeout=30
)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=_options
)

