"""
Telegram Sender - Minimal and Correct
"""
import logging
from typing import Optional
import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)


class TelegramSender:
    """Send messages to Telegram"""
    
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
    
    async def send_message(self, chat_id: int, text: str) -> bool:
        """Send text message to chat"""
        if not self.token or self.token == "your_telegram_bot_token":
            logger.error("Telegram token not configured")
            return False
        
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info(f"Message sent to {chat_id}")
                        return True
                    else:
                        body = await resp.text()
                        logger.error(f"Telegram API error: {resp.status} - {body}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
