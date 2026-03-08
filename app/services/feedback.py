"""
Feedback Generation Service
지출 피드백 생성
"""

import logging
from datetime import datetime
from app.models.schemas import ExpenseExtracted

logger = logging.getLogger(__name__)


class FeedbackGenerator:
    """피드백 생성기"""
    
    # 카테고리별 평균 지출 (예시)
    CATEGORY_BENCHMARKS = {
        "Dining": {"daily_avg": 15000, "monthly_limit": 450000},
        "Groceries": {"daily_avg": 20000, "monthly_limit": 600000},
        "Transportation": {"daily_avg": 10000, "monthly_limit": 300000},
        "Shopping": {"daily_avg": 50000, "monthly_limit": 500000},
        "Utilities": {"monthly_limit": 200000},
        "Subscription": {"monthly_limit": 100000},
        "Health": {"monthly_limit": 200000},
    }
    
    def generate(self, expense: ExpenseExtracted) -> list:
        """
        지출에 대한 피드백 생성
        """
        feedback = []
        
        # 1. 검토 필요 피드백
        if expense.need_review:
            feedback.append("⚠️ 이 지출은 검토가 필요합니다. 상세 정보를 확인해주세요.")
        
        # 2. 카테고리별 피드백
        category_feedback = self._category_feedback(expense)
        if category_feedback:
            feedback.append(category_feedback)
        
        # 3. 금액 피드백
        amount_feedback = self._amount_feedback(expense)
        if amount_feedback:
            feedback.append(amount_feedback)
        
        # 4. 결제 수단 피드백
        payment_feedback = self._payment_feedback(expense)
        if payment_feedback:
            feedback.append(payment_feedback)
        
        # 5. 시간대 피드백
        time_feedback = self._time_feedback(expense)
        if time_feedback:
            feedback.append(time_feedback)
        
        return feedback if feedback else ["✅ 지출이 정상적으로 기록되었습니다."]
    
    def _category_feedback(self, expense: ExpenseExtracted) -> str:
        """카테고리별 피드백"""
        category = expense.category
        
        messages = {
            "Dining": "🍽️ 외식 지출입니다. 자주 외식하면 건강과 지갑에 주의하세요!",
            "Groceries": "🛒 식료품 구매입니다. 집에서 요리하면 더 건강하고 경제적이에요.",
            "Transportation": "🚗 교통비입니다. 대중교통을 이용하면 비용을 절약할 수 있어요.",
            "Shopping": "🛍️ 쇼핑 지출입니다. 충동구매는 금물! 필요한 것만 구매하세요.",
            "Utilities": "💡 공과금입니다. 에너지 절약으로 비용을 줄여보세요.",
            "Subscription": "📱 구독 서비스입니다. 사용하지 않는 구독은 해지하는 게 좋아요.",
            "Health": "🏥 의료비입니다. 건강이 최우선! 정기검진도 잊지 마세요.",
            "Housing": "🏠 주거비입니다. 가장 큰 고정비 중 하나예요.",
            "Education": "📚 교육비입니다. 자기계발에 투자하는 좋은 습관이에요!",
            "Travel": "✈️ 여행비입니다. 좋은 추억을 만드는 데 쓰는 돈이에요.",
            "Income": "💰 수입입니다. 좋은 하루 되세요!",
            "Transfer": "💸 이체입니다. 송금 내역이 기록되었어요.",
        }
        
        return messages.get(category, f"📊 {category} 카테고리 지출입니다.")
    
    def _amount_feedback(self, expense: ExpenseExtracted) -> str:
        """금액 기반 피드백"""
        if not expense.total:
            return None
        
        total = expense.total
        
        if total >= 500000:
            return f"💰 큰 금액({total:,}원)의 지출입니다. 신중하게 검토하세요."
        elif total >= 100000:
            return f"💵 중간 규모({total:,}원)의 지출입니다."
        elif total <= 5000:
            return f"🪙 소액({total:,}원) 지출입니다. 작은 지출도 모이면 큰돈이 돼요!"
        
        return None
    
    def _payment_feedback(self, expense: ExpenseExtracted) -> str:
        """결제 수단 피드백"""
        payment = expense.payment_method
        
        if not payment:
            return None
        
        payment_lower = payment.lower()
        
        if "card" in payment_lower or "카드" in payment_lower:
            return "💳 카드 결제입니다. 카드 포인트/할인 혜택을 확인하세요!"
        elif "cash" in payment_lower or "현금" in payment_lower:
            return "💵 현금 결제입니다. 현금 영수증은 챙기셨나요?"
        elif "transfer" in payment_lower or "이체" in payment_lower:
            return "🏦 계좌 이체입니다."
        
        return None
    
    def _time_feedback(self, expense: ExpenseExtracted) -> str:
        """시간대 피드백"""
        if not expense.transaction_date:
            return None
        
        # 주말 체크
        try:
            date_obj = datetime.strptime(str(expense.transaction_date), "%Y-%m-%d")
            weekday = date_obj.weekday()
            
            if weekday >= 5:  # 토, 일
                return "📅 주말 지출입니다. 주중보다 지출이 많을 수 있어요!"
        except:
            pass
        
        return None
