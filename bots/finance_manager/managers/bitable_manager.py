"""
Bitable 管理器
处理多维表格的查询和保存操作
"""

import json
import logging
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BitableManager:
    """多维表格管理器"""

    def __init__(self, app_id: str, app_secret: str, config: Dict[str, Any]):
        """
        初始化 Bitable 管理器

        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            config: Bitable 配置
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.config = config
        self.app_token = config.get("app_token", "")

        # 表格配置
        self.accounts_table = config.get("accounts_table", {})
        self.budget_table = config.get("budget_table", {})
        self.expense_table = config.get("expense_table", {})
        self.debt_table = config.get("debt_table", {})

        logger.info(f"BitableManager 初始化完成: app_token={self.app_token}")

    @staticmethod
    def build_filter(conditions: List[Dict[str, Any]], conjunction: str = "and") -> Dict[str, Any]:
        """
        构建飞书多维表格 POST 接口的 filter 对象

        Args:
            conditions: 条件列表，每个条件包含 field_name, operator, value
                例如: [{"field_name": "用户ID", "operator": "is", "value": ["user123"]}]
            conjunction: 逻辑连接词，"and" 或 "or"

        Returns:
            filter 对象
        """
        return {
            "conjunction": conjunction,
            "conditions": conditions
        }

    def _get_access_token(self) -> Optional[str]:
        """获取 tenant_access_token"""
        try:
            token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            response = requests.post(token_url, json={
                "app_id": self.app_id,
                "app_secret": self.app_secret
            })

            if response.status_code == 200:
                return response.json()["tenant_access_token"]
            else:
                logger.error(f"获取 access_token 失败: {response.text}")
                return None
        except Exception as e:
            logger.error(f"获取 access_token 异常: {e}", exc_info=True)
            return None

    def query_records(
        self,
        table_config: Dict[str, Any],
        filter_condition: Optional[str] = None,
        page_size: int = 100,
        user_id_type: str = "user_id"
    ) -> List[Dict[str, Any]]:
        """
        查询表格记录

        Args:
            table_config: 表格配置（包含 table_id 和 fields）
            filter_condition: 过滤条件（飞书公式）
            page_size: 每页记录数

        Returns:
            记录列表
        """
        try:
            access_token = self._get_access_token()
            if not access_token:
                return []

            table_id = table_config.get("table_id", "")
            if not table_id:
                logger.error("table_id 未配置")
                return []

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            # 使用正确的 POST 接口：/records/search
            query_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/search?user_id_type={user_id_type}"

            # 构建请求体
            request_body = {
                "page_size": page_size
            }

            # 如果有筛选条件，添加到请求体
            if filter_condition:
                request_body["filter"] = filter_condition
                logger.info(f"筛选条件: {json.dumps(filter_condition, ensure_ascii=False)}")

            response = requests.post(query_url, headers=headers, json=request_body)

            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("code") == 0:
                    # 安全地获取 items，处理 None 的情况
                    data = response_data.get("data")
                    if data is None:
                        logger.warning(f"API 返回的 data 为 None: {response.text}")
                        return []

                    records = data.get("items")
                    if records is None:
                        logger.warning(f"API 返回的 items 为 None: {response.text}")
                        return []

                    logger.info(f"查询到 {len(records)} 条记录")
                    return records
                else:
                    logger.error(f"查询记录失败，错误码: {response_data.get('code')}, 错误信息: {response_data.get('msg')}")
                    return []
            else:
                logger.error(f"查询记录失败，HTTP状态码: {response.status_code}, 响应: {response.text}")
                return []

        except Exception as e:
            logger.error(f"查询记录异常: {e}", exc_info=True)
            return []

    def add_record(
        self,
        table_config: Dict[str, Any],
        fields: Dict[str, Any]
    ) -> bool:
        """
        添加记录到表格

        Args:
            table_config: 表格配置
            fields: 字段数据

        Returns:
            是否成功
        """
        try:
            access_token = self._get_access_token()
            if not access_token:
                return False

            table_id = table_config.get("table_id", "")
            if not table_id:
                logger.error("table_id 未配置")
                return False

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            add_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
            payload = {"fields": fields}

            logger.info(f"添加记录: {fields}")

            response = requests.post(add_url, headers=headers, json=payload)

            if response.status_code == 200 and response.json().get("code") == 0:
                logger.info("添加记录成功")
                return True
            else:
                logger.error(f"添加记录失败: {response.text}")
                return False

        except Exception as e:
            logger.error(f"添加记录异常: {e}", exc_info=True)
            return False

    def update_record(
        self,
        table_config: Dict[str, Any],
        record_id: str,
        fields: Dict[str, Any]
    ) -> bool:
        """
        更新记录

        Args:
            table_config: 表格配置
            record_id: 记录 ID
            fields: 要更新的字段

        Returns:
            是否成功
        """
        try:
            access_token = self._get_access_token()
            if not access_token:
                return False

            table_id = table_config.get("table_id", "")
            if not table_id:
                logger.error("table_id 未配置")
                return False

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            update_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/{record_id}"
            payload = {"fields": fields}

            response = requests.put(update_url, headers=headers, json=payload)

            if response.status_code == 200 and response.json().get("code") == 0:
                logger.info(f"更新记录成功: record_id={record_id}")
                return True
            else:
                logger.error(f"更新记录失败: {response.text}")
                return False

        except Exception as e:
            logger.error(f"更新记录异常: {e}", exc_info=True)
            return False

    # ========== 账户表操作 ==========

    def get_user_accounts(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的所有账户"""
        filter_condition = self.build_filter([
            {"field_name": "用户ID", "operator": "is", "value": [user_id]}
        ])
        records = self.query_records(self.accounts_table, filter_condition)

        # 解析记录
        accounts = []
        for record in records:
            fields = record.get("fields", {})
            accounts.append({
                "record_id": record.get("record_id"),
                "account_name": fields.get("账户名称", ""),
                "account_type": fields.get("账户类型", ""),
                "balance": fields.get("当前余额", 0),
                "status": fields.get("状态", ""),
                "notes": fields.get("备注", "")
            })

        return accounts

    def query_account(self, user_id: str, account_name: str) -> Optional[Dict[str, Any]]:
        """查询特定账户"""
        filter_condition = self.build_filter([{"field_name": "用户ID", "operator": "is", "value": [user_id]}, {"field_name": "账户名称", "operator": "is", "value": [account_name]}])
        records = self.query_records(self.accounts_table, filter_condition)

        if records:
            record = records[0]
            fields = record.get("fields", {})
            return {
                "record_id": record.get("record_id"),
                "account_name": fields.get("账户名称", ""),
                "account_type": fields.get("账户类型", ""),
                "balance": fields.get("当前余额", 0),
                "status": fields.get("状态", ""),
                "notes": fields.get("备注", "")
            }
        return None

    def add_account(self, account_data: Dict[str, Any]) -> bool:
        """添加账户"""
        fields_mapping = self.accounts_table.get("fields", {})

        fields = {
            fields_mapping.get("user_id"): [{"id": account_data.get("user_id", "")}],  # 人员字段格式
            fields_mapping.get("account_name"): account_data.get("account_name", ""),
            fields_mapping.get("account_type"): account_data.get("account_type", ""),
            fields_mapping.get("balance"): account_data.get("balance", 0),
            fields_mapping.get("update_time"): account_data.get("update_time", ""),
            fields_mapping.get("status"): account_data.get("status", "正常"),
            fields_mapping.get("notes"): account_data.get("notes", "")
        }

        return self.add_record(self.accounts_table, fields)

    def update_account(self, record_id: str, update_data: Dict[str, Any]) -> bool:
        """更新账户"""
        fields_mapping = self.accounts_table.get("fields", {})

        fields = {}
        if "balance" in update_data:
            fields[fields_mapping.get("balance")] = update_data["balance"]
        if "update_time" in update_data:
            fields[fields_mapping.get("update_time")] = update_data["update_time"]
        if "status" in update_data:
            fields[fields_mapping.get("status")] = update_data["status"]
        if "notes" in update_data:
            fields[fields_mapping.get("notes")] = update_data["notes"]

        return self.update_record(self.accounts_table, record_id, fields)

    def save_account(self, user_id: str, account_data: Dict[str, Any]) -> bool:
        """保存账户信息"""
        fields_mapping = self.accounts_table.get("fields", {})

        fields = {
            fields_mapping.get("user_id"): [{"id": user_id}],  # 人员字段
            fields_mapping.get("account_name"): account_data.get("name", ""),
            fields_mapping.get("account_type"): account_data.get("type", ""),
            fields_mapping.get("balance"): account_data.get("balance", 0),
            fields_mapping.get("update_time"): int(datetime.now().timestamp() * 1000),
            fields_mapping.get("status"): "活跃",
            fields_mapping.get("notes"): account_data.get("notes", "")
        }

        return self.add_record(self.accounts_table, fields)

    def update_account_balance(self, record_id: str, new_balance: float) -> bool:
        """更新账户余额"""
        fields_mapping = self.accounts_table.get("fields", {})

        fields = {
            fields_mapping.get("balance"): new_balance,
            fields_mapping.get("update_time"): int(datetime.now().timestamp() * 1000)
        }

        return self.update_record(self.accounts_table, record_id, fields)

    # ========== 预算表操作 ==========

    def get_user_categories(self, user_id: str) -> Dict[str, List[str]]:
        """
        获取用户的所有财务类别（用于 AI 上下文）

        Returns:
            {
                "income_categories": ["工资", "兼职", "奖金"],
                "expense_categories": ["房租", "餐饮", "交通"]
            }
        """
        # 查询用户的所有预算记录
        filter_condition = self.build_filter([{"field_name": "用户ID", "operator": "is", "value": [user_id]}])
        records = self.query_records(self.budget_table, filter_condition, page_size=500)

        income_categories = set()
        expense_categories = set()

        for record in records:
            fields = record.get("fields", {})
            budget_type = fields.get("类型", "")
            category = fields.get("类别名称", "")

            if category:
                if budget_type == "收入":
                    income_categories.add(category)
                elif budget_type in ["固定支出", "可变支出"]:
                    expense_categories.add(category)

        return {
            "income_categories": sorted(list(income_categories)),
            "expense_categories": sorted(list(expense_categories))
        }

    def get_current_month_budget(self, user_id: str) -> List[Dict[str, Any]]:
        """获取当前月份的预算"""
        current_month = datetime.now().strftime("%Y-%m")
        filter_condition = self.build_filter([{"field_name": "用户ID", "operator": "is", "value": [user_id]}, {"field_name": "月份", "operator": "is", "value": [current_month]}])

        records = self.query_records(self.budget_table, filter_condition)

        budgets = []
        for record in records:
            fields = record.get("fields", {})
            budgets.append({
                "record_id": record.get("record_id"),
                "month": fields.get("月份", ""),
                "type": fields.get("类型", ""),
                "category": fields.get("类别名称", ""),
                "budget_amount": fields.get("预算金额", 0),
                "actual_amount": fields.get("实际金额", 0)
            })

        return budgets

    def query_budget(self, user_id: str, month: str, budget_type: str, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """查询特定预算"""
        conditions = [
            {"field_name": "用户ID", "operator": "is", "value": [user_id]},
            {"field_name": "月份", "operator": "is", "value": [month]},
            {"field_name": "类型", "operator": "is", "value": [budget_type]}
        ]

        if category:
            conditions.append({"field_name": "类别名称", "operator": "is", "value": [category]})

        filter_condition = self.build_filter(conditions)
        records = self.query_records(self.budget_table, filter_condition)

        if records:
            record = records[0]
            fields = record.get("fields", {})
            return {
                "record_id": record.get("record_id"),
                "month": fields.get("月份", ""),
                "type": fields.get("类型", ""),
                "category": fields.get("类别名称", ""),
                "budget_amount": fields.get("预算金额", 0),
                "actual_amount": fields.get("实际金额", 0)
            }
        return None

    def add_budget(self, budget_data: Dict[str, Any]) -> bool:
        """添加预算"""
        fields_mapping = self.budget_table.get("fields", {})

        fields = {
            fields_mapping.get("user_id"): [{"id": budget_data.get("user_id", "")}],  # 人员字段格式
            fields_mapping.get("month"): budget_data.get("month", ""),
            fields_mapping.get("type"): budget_data.get("type", ""),
            fields_mapping.get("category"): budget_data.get("category", ""),
            fields_mapping.get("budget_amount"): budget_data.get("budget_amount", 0),
            fields_mapping.get("actual_amount"): budget_data.get("actual_amount", 0),
            fields_mapping.get("create_time"): budget_data.get("create_time", ""),
            fields_mapping.get("notes"): budget_data.get("notes", "")
        }

        return self.add_record(self.budget_table, fields)

    def update_budget(self, record_id: str, update_data: Dict[str, Any]) -> bool:
        """更新预算"""
        fields_mapping = self.budget_table.get("fields", {})

        fields = {}
        if "budget_amount" in update_data:
            fields[fields_mapping.get("budget_amount")] = update_data["budget_amount"]
        if "actual_amount" in update_data:
            fields[fields_mapping.get("actual_amount")] = update_data["actual_amount"]
        if "notes" in update_data:
            fields[fields_mapping.get("notes")] = update_data["notes"]

        return self.update_record(self.budget_table, record_id, fields)

    def save_budget(self, user_id: str, budget_data: Dict[str, Any]) -> bool:
        """保存预算"""
        fields_mapping = self.budget_table.get("fields", {})

        fields = {
            fields_mapping.get("user_id"): [{"id": user_id}],
            fields_mapping.get("month"): budget_data.get("month", ""),
            fields_mapping.get("type"): budget_data.get("type", ""),
            fields_mapping.get("category"): budget_data.get("category", ""),
            fields_mapping.get("budget_amount"): budget_data.get("budget_amount", 0),
            fields_mapping.get("actual_amount"): budget_data.get("actual_amount", 0),
            fields_mapping.get("create_time"): int(datetime.now().timestamp() * 1000),
            fields_mapping.get("notes"): budget_data.get("notes", "")
        }

        return self.add_record(self.budget_table, fields)

    # ========== 消费记录表操作 ==========

    def get_month_expenses(self, user_id: str) -> List[Dict[str, Any]]:
        """获取本月消费记录"""
        # 获取本月第一天的时间戳
        now = datetime.now()
        first_day = datetime(now.year, now.month, 1)
        first_day_ts = int(first_day.timestamp() * 1000)

        filter_condition = self.build_filter([{"field_name": "用户ID", "operator": "is", "value": [user_id]}, {"field_name": "消费时间", "operator": "isGreater", "value": ["ExactDate", str(first_day_ts)]}])

        records = self.query_records(self.expense_table, filter_condition)

        expenses = []
        for record in records:
            fields = record.get("fields", {})
            expenses.append({
                "record_id": record.get("record_id"),
                "amount": fields.get("金额", 0),
                "category": fields.get("类别", ""),
                "payment_method": fields.get("支付方式", ""),
                "merchant": fields.get("商家名称", ""),
                "budget_type": fields.get("预算类型", ""),
                "expense_time": fields.get("消费时间", "")
            })

        return expenses

    def add_expense(self, expense_data: Dict[str, Any]) -> bool:
        """添加消费记录"""
        fields_mapping = self.expense_table.get("fields", {})

        fields = {
            fields_mapping.get("user_id"): [{"id": expense_data.get("user_id", "")}],  # 人员字段格式
            fields_mapping.get("expense_time"): expense_data.get("expense_time", ""),
            fields_mapping.get("amount"): expense_data.get("amount", 0),
            fields_mapping.get("category"): expense_data.get("category", ""),
            fields_mapping.get("payment_method"): expense_data.get("payment_method", ""),
            fields_mapping.get("merchant"): expense_data.get("merchant", ""),
            fields_mapping.get("budget_type"): expense_data.get("budget_type", ""),
            fields_mapping.get("receipt_image"): expense_data.get("receipt_image", ""),
            fields_mapping.get("notes"): expense_data.get("notes", ""),
            fields_mapping.get("create_time"): expense_data.get("create_time", "")
        }

        return self.add_record(self.expense_table, fields)

    def save_expense(self, user_id: str, expense_data: Dict[str, Any]) -> bool:
        """保存消费记录"""
        fields_mapping = self.expense_table.get("fields", {})

        # 处理时间字段
        expense_time = expense_data.get("time")
        if expense_time:
            try:
                dt = datetime.strptime(expense_time, "%Y-%m-%d %H:%M")
                timestamp_ms = int(dt.timestamp() * 1000)
            except:
                timestamp_ms = int(datetime.now().timestamp() * 1000)
        else:
            timestamp_ms = int(datetime.now().timestamp() * 1000)

        fields = {
            fields_mapping.get("user_id"): [{"id": user_id}],
            fields_mapping.get("expense_time"): timestamp_ms,
            fields_mapping.get("amount"): expense_data.get("amount", 0),
            fields_mapping.get("category"): expense_data.get("category", ""),
            fields_mapping.get("payment_method"): expense_data.get("payment_method", ""),
            fields_mapping.get("merchant"): expense_data.get("merchant", ""),
            fields_mapping.get("budget_type"): expense_data.get("budget_type", ""),
            fields_mapping.get("notes"): expense_data.get("notes", ""),
            fields_mapping.get("create_time"): int(datetime.now().timestamp() * 1000)
        }

        return self.add_record(self.expense_table, fields)

    # ========== 债务表操作 ==========

    def get_user_debts(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的所有债务"""
        filter_condition = self.build_filter([{"field_name": "用户ID", "operator": "is", "value": [user_id]}])
        records = self.query_records(self.debt_table, filter_condition)

        debts = []
        for record in records:
            fields = record.get("fields", {})
            debts.append({
                "record_id": record.get("record_id"),
                "debt_type": fields.get("债务类型", ""),
                "debt_name": fields.get("债务名称", ""),
                "total_amount": fields.get("总金额", 0),
                "paid_amount": fields.get("已还金额", 0),
                "total_periods": fields.get("总期数", 0),
                "current_period": fields.get("当前期数", 0),
                "period_amount": fields.get("每期金额", 0),
                "status": fields.get("状态", "")
            })

        return debts

    def query_debt(self, user_id: str, debt_name: str) -> Optional[Dict[str, Any]]:
        """查询特定债务"""
        filter_condition = self.build_filter([{"field_name": "用户ID", "operator": "is", "value": [user_id]}, {"field_name": "债务名称", "operator": "is", "value": [debt_name]}])
        records = self.query_records(self.debt_table, filter_condition)

        if records:
            record = records[0]
            fields = record.get("fields", {})
            return {
                "record_id": record.get("record_id"),
                "debt_type": fields.get("债务类型", ""),
                "debt_name": fields.get("债务名称", ""),
                "total_amount": fields.get("总金额", 0),
                "paid_amount": fields.get("已还金额", 0),
                "total_periods": fields.get("总期数", 0),
                "current_period": fields.get("当前期数", 0),
                "period_amount": fields.get("每期金额", 0),
                "status": fields.get("状态", "")
            }
        return None

    def add_debt(self, debt_data: Dict[str, Any]) -> bool:
        """添加债务"""
        fields_mapping = self.debt_table.get("fields", {})

        fields = {
            fields_mapping.get("user_id"): [{"id": debt_data.get("user_id", "")}],  # 人员字段格式
            fields_mapping.get("debt_type"): debt_data.get("debt_type", ""),
            fields_mapping.get("debt_name"): debt_data.get("debt_name", ""),
            fields_mapping.get("total_amount"): debt_data.get("total_amount", 0),
            fields_mapping.get("paid_amount"): debt_data.get("paid_amount", 0),
            fields_mapping.get("total_periods"): debt_data.get("total_periods", 0),
            fields_mapping.get("current_period"): debt_data.get("current_period", 0),
            fields_mapping.get("period_amount"): debt_data.get("period_amount", 0),
            fields_mapping.get("next_payment_date"): debt_data.get("next_payment_date", ""),
            fields_mapping.get("status"): debt_data.get("status", "进行中"),
            fields_mapping.get("notes"): debt_data.get("notes", "")
        }

        return self.add_record(self.debt_table, fields)

    def update_debt(self, record_id: str, update_data: Dict[str, Any]) -> bool:
        """更新债务"""
        fields_mapping = self.debt_table.get("fields", {})

        fields = {}
        if "total_amount" in update_data:
            fields[fields_mapping.get("total_amount")] = update_data["total_amount"]
        if "paid_amount" in update_data:
            fields[fields_mapping.get("paid_amount")] = update_data["paid_amount"]
        if "current_period" in update_data:
            fields[fields_mapping.get("current_period")] = update_data["current_period"]
        if "status" in update_data:
            fields[fields_mapping.get("status")] = update_data["status"]
        if "notes" in update_data:
            fields[fields_mapping.get("notes")] = update_data["notes"]

        return self.update_record(self.debt_table, record_id, fields)

    def save_debt(self, user_id: str, debt_data: Dict[str, Any]) -> bool:
        """保存债务信息"""
        fields_mapping = self.debt_table.get("fields", {})

        fields = {
            fields_mapping.get("user_id"): [{"id": user_id}],
            fields_mapping.get("debt_type"): debt_data.get("type", ""),
            fields_mapping.get("debt_name"): debt_data.get("name", ""),
            fields_mapping.get("total_amount"): debt_data.get("total_amount", 0),
            fields_mapping.get("paid_amount"): debt_data.get("paid_amount", 0),
            fields_mapping.get("total_periods"): debt_data.get("total_periods", 0),
            fields_mapping.get("current_period"): debt_data.get("current_period", 0),
            fields_mapping.get("period_amount"): debt_data.get("period_amount", 0),
            fields_mapping.get("status"): "还款中",
            fields_mapping.get("notes"): debt_data.get("notes", "")
        }

        return self.add_record(self.debt_table, fields)
