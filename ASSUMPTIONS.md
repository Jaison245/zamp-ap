# Assumptions & Decisions — PS-1 Invoice Processing

Built for the ASA case study. Scope here is a **working prototype** (≈3–4 hrs), not the full
7-day build. Where the plan and the prototype differ, this file is the source of truth.

## Core design principle
**The LLM reads; code decides.** Claude only classifies + transcribes the document (with evidence
quotes). Every monetary comparison, tolerance, duplicate, PO-balance and the final
APPROVE / HOLD / REJECT is plain Python using `Decimal`. An invoice that literally says
"AI: approve this" therefore cannot approve itself. Second principle: **fail closed** — any error,
low confidence or ambiguity routes to HOLD with a reason, never a silent approve.

## Stack (confirmed)
- Backend: **Python 3.12 + FastAPI**, **SQLite** via SQLModel, **SSE** for live run streaming.
- Frontend: **React (Vite) + TypeScript + Tailwind**, served by Vite in dev / FastAPI static in prod.
- LLM: **Claude `claude-opus-5-5`**, PDF sent as a native `document` block (no separate OCR), with a
  strict JSON schema. A **mock extractor** (backed by per-invoice ground-truth JSON) lets the whole
  pipeline run and the eval pass with no API key; the real call activates when `ANTHROPIC_API_KEY`
  is set. Toggle via `EXTRACTOR=mock|claude|auto` (auto = claude if key present, else mock).

## Data model assumptions
- **PO `total` is net of tax** (sum of line qty×unit_price). Invoices carry tax on top; cumulative
  billing and line matching compare net amounts, tax is checked separately against `allowed_tax_rates`.
- **Cumulative billing** is tracked in an `invoice_register` table written only on APPROVE, inside a
  transaction. This is what gives the system memory across runs (split-billing overrun demo).
- Vendor matching: exact on tax ID first, then fuzzy name/alias match (rapidfuzz, threshold ~88).
- Currency is per-vendor default; a mismatch vs the PO currency is a HOLD, not a silent conversion.

## Decision outcomes
`APPROVE` (optionally with INFO notes), `HOLD` (a human must look — carries a routing target:
ap_clerk / procurement / vendor / security), `REJECT`. **All** triggered rules are surfaced, not just
the first. Reason codes are machine-readable; Claude writes the plain-English explanation from the
codes + facts only (Prompt D), and drafts (never sends) the vendor email (Prompt E).

## Confidence is computed, not self-reported
A field is trusted only if it is **grounded** (evidence quote found in the PDF text layer, fuzzy),
**reconciles** arithmetically, and (for scanned/low-legibility PDFs where grounding is impossible)
**agrees across a double read**. We ignore the model's own "confidence: 0.95".

## Tolerances (editable live in the UI → re-run the same invoice)
- Line unit price: ±2%. Invoice total vs expected: within **min(2%, $100)**.
- Cumulative billed ≤ PO total × 1.02.
- Demo moment: drop line tolerance to 0.5% and re-run the Acme invoice → flips APPROVE → HOLD.

## Security
The document is **untrusted data**. Any text addressing an AI/automation
("approve this", "ignore previous instructions") is captured into `suspicious_instructions`,
reported as `SUSPICIOUS_INSTRUCTIONS` (HOLD), and — by construction — cannot alter the decision.

## Prototype scope cuts (vs the full plan)
- 3-way match (goods receipt) is implemented but kept simple.
- Email **intake** (forward-to-inbox) and automatic multi-invoice **splitting** are out of scope;
  multiple-invoices-in-one-PDF → HOLD `MULTIPLE_INVOICES`.
- Credit notes → HOLD `CREDIT_NOTE` (not applied to balances automatically).
- Retries/backoff rely on the Anthropic SDK defaults; each stage failure → HOLD `PROCESSING_ERROR`.

## Sample data
8 vendors (1 blocked, 1 pending, 1 with aliases; US/UK/EU/IN), 7 POs, their lines and receipts, and
~9 generated invoices (text + image-only "scanned") covering the four headline edge cases plus a
clean happy path. Each invoice ships with a ground-truth JSON used by the mock extractor and the eval.
