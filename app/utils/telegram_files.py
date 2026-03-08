"""
Telegram File Downloader
"""

import os
import aiohttp
import logging
from typing import Tuple, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class TelegramFileDownloader:
    """Telegram 파일 다운로더"""
    
    def __init__(self):
        self.api_base = settings.telegram_api_url
        self.temp_dir = "/tmp/expense-bot"
        os.makedirs(self.temp_dir, exist_ok=True)
    
    async def download(self, file_id: str) -> Tuple[str, str]:
        """
        파일 다운로드
        
        Returns:
            (파일경로, 파일타입)
        """
        # 1. 파일 정보 가져오기
        file_path = await self._get_file_path(file_id)
        if not file_path:
            raise ValueError(f"Cannot get file path for {file_id}")
        
        # 2. 파일 다운로드
        download_url = f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}"
        
        local_path = os.path.join(self.temp_dir, os.path.basename(file_path))
        
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                if response.status != 200:
                    raise ValueError(f"Download failed: {response.status}")
                
                with open(local_path, 'wb') as f:
                    f.write(await response.read())
        
        # 3. 파일 타입 확인
        file_type = self._detect_file_type(local_path)
        
        logger.info(f"Downloaded: {local_path} ({file_type})")
        return local_path, file_type
    
    async def _get_file_path(self, file_id: str) -> Optional[str]:
        """Telegram에서 파일 경로 가져오기"""
        url = f"{self.api_base}/getFile"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"file_id": file_id}) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                if not data.get("ok"):
                    return None
                
                return data["result"]["file_path"]
    
    def _detect_file_type(self, file_path: str) -> str:
        """파일 타입 감지"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext in ['.pdf']:
            return "pdf"
        elif ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            return "image"
        else:
            # MIME 타입으로 확인
            import mimetypes
            mime, _ = mimetypes.guess_type(file_path)
            
            if mime:
                if mime.startswith('image/'):
                    return "image"
                elif mime == 'application/pdf':
                    return "pdf"
            
            return "unknown"
    
    def cleanup(self, file_path: str):
        """임시 파일 삭제"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up: {file_path}")
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
