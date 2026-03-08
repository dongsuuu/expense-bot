"""
PDF Processing Utility
"""

import os
import logging
from typing import List, Optional
from pdf2image import convert_from_path
import pytesseract
from PyPDF2 import PdfReader

from app.core.config import settings

logger = logging.getLogger(__name__)


class PDFProcessor:
    """PDF 처리기"""
    
    def __init__(self):
        self.temp_dir = "/tmp/expense-bot/pdf"
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def convert_to_images(self, pdf_path: str, dpi: int = 300) -> List[str]:
        """
        PDF를 이미지로 변환
        
        Returns:
            이미지 파일 경로 리스트
        """
        try:
            images = convert_from_path(
                pdf_path,
                dpi=dpi,
                output_folder=self.temp_dir,
                fmt="jpeg",
                paths_only=True
            )
            logger.info(f"PDF converted to {len(images)} images")
            return images
            
        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return []
    
    def extract_text(self, pdf_path: str) -> Optional[str]:
        """
        PDF에서 텍스트 직접 추출 (텍스트 PDF용)
        
        Returns:
            추출된 텍스트 또는 None
        """
        try:
            reader = PdfReader(pdf_path)
            text_parts = []
            
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            
            full_text = "\n".join(text_parts).strip()
            
            # 텍스트가 너무 적으면 스캔된 PDF로 간주
            if len(full_text) < 50:
                logger.info("PDF appears to be scanned (insufficient text)")
                return None
            
            logger.info(f"Extracted {len(full_text)} chars from PDF")
            return full_text
            
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return None
    
    def ocr_pdf(self, pdf_path: str) -> str:
        """
        스캔된 PDF OCR 처리
        
        Returns:
            OCR 텍스트
        """
        images = self.convert_to_images(pdf_path)
        
        if not images:
            return ""
        
        all_text = []
        for img_path in images:
            try:
                text = pytesseract.image_to_string(
                    img_path,
                    lang='eng+kor',  # 영어+한국어
                    config='--psm 6'
                )
                all_text.append(text)
            except Exception as e:
                logger.error(f"OCR failed for {img_path}: {e}")
        
        # 임시 이미지 정리
        for img_path in images:
            try:
                os.remove(img_path)
            except:
                pass
        
        return "\n".join(all_text)
    
    def process(self, pdf_path: str) -> dict:
        """
        PDF 통합 처리
        
        Returns:
            {
                "images": [이미지경로],
                "text": 추출텍스트,
                "is_scanned": 스캔여부
            }
        """
        # 1. 텍스트 추출 시도
        text = self.extract_text(pdf_path)
        is_scanned = text is None
        
        # 2. 텍스트가 없으면 OCR
        if is_scanned:
            text = self.ocr_pdf(pdf_path)
        
        # 3. 이미지 변환 (시각적 분석용)
        images = self.convert_to_images(pdf_path)
        
        return {
            "images": images,
            "text": text or "",
            "is_scanned": is_scanned
        }
