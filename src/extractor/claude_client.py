"""Anthropic Claude Vision client with retry logic for the finparse extraction pipeline."""

import time

import anthropic

from src.preprocessor.processor import ProcessedPage


class ClaudeVisionClient:
    """
    Thin wrapper around the Anthropic SDK that:
    - Constructs multi-image messages from ProcessedPage objects
    - Sends extraction prompts to Claude Vision
    - Retries on rate limit errors with exponential back-off
    """

    MODEL: str = "claude-sonnet-4-5"
    MAX_TOKENS: int = 4096
    MAX_RETRIES: int = 3

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def extract(self, pages: list[ProcessedPage], prompt: str) -> str:
        """
        Send document page images + extraction prompt to Claude Vision.

        Each page is attached as a base64-encoded JPEG image followed by the
        text prompt instructing Claude to return structured JSON.

        Args:
            pages: Processed document pages to analyse.
            prompt: Type-specific extraction prompt.

        Returns:
            Raw text response from Claude (expected to be JSON).

        Raises:
            anthropic.RateLimitError: If all retries are exhausted.
        """
        content: list[dict] = []

        for page in pages:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": page.base64_data,
                    },
                }
            )

        content.append({"type": "text", "text": prompt})

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._client.messages.create(
                    model=self.MODEL,
                    max_tokens=self.MAX_TOKENS,
                    messages=[{"role": "user", "content": content}],
                )
                block = response.content[0]
                return block.text if block.type == "text" else ""
            except anthropic.RateLimitError:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2**attempt)
                    continue
                raise

        return ""  # unreachable but satisfies type checker
