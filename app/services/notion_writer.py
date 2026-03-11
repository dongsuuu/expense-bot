"""
Notion Writer - Real API Integration
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import date
import aiohttp

from app.models.schemas import ExpenseExtracted, Transaction, SaveResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class NotionWriter:
    """Save to Notion database via API"""
    
    def __init__(self):
        self.token = settings.NOTION_TOKEN
        self.database_id = settings.NOTION_DATABASE_ID
        self.base_url = settings.NOTION_API_BASE
        self.version = settings.NOTION_VERSION
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json"
        }
        logger.info(f"NotionWriter initialized with DB: {self.database_id[:8]}...")
    
    async def save_expense(self, expense: ExpenseExtracted) -> SaveResult:
        """Save receipt expense to Notion"""
        try:
            payload = self._build_expense_payload(expense)
            if not payload.get("이름", {}).get("title"):
                return SaveResult(success=False, error="Missing title")
            
            result = await self._create_page(payload)
            if result.get("id"):
                logger.info(f"Expense saved: {expense.merchant}")
                return SaveResult(success=True, page_id=result["id"])
            else:
                error = result.get("message", "Unknown error")
                logger.error(f"Notion API error: {error}")
                return SaveResult(success=False, error=error)
        except Exception as e:
            logger.error(f"Expense save failed: {e}", exc_info=True)
            return SaveResult(success=False, error=str(e))
    
    async def save_transaction(self, tx: Transaction) -> SaveResult:
        """Save statement transaction to Notion"""
        try:
            if not tx.description and not tx.merchant:
                return SaveResult(success=False, error="Missing description/merchant")
            if tx.amount is None or tx.amount == 0:
                return SaveResult(success=False, error=f"Invalid amount: {tx.amount}")
            if not tx.transaction_date:
                return SaveResult(success=False, error="Missing date")
            
            payload = self._build_transaction_payload(tx)
            result = await self._create_page(payload)
            
            if result.get("id"):
                logger.info(f"Transaction saved: {tx.description[:50] if tx.description else 'N/A'}")
                return SaveResult(success=True, page_id=result["id"])
            else:
                error = result.get("message", "Unknown error")
                logger.error(f"Notion API error: {error}")
                return SaveResult(success=False, error=error)
        except Exception as e:
            logger.error(f"Transaction save failed: {e}", exc_info=True)
            return SaveResult(success=False, error=str(e))
    
    async def query_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Query recent entries from database for duplicate checking"""
        url = f"{self.base_url}/databases/{self.database_id}/query"
        payload = {"page_size": limit}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("results", [])
                    else:
                        body = await resp.text()
                        logger.error(f"Notion query error: {resp.status} - {body}")
                        return []
        except Exception as e:
            logger.error(f"Failed to query Notion: {e}")
            return []
    
    async def _create_page(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Create a page in Notion database"""
        url = f"{self.base_url}/pages"
        payload = {"parent": {"database_id": self.database_id}, "properties": properties}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                data = await resp.json()
                if resp.status not in (200, 201):
                    logger.error(f"Notion create page error: {resp.status} - {data}")
                return data
    
    def _build_expense_payload(self, expense: ExpenseExtracted) -> Dict[str, Any]:
        """Build Notion payload for receipt expense"""
        title = (expense.merchant or "Unknown")[:100]
        date_str = expense.transaction_date.isoformat() if expense.transaction_date else None
        return {
            "이름": {"title": [{"text": {"content": title}}]},
            "날짜": {"date": {"start": date_str}} if date_str else {"date": None},
            "금액": {"number": float(expense.total) if expense.total else 0},
            "카테고리": {"select": {"name": expense.category or "미분류"}},
            "세부카테고리": {"select": {"name": expense.subcategory or "미분류"}},
            "결제수단": {"select": {"name": expense.payment_method or "미확인"}},
            "통화": {"select": {"name": expense.currency or "USD"}},
            "문서타입": {"select": {"name": "영수증"}},
            "신뢰도": {"number": float(expense.confidence)},
            "검토필요": {"checkbox": bool(expense.needs_review)},
        }
    
    def _build_transaction_payload(self, tx: Transaction) -> Dict[str, Any]:
        """Build Notion payload for statement transaction"""
        title = (tx.merchant or tx.description or "Unknown")[:100]
        date_str = tx.transaction_date.isoformat() if tx.transaction_date else None
        category = self._map_transaction_category(tx)
        return {
            "이름": {"title": [{"text": {"content": title}}]},
            "날짜": {"date": {"start": date_str}} if date_str else {"date": None},
            "금액": {"number": abs(float(tx.amount)) if tx.amount else 0},
            "카테고리": {"select": {"name": category}},
            "세부카테고리": {"select": {"name": "미분류"}},
            "결제수단": {"select": {"name": self._map_payment_method(tx)}},
            "통화": {"select": {"name": tx.currency or "USD"}},
            "문서타입": {"select": {"name": "명세서"}},
            "신뢰도": {"number": 0.9},
            "검토필요": {"checkbox": False},
        }
    
    def _map_transaction_category(self, tx: Transaction) -> str:
        """Map transaction to category"""
        desc_lower = (tx.description or "").lower()
        if tx.transaction_type == "credit" or (tx.amount and tx.amount < 0):
            if "payroll" in desc_lower or "salary" in desc_lower:
                return "수입"
            if "zelle" in desc_lower:
                return "이체입금"
            return "수입"
        if any(kw in desc_lower for kw in ["restaurant", "dunkin", "food", "cafe"]):
            return "식비"
        if any(kw in desc_lower for kw in ["grocery", "market", "mart"]):
            return "식료품"
        if any(kw in desc_lower for kw in ["transport", "uber", "lyft", "taxi"]):
            return "교통"
        if any(kw in desc_lower for kw in ["shopping", "amazon"]):
            return "쇼핑"
        if "zelle" in desc_lower:
            return "이체"
        if "pos" in desc_lower or "card" in desc_lower:
            return "카드결제"
        return "기타"
    
    def _map_payment_method(self, tx: Transaction) -> str:
        """Map transaction to payment method"""
        raw = (tx.raw_type or "").lower()
        if "zelle" in raw:
            return "Zelle"
        if "ach" in raw:
            return "ACH"
        if "pos" in raw or "card" in raw:
            return "체크카드"
        return "기타"
