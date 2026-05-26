"""
Pydantic v2 output schemas for all supported financial document types.

These schemas enforce structure on Claude's raw JSON extraction before
it is stored in PostgreSQL or returned to the caller.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class BankDetails(BaseModel):
    """Vendor banking details for payment processing."""

    bank: str | None = None
    account_number: str | None = None
    branch_code: str | None = None


class VendorInfo(BaseModel):
    """Invoice vendor (seller) information."""

    name: str
    registration_number: str | None = None
    vat_number: str | None = None
    address: str | None = None
    bank_details: BankDetails | None = None


class InvoiceMeta(BaseModel):
    """Invoice document metadata."""

    invoice_number: str
    invoice_date: str  # ISO 8601
    due_date: str | None = None
    payment_terms: str | None = None


class LineItem(BaseModel):
    """A single line item on an invoice."""

    description: str
    quantity: float
    unit_price: float
    vat_rate: float | None = None
    vat_amount: float | None = None
    total: float


class Totals(BaseModel):
    """Document monetary totals."""

    subtotal: float
    vat: float | None = None
    total: float
    currency: str = "ZAR"


class ValidationInfo(BaseModel):
    """Cross-check results for financial amounts."""

    amounts_balance: bool
    vat_calculation_correct: bool | None = None
    flags: list[str]


class InvoiceDocument(BaseModel):
    """Fully validated invoice extraction result."""

    document_type: Literal["invoice"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    vendor: VendorInfo
    document_meta: InvoiceMeta
    line_items: list[LineItem]
    totals: Totals
    validation: ValidationInfo


# ---------------------------------------------------------------------------
# Bank statement
# ---------------------------------------------------------------------------

VALID_CATEGORIES: frozenset[str] = frozenset(
    {"salary", "rent", "utilities", "transfer", "fees", "shopping", "other"}
)


class Transaction(BaseModel):
    """A single bank statement transaction."""

    date: str  # ISO 8601
    description: str
    debit: float | None = None
    credit: float | None = None
    balance: float | None = None
    category: str | None = None  # salary, rent, utilities, transfer, fees, other


class AccountInfo(BaseModel):
    """Bank account information from a statement header."""

    account_holder: str | None = None
    account_number: str | None = None
    bank: str | None = None
    statement_period_start: str | None = None
    statement_period_end: str | None = None


class BankStatementDocument(BaseModel):
    """Fully validated bank statement extraction result."""

    document_type: Literal["bank_statement"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    account_info: AccountInfo
    transactions: list[Transaction]
    totals: dict  # opening_balance, closing_balance, total_debits, total_credits
    validation: ValidationInfo


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------


class ReceiptDocument(BaseModel):
    """Fully validated receipt extraction result."""

    document_type: Literal["receipt"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    merchant: str
    date: str | None = None
    items: list[dict]  # description, amount
    totals: Totals
    payment_method: str | None = None
    validation: ValidationInfo


# ---------------------------------------------------------------------------
# Payslip
# ---------------------------------------------------------------------------


class EmployerInfo(BaseModel):
    """Payslip employer information."""

    name: str
    registration_number: str | None = None


class EmployeeInfo(BaseModel):
    """Payslip employee information."""

    name: str
    employee_number: str | None = None
    id_number: str | None = None
    position: str | None = None
    department: str | None = None


class PayPeriod(BaseModel):
    """Payslip pay period dates."""

    start_date: str | None = None
    end_date: str | None = None
    payment_date: str | None = None


class EarningLine(BaseModel):
    """A single earning line on a payslip."""

    description: str
    amount: float


class DeductionLine(BaseModel):
    """A single deduction line on a payslip."""

    description: str
    amount: float


class PayslipDocument(BaseModel):
    """Fully validated payslip extraction result."""

    document_type: Literal["payslip"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    employer: EmployerInfo
    employee: EmployeeInfo
    pay_period: PayPeriod
    earnings: list[EarningLine]
    deductions: list[DeductionLine]
    gross_pay: float
    total_deductions: float
    net_pay: float
    currency: str = "ZAR"
    validation: ValidationInfo


# ---------------------------------------------------------------------------
# Union type for all supported document types
# ---------------------------------------------------------------------------

ParsedDocument = InvoiceDocument | BankStatementDocument | ReceiptDocument | PayslipDocument
