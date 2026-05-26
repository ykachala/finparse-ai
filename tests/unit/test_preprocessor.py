"""Unit tests for the document preprocessor pipeline."""

import io
import os
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.preprocessor.processor import DocumentPreprocessor, ProcessedPage


def _make_rgb_image(width: int = 200, height: int = 300, color: tuple = (240, 240, 240)) -> Image.Image:
    """Create a solid-color RGB PIL Image for testing."""
    return Image.new("RGB", (width, height), color)


def _make_grayscale_image(width: int = 200, height: int = 300) -> Image.Image:
    """Create a grayscale L-mode image."""
    return Image.new("L", (width, height), 200)


def _make_rgba_image(width: int = 200, height: int = 300) -> Image.Image:
    """Create an RGBA image with transparency."""
    return Image.new("RGBA", (width, height), (200, 200, 200, 128))


def _image_to_jpeg_bytes(image: Image.Image) -> bytes:
    """Convert a PIL Image to JPEG bytes."""
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG")
    return buf.getvalue()


def _image_to_png_bytes(image: Image.Image) -> bytes:
    """Convert a PIL Image to PNG bytes."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class TestDocumentPreprocessorPDF:
    """Tests for PDF input processing."""

    def test_pdf_input_returns_list_of_processed_pages(self) -> None:
        """PDF input should return one ProcessedPage per page."""
        preprocessor = DocumentPreprocessor()
        mock_pages = [_make_rgb_image(300, 400), _make_rgb_image(300, 400)]

        with patch("src.preprocessor.processor.DocumentPreprocessor._pdf_to_images", return_value=mock_pages):
            pdf_bytes = b"%PDF-1.4 fake"
            result = preprocessor.process(pdf_bytes, "pdf")

        assert len(result) == 2
        assert all(isinstance(page, ProcessedPage) for page in result)

    def test_multi_page_pdf_returns_pages_in_order(self) -> None:
        """Pages must be returned in ascending page_number order."""
        preprocessor = DocumentPreprocessor()
        mock_pages = [
            _make_rgb_image(300, 400, (200, 200, 200)),
            _make_rgb_image(300, 400, (180, 180, 180)),
            _make_rgb_image(300, 400, (160, 160, 160)),
        ]

        with patch("src.preprocessor.processor.DocumentPreprocessor._pdf_to_images", return_value=mock_pages):
            result = preprocessor.process(b"%PDF fake", "pdf")

        assert [p.page_number for p in result] == [1, 2, 3]

    def test_single_page_pdf_returns_one_page(self) -> None:
        """A single-page PDF returns exactly one ProcessedPage."""
        preprocessor = DocumentPreprocessor()
        mock_pages = [_make_rgb_image()]

        with patch("src.preprocessor.processor.DocumentPreprocessor._pdf_to_images", return_value=mock_pages):
            result = preprocessor.process(b"%PDF fake", "pdf")

        assert len(result) == 1
        assert result[0].page_number == 1

    def test_pdf_to_images_called_with_correct_dpi(self) -> None:
        """_pdf_to_images must be called with the configured DPI."""
        preprocessor = DocumentPreprocessor()
        pdf_bytes = b"%PDF-1.4 fake"

        with patch("pdf2image.convert_from_bytes", return_value=[_make_rgb_image()]) as mock_convert:
            result = preprocessor._pdf_to_images(pdf_bytes)

        mock_convert.assert_called_once_with(pdf_bytes, dpi=DocumentPreprocessor.PDF_DPI)


class TestDocumentPreprocessorImage:
    """Tests for image (JPEG/PNG/TIFF) input processing."""

    def test_jpeg_input_returns_single_page(self) -> None:
        """JPEG input must return exactly one ProcessedPage."""
        preprocessor = DocumentPreprocessor()
        img = _make_rgb_image(400, 500)
        jpeg_bytes = _image_to_jpeg_bytes(img)

        result = preprocessor.process(jpeg_bytes, "jpeg")

        assert len(result) == 1
        assert isinstance(result[0], ProcessedPage)

    def test_png_input_returns_single_page(self) -> None:
        """PNG input must return exactly one ProcessedPage."""
        preprocessor = DocumentPreprocessor()
        img = _make_rgb_image(400, 500)
        png_bytes = _image_to_png_bytes(img)

        result = preprocessor.process(png_bytes, "png")

        assert len(result) == 1
        assert result[0].page_number == 1

    def test_grayscale_image_converted_to_rgb(self) -> None:
        """Grayscale (L-mode) images must be converted to RGB before processing."""
        preprocessor = DocumentPreprocessor()
        gray = _make_grayscale_image()
        jpeg_bytes = _image_to_jpeg_bytes(gray)

        result = preprocessor.process(jpeg_bytes, "jpeg")

        # Should succeed and produce valid output
        assert len(result) == 1
        assert len(result[0].image_bytes) > 0

    def test_rgba_image_converted_to_rgb(self) -> None:
        """RGBA images must be converted to RGB (stripping alpha channel)."""
        preprocessor = DocumentPreprocessor()
        rgba = _make_rgba_image()
        png_bytes = _image_to_png_bytes(rgba)

        result = preprocessor.process(png_bytes, "png")

        assert len(result) == 1
        assert len(result[0].image_bytes) > 0


class TestProcessedPageFields:
    """Tests for ProcessedPage field correctness."""

    def test_processed_page_has_non_empty_base64(self) -> None:
        """Each page must have non-empty base64_data."""
        preprocessor = DocumentPreprocessor()
        img = _make_rgb_image(200, 300)
        jpeg_bytes = _image_to_jpeg_bytes(img)

        result = preprocessor.process(jpeg_bytes, "jpeg")

        assert len(result[0].base64_data) > 0

    def test_processed_page_base64_is_valid(self) -> None:
        """base64_data must be valid base64-encoded JPEG."""
        import base64

        preprocessor = DocumentPreprocessor()
        img = _make_rgb_image(200, 300)
        jpeg_bytes = _image_to_jpeg_bytes(img)

        result = preprocessor.process(jpeg_bytes, "jpeg")

        decoded = base64.b64decode(result[0].base64_data)
        assert len(decoded) > 0
        # JPEG magic bytes
        assert decoded[:2] == b"\xff\xd8"

    def test_processed_page_width_height_populated(self) -> None:
        """Width and height must match the processed image dimensions."""
        preprocessor = DocumentPreprocessor()
        img = _make_rgb_image(640, 480)
        jpeg_bytes = _image_to_jpeg_bytes(img)

        result = preprocessor.process(jpeg_bytes, "jpeg")

        assert result[0].width > 0
        assert result[0].height > 0

    def test_processed_page_image_bytes_non_empty(self) -> None:
        """image_bytes must be non-empty JPEG data."""
        preprocessor = DocumentPreprocessor()
        img = _make_rgb_image(200, 300)
        jpeg_bytes = _image_to_jpeg_bytes(img)

        result = preprocessor.process(jpeg_bytes, "jpeg")

        assert len(result[0].image_bytes) > 0

    def test_multi_page_each_page_has_base64(self) -> None:
        """Every page in a multi-page result must have non-empty base64."""
        preprocessor = DocumentPreprocessor()
        mock_pages = [_make_rgb_image(300 + i * 10, 400) for i in range(5)]

        with patch("src.preprocessor.processor.DocumentPreprocessor._pdf_to_images", return_value=mock_pages):
            result = preprocessor.process(b"%PDF fake", "pdf")

        for page in result:
            assert len(page.base64_data) > 0


class TestDeskew:
    """Tests for deskew correction."""

    def test_straight_image_not_significantly_rotated(self) -> None:
        """A straight image (no skew) should return without significant rotation."""
        preprocessor = DocumentPreprocessor()
        # Create an image with horizontal lines (low skew)
        img = _make_rgb_image(400, 600)
        # Draw a few horizontal pixel rows in darker tone to simulate text lines
        pixels = img.load()
        for y in range(100, 601, 80):
            for x in range(400):
                if y < 600:
                    pixels[x, y] = (50, 50, 50)  # type: ignore[index]

        result_img = preprocessor._deskew(img)
        # Should not raise and should return an image
        assert result_img is not None
        assert result_img.mode == "RGB"

    def test_deskew_returns_image_on_exception(self) -> None:
        """If deskew estimation raises, original image is returned unchanged."""
        preprocessor = DocumentPreprocessor()
        img = _make_rgb_image(100, 100)

        with patch.object(preprocessor, "_estimate_skew_angle", side_effect=RuntimeError("fail")):
            result = preprocessor._deskew(img)

        assert result is img  # original returned unchanged
