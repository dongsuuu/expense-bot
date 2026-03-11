"""
Expense Extraction Service - Robust Implementation
"""
import logging
import re
from datetime import datetime
from typing import List, Optional

from app.models.schemas import ExpenseExtracted, Transaction

logger = logging.getLogger(__name__)


class ExpenseExtractionService:
    """Extract expenses from receipts and statements"""
    
    MONTH_MAP = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    async def extract_receipt(self, images: List[str], raw_text: Optional[str] = None, 
                              caption: Optional[str] = None) -> ExpenseExtracted:
        """Extract expense from receipt images/text"""
        expense = ExpenseExtracted()
        
        if raw_text:
            expense = self._parse_receipt_text(raw_text)
        
        if caption:
            if not expense.merchant:
                expense.merchant = caption.strip()[:50]
        
        return expense
    
    def _parse_receipt_text(self, text: str) -> ExpenseExtracted:
        """Parse receipt text"""
        expense = ExpenseExtracted()
        
        amounts = re.findall(r'\$?([\d,]+\.\d{2})', text)
        if amounts:
            try:
                parsed = [float(a.replace(',', '')) for a in amounts]
                expense.total = max(parsed)
            except Exception as e:
                logger.warning(f"Amount parsing failed: {e}")
        
        date_patterns = [
            r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
            r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    if len(match.group(1)) == 4:
                        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    else:
                        month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    expense.transaction_date = datetime(year, month, day).date()
                    break
                except Exception as e:
                    logger.warning(f"Date parsing failed: {e}")
        
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            for line in lines[:5]:
                skip_words = ['receipt', 'invoice', 'order', 'date', 'total']
                if not any(sw in line.lower() for sw in skip_words):
                    expense.merchant = line[:50]
                    break
            if not expense.merchant:
                expense.merchant = lines[0][:50]
        
        return expense
    
    async def extract_statement(self, pdf_text: str, filename: str = "") -> List[Transaction]:
        """Extract transactions from statement"""
        logger.info(f"Extracting statement: {len(pdf_text)} chars, filename={filename}")
        
        if 'chase' in pdf_text.lower() or 'zelle' in pdf_text.lower():
            return self.parse_chase_statement(pdf_text)
        
        return self.parse_chase_statement(pdf_text)
    
    def parse_chase_statement(self, text: str) -> List[Transaction]:
        """Parse Chase statement - robust multiline parser"""
        logger.info(f"Parsing Chase statement: {len(text)} chars")
        
        text = text.replace('−', '-').replace('—', '-').replace('–', '-')
        
        lines = text.split('\n')
        transactions = []
        
        current_date = None
        description_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if self._is_chase_noise(line):
                continue
            
            date_match = re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})(.*)$', 
                                  line, re.IGNORECASE)
            
            if date_match:
                if current_date and description_lines:
                    tx = self._build_transaction(current_date, description_lines)
                    if tx and tx.amount != 0:
                        transactions.append(tx)
                    description_lines = []
                
                try:
                    month_str = date_match.group(1).lower()[:3]
                    month = self.MONTH_MAP.get(month_str, 1)
                    day = int(date_match.group(2))
                    year = int(date_match.group(3))
                    current_date = datetime(year, month, day).date()
                    
                    remaining = date_match.group(4).strip()
                    if remaining:
                        description_lines.append(remaining)
                        
                except Exception as e:
                    logger.warning(f"Date parse error: {e}")
            
            elif current_date:
                tx = self._try_complete_transaction(current_date, description_lines + [line])
                if tx:
                    transactions.append(tx)
                    description_lines = []
                else:
                    description_lines.append(line)
        
        if current_date and description_lines:
            tx = self._build_transaction(current_date, description_lines)
            if tx and tx.amount != 0:
                transactions.append(tx)
        
        logger.info(f"Parsed {len(transactions)} transactions")
        return transactions
    
    def _is_chase_noise(self, line: str) -> bool:
        """Check if line is Chase header/footer noise"""
        noise_patterns = [
            r'^printed from chase',
            r'^total checking',
            r'^chase\.com',
            r'^https://',
            r'^date\s+description',
            r'^page\s+\d+\s+of\s+\d+',
            r'^opening balance',
            r'^closing balance',
            r'^pending$',
            r'^transactions showing',
        ]
        
        line_lower = line.lower()
        for pattern in noise_patterns:
            if re.match(pattern, line_lower):
                return True
        return False
    
    def _try_complete_transaction(self, date: datetime.date, lines: List[str]) -> Optional[Transaction]:
        """Try to build complete transaction from lines"""
        full_text = ' '.join(lines)
        
        amount_match = re.search(r'(-?\$?[\d,]+\.\d{2})\s+(-?\$?[\d,]+\.\d{2})\s*$', full_text)
        
        if not amount_match:
            return None
        
        try:
            amount_str = amount_match.group(1).replace(',', '').replace('$', '')
            balance_str = amount_match.group(2).replace(',', '').replace('$', '')
            
            amount = float(amount_str)
            balance = float(balance_str)
            
            text_upper = full_text.upper()
            raw_type = None
            is_debit = False
            
            if 'ZELLE' in text_upper:
                raw_type = 'Zelle'
                is_debit = amount < 0 or 'DEBIT' in text_upper or 'payment to' in full_text.lower()
            elif 'POS' in text_upper or 'CARD' in text_upper:
                raw_type = 'Card'
                is_debit = True
            elif 'ACH' in text_upper:
                raw_type = 'ACH'
                is_debit = amount < 0
            
            desc_end = amount_match.start()
            description = full_text[:desc_end].strip()
            description = re.sub(r'\s+', ' ', description)
            
            merchant = self._extract_merchant(description, raw_type)
            
            return Transaction(
                transaction_date=date,
                description=description[:200],
                merchant=merchant,
                amount=abs(amount),
                currency='USD',
                transaction_type='debit' if is_debit else 'credit',
                raw_type=raw_type,
                balance=balance
            )
            
        except Exception as e:
            logger.warning(f"Transaction build failed: {e}")
            return None
    
    def _build_transaction(self, date: datetime.date, lines: List[str]) -> Optional[Transaction]:
        """Build transaction from accumulated lines"""
        return self._try_complete_transaction(date, lines)
    
    def _extract_merchant(self, description: str, raw_type: Optional[str]) -> Optional[str]:
        """Extract merchant name from description"""
        if not description:
            return None
        
        prefixes = [
            'POS DEBIT', 'POS', 'ZELLE PAYMENT TO', 'ZELLE TO', 
            'ZELLE FROM', 'ACH DEBIT', 'ACH CREDIT', 'ACH'
        ]
        
        desc_upper = description.upper()
        for prefix in prefixes:
            if desc_upper.startswith(prefix):
                description = description[len(prefix):].strip()
                break
        
        description = re.sub(r'\b\d{6,}\b', '', description)
        description = re.sub(r'\b\d{3}-\d{3}-\d{4}\b', '', description)
        description = re.sub(r'\s+', ' ', description).strip()
        
        return description[:50] if description else None
