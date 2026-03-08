"""
Expense Analysis Bot - FastAPI Backend
Telegram → OCR → Extraction → Notion
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import logging

from app.core.config import settings
from app.routes import telegram

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI 앱 생성
app = FastAPI(
    title="Expense Analysis Bot",
    description="Telegram 기반 지출 분석 및 Notion 연동 시스템",
    version="1.0.0"
)

# 라우터 등록
app.include_router(telegram.router, prefix="/webhook", tags=["telegram"])


@app.get("/")
async def root():
    """헬스체크"""
    return {
        "status": "ok",
        "service": "expense-analysis-bot",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """상태 확인"""
    return {
        "status": "healthy",
        "telegram_webhook": settings.TELEGRAM_WEBHOOK_URL is not None,
        "notion_integration": settings.NOTION_TOKEN is not None
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """전역 예외 처리"""
    logger.error(f"Global error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
