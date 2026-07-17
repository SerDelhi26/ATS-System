from supabase import create_client
from dotenv import load_dotenv
import streamlit as st
import os

load_dotenv()

SUPABASE_URL = (
    st.secrets["SUPABASE_URL"]
    if "SUPABASE_URL" in st.secrets
    else os.getenv("SUPABASE_URL")
)

SUPABASE_KEY = (
    st.secrets["SUPABASE_KEY"]
    if "SUPABASE_KEY" in st.secrets
    else os.getenv("SUPABASE_KEY")
)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)