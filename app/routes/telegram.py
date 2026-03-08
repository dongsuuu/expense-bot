"""
Telegram Webhook Handler
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from app.models.schemas import TelegramWebhook
from app.services.extraction import ExpenseExtractionService
from app.services.categorizer import Categorizer
from app.services.deduper import DuplicateChecker
from app.services.feedback import FeedbackGenerator
from app.services.notion_writer import NotionWriter
from app.services.telegram_sender import TelegramSender
from app.utils.telegram_files import TelegramFileDownloader
from app.utils.pdf_utils import PDFProcessor

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Telegram Webhook 엔드포인트
    사용자가 사진/PDF를 별낼 때 호출됨
    """
    try:
        # Webhook 데이터 파싱
        data = await request.json()
        webhook = TelegramWebhook(**data)
        
        chat_id = webhook.get_chat_id()
        file_id = webhook.get_file_id()
        caption = webhook.get_caption()
        
        if not chat_id:
            logger.warning("No chat_id in webhook")
            return {"ok": True}
        
        if not file_id:
            # 파일이 없으면 텍스트 메시지로 간주
            await TelegramSender.send_message(
                chat_id=chat_id,
                text="📎 영수증 사진 또는 PDF를 별내주세요!"
            )
            return {"ok": True}
        
        # 백그라운드에서 처리
        background_tasks.add_task(
            process_expense_document,
            chat_id=chat_id,
            file_id=file_id,
            caption=caption
        )
        
        # 즉시 응답 (Telegram은 60초 타임아웃)
        return {"ok": True, "message": "Processing started"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def process_expense_document(
    chat_id: int,
    file_id: str,
    caption: Optional[str] = None
):
    """
    지출 문서 처리 메인 로직
    """
    sender = TelegramSender()
    
    try:
        # 1. 파일 다운로드
        await sender.send_message(chat_id, "📥 파일을 다운로드하는 중...")
        
        downloader = TelegramFileDownloader()
        file_path, file_type = await downloader.download(file_id)
        
        # 2. 파일 처리 (이미지/PDF)
        await sender.send_message(chat_id, "🔍 문서를 분석하는 중...")
        
        if file_type == "pdf":
            processor = PDFProcessor()
            images = processor.convert_to_images(file_path)
            raw_text = processor.extract_text(file_path)
        else:
            images = [file_path]
            raw_text = None
        
        # 3. 지출 정보 추출
        extractor = ExpenseExtractionService()
        expense = await extractor.extract(
            images=images,
            raw_text=raw_text,
            caption=caption
        )
        
        # 4. 카테고리 분류
        categorizer = Categorizer()
        expense = categorizer.categorize(expense)
        
        # 5. 중복 검사
        deduper = DuplicateChecker()
        dup_result = await deduper.check(expense)
        
        if dup_result.is_duplicate:
            await sender.send_duplicate_warning(
                chat_id=chat_id,
                expense=expense,
                dup_result=dup_result
            )
            return
        
        # 6. 피드백 생성
        feedback_gen = FeedbackGenerator()
        expense.feedback = feedback_gen.generate(expense)
        
        # 7. Notion에 저장
        await sender.send_message(chat_id, "💾 Notion에 저장하는 중...")
        
        notion = NotionWriter()
        result = await notion.save(expense)
        
        # 8. 결과 응답
        await sender.send_result(
            chat_id=chat_id,
            expense=expense,
            notion_result=result
        )
        
    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        await sender.send_error(chat_id, str(e))
    finally:
        # 임시 파일 정리
        if 'file_path' in locals():
            downloader.cleanup(file_path)
