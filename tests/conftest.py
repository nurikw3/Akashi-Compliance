"""Isolate tests from developer data/compliance.db."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Must run before app.models.db is imported by test modules.
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["SQLITE_PATH"] = _test_db.name

from app.models import db as _db  # noqa: E402

_db.init_db()
