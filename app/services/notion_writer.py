"""
Notion Writer - with detailed logging and statement support
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import date

from app.models.schemas import ExpenseExtracted, Transaction, SaveResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class NotionWriter:
    """Notion 저장기 - 상세 로깅"""
    
    def __init__(self):
        self.database_id = settings.NOTION_DATABASE_ID
        self.client = None  # TODO: initialize Notion client
        logger.info(f"NotionWriter initialized with DB: {self.database_id}")
    
    async def save_expense(self, expense: ExpenseExtracted) -> SaveResult:
        """영수증 저장"""
        try:
            payload = self._build_expense_payload(expense)
            logger.debug(f"Expense payload: {payload}")
            
            # TODO: actual Notion API call
            # result = await self.client.pages.create(parent={"database_id": self.database_id}, properties=payload)
            
            logger.info(f"Expense saved: {expense.merchant}, {expense.total}")
            return SaveResult(success=True, page_id="mock_page_id")
            
        except Exception as e:
            logger.error(f"Expense save failed: {e}", exc_info=True)
            return SaveResult(success=False, error=str(e))
    
    async def save_transaction(self, tx: Transaction) -> SaveResult:
        """거래 저장 - 상세 로깅"""
        logger.info(f"Saving transaction: {tx.description[:50] if tx.description else 'N/A'}, amount={tx.amount}")
        
        try:
            # 1. Validate transaction
            validation_errors = self._validate_transaction(tx)
            if validation_errors:
                logger.error(f"Transaction validation failed: {validation_errors}")
                return SaveResult(success=False, error=f"Validation: {', '.join(validation_errors)}")
            
            # 2. Normalize to expense format
            normalized = self._normalize_transaction(tx)
            logger.debug(f"Normalized: merchant={normalized.get('merchant')}, amount={normalized.get('amount')}, date={normalized.get('date')}")
            
            # 3. Build payload
            payload = self._build_transaction_payload(normalized)
            logger.debug(f"Notion payload: {payload}")
            
            # 4. Validate payload
            payload_errors = self._validate_payload(payload)
            if payload_errors:
                logger.error(f"Payload validation failed: {payload_errors}")
                return SaveResult(success=False, error=f"Payload: {', '.join(payload_errors)}")
            
            # 5. Save to Notion
            # TODO: actual API call
            # result = await self.client.pages.create(
            #     parent={"database_id": self.database_id},
            #     properties=payload
            # )
            
            logger.info(f"Transaction saved successfully: {normalized.get('merchant')}, {normalized.get('amount')}")
            return SaveResult(success=True, page_id="mock_page_id")
            
        except Exception as e:
            logger.error(f"Transaction save failed: {e}", exc_info=True)
            return SaveResult(success=False, error=str(e))
    
    def _validate_transaction(self, tx: Transaction) -> List[str]:
        """거래 유효성 검사"""
        errors = []
        
        if not tx.description:
            errors.append("missing description")
        
        if tx.amount is None or tx.amount == 0:
            errors.append(f"invalid amount: {tx.amount}")
        
        if not tx.transaction_date:
            errors.append("missing date")
        
        return errors
    
    def _normalize_transaction(self, tx: Transaction) -> Dict[str, Any]:
        """Transaction -> Expense 형식 정규화"""
        normalized = {
            'merchant': tx.merchant or tx.description or 'Unknown',
            'amount': abs(float(tx.amount)) if tx.amount else 0,
            'date': tx.transaction_date,
            'currency': tx.currency or 'USD',
            'category': self._map_transaction_category(tx),
            'subcategory': None,
            'payment_method': self._map_payment_method(tx),
            'description': tx.description,
            'raw_type': tx.raw_type,
        }
        
        logger.debug(f"Normalized transaction: {normalized}")
        return normalized
    
    def _map_transaction_category(self, tx: Transaction) -> str:
        """거래 카테고리 매핑"""
        desc_lower = (tx.description or '').lower()
        
        # Income
        if tx.transaction_type == 'credit' or tx.amount > 0:
            if 'payroll' in desc_lower or 'salary' in desc_lower:
                return '수입'
            if 'zelle' in desc_lower and tx.amount > 0:
                return '이체입금'
            return '수입'
        
        # Expense categories
        if 'restaurant' in desc_lower or 'dunkin' in desc_lower or 'food' in desc_lower:
            return '식비'
        if 'grocery' in desc_lower or 'market' in desc_lower:
            return '식료품'
        if 'transport' in desc_lower or 'uber' in desc_lower or 'lyft' in desc_lower:
            return '교통'
        if 'shopping' in desc_lower or 'amazon' in desc_lower:
            return '쇼핑'
        
        # Default
        if 'zelle' in desc_lower:
            return '이체'
        if 'pos' in desc_lower or 'card' in desc_lower:
            return '카드결제'
        
        return '기타'
    
    def _map_payment_method(self, tx: Transaction) -> str:
        """결제수단 매핑"""
        raw = (tx.raw_type or '').lower()
        
        if 'zelle' in raw:
            return 'Zelle'
        if 'ach' in raw:
            return 'ACH'
        if 'pos' in raw or 'card' in raw:
            return '체크카드'
        
        return '기타'
    
    def _validate_payload(self, payload: Dict[str, Any]) -> List[str]:
        """Notion payload 유효성 검사"""
        errors = []
        
        # Check required fields
        if not payload.get('이름', {}).get('title'):
            errors.append("missing 이름(title)")
        
        if not payload.get('날짜', {}).get('date', {}).get('start'):
            errors.append("missing 날짜(date)")
        
        amount = payload.get('금액', {}).get('number')
        if amount is None or amount == 0:
            errors.append(f"invalid 금액(number): {amount}")
        
        return errors
    
    def _build_expense_payload(self, expense: ExpenseExtracted) -> Dict[str, Any]:
        """영수증 payload 빌드"""
        return {
            "이름": {"title": [{"text": {"content": expense.merchant or "Unknown"}}]},
            "날짜": {"date": {"start": str(expense.transaction_date)}},
            "금액": {"number": float(expense.total) if expense.total else 0},
            "카테고리": {"select": {"name": expense.category or "미분류"}},
            "세부카테고리": {"select": {"name": expense.subcategory or "미분류"}},
            "결제수단": {"select": {"name": expense.payment_method or "미확인"}},
            "통화": {"select": {"name": expense.currency or "USD"}},
            "문서타입": {"select": {"name": "영수증"}},
            "신뢰도": {"number": getattr(expense, 'confidence', 0.8)},
            "검토필요": {"checkbox": getattr(expense, 'needs_review', False)},
        }
    
    def _build_transaction_payload(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        """거래 payload 빌드"""
        date_str = normalized.get('date')
        if isinstance(date_str, date):
            date_str = date_str.isoformat()
        
        return {
            "이름": {"title": [{"text": {"content": normalized.get('merchant', 'Unknown')[:100]}}]},
            "날짜": {"date": {"start": date_str}},
            "금액": {"number": float(normalized.get('amount', 0))},
            "카테고리": {"select": {"name": normalized.get('category', '미분류')}},
            "세부카테고리": {"select": {"name": normalized.get('subcategory', '미분류') or '미분류'}},
            "결제수단": {"select": {"name": normalized.get('payment_method', '미확인')}},
            "통화": {"select": {"name": normalized.get('currency', 'USD')}},
            "문서타입": {"select": {"name": "명세서"}},
            "신뢰도": {"number": 0.9},
            "검토필요": {"checkbox": False},
        }
