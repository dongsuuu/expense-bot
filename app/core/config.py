"""
Configuration Settings
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """환경 변수 설정"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_WEBHOOK_URL: Optional[str] = os.getenv("TELEGRAM_WEBHOOK_URL")
    TELEGRAM_API_BASE: str = "https://api.telegram.org/bot"
    
    # Notion
    NOTION_TOKEN: str = os.getenv("NOTION_TOKEN", "")
    NOTION_DATABASE_ID: str = os.getenv("NOTION_DATABASE_ID", "")
    NOTION_API_BASE: str = "https://api.notion.com/v1"
    
    # OpenAI (OCR/Extraction용)
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # Tesseract (로컬 OCR)
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "/usr/bin/tesseract")
    
    # App
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Duplicate Detection
    DUPLICATE_THRESHOLD: float = 0.85  # 유사도 임계값
    
    @property
    def telegram_api_url(self) -> str:
        """Telegram API URL"""
        return f"{self.TELEGRAM_API_BASE}{self.TELEGRAM_BOT_TOKEN}"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# 전역 설정 인스턴스
settings = Settings()
