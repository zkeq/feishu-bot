"""
财务管理机器人
"""

import json
import re
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from bots.base import BaseBot
from core.client import FeishuClient
from core.batcher import MessagePart
from core.ai_client import AIClient
from core.utils import preprocess_markdown_for_feishu

from .parsers.natural_language_parser import NaturalLanguageParser
from .managers.bitable_manager import BitableManager
from .cards.financial_card import FinancialCardGenerator

logger = logging.getLogger(__name__)


class FinanceManagerBot(BaseBot):
    """财务管理机器人"""

    def __init__(self, config: Dict[str, Any], client: FeishuClient, ai_client: AIClient):
        super().__init__(config, client)

        # 使用框架提供的 AI 客户端
        self.ai_client = ai_client

        # OpenAI 配置
        openai_config = config.get("openai", {})
        self.openai_model = openai_config.get("model", "gpt-4o-mini")
        self.openai_temperature = openai_config.get("temperature", 0.3)
        self.openai_max_tokens = openai_config.get("max_tokens")

        # 多维表格配置
        self.bitable_config = config.get("bitable", {})
        self.bitable_enabled = self.bitable_config.get("enabled", False)

        # 初始化解析器
        self.parser = NaturalLanguageParser()

        # 初始化 Bitable 管理器
        if self.bitable_enabled:
            self.bitable_manager = BitableManager(
                client.app_id,
                client.app_secret,
                self.bitable_config
            )
            logger.info("Bitable 管理器初始化成功")
        else:
            self.bitable_manager = None
            logger.warning("Bitable 未启用")

        # 初始化卡片生成器
        self.card_generator = FinancialCardGenerator()

        logger.info(f"财务管理机器人初始化完成: {self.name}")

    def process_messages(
        self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]
    ) -> str:
        """
        处理批量消息

        Args:
            chat_id: 会话 ID
            parts: 消息片段列表
            status_msg_id: 状态消息 ID

        Returns:
            str: 要回复的内容
        """
        try:
            # 检查是否是 /start 命令
            if self._is_start_command(parts):
                return self._handle_start_command(chat_id, parts)

            # 获取用户 ID
            user_id = self._get_user_id(parts)

            # 1. 构建 AI 消息（包含上下文）
            messages = self._build_ai_messages_with_context(parts, user_id)

            # 2. 调用 AI 分析
            self._update_status(chat_id, status_msg_id, "**🤖 正在分析您的财务信息...**")
            ai_response = self._call_ai_streaming(chat_id, messages, status_msg_id)

            # 3. 提取 JSON 数据
            json_data = self._extract_json_data(ai_response)

            # 4. 不自动保存数据，而是通过按钮让用户确认
            # 敏感操作需要用户手动确认

            # 5. 生成交互式卡片（包含确认按钮）
            card = self._build_interactive_card(ai_response, json_data, user_id)

            # 6. 更新状态消息为最终结果
            if status_msg_id:
                self.client.update_message(status_msg_id, card)
            else:
                self.client.send_message(chat_id, card, msg_type="interactive")

            return "已发送财务分析结果"

        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
            return self.on_error(e, chat_id)

    def _is_start_command(self, parts: List[MessagePart]) -> bool:
        """检查是否是 /start 命令"""
        for part in parts:
            if part.kind == "text" and part.text:
                if part.text.strip().lower() in ["/start", "start", "首页", "控制面板"]:
                    return True
        return False

    def _get_user_id(self, parts: List[MessagePart]) -> Optional[str]:
        """获取用户 ID"""
        for part in parts:
            if part.sender_id:
                return part.sender_id
        return None

    def _handle_start_command(self, chat_id: str, parts: List[MessagePart]) -> str:
        """处理 /start 命令，显示控制面板"""
        try:
            user_id = self._get_user_id(parts)
            if not user_id or not self.bitable_manager:
                # 如果没有用户 ID 或 Bitable 未启用，显示简化版
                card = self._build_simple_home_card()
            else:
                # 查询用户数据并生成完整的控制面板
                accounts = self.bitable_manager.get_user_accounts(user_id)
                debts = self.bitable_manager.get_user_debts(user_id)
                budget_data = self.bitable_manager.get_current_month_budget(user_id)
                expenses = self.bitable_manager.get_month_expenses(user_id)

                # 计算财务汇总
                financial_summary = self._calculate_financial_summary(accounts, debts)
                budget_summary = self._calculate_budget_summary(budget_data, expenses)

                # 生成首页卡片
                card = self.card_generator.build_home_card(
                    accounts, debts, budget_summary, financial_summary
                )

            # 发送卡片
            self.client.send_message(chat_id, card, msg_type="interactive")
            return "已发送控制面板"

        except Exception as e:
            logger.error(f"处理 /start 命令失败: {e}", exc_info=True)
            return self.on_error(e, chat_id)

    def _build_simple_home_card(self) -> Dict[str, Any]:
        """构建简化版首页卡片（无数据）"""
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💰 财务管家 - 控制面板"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**欢迎使用财务管家！** 👋\\n\\n请先配置多维表格，然后开始记录您的财务信息。"
                    }
                }
            ]
        }

    def _calculate_financial_summary(
        self, accounts: List[Dict], debts: List[Dict]
    ) -> Dict[str, float]:
        """计算财务汇总"""
        total_assets = sum(acc["balance"] for acc in accounts if acc["balance"] > 0)
        total_liabilities = sum(abs(debt["total_amount"]) for debt in debts)
        net_worth = total_assets - total_liabilities
        debt_ratio = (total_liabilities / total_assets * 100) if total_assets > 0 else 0

        return {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "net_worth": net_worth,
            "debt_ratio": debt_ratio
        }

    def _calculate_budget_summary(
        self, budget_data: List[Dict], expenses: List[Dict]
    ) -> Dict[str, float]:
        """计算预算汇总"""
        total_budget = sum(b["budget_amount"] for b in budget_data if b["type"] == "可变支出")
        total_spent = sum(e["amount"] for e in expenses)
        remaining = total_budget - total_spent

        return {
            "total": total_budget,
            "spent": total_spent,
            "remaining": remaining
        }

    def _build_ai_messages_with_context(
        self, parts: List[MessagePart], user_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """构建 AI 消息（包含用户财务上下文）"""
        content: List[Dict[str, Any]] = []

        # 处理文字和图片
        for part in parts:
            if part.kind == "text" and part.text:
                content.append({"type": "text", "text": part.text})
            elif part.kind == "image" and part.image_key and part.message_id:
                # 获取图片并转换为 base64
                try:
                    import base64
                    image_data = self.client.get_image_resource(part.message_id, part.image_key)
                    if image_data:
                        base64_image = base64.b64encode(image_data).decode('utf-8')
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        })
                        logger.info(f"已添加图片到 AI 消息: image_key={part.image_key}")
                except Exception as e:
                    logger.error(f"获取图片失败: {e}", exc_info=True)

        # 获取当前日期信息
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        current_weekday = weekday_names[now.weekday()]

        # 构建基础系统提示词
        system_prompt = f"{self.get_system_prompt()}\n\n**当前时间信息**：今天是 {current_date} {current_weekday}。"

        # 添加用户财务上下文（如果有）
        if user_id and self.bitable_manager:
            try:
                # 查询用户现有的财务类别
                categories = self.bitable_manager.get_user_categories(user_id)
                income_cats = categories.get("income_categories", [])
                expense_cats = categories.get("expense_categories", [])

                if income_cats or expense_cats:
                    context = "\n\n**用户现有的财务类别**：\n"
                    if income_cats:
                        context += f"- 收入类别: {', '.join(income_cats)}\n"
                    if expense_cats:
                        context += f"- 支出类别: {', '.join(expense_cats)}\n"
                    context += "\n请优先使用用户已有的类别，理解同义词（如'薪水'='工资'）。如果是新类别，可以创建。"
                    system_prompt += context

                # 查询用户当前预算情况（用于消费建议）
                budget_data = self.bitable_manager.get_current_month_budget(user_id)
                expenses = self.bitable_manager.get_month_expenses(user_id)

                if budget_data:
                    budget_summary = self._calculate_budget_summary(budget_data, expenses)
                    budget_context = (
                        f"\n\n**本月预算情况**：\n"
                        f"- 可变支出预算: {budget_summary['total']:.0f}元\n"
                        f"- 已消费: {budget_summary['spent']:.0f}元\n"
                        f"- 剩余: {budget_summary['remaining']:.0f}元\n"
                    )
                    system_prompt += budget_context

            except Exception as e:
                logger.warning(f"获取用户上下文失败: {e}")

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]

    def _build_ai_messages(self, parts: List[MessagePart]) -> List[Dict[str, Any]]:
        """构建 AI 消息"""
        content: List[Dict[str, Any]] = []

        # 处理文字和图片
        for part in parts:
            if part.kind == "text" and part.text:
                content.append({"type": "text", "text": part.text})

        # 获取当前日期信息
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        current_weekday = weekday_names[now.weekday()]

        system_prompt_with_date = (
            f"{self.get_system_prompt()}\n\n"
            f"**当前时间信息**：今天是 {current_date} {current_weekday}。"
        )

        return [
            {"role": "system", "content": system_prompt_with_date},
            {"role": "user", "content": content},
        ]

    def _call_ai_streaming(
        self, chat_id: str, messages: List[Dict[str, Any]], status_msg_id: str
    ) -> str:
        """调用 AI API（流式）"""
        self._update_status(
            chat_id, status_msg_id, "**🚀 正在请求 AI 分析...**\\n\\n等待响应中..."
        )

        def update_callback(content: str):
            """流式更新回调"""
            self._update_status(
                chat_id,
                status_msg_id,
                f"**📝 正在分析中...**\\n\\n{preprocess_markdown_for_feishu(content)}\\n\\n_正在生成中..._",
            )

        result = self.ai_client.call_streaming(
            messages=messages,
            model=self.openai_model,
            temperature=self.openai_temperature,
            max_tokens=self.openai_max_tokens,
            update_callback=update_callback,
            update_interval=0.5,
        )

        return result

    def _update_status(self, chat_id: str, message_id: Optional[str], content: str):
        """更新状态消息"""
        if not message_id:
            return

        card = {
            "config": {"wide_screen_mode": True},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}}
            ],
        }

        self.client.update_message(message_id, card)

    def _extract_json_data(self, ai_response: str) -> Optional[Dict[str, Any]]:
        """从 AI 响应中提取 JSON 数据"""
        try:
            # 使用正则表达式提取 JSON 代码块
            pattern = r'```json\s*(\{[\s\S]*?\})\s*```'
            matches = re.findall(pattern, ai_response)

            if matches:
                json_str = matches[-1]  # 取最后一个匹配
                data = json.loads(json_str)
                logger.info(f"成功提取财务数据: {data}")
                return data
            else:
                logger.warning("未找到 JSON 数据块")
                return None
        except Exception as e:
            logger.error(f"提取 JSON 数据失败: {e}")
            return None

    def _build_interactive_card(
        self, ai_response: str, json_data: Optional[Dict[str, Any]], user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成交互式卡片"""
        # 移除 JSON 代码块，只保留分析内容
        clean_response = re.sub(r'```json[\s\S]*?```', '', ai_response).strip()
        clean_response = preprocess_markdown_for_feishu(clean_response)

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💰 财务管家"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": clean_response}
                }
            ],
        }

        # 根据 action 类型添加按钮
        if json_data and user_id:
            action = json_data.get("action")

            # 为需要确认的操作添加按钮
            if action in ["update_accounts", "create_budget", "record_expense", "repay_debt"]:
                action_buttons = []

                # 添加确认保存按钮
                action_text_map = {
                    "update_accounts": "💾 保存账户信息",
                    "create_budget": "💾 保存预算",
                    "record_expense": "💾 保存消费记录",
                    "repay_debt": "💾 保存还款记录"
                }

                action_buttons.append({
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": action_text_map.get(action, "💾 保存")},
                    "type": "primary",
                    "value": {
                        "action": "confirm_save",
                        "data_action": action,
                        "json_data": json.dumps(json_data),
                        "user_id": user_id
                    }
                })

                # 如果是 update_accounts，还添加查看详情按钮
                if action == "update_accounts":
                    action_buttons.append({
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📊 查看详情"},
                        "type": "default",
                        "value": {"action": "view_details"}
                    })

                card["elements"].append({
                    "tag": "action",
                    "actions": action_buttons
                })

        return card

    def _handle_update_accounts(self, data: Dict[str, Any], user_id: str):
        """处理账户更新"""
        if not self.bitable_enabled or not self.bitable_manager:
            logger.info("多维表格未启用，跳过保存")
            return

        try:
            accounts = data.get("accounts", [])
            debts = data.get("debts", [])

            # 保存账户信息
            for account in accounts:
                account_data = {
                    "user_id": user_id,
                    "account_name": account.get("name"),
                    "account_type": account.get("type"),
                    "balance": account.get("balance", 0),
                    "update_time": int(datetime.now().timestamp() * 1000),
                    "status": "正常",
                    "notes": account.get("notes", "")
                }

                # 检查账户是否已存在
                existing = self.bitable_manager.query_account(user_id, account.get("name"))
                if existing:
                    # 更新现有账户
                    self.bitable_manager.update_account(existing["record_id"], account_data)
                    logger.info(f"更新账户: {account.get('name')}")
                else:
                    # 创建新账户
                    self.bitable_manager.add_account(account_data)
                    logger.info(f"创建账户: {account.get('name')}")

            # 保存债务信息（分期付款）
            for debt in debts:
                debt_data = {
                    "user_id": user_id,
                    "debt_type": debt.get("type", "分期付款"),
                    "debt_name": debt.get("name"),
                    "total_amount": debt.get("total_amount", 0),
                    "paid_amount": 0,  # 初始已还金额为0
                    "total_periods": debt.get("total_periods", 1),
                    "current_period": debt.get("current_period", 1),
                    "period_amount": debt.get("period_amount", 0),
                    "next_payment_date": "",  # 可以根据需要计算
                    "status": "进行中",
                    "notes": debt.get("notes", "")
                }

                # 检查债务是否已存在
                existing = self.bitable_manager.query_debt(user_id, debt.get("name"))
                if existing:
                    # 更新现有债务
                    self.bitable_manager.update_debt(existing["record_id"], debt_data)
                    logger.info(f"更新债务: {debt.get('name')}")
                else:
                    # 创建新债务
                    self.bitable_manager.add_debt(debt_data)
                    logger.info(f"创建债务: {debt.get('name')}")

            logger.info(f"账户更新完成: {len(accounts)} 个账户, {len(debts)} 个债务")

        except Exception as e:
            logger.error(f"更新账户失败: {e}", exc_info=True)

    def _handle_create_budget(self, data: Dict[str, Any], user_id: str):
        """处理预算创建"""
        if not self.bitable_enabled or not self.bitable_manager:
            logger.info("多维表格未启用，跳过保存")
            return

        try:
            month = data.get("month")
            income = data.get("income", [])
            expenses = data.get("expenses", [])

            if not month:
                logger.warning("预算月份为空，跳过保存")
                return

            # 保存收入预算
            for item in income:
                budget_data = {
                    "user_id": user_id,
                    "month": month,
                    "type": "收入",
                    "category": item.get("category"),
                    "budget_amount": item.get("amount", 0),
                    "actual_amount": 0,
                    "create_time": int(datetime.now().timestamp() * 1000),
                    "notes": item.get("notes", "")
                }

                # 检查是否已存在
                existing = self.bitable_manager.query_budget(user_id, month, "收入", item.get("category"))
                if existing:
                    # 更新现有预算
                    self.bitable_manager.update_budget(existing["record_id"], budget_data)
                    logger.info(f"更新收入预算: {item.get('category')}")
                else:
                    # 创建新预算
                    self.bitable_manager.add_budget(budget_data)
                    logger.info(f"创建收入预算: {item.get('category')}")

            # 保存支出预算
            for item in expenses:
                budget_data = {
                    "user_id": user_id,
                    "month": month,
                    "type": item.get("category", "可变支出"),  # 类型：固定支出、可变支出、应急资金
                    "category": item.get("subcategory", item.get("category")),  # 具体类别
                    "budget_amount": item.get("amount", 0),
                    "actual_amount": 0,
                    "create_time": int(datetime.now().timestamp() * 1000),
                    "notes": item.get("notes", "")
                }

                # 检查是否已存在
                existing = self.bitable_manager.query_budget(
                    user_id, month, budget_data["type"], budget_data["category"]
                )
                if existing:
                    # 更新现有预算
                    self.bitable_manager.update_budget(existing["record_id"], budget_data)
                    logger.info(f"更新支出预算: {budget_data['category']}")
                else:
                    # 创建新预算
                    self.bitable_manager.add_budget(budget_data)
                    logger.info(f"创建支出预算: {budget_data['category']}")

            logger.info(f"预算创建完成: {month}, {len(income)} 项收入, {len(expenses)} 项支出")

        except Exception as e:
            logger.error(f"创建预算失败: {e}", exc_info=True)

    def _handle_record_expense(self, data: Dict[str, Any], user_id: str):
        """处理消费记录（实现表联动）"""
        if not self.bitable_enabled or not self.bitable_manager:
            logger.info("多维表格未启用，跳过保存")
            return

        try:
            merchant = data.get("merchant", "")
            amount = data.get("amount", 0)
            expense_time = data.get("time", int(datetime.now().timestamp() * 1000))
            payment_method = data.get("payment_method", "")
            category = data.get("category", "")
            budget_type = data.get("budget_type", "可变支出")
            notes = data.get("notes", "")

            # 1. 保存消费记录
            expense_data = {
                "user_id": user_id,
                "expense_time": expense_time,
                "amount": amount,
                "category": category,
                "payment_method": payment_method,
                "merchant": merchant,
                "budget_type": budget_type,
                "receipt_image": "",  # 如果有图片可以在这里添加
                "notes": notes,
                "create_time": int(datetime.now().timestamp() * 1000)
            }
            self.bitable_manager.add_expense(expense_data)
            logger.info(f"记录消费: {merchant} {amount}元")

            # 2. 更新账户余额（如果支付方式对应某个账户）
            # 例如：支付宝、微信、银行卡等
            if payment_method in ["支付宝", "微信", "银行卡", "现金"]:
                account = self.bitable_manager.query_account(user_id, payment_method)
                if account:
                    new_balance = account["balance"] - amount
                    self.bitable_manager.update_account(
                        account["record_id"],
                        {"balance": new_balance, "update_time": int(datetime.now().timestamp() * 1000)}
                    )
                    logger.info(f"更新账户余额: {payment_method} {account['balance']} -> {new_balance}")

            # 3. 更新预算实际金额
            current_month = datetime.now().strftime("%Y-%m")
            budget = self.bitable_manager.query_budget(user_id, current_month, budget_type, category)
            if budget:
                new_actual = budget["actual_amount"] + amount
                self.bitable_manager.update_budget(
                    budget["record_id"],
                    {"actual_amount": new_actual}
                )
                logger.info(f"更新预算: {category} {budget['actual_amount']} -> {new_actual}")
            else:
                # 如果没有对应预算，更新总的可变支出预算
                total_budget = self.bitable_manager.query_budget(user_id, current_month, budget_type, None)
                if total_budget:
                    new_actual = total_budget["actual_amount"] + amount
                    self.bitable_manager.update_budget(
                        total_budget["record_id"],
                        {"actual_amount": new_actual}
                    )
                    logger.info(f"更新总预算: {budget_type} {total_budget['actual_amount']} -> {new_actual}")

            # 4. 如果是花呗/信用卡消费，更新债务信息
            if payment_method in ["花呗", "信用卡"]:
                debt = self.bitable_manager.query_debt(user_id, payment_method)
                if debt:
                    # 累加债务总额（关键修复：累加而不是替换）
                    new_total = debt["total_amount"] + amount
                    self.bitable_manager.update_debt(
                        debt["record_id"],
                        {
                            "total_amount": new_total,
                            "status": "还款中"
                        }
                    )
                    logger.info(f"累加债务: {payment_method} {debt['total_amount']} -> {new_total}")
                else:
                    # 创建新债务记录
                    debt_data = {
                        "user_id": user_id,
                        "debt_type": payment_method,
                        "debt_name": payment_method,
                        "total_amount": amount,
                        "paid_amount": 0,
                        "total_periods": 1,
                        "current_period": 1,
                        "period_amount": amount,
                        "next_payment_date": "",
                        "status": "还款中",
                        "notes": f"消费产生的{payment_method}债务"
                    }
                    self.bitable_manager.add_debt(debt_data)
                    logger.info(f"创建债务: {payment_method} {amount}元")

            logger.info(f"消费记录完成（含表联动）: {merchant} {amount}元")

        except Exception as e:
            logger.error(f"记录消费失败: {e}", exc_info=True)

    def _handle_repay_debt(self, data: Dict[str, Any], user_id: str):
        """处理还款记录"""
        if not self.bitable_enabled or not self.bitable_manager:
            logger.info("多维表格未启用，跳过保存")
            return

        try:
            debt_name = data.get("debt_name", "")
            amount = data.get("amount", 0)
            payment_source = data.get("payment_source", "")
            repay_time = data.get("repay_time", datetime.now().strftime("%Y-%m-%d"))

            # 1. 查询债务记录
            debt = self.bitable_manager.query_debt(user_id, debt_name)
            if not debt:
                logger.warning(f"未找到债务记录: {debt_name}")
                return

            # 2. 更新已还金额
            new_paid_amount = debt["paid_amount"] + amount
            new_status = "已还清" if new_paid_amount >= debt["total_amount"] else "还款中"

            self.bitable_manager.update_debt(
                debt["record_id"],
                {
                    "paid_amount": new_paid_amount,
                    "status": new_status
                }
            )
            logger.info(f"更新债务: {debt_name} 已还{new_paid_amount}/{debt['total_amount']}元")

            # 3. 如果指定了支付来源，扣除账户余额
            if payment_source:
                account = self.bitable_manager.query_account(user_id, payment_source)
                if account:
                    new_balance = account["balance"] - amount
                    self.bitable_manager.update_account(
                        account["record_id"],
                        {
                            "balance": new_balance,
                            "update_time": int(datetime.now().timestamp() * 1000)
                        }
                    )
                    logger.info(f"扣除账户余额: {payment_source} {account['balance']} -> {new_balance}")

            # 4. 记录还款消费（可选）
            expense_data = {
                "user_id": user_id,
                "expense_time": repay_time,
                "amount": amount,
                "category": "债务还款",
                "payment_method": payment_source if payment_source else "未知",
                "merchant": f"{debt_name}还款",
                "budget_type": "固定支出",
                "receipt_image": "",
                "notes": f"还款{debt_name}",
                "create_time": int(datetime.now().timestamp() * 1000)
            }
            self.bitable_manager.add_expense(expense_data)

            logger.info(f"还款记录完成: {debt_name} {amount}元")

        except Exception as e:
            logger.error(f"还款记录失败: {e}", exc_info=True)

    def handle_card_action(self, action_value: Dict[str, Any], user_id: str, chat_id: str) -> Dict[str, Any]:
        """
        处理卡片按钮交互

        Args:
            action_value: 按钮携带的值
            user_id: 用户 ID
            chat_id: 会话 ID

        Returns:
            Dict: 更新后的卡片或响应
        """
        try:
            action = action_value.get("action")
            logger.info(f"处理卡片交互: {action}")

            if action == "confirm_save":
                # 确认保存数据
                return self._handle_confirm_save(action_value, user_id, chat_id)

            elif action == "view_details":
                # 查看详情 - 显示财务状态卡片
                return self._handle_view_details(user_id)

            elif action == "view_accounts":
                # 查看账户
                return self._handle_view_accounts(user_id)

            elif action == "view_budget":
                # 查看预算
                return self._handle_view_budget(user_id)

            elif action == "view_expenses":
                # 查看消费记录
                return self._handle_view_expenses(user_id)

            elif action == "view_debts":
                # 查看债务
                return self._handle_view_debts(user_id)

            elif action == "get_advice":
                # 获取消费建议
                return self._handle_get_advice(user_id)

            else:
                return {
                    "toast": {
                        "type": "info",
                        "content": "功能开发中..."
                    }
                }

        except Exception as e:
            logger.error(f"处理卡片交互失败: {e}", exc_info=True)
            return {
                "toast": {
                    "type": "error",
                    "content": f"操作失败: {str(e)}"
                }
            }

    def _handle_confirm_save(self, action_value: Dict[str, Any], user_id: str, chat_id: str) -> Dict[str, Any]:
        """处理确认保存操作"""
        try:
            # 从按钮值中提取数据
            data_action = action_value.get("data_action")
            json_data_str = action_value.get("json_data")
            stored_user_id = action_value.get("user_id")

            # 验证用户ID
            if stored_user_id != user_id:
                return {
                    "toast": {
                        "type": "error",
                        "content": "用户验证失败"
                    }
                }

            # 解析JSON数据
            json_data = json.loads(json_data_str)

            # 根据操作类型调用相应的处理方法
            if data_action == "update_accounts":
                self._handle_update_accounts(json_data, user_id)
                message = "✅ 账户信息已保存"
            elif data_action == "create_budget":
                self._handle_create_budget(json_data, user_id)
                message = "✅ 预算已保存"
            elif data_action == "record_expense":
                self._handle_record_expense(json_data, user_id)
                message = "✅ 消费记录已保存"
            elif data_action == "repay_debt":
                self._handle_repay_debt(json_data, user_id)
                message = "✅ 还款记录已保存"
            else:
                message = "❌ 未知操作类型"

            return {
                "toast": {
                    "type": "success",
                    "content": message
                }
            }

        except Exception as e:
            logger.error(f"保存数据失败: {e}", exc_info=True)
            return {
                "toast": {
                    "type": "error",
                    "content": f"保存失败: {str(e)}"
                }
            }

    def _handle_view_details(self, user_id: str) -> Dict[str, Any]:
        """查看财务详情"""
        if not self.bitable_manager:
            return {"toast": {"type": "warning", "content": "多维表格未启用"}}

        accounts = self.bitable_manager.get_user_accounts(user_id)
        debts = self.bitable_manager.get_user_debts(user_id)
        financial_summary = self._calculate_financial_summary(accounts, debts)

        card = self.card_generator.build_financial_status_card(
            accounts, debts, financial_summary
        )

        return {"card": card}

    def _handle_view_accounts(self, user_id: str) -> Dict[str, Any]:
        """查看账户列表"""
        if not self.bitable_manager:
            return {"toast": {"type": "warning", "content": "多维表格未启用"}}

        accounts = self.bitable_manager.get_user_accounts(user_id)

        # 构建账户列表卡片
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**📊 账户总览** ({len(accounts)} 个账户)"
                }
            },
            {"tag": "hr"}
        ]

        for account in accounts:
            balance_color = "green" if account["balance"] >= 0 else "red"
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{account['account_name']}** ({account['account_type']})\n"
                        f"<font color='{balance_color}'>余额: {account['balance']:.2f}元</font>"
                    )
                }
            })

        if not accounts:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "暂无账户数据"
                }
            })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💰 账户列表"},
                "template": "blue"
            },
            "elements": elements
        }

        return {"card": card}

    def _handle_view_budget(self, user_id: str) -> Dict[str, Any]:
        """查看预算"""
        if not self.bitable_manager:
            return {"toast": {"type": "warning", "content": "多维表格未启用"}}

        budget_data = self.bitable_manager.get_current_month_budget(user_id)
        expenses = self.bitable_manager.get_month_expenses(user_id)
        budget_summary = self._calculate_budget_summary(budget_data, expenses)

        card = self.card_generator.build_budget_card(budget_data, budget_summary)

        return {"card": card}

    def _handle_view_expenses(self, user_id: str) -> Dict[str, Any]:
        """查看消费记录"""
        if not self.bitable_manager:
            return {"toast": {"type": "warning", "content": "多维表格未启用"}}

        expenses = self.bitable_manager.get_month_expenses(user_id)

        # 构建消费记录卡片
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**📝 本月消费记录** ({len(expenses)} 笔)"
                }
            },
            {"tag": "hr"}
        ]

        total_amount = sum(e["amount"] for e in expenses)
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**总计**: {total_amount:.2f}元"
            }
        })
        elements.append({"tag": "hr"})

        # 显示最近10笔消费
        for expense in expenses[:10]:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{expense.get('merchant', '未知商家')}** - {expense['amount']:.2f}元\n"
                        f"{expense.get('category', '未分类')} | {expense.get('payment_method', '未知')} | "
                        f"{expense.get('expense_time', '')}"
                    )
                }
            })

        if not expenses:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "本月暂无消费记录"
                }
            })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "📝 消费记录"},
                "template": "blue"
            },
            "elements": elements
        }

        return {"card": card}

    def _handle_view_debts(self, user_id: str) -> Dict[str, Any]:
        """查看债务"""
        if not self.bitable_manager:
            return {"toast": {"type": "warning", "content": "多维表格未启用"}}

        debts = self.bitable_manager.get_user_debts(user_id)

        # 构建债务列表卡片
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**💳 债务总览** ({len(debts)} 笔)"
                }
            },
            {"tag": "hr"}
        ]

        total_debt = sum(d["total_amount"] for d in debts)
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**总负债**: <font color='red'>{total_debt:.2f}元</font>"
            }
        })
        elements.append({"tag": "hr"})

        for debt in debts:
            progress = (debt.get("paid_amount", 0) / debt["total_amount"] * 100) if debt["total_amount"] > 0 else 0
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{debt['debt_name']}** ({debt['debt_type']})\n"
                        f"总额: {debt['total_amount']:.2f}元 | "
                        f"已还: {debt.get('paid_amount', 0):.2f}元 ({progress:.1f}%)\n"
                        f"状态: {debt.get('status', '未知')}"
                    )
                }
            })

        if not debts:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "暂无债务数据 🎉"
                }
            })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💳 债务列表"},
                "template": "red"
            },
            "elements": elements
        }

        return {"card": card}

    def _handle_get_advice(self, user_id: str) -> Dict[str, Any]:
        """获取消费建议"""
        if not self.bitable_manager:
            return {"toast": {"type": "warning", "content": "多维表格未启用"}}

        budget_data = self.bitable_manager.get_current_month_budget(user_id)
        expenses = self.bitable_manager.get_month_expenses(user_id)
        budget_summary = self._calculate_budget_summary(budget_data, expenses)

        # 生成建议
        advice_list = []

        if budget_summary["remaining"] < 0:
            advice_list.append("⚠️ 本月预算已超支，建议减少非必要开支")
        elif budget_summary["remaining"] < budget_summary["total"] * 0.2:
            advice_list.append("⚠️ 预算余额不足20%，请注意控制消费")
        else:
            advice_list.append("✅ 预算执行良好，继续保持")

        # 分析消费类别
        category_spending = {}
        for expense in expenses:
            category = expense.get("category", "未分类")
            category_spending[category] = category_spending.get(category, 0) + expense["amount"]

        if category_spending:
            top_category = max(category_spending.items(), key=lambda x: x[1])
            advice_list.append(f"💡 本月消费最多的类别是「{top_category[0]}」，共 {top_category[1]:.2f}元")

        card = self.card_generator.build_spending_advice_card(advice_list, budget_summary)

        return {"card": card}
