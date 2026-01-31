# 🤖 Zkeq 的生活 - 飞书智能机器人框架

> 一个强大、灵活、易扩展的飞书机器人开发框架，支持多 Bot 管理、AI 智能分析、批量处理等高级功能。

<img width="1586" height="1992" alt="image" src="https://github.com/user-attachments/assets/ecd32c84-2d64-4b26-97f7-32b8bc2a36a2" />

<img width="1586" height="1767" alt="image" src="https://github.com/user-attachments/assets/2959d089-5b52-4261-8b6b-7e9df02cfe2b" />

<img width="1587" height="1992" alt="image" src="https://github.com/user-attachments/assets/409ea0d7-fed3-42aa-8def-bbf43bf7d6ee" />

<img width="3840" height="2160" alt="image" src="https://github.com/user-attachments/assets/9044c98d-f7fb-47ef-91df-da9ce1d3475b" />

<img width="3839" height="2160" alt="image" src="https://github.com/user-attachments/assets/40997820-d49a-4272-ba28-5b4543563c95" />


[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

## ✨ 核心特性

### 🏗️ 框架能力

- **多 Bot 管理**：单进程管理多个飞书机器人，每个 Bot 独立配置
- **消息批处理**：智能合并时间窗口内的多条消息，提升用户体验
- **WebSocket 长连接**：实时接收消息，低延迟响应
- **插件化架构**：轻松扩展新功能，开发自己的 Bot
- **高可用设计**：AI API 主备双源 + 自动重试，保证 100% 可用

### 🍽️ 饮食分析 Bot

内置的饮食分析机器人，提供专业的营养分析和健康建议：

- **🖼️ 智能图片识别**：上传食物照片，自动识别并分析营养成分
- **⚡ 批量并行处理**：一次上传多张照片，并行分析，快速响应
- **📅 时间识别**：自动提取图片水印时间，或识别文字中的日期表达
- **📊 多维表格集成**：一键导入饮食记录到飞书多维表格
- **💬 流式响应**：实时显示 AI 分析过程，体验更流畅
- **🎯 营养评分**：基于科学算法对每餐进行健康评分

### 💰 财务管家 Bot

功能全面的个人财务管理机器人，帮你管钱、省钱、理财：

- **🏠 智能控制面板**：输入 `/start` 查看财务概览，一键访问所有功能
- **📊 财务状态管理**：自动计算总资产、总负债、净资产，实时追踪财务健康度
- **💰 预算规划**：基于"大额合并原则"的预算管理，区分固定支出和可变支出
- **💸 消费记录**：支持文字描述和收据图片识别，AI智能匹配支付方式到账户
- **💳 债务管理**：区分日常负债（花呗/信用卡）和分期债务，自动追踪还款进度
- **🤖 AI 智能助手**：自然语言理解，主动查询数据库给出准确答案
- **🔄 表联动**：消费记录自动更新账户余额和预算执行情况

详细文档：[财务管家 README](bots/finance_manager/README.md)

## 🚀 快速开始

### 环境要求

- Python 3.9+
- 飞书企业账号
- OpenAI API（或兼容的 API 服务）

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/zkeq/feishu-bot.git
cd feishu-bot
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **配置环境变量**

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API 配置：

```env
# 主 API 配置
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# 备用 API 配置（可选，用于故障转移）
OPENAI_API_KEY_BACKUP=your-backup-api-key
OPENAI_BASE_URL_BACKUP=https://backup-api.example.com/v1

# 重试配置
API_MAX_RETRIES=3
API_RETRY_DELAY=2
```

4. **配置飞书 Bot**

复制配置模板并填入你的飞书应用配置：

```bash
cp bots/food_analyzer/config.example.yaml bots/food_analyzer/config.yaml
cp config/bots.example.yaml config/bots.yaml
```

编辑 `bots/food_analyzer/config.yaml`：

```yaml
feishu:
  app_id: "your_app_id"
  app_secret: "your_app_secret"
```

编辑 `config/bots.yaml`，填入你的群组 ID：

```yaml
routes:
  by_chat_id:
    "oc_your_chat_id_here": "food_analyzer"
```

5. **启动框架**

```bash
python main.py
```

看到以下输出表示启动成功：

```
飞书机器人框架启动中...
Bot 加载成功: food_analyzer (饮食分析助手)
所有 Bot 已启动，等待消息...
```

## 📖 使用指南

### 饮食分析 Bot 使用

#### 1. 单张图片分析

直接在飞书中上传食物照片：

```
[上传照片]
今天的午餐
```

机器人会返回：
- ✅ 详细的营养分析
- ✅ 热量、蛋白质、碳水、脂肪计算
- ✅ 健康建议和评分
- ✅ 一键导入按钮

#### 2. 批量处理多张图片

一次性上传多张照片（2张及以上）：

```
[上传3张照片]
今天的饮食记录
```

机器人会：
1. **并行分析**所有图片（快速响应）
2. 每张图片发送**独立的分析消息**
3. 最后发送**汇总统计**（总热量、营养总计等）
4. 提供**批量导入**功能

#### 3. 日期时间识别

支持多种日期表达方式：

```
[上传照片]
昨天中午吃的麻辣香锅
```

或者让 AI 自动识别图片水印时间：

```
[上传带时间水印的照片：2026-01-20 12:30]
```

AI 会自动提取并使用正确的日期时间。

### 导入到多维表格

1. 点击分析结果下方的 **"📥 导入到多维表格"** 按钮
2. 确认导入
3. 数据自动保存到飞书多维表格，包括：
   - 日期时间
   - 餐次类型
   - 食物内容
   - 营养数据
   - 图片附件
   - 评分和备注

### 财务管家 Bot 使用

#### 典型使用流程

财务管家 Bot 的推荐使用流程：

1. **📊 初始化财务状态**
   首先告诉机器人你当前的财务情况，包括存款、花呗、信用卡等所有账户信息。机器人会自动创建账户并计算你的净资产。

2. **💰 设置月度预算**
   告诉机器人你每个月各个方面的预算计划，包括收入和各项支出。机器人会帮你追踪预算执行情况。

3. **🤔 消费前咨询**
   每次买东西之前，可以问机器人"我还能买吗？"或"我这个月还剩多少预算？"，机器人会查询你的预算和账户余额，给出建议。

4. **📸 消费后记账**
   买完东西后，直接发送收据截图或文字描述给机器人。系统会自动：
   - 识别商家、金额、时间
   - AI 智能匹配支付方式到对应账户
   - 自动记账并扣除账户余额
   - 更新预算执行情况

5. **💳 记录分期债务**
   如果有信用卡分期或其他分期付款，告诉机器人分期信息。机器人会创建债务记录，追踪还款进度。

6. **📈 定期查看**
   随时发送 `/start` 查看财务控制面板，了解资产负债情况和预算执行进度。

---

#### 1. 打开控制面板

在飞书中发送 `/start` 命令：

```
/start
```

机器人会显示财务控制面板，包括：
- 📊 财务概览（总资产、总负债、净资产）
- 💰 本月预算执行情况
- 🏦 账户概览
- 💳 债务概览
- 功能按钮（编辑计划、财务询问、记录消费等）

#### 2. 更新财务状态

使用自然语言告诉机器人你的财务状态：

```
小荷包存款1.22w，花呗欠1803，信用卡欠3858
```

机器人会自动：
- 创建或更新账户
- 计算总资产和总负债
- 显示净资产
- 提供确认按钮

#### 3. 创建预算计划

告诉机器人你的预算计划：

```
本月收入8.8w，支出预算：房租1800、个人费用2000、应急资金200
```

机器人会：
- 创建收入和支出预算
- 自动分类（固定支出/可变支出）
- 追踪预算执行情况

#### 4. 记录消费

**方式1：文字描述**
```
在爱家驿站买水花了6.5元，用花呗付的
```

**方式2：发送收据图片**
- 直接发送收据照片
- AI自动识别商家、金额、时间
- 图片自动保存到消费记录

机器人会自动：
- 创建消费记录
- AI智能匹配支付方式到账户（如"花呗"→"花呗"账户）
- 更新账户余额
- 更新预算执行情况

#### 5. 添加分期债务

```
买了iPhone，分3期，每期1333元，总共4000元
```

机器人会：
- 创建债务分期记录
- 追踪还款进度
- 计算剩余期数

#### 6. 财务询问

直接问问题，机器人会查询数据库回答：

```
我这个月还剩多少预算？
```

机器人会：
- 查询预算表
- 查询消费记录
- 计算剩余预算
- 给出消费建议

### 财务管家配置教程

#### 1. 创建飞书多维表格

在飞书中创建4个多维表格：

**表1：财务账户表**
- 用户ID（人员）
- 账户名称（文本）
- 账户类型（单选：存款/债务/分期/投资）
- 当前余额（数字）
- 更新时间（日期）
- 状态（单选：活跃/已关闭）
- 备注（文本）

**表2：预算计划表**
- 用户ID（人员）
- 月份（文本，格式：YYYY-MM）
- 类型（单选：收入/固定支出/可变支出/应急）
- 类别名称（文本）
- 预算金额（数字）
- 实际金额（数字）
- 创建时间（日期）
- 备注（文本）

**表3：消费记录表**
- 用户ID（人员）
- 消费时间（日期）
- 金额（数字）
- 类别（单选）
- 支付方式（单选）
- 商家名称（文本）
- 预算类型（单选）
- 收据图片（附件）
- 备注（文本）
- 创建时间（日期）

**表4：债务分期表**
- 用户ID（人员）
- 债务类型（单选：分期付款/借款）
- 债务名称（文本）
- 总金额（数字）
- 已还金额（多行文本）
- 总期数（数字）
- 当前期数（数字）
- 每期金额（数字）
- 下次还款日（日期）
- 状态（单选：进行中/已结清）
- 备注（文本）

#### 2. 配置财务管家

复制多维表格模版: https://zkeq-life.feishu.cn/base/RHNPb2Z0Aa021VsJoZYcPGEqnCh?from=from_copylink

复制配置模板：

```bash
cp bots/finance_manager/config.example.yaml bots/finance_manager/config.yaml
```

编辑 `bots/finance_manager/config.yaml`，填入你的配置：

```yaml
# 飞书应用配置
feishu:
  app_id: "你的app_id"
  app_secret: "你的app_secret"

# 多维表格配置
bitable:
  enabled: true
  app_token: "你的多维表格app_token"

  # 财务账户表
  accounts_table:
    table_id: "你的table_id"
    fields:
      user_id: "用户ID"
      account_name: "账户名称"
      # ... 其他字段

  # 预算计划表
  budget_table:
    table_id: "你的table_id"
    # ... 字段配置

  # 消费记录表
  expense_table:
    table_id: "你的table_id"
    # ... 字段配置

  # 债务分期表
  debt_table:
    table_id: "你的table_id"
    # ... 字段配置
```

#### 3. 注册 Bot

编辑 `config/bots.yaml`：

```yaml
bots:
  - name: finance_manager
    module: bots.finance_manager.bot
    class: FinanceManagerBot
    config_file: bots/finance_manager/config.yaml
    feishu:
      app_id: "你的app_id"
      app_secret: "你的app_secret"
```

#### 4. 启动机器人

```bash
python main.py
```

看到以下输出表示启动成功：

```
Bot 加载成功: finance_manager (财务管家)
Bot finance_manager 启动成功
```

详细配置说明请参考：[财务管家 README](bots/finance_manager/README.md)

## 🏗️ 项目结构

```
feishu-bot/
├── bots/                    # Bot 实现目录
│   ├── base.py             # Bot 基类
│   └── food_analyzer/      # 饮食分析 Bot
│       ├── bot.py          # Bot 实现
│       └── config.yaml     # Bot 配置
├── core/                    # 核心框架
│   ├── client.py           # 飞书客户端
│   ├── ai_client.py        # AI 客户端（支持高可用）
│   ├── batcher.py          # 消息批处理器
│   └── utils.py            # 工具函数
├── config/                  # 框架配置
│   └── bots.yaml           # Bot 列表配置
├── main.py                  # 主程序入口
├── .env.example            # 环境变量模板
└── requirements.txt        # Python 依赖
```

## 🔧 高级配置

### AI 高可用配置

框架支持主备双源 API 配置，确保 AI 功能始终可用：

```env
# 主 API（日常使用）
OPENAI_API_KEY=primary-key
OPENAI_BASE_URL=https://api.primary.com/v1

# 备用 API（主 API 失败时自动切换）
OPENAI_API_KEY_BACKUP=backup-key
OPENAI_BASE_URL_BACKUP=https://api.backup.com/v1

# 重试策略
API_MAX_RETRIES=3      # 每个源重试3次
API_RETRY_DELAY=2      # 指数退避：2s, 4s, 8s
```

**故障转移流程**：
```
主 API (重试3次) → 失败 → 备用 API (重试3次) → 成功/失败
```

详细说明见：[AI_HA_CONFIG.md](AI_HA_CONFIG.md)

### 多维表格配置

复制多维表格模版: https://zkeq-life.feishu.cn/base/RHNPb2Z0Aa021VsJoZYcPGEqnCh?from=from_copylink

在 `bots/food_analyzer/config.yaml` 中配置：

```yaml
bitable:
  enabled: true
  app_token: "your_bitable_app_token"
  table_id: "your_table_id"
  fields:
    time: "时间"                # 日期时间字段
    meal_type: "类型"           # 餐次类型
    main_dish: "主餐"           # 主餐内容
    calories: "热量（kcal）"    # 热量
    # ... 更多字段映射
```

### 消息批处理配置

```yaml
batch:
  window_seconds: 12  # 消息合并窗口（秒）
```

在 12 秒内的多条消息会被合并处理，提升体验。

## 🔌 扩展开发

### 创建自己的 Bot

1. **创建 Bot 目录**

```bash
mkdir -p bots/my_bot
```

2. **实现 Bot 类**

创建 `bots/my_bot/bot.py`：

```python
from bots.base import BaseBot
from typing import List, Optional
from core.batcher import MessagePart

class MyBot(BaseBot):
    """我的自定义 Bot"""

    def process_messages(
        self,
        chat_id: str,
        parts: List[MessagePart],
        status_msg_id: Optional[str]
    ) -> str:
        # 处理消息并返回回复
        return "Hello from MyBot!"
```

3. **创建配置文件**

创建 `bots/my_bot/config.yaml`：

```yaml
name: "我的 Bot"
description: "Bot 描述"

feishu:
  app_id: "your_app_id"
  app_secret: "your_app_secret"

system_prompt: |
  你是一个有用的助手...
```

4. **注册 Bot**

编辑 `config/bots.yaml`：

```yaml
bots:
  my_bot:
    enabled: true
    module: "bots.my_bot.bot"
    class: "MyBot"
    config_file: "bots/my_bot/config.yaml"
```

5. **重启框架**

```bash
python main.py
```

## 📚 文档

- [框架架构说明](FRAMEWORK_README.md)
- [AI 高可用配置](AI_HA_CONFIG.md)
- [日期识别功能](DATE_RECOGNITION.md)
- [时间表达识别](TIME_RECOGNITION_GUIDE.md)
- [批量处理功能](BATCH_PROCESSING.md)

## 🎯 功能特性详解

### 批量并行处理

当上传多张图片时，框架会：

1. ✅ **并行调用 AI**：同时分析所有图片，而非逐个等待
2. ✅ **独立消息展示**：每张图片的分析结果独立显示
3. ✅ **线程安全**：使用锁机制保证数据完整性
4. ✅ **错误隔离**：单张图片失败不影响其他图片
5. ✅ **批量导入**：支持一键导入所有记录

**性能提升**：3 张图片从串行 15 秒 → 并行约 5 秒

### 智能日期时间识别

**三层优先级**：

1. **图片时间水印**（最高）：自动识别照片左下角的时间戳
2. **文字描述**：识别"昨天"、"上周五"、"1月20日"等表达
3. **当前时间**（默认）：未指定时使用当前日期

**支持的时间格式**：
- 相对日期：昨天、前天、上周五
- 明确日期：1月20日、2026-01-20
- 星期表达：周一、上个周三
- 时间表达：中午12点、下午3点半、晚上6点

详细说明：[DATE_RECOGNITION.md](DATE_RECOGNITION.md)

### 流式响应

AI 分析过程实时显示，用户体验更流畅：

```
正在分析中...

**营养分析** 🍜

哇！麻辣香锅看起来超级诱人呀...

正在生成中...
```

## 🛠️ 技术栈

- **语言**：Python 3.9+
- **飞书 SDK**：lark-oapi
- **AI 客户端**：OpenAI Python SDK
- **配置管理**：PyYAML
- **HTTP 客户端**：requests
- **并发处理**：threading

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/zkeq/feishu-bot.git
cd feishu-bot

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入配置

# 运行
python main.py
```

### 提交规范

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
feat: 新功能
fix: 修复 bug
docs: 文档更新
refactor: 重构代码
chore: 构建/工具变动
```

示例：
```
feat(food_analyzer): 添加批量图片并行处理功能

- 使用多线程并行分析多张图片
- 每张图片独立发送分析消息
- 提供批量导入功能
```

## 📝 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [Lark Open API](https://open.feishu.cn/) - 飞书开放平台
- [OpenAI](https://openai.com/) - AI 能力支持
- 所有贡献者和使用者

## 📧 联系方式

- 作者：Zkeq
- Email：admin@icodeq.com
- GitHub：[@zkeq](https://github.com/zkeq)

## 🗺️ 路线图

- [ ] 支持更多类型的 Bot（天气、翻译、日程等）
- [ ] Web 管理界面
- [ ] 数据统计和可视化
- [ ] 支持更多消息类型（语音、视频等）
- [ ] Docker 部署支持
- [ ] 插件市场

---

⭐ 如果这个项目对你有帮助，欢迎 Star 支持！
