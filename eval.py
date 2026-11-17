"""Eval harness: run every sample invoice through the real pipeline and compare the decision (and,
in claude mode, field accuracy) against the ground truth. Run order matters (register has memory).

Usage:  python eval.py            # uses EXTRACTOR mode from env (.env); mock if no key
        EXTRACTOR=claude python eval.py
"""
from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend import config                       # noqa: E402
from backend.db import get_session, init_db, reset_demo  # noqa: E402
from backend.models import Run                   # noqa: E402
from backend.pipeline import orchestrator        # noqa: E402

# Run in a stable order: ACME-001 before its resend; GLX in sequence.
ORDER = ["INV-ACME-001", "INV-GLX-101", "INV-GLX-102", "INV-GLX-103", "INV-INI-77",
         "INV-ACME-001-RESEND", "INV-WNK-9", "INV-SOY-5", "QUOTE-STARK-1"]


def run_sample(sample_id: str) -> dict:
    with get_session() as s:
        run = Run(source="sample", sample_id=sample_id, filename=f"{sample_id}.pdf")
        s.add(run); s.commit(); s.refresh(run)
        rid = run.id
    shutil.copyfile(config.INVOICES_DIR / f"{sample_id}.pdf", config.UPLOADS_DIR / f"{rid}.pdf")
    final = None
    for ev in orchestrator.run_pipeline(rid):
        if ev.get("type") == "decision":
            final = ev
    with get_session() as s:
        r = s.get(Run, rid)
        return {"decision": r.decision, "codes": [c["code"] for c in (r.decision_codes or [])],
                "run_id": rid, "amount": r.amount}


def main() -> int:
    init_db()
    reset_demo()
    truths = {p.stem.replace(".truth", ""): json.loads(p.read_text(encoding="utf-8"))
              for p in config.INVOICES_DIR.glob("*.truth.json")}
    print(f"\nExtractor mode: {config.extractor_mode()}  |  model: {config.MODEL}\n")
    print(f"{'invoice':<22}{'expected':<10}{'actual':<10}{'codes':<34}{'ok'}")
    print("-" * 92)
    ok_count = 0
    code_hits = code_total = 0
    for sid in ORDER:
        truth = truths[sid]
        res = run_sample(sid)
        exp = truth["expected_decision"]
        got = res["decision"]
        good = (got == exp)
        ok_count += good
        # expected-codes recall (did we surface the headline codes?)
        for c in truth.get("expected_codes", []):
            code_total += 1
            if c in res["codes"]:
                code_hits += 1
        codes = ",".join(res["codes"])[:33]
        print(f"{sid:<22}{exp:<10}{got:<10}{codes:<34}{'OK' if good else 'XX'}")
    n = len(ORDER)
    print("-" * 92)
    print(f"\nDecision accuracy : {ok_count}/{n}  ({ok_count/n*100:.0f}%)")
    if code_total:
        print(f"Headline-code recall: {code_hits}/{code_total}  ({code_hits/code_total*100:.0f}%)")
    return 0 if ok_count == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
