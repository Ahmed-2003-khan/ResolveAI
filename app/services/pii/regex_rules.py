from __future__ import annotations

import re
from typing import Final

PATTERNS: Final[dict[str, str]] = {
    "CNIC": r"\b\d{5}-\d{7}-\d\b|\b\d{13}\b",
    "MOBILE": r"(?:(?<!\w)\+92|\b0)3\d{2}[-\s]?\d{7}\b",
    "IBAN": r"\bPK\d{2}[A-Z]{4}\d{16}\b",
    "CARD": r"\b(?:\d[ -]?){13,19}\b",
    "EMAIL": r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",
}

COMPILED: Final[dict[str, re.Pattern[str]]] = {
    name: re.compile(pattern) for name, pattern in PATTERNS.items()
}
