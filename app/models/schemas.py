"""
Pydantic Models for Expense Analysis
"""

from datetime import date
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator


class LineItem(BaseModel):
    """개별 품목"""
    name: str = Field(..., description="품목명")
    quantity: Optional[float] = Field(None, description="수량")
    unit_price: Optional[float] = Field(None, description="단가")
    total_price: Optional[float] = Field(None, description="총액")


class ExpenseExtracted(BaseModel):
    """추출된 지출 정보"""
    
    document_type: Literal[
        "receipt", "invoice", "screenshot", "statement", "unknown"
    ] = Field(default="unknown", description="문서 유형")
    
    merchant: Optional[str] = Field(None, description="가맹점명")
    transaction_date: Optional[date] = Field(None, description="거래일")
    currency: Optional[str] = Field(default="KRW", description="통화")
    
    subtotal: Optional[float] = Field(None, description="소계")
    tax: Optional[float] = Field(None, description="세금")
    tip: Optional[float] = Field(None, description="팁")
    total: Optional[float] = Field(None, description="총액")
    
    payment_method: Optional[str] = Field(None, description="결제수단")
    
    category: Literal[
        "Groceries", "Dining", "Transportation", "Housing",
        "Utilities", "Shopping", "Health", "Education",
        "Subscription", "Travel", "Income", "Transfer", "Other"
    ] = Field(default="Other", description="카테고리")
    
    subcategory: Optional[str] = Field(None, description="세부카테고리")
    
    line_items: List[LineItem] = Field(default_factory=list, description="품목목록")
    raw_text: Optional[str] = Field(None, description="OCR 원본텍스트")
    
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="신뢰도 (0-1)"
    )
    need_review: bool = Field(default=False, description="검토필요여부")
    feedback: List[str] = Field(default_factory=list, description="AI 피드백")
    
    @validator('need_review', always=True)
    def check_need_review(cls, v, values):
        """핵심 필드 불확실 시 검토 필요"""
        if v:
            return v
        # merchant, date, total 중 하나라도 없으면 검토 필요
        if not values.get('merchant') or not values.get('transaction_date') or not values.get('total'):
            return True
        # 신뢰도 낮으면 검토 필요
        if values.get('confidence', 0) < 0.7:
            return True
        return v


class TelegramWebhook(BaseModel):
    """Telegram Webhook 페이로드"""
    update_id: int
    message: Optional[dict] = None
    edited_message: Optional[dict] = None
    
    def get_chat_id(self) -> Optional[int]:
        """채팅 ID 추출"""
        msg = self.message or self.edited_message
        if msg:
            return msg.get('chat', {}).get('id')
        return None
    
    def get_file_id(self) -> Optional[str]:
        """파일 ID 추출 (사진 또는 문서)"""
        msg = self.message or self.edited_message
        if not msg:
            return None
        
        # 사진 (가장 해상도 높은 것)
        if 'photo' in msg:
            photos = msg['photo']
            return photos[-1]['file_id'] if photos else None
        
        # 문서 (PDF 등)
        if 'document' in msg:
            return msg['document']['file_id']
        
        return None
    
    def get_caption(self) -> Optional[str]:
        """캡션 추출"""
        msg = self.message or self.edited_message
        if msg:
            return msg.get('caption')
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


class TelegramReply(BaseModel):
    """Telegram 응답 메시지"""
    chat_id: int
    text: str
    parse_mode: str = "HTML"
    disable_web_page_preview: bool = True
