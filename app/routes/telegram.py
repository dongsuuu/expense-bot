"""
Telegram Webhook Handler - Dual Mode with Proper Routing
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


def detect_document_type(filename: Optional[str], caption: Optional[str], file_type: str) -> str:
    """
    문서 타입 감지 - 명확한 분리
    Returns: 'receipt', 'statement', 'unknown'
    """
    filename_lower = (filename or "").lower()
    caption_lower = (caption or "").lower()
    
    # Statement indicators (strong)
    statement_keywords = [
        'statement', 'transactions', 'activity', 'checking', 'savings',
        'account', 'chase', 'bank', 'card', 'monthly', 'period'
    ]
    
    for keyword in statement_keywords:
        if keyword in filename_lower:
            logger.info(f"Detected statement by filename: {keyword}")
            return 'statement'
    
    # Caption hint
    if any(kw in caption_lower for kw in ['명세서', 'statement', '거래내역', 'transactions', '은행']):
        logger.info("Detected statement by caption")
        return 'statement'
    
    # PDF without strong receipt indicators -> assume statement for bank PDFs
    if file_type == 'pdf':
        # Check if it's likely a bank PDF
        bank_indicators = ['chase', 'bank', 'credit', 'debit', 'total checking']
        if any(ind in filename_lower for ind in bank_indicators):
            logger.info("Detected likely bank statement PDF")
            return 'statement'
    
    # Image files -> receipt
    if file_type in ['image', 'jpg', 'jpeg', 'png']:
        return 'receipt'
    
    # Default to receipt for safety (but will validate later)
    return 'receipt'


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Telegram Webhook - 명확한 라우팅"""
    try:
        data = await request.json()
        webhook = TelegramWebhook(**data)
        
        chat_id = webhook.get_chat_id()
        file_id = webhook.get_file_id()
        caption = webhook.get_caption()
        filename = webhook.get_document_filename()
        
        if not chat_id:
            logger.warning("No chat_id in webhook")
            return {"ok": True}
        
        if not file_id:
            sender = TelegramSender()
            await sender.send_message(
                chat_id=chat_id,
                text="📎 영수증 사진 또는 PDF 명세서를 별내주세요!"
            )
            return {"ok": True}
        
        # 파일 다운로드 먼저 (타입 확인용)
        downloader = TelegramFileDownloader()
        file_path, file_type = await downloader.download(file_id)
        
        # 문서 타입 감지
        doc_type = detect_document_type(filename, caption, file_type)
        
        logger.info(f"Document type detected: {doc_type} (file: {filename}, type: {file_type})")
        
        # 명확한 라우팅
        if doc_type == 'statement':
            background_tasks.add_task(
                process_statement_document,
                chat_id=chat_id,
                file_path=file_path,
                filename=filename
            )
        else:
            background_tasks.add_task(
                process_receipt_document,
                chat_id=chat_id,
                file_path=file_path,
                caption=caption
            )
        
        return {"ok": True, "message": f"Processing {doc_type}"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def process_receipt_document(
    chat_id: int,
    file_path: str,
    caption: Optional[str] = None
):
    """영수증 처리 - 단일 경로"""
    sender = TelegramSender()
    downloader = TelegramFileDownloader()
    
    try:
        await sender.send_message(chat_id, "📥 영수증을 분석하는 중...")
        
        # 파일 타입 확인
        file_type = 'pdf' if file_path.endswith('.pdf') else 'image'
        
        if file_type == "pdf":
            processor = PDFProcessor()
            images = processor.convert_to_images(file_path)
            raw_text = processor.extract_text(file_path)
        else:
            images = [file_path]
            raw_text = None
        
        # 영수증 추출
        extractor = ExpenseExtractionService()
        expense = await extractor.extract_receipt(
            images=images,
            raw_text=raw_text,
            caption=caption
        )
        
        # Validation: 실패하면 저장 안 함
        if expense.need_review or not expense.merchant or expense.total is None:
            logger.warning(f"Receipt extraction weak: merchant={expense.merchant}, total={expense.total}")
            await sender.send_extraction_failed(
                chat_id=chat_id,
                reason="영수증 정보를 제대로 읽을 수 없습니다. 사진 품질을 확인해주세요."
            )
            return
        
        # 카테고리 분류
        categorizer = Categorizer()
        expense = categorizer.categorize(expense)
        
        # 중복 검사
        deduper = DuplicateChecker()
        dup_result = await deduper.check_expense(expense)
        
        if dup_result.is_duplicate:
            await sender.send_duplicate_warning(chat_id, expense, dup_result)
            return
        
        # Notion 저장
        notion = NotionWriter()
        result = await notion.save_expense(expense)
        
        if result.success:
            await sender.send_receipt_result(chat_id, expense, result)
        else:
            await sender.send_save_failed(chat_id, result.error)
        
    except Exception as e:
        logger.error(f"Receipt processing error: {e}", exc_info=True)
        await sender.send_error(chat_id, str(e))
    finally:
        downloader.cleanup(file_path)


async def process_statement_document(
    chat_id: int,
    file_path: str,
    filename: Optional[str] = None
):
    """명세서 처리 - 별도 경로, 실패 시 저장 안 함"""
    sender = TelegramSender()
    downloader = TelegramFileDownloader()
    
    try:
        await sender.send_message(chat_id, "📥 은행 명세서를 분석하는 중...")
        
        # PDF 텍스트 추출
        processor = PDFProcessor()
        pdf_data = processor.process(file_path)
        
        if not pdf_data.get("text") or len(pdf_data["text"]) < 100:
            logger.error("PDF text extraction failed or too short")
            await sender.send_extraction_failed(
                chat_id=chat_id,
                reason="PDF에서 텍스트를 추출할 수 없습니다. 스캔된 PDF는 지원하지 않습니다."
            )
            return
        
        # 명세서 추출
        extractor = ExpenseExtractionService()
        statement = await extractor.extract_statement(
            pdf_text=pdf_data["text"],
            filename=filename
        )
        
        # Validation: 거래가 없거나 모두 실패하면 저장 안 함
        if not statement.transactions:
            logger.warning("No transactions extracted from statement")
            await sender.send_extraction_failed(
                chat_id=chat_id,
                reason="거래 내역을 찾을 수 없습니다. 파일 형식을 확인해주세요."
            )
            return
        
        # 유효한 거래만 필터링
        valid_transactions = [
            tx for tx in statement.transactions
            if tx.merchant and tx.amount != 0 and tx.transaction_date
        ]
        
        if not valid_transactions:
            logger.warning("No valid transactions after filtering")
            await sender.send_extraction_failed(
                chat_id=chat_id,
                reason=f"{len(statement.transactions)}개 거래를 찾았지만, 유효한 정보가 부족합니다."
            )
            return
        
        logger.info(f"Extracted {len(valid_transactions)} valid transactions from {len(statement.transactions)} total")
        
        # 각 거래 분류
        categorizer = Categorizer()
        for tx in valid_transactions:
            tx = categorizer.categorize_transaction(tx)
        
        # 중복 검사
        deduper = DuplicateChecker()
        new_transactions = []
        duplicates = []
        
        for tx in valid_transactions:
            dup_result = await deduper.check_transaction(tx)
            if dup_result.is_duplicate:
                duplicates.append(tx)
            else:
                new_transactions.append(tx)
        
        if not new_transactions:
            await sender.send_message(
                chat_id,
                f"📄 모든 거래({len(valid_transactions)}개)가 이미 기록되어 있습니다."
            )
            return
        
        # Notion 저장
        await sender.send_message(
            chat_id,
            f"💾 {len(new_transactions)}개 거래를 저장하는 중..."
        )
        
        notion = NotionWriter()
        
        saved_count = 0
        failed_count = 0
        for tx in new_transactions:
            result = await notion.save_transaction(tx)
            if result.success:
                saved_count += 1
            else:
                failed_count += 1
                logger.error(f"Failed to save transaction: {result.error}")
        
        # 월별 요약 업데이트
        if saved_count > 0:
            summary_result = await notion.update_monthly_summary(
                statement.statement_month,
                new_transactions
            )
        else:
            summary_result = None
        
        # 결과 응답
        await sender.send_statement_result(
            chat_id=chat_id,
            statement=statement,
            saved_count=saved_count,
            failed_count=failed_count,
            duplicate_count=len(duplicates),
            valid_count=len(valid_transactions),
            summary_url=summary_result.url if summary_result and summary_result.success else None
        )
        
    except Exception as e:
        logger.error(f"Statement processing error: {e}", exc_info=True)
        await sender.send_error(chat_id, str(e))
    finally:
        downloader.cleanup(file_path)
