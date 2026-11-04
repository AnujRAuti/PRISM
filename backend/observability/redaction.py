"""
Sensitive data redaction for telemetry.
"""
import re
from typing import Any, Dict, List, Set


# Patterns for sensitive data detection
SENSITIVE_KEY_PATTERNS = {
    # Passwords and secrets
    re.compile(r'password', re.IGNORECASE),
    re.compile(r'secret', re.IGNORECASE),
    re.compile(r'key', re.IGNORECASE),
    re.compile(r'token', re.IGNORECASE),
    re.compile(r'access_token', re.IGNORECASE),
    re.compile(r'refresh_token', re.IGNORECASE),
    re.compile(r'authorization', re.IGNORECASE),
    re.compile(r'api_key', re.IGNORECASE),
    re.compile(r'credential', re.IGNORECASE),
    re.compile(r'webhook_secret', re.IGNORECASE),
    re.compile(r'signature', re.IGNORECASE),
    re.compile(r'hmac', re.IGNORECASE),
    re.compile(r'jwt', re.IGNORECASE),
    re.compile(r'bearer', re.IGNORECASE),
    re.compile(r'passwd', re.IGNORECASE),
    re.compile(r'pwd', re.IGNORECASE),
    
    # Additional sensitive patterns
    re.compile(r'private.*key', re.IGNORECASE),
    re.compile(r'client.*secret', re.IGNORECASE),
    re.compile(r'client.*id', re.IGNORECASE),
}

# Values that should never be redacted (allowlist for false positives)
SAFE_KEY_PATTERNS = {
    re.compile(r'status_code', re.IGNORECASE),
    re.compile(r'http.*status', re.IGNORECASE),
    re.compile(r'response.*time', re.IGNORECASE),
    re.compile(r'duration', re.IGNORECASE),
    re.compile(r'latency', re.IGNORECASE),
    re.compile(r'count', re.IGNORECASE),
    re.compile(r'total', re.IGNORECASE),
    re.compile(r'id$', re.IGNORECASE),  # Allow IDs that end with "id" but not "access_token_id" etc.
    re.compile(r'uuid', re.IGNORECASE),
    re.compile(r'trace_id', re.IGNORECASE),
    re.compile(r'span_id', re.IGNORECASE),
    re.compile(r'request_id', re.IGNORECASE),
    # Plural container keys ("tokens", "access_tokens") are recursed into
    # instead of flattened; their sensitive leaf keys (access_token,
    # refresh_token, ...) are still redacted by the sensitive patterns.
    re.compile(r'tokens$', re.IGNORECASE),
}

# Specific keys that should always be redacted regardless of patterns
EXACT_MATCH_REDACT = {
    'password',
    'secret',
    'token',
    'access_token',
    'refresh_token',
    'authorization',
    'api_key',
    'credential',
    'webhook_secret',
    'signature',
    'hmac',
    'jwt',
    'bearer',
    'passwd',
    'pwd',
    'private_key',
    'client_secret',
    'client_id',
}


def is_sensitive_key(key: str) -> bool:
    """
    Determine if a key indicates sensitive data that should be redacted.
    
    Args:
        key: The key to check
        
    Returns:
        True if the key indicates sensitive data
    """
    if not isinstance(key, str):
        return False
    
    key_lower = key.lower()
    
    # Check exact matches first
    if key_lower in EXACT_MATCH_REDACT:
        return True
    
    # Check if it's in the safe list (allowlist)
    for pattern in SAFE_KEY_PATTERNS:
        if pattern.search(key):
            return False
    
    # Check sensitive patterns
    for pattern in SENSITIVE_KEY_PATTERNS:
        if pattern.search(key):
            return True
    
    return False


def redact_value(value: Any) -> Any:
    """
    Redact a sensitive value (partial length-based redaction).

    Used for heuristic value-level redaction (strings that merely *look*
    like tokens). Sensitive *keys* are redacted with the full placeholder
    by :func:`redact_sensitive_data`.

    Args:
        value: The value to redact

    Returns:
        Redacted value
    """
    if isinstance(value, str) and len(value) > 0:
        n = len(value)
        if n <= 4:
            return "[REDACTED]"
        if n == 5:
            return value[0] + "[REDACTED]" + value[-1]
        if n <= 7:
            return value[:2] + "[REDACTED]" + value[-1]
        return value[:2] + "[REDACTED]" + value[-2:]
    return "[REDACTED]"


def redact_sensitive_data(data: Any, _visited: Set[int] = None) -> Any:
    """
    Recursively redact sensitive data from dictionaries, lists, and other data structures.
    
    Args:
        data: The data to redact (dict, list, or other)
        _visited: Internal parameter to track visited objects and prevent infinite recursion
        
    Returns:
        Data with sensitive values redacted
    """
    # Initialize visited set for circular reference detection
    if _visited is None:
        _visited = set()
    
    # Handle None and primitive types
    if data is None or isinstance(data, (bool, int, float)):
        return data
    
    # Handle strings - check if they look like sensitive data
    if isinstance(data, str):
        # Additional check for values that look like tokens or keys
        if len(data) >= 10 and (_looks_like_token(data) or _looks_like_key(data)):
            return redact_value(data)
        return data
    
    # Prevent infinite recursion with circular references
    data_id = id(data)
    if data_id in _visited:
        return "<CIRCULAR_REFERENCE>"
    _visited.add(data_id)
    
    try:
        # Handle dictionaries
        if isinstance(data, dict):
            redacted_dict = {}
            for key, value in data.items():
                # If the key indicates sensitive data, the entire value is
                # replaced with the placeholder — partial redaction could
                # leak credential fragments into telemetry.
                if is_sensitive_key(key):
                    redacted_dict[key] = "[REDACTED]"
                else:
                    redacted_dict[key] = redact_sensitive_data(
                        value, _visited.copy()
                    )
            return redacted_dict
        
        # Handle lists and tuples
        if isinstance(data, (list, tuple)):
            redacted_list = [
                redact_sensitive_data(item, _visited.copy()) for item in data
            ]
            return type(data)(redacted_list)
        
        # Handle sets
        if isinstance(data, set):
            return {
                redact_sensitive_data(item, _visited.copy()) for item in data
            }
        
        # For other types, return as-is (but could be extended for specific types)
        return data
        
    finally:
        # Remove from visited set when backtracking
        _visited.discard(data_id)


def _looks_like_token(value: str) -> bool:
    """
    Heuristic to determine if a string looks like a token or secret.
    
    Args:
        value: String to check
        
    Returns:
        True if the string looks like a token
    """
    # Very long strings are likely tokens or secrets
    if len(value) > 32:
        return True
    
    # Check for common token patterns
    token_patterns = [
        r'^[A-Za-z0-9_-]{20,}$',  # Alphanumeric, dash, underscore, min 20 chars
        r'^[A-Fa-f0-9]{32,}$',    # Hexadecimal, min 32 chars
        r'^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}$',  # UUID
        r'^eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*$',  # JWT
    ]
    
    for pattern in token_patterns:
        if re.match(pattern, value):
            return True
    
    return False


def _looks_like_key(value: str) -> bool:
    """
    Heuristic to determine if a string looks like a cryptographic key.
    
    Args:
        value: String to check
        
    Returns:
        True if the string looks like a key
    """
    # Keys are often base64 encoded or hex
    if len(value) >= 20:
        # Check if it's mostly base64 characters
        base64_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
        if all(c in base64_chars for c in value.strip()):
            return True
        
        # Check if it's mostly hex characters
        hex_chars = set('0123456789abcdefABCDEF')
        if all(c in hex_chars for c in value.strip()):
            return True
    
    return False


def redact_dict_for_logging(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to redact a dictionary for logging purposes.
    
    Args:
        data: Dictionary to redact
        
    Returns:
        New dictionary with sensitive data redacted
    """
    return redact_sensitive_data(data)


def redact_list_for_logging(data: List[Any]) -> List[Any]:
    """
    Convenience function to redact a list for logging purposes.
    
    Args:
        data: List to redact
        
    Returns:
        New list with sensitive data redacted
    """
    return redact_sensitive_data(data)


# Export the main redaction function
__all__ = [
    'redact_sensitive_data',
    'redact_dict_for_logging',
    'redact_list_for_logging',
    'is_sensitive_key',
    'redact_value'
]
