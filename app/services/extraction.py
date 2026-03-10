"""
Expense Extraction Service - Robust Chase Statement Parser
"""

import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

from app.models.schemas import ExpenseExtracted, Transaction

logger = logging.getLogger(__name__)


class ExpenseExtractionService:
    """지출 추출 - Robust Chase 지원"""
    
    # Month name mapping
    MONTH_MAP = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    # Transaction type patterns
    TX_TYPES = [
        'Zelle debit', 'Zelle credit', 'Zelle payment',
        'ACH debit', 'ACH credit',
        'POS DEBIT', 'POS debit',
        'Card', 'Debit Card', 'Credit Card'
    ]
    
    async def extract_receipt(
        self,
        images: List[str],
        raw_text: Optional[str] = None,
        caption: Optional[str] = None
    ) -> ExpenseExtracted:
        """영수증 추출"""
        expense = ExpenseExtracted()
        
        if raw_text:
            expense = self._parse_receipt_text(raw_text)
        
        return expense
    
    def _parse_receipt_text(self, text: str) -> ExpenseExtracted:
        """영수증 텍스트 파싱"""
        expense = ExpenseExtracted()
        
        amounts = re.findall(r'\$?([\d,]+\.\d{2})', text)
        if amounts:
            try:
                parsed = [float(a.replace(',', '')) for a in amounts]
                expense.total = max(parsed)
            except:
                pass
        
        date_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', text)
        if date_match:
            try:
                expense.transaction_date = datetime(
                    int(date_match.group(1)),
                    int(date_match.group(2)),
                    int(date_match.group(3))
                ).date()
            except:
                pass
        
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            expense.merchant = lines[0][:50]
        
        return expense
    
    def parse_chase_statement(self, text: str) -> List[Transaction]:
        """
        Chase statement 파싱 - Robust implementation
        """
        logger.info(f"Starting Chase parser: {len(text)} chars input")
        
        # 1. Normalize text
        normalized = self._normalize_text(text)
        logger.debug(f"Normalized text: {len(normalized)} chars")
        
        # 2. Split and preprocess lines
        raw_lines = normalized.split('\n')
        lines = self._preprocess_lines(raw_lines)
        logger.info(f"After preprocessing: {len(lines)} lines")
        
        if not lines:
            logger.warning("No valid lines after preprocessing")
            return []
        
        # 3. Stateful parsing
        transactions = self._stateful_parse(lines)
        
        logger.info(f"Parsing complete: {len(transactions)} transactions extracted")
        return transactions
    
    def _normalize_text(self, text: str) -> str:
        """텍스트 정규화"""
        # Unicode minus → ASCII minus
        text = text.replace('−', '-')
        text = text.replace('—', '-')
        text = text.replace('–', '-')
        
        # Collapse whitespace but preserve newlines
        lines = text.split('\n')
        normalized_lines = []
        for line in lines:
            # Replace multiple spaces with single space
            line = ' '.join(line.split())
            normalized_lines.append(line)
        
        return '\n'.join(normalized_lines)
    
    def _preprocess_lines(self, raw_lines: List[str]) -> List[str]:
        """라인 전처리 - 헤더/푸터 제거"""
        processed = []
        in_pending_section = False
        
        for line in raw_lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Detect Pending section
            if line.lower() == 'pending':
                logger.debug("Pending section detected, skipping")
                in_pending_section = True
                continue
            
            # Skip pending items
            if in_pending_section:
                # Check if we're out of pending (new date or section)
                if re.match(r'^(\w{3})\s+\d{1,2},?\s+\d{4}$', line):
                    in_pending_section = False
                else:
                    logger.debug(f"Skipping pending line: {line[:50]}")
                    continue
            
            # Skip noise lines
            if self._is_noise_line(line):
                logger.debug(f"Skipping noise: {line[:50]}")
                continue
            
            processed.append(line)
        
        return processed
    
    def _is_noise_line(self, line: str) -> bool:
        """노이즈 라인 필터링"""
        line_lower = line.lower()
        
        # Exact matches
        noise_exact = [
            'printed from chase personal online',
            'total checking',
            'transactions',
            'showing all transactions',
            'date description type amount balance',
            'deposits and additions',
            'withdrawals',
            'opening balance',
            'closing balance',
        ]
        
        for noise in noise_exact:
            if line_lower == noise:
                return True
        
        # Pattern matches
        noise_patterns = [
            r'^chase\.com',
            r'^https://secure\.chase\.com',
            r'^\d+/\d+$',  # page markers like 1/13
            r'^\d+/\d+/\d+\s+\d+:\d+',  # timestamps
            r'^\d{1,2}\.\s*\d{1,2}\.',  # localized dates
            r'^[\d\s]+오전',  # Korean timestamps
            r'^[\d\s]+오후',  # Korean timestamps
        ]
        
        for pattern in noise_patterns:
            if re.match(pattern, line_lower):
                return True
        
        return False
    
    def _stateful_parse(self, lines: List[str]) -> List[Transaction]:
        """Stateful 파싱 - date 유지, multiline 지원"""
        transactions = []
        
        current_date = None
        description_buffer = []
        
        logger.debug(f"Starting stateful parse of {len(lines)} lines")
        
        for i, line in enumerate(lines):
            logger.debug(f"Line {i}: {line[:80]}")
            
            # Try to detect date
            date_result = self._try_parse_date(line)
            
            if date_result:
                # New date found - save previous transaction if exists
                if current_date and description_buffer:
                    tx = self._try_build_transaction(
                        current_date, description_buffer
                    )
                    if tx:
                        transactions.append(tx)
                        logger.debug(f"Transaction built: {tx.description[:50]}")
                    description_buffer = []
                
                # Start new date context
                current_date = date_result['date']
                remaining = date_result['remaining']
                
                logger.debug(f"New date: {current_date}, remaining: {remaining[:50] if remaining else 'None'}")
                
                if remaining:
                    description_buffer.append(remaining)
            
            elif current_date:
                # No date - accumulate to description or try complete transaction
                # Check if this line completes a transaction
                tx = self._try_build_transaction(current_date, description_buffer + [line])
                
                if tx:
                    # This line completed a transaction
                    transactions.append(tx)
                    logger.debug(f"Transaction completed with line: {tx.description[:50]}")
                    description_buffer = []
                else:
                    # Just accumulate
                    description_buffer.append(line)
        
        # Don't forget last transaction
        if current_date and description_buffer:
            tx = self._try_build_transaction(current_date, description_buffer)
            if tx:
                transactions.append(tx)
                logger.debug(f"Final transaction built: {tx.description[:50]}")
        
        return transactions
    
    def _try_parse_date(self, line: str) -> Optional[dict]:
        """날짜 파싱 시도"""
        # Pattern: "Mar 6, 2026" or "Mar 6 2026"
        match = re.match(r'^(\w{3})\s+(\d{1,2}),?\s+(\d{4})(.*)$', line)
        
        if not match:
            return None
        
        month_str = match.group(1).lower()
        day = match.group(2)
        year = match.group(3)
        remaining = match.group(4).strip()
        
        month = self.MONTH_MAP.get(month_str)
        if not month:
            return None
        
        try:
            date = datetime(int(year), month, int(day)).date()
            return {
                'date': date,
                'remaining': remaining
            }
        except ValueError as e:
            logger.warning(f"Invalid date: {year}-{month}-{day}: {e}")
            return None
    
    def _try_build_transaction(
        self,
        date: datetime.date,
        description_lines: List[str]
    ) -> Optional[Transaction]:
        """트랜잭션 빌드 시도"""
        if not description_lines:
            return None
        
        # Join description lines
        full_text = ' '.join(description_lines)
        logger.debug(f"Trying to build transaction from: {full_text[:100]}")
        
        # Look for amount pattern: -$10.00 or $10.00 or just 10.00
        # Must have balance indicator (second amount)
        amount_pattern = r'(-?\$?([\d,]+\.\d{2}))\s+(-?\$?([\d,]+\.\d{2}))'
        amount_match = re.search(amount_pattern, full_text)
        
        if not amount_match:
            logger.debug("No amount/balance pattern found")
            return None
        
        try:
            # Parse amounts
            amount_str = amount_match.group(1).replace(',', '').replace('$', '')
            balance_str = amount_match.group(3).replace(',', '').replace('$', '')
            
            amount = float(amount_str)
            balance = float(balance_str)
            
            # Determine if expense (negative) or income (positive)
            # In Chase statements, debits are shown as negative or with minus sign
            is_expense = amount < 0 or '-$' in amount_match.group(0)
            
            # Extract description (everything before amount)
            desc_end = amount_match.start()
            description = full_text[:desc_end].strip()
            
            # Extract transaction type
            tx_type = self._extract_transaction_type(full_text)
            
            # Clean description
            description = self._clean_description(description, tx_type)
            
            # Build transaction
            transaction = Transaction(
                transaction_date=date,
                description=description,
                merchant=self._extract_merchant(description),
                amount=abs(amount),  # Store positive for expense
                currency='USD',
                raw_type=tx_type,
                transaction_type='debit' if is_expense else 'credit'
            )
            
            logger.debug(f"Built transaction: {description[:50]}, amount={amount}, type={tx_type}")
            return transaction
            
        except Exception as e:
            logger.warning(f"Failed to build transaction: {e}")
            return None
    
    def _extract_transaction_type(self, text: str) -> Optional[str]:
        """트랜잭션 타입 추출"""
        text_upper = text.upper()
        
        for tx_type in self.TX_TYPES:
            if tx_type.upper() in text_upper:
                return tx_type
        
        return None
    
    def _clean_description(self, description: str, tx_type: Optional[str]) -> str:
        """설명 정제"""
        # Remove transaction type from description
        if tx_type:
            description = re.sub(r'\s*' + re.escape(tx_type) + r'\s*', ' ', description, flags=re.IGNORECASE)
        
        # Clean up
        description = re.sub(r'\s+', ' ', description).strip()
        
        return description
    
    def _extract_merchant(self, description: str) -> Optional[str]:
        """가맹점 추출"""
        if not description:
            return None
        
        # Remove common prefixes
        prefixes = ['POS DEBIT', 'Zelle payment to', 'Zelle to', 'ACH', 'WIRE']
        for prefix in prefixes:
            if description.upper().startswith(prefix):
                description = description[len(prefix):].strip()
        
        # Remove long numbers (IDs, phone numbers)
        description = re.sub(r'\b\d{7,}\b', '', description)
        
        # Clean up
        description = re.sub(r'\s+', ' ', description).strip()
        
        return description[:50] if description else None
