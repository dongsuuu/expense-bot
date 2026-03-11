"""
Telegram File Downloader
"""
import logging
import os
import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)


class TelegramFileDownloader:
    """Download files from Telegram"""
    
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
    
    async def download(self, file_id: str) -> tuple:
        """Download file by file_id. Returns: (file_path, file_type)"""
        file_info = await self._get_file_path(file_id)
        if not file_info:
            raise Exception(f"Could not get file path for {file_id}")
        
        file_path = file_info["file_path"]
        file_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            file_type = 'image'
        elif ext == '.pdf':
            file_type = 'pdf'
        else:
            file_type = 'document'
        
        local_path = f"/tmp/{file_id}_{os.path.basename(file_path)}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status == 200:
                    with open(local_path, 'wb') as f:
                        f.write(await resp.read())
                    logger.info(f"Downloaded {file_type} to {local_path}")
                    return local_path, file_type
                else:
                    raise Exception(f"Download failed: {resp.status}")
    
    async def _get_file_path(self, file_id: str) -> dict:
        """Get file path from Telegram"""
        url = f"{self.base_url}/getFile"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"file_id": file_id}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        return data["result"]
                    raise Exception(f"Telegram error: {data}")
                raise Exception(f"HTTP error: {resp.status}")
