# EgoLink DevBench — 项目全周期汇总

> **项目名称**: group01_esp32s3eye — QMA6100P EgoLink DevBench  
> **硬件平台**: ESP32-S3-EYE + OV2640 摄像头 + QMA6100P 加速度计  
> **服务器**: Flask (Python) + SQLite  
> **串口**: COM4 | **WiFi**: SSID `431` / 密码 `88888888` | **服务器 IP**: `10.1.41.43:5000`

---

## 第1周：周期性传感器上传 (Periodic Upload)

> **提交日期**: 2026-09-19
> **对应目录**: `week1_periodic_upload/`

### 📡 项目架构

```
┌──────────────────────┐       Wi-Fi HTTP POST       ┌──────────────────────┐
│   ESP32-S3-EYE       │ ────────────────────────────▶│   Flask Server       │
│   QMA6100P 传感器     │   JSON {ax,ay,az,time}       │   SQLite + API        │
│   每秒采样一次         │                              │   Port 5000           │
└──────────────────────┘                              └──────────┬───────────┘
                                                                  │
                                                     ┌────────────▼───────────┐
                                                     │   浏览器仪表盘          │
                                                     │   EgoLink DevBench      │
                                                     │   波形示波器 + 3D姿态   │
                                                     └────────────────────────┘
```

### 🔧 硬件要求

| 硬件 | 说明 |
|------|------|
| **ESP32-S3-EYE** 开发板 | 板载 QMA6100P 三轴加速度计 |
| USB-C 数据线 | 供电 + 烧录 |
| 电脑 | 运行 Flask 服务器（与 ESP32 同一 Wi-Fi 网络） |

### 📦 软件环境

**服务器端**: Python 3.8+ / Flask  
**ESP32 端**: ESP-IDF v5.2+ / 组件依赖 `espressif/qma6100p` + `espressif/esp32_s3_eye`

### 🚀 部署步骤

```bash
# 1. 启动服务器
cd server
pip install -r requirements.txt
python app.py

# 2. 配置并烧录 ESP32
#    编辑 esp32_firmware/main/main.c，修改 WiFi 和服务器地址
cd esp32_firmware
idf.py set-target esp32s3
idf.py build
idf.py -p COM4 flash monitor
```

### 🖥️ 仪表盘功能

| 功能 | 说明 |
|------|------|
| **波形示波器** | 左侧 ECharts 滚动静默波形，三轴 AX(红)/AY(绿)/AZ(蓝) 分别显示 |
| **数值卡片** | AX/AY/AZ 实时数值（大号字体），变化时闪烁边框动画 |
| **3D 姿态立方体** | 纯 CSS 3D 旋转，Pitch/Roll 角度显示，加速度方向映射空间朝向 |
| **连接状态** | 在线/离线/数据停滞检测，速率 Hz 显示，总记录数统计 |
| **离线运行** | 所有静态资源本地化（echarts.min.js），无需互联网连接 |

### 📄 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/latest` | 获取最新一条数据 |
| `GET` | `/api/history?count=100` | 获取最近 N 条历史数据 |
| `GET` | `/api/count` | 获取总记录数 |
| `POST` | `/api/upload` | ESP32 上传数据 |

### ⚙️ 配置说明

| 参数 | 位置 | 说明 |
|------|------|------|
| Wi-Fi 账号密码 | `main.c` | 改为你的 Wi-Fi |
| 服务器地址 | `main.c` | 改为服务器 IP |
| 设备 ID | `main.c` | 自定义设备标识 |
| 采样间隔 | `main.c` | 默认 1000ms |
| 服务器端口 | `app.py` | 默认 5000 |


---

## 第2周：请求采集与 request_id 闭环

> **对应目录**: `week2_request_collection/`
> **说明**: 第2周的核心功能（request_id 闭环、采集请求轮询）已在第1周的基础上实现，并作为基础架构被后续所有周次（第3-8周）复用。因此本目录无独立 README，该部分内容分散在各周的 API 设计（`/api/pending_request`、`/api/request_collection`）和硬件轮询逻辑中。如需了解详情，请参考第3周及后续周次的系统架构和 API 章节。

---

## 第3周：GPIO0 按键触发事件反馈系统

> **提交日期**: 2026-09-30
> **对应目录**: `week3_key_feedback/`

### 1. 系统架构

```
┌─────────────────────┐         POST /api/trigger         ┌──────────────────────┐
│   ESP32-S3-EYE      │  ──────────────────────────────►  │   Flask Server        │
│   (GPIO0 按键)       │         POST /api/cancel          │   (0.0.0.0:5000)      │
│                     │  ──────────────────────────────►  │                       │
│   main.c            │                                    │   app.py              │
│   http_post_trigger │  ◄──── ACK {ack: true} ─────────  │   trigger_events 表    │
│   http_post_cancel  │                                    │                       │
└─────────────────────┘                                    └─────────┬─────────────┘
                                                                      │
                                                            GET /api/trigger_status
                                                                      │
                                                             ┌────────▼─────────────┐
                                                             │   index.html          │
                                                             │   (前端 500ms 轮询)    │
                                                             │                       │
                                                             │   🔴 本地触发          │
                                                             │   🟢 远端已确认        │
                                                             │   ⚪ 已取消 / 待机     │
                                                             └───────────────────────┘
```

### 2. 按键触发流程

| 步骤 | 操作 | HTTP 请求 | 前端状态 | 指示灯 |
|------|------|-----------|----------|--------|
| **1** | 按下 GPIO0 (BOOT) 键 | `POST /api/trigger` | **本地触发** / 等待确认 | 🟠 橙色闪烁 |
| **2** | 服务器收到事件 → 写入 trigger_events → ACK | 返回 `200 {"ack": true}` | **远端已确认** | 🟢 绿色发光 |
| **3** | 再次按下 GPIO0 (BOOT) 键 | `POST /api/cancel` | **已取消** | 🔴 红色 |
| **4** | 无事件 / 初始状态 | — | **待机** | ⚪ 灰色 |

### 3. 状态定义

| status | 含义 | 点亮颜色 |
|--------|------|----------|
| `IDLE` | 无事件 | 灰色 `#8b949e` |
| `LOCAL_TRIGGERED` | 按键已按下但未收到服务器确认 | 橙色 `#d2991d`（闪烁） |
| `REMOTE_ACKED` | 服务器已确认收到触发 | 绿色 `#3fb950`（发光） |
| `CANCELLED` | 用户取消了本次触发 | 红色 `#f85149` |

### 4. API 接口

| 方法 | 路径 | 说明 | 请求体 |
|------|------|------|--------|
| `POST` | `/api/trigger` | ESP32 按键触发 | `{"device_id":"...","event_id":"..."}` |
| `POST` | `/api/cancel` | ESP32 按键取消 | `{"event_id":"..."}` |
| `GET` | `/api/trigger_status` | 前端轮询状态 | — |
| `GET` | `/api/pending_request` | ESP32 轮询采集请求 | `?device_id=...` |
| `POST` | `/api/request_collection` | Web 端发起采集请求 | `{"device_id":"..."}` |
| `GET` | `/api/latest` | 获取最新传感器数据 | — |
| `GET` | `/api/history` | 获取历史数据 | `?count=100` |
| `POST` | `/api/upload` | ESP32 上传传感器数据 | 20 组加速度数据 |

### 5. Bug 修复记录

| 日期 | 问题 | 根因 | 修复 |
|------|------|------|------|
| 2026-09-30 | 前端按键状态不更新 | `index.html` 多余 `}` 导致 JS 语法错误 | 删除多余 `}` |
| 2026-09-30 | HTTP 错误信息不明确 | `main.c` 只打印 `esp_err_to_name` 无十六进制码 | 添加 `(0x%x)` 和完整 URL 日志 |


---

## 第4周：自然语言查询与请求采集 (NLP Agent)

> **提交日期**: 2026-09-30
> **对应目录**: `week4_nlp_agent/`

### 1. 系统架构（双路径设计）

```
用户输入自然语言
       │
       ▼
 POST /api/nlp   { "text": "查看最新数据" }
       │
       ├── DEEPSEEK_API_KEY 为空？
       │
       ├── YES ──► _local_nlp_parse()    本地规则引擎（关键词匹配）
       │              ├── 意图分类: tool_query_latest / tool_request_collection
       │              ├── 设备提取: 正则 group\d+_\w* / esp32\w*
       │              ├── 歧义检测: "那个"/"这个"/"它" → 反问用户
       │              └── 越界拒绝: 非白名单设备 → 拒绝
       │
       └── NO  ──► _llm_nlp_parse()      DeepSeek Function Calling
                      ├── model: deepseek-chat
                      ├── tools: [tool_query_latest, tool_request_collection]
                      └── fallback: API 失败 → 降级到 _local_nlp_parse()
       │
       ▼
   执行 Tool
       │
       ├── tool_query_latest      → SELECT FROM accelerometer ORDER BY id DESC LIMIT 1
       └── tool_request_collection → INSERT collection_requests → 轮询 10s 等待硬件上报
       │
       ▼
    返回 JSON → 前端 chat-log 渲染
```

**核心特性**：有 API key 时走大模型（DeepSeek function calling）；无 API key 时自动降级到本地规则引擎，零外部依赖；歧义输入反问用户；越界设备直接拒绝。

### 2. 前端功能：自然语言对话面板

网页右下角新增 **🔮 自然语言查询** 面板，包含：💬 对话窗口、📝 输入框、🏷 Badge 状态。

### 3. 测试用例（5 个场景）

| 场景 | 输入 | 预期结果 |
|------|------|----------|
| ① 查询最新数据 | 查看 group01_esp32s3eye 的最新数据 | 返回加速度数值 |
| ② 重新采集 | 帮 group01_esp32s3eye 重新采集一次 | 采集成功，显示新数据 |
| ③ 歧义反问 | 查一下那个东西 | 反问"请问您要查的是什么设备？" |
| ④ 越界拒绝 | 查一下 group99_fake 的最新数据 | 拒绝"不在白名单中" |
| ⑤ 无意义输入 | 今天天气不错 | 无法识别意图，提示可执行操作 |

### 4. 单元测试结果（9/9 通过）

```
[PASS] "查看 group01_esp32s3eye 的最新数据" → tool_query_latest
[PASS] "查一下那个东西"                    → ambiguous（反问）
[PASS] "帮 group01_esp32s3eye 重新采集一次" → tool_request_collection
[PASS] "查一下 group99_fake 的数据"         → rejected（越界）
[PASS] "帮我测一下"                         → tool_request_collection
[PASS] "今天天气不错"                       → ambiguous（无意图）
[PASS] "上一条记录是什么"                   → tool_query_latest
[PASS] "测一下"                             → tool_request_collection
[PASS] "查一下那个东西"                     → ambiguous（反问）
```

### 5. API 接口（新增）

| 方法 | 路径 | 说明 | 请求体 |
|------|------|------|--------|
| `POST` | `/api/nlp` | 自然语言查询 / 采集 | `{"text": "查看最新数据"}` |

### 6. 关键技术决策

| 决策 | 理由 |
|------|------|
| **双路径设计** | 有 API key 时用 DeepSeek function calling；无时降级到本地规则引擎 |
| **歧义必须反问** | 不做猜测，避免"查一下那个"错误匹配 |
| **白名单校验** | 即使 LLM 返回了 device_id，也逐字校验是否在白名单中 |
| **采集轮询上限 10s** | 给硬件更多响应时间 |
| **复用 Week 3 固件** | ESP32 侧不需要修改任何代码 |


---

## 第5周：按键说话与语音播报 (Voice Agent)

> **提交日期**: 2026-09-30
> **对应目录**: `week5_voice_agent/`

### 1. 系统架构（语音链路）

```
▶ 用户按住 "🎤 按住说话" 按钮
       │
       ▼
  💻 电脑麦克风（Web 浏览器端，非 ESP32）
       │
       ▼
  Web Speech API — SpeechRecognition
       │
       ├── 成功 ──► 识别文字填入输入框 → POST /api/nlp（复用 Week 4）
       │                              → JSON 返回 → speechSynthesis TTS 播报
       ├── 静音 ──► "🔇 未检测到声音，请重试"
       ├── 识别失败 ──► "😅 抱歉，未能识别您的语音"
       └── 服务超时 ──► "⚠️ 设备无响应，采集失败"
```

**核心特征**：全程在 Web 浏览器端完成语音识别和合成，零后端改动；文字输入始终可用，语音为可选快捷方式。

### 2. 前端功能

| 元素 | 说明 |
|------|------|
| 🎤 按住说话按钮 | onmousedown 启动语音识别，onmouseup/leave 停止 |
| 📊 语音状态条 | 实时显示当前语音链路环节 |
| 🔊 TTS 播报 | 后端回复自动朗读，支持中途取消 |

### 3. 测试用例（5 个场景）

| 场景 | 操作 | 预期 |
|------|------|------|
| ① 查旧数据 | 说"查看 group01_esp32s3eye 的最新数据" | TTS 朗读数据，保留旧时间 |
| ② 重新采集 | 说"帮 group01_esp32s3eye 重新采集一次" | TTS 播报新 request_id |
| ③ 静音检测 | 按住不说话松开 | 状态显示"🔇 未检测到声音" |
| ④ 断网无响应 | 停止 Flask → 说"查看最新数据" | 显示"⚠️ 服务无响应" |
| ⑤ 歧义反问 | 说"查一下那个东西" | 显示反问，不播报 TTS |

### 4. 异常处理清单

| 异常场景 | 用户提示 |
|----------|----------|
| 浏览器不支持语音 | ⚠️ 浏览器不支持语音识别，请改用文字输入 |
| 静音/无声 | 🔇 未检测到声音，请重试或改用文字输入 |
| 识别失败 | 😅 抱歉，未能识别您的语音，请重试 |
| 录音超时(10s) | ⏰ 录音超时，请重试 |
| 服务无响应 | ⚠️ 服务无响应: {error} |
| 采集失败 | ⚠️ 设备无响应，采集失败 |
| TTS 播报失败 | 静默降级，状态恢复待机 |

### 5. 关键技术决策

| 决策 | 理由 |
|------|------|
| 浏览器端 STT/TTS | 零后端改动，浏览器原生 API 跨平台稳定 |
| 按住说话模式 | 避免意外触发；松开自动停止并提交 |
| 10s 录音超时 | 防止用户忘记松手导致长时间无效录音 |
| 文字输入始终保留 | 语音识别失败时回退方案 |
| 零改动 ESP32 | 所有代码均在 Web 前端 |

---

## 第6周：任务取消与结果隔离 (Voice Interaction)

> **提交日期**: 2026-09-30
> **对应目录**: `week6_voice_interaction/`

### 1. 新增功能总览

| 功能 | 后端 | 前端 | 说明 |
|------|------|------|------|
| **任务取消** | /api/cancel_nlp 端点 + active_task 状态机 | 停止按钮 + 语音取消关键词 | 用户可随时中断正在执行的任务 |
| **结果隔离** | _build_resp() 检查 task_state | stale/cancelled 处理分支 | 旧请求的结果不会覆盖新请求的展示 |
| **延迟注入开关** | ENABLE_SLOW_INJECTION 硬编码开关 | - | 用于测试中途取消，模拟10秒慢采集 |
| **时间指标** | - | showTimeMetrics() 显示三段耗时 | 语音到完成、语音到首响应、总耗时 |

### 2. 取消机制状态机

```
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
```

### 3. 测试场景

| 场景 | 操作 | 预期 |
|------|------|------|
| 中途取消 | 发送采集请求 → 点击停止 | 任务被取消 |
| 快速连续两次查询 | 快速发送两次查询 | 第一个 stale 不显示，第二个正常展示 |
| 语音取消 | 请求采集 → 说"停止" | 任务被取消 |
| 时间指标 | 正常发送一次查询 | 显示三段耗时 |

### 4. API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/nlp | 自然语言查询/采集（含结果隔离） |
| POST | /api/cancel_nlp | 取消当前任务 |
| GET | /api/status | 获取心跳与状态 |

### 5. 关键技术决策

| 决策 | 理由 |
|------|------|
| threading.Lock 保护 active_task | 多线程并发访问，锁保证原子性 |
| UUID 作为 request_id | 全局唯一，避免新/旧请求冲突 |
| 延迟注入用硬编码开关 | 测试功能不应暴露到生产环境 |
| 前端丢弃 stale 不显示 | 用户只关心最新请求的结果 |


---

## 第7周：图像采集与防作弊 (Image Capture)

> **提交日期**: 2026-10-01
> **对应目录**: `week7_image_capture/`

### 0. 最终验证结果 ✅

| 测试项 | 结果 | 输出 |
|--------|------|------|
| ESP32 板载 OV2640 摄像头初始化 | ✅ **通过** | `Detected OV2640 camera` + `Camera OV2640 initialized: QVGA JPEG PSRAM` |
| 网页「拍照」显示真实图像 | ✅ **通过** | 前端显示实时彩色画面，右上角绿色「📷 实时拍摄 (ESP32-CAM)」标签 |
| ESP32 按键触发（红→绿） | ✅ **通过** | 初始红色 → 按键后变绿 |
| 历史记录 & 防作弊 | ✅ **通过** | 清除旧图 + 失败清空，无旧图残留 |
| poll_service 独立任务轮询 | ✅ **通过** | 每秒 Poll response，看门狗无触发 |
| 服务器→板端拍照指令全链路 | ✅ **通过** | 网页点击「拍照」→ 服务器推送 → ESP32 拍照上传 → 网页展示 |

### 1. 图像采集流程

**真实 ESP32-CAM 采集主流程：**
```
用户点击「📷 拍照」→ Flask /api/capture_image → 写入 pending_request
→ ESP32 poll_service 发现 action == "capture"
→ capture_and_upload(): esp_camera_fb_get() → JPEG 编码 → HTTP POST
→ Flask 接收 → base64 → 前端显示彩色图片 + 绿色标记
```

**降级流程**（ESP32 不可达）：摄像头不可用 → 从 precaptured_images/ 随机选择 → 橙色标记

### 2. 防作弊机制（核心）

```javascript
function captureImage() {
    // ⚠️ 第一步：立即清空 image-area 内容（在请求发送之前！）
    area.innerHTML = '<div class="empty-hint">⏳ 采集进行中...</div>';
    lastCapturedImageUrl = null;
    // 第二步：发起采集请求
    fetch('/api/capture_image', {method:'POST'}).then(...).catch(...);
}
```

**关键点**：采集请求发送前立即清除旧图；网络/后端失败时旧图已不可见。

### 3. API 接口

**POST /api/capture_image**: 成功返回 `{success, image(base64), source, filename}`  
**GET /api/pending_request**: 返回 `{has_request, request_id, action}`

### 4. 排错历程

| 问题 | 原因 | 解决 |
|------|------|------|
| Camera not found | 引脚与板型不匹配 | 重写 camera_pins.h |
| GPIO 越界 (GPIO>48) | 引脚号超限 | 修正到合法范围 |
| I2C 地址冲突 | OV2640 与 QMA6100P 共用总线 | CMD_SUSPEND/RESUME 复用 |
| PSRAM 分配失败 | 未启用 PSRAM | sdkconfig 启用 CONFIG_SPIRAM |
| JPEG 编码失败 | 组件未链接 | CMakeLists 添加 REQUIRES esp_jpeg |
| while(1) WDT 复位 | 无 vTaskDelay | 独立任务 + vTaskDelay |
| WDT 仍 5s 触发 | HTTP 超时 5s = WDT 边界 | HTTP_TIMEOUT_MS=3000 |
| perform 无法读 body | DNS/路由 | open/read/close 模式 |
| send() timeout | 防火墙 | 关闭防火墙 |
| 图片上传损坏 | JPEG 截断 | Content-Type + 完整长度 |

### 5. 测试场景

| 场景 | 操作 | 预期 |
|------|------|------|
| ESP32-CAM 真实拍照 | 点击拍照 | 显示彩色画面 + 绿色标记 |
| 按键触发(红→绿) | 按下 GPIO0 | LCD 红色→绿色 |
| 降级测试 | ESP32 不可达 | 显示预存图片 + 橙色标记 |
| 防作弊测试 | 遮挡摄像头→拍照 | 失败时旧图消失 |

---

## 第8周：视觉推理与人工反馈 (Vision Feedback)

> **提交日期**: 2026-10-01
> **对应目录**: `week8_vision_feedback/`

### 0. 最终验证结果 ✅

| 测试项 | 结果 |
|--------|------|
| 推理面板正常显示 | ✅ **通过** — 推理标签、置信度、模型版本、状态正确展示 |
| 低分 uncertain 状态 | ✅ **通过** — 30% 概率触发，显示橙色「⚠️ 不确定 (uncertain)」 |
| 模拟推理标注 | ✅ **通过** — 模型版本 MOCK-V1，橙色警告条「⚠️ 当前为模拟推理（仅演示界面）」 |
| 人工纠正 | ✅ **通过** — 弹窗输入 → 显示「模型说 XX / 人工纠正为 YY」对比 |
| 重新采集 | ✅ **通过** — 清空推理结果 → 重新拍照 → 重新推理 |

### 1. 视觉推理流程

```
用户点击「📷 拍照」→ 采集成功 → 点击「🔍 推理」
→ POST /api/infer_image → _mock_infer() ← 30% 概率低分
→ INSERT vision_results → 返回 result_id
→ 前端展示推理面板（标签 / 置信度 / 版本 / 状态 + 橙色模拟警告）
→ 用户点击「✏️ 人工纠正」→ 弹窗输入 → POST /api/correct_label
→ 显示对比：🤖 模型说 XX（YY%）/ 🙋 人工纠正为 ZZ
```

### 2. 模拟推理机制

```python
ENABLE_MOCK_VISION = True

def _mock_infer():
    candidates = ['环境正常', '人员走动', '物体移动', '光照变化',
                  '异常闯入', '设备异常', '画面模糊']
    label = random.choice(candidates)
    if random.random() < 0.3:        # 30% 低分概率
        score = random.uniform(0.30, 0.68)
        status = 'uncertain'
    else:
        score = random.uniform(0.70, 0.98)
        status = 'success'
    return {'label': label, 'score': round(score, 4),
            'model_version': 'MOCK-V1', 'status': status}
```

### 3. 视觉推理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/infer_image | 对当前图片执行推理，返回 label/score/版本/状态/result_id |
| POST | /api/correct_label | 提交人工纠正标签，保存三方对应 |
| GET | /api/vision_history | 获取推理历史记录 |

### 4. 数据库设计

```sql
CREATE TABLE vision_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL,              -- 推理图片
    model_label TEXT NOT NULL,             -- 模型标签
    model_score REAL NOT NULL,             -- 模型置信度
    model_version TEXT NOT NULL,           -- 模型版本 (MOCK-V1)
    status TEXT NOT NULL DEFAULT 'success', -- success/uncertain
    human_corrected_label TEXT,            -- 人工纠正标签
    corrected_at TEXT,                     -- 纠正时间
    created_at TEXT NOT NULL               -- 推理时间
);
```

### 5. 排错历程

| 问题 | 原因 | 解决 |
|------|------|------|
| `no image available for inference` | 推理端找 `precaptured_images/`，但图片存于 `static/captured/` | 统一路径 |
| 人工纠正提示「请先执行推理」 | 后端未返回 result_id | 加 cursor.lastrowid + result['result_id'] |
| 需区分模拟与真实推理 | 老师要求当堂可见模拟标记 | model_version: "MOCK-V1" + 橙色警告条 |

### 6. 关键技术决策

| 决策 | 理由 |
|------|------|
| ENABLE_MOCK_VISION = True 全局开关 | 可一键切换真实/模拟推理 |
| MOCK-V1 固定版本号 | 前端据此显示橙色警告条 |
| 30% 低分概率 | 保证当堂演示可见 uncertain 状态 |
| lastrowid 返回前端 | 人工纠正需要数据库主键 |
| 路径统一 static/captured/latest.jpg | 与 capture 端点存图路径一致 |
| recapture() 清空 lastVisionResultId | 防止旧 ID 被错误用于新图片 |

---

## 附录：硬件环境（各周通用）

| 项目 | 配置 |
|------|------|
| **开发板** | ESP32-S3-EYE (ESP32-S3R8 + PSRAM 8MB) |
| **摄像头** | 板载 OV2640（通过 FPC 排线连接） |
| **串口** | COM4 (CP2102 USB 转串口) |
| **WiFi** | SSID: `431` / 密码: `88888888` |
| **服务器 IP** | `10.1.41.43:5000` |
| **IDF 版本** | ESP-IDF v5.4.4 |
| **设备 ID** | `group01_esp32s3eye` |

