"""Extraction layer: real Claude (PDF document block + forced-tool structured output) and a
ground-truth-backed mock so the whole pipeline + eval run with no API key.

Mode is chosen by config.extractor_mode():  mock | claude | gemini  (auto resolves to one of these).
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


# -------------------------------------------------------------- gemini ----
# Gemini reads the PDF natively and returns JSON. Same contract as the Claude
# path: the model only transcribes — all decisions stay in deterministic code.
_GEM_IN_RATE = float(os.getenv("GEMINI_PRICE_IN_PER_MTOK", "0.30")) / 1_000_000
_GEM_OUT_RATE = float(os.getenv("GEMINI_PRICE_OUT_PER_MTOK", "2.50")) / 1_000_000


def _gemini_client():
    from google import genai
    return genai.Client()  # reads GEMINI_API_KEY / GOOGLE_API_KEY from env


def _parse_json(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j != -1:
            return json.loads(t[i:j + 1])
        raise


def _gemini_extract(pdf_bytes: bytes, extra_system: str = "") -> tuple[dict, dict]:
    from google.genai import types
    client = _gemini_client()
    system = prompts.SYSTEM_EXTRACT + (("\n\n" + extra_system) if extra_system else "")
    instruction = ("Extract this document. Return ONLY a JSON object matching this schema "
                   "(no markdown, no commentary):\n" + json.dumps(prompts.EXTRACTION_SCHEMA))
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            instruction,
        ],
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            max_output_tokens=8000,
            temperature=0,
        ),
    )
    data = _parse_json(resp.text)
    um = getattr(resp, "usage_metadata", None)
    pin = getattr(um, "prompt_token_count", 0) or 0
    pout = getattr(um, "candidates_token_count", 0) or 0
    cost = pin * _GEM_IN_RATE + pout * _GEM_OUT_RATE
    return data, {"mode": "gemini", "cost_usd": round(cost, 4),
                  "tokens": pin + pout, "in": pin, "out": pout}


def _gemini_text(prompt: str, max_tokens: int) -> str:
    from google.genai import types
    client = _gemini_client()
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=max_tokens, temperature=0.2),
    )
    return (resp.text or "").strip()


# ------------------------------------------------------------ public ------
def run_extraction(pdf_bytes: bytes) -> tuple[dict, dict]:
    mode = config.extractor_mode()
    if mode == "claude":
        return _claude_extract(pdf_bytes)
    if mode == "gemini":
        return _gemini_extract(pdf_bytes)
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


def _claude_text(prompt: str, max_tokens: int) -> str:
    client = _client()
    msg = client.messages.create(
        model=config.MODEL, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def _llm_text(prompt: str, max_tokens: int) -> Optional[str]:
    """Free-text generation via the active provider; None if not in an LLM mode or on error."""
    mode = config.extractor_mode()
    try:
        if mode == "claude":
            return _claude_text(prompt, max_tokens)
        if mode == "gemini":
            return _gemini_text(prompt, max_tokens)
    except Exception:
        return None
    return None


def explain_decision(decision_ctx: dict) -> str:
    out = _llm_text(prompts.EXPLAIN.format(decision=json.dumps(decision_ctx, default=str)), 300)
    return out or _template_explanation(decision_ctx)


def draft_vendor_email(facts: dict) -> Optional[str]:
    if not facts.get("needs_vendor"):
        return None
    out = _llm_text(prompts.VENDOR_EMAIL.format(
        number=facts.get("invoice_number", ""), facts=json.dumps(facts, default=str)), 400)
    return out or _template_email(facts)


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
