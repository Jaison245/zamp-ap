"""SQLite engine + session + startup data load (idempotent)."""
from __future__ import annotations
import csv

from sqlmodel import Session, SQLModel, create_engine, select

from . import config
from .models import GoodsReceipt, POLine, PurchaseOrder, Vendor

engine = create_engine(
    f"sqlite:///{config.DB_PATH}",
    connect_args={"check_same_thread": False},
)


def get_session() -> Session:
    return Session(engine)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    load_master_data()


def _rows(name: str):
    path = config.DATA_DIR / name
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def load_master_data(force: bool = False) -> None:
    """Load CSV master data into SQLite. Skips if vendors already present (unless force)."""
    with get_session() as s:
        if not force and s.exec(select(Vendor)).first():
            return
        if force:
            for model in (Vendor, PurchaseOrder, POLine, GoodsReceipt):
                for obj in s.exec(select(model)).all():
                    s.delete(obj)
            s.commit()

        for r in _rows("vendors.csv"):
            s.add(Vendor(
                vendor_id=r["vendor_id"], legal_name=r["legal_name"], aliases=r["aliases"],
                tax_id=r["tax_id"], country=r["country"], currency=r["currency"],
                bank_account_name=r["bank_account_name"], iban_or_account=r["iban_or_account"],
                payment_terms=r["payment_terms"], status=r["status"], contact_email=r["contact_email"],
            ))
        for r in _rows("purchase_orders.csv"):
            s.add(PurchaseOrder(
                po_number=r["po_number"], vendor_id=r["vendor_id"], po_date=r["po_date"],
                currency=r["currency"], total=float(r["total"]), status=r["status"],
            ))
        for r in _rows("po_lines.csv"):
            s.add(POLine(
                po_number=r["po_number"], line_no=int(r["line_no"]), sku=r["sku"],
                description=r["description"], qty=float(r["qty"]), unit_price=float(r["unit_price"]),
                tax_rate=float(r["tax_rate"]),
            ))
        for r in _rows("goods_receipts.csv"):
            s.add(GoodsReceipt(
                po_number=r["po_number"], line_no=int(r["line_no"]),
                qty_received=float(r["qty_received"]), received_date=r["received_date"],
            ))
        s.commit()


def reset_demo() -> None:
    """Clear process state (runs, register, reviews) and reload master data. For the demo reset button."""
    from .models import InvoiceRegister, ReviewAction, Run
    with get_session() as s:
        for model in (InvoiceRegister, ReviewAction, Run):
            for obj in s.exec(select(model)).all():
                s.delete(obj)
        s.commit()
    load_master_data(force=True)
