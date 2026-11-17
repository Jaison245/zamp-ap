r"""Diagnostic: discover which Gemini models THIS key can actually use, then run
the real extraction path against the first one that works. Prints success /
failure per model. Never prints the API key.

Run from the repo root with your key set for this command only:
  (bash)  GEMINI_API_KEY=... ./.venv/Scripts/python.exe scripts/diag_gemini.py
  (PS)    $env:GEMINI_API_KEY='...'; .\.venv\Scripts\python.exe scripts\diag_gemini.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import config  # noqa: E402

print("key present:", bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

client = genai.Client()

# --- 1) List the models this key can call (that support generateContent) ---
print("\n=== Models available to your key (generateContent) ===")
available = []
try:
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            name = m.name.split("/")[-1] if m.name else str(m)
            available.append(name)
            print("  -", name)
except Exception as e:
    print("  (could not list models:", type(e).__name__, str(e)[:160], ")")

# Prefer flash models (cheap/fast), newest-looking first.
flash = [n for n in available if "flash" in n.lower() and "lite" not in n.lower()
         and "tts" not in n.lower() and "image" not in n.lower()]
flash_lite = [n for n in available if "flash-lite" in n.lower()]
# Try: configured default, then discovered flash, then flash-lite.
candidates = []
for n in [config.GEMINI_MODEL, *sorted(flash, reverse=True), *sorted(flash_lite, reverse=True)]:
    if n and n not in candidates and n in (available or [n]):
        candidates.append(n)
if not candidates:
    candidates = [config.GEMINI_MODEL]

# --- 2) Try the real extraction path on each candidate until one works ---
pdf_bytes = (config.INVOICES_DIR / "INV-ACME-001.pdf").read_bytes()
instruction = "Extract this invoice as JSON: invoice_number, vendor name, and total."

print("\n=== Trying extraction (stops at first success) ===")
winner = None
for model in candidates:
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), instruction],
            config=types.GenerateContentConfig(response_mime_type="application/json",
                                               max_output_tokens=2000, temperature=0),
        )
        dt = time.time() - t0
        print(f"  OK  {model}  ({dt:.1f}s)  -> {(resp.text or '')[:120]}")
        winner = model
        break
    except Exception as e:
        dt = time.time() - t0
        print(f"  FAIL {model}  ({dt:.1f}s)  {type(e).__name__}: {str(e)[:140]}")

print("\n=== RESULT ===")
if winner:
    print(f"WORKING MODEL: {winner}")
    print(f"Tell Claude this name, or set it yourself in .env:  GEMINI_MODEL={winner}")
else:
    print("No model succeeded. If everything says 503/overloaded, wait a few minutes and re-run.")
    print("If everything says 404/permission, paste the model list above to Claude.")
