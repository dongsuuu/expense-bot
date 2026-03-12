"""
Notion Writer - Real API Integration with Auto-Create Database
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import date
import aiohttp

from app.models.schemas import ExpenseExtracted, Transaction, SaveResult
from app.core.config import settings

logger = logging.getLogger(__name__)


def _normalize_notion_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    if value.lower() in ("", "none", "null"):
        return None
    return value


class NotionDatabaseError(Exception):
    """Raised when Notion database is not accessible"""
    pass


class NotionWriter:
    """Save to Notion database via API with auto-create support"""
    
    def __init__(self):
        self.token = settings.NOTION_TOKEN
        self.base_url = settings.NOTION_API_BASE
        self.version = settings.NOTION_VERSION
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json"
        }
        
        self._database_id = _normalize_notion_id(settings.NOTION_DATABASE_ID)
        self._parent_page_id = _normalize_notion_id(settings.NOTION_PARENT_PAGE_ID)
        self._database_created = False
        self._database_accessible = None
        
        logger.info(
            f"NotionWriter init: database_id={'set' if self._database_id else 'empty'}, "
            f"parent_page_id={'set' if self._parent_page_id else 'empty'}"
        )
    
    async def _is_database_accessible(self, db_id: str) -> bool:
        url = f"{self.base_url}/databases/{db_id}/query"
        payload = {"page_size": 1}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    body = await resp.text()
                    logger.warning(f"Database accessibility check failed: {resp.status} - {body}")
                    return False
        except Exception as e:
            logger.error(f"Database accessibility check error: {e}")
            return False
    
    async def _ensure_database(self) -> Optional[str]:
        if self._database_id:
            accessible = await self._is_database_accessible(self._database_id)
            if accessible:
                logger.info(f"Using existing Notion database: {self._database_id}")
                return self._database_id
            logger.warning(f"Configured database is invalid/inaccessible: {self._database_id}")
            self._database_id = None
            self._database_accessible = False
        
        if self._database_created and self._database_id:
            return self._database_id
        
        if not self._parent_page_id:
            logger.error("No valid NOTION_PARENT_PAGE_ID available for auto-create")
            return None
        
        logger.info("Attempting Notion database auto-creation under parent page")
        try:
            db_id = await self._create_database()
            if db_id:
                self._database_id = db_id
                self._database_created = True
                self._database_accessible = True
                logger.info(f"Auto-created database: {db_id}")
                return db_id
            logger.error("Failed to auto-create database")
            return None
        except Exception as e:
            logger.error(f"Database creation failed: {e}", exc_info=True)
            return None
    
    async def _create_database(self) -> Optional[str]:
        """Create Transactions database under parent page"""
        url = f"{self.base_url}/databases"
        
        payload = {
            "parent": {"page_id": self._parent_page_id},
            "title": [{"type": "text", "text": {"content": "Transactions"}}],
            "properties": {
                "이름": {"title": {}},
                "날짜": {"date": {}},
                "금액": {"number": {"format": "dollar"}},
                "카테고리": {
                    "select": {
                        "options": [
                            {"name": "식비", "color": "red"},
                            {"name": "식료품", "color": "orange"},
                            {"name": "교통", "color": "yellow"},
                            {"name": "쇼핑", "color": "green"},
                            {"name": "여가", "color": "blue"},
                            {"name": "공과금", "color": "purple"},
                            {"name": "의료", "color": "pink"},
                            {"name": "수입", "color": "gray"},
                            {"name": "이체", "color": "brown"},
                            {"name": "이체입금", "color": "brown"},
                            {"name": "카드결제", "color": "default"},
                            {"name": "기타", "color": "default"},
                            {"name": "미분류", "color": "default"},
                        ]
                    }
                },
                "세부카테고리": {
                    "select": {
                        "options": [
                            {"name": "외식", "color": "default"},
                            {"name": "마트", "color": "default"},
                            {"name": "대중교통", "color": "default"},
                            {"name": "일반", "color": "default"},
                            {"name": "구독", "color": "default"},
                            {"name": "기본", "color": "default"},
                            {"name": "미분류", "color": "default"},
                        ]
                    }
                },
                "결제수단": {
                    "select": {
                        "options": [
                            {"name": "카드", "color": "blue"},
                            {"name": "현금", "color": "green"},
                            {"name": "Zelle", "color": "yellow"},
                            {"name": "ACH", "color": "orange"},
                            {"name": "체크카드", "color": "purple"},
                            {"name": "미확인", "color": "gray"},
                            {"name": "기타", "color": "default"},
                        ]
                    }
                },
                "통화": {
                    "select": {
                        "options": [
                            {"name": "USD", "color": "blue"},
                            {"name": "KRW", "color": "red"},
                            {"name": "EUR", "color": "green"},
                            {"name": "JPY", "color": "yellow"},
                        ]
                    }
                },
                "문서타입": {
                    "select": {
                        "options": [
                            {"name": "영수증", "color": "blue"},
                            {"name": "명세서", "color": "green"},
                        ]
                    }
                },
                "신뢰도": {"number": {"format": "percent"}},
                "검토필요": {"checkbox": {}},
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                data = await resp.json()
                
                if resp.status in (200, 201):
                    db_id = data.get("id")
                    logger.info(f"Successfully created database: {db_id}")
                    return db_id
                elif resp.status == 404:
                    logger.error(f"Parent page not found or not accessible: {self._parent_page_id}")
                    return None
                else:
                    logger.error(f"Failed to create database: {resp.status} - {data.get('message', 'Unknown error')}")
                    return None
    
    async def save_expense(self, expense: ExpenseExtracted) -> SaveResult:
        """Save receipt expense to Notion"""
        db_id = await self._ensure_database()
        if not db_id:
            return SaveResult(
                success=False,
                error="NO_DATABASE_AVAILABLE",
                error_type="config"
            )
        
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
        db_id = await self._ensure_database()
        if not db_id:
            return SaveResult(
                success=False,
                error="NO_DATABASE_AVAILABLE",
                error_type="config"
            )
        
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
        db_id = await self._ensure_database()
        if not db_id:
            return []
        
        url = f"{self.base_url}/databases/{db_id}/query"
        payload = {"page_size": limit}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("results", [])
                    else:
                        logger.error(f"Notion query error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Failed to query Notion: {e}")
            return []
    
    async def _create_page(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Create a page in Notion database"""
        db_id = await self._ensure_database()
        if not db_id:
            return {"code": "NO_DATABASE", "message": "No database available"}
        
        url = f"{self.base_url}/pages"
        payload = {"parent": {"database_id": db_id}, "properties": properties}
        
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
