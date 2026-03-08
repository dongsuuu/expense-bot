"""
Categorization Service
규칙 기반 카테고리 분류
"""

import logging
from app.models.schemas import ExpenseExtracted

logger = logging.getLogger(__name__)


class Categorizer:
    """카테고리 분류기"""
    
    # 키워드 기반 분류 규칙
    RULES = {
        "Dining": {
            "keywords": [
                "restaurant", "cafe", "coffee", "bakery", "pizza", "burger",
                "mcdonald", "starbucks", "kfc", "subway", "domino", "bbq",
                "식당", "카페", "커피", "베이커리", "피자", "버거",
                "맥도날드", "스타벅스", "배달", "음식", "식사", "점심", "저녁"
            ],
            "subcategories": {
                "Fast Food": ["mcdonald", "burger king", "kfc", "subway", "맥도날드", "버거킹"],
                "Cafe": ["starbucks", "coffee", "cafe", "스타벅스", "카페", "커피"],
                "Delivery": ["delivery", "배달", "배민", "요기요", "쿠팡이츠"]
            }
        },
        "Groceries": {
            "keywords": [
                "mart", "market", "grocery", "supermarket", "emart", "homeplus",
                "costco", "traders", "cu", "gs25", "7-eleven", "ministop",
                "마트", "슈퍼", "이마트", "홈플러스", "코스트코", "트레이더스",
                "편의점", "cu", "gs25", "세븐일레븐"
            ],
            "subcategories": {
                "Supermarket": ["emart", "homeplus", "costco", "이마트", "홈플러스", "코스트코"],
                "Convenience": ["cu", "gs25", "7-eleven", "ministop", "편의점"]
            }
        },
        "Transportation": {
            "keywords": [
                "taxi", "uber", "kakao t", "bus", "subway", "metro",
                "gas", "oil", "parking", "toll", "highway",
                "택시", "카카오티", "버스", "지하철", "주유", "주차",
                "고속도로", "통행료"
            ],
            "subcategories": {
                "Taxi": ["taxi", "uber", "kakao t", "택시", "카카오티"],
                "Public Transit": ["bus", "subway", "metro", "버스", "지하철"],
                "Fuel": ["gas", "oil", "주유", "주유소"],
                "Parking": ["parking", "주차"]
            }
        },
        "Shopping": {
            "keywords": [
                "coupang", "gmarket", "11st", "auction", "amazon",
                "mall", "store", "shop", "outlet", "duty free",
                "쿠팡", "지마켓", "11번가", "옥션", "아마존",
                "백화점", "쇼핑몰", "아울렛", "면세점"
            ],
            "subcategories": {
                "Online": ["coupang", "gmarket", "11st", "auction", "amazon", "쿠팡", "지마켓", "11번가"],
                "Offline": ["mall", "department", "백화점", "아울렛"]
            }
        },
        "Utilities": {
            "keywords": [
                "electric", "gas", "water", "internet", "phone", "mobile",
                "kt", "sk", "lg", "telecom",
                "전기", "가스", "수도", "인터넷", "통신", "휴폰",
                "kt", "sk", "lg"
            ]
        },
        "Health": {
            "keywords": [
                "hospital", "clinic", "pharmacy", "drugstore",
                "medical", "dentist", "dermatology",
                "병원", "의원", "약국", "치과", "피부과",
                "한의원", "약", "처방"
            ]
        },
        "Subscription": {
            "keywords": [
                "netflix", "youtube", "spotify", "melon", "genie",
                "membership", "subscription",
                "넷플릭스", "유튜브", "멜론", "지니", "멤버십", "구독"
            ]
        },
        "Housing": {
            "keywords": [
                "rent", "lease", "deposit", "maintenance",
                "월세", "전세", "임대", "관리비", "수리"
            ]
        },
        "Travel": {
            "keywords": [
                "hotel", "airbnb", "flight", "airline", "travel",
                "호텔", "에어비앤비", "항공", "여행", "숙박"
            ]
        },
        "Education": {
            "keywords": [
                "academy", "tutor", "course", "book", "stationery",
                "학원", "과외", "강의", "책", "문구"
            ]
        }
    }
    
    def categorize(self, expense: ExpenseExtracted) -> ExpenseExtracted:
        """
        지출 카테고리 분류
        """
        if expense.category != "Other":
            # 이미 분류됨
            return expense
        
        text = f"{expense.merchant or ''} {expense.raw_text or ''}".lower()
        
        best_category = "Other"
        best_subcategory = None
        best_score = 0
        
        for category, rules in self.RULES.items():
            score = 0
            
            # 키워드 매칭
            for keyword in rules.get("keywords", []):
                if keyword.lower() in text:
                    score += 1
            
            # 서브카테고리 매칭
            subcategories = rules.get("subcategories", {})
            for subcat, subkeywords in subcategories.items():
                for subkw in subkeywords:
                    if subkw.lower() in text:
                        score += 2
                        best_subcategory = subcat
                        break
            
            if score > best_score:
                best_score = score
                best_category = category
        
        expense.category = best_category
        expense.subcategory = best_subcategory
        
        logger.info(f"Categorized: {expense.merchant} -> {best_category}/{best_subcategory}")
        
        return expense
