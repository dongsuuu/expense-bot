"""
Duplicate Detection Service
중복 지출 검사
"""

import hashlib
import logging
from datetime import timedelta
from typing import Optional

import aiohttp

from app.core.config import settings
from app.models.schemas import ExpenseExtracted, DuplicateCheckResult

logger = logging.getLogger(__name__)


class DuplicateChecker:
    """중복 검사기"""
    
    def __init__(self):
        self.notion_api_base = settings.NOTION_API_BASE
        self.notion_token = settings.NOTION_TOKEN
        self.database_id = settings.NOTION_DATABASE_ID
    
    async def check(self, expense: ExpenseExtracted) -> DuplicateCheckResult:
        """
        중복 여부 검사
        """
        if not expense.merchant or not expense.total:
            return DuplicateCheckResult(
                is_duplicate=False,
                similarity_score=0.0,
                message="Insufficient data for duplicate check"
            )
        
        # 1. 해시 기반 빠른 검사
        content_hash = self._compute_hash(expense)
        
        # 2. Notion에서 최근 데이터 조회
        recent_entries = await self._fetch_recent_entries(days=7)
        
        # 3. 유사도 계산
        for entry in recent_entries:
            similarity = self._calculate_similarity(expense, entry)
            
            if similarity >= settings.DUPLICATE_THRESHOLD:
                return DuplicateCheckResult(
                    is_duplicate=True,
                    similarity_score=similarity,
                    existing_page_id=entry.get("id"),
                    message=f"Possible duplicate detected (similarity: {similarity:.2f})"
                )
        
        return DuplicateCheckResult(
            is_duplicate=False,
            similarity_score=0.0,
            message="No duplicate found"
        )
    
    def _compute_hash(self, expense: ExpenseExtracted) -> str:
        """내용 해시 계산"""
        content = f"{expense.merchant or ''}|{expense.total or 0}|{expense.transaction_date or ''}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def _fetch_recent_entries(self, days: int = 7) -> list:
        """Notion에서 최근 지출 조회"""
        try:
            url = f"{self.notion_api_base}/databases/{self.database_id}/query"
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }
            
            # 최근 7일 필터
            from datetime import datetime, timedelta
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            payload = {
                "filter": {
                    "property": "날짜",
                    "date": {
                        "on_or_after": cutoff_date
                    }
                },
                "page_size": 100
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Notion query failed: {resp.status}")
                        return []
                    
                    data = await resp.json()
                    return data.get("results", [])
                    
        except Exception as e:
            logger.error(f"Fetch recent entries failed: {e}")
            return []
    
    def _calculate_similarity(self, expense: ExpenseExtracted, entry: dict) -> float:
        """유사도 계산 (0-1)"""
        score = 0.0
        weights = 0.0
        
        properties = entry.get("properties", {})
        
        # 가맹점 비교 (가중치 0.4)
        entry_merchant = self._get_title(properties.get("이름", {}))
        if expense.merchant and entry_merchant:
            weights += 0.4
            if expense.merchant.lower() in entry_merchant.lower() or \
               entry_merchant.lower() in expense.merchant.lower():
                score += 0.4
        
        # 금액 비교 (가중치 0.35)
        entry_amount = self._get_number(properties.get("금액", {}))
        if expense.total and entry_amount:
            weights += 0.35
            # 금액이 정확히 같으면 full score, ±10% 차이면 partial
            diff_ratio = abs(expense.total - entry_amount) / max(expense.total, entry_amount)
            if diff_ratio < 0.01:  # 1% 이내
                score += 0.35
            elif diff_ratio < 0.1:  # 10% 이내
                score += 0.35 * (1 - diff_ratio)
        
        # 날짜 비교 (가중치 0.25)
        entry_date = self._get_date(properties.get("날짜", {}))
        if expense.transaction_date and entry_date:
            weights += 0.25
            from datetime import datetime
            try:
                d1 = datetime.strptime(str(expense.transaction_date), "%Y-%m-%d")
                d2 = datetime.strptime(entry_date, "%Y-%m-%d")
                day_diff = abs((d1 - d2).days)
                
                if day_diff == 0:
                    score += 0.25
                elif day_diff <= 1:
                    score += 0.15
                elif day_diff <= 3:
                    score += 0.05
            except:
                pass
        
        # 정규화
        if weights == 0:
            return 0.0
        
        return score / weights
    
    def _get_title(self, prop: dict) -> Optional[str]:
        """Notion title 속성 추출"""
        titles = prop.get("title", [])
        if titles:
            return titles[0].get("text", {}).get("content", "")
        return None
    
    def _get_number(self, prop: dict) -> Optional[float]:
        """Notion number 속성 추출"""
        return prop.get("number")
    
    def _get_date(self, prop: dict) -> Optional[str]:
        """Notion date 속성 추출"""
        date_obj = prop.get("date")
        if date_obj:
            return date_obj.get("start")
        return None
