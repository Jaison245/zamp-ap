r"""Diagnostic: exercise the exact Gemini extraction path used by the pipeline,
against a real sample invoice, and print only success/failure + error text.
Never prints the API key.

Run from the repo root with your key set for this command only:
  (bash)  GEMINI_API_KEY=... ./.venv/Scripts/python.exe scripts/diag_gemini.py
  (PS)    $env:GEMINI_API_KEY='...'; .\.venv\Scripts\python.exe scripts\diag_gemini.py
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import config  # noqa: E402
from backend.llm import extractor  # noqa: E402

print("extractor_mode:", config.extractor_mode())
print("gemini model:", config.GEMINI_MODEL)
print("key present:", bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")))

pdf_path = config.INVOICES_DIR / "INV-ACME-001.pdf"
pdf_bytes = pdf_path.read_bytes()
print(f"sample pdf: {pdf_path.name} ({len(pdf_bytes)} bytes)")

t0 = time.time()
try:
    data, meta = extractor._gemini_extract(pdf_bytes)
    dt = time.time() - t0
    print(f"\nOK in {dt:.1f}s  meta={meta}")
    print("invoice_number:", data.get("invoice_number"))
    print("total:", data.get("total"))
    print("vendor:", (data.get("vendor") or {}).get("name"))
except Exception as e:
    dt = time.time() - t0
    print(f"\nFAILED after {dt:.1f}s: {type(e).__name__}: {e}")
    traceback.print_exc()
