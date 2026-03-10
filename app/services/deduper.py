"""
Duplicate Detection Service - Safe Implementation
"""

import hashlib
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DuplicateChecker:
    """중복 검사기 - 안전한 구현"""
    
    def __init__(self, notion_client=None):
        self.notion_client = notion_client
        logger.info("DuplicateChecker initialized")
    
    async def check(self, item: Any) -> Dict[str, Optional[Any]]:
        """
        Main duplicate-check method.
        Returns: {"is_duplicate": bool, "matched_id": str | None}
        """
        try:
            merchant = getattr(item, "merchant", None) or ""
            date = getattr(item, "transaction_date", None) or getattr(item, "date", None)
            total = getattr(item, "total", None) or getattr(item, "amount", None)
            
            logger.debug(f"Checking duplicate: merchant={merchant}, date={date}, total={total}")
            
            # 핵심 필드 없으면 스킵
            if not merchant or not date or total in (None, 0, 0.0):
                logger.info("Not enough fields for duplicate checking; skipping.")
                return {"is_duplicate": False, "matched_id": None}
            
            # TODO: 실제 Notion/database 쿼리로 대체
            normalized_key = f"{str(merchant).strip().lower()}|{date}|{float(total):.2f}"
            key_hash = hashlib.sha256(normalized_key.encode()).hexdigest()
            logger.info(f"Duplicate check key: {key_hash[:12]} (not checking actual DB)")
            
            # 지금은 항상 중복 아님으로 (실제 구현 시 DB 조회)
            return {"is_duplicate": False, "matched_id": None}
            
        except Exception as e:
            logger.error(f"Duplicate check failed: {e}", exc_info=True)
            return {"is_duplicate": False, "matched_id": None}
    
    async def check_expense(self, expense: Any) -> Dict[str, Optional[Any]]:
        """Backward-compatible alias"""
        logger.debug("check_expense called (alias to check)")
        return await self.check(expense)
    
    async def check_transaction(self, tx: Any) -> Dict[str, Optional[Any]]:
        """거래 중복 검사"""
        logger.debug("check_transaction called")
        return await self.check(tx)
