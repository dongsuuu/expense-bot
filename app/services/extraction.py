"""
Expense Extraction Service - with Proper Failure Handling
"""

import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

from app.models.schemas import (
    ExpenseExtracted, Transaction, StatementExtractionResult
)

logger = logging.getLogger(__name__)


class ExpenseExtractionService:
    """지출 추출 - 실패 시 명확한 결과 반환"""
    
    def __init__(self):
        self.openai_client = None
        try:
            import openai
            from app.core.config import settings
            if settings.OPENAI_API_KEY:
                self.openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        except:
            pass
    
    async def extract_receipt(
        self,
        images: List[str],
        raw_text: Optional[str] = None,
        caption: Optional[str] = None
    ) -> ExpenseExtracted:
        """영수증 추출 - 실패 시 need_review=True"""
        
        ocr_texts = []
        
        if raw_text:
            ocr_texts.append(raw_text)
        
        # OCR (생략 - 기존 코드 유지)
        full_text = "\n".join(ocr_texts).strip()
        
        if not full_text:
            logger.warning("No text extracted from receipt")
            return ExpenseExtracted(
                need_review=True,
                confidence=0.0,
                feedback=["텍스트를 추출할 수 없습니다."]
            )
        
        # 파싱 시도
        expense = self._parse_receipt_text(full_text)
        expense.raw_text = full_text[:2000]
        
        # Validation: 핵심 필드 없으면 실패
        if not expense.merchant or expense.total is None:
            logger.warning(f"Receipt parsing incomplete: merchant={expense.merchant}, total={expense.total}")
            expense.need_review = True
            expense.confidence = 0.2
            expense.feedback.append("핵심 정보(가맹점, 금액)를 찾을 수 없습니다.")
        
        return expense
    
    def _parse_receipt_text(self, text: str) -> ExpenseExtracted:
        """영수증 텍스트 파싱 - 최소한의 추측"""
        expense = ExpenseExtracted()
        
        # 금액 추출 (가장 큰 금액을 total로)
        amounts = re.findall(r'\$?([\d,]+\.\d{2})', text)
        if amounts:
            try:
                # Convert and find max
                parsed = [float(a.replace(',', '')) for a in amounts]
                expense.total = max(parsed)
            except:
                pass
        
        # 날짜 추출
        date_patterns = [
            r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
            r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    groups = match.groups()
                    if len(groups[0]) == 4:
                        expense.transaction_date = datetime(
                            int(groups[0]), int(groups[1]), int(groups[2])
                        ).date()
                    break
                except:
                    pass
        
        # 가맹점 추출 (첫 줄 또는 특정 패턴)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            # 첫 번째 의미있는 줄을 가맹점으로
            for line in lines[:3]:
                if len(line) > 2 and not line.startswith('$') and not line[0].isdigit():
                    expense.merchant = line[:50]
                    break
        
        # 추출 성공 여부에 따른 confidence
        if expense.merchant and expense.total and expense.transaction_date:
            expense.confidence = 0.6
        elif expense.total:
            expense.confidence = 0.4
        else:
            expense.confidence = 0.2
            expense.need_review = True
        
        return expense
    
    async def extract_statement(
        self,
        pdf_text: str,
        filename: Optional[str] = None
    ) -> StatementExtractionResult:
        """명세서 추출 - 실패 시 빈 transactions 반환"""
        
        if not pdf_text or len(pdf_text) < 200:
            logger.error("PDF text too short or empty")
            return StatementExtractionResult(
                transactions=[],
                confidence=0.0,
                need_review=True
            )
        
        # 명세서 월 추출
        statement_month = self._extract_statement_month(pdf_text)
        
        # 거래 라인 파싱
        transactions = self._parse_transaction_lines(pdf_text)
        
        if not transactions:
            logger.warning("No transactions parsed from statement")
            return StatementExtractionResult(
                transactions=[],
                statement_month=statement_month,
                confidence=0.0,
                need_review=True
            )
        
        # 유효한 거래만 필터링
        valid_transactions = []
        for tx in transactions:
            # 최소한의 유효성 검사
            if tx.amount == 0:
                continue  # Skip zero amounts
            if not tx.description or len(tx.description) < 3:
                continue  # Skip too short descriptions
            
            valid_transactions.append(tx)
        
        logger.info(f"Parsed {len(transactions)} transactions, {len(valid_transactions)} valid")
        
        # 요약 계산
        total_debits = sum(t.amount for t in valid_transactions if t.amount > 0)
        total_credits = sum(abs(t.amount) for t in valid_transactions if t.amount < 0)
        
        # 신뢰도 계산
        if len(valid_transactions) >= 5:
            confidence = 0.7
        elif len(valid_transactions) >= 1:
            confidence = 0.5
        else:
            confidence = 0.2
        
        return StatementExtractionResult(
            transactions=valid_transactions,
            statement_month=statement_month,
            total_debits=total_debits,
            total_credits=total_credits,
            currency="USD",
            source_file=filename,
            confidence=confidence,
            need_review=(len(valid_transactions) == 0)
        )
    
    def _extract_statement_month(self, text: str) -> Optional[str]:
        """명세서 월 추출"""
        # Chase style: "Feb 27, 2026"
        patterns = [
            (r'(\w{3})\s+(\d{1,2}),?\s+(\d{4})', 'mon_day_year'),
            (r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', 'year_mon_day'),
        ]
        
        for pattern, ptype in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    groups = match.groups()
                    if ptype == 'mon_day_year':
                        year = groups[2]
                        month_str = groups[0]
                        month_map = {
                            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                        }
                        month = month_map.get(month_str.lower(), '01')
                        return f"{year}-{month}"
                    else:
                        year = groups[0]
                        month = groups[1].zfill(2)
                        return f"{year}-{month}"
                except:
                    pass
        
        return datetime.now().strftime("%Y-%m")
    
    def _parse_transaction_lines(self, text: str) -> List[Transaction]:
        """거래 라인 파싱 - 엄격한 필터링"""
        transactions = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 20:
                continue
            
            # Skip non-transaction lines
            if self._is_non_transaction_line(line):
                continue
            
            # Parse transaction
            transaction = self._parse_single_transaction(line)
            if transaction and transaction.amount != 0:
                transactions.append(transaction)
        
        return transactions
    
    def _is_non_transaction_line(self, line: str) -> bool:
        """거래가 아닌 라인 필터링 - 더 엄격하게"""
        skip_keywords = [
            'total checking', 'chase.com', 'printed from', 'page ', ' of ',
            'transactions showing', 'date description', 'balance', 'pending',
            'https://', 'www.', '.com', 'account', 'summary', 'opening balance',
            'closing balance', 'total', 'deposits', 'withdrawals'
        ]
        
        line_lower = line.lower()
        
        # Skip keywords
        for kw in skip_keywords:
            if kw in line_lower:
                return True
        
        # Just numbers (balance lines)
        if re.match(r'^\$?[\d,]+\.?\d*$', line.strip()):
            return True
        
        # Too many numbers, not enough text
        num_count = len(re.findall(r'\d', line))
        letter_count = len(re.findall(r'[a-zA-Z]', line))
        if num_count > letter_count * 2:
            return True
        
        return False
    
    def _parse_single_transaction(self, line: str) -> Optional[Transaction]:
        """단일 거래 파싱 - Chase 포맷 중심"""
        
        # Chase pattern: "Mar 6, 2026 Description ... − $10.00 $816.34"
        # Look for date + description + amount + balance
        
        # Date pattern
        date_match = re.search(r'(\w{3})\s+(\d{1,2}),?\s+(\d{4})', line)
        if not date_match:
            return None
        
        # Extract date
        try:
            date_str = f"{date_match.group(3)}-{self._month_to_num(date_match.group(1))}-{date_match.group(2).zfill(2)}"
            tx_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            tx_date = None
        
        # Find amounts ($X.XX patterns)
        amounts = re.findall(r'\$([\d,]+\.\d{2})', line)
        if len(amounts) < 2:
            return None  # Need at least transaction amount and balance
        
        # Transaction amount is usually the second-to-last, balance is last
        try:
            tx_amount = float(amounts[-2].replace(',', ''))
        except:
            return None
        
        # Determine if debit (expense) or credit
        # Check for minus sign or debit keywords before the amount
        before_amount = line[:line.find(f"${amounts[-2]}")]
        is_debit = any(c in before_amount for c in ['−', '-']) or 'debit' in line.lower()
        
        if not is_debit:
            # Might be credit or balance-only line
            # Skip if looks like balance line
            return None
        
        # Extract description (between date and amount)
        desc_start = date_match.end()
        desc_end = line.find(f"${amounts[-2]}")
        if desc_start < desc_end:
            description = line[desc_start:desc_end].strip()
            # Clean up
            description = re.sub(r'\s+', ' ', description)
            description = re.sub(r'\d{5,}', '', description)  # Remove long numbers
            description = description.strip()
        else:
            description = "Unknown"
        
        if len(description) < 3:
            return None
        
        # Extract merchant
        merchant = self._extract_merchant(description)
        
        # Extract raw type
        raw_type = None
        if 'Zelle' in line:
            raw_type = 'Zelle'
        elif 'POS DEBIT' in line:
            raw_type = 'POS DEBIT'
        elif 'ACH' in line:
            raw_type = 'ACH'
        
        return Transaction(
            transaction_date=tx_date,
            description=description,
            merchant=merchant,
            amount=tx_amount,  # Positive = expense
            currency="USD",
            raw_type=raw_type,
            transaction_type="debit" if is_debit else "credit",
            confidence=0.6 if tx_date else 0.4
        )
    
    def _month_to_num(self, month_str: str) -> str:
        """월 이름을 숫자로"""
        month_map = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        return month_map.get(month_str.lower(), '01')
    
    def _extract_merchant(self, description: str) -> Optional[str]:
        """설명에서 가맹점 추출"""
        # Remove common prefixes
        prefixes = ['POS DEBIT', 'Zelle payment to', 'ACH debit', 'Zelle']
        for prefix in prefixes:
            if description.startswith(prefix):
                description = description[len(prefix):].strip()
        
        # Clean
        description = re.sub(r'\d{5,}', '', description).strip()
        description = re.sub(r'\s+', ' ', description)
        
        return description[:50] if description else None
