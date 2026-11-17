"""Vendor validation: match, blocked/pending, bank-change + tax-id fraud signals, addressee."""
from __future__ import annotations
from typing import Optional

from rapidfuzz import fuzz
from sqlmodel import Session, select

from ..config import load_rules
from ..models import Vendor


def _norm(s: Optional[str]) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def match_vendor(session: Session, extraction: dict) -> tuple[Optional[Vendor], int, str]:
    """Return (vendor, score, basis). Exact tax-id first, then fuzzy name/alias."""
    v = extraction.get("vendor") or {}
    tax_id = _norm(v.get("tax_id"))
    name = (v.get("name") or "").strip()
    vendors = session.exec(select(Vendor)).all()

    if tax_id:
        for vd in vendors:
            if _norm(vd.tax_id) and _norm(vd.tax_id) == tax_id:
                return vd, 100, "tax_id"

    best, best_score = None, 0
    for vd in vendors:
        candidates = [vd.legal_name] + [a for a in (vd.aliases or "").split("|") if a]
        score = max((fuzz.token_sort_ratio(name, c) for c in candidates), default=0)
        if score > best_score:
            best, best_score = vd, score
    if best and best_score >= 88:
        return best, int(best_score), "name"
    return None, int(best_score), "none"


def validate_vendor(session: Session, extraction: dict) -> dict:
    """Produce findings + the resolved vendor. Pure checks; no decision here."""
    findings: list[dict] = []
    vendor, score, basis = match_vendor(session, extraction)
    ev = extraction.get("vendor") or {}

    if not vendor:
        findings.append({"code": "UNKNOWN_VENDOR",
                         "message": f"No vendor matched '{ev.get('name','?')}' (best score {score}).",
                         "detail": "Start vendor onboarding."})
        return {"vendor": None, "score": score, "basis": basis, "findings": findings}

    # addressee check
    bill_to = ((extraction.get("bill_to") or {}).get("name") or "")
    our_names = [n.lower() for n in load_rules().get("our_company", {}).get("names", [])]
    if bill_to and our_names and not any(n in bill_to.lower() for n in our_names):
        findings.append({"code": "WRONG_ADDRESSEE",
                         "message": f"Billed to '{bill_to}', not us.",
                         "evidence": bill_to})

    if vendor.status == "blocked":
        findings.append({"code": "VENDOR_BLOCKED", "message": f"{vendor.legal_name} is blocked."})
    elif vendor.status == "pending":
        findings.append({"code": "VENDOR_PENDING", "message": f"{vendor.legal_name} onboarding is pending."})

    # bank details change (fraud signal) — compare account numbers, punctuation-insensitive
    inv_bank = _norm((ev.get("bank") or {}).get("iban_or_account"))
    if inv_bank and _norm(vendor.iban_or_account) and inv_bank != _norm(vendor.iban_or_account):
        findings.append({
            "code": "BANK_DETAILS_CHANGED",
            "message": "Bank account on the invoice does not match the vendor master.",
            "evidence": f"invoice: {(ev.get('bank') or {}).get('iban_or_account')}  |  master: {vendor.iban_or_account}",
        })

    # tax id mismatch (only when matched by name, not tax id)
    if basis != "tax_id":
        inv_tax = _norm(ev.get("tax_id"))
        if inv_tax and _norm(vendor.tax_id) and inv_tax != _norm(vendor.tax_id):
            findings.append({"code": "TAX_ID_MISMATCH",
                             "message": f"Tax ID {ev.get('tax_id')} != master {vendor.tax_id}."})

    return {"vendor": vendor, "score": score, "basis": basis, "findings": findings}
