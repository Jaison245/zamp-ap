"""All money math. Decimal only — never float. Arithmetic reconciliation of an extraction."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

CENT = Decimal("0.01")


def D(val) -> Optional[Decimal]:
    """Coerce an amount object / string / number to Decimal. Returns None if not parseable."""
    if val is None:
        return None
    if isinstance(val, dict):
        val = val.get("value", val.get("raw"))
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    s = str(val).strip()
    if not s:
        return None
    # strip currency symbols / codes / spaces, normalise separators
    s = s.replace(" ", " ")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    keep = []
    for ch in s:
        if ch.isdigit() or ch in ".,-":
            keep.append(ch)
    s = "".join(keep)
    if s.count(",") and s.count("."):
        # the rightmost separator is the decimal point
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") and not s.count("."):
        # comma could be decimal (1.234,56 style) or thousands (1,234) — decide by position
        if len(s) - s.rfind(",") - 1 == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return -d if neg else d


def q(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def approx(a: Optional[Decimal], b: Optional[Decimal], tol: Decimal = CENT) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def pct_diff(actual: Decimal, expected: Decimal) -> Decimal:
    if expected == 0:
        return Decimal("0") if actual == 0 else Decimal("1")
    return (actual - expected) / expected


def reconcile(extraction: dict) -> tuple[bool, list[dict]]:
    """Return (ok, checks). Each check: {name, ok, detail}. Tolerant of tax-inclusive pricing."""
    checks: list[dict] = []
    ok = True

    # 1. per-line qty * unit_price == amount
    line_sum = Decimal("0")
    for i, li in enumerate(extraction.get("line_items") or [], 1):
        qty = D(li.get("quantity"))
        unit = D(li.get("unit_price"))
        amt = D(li.get("amount"))
        if amt is not None:
            line_sum += amt
        if qty is not None and unit is not None and amt is not None:
            expect = q(qty * unit)
            good = approx(expect, amt, Decimal("0.02"))
            ok = ok and good
            checks.append({"name": f"line {i}: qty*price=amount", "ok": good,
                           "detail": f"{qty} x {unit} = {expect} vs {amt}"})

    subtotal = D(extraction.get("subtotal"))
    if subtotal is not None and extraction.get("line_items"):
        good = approx(line_sum, subtotal, Decimal("0.05"))
        ok = ok and good
        checks.append({"name": "sum(lines)=subtotal", "ok": good, "detail": f"{q(line_sum)} vs {subtotal}"})

    # 2. tax amount == subtotal * rate (per tax line)
    tax_total = Decimal("0")
    for tl in extraction.get("tax_lines") or []:
        rate = D(tl.get("rate"))
        amt = D(tl.get("amount"))
        if amt is not None:
            tax_total += amt
        if rate is not None and amt is not None and subtotal is not None and not extraction.get("tax_inclusive"):
            expect = q(subtotal * rate)
            good = approx(expect, amt, Decimal("0.05"))
            ok = ok and good
            checks.append({"name": f"tax {tl.get('label','')}={rate}*subtotal", "ok": good,
                           "detail": f"{expect} vs {amt}"})

    # 3. subtotal - discount + shipping + tax == total
    total = D(extraction.get("total"))
    discount = D(extraction.get("discount")) or Decimal("0")
    shipping = D(extraction.get("shipping")) or Decimal("0")
    if total is not None and subtotal is not None:
        if extraction.get("tax_inclusive"):
            expect = q(subtotal - discount + shipping)
        else:
            expect = q(subtotal - discount + shipping + tax_total)
        good = approx(expect, total, Decimal("0.05"))
        ok = ok and good
        checks.append({"name": "subtotal-disc+ship+tax=total", "ok": good, "detail": f"{expect} vs {total}"})

    return ok, checks
