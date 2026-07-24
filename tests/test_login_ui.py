
import pytest
from streamlit.testing.v1 import AppTest
from unittest.mock import patch

@patch("streamlit.secrets", {"SUPABASE_URL": "[https://fake.supabase.co](https://fake.supabase.co)", "SUPABASE_KEY": "fake-key"})
@patch("login.authenticate_user")
def test_successful_login(mock_authenticate):
    """
    Simulate successful login workflow.
    """
    mock_authenticate.return_value = True
    
    at = AppTest.from_file("Home.py")
    at.run()
    
    at.text_input[0].input("admin@ats.com")
    at.text_input[1].input("securepassword123")
    at.button[0].click().run()
    
    mock_authenticate.assert_called_once_with("admin@ats.com", "securepassword123")
    assert at.success[0].value == "Login Successful"

@patch("streamlit.secrets", {"SUPABASE_URL": "[https://fake.supabase.co](https://fake.supabase.co)", "SUPABASE_KEY": "fake-key"})
@patch("login.authenticate_user")
def test_failed_login(mock_authenticate):
    """
    Simulate failed login workflow.
    """
    mock_authenticate.return_value = False
    
    at = AppTest.from_file("Home.py")
    at.run()
    
    at.text_input[0].input("wrong@user.com")
    at.text_input[1].input("badpassword")
    at.button[0].click().run()
    
    assert at.error[0].value == "Invalid Email or Password"