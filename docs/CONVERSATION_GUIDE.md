# 多轮对话功能使用指南

## 功能概述

本系统现在支持多轮对话功能，当机器人处理请求时信息不足，可以向用户询问补充信息，用户回复后机器人会继续执行原任务。

## 核心组件

### 1. ConversationManager（会话管理器）

位置：`core/conversation_manager.py`

负责管理会话状态，包括：
- 创建和存储会话上下文
- 检查会话是否活跃
- 自动清理过期会话（默认30分钟）

### 2. BaseBot 新增方法

位置：`bots/base.py`

#### `ask_user()` 方法

向用户询问补充信息：

```python
def ask_user(
    self,
    chat_id: str,
    question: str,
    original_parts: List[MessagePart],
    callback_data: Optional[Dict[str, Any]] = None,
    original_user_id: Optional[str] = None
) -> str:
```

**参数说明：**
- `chat_id`: 会话 ID
- `question`: 要问的问题
- `original_parts`: 原始消息内容
- `callback_data`: 回调需要的数据（用于继续处理）
- `original_user_id`: 原始发送者ID

**返回值：**
- 提问消息（会发送给用户）

#### `handle_user_response()` 方法

处理用户的补充回复：

```python
def handle_user_response(
    self,
    chat_id: str,
    parts: List[MessagePart],
    user_id: Optional[str] = None
) -> Optional[str]:
```

**默认行为：**
- 将原始消息和用户回复合并
- 重新调用 `process_messages()` 处理

**自定义处理：**
- 子类可以重写此方法实现自定义逻辑
- 返回 `None` 表示需要子类自行处理

## 使用示例

### 示例 1：简单的信息补充

```python
class MyBot(BaseBot):
    def process_messages(self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]) -> str:
        user_message = " ".join([p.text for p in parts if p.kind == "text"])

        # 检查信息是否完整
        if "创建任务" in user_message and "截止日期" not in user_message:
            # 信息不足，询问用户
            return self.ask_user(
                chat_id=chat_id,
                question="请问这个任务的截止日期是什么时候？",
                original_parts=parts
            )

        # 信息完整，正常处理
        return self._create_task(user_message)
```

### 示例 2：自定义回复处理

```python
class MyBot(BaseBot):
    def process_messages(self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]) -> str:
        user_message = " ".join([p.text for p in parts if p.kind == "text"])

        if "预订" in user_message and "人数" not in user_message:
            # 保存预订信息到 callback_data
            callback_data = {
                "action": "booking",
                "restaurant": "某餐厅",
                "time": "晚上7点"
            }

            return self.ask_user(
                chat_id=chat_id,
                question="请问有几位用餐？",
                original_parts=parts,
                callback_data=callback_data
            )

        return self._process_booking(user_message)

    def handle_user_response(self, chat_id: str, parts: List[MessagePart], user_id: Optional[str] = None) -> Optional[str]:
        """自定义处理用户回复"""
        context = self.conversation_manager.get_conversation(chat_id)
        if not context:
            return None

        # 提取用户回复
        user_reply = " ".join([p.text for p in parts if p.kind == "text"])

        # 获取之前保存的数据
        action = context.callback_data.get("action")

        if action == "booking":
            restaurant = context.callback_data.get("restaurant")
            time = context.callback_data.get("time")

            # 完成会话
            self.conversation_manager.complete_conversation(chat_id)

            # 处理预订
            return f"已为您预订 {restaurant}，{time}，{user_reply} 位"

        return None
```

## 演示 Bot

位置：`bots/demo_conversation/bot.py`

这是一个完整的演示 Bot，展示了如何使用多轮对话功能。

### 功能演示

1. 用户发送："创建任务：完成项目报告"
2. Bot 检测到缺少截止日期，询问："请问这个任务的截止日期是什么时候？"
3. 用户回复："下周五"
4. Bot 继续处理并创建任务

### 配置演示 Bot

1. 修改 `bots/demo_conversation/config.yaml`，填入你的飞书应用配置：
   ```yaml
   feishu:
     app_id: "YOUR_APP_ID"
     app_secret: "YOUR_APP_SECRET"
   ```

2. 在 `config/bots.yaml` 中添加：
   ```yaml
   bots:
     demo_conversation:
       enabled: true
       module: "bots.demo_conversation.bot"
       class: "DemoConversationBot"
       config_file: "bots/demo_conversation/config.yaml"
   ```

3. 启动机器人：
   ```bash
   python main.py
   ```

## 工作流程

```
用户发送消息
    ↓
Bot.process_messages() 检测信息不足
    ↓
Bot.ask_user() 创建会话并询问用户
    ↓
ConversationManager 保存会话状态
    ↓
用户回复补充信息
    ↓
系统检测到活跃会话
    ↓
Bot.handle_user_response() 处理回复
    ↓
完成原任务并返回结果
```

## 注意事项

1. **会话过期时间**：默认 30 分钟，可在创建会话时自定义
2. **会话清理**：过期会话会自动清理，每 5 分钟检查一次
3. **线程安全**：ConversationManager 使用锁保证线程安全
4. **状态管理**：每个 chat_id 只能有一个活跃会话
5. **错误处理**：如果用户长时间不回复，会话会自动过期

## 高级用法

### 多步骤信息收集

```python
def process_messages(self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]) -> str:
    # 检查会话状态
    context = self.conversation_manager.get_conversation(chat_id)

    if context:
        step = context.callback_data.get("step", 0)

        if step == 1:
            # 收集第二个信息
            self.conversation_manager.update_conversation(
                chat_id,
                callback_data={"step": 2, "info1": user_input}
            )
            return self.ask_user(chat_id, "请提供第二个信息", parts)

        elif step == 2:
            # 收集完成，处理任务
            info1 = context.callback_data.get("info1")
            info2 = user_input
            return self._process_task(info1, info2)

    # 开始收集第一个信息
    return self.ask_user(
        chat_id,
        "请提供第一个信息",
        parts,
        callback_data={"step": 1}
    )
```

### 条件分支处理

```python
def handle_user_response(self, chat_id: str, parts: List[MessagePart], user_id: Optional[str] = None) -> Optional[str]:
    context = self.conversation_manager.get_conversation(chat_id)
    if not context:
        return None

    action_type = context.callback_data.get("action_type")

    if action_type == "confirm":
        # 处理确认类回复
        return self._handle_confirmation(parts, context)
    elif action_type == "input":
        # 处理输入类回复
        return self._handle_input(parts, context)
    else:
        # 默认处理
        return super().handle_user_response(chat_id, parts, user_id)
```

## 故障排查

### 问题 1：会话没有被检测到

**原因**：会话可能已过期或未正确创建

**解决**：
- 检查 `ask_user()` 是否被正确调用
- 检查会话过期时间设置
- 查看日志确认会话创建

### 问题 2：用户回复后没有继续处理

**原因**：`handle_user_response()` 返回了 `None`

**解决**：
- 确保重写的 `handle_user_response()` 返回了有效的字符串
- 或者使用默认实现（不重写该方法）

### 问题 3：多个用户的会话互相干扰

**原因**：使用了相同的 `chat_id`

**解决**：
- 确保每个对话使用唯一的 `chat_id`
- 私聊和群聊的 `chat_id` 是不同的

## 总结

多轮对话功能让机器人能够：
- ✅ 主动询问用户补充信息
- ✅ 保存对话上下文
- ✅ 自动管理会话状态
- ✅ 支持自定义处理逻辑
- ✅ 线程安全且自动清理

这使得机器人能够处理更复杂的交互场景，提供更好的用户体验。
