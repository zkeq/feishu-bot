"""
财务卡片生成器
生成美观的飞书卡片UI
"""

from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class FinancialCardGenerator:
    """财务卡片生成器"""

    @staticmethod
    def build_home_card(
        accounts: List[Dict[str, Any]],
        debts: List[Dict[str, Any]],
        budget_summary: Dict[str, Any],
        financial_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成首页卡片（控制面板）

        Args:
            accounts: 账户列表
            debts: 债务列表
            budget_summary: 预算汇总
            financial_summary: 财务汇总

        Returns:
            飞书卡片 JSON
        """
        # 财务汇总数据
        total_assets = financial_summary.get("total_assets", 0)
        total_liabilities = financial_summary.get("total_liabilities", 0)
        net_worth = financial_summary.get("net_worth", 0)

        # 预算数据
        budget_remaining = budget_summary.get("remaining", 0)
        budget_spent = budget_summary.get("spent", 0)
        budget_total = budget_summary.get("total", 0)
        execution_rate = (budget_spent / budget_total * 100) if budget_total > 0 else 0

        # 构建账户概览（只显示正余额的账户）
        accounts_preview = ""
        positive_accounts = [acc for acc in accounts if acc["balance"] >= 0]
        for i, acc in enumerate(positive_accounts[:3]):  # 只显示前3个
            balance_str = f"{acc['balance']:,.0f}"
            accounts_preview += f"💰 {acc['account_name']}: {balance_str}元\n"
        if len(positive_accounts) > 3:
            accounts_preview += f"...还有 {len(positive_accounts) - 3} 个账户"
        if not accounts_preview:
            accounts_preview = "暂无资产账户"

        # 构建债务概览（包含负余额的账户和债务表中的债务）
        debts_preview = ""

        # 添加负余额的账户（信用卡、花呗等）
        negative_accounts = [acc for acc in accounts if acc["balance"] < 0]
        for acc in negative_accounts[:3]:
            balance_str = f"{abs(acc['balance']):,.0f}"
            debts_preview += f"💳 {acc['account_name']}: {balance_str}元\n"

        # 添加债务表中的债务
        remaining_slots = 3 - len(negative_accounts)
        if remaining_slots > 0 and debts:
            for debt in debts[:remaining_slots]:
                debts_preview += f"💳 {debt['debt_name']}: {debt['total_amount']:,.0f}元\n"

        total_debt_count = len(negative_accounts) + len(debts)
        if total_debt_count > 3:
            debts_preview += f"...还有 {total_debt_count - 3} 笔债务"

        if not debts_preview:
            debts_preview = "✅ 无债务"

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💰 财务管家 - 控制面板"},
                "template": "blue"
            },
            "elements": [
                # 欢迎语
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**欢迎使用财务管家！** 👋\n\n这里是你的财务控制中心，一站式管理你的所有财务信息。"
                    }
                },
                {"tag": "hr"},
                # 财务概览
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**📊 财务概览**"
                    }
                },
                {
                    "tag": "column_set",
                    "flex_mode": "none",
                    "background_style": "grey",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**总资产**\n{total_assets:,.0f}元"
                                    }
                                }
                            ]
                        },
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**总负债**\n{total_liabilities:,.0f}元"
                                    }
                                }
                            ]
                        },
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**净资产**\n{net_worth:,.0f}元"
                                    }
                                }
                            ]
                        }
                    ]
                },
                {"tag": "hr"},
                # 本月预算
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**💰 本月预算**\n\n• 预算总额: {budget_total:,.0f}元\n• 已消费: {budget_spent:,.0f}元\n• 剩余: {budget_remaining:,.0f}元\n• 执行率: {execution_rate:.1f}%"
                    }
                },
                {"tag": "hr"},
                # 账户概览
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**🏦 账户概览**\n\n{accounts_preview if accounts_preview else '暂无账户'}"
                    }
                },
                # 债务概览
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**💳 债务概览**\n\n{debts_preview}"
                    }
                },
                {"tag": "hr"},
                # 功能按钮 - 第一行
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📝 编辑计划"},
                            "type": "primary",
                            "value": {"action": "edit_budget"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "💬 财务询问"},
                            "type": "default",
                            "value": {"action": "financial_query"}
                        }
                    ]
                },
                # 功能按钮 - 第二行
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "💸 记录消费"},
                            "type": "default",
                            "value": {"action": "record_expense"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "💳 负债管理"},
                            "type": "default",
                            "value": {"action": "debt_management"}
                        }
                    ]
                },
                # 功能按钮 - 第三行
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📊 查看详情"},
                            "type": "default",
                            "value": {"action": "view_details"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔄 刷新数据"},
                            "type": "default",
                            "value": {"action": "refresh"}
                        }
                    ]
                }
            ]
        }

        return card

    @staticmethod
    def build_financial_status_card(
        accounts: List[Dict[str, Any]],
        debts: List[Dict[str, Any]],
        summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成财务状态卡片

        Args:
            accounts: 账户列表
            debts: 债务列表
            summary: 财务汇总

        Returns:
            飞书卡片 JSON
        """
        # 计算总资产和总负债
        total_assets = summary.get("total_assets", 0)
        total_liabilities = summary.get("total_liabilities", 0)
        net_worth = summary.get("net_worth", 0)
        debt_ratio = summary.get("debt_ratio", 0)

        # 构建账户列表文本
        accounts_text = ""
        for acc in accounts:
            icon = "💰" if acc["balance"] >= 0 else "💳"
            balance_str = f"{acc['balance']:,.0f}" if acc['balance'] >= 0 else f"-{abs(acc['balance']):,.0f}"
            accounts_text += f"{icon} **{acc['account_name']}**: {balance_str}元\n"

        # 构建债务列表文本
        debts_text = ""
        for debt in debts:
            if debt.get("total_periods", 0) > 0:
                debts_text += f"📅 **{debt['debt_name']}**: {debt['total_amount']:,.0f}元 ({debt['current_period']}/{debt['total_periods']}期)\n"
            else:
                debts_text += f"💳 **{debt['debt_name']}**: {debt['total_amount']:,.0f}元\n"

        # 健康度评估
        if debt_ratio < 30:
            health_status = "✅ 健康"
            health_color = "green"
        elif debt_ratio < 60:
            health_status = "⚠️ 一般"
            health_color = "orange"
        else:
            health_status = "❌ 需注意"
            health_color = "red"

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💰 财务状态总览"},
                "template": "blue"
            },
            "elements": [
                # 财务汇总
                {
                    "tag": "column_set",
                    "flex_mode": "none",
                    "background_style": "grey",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**总资产**\n\n{total_assets:,.0f}元"
                                    }
                                }
                            ]
                        },
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**总负债**\n\n{total_liabilities:,.0f}元"
                                    }
                                }
                            ]
                        },
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**净资产**\n\n{net_worth:,.0f}元"
                                    }
                                }
                            ]
                        }
                    ]
                },
                {"tag": "hr"},
                # 账户明细
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📊 账户明细**\n\n{accounts_text if accounts_text else '暂无账户'}"
                    }
                },
                # 债务明细
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**💳 债务明细**\n\n{debts_text if debts_text else '无债务'}"
                    }
                },
                {"tag": "hr"},
                # 财务健康度
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**💊 财务健康度**: {health_status} (负债率 {debt_ratio:.1f}%)"
                    }
                },
                # 操作按钮
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📊 查看详情"},
                            "type": "default",
                            "value": {"action": "view_details"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔄 刷新数据"},
                            "type": "primary",
                            "value": {"action": "refresh"}
                        }
                    ]
                }
            ]
        }

        return card

    @staticmethod
    def build_budget_card(
        budget_data: List[Dict[str, Any]],
        budget_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成预算执行卡片

        Args:
            budget_data: 预算数据
            budget_summary: 预算汇总

        Returns:
            飞书卡片 JSON
        """
        # 从汇总中获取数据
        total_budget = budget_summary.get("total", 0)
        total_spent = budget_summary.get("spent", 0)
        remaining = budget_summary.get("remaining", 0)

        # 执行率
        execution_rate = (total_spent / total_budget * 100) if total_budget > 0 else 0

        # 状态判断
        if execution_rate < 70:
            status_icon = "✅"
            status_text = "良好"
            header_template = "green"
        elif execution_rate < 90:
            status_icon = "⚠️"
            status_text = "接近预算"
            header_template = "orange"
        else:
            status_icon = "❌"
            status_text = "超支风险"
            header_template = "red"

        # 构建预算明细
        budget_details = ""
        for item in budget_data[:5]:  # 只显示前5项
            budget_details += f"• **{item.get('category', '未知')}**: {item.get('budget_amount', 0):,.0f}元\n"

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "📊 本月预算执行"},
                "template": header_template
            },
            "elements": [
                # 预算总览
                {
                    "tag": "column_set",
                    "flex_mode": "none",
                    "background_style": "grey",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**预算总额**\n\n{total_budget:,.0f}元"
                                    }
                                }
                            ]
                        },
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**已消费**\n\n{total_spent:,.0f}元"
                                    }
                                }
                            ]
                        },
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**剩余**\n\n{remaining:,.0f}元"
                                    }
                                }
                            ]
                        }
                    ]
                },
                {"tag": "hr"},
                # 执行率
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**💰 预算执行情况**\n\n"
                            f"• 执行率: {execution_rate:.1f}%\n"
                            f"• 状态: {status_icon} {status_text}"
                        )
                    }
                },
                {"tag": "hr"},
                # 预算明细
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📋 预算明细**\n\n{budget_details if budget_details else '暂无预算数据'}"
                    }
                },
                {"tag": "hr"},
                # 操作按钮
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📝 查看消费"},
                            "type": "primary",
                            "value": {"action": "view_expenses"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "💡 获取建议"},
                            "type": "default",
                            "value": {"action": "get_advice"}
                        }
                    ]
                }
            ]
        }

        return card

    @staticmethod
    def build_spending_advice_card(
        advice_list: List[str],
        budget_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成消费建议卡片

        Args:
            advice_list: 建议列表
            budget_summary: 预算汇总

        Returns:
            飞书卡片 JSON
        """
        total_budget = budget_summary.get("total", 0)
        total_spent = budget_summary.get("spent", 0)
        remaining = budget_summary.get("remaining", 0)
        execution_rate = (total_spent / total_budget * 100) if total_budget > 0 else 0

        # 判断建议类型
        if remaining < 0:
            header_template = "red"
            status_icon = "❌"
        elif remaining < total_budget * 0.2:
            header_template = "orange"
            status_icon = "⚠️"
        else:
            header_template = "green"
            status_icon = "✅"

        # 构建建议文本
        advice_text = ""
        for i, advice in enumerate(advice_list, 1):
            advice_text += f"{i}. {advice}\n"

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💡 消费建议"},
                "template": header_template
            },
            "elements": [
                # 预算状态
                {
                    "tag": "column_set",
                    "flex_mode": "none",
                    "background_style": "grey",
                    "columns": [
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**预算总额**\n\n{total_budget:,.0f}元"
                                    }
                                }
                            ]
                        },
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**已消费**\n\n{total_spent:,.0f}元"
                                    }
                                }
                            ]
                        },
                        {
                            "tag": "column",
                            "width": "weighted",
                            "weight": 1,
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {
                                        "tag": "lark_md",
                                        "content": f"**剩余**\n\n{remaining:,.0f}元"
                                    }
                                }
                            ]
                        }
                    ]
                },
                {"tag": "hr"},
                # 执行率
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{status_icon} 预算执行率**: {execution_rate:.1f}%"
                    }
                },
                {"tag": "hr"},
                # 建议列表
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**💡 智能建议**\n\n{advice_text if advice_text else '暂无建议'}"
                    }
                },
                {"tag": "hr"},
                # 操作按钮
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📝 查看消费"},
                            "type": "primary",
                            "value": {"action": "view_expenses"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📊 查看预算"},
                            "type": "default",
                            "value": {"action": "view_budget"}
                        }
                    ]
                }
            ]
        }

        return card

    @staticmethod
    def build_simple_response_card(
        ai_response: str,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        生成简单响应卡片

        Args:
            ai_response: AI 响应内容
            json_data: JSON 数据（可选）

        Returns:
            飞书卡片 JSON
        """
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💰 财务管家"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": ai_response}
                }
            ]
        }

        # 根据 action 类型添加按钮
        if json_data:
            action = json_data.get("action")

            if action == "update_accounts":
                card["elements"].append({
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📊 查看详情"},
                            "type": "primary",
                            "value": {"action": "view_details"}
                        }
                    ]
                })

        return card
