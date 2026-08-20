from supabase import create_client
from dotenv import load_dotenv
import streamlit as st
import os

load_dotenv()

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

SUPABASE_URL = get_secret("SUPABASE_URL", "https://placeholder-url.supabase.co")
SUPABASE_KEY = get_secret("SUPABASE_KEY", "placeholder-key")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)