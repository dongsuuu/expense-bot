"""
FastAPI Main Application
"""
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.routes import telegram
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Expense Bot",
    description="Telegram → Notion Expense Tracker",
    version="1.0.0"
)

app.include_router(telegram.router, prefix="/webhook")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    config_status = settings.is_configured()
    return {
        "status": "healthy",
        "configured": config_status,
        "all_ready": config_status["telegram"] and config_status["notion"]
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {"app": "Expense Bot", "version": "1.0.0", "docs": "/docs"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})
