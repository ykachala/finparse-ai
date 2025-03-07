"""
Document validator: Pydantic schema enforcement + financial cross-check logic.

Validates:
- Schema compliance via Pydantic v2 model_validate
- Invoice: line items sum vs stated subtotal; subtotal + VAT vs total
- Bank statement: running balance reconciliation
- Date normalisation before validation
"""

import copy
import re
from datetime import datetime

from pydantic import ValidationError

from src.validators.schemas import (
    BankStatementDocument,
    InvoiceDocument,
    ParsedDocument,
    PayslipDocument,
    ReceiptDocument,
    ValidationInfo,
)

# Monetary tolerance: 2 cents per line to account for floating-point rounding
_TOLERANCE_PER_LINE = 0.02

# Regex patterns for date detection and parsing
_DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "%Y-%m-%d"),  # Already ISO 8601
    (re.compile(r"^(\d{2})/(\d{2})/(\d{4})$"), "%d/%m/%Y"),
    (re.compile(r"^(\d{2})-(\d{2})-(\d{4})$"), "%d-%m-%Y"),
    (re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$"), "%d.%m.%Y"),
    (re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})$"), "%Y.%m.%d"),
    (re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$"), "%d %B %Y"),
    (re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$"), "%B %d %Y"),
    (re.compile(r"^(\d{2})/(\d{2})/(\d{2})$"), "%d/%m/%y"),
]

_MONTH_ABBREVS: dict[str, str] = {
    "jan": "January", "feb": "February", "mar": "March", "apr": "April",
    "may": "May", "jun": "June", "jul": "July", "aug": "August",
    "sep": "September", "oct": "October", "nov": "November", "dec": "December",
}

_CURRENCY_SYMBOLS: dict[str, str] = {
    "R": "ZAR", "ZAR": "ZAR",
    "$": "USD", "USD": "USD",
    "£": "GBP", "GBP": "GBP",
    "€": "EUR", "EUR": "EUR",
}


class DocumentValidator:
    """
    Validates raw extraction output against Pydantic schemas and financial rules.

    Usage:
        validator = DocumentValidator()
        doc, flags = validator.validate(raw_data)
    """

    TOLERANCE: float = _TOLERANCE_PER_LINE

    def validate(self, raw_data: dict) -> tuple[ParsedDocument, list[str]]:
        """
        Validate raw extraction dict and return (parsed_doc, flags).

        Args:
            raw_data: Raw dict from Claude extraction.

        Returns:
            Tuple of (parsed document, list of validation flag strings).
            The ValidationInfo inside the document reflects the flags.

        Raises:
            pydantic.ValidationError: If the data cannot be validated against any schema.
        """
        # Deep copy so we don't mutate the caller's dict
        data = copy.deepcopy(raw_data)
        data = self._normalize_dates(data)

        doc_type = data.get("document_type", "invoice")
        flags: list[str] = []

        if doc_type == "invoice":
            # Add placeholder validation before Pydantic parse
            if "validation" not in data:
                data["validation"] = {"amounts_balance": True, "flags": []}
            doc = InvoiceDocument.model_validate(data)
            flags.extend(self._validate_invoice_amounts(doc))

        elif doc_type == "bank_statement":
            if "validation" not in data:
                data["validation"] = {"amounts_balance": True, "flags": []}
            doc = BankStatementDocument.model_validate(data)
            flags.extend(self._validate_statement_balances(doc))

        elif doc_type == "receipt":
            if "validation" not in data:
                data["validation"] = {"amounts_balance": True, "flags": []}
            doc = ReceiptDocument.model_validate(data)
            flags.extend(self._validate_receipt_amounts(doc))

        elif doc_type == "payslip":
            if "validation" not in data:
                data["validation"] = {"amounts_balance": True, "flags": []}
            doc = PayslipDocument.model_validate(data)
            flags.extend(self._validate_payslip_amounts(doc))

        else:
            # Try invoice as fallback
            if "validation" not in data:
                data["validation"] = {"amounts_balance": True, "flags": []}
            doc = InvoiceDocument.model_validate(data)

        # Update validation flags on the document
        amounts_balance = len([f for f in flags if "mismatch" in f or "balance" in f.lower()]) == 0
        updated_validation = ValidationInfo(
            amounts_balance=amounts_balance,
            vat_calculation_correct=None,
            flags=flags,
        )

        if isinstance(doc, InvoiceDocument):
            return doc.model_copy(update={"validation": updated_validation}), flags
        elif isinstance(doc, BankStatementDocument):
            return doc.model_copy(update={"validation": updated_validation}), flags
        elif isinstance(doc, ReceiptDocument):
            return doc.model_copy(update={"validation": updated_validation}), flags
        elif isinstance(doc, PayslipDocument):
            return doc.model_copy(update={"validation": updated_validation}), flags

        return doc, flags  # type: ignore[return-value]

    def _validate_invoice_amounts(self, doc: InvoiceDocument) -> list[str]:
        """
        Cross-check line items against stated totals.

        Flags:
        - line_items_subtotal_mismatch: sum(line_items.total) != totals.subtotal
        - total_mismatch: subtotal + vat != total
        """
        flags: list[str] = []
        tolerance = self.TOLERANCE * max(len(doc.line_items), 1)

        line_total = sum(item.total for item in doc.line_items)
        if abs(line_total - doc.totals.subtotal) > tolerance:
            flags.append(
                f"line_items_subtotal_mismatch: computed={line_total:.2f}, "
                f"stated={doc.totals.subtotal:.2f}"
            )

        if doc.totals.vat is not None:
            expected_total = doc.totals.subtotal + doc.totals.vat
            if abs(expected_total - doc.totals.total) > self.TOLERANCE:
                flags.append(
                    f"total_mismatch: subtotal+vat={expected_total:.2f}, "
                    f"stated={doc.totals.total:.2f}"
                )

        return flags

    def _validate_receipt_amounts(self, doc: ReceiptDocument) -> list[str]:
        """Validate receipt item amounts against stated total."""
        flags: list[str] = []
        if not doc.items:
            return flags

        item_total = sum(
            float(item.get("amount", 0)) for item in doc.items if isinstance(item, dict)
        )
        tolerance = self.TOLERANCE * max(len(doc.items), 1)

        if doc.totals.subtotal is not None:
            if abs(item_total - doc.totals.subtotal) > tolerance:
                flags.append(
                    f"items_subtotal_mismatch: computed={item_total:.2f}, "
                    f"stated={doc.totals.subtotal:.2f}"
                )

        return flags

    def _validate_payslip_amounts(self, doc: PayslipDocument) -> list[str]:
        """Validate gross_pay - total_deductions == net_pay."""
        flags: list[str] = []

        computed_net = doc.gross_pay - doc.total_deductions
        if abs(computed_net - doc.net_pay) > self.TOLERANCE:
            flags.append(
                f"net_pay_mismatch: gross-deductions={computed_net:.2f}, "
                f"stated_net={doc.net_pay:.2f}"
            )

        return flags

    def _validate_statement_balances(self, doc: BankStatementDocument) -> list[str]:
        """
        Verify running balance continuity across transactions.

        For each transaction where balance is provided, checks:
        prev_balance +/- credit/debit == current_balance (within TOLERANCE).
        """
        flags: list[str] = []
        transactions = doc.transactions

        for i in range(1, len(transactions)):
            prev = transactions[i - 1]
            curr = transactions[i]

            if prev.balance is None or curr.balance is None:
                continue

            movement = (curr.credit or 0.0) - (curr.debit or 0.0)
            expected = prev.balance + movement
            if abs(expected - curr.balance) > self.TOLERANCE:
                flags.append(
                    f"balance_discontinuity at tx[{i}] "
                    f"(date={curr.date}): expected={expected:.2f}, "
                    f"stated={curr.balance:.2f}"
                )

        return flags

    def _normalize_dates(self, data: object) -> dict:
        """
        Recursively walk a dict/list structure and normalise date-like strings to ISO 8601.

        Recognised date fields (by key name): any key ending in _date, date, period_start,
        period_end, valid_until, payment_date, invoice_date, due_date, statement_period_*.

        Returns the mutated copy.
        """
        if isinstance(data, dict):
            return {k: self._normalize_value(k, v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._normalize_dates(item) for item in data]  # type: ignore[return-value]
        return data  # type: ignore[return-value]

    def _normalize_value(self, key: str, value: object) -> object:
        """Normalise a single value if the key suggests it is a date field."""
        date_key_signals = (
            "date", "period_start", "period_end", "valid_until",
            "payment_date", "invoice_date", "due_date",
        )
        if isinstance(value, str) and any(sig in key.lower() for sig in date_key_signals):
            return self._parse_date(value) or value
        if isinstance(value, dict):
            return self._normalize_dates(value)
        if isinstance(value, list):
            return [self._normalize_dates(item) if isinstance(item, dict) else item for item in value]
        return value

    def _parse_date(self, raw: str) -> str | None:
        """
        Attempt to parse a date string into ISO 8601 format (YYYY-MM-DD).

        Args:
            raw: Input date string in any supported format.

        Returns:
            ISO 8601 string, or None if parsing fails.
        """
        raw = raw.strip()

        # Expand month abbreviations to full names for strptime compatibility
        for abbrev, full in _MONTH_ABBREVS.items():
            if abbrev in raw.lower():
                raw = re.sub(re.escape(abbrev), full, raw, flags=re.IGNORECASE)
                break

        for _pattern, fmt in _DATE_PATTERNS:
            try:
                parsed = datetime.strptime(raw, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    def _detect_currency(self, text: str) -> str:
        """
        Detect currency from a text string containing symbols or codes.

        Args:
            text: Any string that may contain a currency indicator.

        Returns:
            3-letter ISO currency code (defaults to "ZAR" if not detected).
        """
        for symbol, code in _CURRENCY_SYMBOLS.items():
            if symbol in text:
                return code
        return "ZAR"
