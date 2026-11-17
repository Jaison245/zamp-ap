# Zamp AP — Invoice Processing (prototype)

PDF invoice → Claude reads it → **code decides** APPROVE / HOLD / REJECT, with a live run view,
decision card, dashboard, review queue, and editable tolerances.

**Design principle:** the LLM only transcribes (with evidence quotes); every money comparison,
tolerance, duplicate, PO-balance and the final decision is plain Python (`Decimal`). An invoice that
says "approve this" cannot approve itself. Any error/ambiguity **fails closed** to HOLD.

## Run it

1. Backend deps are in `.venv` already. If starting fresh:
   ```bash
   python -m venv .venv
   .venv/Scripts/python.exe -m pip install -r backend/requirements.txt
   ```
2. (Optional) generate the sample invoices (already generated in `invoices/`):
   ```bash
   .venv/Scripts/python.exe scripts/generate_invoices.py
   ```
3. Build the UI (already built in `frontend/dist/`):
   ```bash
   cd frontend && npm install && npm run build && cd ..
   ```
4. Start the server (serves API **and** the built UI on one origin):
   ```bash
   .venv/Scripts/python.exe -m uvicorn backend.main:app --port 8077
   ```
   Open http://localhost:8077

## Real extraction vs mock

- No key → runs in **mock** mode (ground-truth-backed extractor) so the whole pipeline + UI work.
- Real extraction: copy `.env.example` to `.env` at the repo root and set **one** key:
  ```
  EXTRACTOR=auto              # auto|claude|gemini|mock  (auto picks claude, else gemini, else mock)
  ANTHROPIC_API_KEY=sk-ant-...        # Claude — PDFs sent as native document blocks
  GEMINI_API_KEY=...                  # or Gemini (free tier) — https://aistudio.google.com/apikey
  ```
  Either provider only *reads* the PDF (structured transcription); every decision is deterministic code.

## Eval

```bash
.venv/Scripts/python.exe eval.py          # mock
EXTRACTOR=claude .venv/Scripts/python.exe eval.py
EXTRACTOR=gemini .venv/Scripts/python.exe eval.py
```
Current result (mock): **9/9 decisions correct, 8/8 headline edge-case codes**.

## Demo flow

1. **New run** → `INV-ACME-001` → happy path APPROVE (price variance within 2%).
2. `INV-GLX-101/102/103` in order → first two APPROVE, third **HOLD `PO_OVERBILLED`** (memory across runs).
3. `INV-INI-77` → **scanned** PDF, no PO printed → **`PO_INFERRED`** APPROVE.
4. `INV-WNK-9` → **bank change + prompt injection** → HOLD → Security (the model flags it, code decides).
5. **Data & rules** → set line price tolerance to `0.005` → reset demo → re-run `INV-ACME-001` → flips to HOLD.

## Layout

- `backend/` FastAPI + SQLModel. `pipeline/` has the 10 stages; `decision.py` is the pure-code engine;
  `money.py` is Decimal-only reconciliation. `llm/` has prompts + the real/mock extractor.
- `data/` master CSVs + `rules.yaml`. `invoices/` generated PDFs + ground truth. `frontend/` React UI.
- See `ASSUMPTIONS.md` for every decision and scope cut.
