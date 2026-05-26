"""
Extraction orchestrator: coordinates multi-page aggregation and prompt routing.

Flow:
  pages + document_hint → select prompt → ClaudeVisionClient.extract() → parse JSON
  multi-page bank statements → extract per page → merge transaction lists
"""

import json
import logging
from typing import Any

from src.extractor.claude_client import ClaudeVisionClient
from src.extractor.prompts import (
    get_auto_detect_prompt,
    get_bank_statement_prompt,
    get_invoice_prompt,
    get_payslip_prompt,
    get_receipt_prompt,
)
from src.preprocessor.processor import ProcessedPage

logger = logging.getLogger(__name__)

PROMPT_MAP: dict[str, Any] = {
    "invoice": get_invoice_prompt,
    "receipt": get_receipt_prompt,
    "bank_statement": get_bank_statement_prompt,
    "payslip": get_payslip_prompt,
}

# Number of pages to send in a single Claude request (context window limit)
MAX_PAGES_PER_REQUEST: int = 10


class DocumentExtractor:
    """
    Orchestrates document extraction:
    - Routes to type-specific prompt based on document_hint
    - Auto-detects document type when hint is absent
    - Handles multi-page documents via chunked extraction and result merging
    """

    def __init__(self, client: ClaudeVisionClient) -> None:
        self._client = client

    def extract(self, pages: list[ProcessedPage], document_hint: str | None) -> dict:
        """
        Extract structured data from document pages.

        Args:
            pages: Ordered list of preprocessed document pages.
            document_hint: Optional document type hint from the API caller.
                           One of: invoice, receipt, bank_statement, payslip.
                           When None, auto-detection is used.

        Returns:
            Raw extracted dict (before Pydantic validation).
        """
        if not pages:
            return {}

        # Auto-detect document type if no hint provided
        effective_hint = document_hint
        if effective_hint is None:
            effective_hint = self._detect_document_type(pages[:2])

        prompt_fn = PROMPT_MAP.get(effective_hint, get_auto_detect_prompt)
        prompt = prompt_fn()

        # Single-batch extraction for short documents
        if len(pages) <= MAX_PAGES_PER_REQUEST:
            raw = self._client.extract(pages, prompt)
            return self._parse_json_response(raw)

        # Multi-page: extract in chunks and merge
        return self._extract_multi_page(pages, effective_hint, prompt)

    def _detect_document_type(self, sample_pages: list[ProcessedPage]) -> str:
        """
        Use the auto-detect prompt to determine the document type.

        Args:
            sample_pages: A small sample of pages (typically the first 1-2).

        Returns:
            Detected document type string (invoice/receipt/bank_statement/payslip).
        """
        auto_prompt = get_auto_detect_prompt()
        raw = self._client.extract(sample_pages, auto_prompt)
        try:
            data = self._parse_json_response(raw)
            detected = data.get("document_type", "invoice")
            if detected in PROMPT_MAP:
                return detected
        except (json.JSONDecodeError, ValueError):
            pass
        # Fall back to invoice if detection fails
        return "invoice"

    def _extract_multi_page(
        self,
        pages: list[ProcessedPage],
        doc_type: str,
        prompt: str,
    ) -> dict:
        """
        Extract data from a document with more pages than MAX_PAGES_PER_REQUEST.

        Strategy:
        - Chunk pages into batches of MAX_PAGES_PER_REQUEST
        - Extract each batch independently
        - Merge: for bank statements, concatenate transactions list
        - For other types: use the first batch result (title page carries the data)
        """
        results: list[dict] = []

        for i in range(0, len(pages), MAX_PAGES_PER_REQUEST):
            chunk = pages[i : i + MAX_PAGES_PER_REQUEST]
            raw = self._client.extract(chunk, prompt)
            try:
                parsed = self._parse_json_response(raw)
                results.append(parsed)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Failed to parse chunk %d: %s", i // MAX_PAGES_PER_REQUEST, exc)

        if not results:
            return {}

        if doc_type == "bank_statement":
            return self._merge_bank_statement_results(results)

        # For invoices/receipts/payslips: first chunk has the header info
        return results[0]

    def _merge_bank_statement_results(self, results: list[dict]) -> dict:
        """
        Merge multiple bank statement extraction results into one.

        Concatenates the transactions list across all chunks.
        Uses the first result for account_info and totals (most likely to be complete).
        """
        if not results:
            return {}

        merged = dict(results[0])
        all_transactions: list[dict] = list(merged.get("transactions", []))

        for subsequent in results[1:]:
            transactions = subsequent.get("transactions", [])
            if isinstance(transactions, list):
                all_transactions.extend(transactions)

        merged["transactions"] = all_transactions
        return merged

    def _parse_json_response(self, raw: str) -> dict:
        """
        Extract a JSON object from Claude's raw text response.

        Handles:
        - Bare JSON strings
        - Responses wrapped in markdown code blocks (```json ... ```)
        - Leading/trailing whitespace

        Args:
            raw: Raw text response from Claude.

        Returns:
            Parsed dict.

        Raises:
            json.JSONDecodeError: If the response cannot be parsed as JSON.
        """
        text = raw.strip()

        # Strip markdown code block wrappers
        if text.startswith("```"):
            lines = text.split("\n")
            # Skip the first line (```json or ```) and last line (```)
            inner_lines = lines[1:]
            if inner_lines and inner_lines[-1].strip() == "```":
                inner_lines = inner_lines[:-1]
            text = "\n".join(inner_lines).strip()

        return json.loads(text)
