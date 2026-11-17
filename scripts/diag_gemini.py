r"""Full diagnostic: run the REAL extraction (with coercion) once, dump exactly
what the model returned, then run each downstream stage and print the exact
exception if any. One API call. Never prints the API key.

Run from the repo root with your key set for this command only:
  (PS)  $env:GEMINI_API_KEY='...'; .\.venv\Scripts\python.exe scripts\diag_gemini.py
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import config  # noqa: E402
from backend.db import engine, init_db  # noqa: E402
from backend.llm import extractor  # noqa: E402
from backend.pipeline import duplicates, lines, normalize, po_match, money  # noqa: E402
from backend.pipeline import vendor as vendor_mod  # noqa: E402
from sqlmodel import Session  # noqa: E402

print("extractor_mode:", config.extractor_mode(), "| model:", config.GEMINI_MODEL)
init_db()

pdf = config.INVOICES_DIR / "INV-ACME-001.pdf"
pdf_bytes = pdf.read_bytes()

print("\n=== running extraction (1 API call) ===")
try:
    extraction, meta = extractor.run_extraction(pdf_bytes)
except Exception as e:
    print("EXTRACTION ITSELF FAILED:", type(e).__name__, e)
    sys.exit(1)
print("meta:", meta)

print("\n=== RAW EXTRACTION (what the model returned, after coercion) ===")
print(json.dumps(extraction, indent=2, default=str)[:4000])

file_hash = extractor.sha256(pdf_bytes)
inv_date = normalize.parse_iso(extraction.get("invoice_date"))
invoice_net = money.D(extraction.get("subtotal")) or money.D(extraction.get("total"))
total_gross = money.D(extraction.get("total"))
currency = normalize.infer_currency(extraction, None)


def step(name, fn):
    try:
        fn()
        print(f"  OK   {name}")
    except Exception as e:
        print(f"  FAIL {name}: {type(e).__name__}: {e}")
        traceback.print_exc()


print("\n=== running each stage against the extraction ===")
with Session(engine) as s:
    vend_holder = {}

    def _vendor():
        vend_holder["v"] = vendor_mod.validate_vendor(s, extraction)
    step("vendor.validate_vendor", _vendor)
    vend = (vend_holder.get("v") or {}).get("vendor")

    step("duplicates.check_duplicates",
         lambda: duplicates.check_duplicates(s, vend, extraction, file_hash, total_gross, inv_date))
    step("po_match.match_po",
         lambda: po_match.match_po(s, vend, extraction, invoice_net, currency))
    step("lines.match_lines",
         lambda: lines.match_lines(s, None, vend, extraction, invoice_net, currency))

print("\n=== DONE ===")
