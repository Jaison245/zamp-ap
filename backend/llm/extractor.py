"""Extraction layer: real Claude (PDF document block + forced-tool structured output) and a
ground-truth-backed mock so the whole pipeline + eval run with no API key.

Mode is chosen by config.extractor_mode():  mock | claude  (auto resolves to one of these).
"""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from .. import config
from . import prompts

# rough display-only rates (USD per token); override via env if you know the real numbers
_IN_RATE = float(os.getenv("PRICE_IN_PER_MTOK", "15")) / 1_000_000
_OUT_RATE = float(os.getenv("PRICE_OUT_PER_MTOK", "75")) / 1_000_000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- mock ----
_MOCK: dict[str, dict] | None = None


def _mock_index() -> dict[str, dict]:
    global _MOCK
    if _MOCK is None:
        _MOCK = {}
        for truth in config.INVOICES_DIR.glob("*.truth.json"):
            data = json.loads(truth.read_text(encoding="utf-8"))
            pdf = config.INVOICES_DIR / f"{data['id']}.pdf"
            if pdf.exists():
                _MOCK[sha256(pdf.read_bytes())] = data
    return _MOCK


def _mock_extract(pdf_bytes: bytes) -> tuple[dict, dict]:
    hit = _mock_index().get(sha256(pdf_bytes))
    if hit:
        return copy.deepcopy(hit["extraction"]), {"mode": "mock", "cost_usd": 0.0, "tokens": 0}
    # unknown upload in mock mode: minimal, honest "couldn't read" payload -> pipeline will HOLD/REJECT
    return (
        {"document_type": "other", "contains_multiple_invoices": False, "line_items": [],
         "total": {"raw": None, "value": None}, "legibility": "poor",
         "missing_fields": ["invoice_number", "invoice_date", "total", "vendor"],
         "extraction_warnings": ["No ground truth for this file; run in claude mode for a real read."],
         "suspicious_instructions": [], "evidence": {}},
        {"mode": "mock", "cost_usd": 0.0, "tokens": 0, "unknown": True},
    )


# -------------------------------------------------------------- claude ----
def _client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


def _claude_extract(pdf_bytes: bytes, extra_system: str = "") -> tuple[dict, dict]:
    client = _client()
    b64 = base64.standard_b64encode(pdf_bytes).decode()
    tool = {"name": "record_extraction",
            "description": "Record the transcribed document fields.",
            "input_schema": prompts.EXTRACTION_SCHEMA}
    msg = client.messages.create(
        model=config.MODEL,
        max_tokens=8000,
        system=prompts.SYSTEM_EXTRACT + (("\n\n" + extra_system) if extra_system else ""),
        tools=[tool],
        tool_choice={"type": "tool", "name": "record_extraction"},
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
            {"type": "text", "text": "Extract this document into the tool schema."},
        ]}],
    )
    data = {}
    for block in msg.content:
        if block.type == "tool_use" and block.name == "record_extraction":
            data = block.input
            break
    usage = msg.usage
    cost = usage.input_tokens * _IN_RATE + usage.output_tokens * _OUT_RATE
    return data, {"mode": "claude", "cost_usd": round(cost, 4),
                  "tokens": usage.input_tokens + usage.output_tokens,
                  "in": usage.input_tokens, "out": usage.output_tokens}


# ------------------------------------------------------------ public ------
def run_extraction(pdf_bytes: bytes) -> tuple[dict, dict]:
    if config.extractor_mode() == "claude":
        return _claude_extract(pdf_bytes)
    return _mock_extract(pdf_bytes)


def double_read(pdf_bytes: bytes) -> tuple[dict, dict, list[str]]:
    """Run twice; return (primary, secondary, disagreeing_key_fields)."""
    a, meta_a = run_extraction(pdf_bytes)
    b, _ = run_extraction(pdf_bytes)
    keys = ["invoice_number", "total", "po_reference"]
    disagree = []

    def getv(d, k):
        v = d.get(k)
        if isinstance(v, dict):
            v = v.get("value") or v.get("iso") or v.get("raw")
        return v
    for k in keys:
        if getv(a, k) != getv(b, k):
            disagree.append(k)
    return a, b, disagree


def explain_decision(decision_ctx: dict) -> str:
    if config.extractor_mode() == "claude":
        try:
            client = _client()
            msg = client.messages.create(
                model=config.MODEL, max_tokens=300,
                messages=[{"role": "user", "content": prompts.EXPLAIN.format(
                    decision=json.dumps(decision_ctx, default=str))}])
            return "".join(b.text for b in msg.content if b.type == "text").strip()
        except Exception:
            pass
    return _template_explanation(decision_ctx)


def draft_vendor_email(facts: dict) -> Optional[str]:
    needs = facts.get("needs_vendor")
    if not needs:
        return None
    if config.extractor_mode() == "claude":
        try:
            client = _client()
            msg = client.messages.create(
                model=config.MODEL, max_tokens=400,
                messages=[{"role": "user", "content": prompts.VENDOR_EMAIL.format(
                    number=facts.get("invoice_number", ""), facts=json.dumps(facts, default=str))}])
            return "".join(b.text for b in msg.content if b.type == "text").strip()
        except Exception:
            pass
    return _template_email(facts)


# --------------------------------------------------- deterministic fallbacks ----
def _clean_msg(msg: str) -> str:
    return (msg or "").strip().rstrip(".").strip()


def _template_explanation(ctx: dict) -> str:
    decision = ctx.get("decision")
    codes = ctx.get("codes") or []
    vendor = ctx.get("vendor") or "the vendor"
    amount = ctx.get("amount")
    cur = ctx.get("currency") or ""
    if decision == "APPROVE":
        info = next((c for c in codes if c.get("outcome") == "INFO"), None)
        note = f" ({_clean_msg(info['message'])})" if info else ""
        return (f"Approved: invoice {ctx.get('invoice_number','')} from {vendor} for {cur} {amount} "
                f"passed vendor, duplicate, PO and line checks{note}. Post it for payment.")
    flags = [c for c in codes if c.get("outcome") != "INFO"]
    top = flags[0] if flags else (codes[0] if codes else None)
    if not top:
        return f"{decision}: this invoice from {vendor} needs review."
    others = "; ".join(_clean_msg(c["message"]) for c in flags[1:4] if c is not top)
    tail = f" Also: {others}." if others else ""
    nxt = (f" Route to {top.get('routing_label')}." if top.get("routing_label") else "")
    verb = "Rejected" if decision == "REJECT" else "On hold"
    return f"{verb}: {_clean_msg(top['message'])}.{tail}{nxt}"


def _template_email(facts: dict) -> str:
    num = facts.get("invoice_number", "")
    reasons = facts.get("reasons", [])
    bank = any("BANK" in (r or "") for r in facts.get("codes", []))
    body = [f"Dear {facts.get('vendor','Accounts team')},", "",
            f"Thank you for invoice {num}. We are unable to process it yet for the following reason(s):"]
    for r in reasons:
        body.append(f"  - {r}")
    if bank:
        body.append("")
        body.append("For the change in bank details, please confirm the account by calling us on the "
                     "number held on your account before we can proceed.")
    body += ["", "Could you review and resend the corrected invoice at your convenience?",
             "", "Kind regards,", "Accounts Payable"]
    return "\n".join(body)
