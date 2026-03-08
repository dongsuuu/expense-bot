"""
Notion Writer Service
Notion에 지출 정보 저장
"""

import logging
from typing import Optional

import aiohttp

from app.core.config import settings
from app.models.schemas import ExpenseExtracted, NotionPageResult

logger = logging.getLogger(__name__)


class NotionWriter:
    """Notion 작성기"""
    
    def __init__(self):
        self.api_base = settings.NOTION_API_BASE
        self.token = settings.NOTION_TOKEN
        self.database_id = settings.NOTION_DATABASE_ID
    
    async def save(self, expense: ExpenseExtracted) -> NotionPageResult:
        """
        Notion에 지출 저장
        """
        try:
            # 1. 페이지 생성
            page_data = await self._create_page(expense)
            
            if not page_data:
                return NotionPageResult(
                    success=False,
                    error="Failed to create Notion page"
                )
            
            page_id = page_data["id"]
            
            # 2. 페이지 내용 추가 (블록)
            await self._append_blocks(page_id, expense)
            
            # 3. URL 생성
            url = f"https://notion.so/{page_id.replace('-', '')}"
            
            logger.info(f"Saved to Notion: {url}")
            
            return NotionPageResult(
                success=True,
                page_id=page_id,
                url=url
            )
            
        except Exception as e:
            logger.error(f"Notion save failed: {e}", exc_info=True)
            return NotionPageResult(
                success=False,
                error=str(e)
            )
    
    async def _create_page(self, expense: ExpenseExtracted) -> Optional[dict]:
        """Notion 페이지 생성"""
        url = f"{self.api_base}/pages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        # 날짜 포맷
        date_str = expense.transaction_date.isoformat() if expense.transaction_date else None
        
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "이름": {
                    "title": [{"text": {"content": expense.merchant or "Unknown"}}]
                },
                "날짜": {
                    "date": {"start": date_str} if date_str else None
                },
                "금액": {
                    "number": expense.total
                },
                "카테고리": {
                    "select": {"name": expense.category}
                },
                "세부카테고리": {
                    "select": {"name": expense.subcategory} if expense.subcategory else None
                },
                "결제수단": {
                    "select": {"name": expense.payment_method or "Unknown"}
                },
                "통화": {
                    "select": {"name": expense.currency or "KRW"}
                },
                "문서타입": {
                    "select": {"name": expense.document_type}
                },
                "신뢰도": {
                    "number": round(expense.confidence, 2)
                },
                "검토필요": {
                    "checkbox": expense.need_review
                }
            }
        }
        
        # None 값 제거
        payload["properties"] = {
            k: v for k, v in payload["properties"].items()
            if v is not None and (not isinstance(v, dict) or v.get("date") is not None)
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Notion API error: {resp.status} - {error_text}")
                    return None
                
                return await resp.json()
    
    async def _append_blocks(self, page_id: str, expense: ExpenseExtracted):
        """페이지에 상세 내용 추가"""
        url = f"{self.api_base}/blocks/{page_id}/children"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        blocks = []
        
        # 요약
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📊 요약"}}]
            }
        })
        
        summary = f"가맹점: {expense.merchant or 'Unknown'}\n"
        summary += f"금액: {expense.total or 0:,} {expense.currency}\n"
        summary += f"카테고리: {expense.category}"
        if expense.subcategory:
            summary += f" / {expense.subcategory}"
        
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": summary}}]
            }
        })
        
        # 품목 목록
        if expense.line_items:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "📝 품목"}}]
                }
            })
            
            for item in expense.line_items:
                item_text = f"• {item.name}"
                if item.quantity and item.unit_price:
                    item_text += f" ({item.quantity} x {item.unit_price:,})"
                if item.total_price:
                    item_text += f" = {item.total_price:,}"
                
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": item_text}}]
                    }
                })
        
        # 피드백
        if expense.feedback:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "💡 피드백"}}]
                }
            })
            
            for fb in expense.feedback:
                blocks.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [{"type": "text", "text": {"content": fb}}],
                        "icon": {"emoji": "💡"}
                    }
                })
        
        # 원본 텍스트
        if expense.raw_text:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "🔍 OCR 원본"}}]
                }
            })
            
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": expense.raw_text[:2000]}}]
                }
            })
        
        # 신뢰도
        confidence_text = f"신뢰도: {expense.confidence:.2f}"
        if expense.need_review:
            confidence_text += " ⚠️ 검토 필요"
        
        blocks.append({
            "object": "block",
            "type": "divider",
            "divider": {}
        })
        
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": confidence_text},
                    "annotations": {"italic": True}
                }]
            }
        })
        
        # 배치로 전송 (100개 제한)
        for i in range(0, len(blocks), 100):
            batch = blocks[i:i+100]
            payload = {"children": batch}
            
            async with aiohttp.ClientSession() as session:
                async with session.patch(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to append blocks: {resp.status}")
