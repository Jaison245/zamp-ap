"""Line-level 2-way / 3-way match, cumulative billing, tax-rate and currency checks."""
from __future__ import annotations
from decimal import Decimal
from typing import Optional

from rapidfuzz import fuzz
from sqlmodel import Session, select

from ..config import load_rules
from ..models import GoodsReceipt, POLine, PurchaseOrder, Vendor
from .money import D, pct_diff
from .po_match import billed_net


def _match_line(inv_desc: str, inv_sku: str, po_lines: list[POLine]) -> Optional[POLine]:
    if inv_sku:
        for pl in po_lines:
            if pl.sku and pl.sku.lower() == inv_sku.lower():
                return pl
    best, best_s = None, 0
    for pl in po_lines:
        s = fuzz.token_set_ratio(inv_desc, pl.description)
        if s > best_s:
            best, best_s = pl, s
    return best if best_s >= 60 else None


def match_lines(session: Session, po: Optional[PurchaseOrder], vendor: Optional[Vendor],
                extraction: dict, invoice_net: Optional[Decimal], currency: Optional[str]) -> dict:
    findings: list[dict] = []
    rows: list[dict] = []
    rules = load_rules()
    line_tol = Decimal(str(rules["tolerances"]["line_price_pct"]))
    cum_tol = Decimal(str(rules["tolerances"]["cumulative_po_pct"]))

    # tax-rate allowance (per vendor country)
    if vendor:
        allowed = [Decimal(str(x)) for x in rules.get("allowed_tax_rates", {}).get(vendor.country, [])]
        if allowed:
            for tl in extraction.get("tax_lines") or []:
                rate = D(tl.get("rate"))
                if rate is not None and rate not in allowed:
                    findings.append({"code": "TAX_RATE_UNEXPECTED",
                                     "message": f"Tax rate {rate} not allowed for {vendor.country}.",
                                     "evidence": f"allowed: {allowed}"})

    if not po:
        return {"findings": findings, "rows": rows}

    # currency vs PO
    if currency and po.currency and currency != po.currency:
        findings.append({"code": "CURRENCY_MISMATCH",
                         "message": f"Invoice in {currency}, PO {po.po_number} in {po.currency}.",
                         "evidence": f"{currency} vs {po.currency}"})

    po_lines = session.exec(select(POLine).where(POLine.po_number == po.po_number)).all()
    receipts: dict[int, float] = {}
    for gr in session.exec(select(GoodsReceipt).where(GoodsReceipt.po_number == po.po_number)).all():
        receipts[gr.line_no] = receipts.get(gr.line_no, 0.0) + gr.qty_received

    three_way = bool(receipts)
    within_tol_variance = False
    for li in extraction.get("line_items") or []:
        inv_desc = str(li.get("description") or "")
        inv_sku = str(li.get("sku") or "")
        qty = D(li.get("quantity"))
        unit = D(li.get("unit_price"))
        pl = _match_line(inv_desc, inv_sku, po_lines)
        row = {"description": inv_desc, "sku": inv_sku,
               "inv_qty": str(qty) if qty is not None else None,
               "inv_unit": str(unit) if unit is not None else None,
               "po_sku": pl.sku if pl else None,
               "po_qty": pl.qty if pl else None,
               "po_unit": pl.unit_price if pl else None,
               "received": receipts.get(pl.line_no) if pl else None,
               "status": "ok", "notes": []}
        if not pl:
            row["status"] = "warn"; row["notes"].append("no PO line matched")
            rows.append(row); continue

        if unit is not None:
            variance = pct_diff(unit, Decimal(str(pl.unit_price)))
            row["variance_pct"] = round(float(variance) * 100, 2)
            if abs(variance) > line_tol:
                row["status"] = "fail"; row["notes"].append(f"price {row['variance_pct']}% > tol")
                findings.append({"code": "PRICE_VARIANCE",
                                 "message": f"'{inv_desc}': {row['variance_pct']}% vs PO (tol {float(line_tol)*100:g}%).",
                                 "evidence": f"{unit} vs {pl.unit_price}"})
            elif abs(variance) > 0:
                within_tol_variance = True
                row["notes"].append(f"within tol ({row['variance_pct']}%)")

        if qty is not None and qty > Decimal(str(pl.qty)):
            row["status"] = "fail"; row["notes"].append("qty > ordered")
            findings.append({"code": "QTY_EXCEEDS_ORDERED",
                             "message": f"'{inv_desc}': billed {qty} > ordered {pl.qty}.",
                             "evidence": f"{qty} vs {pl.qty}"})
        if three_way and qty is not None and pl.line_no in receipts and qty > Decimal(str(receipts[pl.line_no])):
            row["status"] = "fail"; row["notes"].append("qty > received")
            findings.append({"code": "QTY_EXCEEDS_RECEIVED",
                             "message": f"'{inv_desc}': billed {qty} > received {receipts[pl.line_no]}.",
                             "evidence": f"{qty} vs {receipts[pl.line_no]}"})
        rows.append(row)

    # cumulative billing (split invoices)
    if invoice_net is not None:
        prior = billed_net(session, po.po_number)
        cumulative = prior + invoice_net
        limit = Decimal(str(po.total)) * (Decimal("1") + cum_tol)
        if cumulative > limit:
            findings.append({"code": "PO_OVERBILLED",
                             "message": f"Cumulative {cumulative} > PO {po.po_number} total {po.total} "
                                        f"(prior {prior} + this {invoice_net}).",
                             "evidence": f"limit {limit}"})
    if within_tol_variance and not any(f["code"] == "PRICE_VARIANCE" for f in findings):
        findings.append({"code": "PRICE_WITHIN_TOLERANCE",
                         "message": f"Line price variance within the {float(line_tol)*100:g}% tolerance."})
    if three_way and not any(f["code"].startswith("QTY_") for f in findings):
        findings.append({"code": "THREE_WAY_MATCHED", "message": f"Matched against goods receipt for {po.po_number}."})

    return {"findings": findings, "rows": rows}
