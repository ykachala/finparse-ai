"""
Document preprocessor: PDF-to-image conversion and image normalisation pipeline.

Pipeline overview:
  raw bytes → PDF-to-images (pdf2image) → normalise each page
              ↓
  normalise: RGB conversion → contrast enhancement (1.3x) → sharpening → deskew
              ↓
  output: list of ProcessedPage (JPEG bytes + base64 for Claude API)
"""

import base64
import io
import math
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter


@dataclass
class ProcessedPage:
    """A single normalised page ready for Claude Vision."""

    page_number: int
    image_bytes: bytes  # JPEG bytes
    base64_data: str  # base64-encoded JPEG for Claude API
    width: int
    height: int


class DocumentPreprocessor:
    """Convert uploaded documents into a list of normalised ProcessedPage objects."""

    # DPI for PDF-to-image conversion — 200 DPI provides good OCR quality
    PDF_DPI: int = 200
    # JPEG quality for output images — high enough for Claude to read fine print
    JPEG_QUALITY: int = 90
    # Contrast enhancement factor (1.0 = original, 1.3 = slightly boosted)
    CONTRAST_FACTOR: float = 1.3
    # Minimum skew angle (degrees) below which we skip correction
    SKEW_THRESHOLD: float = 0.5

    def process(self, file_data: bytes, file_type: str) -> list[ProcessedPage]:
        """
        Convert file bytes to a list of normalised ProcessedPage objects.

        Args:
            file_data: Raw bytes of the uploaded file.
            file_type: One of "pdf", "jpeg", "png", "tiff".

        Returns:
            Ordered list of ProcessedPage, one per page.
        """
        if file_type == "pdf":
            images = self._pdf_to_images(file_data)
        else:
            images = [Image.open(io.BytesIO(file_data))]

        return [self._process_image(img, i + 1) for i, img in enumerate(images)]

    def _pdf_to_images(self, pdf_data: bytes) -> list[Image.Image]:
        """Convert PDF bytes to a list of PIL Images, one per page."""
        from pdf2image import convert_from_bytes

        return convert_from_bytes(pdf_data, dpi=self.PDF_DPI)

    def _process_image(self, image: Image.Image, page_num: int) -> ProcessedPage:
        """
        Normalise a single PIL Image:
        1. Convert to RGB (handles CMYK, RGBA, L mode inputs)
        2. Enhance contrast
        3. Apply mild sharpening
        4. Deskew (correct small rotations)
        5. Encode to JPEG bytes and base64

        Returns a ProcessedPage.
        """
        # Step 1: Ensure RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Step 2: Contrast enhancement
        contrast_enhancer = ImageEnhance.Contrast(image)
        image = contrast_enhancer.enhance(self.CONTRAST_FACTOR)

        # Step 3: Mild sharpening
        image = image.filter(ImageFilter.SHARPEN)

        # Step 4: Deskew
        image = self._deskew(image)

        # Step 5: Encode to JPEG
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self.JPEG_QUALITY, optimize=True)
        jpeg_bytes = buffer.getvalue()

        b64 = base64.b64encode(jpeg_bytes).decode("ascii")

        return ProcessedPage(
            page_number=page_num,
            image_bytes=jpeg_bytes,
            base64_data=b64,
            width=image.width,
            height=image.height,
        )

    def _deskew(self, image: Image.Image) -> Image.Image:
        """
        Detect and correct small rotational skew in the image.

        Strategy:
        - Convert to grayscale and threshold to binary
        - Project horizontal pixel sums to detect dominant line angle
        - Rotate by negative of detected angle if above SKEW_THRESHOLD
        - Fill with white background after rotation
        """
        try:
            gray = image.convert("L")
            # Simple variance-projection deskew
            angle = self._estimate_skew_angle(gray)
            if abs(angle) < self.SKEW_THRESHOLD:
                return image
            # Rotate to correct skew; expand=True avoids cropping
            return image.rotate(angle, expand=True, fillcolor=(255, 255, 255))
        except Exception:
            # If deskew fails for any reason, return original unchanged
            return image

    def _estimate_skew_angle(self, gray: Image.Image) -> float:
        """
        Estimate skew angle by finding the angle that maximises horizontal
        projection variance (standard Hough-inspired approach without OpenCV).

        Tests angles in [-10, +10] degree range at 0.5 degree increments.
        Returns the angle (in degrees) that produced the highest row-sum variance.
        """
        import array

        best_angle = 0.0
        best_variance = -1.0

        candidates = [i * 0.5 for i in range(-20, 21)]  # -10 to +10 degrees

        for angle in candidates:
            rotated = gray.rotate(angle, expand=False, fillcolor=255)
            pixels = rotated.load()
            width, height = rotated.size

            row_sums = array.array("l")
            for y in range(height):
                row_sum = sum(pixels[x, y] for x in range(width))  # type: ignore[index]
                row_sums.append(row_sum)

            mean = sum(row_sums) / len(row_sums)
            variance = sum((v - mean) ** 2 for v in row_sums) / len(row_sums)

            if variance > best_variance:
                best_variance = variance
                best_angle = angle

        return best_angle
