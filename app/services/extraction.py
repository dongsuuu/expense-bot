"""
Expense Extraction Service
OCR + LLM 기반 지출 정보 추출
"""

import json
import logging
from typing import List, Optional
from datetime import date

import openai
import pytesseract
from PIL import Image

from app.core.config import settings
from app.models.schemas import ExpenseExtracted, LineItem

logger = logging.getLogger(__name__)


class ExpenseExtractionService:
    """지출 정보 추출 서비스"""
    
    def __init__(self):
        self.openai_client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY
        ) if settings.OPENAI_API_KEY else None
    
    async def extract(
        self,
        images: List[str],
        raw_text: Optional[str] = None,
        caption: Optional[str] = None
    ) -> ExpenseExtracted:
        """
        이미지에서 지출 정보 추출
        """
        # 1. OCR 텍스트 수집
        ocr_texts = []
        
        if raw_text:
            ocr_texts.append(raw_text)
        
        for img_path in images:
            try:
                text = pytesseract.image_to_string(
                    Image.open(img_path),
                    lang='eng+kor'
                )
                ocr_texts.append(text)
            except Exception as e:
                logger.error(f"OCR failed: {e}")
        
        full_text = "\n".join(ocr_texts).strip()
        
        # 2. LLM으로 구조화
        if self.openai_client and full_text:
            extracted = await self._extract_with_llm(full_text, caption)
        else:
            # LLM 없으면 기본 파싱
            extracted = self._extract_with_regex(full_text)
        
        extracted.raw_text = full_text[:2000]  # 원본 텍스트 저장
        
        return extracted
    
    async def _extract_with_llm(
        self,
        text: str,
        caption: Optional[str] = None
    ) -> ExpenseExtracted:
        """LLM으로 정보 추출"""
        
        prompt = f"""You are an expense extraction engine. Analyze this receipt/invoice and extract structured information.

Extracted text:
{text[:3000]}

User caption: {caption or "None"}

Return valid JSON only:
{{
    "document_type": "receipt|invoice|screenshot|statement|unknown",
    "merchant": "store name or null",
    "transaction_date": "YYYY-MM-DD or null",
    "currency": "KRW|USD|etc or null",
    "subtotal": number or null,
    "tax": number or null,
    "tip": number or null,
    "total": number or null,
    "payment_method": "card|cash|etc or null",
    "category": "Groceries|Dining|Transportation|Housing|Utilities|Shopping|Health|Education|Subscription|Travel|Income|Transfer|Other",
    "subcategory": "string or null",
    "line_items": [{{"name": "...", "quantity": 1, "unit_price": 1000, "total_price": 1000}}],
    "confidence": 0.0-1.0,
    "need_review": true/false,
    "feedback": ["string"]
}}

Rules:
- Never hallucinate values
- Use null for unknown fields
- If merchant, date, or total is uncertain, set need_review=true
- confidence should reflect extraction certainty
- Parse dates flexibly (Korean format supported)
- Remove currency symbols from numbers"""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract expense data from receipts. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content
            
            # JSON 파싱
            # 코드 블록 제거
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content.strip())
            
            # 날짜 파싱
            date_str = data.get("transaction_date")
            if date_str:
                try:
                    date_obj = date.fromisoformat(date_str)
                except:
                    date_obj = None
            else:
                date_obj = None
            
            return ExpenseExtracted(
                document_type=data.get("document_type", "unknown"),
                merchant=data.get("merchant"),
                transaction_date=date_obj,
                currency=data.get("currency", "KRW"),
                subtotal=data.get("subtotal"),
                tax=data.get("tax"),
                tip=data.get("tip"),
                total=data.get("total"),
                payment_method=data.get("payment_method"),
                category=data.get("category", "Other"),
                subcategory=data.get("subcategory"),
                line_items=[LineItem(**item) for item in data.get("line_items", [])],
                confidence=data.get("confidence", 0.5),
                need_review=data.get("need_review", True),
                feedback=data.get("feedback", [])
            )
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return self._extract_with_regex(text)
    
    def _extract_with_regex(self, text: str) -> ExpenseExtracted:
        """정규식 기본 추출 (LLM 실패 시 폴백)"""
        import re
        
        # 금액 추출 (숫자 + ,)
        amounts = re.findall(r'(\d{1,3}(?:,\d{3})+)', text)
        amounts = [int(a.replace(',', '')) for a in amounts]
        
        total = max(amounts) if amounts else None
        
        # 날짜 추출
        date_patterns = [
            r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
            r'(\d{2})[-/.](\d{1,2})[-/.](\d{2,4})',
        ]
        
        transaction_date = None
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    groups = match.groups()
                    if len(groups[0]) == 4:
                        transaction_date = date(int(groups[0]), int(groups[1]), int(groups[2]))
                    else:
                        year = int(groups[2]) if len(groups[2]) == 4 else 2000 + int(groups[2])
                        transaction_date = date(year, int(groups[0]), int(groups[1]))
                    break
                except:
                    pass
        
        return ExpenseExtracted(
            document_type="unknown",
            merchant=None,
            transaction_date=transaction_date,
            total=total,
            confidence=0.3,
            need_review=True,
            feedback=["LLM extraction failed. Basic regex used. Please review."]
        )
