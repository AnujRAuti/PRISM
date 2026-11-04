from io import BytesIO
from typing import Any

import exifread


def extract_exif(data: bytes) -> dict[str, Any]:
    tags = exifread.process_file(BytesIO(data), details=False)
    return {str(key): _json_value(value) for key, value in tags.items()}


def _json_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)