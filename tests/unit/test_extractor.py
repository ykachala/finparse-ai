"""Unit tests for DocumentExtractor JSON parsing and multi-page merging."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.extractor.extractor import DocumentExtractor
from src.preprocessor.processor import ProcessedPage


def _make_page(n: int = 1) -> ProcessedPage:
    return ProcessedPage(
        page_number=n,
        image_bytes=b"fake_jpeg",
        base64_data="ZmFrZQ==",
        width=800,
        height=1100,
    )


def _invoice_result() -> dict:
    return {
        "document_type": "invoice",
        "confidence": 0.95,
        "vendor": {"name": "Acme"},
        "document_meta": {"invoice_number": "INV-001", "invoice_date": "2025-01-01"},
        "line_items": [{"description": "Service", "quantity": 1, "unit_price": 100.0, "total": 100.0}],
        "totals": {"subtotal": 100.0, "total": 115.0, "currency": "ZAR"},
        "validation": {"amounts_balance": True, "flags": []},
    }


def _statement_result(transactions: list) -> dict:
    return {
        "document_type": "bank_statement",
        "confidence": 0.95,
        "account_info": {"account_holder": "Test"},
        "transactions": transactions,
        "totals": {},
        "validation": {"amounts_balance": True, "flags": []},
    }


class TestJsonParsing:
    def test_bare_json_parsed(self) -> None:
        mock_client = MagicMock()
        mock_client.extract.return_value = json.dumps(_invoice_result())
        extractor = DocumentExtractor(mock_client)
        result = extractor.extract([_make_page()], "invoice")
        assert result["document_type"] == "invoice"

    def test_markdown_wrapped_json_parsed(self) -> None:
        mock_client = MagicMock()
        raw = "```json\n" + json.dumps(_invoice_result()) + "\n```"
        mock_client.extract.return_value = raw
        extractor = DocumentExtractor(mock_client)
        result = extractor.extract([_make_page()], "invoice")
        assert result["document_type"] == "invoice"

    def test_empty_pages_returns_empty_dict(self) -> None:
        mock_client = MagicMock()
        extractor = DocumentExtractor(mock_client)
        result = extractor.extract([], "invoice")
        assert result == {}


class TestMultiPageMerging:
    def test_bank_statement_transactions_merged_across_pages(self) -> None:
        txn_page1 = [{"date": "2025-01-01", "description": "A", "credit": 100.0}]
        txn_page2 = [{"date": "2025-01-02", "description": "B", "debit": 50.0}]

        mock_client = MagicMock()

        def extract_side_effect(pages, prompt):
            if pages[0].page_number <= 10:
                return json.dumps(_statement_result(txn_page1))
            return json.dumps(_statement_result(txn_page2))

        mock_client.extract.side_effect = extract_side_effect
        extractor = DocumentExtractor(mock_client)

        # Create 11 pages to trigger multi-page path
        pages = [_make_page(i) for i in range(1, 12)]
        result = extractor.extract(pages, "bank_statement")
        assert len(result["transactions"]) == 2

    def test_non_statement_multi_page_returns_first_chunk(self) -> None:
        mock_client = MagicMock()
        mock_client.extract.return_value = json.dumps(_invoice_result())
        extractor = DocumentExtractor(mock_client)

        pages = [_make_page(i) for i in range(1, 12)]
        result = extractor.extract(pages, "invoice")
        assert result["document_type"] == "invoice"
