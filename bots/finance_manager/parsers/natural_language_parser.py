"""
自然语言解析器
解析用户的财务相关自然语言输入
"""

import re
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class NaturalLanguageParser:
    """自然语言解析器"""

    # 中文数字映射
    CHINESE_NUM_MAP = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        "零": 0
    }

    def __init__(self):
        """初始化解析器"""
        pass

    def parse_financial_status(self, text: str) -> Dict[str, Any]:
        """
        解析财务状态描述

        示例输入: "账户A存款X万，账户B欠Y千，账户C欠Z千，还有N期M千正在还第一期"

        返回:
        {
            "accounts": [
                {"name": "账户A", "type": "存款", "balance": X},
                {"name": "账户B", "type": "债务", "balance": -Y},
                {"name": "账户C", "type": "债务", "balance": -Z}
            ],
            "debts": [
                {
                    "type": "分期付款",
                    "name": "分期付款",
                    "total_amount": M,
                    "total_periods": N,
                    "current_period": 1,
                    "period_amount": XXX
                }
            ]
        }
        """
        result = {
            "accounts": [],
            "debts": []
        }

        # 分句处理（按逗号、句号、分号分割）
        sentences = re.split(r'[，。；、]', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 识别存款账户
            if any(kw in sentence for kw in ["存款", "余额", "账户"]):
                account = self._parse_account(sentence, "存款")
                if account:
                    result["accounts"].append(account)

            # 识别债务
            elif any(kw in sentence for kw in ["欠", "欠款", "花呗", "信用卡"]):
                debt = self._parse_debt(sentence)
                if debt:
                    result["accounts"].append(debt)

            # 识别分期
            elif "期" in sentence:
                installment = self._parse_installment(sentence)
                if installment:
                    result["debts"].append(installment)

        return result

    def _parse_account(self, text: str, account_type: str) -> Optional[Dict]:
        """
        解析账户信息

        示例: "账户A存款X万" -> {"name": "账户A", "type": "存款", "balance": X}
        """
        # 提取账户名称（在关键词之前的文字）
        name_match = re.search(r'([^\d]+?)(?:存款|余额|账户)', text)
        name = name_match.group(1).strip() if name_match else "未命名账户"

        # 提取金额
        amount = self._extract_amount(text)

        if amount > 0:
            return {
                "name": name,
                "type": account_type,
                "balance": amount
            }
        return None

    def _parse_debt(self, text: str) -> Optional[Dict]:
        """
        解析债务信息

        示例: "账户B欠Y千" -> {"name": "账户B", "type": "债务", "balance": -Y}
        """
        # 识别债务类型
        debt_type = "债务"
        name = "债务"

        if "花呗" in text:
            debt_type = "债务"
            name = "花呗"
        elif "信用卡" in text:
            debt_type = "债务"
            name = "信用卡"
        elif "借款" in text:
            debt_type = "债务"
            name = "借款"

        # 提取金额
        amount = self._extract_amount(text)

        if amount > 0:
            return {
                "name": name,
                "type": debt_type,
                "balance": -amount  # 负数表示债务
            }
        return None

    def _parse_installment(self, text: str) -> Optional[Dict]:
        """
        解析分期信息

        示例: "N期M千正在还第一期" ->
        {
            "type": "分期付款",
            "name": "分期付款",
            "total_amount": M,
            "total_periods": N,
            "current_period": 1,
            "period_amount": M/N
        }
        """
        # 提取总期数: "3期"
        periods_match = re.search(r'(\d+)期', text)
        total_periods = int(periods_match.group(1)) if periods_match else 0

        # 提取当前期数: "第1期" 或 "还第一期"
        current_match = re.search(r'第?([一二三四五六七八九十\d]+)期', text)
        if current_match:
            current_str = current_match.group(1)
            current_period = self._chinese_to_number(current_str)
        else:
            current_period = 1

        # 提取总金额
        total_amount = self._extract_amount(text)

        if total_periods > 0 and total_amount > 0:
            period_amount = round(total_amount / total_periods, 2)
            return {
                "type": "分期付款",
                "name": "分期付款",
                "total_amount": total_amount,
                "total_periods": total_periods,
                "current_period": current_period,
                "period_amount": period_amount,
                "paid_amount": period_amount * (current_period - 1),
                "remaining_amount": total_amount - period_amount * (current_period - 1)
            }
        return None

    def _extract_amount(self, text: str) -> float:
        """
        提取金额

        支持格式:
        - X.Xw, X万 -> X*10000
        - X.Xk, X千 -> X*1000
        - X元, ¥X -> X
        - 纯数字 -> 原值
        """
        # 匹配万
        match = re.search(r'(\d+\.?\d*)[wW万]', text)
        if match:
            return float(match.group(1)) * 10000

        # 匹配千
        match = re.search(r'(\d+\.?\d*)[kK千]', text)
        if match:
            return float(match.group(1)) * 1000

        # 匹配元或人民币符号
        match = re.search(r'¥?(\d+\.?\d*)元?', text)
        if match:
            return float(match.group(1))

        return 0.0

    def _chinese_to_number(self, chinese: str) -> int:
        """
        中文数字转阿拉伯数字

        示例: "一" -> 1, "十" -> 10
        """
        if chinese.isdigit():
            return int(chinese)

        return self.CHINESE_NUM_MAP.get(chinese, 1)

    def parse_budget(self, text: str) -> Dict[str, Any]:
        """
        解析预算规划

        示例输入:
        "收入工资X元，兼职Y元，固定支出房租Z元，可变支出W元，应急V元"

        返回:
        {
            "month": "2026-01",
            "income": [
                {"category": "工资", "amount": X},
                {"category": "兼职", "amount": Y}
            ],
            "expenses": [
                {"category": "固定支出", "subcategory": "房租", "amount": Z},
                {"category": "可变支出", "subcategory": "个人费用", "amount": W},
                {"category": "应急资金", "amount": V}
            ]
        }
        """
        result = {
            "month": datetime.now().strftime("%Y-%m"),
            "income": [],
            "expenses": []
        }

        # 分句处理
        sentences = re.split(r'[，。；、]', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 识别收入
            if "收入" in sentence or "工资" in sentence or "兼职" in sentence:
                income_item = self._parse_income(sentence)
                if income_item:
                    result["income"].append(income_item)

            # 识别支出
            elif "支出" in sentence or "房租" in sentence or "应急" in sentence:
                expense_item = self._parse_expense(sentence)
                if expense_item:
                    result["expenses"].append(expense_item)

        return result

    def _parse_income(self, text: str) -> Optional[Dict]:
        """
        解析收入项（仅提取金额，分类由 AI 处理）

        注意：此方法仅用于基础解析，实际分类应由 AI 根据用户现有类别智能判断
        """
        amount = self._extract_amount(text)
        if amount <= 0:
            return None

        # 只返回金额和原始文本，让 AI 处理分类
        return {"amount": amount, "raw_text": text}

    def _parse_expense(self, text: str) -> Optional[Dict]:
        """
        解析支出项（仅提取金额，分类由 AI 处理）

        注意：此方法仅用于基础解析，实际分类应由 AI 根据用户现有类别智能判断
        """
        amount = self._extract_amount(text)
        if amount <= 0:
            return None

        # 只返回金额和原始文本，让 AI 处理分类
        return {"amount": amount, "raw_text": text}

    def parse_expense_record(self, text: str) -> Optional[Dict]:
        """
        解析消费记录（仅提取基础信息，分类由 AI 处理）

        示例输入: "用账户A买了X元的商品"

        返回:
        {
            "payment_method": "账户A",
            "amount": X,
            "raw_text": "用账户A买了X元的商品"
        }

        注意：消费类别应由 AI 根据用户历史记录智能判断
        """
        result = {}

        # 提取支付方式（这个可以保留，因为是固定的支付渠道）
        payment_keywords = {
            "小荷包": "小荷包",
            "支付宝": "支付宝",
            "微信": "微信",
            "花呗": "花呗",
            "信用卡": "信用卡",
            "现金": "现金"
        }

        for keyword, method in payment_keywords.items():
            if keyword in text:
                result["payment_method"] = method
                break

        # 提取金额
        amount = self._extract_amount(text)
        if amount > 0:
            result["amount"] = amount

        # 保存原始文本，让 AI 处理分类
        result["raw_text"] = text

        return result if result else None
