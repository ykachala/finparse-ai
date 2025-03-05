"""
Page splitting utilities for multi-page document handling.

Provides functions to split and order pages from the preprocessor pipeline,
supporting both full-document processing and selective page extraction.
"""

from src.preprocessor.processor import ProcessedPage


def split_pages(
    pages: list[ProcessedPage],
    max_pages_per_chunk: int | None = None,
) -> list[list[ProcessedPage]]:
    """
    Split a list of ProcessedPage objects into ordered chunks.

    Args:
        pages: All document pages in order.
        max_pages_per_chunk: Maximum pages per chunk. None returns all pages as
            a single chunk (default for Claude's multi-image context window).

    Returns:
        List of page chunks, each chunk being a contiguous ordered list.
    """
    if not pages:
        return []

    # Ensure pages are sorted by page number
    ordered = sorted(pages, key=lambda p: p.page_number)

    if max_pages_per_chunk is None:
        return [ordered]

    chunks: list[list[ProcessedPage]] = []
    for i in range(0, len(ordered), max_pages_per_chunk):
        chunks.append(ordered[i : i + max_pages_per_chunk])
    return chunks


def select_representative_pages(
    pages: list[ProcessedPage],
    max_pages: int = 10,
) -> list[ProcessedPage]:
    """
    Select a representative subset of pages for documents with many pages.

    For documents longer than max_pages, selects:
    - The first two pages (cover + summary)
    - Evenly spaced middle pages
    - The last page (often contains totals/signatures)

    This keeps Claude API token usage bounded while preserving document coverage.

    Args:
        pages: All document pages in order.
        max_pages: Maximum pages to return.

    Returns:
        Ordered subset of pages most likely to contain extractable data.
    """
    if len(pages) <= max_pages:
        return sorted(pages, key=lambda p: p.page_number)

    ordered = sorted(pages, key=lambda p: p.page_number)

    # Always include first two and last page
    selected_indices: set[int] = {0, min(1, len(ordered) - 1), len(ordered) - 1}

    # Fill remaining slots with evenly spaced pages
    remaining_slots = max_pages - len(selected_indices)
    if remaining_slots > 0 and len(ordered) > 3:
        step = (len(ordered) - 2) / (remaining_slots + 1)
        for i in range(1, remaining_slots + 1):
            idx = min(int(round(i * step)), len(ordered) - 2)
            selected_indices.add(idx)

    return [ordered[i] for i in sorted(selected_indices)]
