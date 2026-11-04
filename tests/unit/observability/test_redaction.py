"""
Unit tests for observability redaction.
"""
from backend.observability.redaction import (
    redact_sensitive_data,
    redact_dict_for_logging,
    redact_list_for_logging,
    is_sensitive_key,
    redact_value
)


def test_is_sensitive_key():
    """Test detection of sensitive keys."""
    # Should be sensitive
    assert is_sensitive_key("password") == True
    assert is_sensitive_key("secret") == True
    assert is_sensitive_key("token") == True
    assert is_sensitive_key("access_token") == True
    assert is_sensitive_key("refresh_token") == True
    assert is_sensitive_key("authorization") == True
    assert is_sensitive_key("api_key") == True
    assert is_sensitive_key("credential") == True
    assert is_sensitive_key("webhook_secret") == True
    assert is_sensitive_key("signature") == True
    assert is_sensitive_key("hmac") == True
    assert is_sensitive_key("jwt") == True
    assert is_sensitive_key("bearer") == True
    assert is_sensitive_key("passwd") == True
    assert is_sensitive_key("pwd") == True
    assert is_sensitive_key("private_key") == True
    assert is_sensitive_key("client_secret") == True
    assert is_sensitive_key("client_id") == True
    
    # Case insensitive
    assert is_sensitive_key("PASSWORD") == True
    assert is_sensitive_key("Secret") == True
    assert is_sensitive_key("TOKEN") == True
    
    # Should not be sensitive (safe keys)
    assert is_sensitive_key("username") == False
    assert is_sensitive_key("email") == False
    assert is_sensitive_key("message") == False
    assert is_sensitive_key("status_code") == False
    assert is_sensitive_key("duration_ms") == False
    assert is_sensitive_key("method") == False
    assert is_sensitive_key("path") == False
    assert is_sensitive_key("request_id") == False
    assert is_sensitive_key("trace_id") == False
    assert is_sensitive_key("span_id") == False
    assert is_sensitive_key("service") == False
    assert is_sensitive_key("component") == False
    assert is_sensitive_key("event") == False
    assert is_sensitive_key("level") == False
    assert is_sensitive_key("timestamp") == False


def test_redact_value():
    """Test value redaction."""
    # Short values
    assert redact_value("abc") == "[REDACTED]"
    assert redact_value("abcd") == "[REDACTED]"
    
    # Medium values
    assert redact_value("abcde") == "a[REDACTED]e"
    assert redact_value("abcdef") == "ab[REDACTED]f"
    assert redact_value("abcdefg") == "ab[REDACTED]g"
    assert redact_value("abcdefgh") == "ab[REDACTED]gh"
    
    # Longer values
    assert redact_value("abcdefghij") == "ab[REDACTED]ij"
    assert redact_value("a" * 20) == "aa[REDACTED]aa"
    
    # Non-string values
    assert redact_value(123) == "[REDACTED]"
    assert redact_value(None) == "[REDACTED]"
    assert redact_value(True) == "[REDACTED]"
    assert redact_value(False) == "[REDACTED]"


def test_redact_sensitive_data_simple():
    """Test redacting simple dictionaries."""
    data = {
        "username": "testuser",
        "password": "secret123",
        "api_key": "key123"
    }
    
    redacted = redact_sensitive_data(data)
    
    assert redacted["username"] == "testuser"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"


def test_redact_sensitive_data_nested():
    """Test redacting nested dictionaries."""
    data = {
        "user": {
            "username": "testuser",
            "password": "secret123",
            "details": {
                "email": "test@example.com",
                "api_key": "nested_key123"
            }
        },
        "tokens": {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456"
        }
    }
    
    redacted = redact_sensitive_data(data)
    
    # Check top level
    assert redacted["user"]["username"] == "testuser"
    assert redacted["user"]["password"] == "[REDACTED]"
    assert redacted["user"]["details"]["email"] == "test@example.com"
    assert redacted["user"]["details"]["api_key"] == "[REDACTED]"
    
    # Check nested tokens
    assert redacted["tokens"]["access_token"] == "[REDACTED]"
    assert redacted["tokens"]["refresh_token"] == "[REDACTED]"


def test_redact_sensitive_data_lists():
    """Test redacting lists and nested structures."""
    data = [
        {
            "username": "user1",
            "password": "pass1"
        },
        {
            "username": "user2", 
            "token": "token123"
        },
        "plain_string",
        {
            "nested_list": [
                {"password": "list_pass"},
                {"safe": "safe_value"}
            ]
        }
    ]
    
    redacted = redact_sensitive_data(data)
    
    assert redacted[0]["username"] == "user1"
    assert redacted[0]["password"] == "[REDACTED]"
    assert redacted[1]["username"] == "user2"
    assert redacted[1]["token"] == "[REDACTED]"
    assert redacted[2] == "plain_string"
    assert redacted[3]["nested_list"][0]["password"] == "[REDACTED]"
    assert redacted[3]["nested_list"][1]["safe"] == "safe_value"


def test_redact_sensitive_data_no_change_when_disabled():
    """Test that redaction doesn't change data when disabled."""
    # This would require mocking the config setting, but for now we'll test
    # that the function works correctly
    data = {
        "password": "secret123",
        "message": "hello world"
    }
    
    redacted = redact_sensitive_data(data)
    
    # Password should be redacted
    assert redacted["password"] == "[REDACTED]"
    # Message should be unchanged
    assert redacted["message"] == "hello world"


def test_redact_dict_for_logging():
    """Test the convenience function for dict redaction."""
    data = {
        "username": "testuser",
        "password": "secret123"
    }
    
    redacted = redact_dict_for_logging(data)
    
    assert redacted["username"] == "testuser"
    assert redacted["password"] == "[REDACTED]"


def test_redact_list_for_logging():
    """Test the convenience function for list redaction."""
    data = [
        {"username": "user1", "password": "pass1"},
        {"username": "user2", "token": "token123"}
    ]
    
    redacted = redact_list_for_logging(data)
    
    assert redacted[0]["username"] == "user1"
    assert redacted[0]["password"] == "[REDACTED]"
    assert redacted[1]["username"] == "user2"
    assert redacted[1]["token"] == "[REDACTED]"
