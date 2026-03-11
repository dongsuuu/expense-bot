"""
Categorization Service - Fixed Logic
"""
import logging
from typing import Optional

from app.models.schemas import ExpenseExtracted

logger = logging.getLogger(__name__)


class Categorizer:
    """Categorize expenses based on merchant/description"""
    
    RULES = [
        (["restaurant", "cafe", "coffee", "starbucks", "dunkin", "mcdonalds", "kfc", "pizza"], "식비", "외식"),
        (["grocery", "supermarket", "mart", "costco", "whole foods", "trader joe"], "식료품", "마트"),
        (["uber", "lyft", "taxi", "transit", "subway", "bus", "train", "gas", "shell", "exxon"], "교통", "대중교통"),
        (["amazon", "walmart", "target", "costco", "shopping", "mall"], "쇼핑", "일반"),
        (["netflix", "spotify", "movie", "theater", "game", "steam"], "여가", "구독"),
        (["electric", "gas", "water", "internet", "phone", "utility"], "공과금", "기본"),
        (["pharmacy", "hospital", "doctor", "medical", "health"], "의료", "일반"),
    ]
    
    def categorize(self, expense: ExpenseExtracted) -> ExpenseExtracted:
        """Categorize expense based on merchant/description"""
        if expense.category and expense.category not in [None, "", "Other", "미분류"]:
            logger.debug(f"Keeping existing category: {expense.category}")
            return expense
        
        text = f"{expense.merchant or ''} {expense.raw_text or ''}".lower()
        
        for keywords, category, subcategory in self.RULES:
            if any(kw in text for kw in keywords):
                expense.category = category
                expense.subcategory = subcategory
                logger.info(f"Categorized as {category}/{subcategory}: {expense.merchant}")
                return expense
        
        expense.category = "기타"
        expense.subcategory = "미분류"
        logger.debug(f"Default category for: {expense.merchant}")
        
        return expense
