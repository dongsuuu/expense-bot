"""
Duplicate Detection Service - Uses NotionWriter for database access
"""
import logging
import re
from typing import Any, Optional
import aiohttp

from app.models.schemas import ExpenseExtracted, Transaction, DuplicateCheckResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class DuplicateChecker:
    """Check for duplicates using shared NotionWriter"""
    
    def __init__(self, notion_writer=None):
        self.token = settings.NOTION_TOKEN
        self.base_url = settings.NOTION_API_BASE
        self.version = settings.NOTION_VERSION
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json"
        }
        
        # Use shared NotionWriter - do NOT read settings directly
        self._notion_writer = notion_writer
        self._database_id: Optional[str] = None  # Will be set from outside
        
        if notion_writer:
            logger.info("DuplicateChecker initialized with NotionWriter")
        else:
            logger.warning("DuplicateChecker initialized without NotionWriter")
    
    def set_database_id(self, db_id: Optional[str]):
        """Set database ID from route/NotionWriter"""
        self._database_id = db_id.strip() if db_id else None
        if self._database_id:
            logger.info(f"DuplicateChecker using database: {self._database_id[:20]}...")
        else:
            logger.warning("DuplicateChecker database ID set to None")
    
    async def check(self, item: Any) -> DuplicateCheckResult:
        """Check if item is duplicate"""
        try:
            if isinstance(item, ExpenseExtracted):
                merchant = item.merchant or ""
                date = item.transaction_date
                amount = item.total
            elif isinstance(item, Transaction):
                merchant = item.merchant or item.description or ""
                date = item.transaction_date
                amount = item.amount
            else:
                merchant = getattr(item, "merchant", "") or getattr(item, "description", "")
                date = getattr(item, "transaction_date", None) or getattr(item, "date", None)
                amount = getattr(item, "total", None) or getattr(item, "amount", None)
            
            if not merchant or not date or amount is None:
                logger.debug("Skip duplicate check: missing fields")
                return DuplicateCheckResult(is_duplicate=False, confidence=0.0)
            
            # Use database ID from NotionWriter if available
            if self._notion_writer:
                db_id = await self._notion_writer._ensure_database()
            else:
                db_id = self._database_id
            
            if not db_id:
                logger.debug("No database available for duplicate check")
                return DuplicateCheckResult(is_duplicate=False, confidence=0.0)
            
            norm_merchant = self._normalize_text(merchant)
            norm_amount = round(float(amount), 2)
            date_str = date.isoformat() if date else None
            
            if not date_str:
                return DuplicateCheckResult(is_duplicate=False, confidence=0.0)
            
            recent = await self._query_recent(db_id)
            
            for entry in recent:
                entry_props = entry.get("properties", {})
                entry_title = self._extract_title(entry_props.get("이름", {}))
                entry_date = self._extract_date(entry_props.get("날짜", {}))
                entry_amount = self._extract_number(entry_props.get("금액", {}))
                
                if not entry_title or not entry_date or entry_amount is None:
                    continue
                
                entry_merchant_norm = self._normalize_text(entry_title)
                
                if (entry_merchant_norm == norm_merchant and 
                    entry_date == date_str and 
                    round(entry_amount, 2) == norm_amount):
                    logger.info(f"Duplicate found: {entry.get('id')}")
                    return DuplicateCheckResult(is_duplicate=True, matched_id=entry.get("id"), confidence=1.0)
                
                merchant_sim = self._text_similarity(entry_merchant_norm, norm_merchant)
                if merchant_sim > 0.9 and entry_date == date_str and abs(entry_amount - norm_amount) < 0.01:
                    logger.info(f"Fuzzy duplicate found: {entry.get('id')} (sim={merchant_sim})")
                    return DuplicateCheckResult(is_duplicate=True, matched_id=entry.get("id"), confidence=merchant_sim)
            
            return DuplicateCheckResult(is_duplicate=False, confidence=0.0)
            
        except Exception as e:
            logger.error(f"Duplicate check failed: {e}", exc_info=True)
            return DuplicateCheckResult(is_duplicate=False, confidence=0.0)
    
    async def check_expense(self, expense: ExpenseExtracted) -> DuplicateCheckResult:
        """Check expense for duplicates"""
        return await self.check(expense)
    
    async def check_transaction(self, tx: Transaction) -> DuplicateCheckResult:
        """Check transaction for duplicates"""
        return await self.check(tx)
    
    async def _query_recent(self, db_id: str, limit: int = 100) -> list:
        """Query recent entries from Notion"""
        if not self.token or not db_id:
            return []
        
        url = f"{self.base_url}/databases/{db_id}/query"
        payload = {
            "page_size": limit,
            "sorts": [{"timestamp": "created_time", "direction": "descending"}]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("results", [])
                    else:
                        logger.error(f"Query error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Failed to query: {e}")
            return []
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[.,/#!$%^&*;:{}=\-_`~()]', '', text)
        return text.strip()
    
    def _text_similarity(self, a: str, b: str) -> float:
        """Simple text similarity (0-1)"""
        if a == b:
            return 1.0
        if not a or not b:
            return 0.0
        set_a = set(a.split())
        set_b = set(b.split())
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)
    
    def _extract_title(self, title_prop: dict) -> Optional[str]:
        """Extract text from Notion title property"""
        try:
            titles = title_prop.get("title", [])
            if titles:
                return titles[0].get("text", {}).get("content", "")
        except:
            pass
        return None
    
    def _extract_date(self, date_prop: dict) -> Optional[str]:
        """Extract date from Notion date property"""
        try:
            return date_prop.get("date", {}).get("start")
        except:
            pass
        return None
    
    def _extract_number(self, num_prop: dict) -> Optional[float]:
        """Extract number from Notion number property"""
        try:
            return num_prop.get("number")
        except:
            pass
        return None
