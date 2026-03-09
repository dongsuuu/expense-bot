"""
Pydantic Models for Expense Analysis - Dual Mode Support
Single Receipt + Bank Statement Transactions
"""

from datetime import date, datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator


class LineItem(BaseModel):
    """개별 품목 (영수증용)"""
    name: str = Field(..., description="품목명")
    quantity: Optional[float] = Field(None, description="수량")
    unit_price: Optional[float] = Field(None, description="단가")
    total_price: Optional[float] = Field(None, description="총액")


class Transaction(BaseModel):
    """은행 명세서 개별 거래"""
    transaction_date: Optional[date] = Field(None, description="거래일")
    description: str = Field(..., description="원본 설명")
    merchant: Optional[str] = Field(None, description="정제된 가맹점명")
    amount: float = Field(..., description="금액 (양수=지출, 음수=수입)")
    currency: str = Field(default="USD", description="통화")
    raw_type: Optional[str] = Field(None, description="원본 타입 (POS DEBIT, Zelle 등)")
    transaction_type: Literal["debit", "credit", "transfer", "unknown"] = Field(
        default="unknown", description="거래 유형"
    )
    category: Literal[
        "Groceries", "Dining", "Transportation", "Housing", "Utilities",
        "Shopping", "Health", "Education", "Subscription", "Travel",
        "Income", "Transfer", "Other"
    ] = Field(default="Other", description="카테고리")
    subcategory: Optional[str] = Field(None, description="세부카테고리")
    spending_pattern: Literal["fixed", "variable", "likely_fixed", "unknown"] = Field(
        default="unknown", description="지출 패턴"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="신뢰도")
    need_review: bool = Field(default=False, description="검토필요여부")
    raw_text: Optional[str] = Field(None, description="원본 텍스트")
    statement_month: Optional[str] = Field(None, description="명세서 월 (YYYY-MM)")
    source_file: Optional[str] = Field(None, description="원본 파일명")


class StatementExtractionResult(BaseModel):
    """명세서 추출 결과"""
    transactions: List[Transaction] = Field(default_factory=list)
    statement_month: Optional[str] = Field(None, description="명세서 월")
    total_debits: float = Field(default=0.0, description="총 지출")
    total_credits: float = Field(default=0.0, description="총 수입")
    currency: str = Field(default="USD")
    source_file: Optional[str] = Field(None)
    confidence: float = Field(default=0.5)
    need_review: bool = Field(default=False)


class ExpenseExtracted(BaseModel):
    """단일 영수증 추출 결과 (기존 모델 유지)"""
    document_type: Literal["receipt", "invoice", "screenshot", "statement", "unknown"] = Field(
        default="unknown"
    )
    merchant: Optional[str] = Field(None)
    transaction_date: Optional[date] = Field(None)
    currency: str = Field(default="KRW")
    subtotal: Optional[float] = Field(None)
    tax: Optional[float] = Field(None)
    tip: Optional[float] = Field(None)
    total: Optional[float] = Field(None)
    payment_method: Optional[str] = Field(None)
    category: Literal[
        "Groceries", "Dining", "Transportation", "Housing", "Utilities",
        "Shopping", "Health", "Education", "Subscription", "Travel",
        "Income", "Transfer", "Other"
    ] = Field(default="Other")
    subcategory: Optional[str] = Field(None)
    line_items: List[LineItem] = Field(default_factory=list)
    raw_text: Optional[str] = Field(None)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    need_review: bool = Field(default=False)
    feedback: List[str] = Field(default_factory=list)


class TelegramWebhook(BaseModel):
    """Telegram Webhook 페이로드"""
    update_id: int
    message: Optional[dict] = None
    edited_message: Optional[dict] = None
    
    def get_chat_id(self) -> Optional[int]:
        msg = self.message or self.edited_message
        if msg:
            return msg.get('chat', {}).get('id')
        return None
    
    def get_file_id(self) -> Optional[str]:
        msg = self.message or self.edited_message
        if not msg:
            return None
        if 'photo' in msg:
            photos = msg['photo']
            return photos[-1]['file_id'] if photos else None
        if 'document' in msg:
            return msg['document']['file_id']
        return None
    
    def get_document_filename(self) -> Optional[str]:
        """문서 파일명 추출"""
        msg = self.message or self.edited_message
        if msg and 'document' in msg:
            return msg['document'].get('file_name', '')
        return None
    
    def get_caption(self) -> Optional[str]:
        msg = self.message or self.edited_message
        if msg:
            return msg.get('caption')
        return None
    
    def get_document_filename(self) -> Optional[str]:
        """문서 파일명 추출"""
        msg = self.message or self.edited_message
        if msg and 'document' in msg:
            return msg['document'].get('file_name', '')
        return None


class DuplicateCheckResult(BaseModel):
    """중복 검사 결과"""
    is_duplicate: bool
    similarity_score: float
    existing_page_id: Optional[str] = None
    message: str


class NotionPageResult(BaseModel):
    """Notion 페이지 생성 결과"""
    success: bool
    page_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class MonthlySummary(BaseModel):
    """월별 요약"""
    month: str  # YYYY-MM
    total_spending: float
    fixed_spending: float
    variable_spending: float
    transaction_count: int
    category_summary: dict  # category -> total
    currency: str = "USD"
