"""
Telegram Webhook Handler - Fixed Implementation
"""

import logging
from typing import Optional, List
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


def is_chase_statement(text: str) -> bool:
    """Chase statement 감지 - 강력한 규칙"""
    if not text:
        return False
    
    text_lower = text.lower()
    
    chase_indicators = [
        'printed from chase personal online',
        'total checking',
        'chase.com',
        'secure.chase.com',
        'transactions showing',
        'date description type amount balance',
    ]
    
    for indicator in chase_indicators:
        if indicator in text_lower:
            logger.info(f"Chase statement detected by: {indicator}")
            return True
    
    if 'chase' in text_lower and ('checking' in text_lower or 'account' in text_lower):
        if 'zelle' in text_lower or 'pos debit' in text_lower:
            logger.info("Chase statement detected by combined indicators")
            return True
    
    return False


def is_valid_expense(expense) -> bool:
    """지출 유효성 검사"""
    merchant = getattr(expense, "merchant", None)
    total = getattr(expense, "total", None)
    date = getattr(expense, "transaction_date", None)
    
    if merchant and 'printed from chase' in str(merchant).lower():
        logger.warning(f"Filtered Chase header as merchant: {merchant}")
        return False
    
    if (not merchant or str(merchant).lower() in ['unknown', '']) and \
       (not date) and \
       (not total or float(total) == 0):
        return False
    
    return True


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Telegram Webhook - fixed"""
    try:
        data = await request.json()
        webhook = TelegramWebhook(**data)
        
        chat_id = webhook.get_chat_id()
        file_id = webhook.get_file_id()
        caption = webhook.get_caption()
        filename = webhook.get_document_filename() or ""
        
        logger.info(f"Webhook received: chat_id={chat_id}, filename={filename}")
        
        if not chat_id:
            return {"ok": True}
        
        if not file_id:
            sender = TelegramSender()
            await sender.send_message(chat_id, "📎 파일을 별내주세요!")
            return {"ok": True}
        
        downloader = TelegramFileDownloader()
        file_path, file_type = await downloader.download(file_id)
        logger.info(f"Downloaded: {file_path} ({file_type})")
        
        pdf_text = None
        is_pdf = file_path.endswith('.pdf')
        
        if is_pdf:
            try:
                processor = PDFProcessor()
                pdf_text = processor.extract_text(file_path)
                logger.info(f"PDF text extracted: {len(pdf_text) if pdf_text else 0} chars")
            except Exception as e:
                logger.warning(f"PDF text extraction failed: {e}")
        
        is_statement = False
        
        if pdf_text and is_chase_statement(pdf_text):
            is_statement = True
            logger.info("Detected as Chase statement by content")
        elif any(kw in filename.lower() for kw in ['statement', 'chase', 'transactions', 'activity']):
            is_statement = True
            logger.info("Detected as statement by filename")
        elif caption and any(kw in caption.lower() for kw in ['명세서', 'statement', '거래내역']):
            is_statement = True
            logger.info("Detected as statement by caption")
        elif is_pdf and not is_statement:
            logger.info("Defaulting PDF to statement mode")
            is_statement = True
        
        logger.info(f"Document type: {'statement' if is_statement else 'receipt'}")
        
        if is_statement:
            background_tasks.add_task(
                process_statement,
                chat_id=chat_id,
                file_path=file_path,
                pdf_text=pdf_text,
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
    """영수증 처리 - fixed"""
    sender = TelegramSender()
    
    try:
        await sender.send_message(chat_id, "🔍 영수증을 분석하는 중...")
        logger.info(f"Processing receipt: {filename}")
        
        extractor = ExpenseExtractionService()
        
        is_pdf = file_path.endswith('.pdf')
        if is_pdf:
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
        
        logger.info(f"Extracted: merchant={expense.merchant}, total={expense.total}, date={expense.transaction_date}")
        
        if not is_valid_expense(expense):
            logger.warning(f"Invalid expense, blocking save: {expense.merchant}, {expense.total}")
            await sender.send_message(
                chat_id,
                "❌ 유효한 지출 정보를 추출하지 못했습니다.\n"
                "PDF 명세서는 'statement'가 포함된 파일명으로 별내주세요."
            )
            return
        
        categorizer = Categorizer()
        expense = categorizer.categorize(expense)
        logger.info(f"Categorized: {expense.category}")
        
        try:
            deduper = DuplicateChecker()
            dup_result = await deduper.check(expense)
            is_duplicate = dup_result.get("is_duplicate", False)
            logger.info(f"Duplicate check: {is_duplicate}")
        except Exception as e:
            logger.error(f"Duplicate check error: {e}")
            is_duplicate = False
        
        if is_duplicate:
            await sender.send_message(chat_id, "⚠️ 중복 지출이 감지되었습니다.")
            return
        
        await sender.send_message(chat_id, "💾 저장하는 중...")
        notion = NotionWriter()
        
        try:
            result = await notion.save_expense(expense)
            if result.success:
                await sender.send_message(
                    chat_id,
                    f"✅ 저장 완료\n\n"
                    f"🏪 {expense.merchant}\n"
                    f"📅 {expense.transaction_date}\n"
                    f"💰 {expense.total} {expense.currency}"
                )
            else:
                logger.error(f"Notion save failed: {result.error}")
                await sender.send_message(chat_id, "❌ 저장에 실패했습니다.")
        except Exception as e:
            logger.error(f"Notion save error: {e}")
            await sender.send_message(chat_id, "❌ 저장 중 오류가 발생했습니다.")
        
    except Exception as e:
        logger.error(f"Receipt processing error: {e}", exc_info=True)
        await sender.send_message(chat_id, "❌ 처리 중 오류가 발생했습니다.")


async def process_statement(
    chat_id: int,
    file_path: str,
    pdf_text: Optional[str],
    filename: str
):
    """명세서 처리 - Chase 지원"""
    sender = TelegramSender()
    
    try:
        await sender.send_message(chat_id, "📄 명세서를 분석하는 중...")
        logger.info(f"Processing statement: {filename}")
        
        if not pdf_text:
            await sender.send_message(chat_id, "❌ PDF에서 텍스트를 읽을 수 없습니다.")
            return
        
        extractor = ExpenseExtractionService()
        transactions = await extractor.extract_statement(pdf_text, filename)
        
        logger.info(f"Parsed {len(transactions)} transactions from Chase statement")
        
        if not transactions:
            await sender.send_message(
                chat_id,
                "❌ 거래 내역을 찾을 수 없습니다.\n"
                "Chase 명세서 형식이 변경되었을 수 있습니다."
            )
            return
        
        valid_txs = [tx for tx in transactions if tx.amount != 0 and tx.description]
        logger.info(f"Valid transactions: {len(valid_txs)}")
        
        if not valid_txs:
            await sender.send_message(chat_id, "❌ 유효한 거래를 찾을 수 없습니다.")
            return
        
        await sender.send_message(chat_id, f"💾 {len(valid_txs)}개 거래를 저장하는 중...")
        
        notion = NotionWriter()
        saved = 0
        failed = 0
        
        for tx in valid_txs:
            try:
                result = await notion.save_transaction(tx)
                if result.success:
                    saved += 1
                else:
                    failed += 1
                    logger.warning(f"Failed to save transaction: {result.error}")
            except Exception as e:
                failed += 1
                logger.error(f"Transaction save error: {e}")
        
        logger.info(f"Saved: {saved}, Failed: {failed}")
        
        await sender.send_message(
            chat_id,
            f"✅ 처리 완료\n\n"
            f"📊 거래: {len(valid_txs)}개\n"
            f"💾 저장성공: {saved}개\n"
            f"❌ 저장실패: {failed}개"
        )
        
    except Exception as e:
        logger.error(f"Statement processing error: {e}", exc_info=True)
        await sender.send_message(chat_id, "❌ 처리 중 오류가 발생했습니다.")
