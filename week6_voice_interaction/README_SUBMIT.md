# Week 6: 任务取消与结果隔离 (Voice Interaction)

> **项目名称**: group01_esp32s3eye — QMA6100P EgoLink DevBench  
> **提交日期**: 2026-09-30  

---

## 1. 新增功能总览

| 功能 | 后端 | 前端 | 说明 |
|------|------|------|------|
| **任务取消** | /api/cancel_nlp 端点 + active_task 状态机 | 停止按钮 + 语音取消关键词 | 用户可随时中断正在执行的任务 |
| **结果隔离** | _build_resp() 检查 task_state | stale/cancelled 处理分支 | 旧请求的结果不会覆盖新请求的展示 |
| **延迟注入开关** | ENABLE_SLOW_INJECTION 硬编码开关 | - | 用于测试中途取消，模拟10秒慢采集 |
| **时间指标** | - | showTimeMetrics() 显示三段耗时 | 语音到完成、语音到首响应、总耗时 |

---

## 2. 取消机制

### 2.1 后端状态机

`
                  +-----------------+
                  |     idle        |
                  +--------+--------+
                           | POST /api/nlp
                           v
                  +-----------------+
         +-------+   executing     |<------ active_task.request_id = uuid
         |       +--------+--------+
         |                |
         |       +--------+--------+
         |       |                 |
         v       v                 v
  +----------+ +----------+ +----------+
  |cancelled | |completed | |  idle    |
  |(POST     | |(自然完成) | |(新请求)  |
  | /cancel) | |          | |          |
  +----------+ +----------+ +----------+
`

**核心数据结构**：
`python
active_task = {
    'request_id': None,        # 当前任务的唯一UUID
    'task_state': 'idle',      # idle | executing | completed | cancelled
    'cancel_event': None       # threading.Event 用于中断采集轮询
}
task_lock = threading.Lock()   # 保护 active_task 的线程安全
`

**状态转换规则**：
- idle -> executing：新 /api/nlp 请求到达
- executing -> completed：任务正常结束
- executing -> cancelled：用户调用 /api/cancel_nlp
- 任何状态 -> idle：新请求覆盖（旧请求结果变为 stale）

### 2.2 结果隔离

_build_resp() 内部函数在返回响应前检查当前 active_task：
- 若 request_id 不一致 → task_state = "stale"（旧请求被新任务覆盖）
- 若 task_state 为 "cancelled" → 按取消处理
- 否则 → task_state = "completed"，正常返回

前端处理逻辑：
- `ts === "stale"`：不显示结果（return 丢弃），保持当前展示不变
- `ts === "cancelled"`：显示"⏹ 任务已取消"
- 其他：正常展示结果

### 2.3 延迟注入（测试用途）

硬编码开关，默认关闭。开启后采集请求会先进入10秒延迟循环，每0.5秒检查取消状态。
```python
ENABLE_SLOW_INJECTION = False   # 默认关闭
# 开启后，采集前阻塞10秒，可中途取消
if ENABLE_SLOW_INJECTION:
    for i in range(20):
        time.sleep(0.5)
        with task_lock:
            if active_task.get("task_state") == "cancelled":
                return {"success": False, "reply": "⏹ 任务已被取消"}
```

---

## 3. 前端新增功能

### 3.1 ⏹ 停止按钮

| 属性 | 值 |
|------|-----|
| **位置** | 输入框右侧 |
| **默认状态** | `disabled` |
| **激活时机** | `sendNlp()` 发送请求后立即启用 |
| **禁用时机** | 请求完成（成功/失败/取消）后 |
| **样式** | 红色背景，白色文字，悬停加深 |

```html
<button id="stop-btn" class="stop-btn" disabled>⏹ 停止</button>
```

### 3.2 语音取消关键词

在语音识别回调中检测以下关键词（不区分大小写）：

`停止 / 别说了 / 取消 / 闭嘴 / 住口 / stop / 别读了 / 停`

检测到任一关键词时：
1. 调用 `cancelNlp()` 发送取消请求
2. 阻止后续 NLP 请求（`return`）

### 3.3 时间指标

三个时间指标在任务完成后显示在输入框下方：

| 指标 | 计算公式 | 说明 |
|------|----------|------|
| 🎤→完成 | taskCompleteTime - endOfSpeechTime | 语音结束到结果展示 |
| 🎤→首响应 | firstFeedbackTime - endOfSpeechTime | 语音结束到首次收到后端响应 |
| ⏱ 总耗时 | 同 🎤→完成 | 完整链路耗时 |

`endOfSpeechTime` 在语音识别结果回调中记录
`firstFeedbackTime` 在第一次 `.then()` 中记录（非 stale/cancelled 分支）
`taskCompleteTime` 在结果显示后记录

---

## 4. 测试场景

### 4.1 中途取消（需开启延迟注入）
**前提**: `ENABLE_SLOW_INJECTION = True`
**操作**: 输入文字 "帮 group01_esp32s3eye 重新采集一次" → 点击发送 → 等待1秒 → 点击停止
**观察**: 按钮变为禁用，"⏹ 正在取消..." → 状态回到空闲 → 后端返回被丢弃

### 4.2 快速连续两次查询
**操作**: 快速输入 "查看最新数据" 发送 → 立即再输入 "再查一次" 发送
**观察**: 第一个返回标记 stale 不显示，第二个正常展示

### 4.3 语音说"停止"取消
**前提**: `ENABLE_SLOW_INJECTION = True`
**操作**: 输入文字请求采集 → 按住⏰ → 说"停止"
**观察**: 语音识别到取消关键词 → 发送取消请求 → 任务被取消

### 4.4 时间指标显示
**操作**: 正常发送一次查询
**观察**: 输入框下方显示三段耗时指标

---

## 5. 文件变更记录

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `server/app.py` | 修改 | 新增取消、结果隔离、延迟注入 |
| `server/templates/index.html` | 修改 | 新增停止按钮、取消关键词、时间指标 |
| `.gitignore` | 修改 | 新增 week6 build 目录 |

---

## 6. 文件结构

```
week6_voice_interaction/
├─ server/
│   ├─ app.py                 # Flask 应用（新增取消与结果隔离）
│   ├─ .env                   # DEEPSEEK_API_KEY（可选，已 .gitignore）
│   ├─ requirements.txt       # 依赖
│   ├─ templates/
│   │   └─ index.html         # 新增停止按钮、取消关键词、时间指标
│   └─ static/
│       └─ echarts.min.js     # ECharts 图表库
├─ esp32_firmware/            # 复用 Week 3 固件（未修改）
│   ├─ main/
│   │   └─ main.c
│   ├─ CMakeLists.txt
│   └─ build_flash.bat
├─ tools/
│   ├─ test_nlp.py
│   ├─ test_parser_unit.py
│   └─ ...
└─ README_SUBMIT.md           # 本文件
```

---

## 7. 启动方式

```batch
:: 1. 安装依赖
cd week6_voice_interaction\server
pip install -r requirements.txt

:: 2. （可选）配置 DeepSeek API Key
::    编辑 server\.env，填入真实的 DEEPSEEK_API_KEY
::    不填则自动使用本地规则引擎

:: 3. （可选）开启延迟注入进行取消测试
::    编辑 server\app.py，将 ENABLE_SLOW_INJECTION 改为 True

:: 4. 启动 Flask
python app.py

:: 5. 浏览器打开
http://localhost:5000
```

> ⚠️ **浏览器要求**: 推荐 Chrome / Edge / Safari
> ⚠️ **必须使用 localhost**: 浏览器安全策略要求语音识别仅在安全上下文中可用

---

## 8. API 接口

| 方法 | 路径 | 说明 | 请求体 |
|------|------|------|--------|
| POST | /api/nlp | 自然语言查询 / 采集（含结果隔离） | {"text": "查看最新数据"} |
| POST | /api/cancel_nlp | 取消当前任务（更新DB状态） | {}（空请求体） |
| GET | /api/status | 获取心跳与状态 | - |

### 响应格式（/api/nlp）

```json
{
  "reply": "...",
  "success": true,
  "tool_used": "tool_query_latest",
  "data": { ... },
  "task_state": "completed",
  "request_id": "uuid-string"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| task_state | string | completed / cancelled / stale |
| request_id | string | 每次请求唯一的UUID，用于前端判断 |

### 响应格式（/api/cancel_nlp）

```json
{
  "status": "cancelled",
  "message": "任务已取消"
}
```

---

## 9. 关键技术决策

| 决策 | 理由 |
|------|------|
| threading.Lock 保护 active_task | 多线程并发访问，锁保证原子性 |
| UUID 作为 request_id | 全局唯一，避免新/旧请求冲突 |
| 延迟注入用硬编码开关 | 测试功能不应暴露到生产环境 |
| 前端丢弃 stale 不显示 | 用户只关心最新请求的结果 |
| 语音取消关键词在识别回调中检测 | 语音输入过程中可直接说"停止"中断 |
| 时间指标仅在有完整数据时显示 | 避免不完整的测量值误导用户 |
| 结果隔离在_build_resp内部 | 所有工具分支统一调用，保证一致性 |

