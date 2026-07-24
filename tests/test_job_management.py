
import pytest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

@patch("streamlit.secrets", {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_KEY": "fake-key"})
@patch("db.supabase")
@patch("streamlit.cache_data", lambda *args, **kwargs: (lambda f: f))
def test_job_management_form_validation(mock_supabase):
    """
    Test Job Management module loads safely with mocked database.
    """
    mock_supabase.table.return_value.select.return_value.execute.return_value.data = []

    at = AppTest.from_file("pages/4_Job_Management.py")
    at.session_state["logged_in"] = True
    at.session_state["user_role"] = "Admin"
    
    at.run()
    assert not at.exception