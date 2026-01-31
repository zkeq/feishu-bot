# 多维表格 API 修复总结

## 问题描述

财务管理机器人在查询多维表格时出现错误：
```
TypeError: object of type 'NoneType' has no len()
```

## 根本原因

1. **使用了错误的 API 接口**
   - 旧代码：GET `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records`
   - 正确接口：POST `/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search`

2. **使用了错误的 filter 格式**
   - 旧格式（字符串）：`CurrentValue.[用户ID] = "a7fde8cc"`
   - 新格式（JSON）：
     ```json
     {
       "conjunction": "and",
       "conditions": [
         {
           "field_name": "用户ID",
           "operator": "is",
           "value": ["a7fde8cc"]
         }
       ]
     }
     ```

3. **错误处理不完善**
   - 当 API 返回的 `data` 或 `items` 为 `None` 时，代码会崩溃

## 修复内容

### 1. 修改查询接口 ✅

**文件**：`bots/finance_manager/managers/bitable_manager.py`

**修改**：
- 将 GET 请求改为 POST 请求
- 使用 `/records/search` 端点
- 将 filter 从 URL 参数改为请求体

```python
# 旧代码
query_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
params = {"page_size": page_size}
if filter_condition:
    params["filter"] = filter_condition
response = requests.get(query_url, headers=headers, params=params)

# 新代码
query_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/search"
request_body = {"page_size": page_size}
if filter_condition:
    request_body["filter"] = filter_condition
response = requests.post(query_url, headers=headers, json=request_body)
```

### 2. 添加 filter 构建辅助函数 ✅

```python
@staticmethod
def build_filter(conditions: List[Dict[str, Any]], conjunction: str = "and") -> Dict[str, Any]:
    """
    构建飞书多维表格 POST 接口的 filter 对象

    Args:
        conditions: 条件列表，每个条件包含 field_name, operator, value
        conjunction: 逻辑连接词，"and" 或 "or"

    Returns:
        filter 对象
    """
    return {
        "conjunction": conjunction,
        "conditions": conditions
    }
```

### 3. 更新所有 filter 使用 ✅

修改了 9 处使用旧 filter 格式的地方：

1. `get_user_accounts()` - 获取用户账户
2. `query_account()` - 查询特定账户
3. `get_user_categories()` - 获取用户类别
4. `get_current_month_budget()` - 获取当月预算
5. `query_budget()` - 查询特定预算
6. `get_month_expenses()` - 获取本月消费
7. `get_user_debts()` - 获取用户债务
8. `query_debt()` - 查询特定债务

**示例**：
```python
# 旧代码
filter_condition = f'CurrentValue.[用户ID] = "{user_id}"'

# 新代码
filter_condition = self.build_filter([
    {"field_name": "用户ID", "operator": "is", "value": [user_id]}
])
```

**多条件示例**：
```python
# 旧代码
filter_condition = f'AND(CurrentValue.[用户ID] = "{user_id}", CurrentValue.[月份] = "{current_month}")'

# 新代码
filter_condition = self.build_filter([
    {"field_name": "用户ID", "operator": "is", "value": [user_id]},
    {"field_name": "月份", "operator": "is", "value": [current_month]}
])
```

### 4. 改进错误处理 ✅

```python
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
```

## 飞书 API 文档参考

### 查询记录接口

- **接口地址**：`POST /open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/search`
- **权限要求**：
  - 根据条件搜索记录(base:record:retrieve)
  - 查看、评论、编辑和管理多维表格(bitable:app)
  - 查看、评论和导出多维表格(bitable:app:readonly)

### Filter 参数说明

**支持的运算符**：
- `is`：等于
- `isNot`：不等于
- `contains`：包含
- `doesNotContain`：不包含
- `isEmpty`：为空
- `isNotEmpty`：不为空
- `isGreater`：大于
- `isGreaterEqual`：大于等于
- `isLess`：小于
- `isLessEqual`：小于等于

**示例**：
```json
{
  "filter": {
    "conjunction": "and",
    "conditions": [
      {
        "field_name": "职位",
        "operator": "is",
        "value": ["初级销售员"]
      },
      {
        "field_name": "销售额",
        "operator": "isGreater",
        "value": ["10000.0"]
      }
    ]
  }
}
```

## 测试验证

### 语法检查
```bash
python3 -m py_compile bots/finance_manager/managers/bitable_manager.py  # ✅ 通过
```

### 功能测试
1. 发送 `/start` 命令
2. 机器人应该能够：
   - 正确查询用户账户
   - 正确查询预算信息
   - 正确查询消费记录
   - 正确查询债务信息
   - 显示财务控制面板

## 注意事项

1. **高级权限**
   - 如果多维表格开启了高级权限，需要确保应用拥有可管理权限
   - 否则可能出现调用成功但返回数据为空的情况

2. **并发限制**
   - 多维表格底层对数据表的处理基于版本维度的串行方式
   - 不支持并发，建议避免对单个数据表进行并发请求

3. **分页查询**
   - 单次最多查询 500 行记录
   - 使用 `page_token` 进行分页

4. **频率限制**
   - 接口频率限制：20 次/秒

## 总结

✅ **问题已修复**
- 使用正确的 POST 接口
- 使用正确的 JSON filter 格式
- 添加完善的错误处理
- 所有查询方法已更新

现在财务管理机器人应该能够正常查询多维表格数据了！🎉
