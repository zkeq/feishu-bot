# 飞书机器人框架 - 多连接管理模式

一个可扩展的飞书机器人框架，支持多种 Bot 应用。**一个进程管理多个 WebSocket 连接，每个 Bot 独立配置飞书应用。**

## 🎯 架构特点

- **多连接管理**: 一个进程运行多个 Bot，每个 Bot 独立的 WebSocket 连接
- **独立应用**: 每个 Bot 使用独立的飞书 APP_ID 和 APP_SECRET
- **可扩展**: 轻松添加新的 Bot 应用
- **模块化**: 核心功能与业务逻辑分离
- **配置驱动**: 通过配置文件管理多个 Bot
- **流式响应**: 支持 AI 流式输出，实时更新
- **智能批处理**: 自动合并时间窗口内的消息，带倒计时显示
- **状态反馈**: 实时显示处理进度

## 📁 项目结构

```
feishu-bot/
├── core/                      # 核心框架（所有 Bot 共享）
│   ├── __init__.py           # 模块导出
│   ├── client.py             # 飞书客户端封装
│   ├── batcher.py            # 消息批处理器（状态更新、倒计时）
│   ├── ai_client.py          # AI 客户端（流式/非流式）
│   └── utils.py              # 工具函数（Markdown 预处理）
├── bots/                      # Bot 实现（每个 Bot 独立目录）
│   ├── __init__.py           # Bots 模块
│   ├── base.py               # Bot 基类
│   └── food_analyzer/        # 饮食分析 Bot
│       ├── __init__.py      # Bot 模块导出
│       ├── bot.py           # 业务逻辑
│       └── config.yaml      # Bot 配置（含独立的飞书应用配置）
├── config/
│   └── bots.yaml             # Bot 注册和路由配置
├── .env                       # 全局配置（OpenAI API）
└── main.py                    # 多连接管理入口
```

## 🚀 快速开始

### 1. 配置全局环境变量

编辑 `.env` 文件（所有 Bot 共享的配置）：

```bash
# OpenAI 配置（所有 Bot 共享）
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
```

**注意**: 飞书应用配置（APP_ID/APP_SECRET）现在在每个 Bot 的 config.yaml 中独立配置。

### 2. 配置 Bot

每个 Bot 有自己的配置文件。以 `food_analyzer` 为例：

编辑 `bots/food_analyzer/config.yaml`：

```yaml
name: "饮食分析助手"
description: "分析饮食热量和营养成分"

# 飞书应用配置（每个 Bot 独立）
feishu:
  app_id: "cli_xxxxx"
  app_secret: "your_app_secret"
  ws_insecure: true  # WebSocket SSL 配置

# Bot 专属的系统提示词
system_prompt: |
  你是一个专业的饮食分析助手...

# OpenAI 配置
openai:
  model: "gpt-4o-mini"
  temperature: 0.7
  max_tokens: 2000

# 批处理配置
batch:
  window_seconds: 12  # 消息合并窗口（秒）
```

### 3. 启用 Bot

编辑 `config/bots.yaml`，启用你的 Bot：

```yaml
bots:
  food_analyzer:
    enabled: true  # 设置为 true 启用
    module: "bots.food_analyzer.bot"
    class: "FoodAnalyzerBot"
    config_file: "bots/food_analyzer/config.yaml"
```

### 4. 启动框架

```bash
python main.py
```

框架会自动：
- 加载所有 `enabled: true` 的 Bot
- 为每个 Bot 创建独立的飞书客户端和 WebSocket 连接
- 在独立线程中运行每个 Bot
- 所有 Bot 共享一个 AI 客户端（节省资源）

## 🤖 创建新的 Bot

### 1. 创建 Bot 目录

```bash
mkdir -p bots/my_bot
touch bots/my_bot/__init__.py
```

### 2. 创建配置文件

`bots/my_bot/config.yaml`:

```yaml
name: "我的机器人"
description: "做什么的"

# 飞书应用配置（独立的 APP）
feishu:
  app_id: "cli_xxxxx"
  app_secret: "your_app_secret"
  ws_insecure: true

# Bot 专属的系统提示词
system_prompt: |
  你是一个...

  注意：飞书 lark_md 格式限制
  - 标题用 **加粗** 代替，不要用 # ## ###
  - 不要使用引用块 (>)
  - 不要使用斜体 (_text_)
  - 不要在加粗后再加星号

# OpenAI 配置
openai:
  model: "gpt-4o-mini"
  temperature: 0.7
  max_tokens: 2000

# 批处理配置
batch:
  window_seconds: 12
```

### 3. 实现 Bot 类

`bots/my_bot/__init__.py`:
```python
from .bot import MyBot
__all__ = ["MyBot"]
```

`bots/my_bot/bot.py`:

```python
import logging
from typing import Any, Dict, List, Optional

from bots.base import BaseBot
from core.batcher import MessagePart
from core.ai_client import AIClient

logger = logging.getLogger(__name__)


class MyBot(BaseBot):
    """我的机器人"""

    def __init__(self, config: Dict[str, Any], client, ai_client: AIClient):
        super().__init__(config, client)
        self.ai_client = ai_client
        self.openai_model = config.get("openai", {}).get("model", "gpt-4o-mini")
        self.openai_temperature = config.get("openai", {}).get("temperature", 0.7)
        self.openai_max_tokens = config.get("openai", {}).get("max_tokens")

    def process_messages(
        self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]
    ) -> str:
        """处理消息并返回回复"""

        # 1. 构建 AI 消息（可参考 food_analyzer/bot.py）
        messages = self._build_ai_messages(parts)

        # 2. 调用 AI（支持流式更新）
        if status_msg_id:
            result = self._call_ai_streaming(chat_id, messages, status_msg_id)
        else:
            result = self.ai_client.call(
                messages=messages,
                model=self.openai_model,
                temperature=self.openai_temperature,
                max_tokens=self.openai_max_tokens,
            )

        return result
```

### 4. 注册 Bot

在 `config/bots.yaml` 中添加：

```yaml
bots:
  my_bot:
    enabled: true
    module: "bots.my_bot.bot"
    class: "MyBot"
    config_file: "bots/my_bot/config.yaml"
```

### 5. 启动框架

```bash
python main.py
```

框架会自动加载并启动你的 Bot！

## 📊 多维表格集成（可选）

在 Bot 配置中启用多维表格：

```yaml
bitable:
  enabled: true
  app_token: "your_app_token"
  table_id: "your_table_id"
  fields:
    date: "日期"
    content: "内容"
```

在 Bot 中实现数据保存逻辑（参考 `food_analyzer/bot.py` 的 `_save_to_bitable` 方法）。

## 🔧 核心功能详解

### 1. 飞书客户端 (FeishuClient)

封装常用的飞书 API 操作：

```python
from core.client import FeishuClient

# 每个 Bot 有独立的客户端
client = FeishuClient(app_id, app_secret)

# 发送消息（返回 message_id）
msg_id = client.send_message(chat_id, content, msg_type="interactive")

# 更新消息（用于流式输出）
client.update_message(message_id, new_content)

# 撤回消息
client.delete_message(message_id)

# 获取图片资源
image_data = client.get_image_resource(message_id, image_key)
```

### 2. 消息批处理器 (MessageBatcher)

自动合并时间窗口内的多条消息，并显示实时状态：

```python
from core.batcher import MessageBatcher

# 创建批处理器（独立实例）
batcher = MessageBatcher(window_seconds=12, client=client)

# 添加消息（会自动发送状态消息）
batcher.add(chat_id, parts, callback)
```

功能特性：
- **倒计时显示**: 每秒更新，显示剩余合并时间
- **消息统计**: 显示当前窗口内的消息数量（文本/图片）
- **智能撤回**: 新消息到来时自动撤回旧状态，发送新状态
- **状态追踪**: 实时显示处理进度

### 3. AI 客户端 (AIClient)

统一的 AI API 接口，支持流式和非流式调用：

```python
from core.ai_client import AIClient

# 所有 Bot 共享一个 AI 客户端
ai_client = AIClient(api_key, base_url)

# 非流式调用
result = ai_client.call(
    messages=[{"role": "user", "content": "Hello"}],
    model="gpt-4o-mini",
    temperature=0.7,
    max_tokens=2000
)

# 流式调用（带实时更新回调）
def update_callback(content: str):
    # 更新飞书消息
    client.update_message(msg_id, format_content(content))

result = ai_client.call_streaming(
    messages=messages,
    model="gpt-4o-mini",
    update_callback=update_callback,
    update_interval=0.5  # 每0.5秒更新一次
)
```

### 4. Markdown 预处理 (preprocess_markdown_for_feishu)

适配飞书 lark_md 格式限制：

```python
from core.utils import preprocess_markdown_for_feishu

# 将标题转换为加粗
text = "# 标题\n内容"
result = preprocess_markdown_for_feishu(text)
# 输出: "**标题**\n内容"
```

## 🎨 Bot 实现示例

### 饮食分析 Bot (food_analyzer)

**功能**:
- 分析饮食热量和营养成分
- 支持文字描述 + 图片识别
- 流式输出分析结果
- 可选保存到多维表格

**配置亮点**:
```yaml
feishu:
  app_id: "cli_xxxxx"  # 独立的飞书应用
  app_secret: "xxxxx"

system_prompt: |
  你是一个专业的饮食分析助手...

  注意：飞书 lark_md 格式限制
  - 不要使用引用块 (>)
  - 不要使用斜体
  - 标题用加粗

openai:
  model: "gemini-2.5-pro"  # 支持任何 OpenAI 兼容的模型
  temperature: 0.7
```

## 📝 开发指南

### Bot 生命周期

```
启动 (main.py)
  ↓
加载配置 (config/bots.yaml + bot config.yaml)
  ↓
创建 Bot 实例 (BotInstance)
  ├─ 独立的 FeishuClient
  ├─ 独立的 MessageBatcher
  └─ 共享的 AIClient
  ↓
启动 WebSocket 连接 (独立线程)
  ↓
接收消息事件
  ↓
解析消息 → 添加到批处理队列
  ↓
发送初始状态消息（倒计时开始）
  ↓
等待批处理窗口（可能撤回并更新状态）
  ↓
触发 Bot.process_messages()
  ↓
调用 AI（流式更新消息内容）
  ↓
返回最终结果
```

### 架构优势

1. **独立隔离**: 每个 Bot 使用独立的飞书应用，互不干扰
2. **资源共享**: 所有 Bot 共享 AI 客户端，节省连接和成本
3. **统一管理**: 单进程管理所有 Bot，便于监控和运维
4. **易于扩展**: 添加新 Bot 只需创建目录和配置

### 最佳实践

1. **配置优先**: 所有可配置的内容都放在 `config.yaml` 中
2. **日志记录**: 使用 `logger` 记录关键操作，便于调试
3. **异常处理**: 实现错误处理，避免单个 Bot 崩溃影响其他 Bot
4. **状态反馈**: 利用流式更新给用户实时反馈
5. **格式适配**: 在 system_prompt 中明确说明飞书 lark_md 的格式限制

### 飞书 lark_md 格式注意事项

飞书的 Markdown 支持有限，需要注意：

**✅ 支持的语法**:
- 加粗: `**文本**`
- 列表: `• 项目` 或 `1. 项目`
- 链接: `[文本](url)`
- 代码块: ` ```code``` `

**❌ 不支持/有问题的语法**:
- 标题: `# ## ###` (用加粗代替)
- 引用块: `>` (直接写文本)
- 斜体: `*text*` 或 `_text_` (容易产生多余星号)
- 嵌套列表: 可能渲染不正确

**解决方案**: 在 Bot 的 `system_prompt` 中明确告知 AI 这些限制。

## 📄 许可证

MIT
