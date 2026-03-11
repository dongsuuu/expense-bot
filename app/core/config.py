"""
Configuration - Pydantic Settings
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = Field(..., description="Telegram bot token")
    
    # Notion
    NOTION_TOKEN: str = Field(..., description="Notion integration token")
    NOTION_DATABASE_ID: Optional[str] = Field(default=None, description="Notion database ID (optional - auto-creates if not provided)")
    NOTION_PARENT_PAGE_ID: Optional[str] = Field(default=None, description="Notion parent page ID for auto-created database")
    NOTION_API_BASE: str = "https://api.notion.com/v1"
    NOTION_VERSION: str = "2022-06-28"
    
    # Render
    RENDER_EXTERNAL_URL: Optional[str] = None
    
    # Optional
    OPENAI_API_KEY: Optional[str] = None
    DUPLICATE_THRESHOLD: float = 0.85
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    def is_configured(self) -> dict:
        """Check which services are properly configured"""
        return {
            "telegram": bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_BOT_TOKEN != "your_telegram_bot_token"),
            "notion": bool(self.NOTION_TOKEN and self.NOTION_TOKEN != "your_notion_token"),
            "notion_parent": bool(self.NOTION_PARENT_PAGE_ID and self.NOTION_PARENT_PAGE_ID != "your_parent_page_id"),
            "openai": bool(self.OPENAI_API_KEY),
        }


settings = Settings()
