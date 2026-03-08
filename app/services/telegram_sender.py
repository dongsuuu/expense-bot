"""
Telegram Sender Service
Telegram 응답 메시지 전송
"""

import logging
from typing import Optional

import aiohttp

from app.core.config import settings
from app.models.schemas import ExpenseExtracted, DuplicateCheckResult, NotionPageResult

logger = logging.getLogger(__name__)


class TelegramSender:
    """Telegram 발송기"""
    
    def __init__(self):
        self.api_base = settings.telegram_api_url
    
    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML"
    ) -> bool:
        """기본 메시지 전송"""
        url = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Telegram send failed: {resp.status}")
                        return False
                    return True
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False
    
    async def send_result(
        self,
        chat_id: int,
        expense: ExpenseExtracted,
        notion_result: NotionPageResult
    ):
        """처리 결과 전송"""
        
        # 성공/실패 이모지
        status_emoji = "✅" if notion_result.success else "❌"
        review_emoji = "⚠️" if expense.need_review else ""
        
        # 메시지 구성
        lines = [
            f"{status_emoji} <b>지출 기록 완료</b> {review_emoji}",
            "",
            f"🏪 <b>{expense.merchant or 'Unknown'}</b>",
            f"📅 {expense.transaction_date or '날짜 미확인'}",
            f"💰 {expense.total or 0:,} {expense.currency}",
            f"📂 {expense.category}" + (f" / {expense.subcategory}" if expense.subcategory else ""),
        ]
        
        # Notion 링크
        if notion_result.success and notion_result.url:
            lines.append(f"")
            lines.append(f"🔗 <a href='{notion_result.url}'>Notion에서 보기</a>")
        
        # 검토 필요 시 경고
        if expense.need_review:
            lines.append("")
            lines.append("⚠️ <b>검토가 필요합니다</b>")
            lines.append("상세 정보가 정확한지 확인해주세요.")
        
        # 피드백 (첫 2개만)
        if expense.feedback:
            lines.append("")
            for fb in expense.feedback[:2]:
                lines.append(f"💡 {fb}")
        
        message = "\n".join(lines)
        
        await self.send_message(chat_id, message)
    
    async def send_duplicate_warning(
        self,
        chat_id: int,
        expense: ExpenseExtracted,
        dup_result: DuplicateCheckResult
    ):
        """중복 경고 전송"""
        
        lines = [
            "⚠️ <b>중복 가능성 감지</b>",
            "",
            f"🏪 {expense.merchant or 'Unknown'}",
            f"💰 {expense.total or 0:,} {expense.currency}",
            f"📅 {expense.transaction_date or '날짜 미확인'}",
            "",
            f"유사도: {dup_result.similarity_score:.1%}",
            "",
            "이미 비슷한 지출이 기록되어 있습니다.",
            "새로 저장하지 않았습니다.",
        ]
        
        if dup_result.existing_page_id:
            notion_url = f"https://notion.so/{dup_result.existing_page_id.replace('-', '')}"
            lines.append(f"")
            lines.append(f"🔗 <a href='{notion_url}'>기존 기록 보기</a>")
        
        message = "\n".join(lines)
        
        await self.send_message(chat_id, message)
    
    async def send_error(
        self,
        chat_id: int,
        error_message: str
    ):
        """에러 메시지 전송"""
        
        lines = [
            "❌ <b>처리 중 오류 발생</b>",
            "",
            "죄송합니다. 지출 처리 중 문제가 발생했습니다.",
            "",
            f"<code>{error_message[:200]}</code>",
            "",
            "다시 시도하거나, 수동으로 입력해주세요.",
        ]
        
        message = "\n".join(lines)
        
        await self.send_message(chat_id, message)
