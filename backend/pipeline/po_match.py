"""PO matching: explicit reference first, otherwise shortlist + infer (code-only tie-break)."""
from __future__ import annotations
from decimal import Decimal
from typing import Optional

from rapidfuzz import fuzz
from sqlmodel import Session, select

from ..config import load_rules
from ..models import InvoiceRegister, POLine, PurchaseOrder, Vendor
from .money import D


def billed_net(session: Session, po_number: str) -> Decimal:
    """Sum of net amounts already APPROVED against a PO (from the register)."""
    total = Decimal("0")
    for r in session.exec(select(InvoiceRegister).where(InvoiceRegister.po_number == po_number)).all():
        v = D(r.subtotal_net)
        if v:
            total += v
    return total


def _line_similarity(extraction: dict, po_number: str, session: Session) -> float:
    inv_desc = " ".join((li.get("description") or "") for li in (extraction.get("line_items") or []))
    po_desc = " ".join(pl.description for pl in
                       session.exec(select(POLine).where(POLine.po_number == po_number)).all())
    if not inv_desc or not po_desc:
        return 0.0
    return float(fuzz.token_set_ratio(inv_desc, po_desc))


def match_po(session: Session, vendor: Optional[Vendor], extraction: dict,
             invoice_net: Optional[Decimal], currency: Optional[str]) -> dict:
    findings: list[dict] = []
    tol = Decimal(str(load_rules()["tolerances"]["cumulative_po_pct"]))
    ref = (extraction.get("po_reference") or "").strip()

    # 1. explicit reference
    if ref:
        po = session.get(PurchaseOrder, ref)
        if po:
            if vendor and po.vendor_id != vendor.vendor_id:
                findings.append({"code": "PO_VENDOR_MISMATCH",
                                 "message": f"{ref} belongs to {po.vendor_id}, not {vendor.vendor_id}.",
                                 "evidence": ref})
                return {"po": None, "inferred": False, "findings": findings, "candidates": []}
            if po.status in ("closed", "cancelled"):
                findings.append({"code": "PO_CLOSED", "message": f"{ref} is {po.status}.", "evidence": ref})
            return {"po": po, "inferred": False, "findings": findings, "candidates": []}
        # referenced PO doesn't exist -> fall through to inference
        findings.append({"code": "NO_PO_FOUND",
                         "message": f"Referenced PO '{ref}' does not exist; attempting to infer.",
                         "detail": "inference"})

    if not vendor:
        if not any(f["code"] == "NO_PO_FOUND" for f in findings):
            findings.append({"code": "NO_PO_FOUND", "message": "No vendor, so no PO can be matched."})
        return {"po": None, "inferred": False, "findings": findings, "candidates": []}

    # 2. shortlist candidates
    cands = []
    pos = session.exec(select(PurchaseOrder).where(PurchaseOrder.vendor_id == vendor.vendor_id)).all()
    for po in pos:
        if po.status not in ("open", "partially_billed"):
            continue
        if currency and po.currency and currency != po.currency:
            continue
        remaining = Decimal(str(po.total)) - billed_net(session, po.po_number)
        if invoice_net is not None and remaining + (Decimal(str(po.total)) * tol) < invoice_net:
            continue  # not enough balance
        amt_closeness = 0.0
        if invoice_net is not None and po.total:
            amt_closeness = max(0.0, 100.0 - float(abs(invoice_net - Decimal(str(po.total))) / Decimal(str(po.total)) * 100))
        sim = _line_similarity(extraction, po.po_number, session)
        score = 0.6 * sim + 0.4 * amt_closeness
        cands.append({"po": po, "score": round(score, 1), "similarity": round(sim, 1),
                      "remaining": float(remaining)})
    cands.sort(key=lambda c: c["score"], reverse=True)
    cand_view = [{"po_number": c["po"].po_number, "score": c["score"], "similarity": c["similarity"],
                  "remaining": c["remaining"], "total": c["po"].total} for c in cands]

    # drop the failed explicit-ref NO_PO_FOUND if we can now infer
    findings = [f for f in findings if f["code"] != "NO_PO_FOUND"]

    if not cands:
        findings.append({"code": "NO_PO_FOUND", "message": "No open PO for this vendor matches the amount."})
        return {"po": None, "inferred": False, "findings": findings, "candidates": cand_view}

    top = cands[0]
    second = cands[1] if len(cands) > 1 else None
    clearly_best = (second is None) or (top["score"] - second["score"] >= 12)
    if clearly_best and top["score"] >= 45:
        findings.append({"code": "PO_INFERRED",
                         "message": f"Inferred {top['po'].po_number} (match score {top['score']}).",
                         "evidence": f"vendor {vendor.vendor_id}, amount & lines"})
        if top["po"].status in ("closed", "cancelled"):
            findings.append({"code": "PO_CLOSED", "message": f"{top['po'].po_number} is {top['po'].status}."})
        return {"po": top["po"], "inferred": True, "findings": findings, "candidates": cand_view}

    findings.append({"code": "AMBIGUOUS_PO",
                     "message": f"{len(cands)} POs could match; top two scores {top['score']} / "
                                f"{second['score'] if second else '-'}.",
                     "detail": "A human (or an LLM tie-break) must choose."})
    return {"po": None, "inferred": False, "findings": findings, "candidates": cand_view}
