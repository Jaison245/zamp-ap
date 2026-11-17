"""The pipeline. A generator that runs stages 0-10, yields event dicts (for SSE), and on APPROVE
commits side effects (invoice register + PO balance) inside the run's transaction."""
from __future__ import annotations
import io
import json
import time
import traceback
from datetime import date, datetime
from decimal import Decimal
from typing import Iterator, Optional

import pdfplumber
from rapidfuzz import fuzz
from sqlmodel import Session, select

from .. import config
from ..db import engine
from ..llm import extractor
from ..models import InvoiceRegister, PurchaseOrder, Run
from . import decision as decision_mod
from . import duplicates, lines, money, normalize, po_match, vendor as vendor_mod

KEY_EVIDENCE_FIELDS = ["invoice_number", "invoice_date", "total", "po_reference", "bank_account"]


def _now() -> float:
    return time.time()


_ERR_LOG = config.ROOT / "pipeline_errors.log"


def _log_err(stage: str, exc: Exception, extraction: dict | None = None) -> str:
    """Append a full traceback + the extraction to a file, for post-mortem. Returns short msg."""
    try:
        with open(_ERR_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*70}\n{datetime.now().isoformat()}  STAGE: {stage}\n")
            f.write(f"{type(exc).__name__}: {exc}\n")
            f.write(traceback.format_exc())
            if extraction is not None:
                f.write("EXTRACTION:\n" + json.dumps(extraction, default=str, indent=2) + "\n")
    except Exception:
        pass
    return f"{type(exc).__name__}: {exc}"


def _grounded(quote: Optional[str], text: str) -> bool:
    if not quote:
        return True
    q = str(quote).strip()
    if not q or not text:
        return False
    if q.lower() in text.lower():
        return True
    return fuzz.partial_ratio(q.lower(), text.lower()) >= 85


def run_pipeline(run_id: int) -> Iterator[dict]:
    t_run = _now()
    session = Session(engine)
    run = session.get(Run, run_id)
    if not run:
        yield {"type": "error", "message": "run not found"}
        return

    pdf_path = config.UPLOADS_DIR / f"{run_id}.pdf"
    pdf_bytes = pdf_path.read_bytes()
    findings: list[dict] = []
    events: list[dict] = []
    run.status = "running"
    session.add(run); session.commit()

    def emit(stage: int, name: str, status: str, t0: float, detail: dict,
             codes: Optional[list] = None, notes: Optional[list] = None) -> dict:
        ev = {"type": "stage", "stage": stage, "name": name, "status": status,
              "duration_ms": int((_now() - t0) * 1000), "detail": detail,
              "codes": codes or [], "notes": notes or []}
        events.append(ev)
        return ev

    def start(stage: int, name: str) -> dict:
        return {"type": "stage", "stage": stage, "name": name, "status": "running",
                "duration_ms": 0, "detail": {}, "codes": [], "notes": []}

    # ---------------- Stage 0: Intake ----------------
    t0 = _now(); yield start(0, "Intake")
    file_hash = extractor.sha256(pdf_bytes)
    run.file_hash = file_hash
    pages = 0
    text_layer = ""
    readable = True
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = len(pdf.pages)
            text_layer = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        readable = False
        findings.append({"code": "UNREADABLE_FILE", "message": f"Could not open PDF: {e}"})
    size_kb = round(len(pdf_bytes) / 1024, 1)
    if not readable:
        yield emit(0, "Intake", "fail", t0, {"size_kb": size_kb, "sha256": file_hash[:16]})
        yield from _finish(session, run, findings, events, {}, None, None, None, t_run)
        return
    yield emit(0, "Intake", "pass", t0,
               {"size_kb": size_kb, "pages": pages, "sha256": file_hash[:16] + "…"})

    # ---------------- Stage 1: Pre-processing ----------------
    t0 = _now(); yield start(1, "Pre-processing")
    chars_per_page = (len(text_layer) / pages) if pages else 0
    source = "scanned" if chars_per_page < 50 else "text"
    yield emit(1, "Pre-processing", "pass", t0,
               {"source": source, "text_chars": len(text_layer), "chars_per_page": int(chars_per_page)},
               notes=[f"treated as {source} PDF"])

    # ---------------- Stage 2: Classification + extraction ----------------
    t0 = _now(); yield start(2, "Extraction (Claude)")
    extraction, meta = extractor.run_extraction(pdf_bytes)
    run.extraction = extraction
    run.cost_usd = meta.get("cost_usd")
    doc_type = extraction.get("document_type", "other")
    susp = extraction.get("suspicious_instructions") or []
    ext_notes = [f"mode={meta.get('mode')}", f"type={doc_type}"]
    if meta.get("model"):
        ext_notes.append(f"model={meta['model']}")
    if meta.get("cost_usd"):
        ext_notes.append(f"${meta['cost_usd']} / {meta.get('tokens')} tok")
    yield emit(2, "Extraction (Claude)", "pass", t0,
               {"document_type": doc_type, "legibility": extraction.get("legibility"),
                "line_items": len(extraction.get("line_items") or []),
                "mode": meta.get("mode"), "model": meta.get("model"), "cost_usd": meta.get("cost_usd"),
                "suspicious_instructions": susp,
                "fields": _field_summary(extraction)},
               notes=ext_notes)

    if susp:
        findings.append({"code": "SUSPICIOUS_INSTRUCTIONS",
                         "message": "Document tries to instruct the AI; ignored by design.",
                         "evidence": susp[0][:200]})

    # non-invoice / special document routing -> straight to decision
    if doc_type != "invoice":
        code = {"credit_note": "CREDIT_NOTE", "proforma": "NOT_AN_INVOICE", "quote": "NOT_AN_INVOICE",
                "statement": "NOT_AN_INVOICE", "receipt": "NOT_AN_INVOICE",
                "purchase_order": "NOT_AN_INVOICE", "other": "NOT_AN_INVOICE"}.get(doc_type, "NOT_AN_INVOICE")
        findings.append({"code": code, "message": f"Document classified as '{doc_type}'.",
                         "evidence": doc_type})
        yield from _finish(session, run, findings, events, extraction, None, None, None, t_run)
        return
    if extraction.get("contains_multiple_invoices"):
        findings.append({"code": "MULTIPLE_INVOICES", "message": "More than one invoice in the file."})

    # ---------------- Stage 3: Verify extraction ----------------
    t0 = _now(); yield start(3, "Verify extraction")
    verify_detail = {"grounding": [], "reconciliation": [], "double_read": None}
    status3 = "pass"

    if source == "text":
        ev = extraction.get("evidence") or {}
        for f in KEY_EVIDENCE_FIELDS:
            q = (ev.get(f) or {}).get("quote") if isinstance(ev.get(f), dict) else None
            if q is None:
                continue
            ok = _grounded(q, text_layer)
            verify_detail["grounding"].append({"field": f, "ok": ok, "quote": q})
            if not ok:
                status3 = "warn"
                findings.append({"code": "GROUNDING_FAILED",
                                 "message": f"'{f}' not found verbatim in the document text.",
                                 "evidence": q})
    else:
        a, b, disagree = extractor.double_read(pdf_bytes)
        verify_detail["double_read"] = {"disagree": disagree}
        for f in disagree:
            status3 = "warn"
            findings.append({"code": "LOW_CONFIDENCE_FIELD",
                             "message": f"'{f}' disagreed across two reads of the scan."})

    ok_recon, checks = money.reconcile(extraction)
    verify_detail["reconciliation"] = checks
    if not ok_recon:
        status3 = "warn"
        findings.append({"code": "ARITHMETIC_MISMATCH",
                         "message": "Line items / totals do not reconcile.",
                         "evidence": "; ".join(f"{c['name']}: {c['detail']}" for c in checks if not c["ok"])[:300]})

    # required fields
    missing = []
    if not extraction.get("invoice_number"): missing.append("invoice_number")
    if not normalize.parse_iso(extraction.get("invoice_date")): missing.append("invoice_date")
    if not (extraction.get("vendor") or {}).get("name"): missing.append("vendor")
    if money.D(extraction.get("total")) is None: missing.append("total")
    if missing:
        status3 = "warn"
        findings.append({"code": "MISSING_REQUIRED_FIELD",
                         "message": "Missing: " + ", ".join(missing), "evidence": ", ".join(missing)})
    yield emit(3, "Verify extraction", status3, t0, verify_detail,
               notes=[f"reconciles={ok_recon}", f"source={source}"])

    # ---------------- Stage 4: Normalisation ----------------
    t0 = _now(); yield start(4, "Normalisation")
    inv_date = normalize.parse_iso(extraction.get("invoice_date"))
    inv_no_norm = normalize.norm_invoice_number(extraction.get("invoice_number"))
    invoice_net = money.D(extraction.get("subtotal")) or money.D(extraction.get("total"))
    total_gross = money.D(extraction.get("total"))
    ref = config.reference_date()
    age_detail = {}
    if inv_date:
        age_days = (ref - inv_date).days
        age_detail = {"invoice_date": inv_date.isoformat(), "age_days": age_days}
        ai = config.load_rules().get("invoice_age", {})
        if age_days > int(ai.get("max_age_days", 180)):
            findings.append({"code": "STALE_INVOICE", "message": f"Invoice is {age_days} days old."})
        if age_days < -int(ai.get("future_tolerance_days", 2)):
            findings.append({"code": "FUTURE_DATED", "message": f"Invoice dated {abs(age_days)} days in the future."})
    yield emit(4, "Normalisation", "pass", t0,
               {"invoice_number_norm": inv_no_norm, "invoice_net": str(invoice_net),
                "total_gross": str(total_gross), **age_detail})

    # The long LLM extraction above may have resumed this streaming generator on
    # a different worker thread; a SQLAlchemy/SQLite session is not safe across
    # that. Persist what stage 2 set, then use a fresh session for the DB stages.
    session.add(run); session.commit()
    try:
        session.close()
    except Exception:
        pass
    session = Session(engine)
    run = session.get(Run, run_id)

    # ---------------- Stage 5: Vendor validation ----------------
    t0 = _now(); yield start(5, "Vendor validation")
    try:
        vres = vendor_mod.validate_vendor(session, extraction)
    except Exception as e:
        vres = {"vendor": None, "score": 0, "basis": "error",
                "findings": [{"code": "PROCESSING_ERROR",
                              "message": f"Vendor validation error — {_log_err('vendor', e, extraction)}"}]}
    vend = vres["vendor"]
    findings += vres["findings"]
    currency = normalize.infer_currency(extraction, vend.currency if vend else None)
    s5 = "fail" if any(f["code"] in ("VENDOR_BLOCKED",) for f in vres["findings"]) else (
        "warn" if vres["findings"] else "pass")
    yield emit(5, "Vendor validation", s5, t0,
               {"vendor": vend.legal_name if vend else None, "vendor_id": vend.vendor_id if vend else None,
                "match_score": vres["score"], "basis": vres["basis"], "currency": currency,
                "status": vend.status if vend else None},
               notes=[f["code"] for f in vres["findings"]])

    # ---------------- Stage 6: Duplicate detection ----------------
    t0 = _now(); yield start(6, "Duplicate detection")
    try:
        dups = duplicates.check_duplicates(session, vend, extraction, file_hash, total_gross, inv_date)
    except Exception as e:
        dups = [{"code": "PROCESSING_ERROR", "message": f"Duplicate check error — {_log_err('duplicates', e, extraction)}"}]
    findings += dups
    yield emit(6, "Duplicate detection", "fail" if dups else "pass", t0,
               {"checked_register": True}, notes=[d["code"] for d in dups])

    # ---------------- Stage 7: PO matching ----------------
    t0 = _now(); yield start(7, "PO matching")
    try:
        pom = po_match.match_po(session, vend, extraction, invoice_net, currency)
    except Exception as e:
        pom = {"po": None, "inferred": False, "candidates": [],
               "findings": [{"code": "PROCESSING_ERROR", "message": f"PO matching error — {_log_err('po_match', e, extraction)}"}]}
    po = pom["po"]
    findings += pom["findings"]
    yield emit(7, "PO matching", "warn" if any(f["code"] in ("NO_PO_FOUND", "AMBIGUOUS_PO", "PO_CLOSED",
               "PO_VENDOR_MISMATCH") for f in pom["findings"]) else "pass", t0,
               {"po": po.po_number if po else None, "inferred": pom["inferred"],
                "candidates": pom["candidates"]},
               notes=[f["code"] for f in pom["findings"]])

    # ---------------- Stage 8: Line match (2/3-way) ----------------
    t0 = _now(); yield start(8, "Line match (2/3-way)")
    try:
        lm = lines.match_lines(session, po, vend, extraction, invoice_net, currency)
    except Exception as e:
        lm = {"findings": [{"code": "PROCESSING_ERROR", "message": f"Line match error — {_log_err('lines', e, extraction)}"}], "rows": []}
    findings += lm["findings"]
    po_table = lm["rows"]
    yield emit(8, "Line match (2/3-way)", "fail" if any(f["code"] in ("PO_OVERBILLED", "PRICE_VARIANCE",
               "QTY_EXCEEDS_ORDERED", "QTY_EXCEEDS_RECEIVED", "CURRENCY_MISMATCH") for f in lm["findings"])
               else "pass", t0, {"rows": po_table}, notes=[f["code"] for f in lm["findings"]])

    # ---------------- Stages 9 + 10 ----------------
    yield from _finish(session, run, findings, events, extraction, vend, po, invoice_net, t_run,
                       currency=currency, total_gross=total_gross, inv_no_norm=inv_no_norm,
                       inv_date=inv_date, po_table=po_table)


def _field_summary(extraction: dict) -> dict:
    v = extraction.get("vendor") or {}
    return {"invoice_number": extraction.get("invoice_number"),
            "vendor": v.get("name"),
            "total": (extraction.get("total") or {}).get("raw"),
            "currency": extraction.get("currency"),
            "po_reference": extraction.get("po_reference")}


def _finish(session: Session, run: Run, findings: list, events: list, extraction: dict,
            vend, po, invoice_net, t_run, currency=None, total_gross=None,
            inv_no_norm="", inv_date: Optional[date] = None, po_table=None) -> Iterator[dict]:
    # Persist anything pending on the incoming session (e.g. stage-2 extraction +
    # cost) before we later swap to a fresh write session.
    try:
        session.add(run); session.commit()
    except Exception:
        pass
    # Stage 9: decision engine
    t0 = _now()
    yield {"type": "stage", "stage": 9, "name": "Decision engine", "status": "running",
           "duration_ms": 0, "detail": {}, "codes": [], "notes": []}
    dec = decision_mod.decide(findings)
    decision = dec["decision"]
    ev9 = {"type": "stage", "stage": 9, "name": "Decision engine",
           "status": {"APPROVE": "pass", "HOLD": "warn", "REJECT": "fail"}[decision],
           "duration_ms": int((_now() - t0) * 1000),
           "detail": {"decision": decision, "routing": dec["routing"]},
           "codes": dec["codes"], "notes": [c["code"] for c in dec["codes"]]}
    events.append(ev9)
    yield ev9

    # Stage 10: explain + act
    t0 = _now()
    yield {"type": "stage", "stage": 10, "name": "Explain & act", "status": "running",
           "duration_ms": 0, "detail": {}, "codes": [], "notes": []}
    v = extraction.get("vendor") or {}
    amount = str(total_gross) if total_gross is not None else (extraction.get("total") or {}).get("value")
    ctx = {"decision": decision, "codes": dec["codes"], "vendor": v.get("name"),
           "invoice_number": extraction.get("invoice_number"), "amount": amount, "currency": currency}
    explanation = extractor.explain_decision(ctx)

    needs_vendor = decision in ("HOLD", "REJECT") and any(
        c["routing"] in ("vendor",) or c["code"] in ("BANK_DETAILS_CHANGED", "MISSING_REQUIRED_FIELD",
        "ARITHMETIC_MISMATCH", "MULTIPLE_INVOICES") for c in dec["codes"])
    vendor_email = extractor.draft_vendor_email({
        "needs_vendor": needs_vendor, "vendor": v.get("name"),
        "invoice_number": extraction.get("invoice_number"), "amount": amount,
        "codes": [c["code"] for c in dec["codes"]],
        "reasons": [c["message"] for c in dec["codes"] if c["outcome"] != "INFO"]})

    # Capture what we need as plain values, then use a FRESH session for all
    # writes — never held across the LLM calls above (which may have resumed this
    # streaming generator on a different thread, corrupting the old session).
    run_id = run.id
    vend_id = vend.vendor_id if vend else None
    vend_name = vend.legal_name if vend else v.get("name")
    po_number = po.po_number if po else None
    try:
        session.close()
    except Exception:
        pass
    session = Session(engine)
    run = session.get(Run, run_id)

    posting = None
    side_effects = []
    if decision == "APPROVE" and vend_id is not None:
        posting = _commit_approval(session, run, extraction, vend_id, vend_name, po_number,
                                   invoice_net, total_gross, inv_no_norm, inv_date, currency)
        side_effects = posting.get("side_effects", [])

    result = {
        "decision": decision, "codes": dec["codes"], "routing": dec["routing"],
        "top_reason": dec["top_reason"], "explanation": explanation, "vendor_email": vendor_email,
        "posting": posting, "side_effects": side_effects,
        "extraction": extraction, "po_table": po_table or [],
        "vendor": {"name": vend_name, "id": vend_id} if vend_id else None,
        "amount": amount, "currency": currency,
        "invoice_number": extraction.get("invoice_number"),
    }
    ev10 = {"type": "stage", "stage": 10, "name": "Explain & act",
            "status": "pass", "duration_ms": int((_now() - t0) * 1000),
            "detail": {"explanation": explanation, "has_email": bool(vendor_email),
                       "side_effects": side_effects}, "codes": [], "notes": side_effects}
    events.append(ev10)
    yield ev10

    # persist
    run.status = "done"
    run.decision = decision
    run.decision_codes = dec["codes"]
    run.explanation = explanation
    run.vendor_email = vendor_email
    run.events = events
    run.result = result
    run.vendor_name = vend_name
    run.invoice_number = extraction.get("invoice_number")
    run.amount = float(total_gross) if total_gross is not None else None
    run.currency = currency
    run.duration_ms = int((_now() - t_run) * 1000)
    session.add(run); session.commit()
    cost_usd = run.cost_usd

    yield {"type": "decision", "run_id": run_id, "result": result,
           "duration_ms": run.duration_ms, "cost_usd": cost_usd}
    session.close()


def _commit_approval(session: Session, run: Run, extraction: dict, vend_id: str, vend_name: str,
                     po_number: Optional[str], invoice_net, total_gross, inv_no_norm, inv_date,
                     currency) -> dict:
    """Write the invoice register and update the PO balance, in a fresh session."""
    po = (session.exec(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number)).first()
          if po_number else None)
    prior_billed = po_match.billed_net(session, po_number) if po_number else Decimal("0")
    reg = InvoiceRegister(
        run_id=run.id, vendor_id=vend_id, invoice_number_norm=inv_no_norm,
        invoice_number_raw=extraction.get("invoice_number") or "",
        po_number=po_number,
        invoice_date=inv_date.isoformat() if inv_date else "",
        currency=currency or "", subtotal_net=float(invoice_net or 0),
        total_gross=float(total_gross or 0), file_hash=run.file_hash, decision="APPROVE")
    session.add(reg)
    side_effects = [f"registered invoice {reg.invoice_number_raw}"]
    if po:
        billed = prior_billed + (invoice_net or Decimal("0"))
        remaining = Decimal(str(po.total)) - billed
        new_status = "closed" if remaining <= Decimal(str(po.total)) * Decimal("0.001") else "partially_billed"
        po.status = new_status
        session.add(po)
        side_effects.append(f"PO {po.po_number} billed {billed} / {po.total} -> {new_status}")
    session.commit()
    posting = {
        "vendor": vend_name, "vendor_id": vend_id,
        "invoice_number": extraction.get("invoice_number"),
        "po_number": po_number, "currency": currency,
        "net": str(invoice_net), "gross": str(total_gross),
        "gl_account": "2000 Accounts Payable",
        "lines": [{"description": li.get("description"), "amount": (li.get("amount") or {}).get("value")}
                  for li in (extraction.get("line_items") or [])],
        "side_effects": side_effects,
    }
    return posting
