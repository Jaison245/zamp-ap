"""FastAPI app: run endpoints, SSE live stream, dashboard, review queue, data & rules, demo reset."""
from __future__ import annotations
import json
import shutil
from collections import Counter
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from . import config
from .db import get_session, init_db, reset_demo
from .models import GoodsReceipt, InvoiceRegister, POLine, PurchaseOrder, ReviewAction, Run, Vendor
from .pipeline import orchestrator
from .pipeline.po_match import billed_net

app = FastAPI(title="Zamp AP — Invoice Processing")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "extractor": config.extractor_mode(), "model": config.MODEL}


# ----------------------------------------------------------------- samples ----
@app.get("/api/samples")
def samples():
    idx = config.INVOICES_DIR / "index.json"
    return json.loads(idx.read_text(encoding="utf-8")) if idx.exists() else []


@app.get("/api/samples/{sample_id}/pdf")
def sample_pdf(sample_id: str):
    p = config.INVOICES_DIR / f"{sample_id}.pdf"
    if not p.exists():
        raise HTTPException(404, "sample not found")
    return FileResponse(p, media_type="application/pdf")


# -------------------------------------------------------------------- runs ----
@app.post("/api/runs")
async def create_run(file: Optional[UploadFile] = File(None), sample_id: Optional[str] = Form(None)):
    if not file and not sample_id:
        raise HTTPException(400, "provide a file or a sample_id")
    with get_session() as s:
        run = Run(source="sample" if sample_id else "upload",
                  sample_id=sample_id,
                  filename=(sample_id + ".pdf") if sample_id else (file.filename or "upload.pdf"))
        s.add(run); s.commit(); s.refresh(run)
        run_id = run.id

    dest = config.UPLOADS_DIR / f"{run_id}.pdf"
    if sample_id:
        src = config.INVOICES_DIR / f"{sample_id}.pdf"
        if not src.exists():
            raise HTTPException(404, "sample not found")
        shutil.copyfile(src, dest)
    else:
        with open(dest, "wb") as f:
            f.write(await file.read())
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}/stream")
def stream_run(run_id: int):
    def gen():
        try:
            for event in orchestrator.run_pipeline(run_id):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:  # fail closed
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield "event: end\ndata: {}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/runs")
def list_runs():
    with get_session() as s:
        runs = s.exec(select(Run).order_by(Run.id.desc())).all()
        return [{"id": r.id, "vendor": r.vendor_name, "invoice_number": r.invoice_number,
                 "amount": r.amount, "currency": r.currency, "decision": r.decision,
                 "top_reason": (r.decision_codes[0]["code"] if r.decision_codes else None),
                 "status": r.status, "duration_ms": r.duration_ms, "cost_usd": r.cost_usd,
                 "source": r.source, "created_at": r.created_at.isoformat()} for r in runs]


@app.get("/api/runs/{run_id}")
def get_run(run_id: int):
    with get_session() as s:
        r = s.get(Run, run_id)
        if not r:
            raise HTTPException(404, "run not found")
        reviews = s.exec(select(ReviewAction).where(ReviewAction.run_id == run_id)).all()
        return {"id": r.id, "filename": r.filename, "source": r.source, "status": r.status,
                "decision": r.decision, "codes": r.decision_codes, "explanation": r.explanation,
                "vendor_email": r.vendor_email, "events": r.events, "result": r.result,
                "vendor": r.vendor_name, "invoice_number": r.invoice_number, "amount": r.amount,
                "currency": r.currency, "duration_ms": r.duration_ms, "cost_usd": r.cost_usd,
                "reviews": [{"action": rv.action, "comment": rv.comment, "actor": rv.actor,
                             "created_at": rv.created_at.isoformat()} for rv in reviews]}


@app.get("/api/runs/{run_id}/pdf")
def run_pdf(run_id: int):
    p = config.UPLOADS_DIR / f"{run_id}.pdf"
    if not p.exists():
        raise HTTPException(404, "pdf not found")
    return FileResponse(p, media_type="application/pdf")


# -------------------------------------------------------------- dashboard ----
@app.get("/api/dashboard")
def dashboard():
    with get_session() as s:
        runs = [r for r in s.exec(select(Run)).all() if r.status == "done"]
    total = len(runs)
    mix = Counter(r.decision for r in runs)
    approved = mix.get("APPROVE", 0)
    durations = [r.duration_ms for r in runs if r.duration_ms]
    costs = [r.cost_usd for r in runs if r.cost_usd]
    hold_reasons = Counter()
    for r in runs:
        if r.decision in ("HOLD", "REJECT") and r.decision_codes:
            hold_reasons[r.decision_codes[0]["code"]] += 1
    return {
        "total_processed": total,
        "auto_approval_rate": round(approved / total * 100, 1) if total else 0,
        "on_hold": mix.get("HOLD", 0),
        "rejected": mix.get("REJECT", 0),
        "total_value": round(sum(r.amount or 0 for r in runs if r.decision == "APPROVE"), 2),
        "avg_ms": int(sum(durations) / len(durations)) if durations else 0,
        "avg_cost": round(sum(costs) / len(costs), 4) if costs else 0,
        "decision_mix": dict(mix),
        "top_hold_reasons": hold_reasons.most_common(6),
    }


# ------------------------------------------------------------- review queue ----
@app.get("/api/review")
def review_queue():
    with get_session() as s:
        runs = s.exec(select(Run).where(Run.decision == "HOLD").order_by(Run.id.desc())).all()
        return [{"id": r.id, "vendor": r.vendor_name, "invoice_number": r.invoice_number,
                 "amount": r.amount, "currency": r.currency,
                 "codes": r.decision_codes, "explanation": r.explanation,
                 "routing": (r.result or {}).get("routing")} for r in runs]


@app.post("/api/review/{run_id}")
def review_action(run_id: int, payload: dict):
    action = payload.get("action")
    if action not in ("approve", "reject", "request_info"):
        raise HTTPException(400, "invalid action")
    with get_session() as s:
        r = s.get(Run, run_id)
        if not r:
            raise HTTPException(404, "run not found")
        s.add(ReviewAction(run_id=run_id, action=action, comment=payload.get("comment", ""),
                           actor=payload.get("actor", "reviewer")))
        if action == "approve":
            r.decision = "APPROVE_OVERRIDE"
        elif action == "reject":
            r.decision = "REJECT_OVERRIDE"
        s.add(r); s.commit()
    return {"ok": True}


# --------------------------------------------------------------- data & rules ----
@app.get("/api/data")
def data_view():
    with get_session() as s:
        vendors = s.exec(select(Vendor)).all()
        pos = s.exec(select(PurchaseOrder)).all()
        receipts = s.exec(select(GoodsReceipt)).all()
        lines = s.exec(select(POLine)).all()
        po_view = []
        for po in pos:
            billed = float(billed_net(s, po.po_number))
            po_view.append({"po_number": po.po_number, "vendor_id": po.vendor_id,
                            "currency": po.currency, "total": po.total, "status": po.status,
                            "billed": round(billed, 2), "remaining": round(po.total - billed, 2)})
        return {
            "vendors": [v.model_dump() for v in vendors],
            "purchase_orders": po_view,
            "po_lines": [l.model_dump() for l in lines],
            "receipts": [r.model_dump() for r in receipts],
        }


@app.get("/api/rules")
def get_rules():
    return config.load_rules(force=True)


@app.put("/api/rules")
def put_rules(rules: dict):
    return config.save_rules(rules)


@app.post("/api/reset")
def reset():
    reset_demo()
    return {"ok": True}


# ----------------------------------------------------------- static frontend ----
if config.FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIST), html=True), name="frontend")
