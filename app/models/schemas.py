"""
Pydantic Schemas
"""

from typing import Optional, List
from datetime import date
from pydantic import BaseModel, Field


class ExpenseExtracted(BaseModel):
    """추출된 지출 정보"""
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


class Transaction(BaseModel):
    """은행 거래 내역"""
    transaction_date: Optional[date] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None  # Positive = expense, negative = income
    currency: str = "USD"
    transaction_type: Optional[str] = None  # 'debit' or 'credit'
    raw_type: Optional[str] = None  # 'Zelle debit', 'Card', etc.
    balance: Optional[float] = None
    
    class Config:
        arbitrary_types_allowed = True


class Statement(BaseModel):
    """명세서"""
    statement_date: Optional[date] = None
    account_type: Optional[str] = None
    transactions: List[Transaction] = Field(default_factory=list)
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None


class SaveResult(BaseModel):
    """저장 결과"""
    success: bool
    page_id: Optional[str] = None
    error: Optional[str] = None


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
        
        # Photo
        if 'photo' in self.message and self.message['photo']:
            return self.message['photo'][-1].get('file_id')
        
        # Document
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
