"""
Pydantic Schemas - Unified and Clean
"""
from typing import Optional, List, Any
from datetime import date
from pydantic import BaseModel, Field


class ExpenseExtracted(BaseModel):
    """Extracted expense from receipt"""
    merchant: Optional[str] = None
    total: Optional[float] = None
    transaction_date: Optional[date] = None
    currency: str = "USD"
    category: Optional[str] = None
    subcategory: Optional[str] = None
    payment_method: Optional[str] = None
    confidence: float = 0.8
    needs_review: bool = False
    items: Optional[List[dict]] = None
    tax: Optional[float] = None
    tip: Optional[float] = None
    raw_text: Optional[str] = None
    feedback: Optional[str] = None


class Transaction(BaseModel):
    """Bank transaction from statement"""
    transaction_date: Optional[date] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "USD"
    transaction_type: Optional[str] = None
    raw_type: Optional[str] = None
    balance: Optional[float] = None
    
    class Config:
        arbitrary_types_allowed = True


class Statement(BaseModel):
    """Parsed statement"""
    statement_date: Optional[date] = None
    account_type: Optional[str] = None
    transactions: List[Transaction] = Field(default_factory=list)
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None


class SaveResult(BaseModel):
    """Result of saving to Notion"""
    success: bool
    page_id: Optional[str] = None
    error: Optional[str] = None


class DuplicateCheckResult(BaseModel):
    """Result of duplicate check"""
    is_duplicate: bool = False
    matched_id: Optional[str] = None
    confidence: float = 0.0


class TelegramWebhook(BaseModel):
    """Telegram Webhook Payload"""
    update_id: int
    message: Optional[dict] = None
    
    def get_chat_id(self) -> Optional[int]:
        if self.message and 'chat' in self.message:
            return self.message['chat'].get('id')
        return None
    
    def get_file_id(self) -> Optional[str]:
        if not self.message:
            return None
        if 'photo' in self.message and self.message['photo']:
            return self.message['photo'][-1].get('file_id')
        if 'document' in self.message:
            return self.message['document'].get('file_id')
        return None
    
    def get_caption(self) -> Optional[str]:
        if self.message:
            return self.message.get('caption')
        return None
    
    def get_document_filename(self) -> Optional[str]:
        if self.message and 'document' in self.message:
            return self.message['document'].get('file_name')
        return None
