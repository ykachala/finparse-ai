#!/usr/bin/env python3
"""
Accuracy evaluation harness for finparse-ai.

Compares extracted fields against ground-truth annotations for a corpus of
annotated financial documents and reports per-type accuracy metrics.

Usage:
    python scripts/evaluate.py --corpus /path/to/annotated-corpus
    python scripts/evaluate.py --corpus /path/to/annotated-corpus --output results.json

Corpus directory structure:
    corpus/
        invoices/
            clean/
                doc_001/
                    input.pdf          # original document (or .jpg / .png)
                    expected.json      # ground-truth extraction (same schema as API output)
            scanned/
                doc_042/
                    input.jpg
                    expected.json
        statements/
            doc_101/
                input.pdf
                expected.json
        receipts/
            ...

The corpus used to produce the accuracy figures in the README is not checked into
this repository (contains confidential client documents from South African fintech
integrations). A representative public sample lives in tests/fixtures/. Contact
the author for access to the anonymised evaluation set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Field weights by document type
# Higher weight = more impact on the overall accuracy score.
# Reflects what financial backends actually care about.
# ---------------------------------------------------------------------------

FIELD_WEIGHTS: dict[str, dict[str, float]] = {
    "invoice": {
        "vendor.name": 2.0,
        "vendor.vat_number": 1.5,
        "vendor.bank_details.account_number": 2.0,
        "document_meta.invoice_number": 2.0,
        "document_meta.invoice_date": 2.0,
        "document_meta.due_date": 1.5,
        "totals.subtotal": 2.0,
        "totals.vat": 2.0,
        "totals.total": 3.0,
        "line_items": 3.0,
    },
    "bank_statement": {
        "account.account_number": 2.0,
        "statement_period.from": 1.5,
        "statement_period.to": 1.5,
        "opening_balance": 2.5,
        "closing_balance": 2.5,
        "transactions": 4.0,
    },
    "receipt": {
        "merchant.name": 2.0,
        "document_meta.transaction_date": 2.0,
        "totals.total": 3.0,
        "line_items": 2.0,
    },
    "payslip": {
        "employee.name": 2.0,
        "employee.id_number": 1.5,
        "pay_period": 1.5,
        "gross_pay": 2.0,
        "net_pay": 3.0,
        "deductions": 2.0,
    },
}

AMOUNT_TOLERANCE = 0.50  # ZAR — acceptable rounding difference on amounts


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


@dataclass
class FieldResult:
    total: int = 0
    correct: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0


@dataclass
class DocTypeResult:
    name: str
    field_accuracy: FieldResult = field(default_factory=FieldResult)
    amount_validation_passed: int = 0
    amount_validation_total: int = 0
    doc_count: int = 0
    failed: int = 0

    @property
    def amount_pass_rate(self) -> float:
        if self.amount_validation_total == 0:
            return 0.0
        return self.amount_validation_passed / self.amount_validation_total


def _get_nested(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def _compare_field(extracted: Any, expected: Any, key: str) -> bool:
    if key in ("line_items", "transactions"):
        if not isinstance(extracted, list) or not isinstance(expected, list):
            return False
        if len(extracted) != len(expected):
            return False
        for ext_item, exp_item in zip(extracted, expected):
            for k, v in exp_item.items():
                if isinstance(v, (int, float)):
                    ext_v = ext_item.get(k)
                    if ext_v is None or abs(float(ext_v) - float(v)) > AMOUNT_TOLERANCE:
                        return False
        return True

    if isinstance(expected, (int, float)) and isinstance(extracted, (int, float)):
        return abs(float(extracted) - float(expected)) <= AMOUNT_TOLERANCE

    if isinstance(expected, str) and isinstance(extracted, str):
        return expected.strip().lower() == extracted.strip().lower()

    return extracted == expected


def _score_document(extracted: dict, expected: dict, doc_type: str) -> tuple[int, int]:
    weights = FIELD_WEIGHTS.get(doc_type, {})
    total_weight = 0.0
    correct_weight = 0.0

    for field_path, weight in weights.items():
        ext_val = _get_nested(extracted, field_path)
        exp_val = _get_nested(expected, field_path)
        total_weight += weight
        if _compare_field(ext_val, exp_val, field_path.split(".")[-1]):
            correct_weight += weight

    return int(correct_weight * 1000), int(total_weight * 1000)


# ---------------------------------------------------------------------------
# Extraction runner
# ---------------------------------------------------------------------------


async def _run_extraction(input_path: Path) -> dict:
    from src.preprocessor.processor import preprocess_document
    from src.extractor.extractor import extract_document

    pages = await preprocess_document(str(input_path))
    return await extract_document(pages)


# ---------------------------------------------------------------------------
# Corpus evaluation
# ---------------------------------------------------------------------------


async def evaluate_corpus(
    corpus_dir: Path,
    *,
    verbose: bool = False,
) -> dict[str, DocTypeResult]:
    results: dict[str, DocTypeResult] = {}

    doc_dirs = [d for d in sorted(corpus_dir.rglob("*")) if (d / "expected.json").exists()]

    if not doc_dirs:
        print(f"No annotated documents found under {corpus_dir}", file=sys.stderr)
        return results

    print(f"Found {len(doc_dirs)} annotated documents\n")

    for doc_dir in doc_dirs:
        expected_path = doc_dir / "expected.json"
        input_files = [
            f for f in doc_dir.iterdir()
            if f.name.startswith("input.") and f.suffix in (".pdf", ".jpg", ".jpeg", ".png", ".tiff")
        ]

        if not input_files:
            print(f"  SKIP  {doc_dir.name} (no input file)", file=sys.stderr)
            continue

        with open(expected_path) as f:
            expected = json.load(f)

        doc_type = expected.get("document_type", "unknown")
        if doc_type not in results:
            results[doc_type] = DocTypeResult(name=doc_type)

        result = results[doc_type]
        result.doc_count += 1

        try:
            extracted = await _run_extraction(input_files[0])
        except Exception as exc:
            result.failed += 1
            result.field_accuracy.total += int(sum(FIELD_WEIGHTS.get(doc_type, {}).values()) * 1000)
            result.amount_validation_total += 1
            if verbose:
                print(f"  FAIL  {doc_dir.name}: {exc}", file=sys.stderr)
            else:
                print(f"  FAIL  {doc_dir.name}", file=sys.stderr)
            continue

        correct, total = _score_document(extracted, expected, doc_type)
        result.field_accuracy.correct += correct
        result.field_accuracy.total += total

        result.amount_validation_total += 1
        validation = extracted.get("validation", {})
        if validation.get("amounts_balance") and not validation.get("flags"):
            result.amount_validation_passed += 1

        if verbose:
            field_pct = correct / total * 100 if total else 0
            print(f"  OK    {doc_dir.name} ({doc_type}) — {field_pct:.0f}% fields correct")
        else:
            print(f"  OK    {doc_dir.name}")

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _print_table(results: dict[str, DocTypeResult]) -> None:
    type_labels = {
        "invoice": "Invoices (PDF, clean)",
        "invoice_scanned": "Invoices (scanned)",
        "bank_statement": "Bank statements",
        "receipt": "Receipts",
        "payslip": "Payslips",
    }

    print()
    print("=" * 76)
    print(f"  {'Document type':<34} {'Field accuracy':>16}   {'Amt val. pass rate':>16}")
    print("=" * 76)

    total_correct = 0
    total_fields = 0
    total_docs = 0

    for doc_type, result in sorted(results.items()):
        if result.doc_count == 0:
            continue
        label = type_labels.get(doc_type, doc_type)
        field_pct = result.field_accuracy.accuracy * 100
        amount_pct = result.amount_pass_rate * 100
        failed_str = f" ({result.failed} failed)" if result.failed else ""
        print(
            f"  {label + failed_str:<34} {field_pct:>15.1f}%   {amount_pct:>15.1f}%"
        )
        total_correct += result.field_accuracy.correct
        total_fields += result.field_accuracy.total
        total_docs += result.doc_count

    overall = total_correct / total_fields * 100 if total_fields else 0.0
    print("=" * 76)
    print(f"  {'Overall (' + str(total_docs) + ' documents)':<34} {overall:>15.1f}%")
    print()


def _write_json(results: dict[str, DocTypeResult], output_path: Path) -> None:
    data = {
        doc_type: {
            "doc_count": r.doc_count,
            "failed": r.failed,
            "field_accuracy": round(r.field_accuracy.accuracy, 4),
            "amount_pass_rate": round(r.amount_pass_rate, 4),
        }
        for doc_type, r in results.items()
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Results written to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate finparse-ai extraction accuracy against an annotated corpus"
    )
    parser.add_argument(
        "--corpus",
        required=True,
        type=Path,
        help="Root directory of the annotated corpus (see docstring for layout)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON results to this path",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-field accuracy for each document",
    )
    args = parser.parse_args()

    if not args.corpus.is_dir():
        print(f"error: corpus not found: {args.corpus}", file=sys.stderr)
        sys.exit(1)

    results = asyncio.run(evaluate_corpus(args.corpus, verbose=args.verbose))

    if not results:
        sys.exit(1)

    _print_table(results)

    if args.output:
        _write_json(results, args.output)


if __name__ == "__main__":
    main()
