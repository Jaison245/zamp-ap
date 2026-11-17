"""Reason-code catalog + the pure-code decision engine.

A 'finding' is {code, message, evidence?, detail?} produced by the stages. The engine looks each
code up in the catalog for its outcome (REJECT/HOLD/INFO), severity and routing target, then applies
an ordered rule: any REJECT -> REJECT; else any HOLD -> HOLD; else APPROVE. ALL findings are surfaced.
"""
from __future__ import annotations

# code -> (outcome, severity, routing, default_message)
CATALOG: dict[str, tuple[str, str, str, str]] = {
    # ---- REJECT ----
    "NOT_AN_INVOICE":        ("REJECT", "medium", "ap_clerk",   "Document is not an invoice."),
    "UNREADABLE_FILE":       ("REJECT", "medium", "ap_clerk",   "File could not be read."),
    "VENDOR_BLOCKED":        ("REJECT", "high",   "procurement","Vendor is blocked."),
    "DUPLICATE_INVOICE":     ("REJECT", "high",   "ap_clerk",   "Exact duplicate of an already-processed invoice."),
    "DUPLICATE_FILE":        ("REJECT", "high",   "ap_clerk",   "Identical file already processed."),
    "WRONG_ADDRESSEE":       ("REJECT", "medium", "ap_clerk",   "Invoice is not addressed to us."),
    # ---- HOLD ----
    "BANK_DETAILS_CHANGED":  ("HOLD",   "high",   "security",   "Bank details differ from the vendor master."),
    "SUSPICIOUS_INSTRUCTIONS":("HOLD",  "high",   "security",   "Document contains instructions aimed at an automated system."),
    "UNKNOWN_VENDOR":        ("HOLD",   "medium", "procurement","Vendor is not in the master file."),
    "VENDOR_PENDING":        ("HOLD",   "medium", "procurement","Vendor onboarding is not complete."),
    "TAX_ID_MISMATCH":       ("HOLD",   "medium", "procurement","Tax ID differs from the vendor master."),
    "POSSIBLE_DUPLICATE":    ("HOLD",   "medium", "ap_clerk",   "Possible duplicate of an earlier invoice."),
    "MISSING_REQUIRED_FIELD":("HOLD",   "medium", "vendor",     "A required field is missing."),
    "LOW_CONFIDENCE_FIELD":  ("HOLD",   "medium", "ap_clerk",   "A key field could not be read with confidence."),
    "GROUNDING_FAILED":      ("HOLD",   "medium", "ap_clerk",   "Extracted value not found in the document text."),
    "ARITHMETIC_MISMATCH":   ("HOLD",   "medium", "vendor",     "The invoice does not add up."),
    "NO_PO_FOUND":           ("HOLD",   "medium", "procurement","No matching purchase order."),
    "AMBIGUOUS_PO":          ("HOLD",   "medium", "procurement","Several POs could match; needs a human."),
    "PO_VENDOR_MISMATCH":    ("HOLD",   "high",   "procurement","PO belongs to a different vendor."),
    "PO_CLOSED":             ("HOLD",   "medium", "procurement","Referenced PO is closed or cancelled."),
    "PO_OVERBILLED":         ("HOLD",   "high",   "procurement","Cumulative billing exceeds the PO total."),
    "PRICE_VARIANCE":        ("HOLD",   "medium", "procurement","Line price is outside tolerance."),
    "QTY_EXCEEDS_ORDERED":   ("HOLD",   "medium", "procurement","Billed quantity exceeds ordered."),
    "QTY_EXCEEDS_RECEIVED":  ("HOLD",   "medium", "procurement","Billed quantity exceeds goods received."),
    "CURRENCY_MISMATCH":     ("HOLD",   "high",   "ap_clerk",   "Invoice currency differs from the PO."),
    "TAX_RATE_UNEXPECTED":   ("HOLD",   "medium", "ap_clerk",   "Tax rate is not allowed for this country."),
    "CREDIT_NOTE":           ("HOLD",   "low",    "ap_clerk",   "Credit note — apply to the vendor balance."),
    "MULTIPLE_INVOICES":     ("HOLD",   "medium", "vendor",     "Several invoices in one file — split and resubmit."),
    "STALE_INVOICE":         ("HOLD",   "low",    "ap_clerk",   "Invoice is older than the allowed age."),
    "FUTURE_DATED":          ("HOLD",   "low",    "ap_clerk",   "Invoice is dated in the future."),
    "PROCESSING_ERROR":      ("HOLD",   "medium", "ap_clerk",   "Processing error — a human must review."),
    # ---- INFO (notes on an APPROVE) ----
    "PRICE_WITHIN_TOLERANCE":("INFO",   "low",    "ap_clerk",   "Price variance within tolerance."),
    "PO_INFERRED":           ("INFO",   "low",    "ap_clerk",   "PO inferred from vendor and amount."),
    "TOTAL_WITHIN_TOLERANCE":("INFO",   "low",    "ap_clerk",   "Invoice total within tolerance of the PO."),
    "THREE_WAY_MATCHED":     ("INFO",   "low",    "ap_clerk",   "Matched against goods receipt (3-way)."),
}

ROUTING_LABEL = {
    "ap_clerk": "AP clerk", "procurement": "Procurement",
    "vendor": "Vendor", "security": "Security", "finance": "Finance",
}


def enrich(findings: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for f in findings:
        code = f["code"]
        if code in seen:
            continue
        seen.add(code)
        outcome, severity, routing, default_msg = CATALOG.get(
            code, ("HOLD", "medium", "ap_clerk", code))
        out.append({
            "code": code,
            "outcome": outcome,
            "severity": severity,
            "routing": routing,
            "routing_label": ROUTING_LABEL.get(routing, routing),
            "message": f.get("message") or default_msg,
            "evidence": f.get("evidence"),
            "detail": f.get("detail"),
        })
    # strongest severity first within display
    order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda c: (("REJECT", "HOLD", "INFO").index(c["outcome"]), order.get(c["severity"], 1)))
    return out


def decide(findings: list[dict]) -> dict:
    codes = enrich(findings)
    if any(c["outcome"] == "REJECT" for c in codes):
        decision = "REJECT"
    elif any(c["outcome"] == "HOLD" for c in codes):
        decision = "HOLD"
    else:
        decision = "APPROVE"
    primary = next((c for c in codes if c["outcome"] == decision), None)
    routing = primary["routing_label"] if primary and decision != "APPROVE" else None
    return {"decision": decision, "codes": codes, "routing": routing,
            "top_reason": primary["code"] if primary else None}
