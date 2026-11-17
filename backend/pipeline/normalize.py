"""Normalisation helpers: invoice-number key, dates, currency."""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

CURRENCY_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR"}


def norm_invoice_number(raw: Optional[str]) -> str:
    """'INV-0042' / 'INV 0042' / 'inv0042' -> 'INV0042' for duplicate matching."""
    if not raw:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(raw)).upper()


def parse_iso(d: Optional[dict | str]) -> Optional[date]:
    if not d:
        return None
    s = d.get("iso") if isinstance(d, dict) else d
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def infer_currency(extraction: dict, vendor_default: Optional[str]) -> Optional[str]:
    cur = extraction.get("currency")
    if cur and len(str(cur)) == 3 and str(cur).isalpha():
        return str(cur).upper()
    if cur and str(cur) in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[str(cur)]
    return vendor_default
