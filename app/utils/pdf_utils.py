"""
PDF Utilities
"""
import logging
from typing import List, Optional
from pdf2image import convert_from_path
import PyPDF2

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Process PDF files"""
    
    def extract_text(self, pdf_path: str) -> Optional[str]:
        """Extract text from PDF"""
        try:
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return text if text.strip() else None
        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
            return None
    
    def convert_to_images(self, pdf_path: str, dpi: int = 200) -> List[str]:
        """Convert PDF pages to images"""
        try:
            images = convert_from_path(pdf_path, dpi=dpi)
            image_paths = []
            for i, image in enumerate(images):
                path = f"{pdf_path}_page_{i}.jpg"
                image.save(path, 'JPEG')
                image_paths.append(path)
            logger.info(f"Converted PDF to {len(image_paths)} images")
            return image_paths
        except Exception as e:
            logger.error(f"PDF to image conversion failed: {e}")
            return []
