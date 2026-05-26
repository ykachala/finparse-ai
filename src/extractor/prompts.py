"""
Extraction prompt templates for each supported document type.

Each prompt instructs Claude to return ONLY valid JSON matching the described schema,
with no preamble, explanation, or markdown outside the JSON block.
"""


def get_invoice_prompt() -> str:
    """
    Return the extraction prompt for invoice documents.

    Schema: vendor, document_meta, line_items[], totals, document_type, confidence
    """
    return """You are a financial document extraction system. Analyse the invoice image(s) and extract ALL data.

Return ONLY a valid JSON object — no explanation, no markdown outside the JSON block. If a field is not visible or legible, use null.

Required JSON schema:
{
  "document_type": "invoice",
  "confidence": <float 0.0-1.0 reflecting overall extraction certainty>,
  "vendor": {
    "name": "<company name>",
    "registration_number": "<company registration number or null>",
    "vat_number": "<VAT/tax number or null>",
    "address": "<full address string or null>",
    "bank_details": {
      "bank": "<bank name or null>",
      "account_number": "<account number or null>",
      "branch_code": "<branch/sort code or null>"
    }
  },
  "document_meta": {
    "invoice_number": "<invoice number — e.g. INV-2026-00421>",
    "invoice_date": "<ISO 8601 date — YYYY-MM-DD>",
    "due_date": "<ISO 8601 date or null>",
    "payment_terms": "<e.g. '30 days', 'COD', or null>"
  },
  "line_items": [
    {
      "description": "<item or service description>",
      "quantity": <number>,
      "unit_price": <number>,
      "vat_rate": <decimal e.g. 0.15 for 15% or null>,
      "vat_amount": <number or null>,
      "total": <number — quantity * unit_price + vat_amount>
    }
  ],
  "totals": {
    "subtotal": <sum of line items before VAT>,
    "vat": <total VAT amount or null>,
    "total": <final payable amount>,
    "currency": "<3-letter ISO code, e.g. ZAR, USD, GBP, EUR>"
  }
}

Extract every line item. Do not summarise or merge items. Amounts must be numeric (no currency symbols).
"""


def get_receipt_prompt() -> str:
    """
    Return the extraction prompt for receipt documents.

    Schema: merchant, date, items[], totals, payment_method, document_type, confidence
    """
    return """You are a financial document extraction system. Analyse the receipt image and extract ALL data.

Return ONLY a valid JSON object — no explanation, no markdown outside the JSON block.

Required JSON schema:
{
  "document_type": "receipt",
  "confidence": <float 0.0-1.0>,
  "merchant": "<merchant/store name>",
  "date": "<ISO 8601 date YYYY-MM-DD or null>",
  "items": [
    {
      "description": "<item name>",
      "quantity": <number or 1 if not shown>,
      "amount": <line total as number>
    }
  ],
  "totals": {
    "subtotal": <subtotal before tax or null>,
    "vat": <tax amount or null>,
    "total": <final total paid>,
    "currency": "<3-letter ISO code>"
  },
  "payment_method": "<cash | card | eft | unknown or null>"
}

Amounts must be numeric. Extract every item line.
"""


def get_bank_statement_prompt() -> str:
    """
    Return the extraction prompt for bank statement documents.

    Schema: account_info, transactions[], totals, document_type, confidence
    """
    return """You are a financial document extraction system. Analyse the bank statement image(s) and extract ALL data.

Return ONLY a valid JSON object — no explanation, no markdown outside the JSON block.

Required JSON schema:
{
  "document_type": "bank_statement",
  "confidence": <float 0.0-1.0>,
  "account_info": {
    "account_holder": "<name or null>",
    "account_number": "<account number, may be masked — e.g. ****1234 — or null>",
    "bank": "<bank name or null>",
    "statement_period_start": "<ISO 8601 date YYYY-MM-DD or null>",
    "statement_period_end": "<ISO 8601 date YYYY-MM-DD or null>"
  },
  "transactions": [
    {
      "date": "<ISO 8601 date YYYY-MM-DD>",
      "description": "<transaction description>",
      "debit": <amount as positive number or null if credit>,
      "credit": <amount as positive number or null if debit>,
      "balance": <running balance after transaction or null>,
      "category": "<salary | rent | utilities | transfer | fees | shopping | other>"
    }
  ],
  "totals": {
    "opening_balance": <opening balance or null>,
    "closing_balance": <closing balance or null>,
    "total_debits": <sum of all debits or null>,
    "total_credits": <sum of all credits or null>
  }
}

Extract EVERY transaction visible. Amounts must be positive numbers (debit/credit field indicates direction).
Auto-categorise each transaction based on description keywords:
- salary/payroll/remuneration → "salary"
- rent/lease/property → "rent"
- electricity/water/internet/municipal → "utilities"
- transfer/payment/eft/debit order → "transfer"
- bank charges/fee/service charge → "fees"
- all other transactions → "other"
"""


def get_payslip_prompt() -> str:
    """
    Return the extraction prompt for payslip documents.

    Schema: employer, employee, pay_period, gross_pay, deductions[], net_pay, document_type, confidence
    """
    return """You are a financial document extraction system. Analyse the payslip image and extract ALL data.

Return ONLY a valid JSON object — no explanation, no markdown outside the JSON block.

Required JSON schema:
{
  "document_type": "payslip",
  "confidence": <float 0.0-1.0>,
  "employer": {
    "name": "<employer company name>",
    "registration_number": "<registration number or null>"
  },
  "employee": {
    "name": "<employee full name>",
    "employee_number": "<employee ID or null>",
    "id_number": "<national ID number or null>",
    "position": "<job title or null>",
    "department": "<department or null>"
  },
  "pay_period": {
    "start_date": "<ISO 8601 date YYYY-MM-DD or null>",
    "end_date": "<ISO 8601 date YYYY-MM-DD or null>",
    "payment_date": "<ISO 8601 date YYYY-MM-DD or null>"
  },
  "earnings": [
    {
      "description": "<e.g. Basic Salary, Overtime, Commission>",
      "amount": <number>
    }
  ],
  "deductions": [
    {
      "description": "<e.g. PAYE, UIF, Medical Aid, Pension>",
      "amount": <positive number>
    }
  ],
  "gross_pay": <total before deductions>,
  "total_deductions": <sum of all deductions>,
  "net_pay": <gross_pay - total_deductions>,
  "currency": "<3-letter ISO code>"
}

Extract all earnings and deduction line items. Amounts must be numeric.
"""


def get_quote_prompt() -> str:
    """
    Return the extraction prompt for quote/estimate documents.

    Schema: vendor, document_meta, line_items[], totals, document_type, confidence
    Similar structure to invoices but document_type is 'quote'.
    """
    return """You are a financial document extraction system. Analyse the quote/estimate image and extract ALL data.

Return ONLY a valid JSON object — no explanation, no markdown outside the JSON block.

Required JSON schema:
{
  "document_type": "quote",
  "confidence": <float 0.0-1.0>,
  "vendor": {
    "name": "<company name>",
    "registration_number": "<registration number or null>",
    "vat_number": "<VAT number or null>",
    "address": "<full address or null>",
    "bank_details": {"bank": null, "account_number": null, "branch_code": null}
  },
  "document_meta": {
    "quote_number": "<quote number>",
    "quote_date": "<ISO 8601 date YYYY-MM-DD>",
    "valid_until": "<ISO 8601 date or null>",
    "payment_terms": "<e.g. '50% deposit' or null>"
  },
  "line_items": [
    {
      "description": "<description>",
      "quantity": <number>,
      "unit_price": <number>,
      "vat_rate": <decimal or null>,
      "vat_amount": <number or null>,
      "total": <number>
    }
  ],
  "totals": {
    "subtotal": <subtotal>,
    "vat": <VAT total or null>,
    "total": <grand total>,
    "currency": "<3-letter ISO code>"
  }
}

Extract every line item. Amounts must be numeric.
"""


def get_auto_detect_prompt() -> str:
    """
    Return the prompt used when document_hint is None.

    Claude first detects the document type, then returns full structured extraction.
    This avoids a two-round-trip approach for most documents.
    """
    return """You are a financial document extraction system. First identify the document type, then extract ALL structured data.

Supported document types: invoice, receipt, bank_statement, payslip

Return ONLY a valid JSON object — no explanation, no markdown outside the JSON block.

Step 1: Identify the document_type from the image.
Step 2: Extract all fields appropriate to that type using these schemas:

For invoice:
{
  "document_type": "invoice",
  "confidence": <float 0.0-1.0>,
  "vendor": {"name": "...", "registration_number": null, "vat_number": null, "address": null, "bank_details": {"bank": null, "account_number": null, "branch_code": null}},
  "document_meta": {"invoice_number": "...", "invoice_date": "YYYY-MM-DD", "due_date": null, "payment_terms": null},
  "line_items": [{"description": "...", "quantity": 1, "unit_price": 0.0, "vat_rate": null, "vat_amount": null, "total": 0.0}],
  "totals": {"subtotal": 0.0, "vat": null, "total": 0.0, "currency": "ZAR"}
}

For receipt:
{
  "document_type": "receipt",
  "confidence": <float>,
  "merchant": "...", "date": "YYYY-MM-DD",
  "items": [{"description": "...", "quantity": 1, "amount": 0.0}],
  "totals": {"subtotal": null, "vat": null, "total": 0.0, "currency": "ZAR"},
  "payment_method": null
}

For bank_statement:
{
  "document_type": "bank_statement",
  "confidence": <float>,
  "account_info": {"account_holder": null, "account_number": null, "bank": null, "statement_period_start": null, "statement_period_end": null},
  "transactions": [{"date": "YYYY-MM-DD", "description": "...", "debit": null, "credit": null, "balance": null, "category": "other"}],
  "totals": {"opening_balance": null, "closing_balance": null, "total_debits": null, "total_credits": null}
}

For payslip:
{
  "document_type": "payslip",
  "confidence": <float>,
  "employer": {"name": "...", "registration_number": null},
  "employee": {"name": "...", "employee_number": null, "id_number": null, "position": null, "department": null},
  "pay_period": {"start_date": null, "end_date": null, "payment_date": null},
  "earnings": [{"description": "...", "amount": 0.0}],
  "deductions": [{"description": "...", "amount": 0.0}],
  "gross_pay": 0.0, "total_deductions": 0.0, "net_pay": 0.0, "currency": "ZAR"
}

Choose the schema matching the document and populate every visible field. Return ONLY the JSON object.
"""
