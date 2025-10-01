# lumen/api/app/privacy/sanitize.py
from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
IBAN  = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
PT_NIF = re.compile(r"\b\d{9}\b")

def sanitize(text: str) -> str:
    """
    Minimal DEV sanitizer. Replace with Presidio/spaCy later.
    """
    t = EMAIL.sub("[EMAIL]", text)
    t = PHONE.sub("[PHONE]", t)
    t = IBAN.sub("[IBAN]", t)
    t = PT_NIF.sub("[PT_TAX]", t)
    return t
