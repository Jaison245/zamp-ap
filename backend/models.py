"""SQLModel tables. Master data (vendors/POs/lines/receipts) + process state
(invoice_register, runs, review actions)."""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Vendor(SQLModel, table=True):
    vendor_id: str = Field(primary_key=True)
    legal_name: str
    aliases: str = ""           # pipe-separated
    tax_id: str = ""
    country: str = ""
    currency: str = ""
    bank_account_name: str = ""
    iban_or_account: str = ""
    payment_terms: str = ""
    status: str = "active"      # active | blocked | pending
    contact_email: str = ""


class PurchaseOrder(SQLModel, table=True):
    po_number: str = Field(primary_key=True)
    vendor_id: str = Field(index=True)
    po_date: str = ""
    currency: str = ""
    total: float = 0.0          # net of tax (sum of line qty*unit_price)
    status: str = "open"        # open | partially_billed | closed | cancelled


class POLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    po_number: str = Field(index=True)
    line_no: int = 0
    sku: str = ""
    description: str = ""
    qty: float = 0.0
    unit_price: float = 0.0
    tax_rate: float = 0.0


class GoodsReceipt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    po_number: str = Field(index=True)
    line_no: int = 0
    qty_received: float = 0.0
    received_date: str = ""


class InvoiceRegister(SQLModel, table=True):
    """Written on APPROVE (and referenced for duplicate + cumulative billing checks)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    vendor_id: str = Field(index=True)
    invoice_number_norm: str = Field(index=True)
    invoice_number_raw: str = ""
    po_number: Optional[str] = Field(default=None, index=True)
    invoice_date: str = ""
    currency: str = ""
    subtotal_net: float = 0.0   # net amount billed against the PO
    total_gross: float = 0.0
    file_hash: str = ""
    decision: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Run(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str = ""
    source: str = "upload"      # upload | sample
    sample_id: Optional[str] = None
    file_hash: str = ""
    status: str = "pending"     # pending | running | done | error
    decision: Optional[str] = None
    decision_codes: list = Field(default_factory=list, sa_column=Column(JSON))
    explanation: Optional[str] = None
    vendor_email: Optional[str] = None
    extraction: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    events: list = Field(default_factory=list, sa_column=Column(JSON))
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    duration_ms: Optional[int] = None
    cost_usd: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewAction(SQLModel, table=True):
    """Human override from the Review Queue (audit trail)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    action: str = ""            # approve | reject | request_info
    comment: str = ""
    actor: str = "reviewer"
    created_at: datetime = Field(default_factory=datetime.utcnow)
