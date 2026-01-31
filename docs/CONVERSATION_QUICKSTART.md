# 多轮对话功能 - 快速开始

## 功能说明

当机器人处理请求时信息不足，可以向用户询问补充信息，用户回复后机器人会继续执行原任务。

## 快速使用

### 1. 在你的 Bot 中使用

```python
from bots.base import BaseBot
from core.batcher import MessagePart

class MyBot(BaseBot):
    def process_messages(self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]) -> str:
        # 提取用户消息
        user_message = " ".join([p.text for p in parts if p.kind == "text"])

        # 检查信息是否完整
        if "创建任务" in user_message:
            # 检查是否有截止日期
            if "截止" not in user_message and "日期" not in user_message:
                # 信息不足，询问用户
                question = self.ask_user(
                    chat_id=chat_id,
                    question="请问这个任务的截止日期是什么时候？",
                    original_parts=parts,
                    callback_data={"action": "create_task", "description": user_message}
                )

                # 发送提问消息
                if status_msg_id:
                    self.client.update_message(status_msg_id, {"text": question})
                else:
                    self.client.send_message(chat_id, question)

                return question

        # 信息完整，正常处理
        return self._process_task(user_message)
```

### 2. 自定义处理用户回复（可选）

如果你需要自定义处理逻辑，可以重写 `handle_user_response` 方法：

```python
def handle_user_response(self, chat_id: str, parts: List[MessagePart], user_id: Optional[str] = None) -> Optional[str]:
    # 获取会话上下文
    context = self.conversation_manager.get_conversation(chat_id)
    if not context:
        return None

    # 提取用户回复
    user_reply = " ".join([p.text for p in parts if p.kind == "text"])

    # 获取之前保存的数据
    action = context.callback_data.get("action")
    description = context.callback_data.get("description")

    # 完成会话
    self.conversation_manager.complete_conversation(chat_id)

    # 处理任务
    return f"任务已创建：{description}，截止日期：{user_reply}"
```

## 测试演示 Bot

项目中包含了一个完整的演示 Bot：`bots/demo_conversation/bot.py`

### 配置步骤

1. 修改配置文件 `bots/demo_conversation/config.yaml`：
   ```yaml
   feishu:
     app_id: "YOUR_APP_ID"
     app_secret: "YOUR_APP_SECRET"
   ```

2. 在 `config/bots.yaml` 中启用：
   ```yaml
   bots:
     demo_conversation:
       enabled: true
       module: "bots.demo_conversation.bot"
       class: "DemoConversationBot"
       config_file: "bots/demo_conversation/config.yaml"
   ```

3. 运行测试：
   ```bash
   python3 test_conversation.py  # 测试会话管理器
   python3 main.py               # 启动机器人
   ```

### 测试场景

1. 发送："创建任务：完成项目报告"
2. Bot 回复："请问这个任务的截止日期是什么时候？"
3. 回复："下周五"
4. Bot 回复："✅ 任务创建成功！..."

## 核心 API

### `ask_user()` - 询问用户

```python
self.ask_user(
    chat_id=chat_id,              # 会话ID
    question="你的问题？",         # 要问的问题
    original_parts=parts,         # 原始消息
    callback_data={...},          # 保存的数据（可选）
    original_user_id=user_id      # 用户ID（可选）
)
```

### `handle_user_response()` - 处理回复

```python
def handle_user_response(self, chat_id, parts, user_id=None):
    context = self.conversation_manager.get_conversation(chat_id)
    # 处理用户回复
    # 返回结果消息
    return "处理结果"
```

## 更多信息

详细文档请查看：`docs/CONVERSATION_GUIDE.md`

## 技术支持

如有问题，请查看：
- 完整文档：`docs/CONVERSATION_GUIDE.md`
- 示例代码：`bots/demo_conversation/bot.py`
- 测试脚本：`test_conversation.py`
