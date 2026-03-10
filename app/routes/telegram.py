"""
Telegram Webhook Handler - Safe Implementation
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from app.models.schemas import TelegramWebhook
from app.services.extraction import ExpenseExtractionService
from app.services.categorizer import Categorizer
from app.services.deduper import DuplicateChecker
from app.services.notion_writer import NotionWriter
from app.services.telegram_sender import TelegramSender
from app.utils.telegram_files import TelegramFileDownloader
from app.utils.pdf_utils import PDFProcessor

logger = logging.getLogger(__name__)
router = APIRouter()


def is_valid_expense(expense) -> bool:
    """지출 유효성 검사"""
    merchant = getattr(expense, "merchant", None)
    total = getattr(expense, "total", None)
    date = getattr(expense, "transaction_date", None)
    
    # 핵심 필드 모두 없으면 invalid
    if (not merchant or merchant == "Unknown") and (not date) and (not total or float(total) == 0):
        return False
    return True


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Telegram Webhook - 안전한 구현"""
    try:
        data = await request.json()
        webhook = TelegramWebhook(**data)
        
        chat_id = webhook.get_chat_id()
        file_id = webhook.get_file_id()
        caption = webhook.get_caption()
        filename = webhook.get_document_filename()
        
        if not chat_id:
            return {"ok": True}
        
        if not file_id:
            sender = TelegramSender()
            await sender.send_message(chat_id, "📎 파일을 별내주세요!")
            return {"ok": True}
        
        # 파일 다운로드
        downloader = TelegramFileDownloader()
        file_path, file_type = await downloader.download(file_id)
        
        # PDF 텍스트 읽기 (감지용)
        pdf_text = None
        if file_type == 'pdf':
            try:
                processor = PDFProcessor()
                pdf_text = processor.extract_text(file_path)
            except:
                pass
        
        # 문서 타입 감지
        is_statement = False
        if pdf_text and 'chase' in pdf_text.lower() and 'total checking' in pdf_text.lower():
            is_statement = True
        elif filename and any(kw in filename.lower() for kw in ['statement', 'chase', 'transactions']):
            is_statement = True
        
        logger.info(f"Document type: {'statement' if is_statement else 'receipt'}")
        
        # 라우팅
        if is_statement:
            background_tasks.add_task(
                process_statement,
                chat_id=chat_id,
                file_path=file_path,
                filename=filename
            )
        else:
            background_tasks.add_task(
                process_receipt,
                chat_id=chat_id,
                file_path=file_path,
                filename=filename,
                caption=caption
            )
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def process_receipt(
    chat_id: int,
    file_path: str,
    filename: str,
    caption: Optional[str] = None
):
    """영수증 처리 - 안전한 구현"""
    sender = TelegramSender()
    
    try:
        await sender.send_message(chat_id, "🔍 문서를 분석하는 중...")
        
        # 추출
        extractor = ExpenseExtractionService()
        
        file_type = 'pdf' if file_path.endswith('.pdf') else 'image'
        if file_type == "pdf":
            processor = PDFProcessor()
            raw_text = processor.extract_text(file_path)
            images = processor.convert_to_images(file_path)
        else:
            raw_text = None
            images = [file_path]
        
        expense = await extractor.extract_receipt(
            images=images,
            raw_text=raw_text,
            caption=caption
        )
        
        # Validation: 유효하지 않으면 저장 안 함
        if not is_valid_expense(expense):
            logger.warning(f"Invalid expense: merchant={expense.merchant}, total={expense.total}")
            await sender.send_message(
                chat_id,
                "❌ 문서에서 유효한 지출 정보를 추출하지 못했습니다.\n"
                "PDF 명세서인 경우 파일명에 'statement'를 포함해주세요."
            )
            return
        
        # 카테고리 분류
        categorizer = Categorizer()
        expense = categorizer.categorize(expense)
        
        # 중복 검사 (try/except로 보호)
        try:
            deduper = DuplicateChecker()
            dup_result = await deduper.check(expense)  # check_expense -> check
            is_duplicate = dup_result.get("is_duplicate", False)
        except Exception as e:
            logger.error(f"Duplicate check failed: {e}")
            is_duplicate = False
        
        if is_duplicate:
            await sender.send_message(
                chat_id,
                "⚠️ 비슷한 지출이 이미 저장된 것 같아요. 중복 저장은 걄뛰었습니다."
            )
            return
        
        # 저장
        await sender.send_message(chat_id, "💾 Notion에 저장하는 중...")
        notion = NotionWriter()
        result = await notion.save_expense(expense)
        
        if result.success:
            await sender.send_message(
                chat_id,
                f"✅ 지출 기록 완료\n\n"
                f"🏪 {expense.merchant or '미확인'}\n"
                f"📅 {expense.transaction_date or '날짜 미확인'}\n"
                f"💰 {expense.total or 0} {expense.currency}"
            )
        else:
            await sender.send_message(chat_id, "❌ 저장에 실패했습니다.")
        
    except Exception as e:
        logger.error(f"Receipt processing error: {e}", exc_info=True)
        await sender.send_message(chat_id, "❌ 처리 중 오류가 발생했습니다.")
    finally:
        # cleanup
        pass


async def process_statement(
    chat_id: int,
    file_path: str,
    filename: str
):
    """명세서 처리"""
    sender = TelegramSender()
    
    try:
        await sender.send_message(chat_id, "📄 명세서를 분석하는 중...")
        
        processor = PDFProcessor()
        pdf_text = processor.extract_text(file_path)
        
        if not pdf_text:
            await sender.send_message(chat_id, "❌ PDF에서 텍스트를 읽을 수 없습니다.")
            return
        
        extractor = ExpenseExtractionService()
        statement = await extractor.extract_statement(pdf_text, filename)
        
        if not statement.transactions:
            await sender.send_message(chat_id, "❌ 거래 내역을 찾을 수 없습니다.")
            return
        
        # 유효한 거래만
        valid_txs = [tx for tx in statement.transactions if tx.amount != 0]
        
        await sender.send_message(
            chat_id,
            f"💾 {len(valid_txs)}개 거래를 저장하는 중..."
        )
        
        # 저장
        notion = NotionWriter()
        saved = 0
        for tx in valid_txs:
            try:
                result = await notion.save_transaction(tx)
                if result.success:
                    saved += 1
            except:
                pass
        
        await sender.send_message(
            chat_id,
            f"✅ {saved}/{len(valid_txs)}개 거래 저장 완료"
        )
        
    except Exception as e:
        logger.error(f"Statement processing error: {e}", exc_info=True)
        await sender.send_message(chat_id, "❌ 처리 중 오류가 발생했습니다.")
