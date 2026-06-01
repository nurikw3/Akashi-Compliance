from __future__ import annotations

from typing import Any


def normalize_person_name(value: Any) -> str | None:
    """Return a displayable person name; ignore nested risk/JSON blobs."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text in ("—", "-", "null", "None"):
            return None
        if text.startswith(("{", "[")):
            return None
        return text
    if isinstance(value, dict):
        for key in (
            "fullname_director",
            "full_name",
            "fullName",
            "name",
            "fio",
            "director_name",
            "head_name",
        ):
            found = normalize_person_name(value.get(key))
            if found:
                return found
        return None
    return None
