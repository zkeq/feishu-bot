# AI API 高可用配置说明

本项目实现了主备双源和自动重试机制，确保 AI 功能 100% 可用。

## 功能特性

### 1. 主备双源
- **主 API 源**：默认使用的 API 服务
- **备用 API 源**：主源完全失败后自动切换
- 支持不同的 API 提供商（OpenAI、第三方代理等）

### 2. 自动重试
- **每个源独立重试**：主源重试 3 次，备用源重试 3 次（默认配置）
- **指数退避策略**：避免频繁请求，保护 API 服务
  - 第 1 次重试：等待 2 秒
  - 第 2 次重试：等待 4 秒
  - 第 3 次重试：等待 8 秒
- **详细日志记录**：每次尝试都有完整的日志输出

### 3. 支持流式和非流式调用
- 两种调用方式都支持主备双源和重试机制
- 流式调用支持实时更新显示

## 环境变量配置

在 `.env` 文件中配置以下环境变量：

```bash
# ========== 主 API 配置 ==========
OPENAI_API_KEY=your-primary-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# ========== 备用 API 配置（可选）==========
OPENAI_API_KEY_BACKUP=your-backup-api-key
OPENAI_BASE_URL_BACKUP=https://backup-api.example.com/v1
OPENAI_MODEL_BACKUP=gpt-4o-mini

# ========== 重试配置 ==========
API_MAX_RETRIES=3      # 每个源的最大重试次数（默认 3）
API_RETRY_DELAY=2      # 重试基础延迟（秒，默认 2）
```

## 配置说明

### 主 API 配置（必填）
- `OPENAI_API_KEY`：主 API 密钥
- `OPENAI_BASE_URL`：主 API 基础 URL
- `OPENAI_MODEL`：使用的模型名称

### 备用 API 配置（可选）
- `OPENAI_API_KEY_BACKUP`：备用 API 密钥
- `OPENAI_BASE_URL_BACKUP`：备用 API 基础 URL
- `OPENAI_MODEL_BACKUP`：备用源使用的模型（默认使用主源模型）

**注意**：
- 如果不配置备用 API，系统仍会在主 API 上进行重试
- 只有同时配置了 `OPENAI_API_KEY_BACKUP` 和 `OPENAI_BASE_URL_BACKUP` 才会启用备用源

### 重试配置（可选）
- `API_MAX_RETRIES`：每个源的最大重试次数
  - 默认值：3
  - 建议范围：2-5 次
  - 设置过大会导致响应时间过长

- `API_RETRY_DELAY`：重试基础延迟（秒）
  - 默认值：2 秒
  - 使用指数退避：第 N 次重试等待 `delay * 2^(N-1)` 秒
  - 建议范围：1-3 秒

## 故障转移流程

```
用户请求
    |
    v
使用主 API
    |
    +--> 成功 -------> 返回结果
    |
    +--> 失败
         |
         +--> 重试 1 次（等待 2s）
         |
         +--> 重试 2 次（等待 4s）
         |
         +--> 重试 3 次（等待 8s）
         |
         +--> 主 API 完全失败
              |
              +--> 是否有备用 API？
                   |
                   +--> 否 -------> 返回错误
                   |
                   +--> 是 -------> 切换到备用 API
                                    |
                                    +--> 重试 1 次（等待 2s）
                                    |
                                    +--> 重试 2 次（等待 4s）
                                    |
                                    +--> 重试 3 次（等待 8s）
                                    |
                                    +--> 成功 -------> 返回结果
                                    |
                                    +--> 失败 -------> 返回错误
```

## 日志输出示例

### 主 API 成功
```
[主API] 第 1/3 次尝试
[主API] 调用成功
AI API 调用成功，响应长度: 256 字符
```

### 主 API 重试后成功
```
[主API] 第 1/3 次尝试
[主API] 第 1 次尝试失败: HTTPError: 503 Service Unavailable
[主API] 等待 2.0 秒后重试...
[主API] 第 2/3 次尝试
[主API] 调用成功
AI API 调用成功，响应长度: 256 字符
```

### 主 API 失败，备用 API 成功
```
[主API] 第 1/3 次尝试
[主API] 第 1 次尝试失败: HTTPError: 503 Service Unavailable
[主API] 等待 2.0 秒后重试...
[主API] 第 2/3 次尝试
[主API] 第 2 次尝试失败: HTTPError: 503 Service Unavailable
[主API] 等待 4.0 秒后重试...
[主API] 第 3/3 次尝试
[主API] 第 3 次尝试失败: HTTPError: 503 Service Unavailable
[主API] 所有 3 次尝试均失败
主 API 调用失败: HTTPError: 503 Service Unavailable
主 API 失败，切换到备用 API
[备用API] 第 1/3 次尝试
[备用API] 调用成功
备用 API 调用成功，响应长度: 256 字符
```

## 使用建议

### 1. 生产环境配置
- **必须配置备用 API**：确保高可用性
- **使用不同的 API 提供商**：避免单点故障
- **合理设置重试次数**：建议 3 次
- **监控日志**：及时发现 API 问题

### 2. 开发环境配置
- 可以只配置主 API
- 降低重试次数以加快调试速度
- 设置 `API_MAX_RETRIES=1`

### 3. 成本优化
- **主 API**：使用性价比高的服务
- **备用 API**：使用可靠但可能成本稍高的服务
- 正常情况下只使用主 API，降低成本
- 故障时自动切换到备用 API，保证可用性

### 4. API 提供商建议

**主 API 推荐**：
- OpenAI 官方 API
- 第三方代理服务（如 api.bltcy.ai）
- 自建代理

**备用 API 推荐**：
- 使用不同的提供商（避免同时故障）
- 选择稳定性更高的服务
- 可以是 OpenAI 官方（作为最后保障）

## 常见问题

### Q1: 如何测试故障转移是否正常工作？
A: 临时设置一个无效的主 API Key，观察日志是否自动切换到备用 API。

### Q2: 重试会不会导致响应时间过长？
A: 会有一定影响。最坏情况：主 API 3 次重试（2+4+8=14秒）+ 备用 API 3 次重试（14秒）= 28秒。但这种情况极少发生。

### Q3: 是否支持超过 2 个 API 源？
A: 当前版本只支持主备双源。如需更多源，需要修改代码实现多源轮询。

### Q4: 流式调用和非流式调用的重试逻辑有区别吗？
A: 没有区别，两者使用相同的重试和故障转移机制。

### Q5: 如何调整重试策略？
A: 修改 `API_MAX_RETRIES` 和 `API_RETRY_DELAY` 环境变量。注意指数退避公式：`delay * 2^(attempt-1)`。

## 代码集成

如果你是开发者，想了解如何在代码中使用：

```python
from core.ai_client import AIClient

# 创建 AI 客户端（支持主备双源）
ai_client = AIClient(
    api_key="primary-key",
    base_url="https://api.openai.com/v1",
    backup_api_key="backup-key",  # 可选
    backup_base_url="https://backup-api.com/v1",  # 可选
    max_retries=3,  # 每个源重试次数
    retry_delay=2.0,  # 基础延迟
)

# 非流式调用
response = ai_client.call(
    messages=[{"role": "user", "content": "Hello"}],
    model="gpt-4o-mini",
)

# 流式调用
response = ai_client.call_streaming(
    messages=[{"role": "user", "content": "Hello"}],
    model="gpt-4o-mini",
    update_callback=lambda content: print(content),  # 实时更新回调
    update_interval=0.5,  # 更新间隔
)
```

## 总结

通过主备双源 + 自动重试机制，本项目实现了：
- ✅ 单个 API 故障时自动重试
- ✅ 主 API 完全失败时自动切换备用
- ✅ 指数退避避免过度请求
- ✅ 详细日志便于问题排查
- ✅ 100% 可用性保证（前提是至少一个 API 可用）

建议生产环境配置主备双源，确保服务稳定性。
