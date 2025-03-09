"""Unit tests for DocumentValidator financial cross-check logic."""

import pytest

from src.validators.schemas import (
    InvoiceDocument,
    BankStatementDocument,
    PayslipDocument,
)
from src.validators.validator import DocumentValidator


def _invoice_payload(line_total: float, subtotal: float, vat: float, total: float) -> dict:
    return {
        "document_type": "invoice",
        "confidence": 0.95,
        "vendor": {"name": "Test Vendor"},
        "document_meta": {"invoice_number": "INV-001", "invoice_date": "2025-01-15"},
        "line_items": [
            {"description": "Service", "quantity": 1, "unit_price": line_total, "total": line_total}
        ],
        "totals": {"subtotal": subtotal, "vat": vat, "total": total, "currency": "ZAR"},
        "validation": {"amounts_balance": True, "flags": []},
    }


def _bank_statement_payload(transactions: list[dict]) -> dict:
    return {
        "document_type": "bank_statement",
        "confidence": 0.95,
        "account_info": {"account_holder": "Test User"},
        "transactions": transactions,
        "totals": {"opening_balance": 1000.0, "closing_balance": 900.0},
        "validation": {"amounts_balance": True, "flags": []},
    }


validator = DocumentValidator()


class TestInvoiceValidation:
    def test_balanced_invoice_has_no_flags(self) -> None:
        payload = _invoice_payload(line_total=45000.0, subtotal=45000.0, vat=6750.0, total=51750.0)
        doc, flags = validator.validate(payload)
        assert isinstance(doc, InvoiceDocument)
        assert flags == []

    def test_line_items_subtotal_mismatch_is_flagged(self) -> None:
        payload = _invoice_payload(line_total=45000.0, subtotal=50000.0, vat=7500.0, total=57500.0)
        doc, flags = validator.validate(payload)
        assert any("line_items_subtotal_mismatch" in f for f in flags)

    def test_total_mismatch_is_flagged(self) -> None:
        payload = _invoice_payload(line_total=45000.0, subtotal=45000.0, vat=6750.0, total=60000.0)
        doc, flags = validator.validate(payload)
        assert any("total_mismatch" in f for f in flags)

    def test_balanced_amounts_returns_amounts_balance_true(self) -> None:
        payload = _invoice_payload(line_total=100.0, subtotal=100.0, vat=15.0, total=115.0)
        doc, flags = validator.validate(payload)
        assert doc.validation.amounts_balance is True

    def test_amounts_balance_false_when_mismatch(self) -> None:
        payload = _invoice_payload(line_total=100.0, subtotal=200.0, vat=30.0, total=230.0)
        doc, flags = validator.validate(payload)
        assert doc.validation.amounts_balance is False


class TestDateNormalisation:
    def test_dd_mm_yyyy_slash_normalised(self) -> None:
        payload = _invoice_payload(100.0, 100.0, 15.0, 115.0)
        payload["document_meta"]["invoice_date"] = "15/01/2025"
        doc, _ = validator.validate(payload)
        assert isinstance(doc, InvoiceDocument)
        assert doc.document_meta.invoice_date == "2025-01-15"

    def test_iso_date_left_unchanged(self) -> None:
        payload = _invoice_payload(100.0, 100.0, 15.0, 115.0)
        payload["document_meta"]["invoice_date"] = "2025-01-15"
        doc, _ = validator.validate(payload)
        assert doc.document_meta.invoice_date == "2025-01-15"

    def test_written_month_normalised(self) -> None:
        payload = _invoice_payload(100.0, 100.0, 15.0, 115.0)
        payload["document_meta"]["invoice_date"] = "15 January 2025"
        doc, _ = validator.validate(payload)
        assert doc.document_meta.invoice_date == "2025-01-15"


class TestBankStatementValidation:
    def test_continuous_balance_has_no_flags(self) -> None:
        txns = [
            {"date": "2025-01-01", "description": "Opening", "credit": 1000.0, "balance": 1000.0},
            {"date": "2025-01-02", "description": "Debit", "debit": 200.0, "balance": 800.0},
            {"date": "2025-01-03", "description": "Credit", "credit": 500.0, "balance": 1300.0},
        ]
        payload = _bank_statement_payload(txns)
        doc, flags = validator.validate(payload)
        assert isinstance(doc, BankStatementDocument)
        assert flags == []

    def test_balance_discontinuity_is_flagged(self) -> None:
        txns = [
            {"date": "2025-01-01", "description": "Opening", "credit": 1000.0, "balance": 1000.0},
            # Balance should be 800.0 after 200.0 debit, but stated as 900.0
            {"date": "2025-01-02", "description": "Debit", "debit": 200.0, "balance": 900.0},
        ]
        payload = _bank_statement_payload(txns)
        doc, flags = validator.validate(payload)
        assert any("balance_discontinuity" in f for f in flags)


class TestPayslipValidation:
    def test_balanced_payslip_has_no_flags(self) -> None:
        payload = {
            "document_type": "payslip",
            "confidence": 0.95,
            "employer": {"name": "Acme Corp"},
            "employee": {"name": "John Doe"},
            "pay_period": {"payment_date": "2025-01-31"},
            "earnings": [{"description": "Basic Salary", "amount": 50000.0}],
            "deductions": [{"description": "PAYE", "amount": 10000.0}],
            "gross_pay": 50000.0,
            "total_deductions": 10000.0,
            "net_pay": 40000.0,
            "currency": "ZAR",
            "validation": {"amounts_balance": True, "flags": []},
        }
        doc, flags = validator.validate(payload)
        assert isinstance(doc, PayslipDocument)
        assert flags == []

    def test_net_pay_mismatch_is_flagged(self) -> None:
        payload = {
            "document_type": "payslip",
            "confidence": 0.95,
            "employer": {"name": "Acme Corp"},
            "employee": {"name": "John Doe"},
            "pay_period": {"payment_date": "2025-01-31"},
            "earnings": [{"description": "Basic Salary", "amount": 50000.0}],
            "deductions": [{"description": "PAYE", "amount": 10000.0}],
            "gross_pay": 50000.0,
            "total_deductions": 10000.0,
            "net_pay": 45000.0,  # should be 40000.0
            "currency": "ZAR",
            "validation": {"amounts_balance": True, "flags": []},
        }
        doc, flags = validator.validate(payload)
        assert any("net_pay_mismatch" in f for f in flags)
