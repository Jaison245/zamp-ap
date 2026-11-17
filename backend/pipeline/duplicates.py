"""Duplicate detection against the invoice register (strongest signal first)."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from ..config import load_rules
from ..models import InvoiceRegister, Vendor
from .money import D
from .normalize import norm_invoice_number


def _norm_po(s) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def check_duplicates(session: Session, vendor: Optional[Vendor], extraction: dict,
                     file_hash: str, total_gross: Optional[Decimal],
                     inv_date: Optional[date]) -> list[dict]:
    findings: list[dict] = []
    reg = session.exec(select(InvoiceRegister)).all()
    rules = load_rules().get("duplicate", {})

    # 2. exact file hash
    for r in reg:
        if file_hash and r.file_hash == file_hash:
            findings.append({"code": "DUPLICATE_FILE",
                             "message": f"Identical file already processed (run #{r.run_id}).",
                             "evidence": f"sha256 {file_hash[:16]}…"})
            break

    norm = norm_invoice_number(extraction.get("invoice_number"))
    vid = vendor.vendor_id if vendor else None

    # 1. same vendor + same normalised invoice number
    for r in reg:
        if vid and r.vendor_id == vid and norm and r.invoice_number_norm == norm:
            findings.append({"code": "DUPLICATE_INVOICE",
                             "message": f"Invoice {extraction.get('invoice_number')} already processed "
                                        f"(run #{r.run_id}, {r.decision}).",
                             "evidence": f"earlier raw number: {r.invoice_number_raw}"})
            return findings  # strongest signal; stop

    # 3. possible duplicate: same vendor, total within pct, within window, different number
    pct = Decimal(str(rules.get("possible_amount_pct", 0.01)))
    window = int(rules.get("possible_window_days", 30))
    cur_po = _norm_po(extraction.get("po_reference"))
    if vid and total_gross is not None and inv_date is not None:
        for r in reg:
            if r.vendor_id != vid or r.invoice_number_norm == norm:
                continue
            # legitimate split billing against the SAME PO is not a duplicate; the
            # cumulative-overbilling check (stage 8) governs that risk instead.
            if cur_po and _norm_po(r.po_number) == cur_po:
                continue
            other_total = D(r.total_gross)
            if other_total is None or other_total == 0:
                continue
            if abs(total_gross - other_total) / other_total <= pct:
                try:
                    od = date.fromisoformat((r.invoice_date or "")[:10])
                except ValueError:
                    od = None
                if od and abs((inv_date - od).days) <= window:
                    findings.append({"code": "POSSIBLE_DUPLICATE",
                                     "message": f"Same vendor and amount as invoice {r.invoice_number_raw} "
                                                f"(run #{r.run_id}), {abs((inv_date-od).days)} days apart.",
                                     "evidence": f"both ~{other_total} {r.currency}"})
                    break
    return findings
