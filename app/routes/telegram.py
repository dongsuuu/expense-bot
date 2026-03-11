"""
Telegram Webhook Handler - Production Ready with Auto-Create Database
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Request, BackgroundTasks

from app.models.schemas import TelegramWebhook, ExpenseExtracted, Transaction, SaveResult
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
    """Detect Chase statement by content"""
    if not text:
        return False
    text_lower = text.lower()
    indicators = [
        'printed from chase personal online',
        'total checking', 'chase.com', 'secure.chase.com',
        'transactions showing', 'date description type amount balance',
        'zelle', 'pos debit',
    ]
    for indicator in indicators:
        if indicator in text_lower:
            logger.info(f"Chase detected by: {indicator}")
            return True
    return False


def is_valid_expense(expense: ExpenseExtracted) -> bool:
    """Validate extracted expense"""
    if not expense.merchant or expense.merchant in ['Unknown', '']:
        if not expense.raw_text:
            return False
    if not expense.total or expense.total == 0:
        return False
    if expense.merchant and 'printed from chase' in expense.merchant.lower():
        return False
    return True


def is_valid_transaction(tx: Transaction) -> bool:
    """Validate parsed transaction"""
    if not tx.description and not tx.merchant:
        return False
    if not tx.amount or tx.amount == 0:
        return False
    if not tx.transaction_date:
        return False
    return True


@router.post("/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle Telegram webhook"""
    try:
        data = await request.json()
        webhook = TelegramWebhook(**data)
        
        chat_id = webhook.get_chat_id()
        file_id = webhook.get_file_id()
        caption = webhook.get_caption()
        filename = webhook.get_document_filename() or ""
        
        logger.info(f"Webhook: chat_id={chat_id}, filename={filename}")
        
        if not chat_id:
            return {"ok": True}
        
        if not file_id:
            sender = TelegramSender()
            await sender.send_message(chat_id, "📎 파일을 별내주세요!")
            return {"ok": True}
        
        downloader = TelegramFileDownloader()
        file_path, file_type = await downloader.download(file_id)
        logger.info(f"Downloaded: {file_path}")
        
        background_tasks.add_task(
            process_document,
            chat_id=chat_id,
            file_path=file_path,
            filename=filename,
            caption=caption
        )
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def process_document(chat_id: int, file_path: str, filename: str, caption: Optional[str] = None):
    """Process uploaded document"""
    sender = TelegramSender()
    
    try:
        is_pdf = file_path.endswith('.pdf')
        pdf_text = None
        images = []
        
        if is_pdf:
            processor = PDFProcessor()
            pdf_text = processor.extract_text(file_path)
            logger.info(f"PDF text: {len(pdf_text) if pdf_text else 0} chars")
            if not pdf_text or len(pdf_text) < 100:
                logger.info("PDF has no text, converting to images for OCR")
                images = processor.convert_to_images(file_path)
        else:
            images = [file_path]
        
        is_statement = False
        if pdf_text and is_chase_statement(pdf_text):
            is_statement = True
        elif any(kw in filename.lower() for kw in ['statement', 'chase']):
            is_statement = True
        
        if is_statement:
            await process_statement(chat_id, pdf_text, images, filename, sender)
        else:
            await process_receipt(chat_id, pdf_text, images, filename, caption, sender)
            
    except Exception as e:
        logger.error(f"Document processing error: {e}", exc_info=True)
        await sender.send_message(chat_id, "❌ 처리 중 오류가 발생했습니다.")


async def process_receipt(chat_id: int, pdf_text: Optional[str], images: List[str], 
                          filename: str, caption: Optional[str], sender: TelegramSender):
    """Process receipt document"""
    await sender.send_message(chat_id, "🔍 영수증을 분석하는 중...")
    
    try:
        extractor = ExpenseExtractionService()
        expense = await extractor.extract_receipt(images=images, raw_text=pdf_text, caption=caption)
        
        if not is_valid_expense(expense):
            logger.warning(f"Invalid expense: {expense}")
            await sender.send_message(chat_id, "❌ 유효한 지출 정보를 추출하지 못했습니다.\n영수증 이미지가 선명한지 확인해주세요.")
            return
        
        categorizer = Categorizer()
        expense = categorizer.categorize(expense)
        
        # Create shared NotionWriter instance
        notion = NotionWriter()
        deduper = DuplicateChecker()
        
        # Share database ID with deduper (for auto-create mode)
        db_id = await notion._ensure_database()
        if db_id:
            deduper.set_database_id(db_id)
        
        dup_result = await deduper.check_expense(expense)
        
        if dup_result.is_duplicate:
            await sender.send_message(chat_id, f"⚠️ 중복 지출이 감지되었습니다.")
            return
        
        await sender.send_message(chat_id, "💾 Notion에 저장하는 중...")
        
        result = await notion.save_expense(expense)
        
        # Handle database creation/access errors
        if result.error == "PARENT_PAGE_INVALID":
            logger.error("Notion parent page is invalid or not accessible")
            await sender.send_message(
                chat_id,
                "❌ Notion 데이터베이스를 생성할 수 없습니다.\n\n"
                "부모 페이지 ID가 잘못되었거나,\n"
                "integration과 페이지가 공유되지 않았습니다.\n\n"
                "확인 방법:\n"
                "1. NOTION_PARENT_PAGE_ID 확인\n"
                "2. Integration에 페이지 공유 설정"
            )
            return
        
        if result.error == "DATABASE_INACCESSIBLE":
            logger.error("Notion database is not accessible")
            await sender.send_message(
                chat_id,
                "❌ Notion 데이터베이스에 접근할 수 없습니다.\n\n"
                "데이터베이스 ID가 잘못되었거나,\n"
                "integration과 데이터베이스가 공유되지 않았습니다.\n\n"
                "확인 방법:\n"
                "1. NOTION_DATABASE_ID 확인 (또는 비워두면 자동 생성)\n"
                "2. Integration에 데이터베이스 공유 설정"
            )
            return
        
        if result.success:
            await sender.send_message(
                chat_id,
                f"✅ 저장 완료\n\n🏪 {expense.merchant}\n📅 {expense.transaction_date}\n💰 {expense.total:,.2f} {expense.currency}\n📂 {expense.category or '미분류'}"
            )
        else:
            logger.error(f"Save failed: {result.error}")
            await sender.send_message(chat_id, f"❌ 저장에 실패했습니다.\n오류: {result.error or '알 수 없음'}")
            
    except Exception as e:
        logger.error(f"Receipt processing error: {e}", exc_info=True)
        await sender.send_message(chat_id, "❌ 영수증 처리 중 오류가 발생했습니다.")


async def process_statement(chat_id: int, pdf_text: Optional[str], images: List[str],
                            filename: str, sender: TelegramSender):
    """Process statement document"""
    await sender.send_message(chat_id, "📄 명세서를 분석하는 중...")
    
    try:
        if not pdf_text and not images:
            await sender.send_message(chat_id, "❌ PDF에서 내용을 읽을 수 없습니다.")
            return
        
        if not pdf_text or len(pdf_text) < 200:
            if images:
                await sender.send_message(chat_id, "🔍 OCR로 텍스트 추출 중...")
                await sender.send_message(chat_id, "⚠️ PDF에서 텍스트를 추출할 수 없습니다.\n스캔된 PDF는 OCR 기능이 필요합니다.")
                return
        
        extractor = ExpenseExtractionService()
        transactions = await extractor.extract_statement(pdf_text or "", filename)
        
        logger.info(f"Extracted {len(transactions)} transactions")
        
        if not transactions:
            await sender.send_message(chat_id, "❌ 거래 내역을 찾을 수 없습니다.\n지원되는 형식: Chase bank statements")
            return
        
        valid_txs = [tx for tx in transactions if is_valid_transaction(tx)]
        logger.info(f"Valid transactions: {len(valid_txs)}")
        
        if not valid_txs:
            await sender.send_message(chat_id, "❌ 유효한 거래를 찾을 수 없습니다.")
            return
        
        await sender.send_message(chat_id, f"💾 {len(valid_txs)}개 거래 처리 중...")
        
        # Create shared NotionWriter instance
        notion = NotionWriter()
        deduper = DuplicateChecker()
        
        # Share database ID with deduper (for auto-create mode)
        db_id = await notion._ensure_database()
        if db_id:
            deduper.set_database_id(db_id)
        
        saved = 0
        failed = 0
        duplicates = 0
        database_error = False
        error_message = None
        
        for i, tx in enumerate(valid_txs):
            if database_error:
                logger.info(f"Skipping remaining {len(valid_txs) - i} transactions due to database error")
                break
            
            try:
                dup_result = await deduper.check_transaction(tx)
                if dup_result.is_duplicate:
                    duplicates += 1
                    continue
                
                result = await notion.save_transaction(tx)
                
                # Check for database configuration errors
                if result.error == "PARENT_PAGE_INVALID":
                    database_error = True
                    error_message = "parent_page"
                    logger.error(f"Notion parent page invalid on transaction {i+1}, stopping batch")
                    break
                
                if result.error == "DATABASE_INACCESSIBLE":
                    database_error = True
                    error_message = "database"
                    logger.error(f"Notion database not accessible on transaction {i+1}, stopping batch")
                    break
                
                if result.success:
                    saved += 1
                else:
                    failed += 1
                    logger.warning(f"Save failed: {result.error}")
                    
            except Exception as e:
                failed += 1
                logger.error(f"Transaction processing error: {e}")
        
        # Build result message
        if database_error:
            if error_message == "parent_page":
                msg = (
                    f"❌ Notion 데이터베이스 생성 실패\n\n"
                    f"📊 총 거래: {len(valid_txs)}개\n"
                    f"💾 저장 성공: {saved}개\n"
                )
                if duplicates > 0:
                    msg += f"⚠️ 중복 제외: {duplicates}개\n"
                if failed > 0:
                    msg += f"❌ 저장 실패: {failed}개\n"
                msg += (
                    f"\n⛔️ 부모 페이지 ID가 잘못되었거나\n"
                    f"integration과 공유되지 않았습니다.\n\n"
                    f"확인 방법:\n"
                    f"1. NOTION_PARENT_PAGE_ID 확인\n"
                    f"2. Integration에 페이지 공유 설정"
                )
            else:
                msg = (
                    f"❌ Notion 데이터베이스 오류\n\n"
                    f"📊 총 거래: {len(valid_txs)}개\n"
                    f"💾 저장 성공: {saved}개\n"
                )
                if duplicates > 0:
                    msg += f"⚠️ 중복 제외: {duplicates}개\n"
                if failed > 0:
                    msg += f"❌ 저장 실패: {failed}개\n"
                msg += (
                    f"\n⛔️ 데이터베이스 ID가 잘못되었거나\n"
                    f"integration과 공유되지 않았습니다.\n\n"
                    f"확인 방법:\n"
                    f"1. NOTION_DATABASE_ID 확인 (또는 비워두면 자동 생성)\n"
                    f"2. Integration에 데이터베이스 공유 설정"
                )
        else:
            msg = (
                f"✅ 처리 완료\n\n"
                f"📊 총 거래: {len(valid_txs)}개\n"
                f"💾 저장 성공: {saved}개\n"
            )
            if duplicates > 0:
                msg += f"⚠️ 중복 제외: {duplicates}개\n"
            if failed > 0:
                msg += f"❌ 저장 실패: {failed}개"
        
        await sender.send_message(chat_id, msg)
        
    except Exception as e:
        logger.error(f"Statement processing error: {e}", exc_info=True)
        await sender.send_message(chat_id, "❌ 명세서 처리 중 오류가 발생했습니다.")
