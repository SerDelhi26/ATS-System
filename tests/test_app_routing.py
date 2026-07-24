import pytest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

@patch("db.supabase")
@patch("streamlit.secrets", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_KEY": "fake-key"})
def test_unauthenticated_routing(mock_supabase):
    """
    Test unauthenticated routing on Dashboard.
    """
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = []
    at = AppTest.from_file("pages/2_Dashboard.py")
    at.run()
    assert "logged_in" not in at.session_state or at.session_state["logged_in"] is False

@patch("streamlit.secrets", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_KEY": "fake-key"})
def test_home_page_rendering():
    """
    Test Home page loads correctly.
    """
    at = AppTest.from_file("Home.py")
    at.run()
    assert not at.exception
    assert at.title[0].value == "ATS Login"
    assert len(at.text_input) == 2
    assert at.button[0].label == "Login"