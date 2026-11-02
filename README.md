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

### ✅ 实机复验（2026-11-02）

> 详细台账：`evidence/week07/REAL_DEVICE_20261102.md`（`/evidence/` 已在 `.gitignore:69` 忽略，仅本地留证）

| 项 | 实测值 |
|---|---|
| 板端 IP | `10.1.41.149`（`WiFi connected!` 3.6 s，`Got IP` 4.7 s） |
| 上传 | `POST /api/upload` → **200**，`Upload: device=group01_esp32s3eye ax=-0.800 ay=0.680 az=-1.030` |
| 入库 | `accelerometer` 新增 id=37，`device_time = server_time = 2026-11-02 09:31:51` |
| 稳定性 | `STATS: ok=1 fail=0 sensor_err=0`，串口无 `E (...)` 错误行 |

> 口径说明：本次实机跑的是第 7 周固件，传感器上传由「请求采集」触发（`main.c:927`），**不是定时周期上传**；第 1 周的“周期性上传”由 `week1_periodic_upload/` 固件负责，本轮未单独烧录验证。

**一段话结论**：上电 3.6 s 连上 `431`、4.7 s 拿到 `10.1.41.149`，与服务端记录的 `request.remote_addr` 完全一致；`POST /api/upload` 返回 **200**（`app.py:191`，不是 201），单轮统计 `STATS: ok=1 fail=0 sensor_err=0`，串口 0 条 `E (...)` 错误行（唯一 1 条 `W (...)` 是 flash size 提示）。

---

## 第2周：请求采集与 request_id 闭环

> **对应目录**: `week2_request_collection/`
> **说明**: 第2周的核心功能（request_id 闭环、采集请求轮询）已在第1周的基础上实现，并作为基础架构被后续所有周次（第3-8周）复用。因此本目录无独立 README，该部分内容分散在各周的 API 设计（`/api/pending_request`、`/api/request_collection`）和硬件轮询逻辑中。如需了解详情，请参考第3周及后续周次的系统架构和 API 章节。

### ✅ 实机复验（2026-11-02）

| 环节 | 实测证据 |
|---|---|
| 网页发起 | `POST /api/request_collection` → 200，`request_id=20261102_093151_988A69` |
| 板端取到 | `I (23824) MAIN: Poll: received request_id=20261102_093151_988A69` |
| 带 id 回传 | `I (23984) MAIN: UPLOAD HTTP 200 OK`（请求→上传 **160 ms**，payload 含 `request_id`） |
| 闭环落库 | `collection_requests.status=COMPLETED`、`completed_at=2026-11-02 09:31:51`；`accelerometer.id=37` 同秒写入 |

**一段话结论**：2026-11-02 09:31:51 网页发起 `20261102_093151_988A69` → 板端轮询取到后 **160 ms** 内带 `request_id` 回传 `HTTP 200`（ax=-0.80 / ay=0.68 / az=-1.03）→ 服务端同秒写 `accelerometer` id=37 并把该请求置 `COMPLETED`，`completed_at` 与采样时间同为 `2026-11-02 09:31:51`，构成「网页发起→板端执行→带 id 回传→落库闭环」的完整证据链。

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
                                                             │   🟠 本地触发(转瞬)    │
                                                             │   🟢 远端已确认        │
                                                             │   🔴 已取消 / ⚪ 待机    │
                                                             └───────────────────────┘
```

### 2. 按键触发流程

| 步骤 | 操作 | HTTP 请求 | 固件状态 | **LCD 全屏实际颜色**（2026-11-02 实物实测） | 网页角标 |
|------|------|-----------|----------|------------------------------------------|----------|
| **1** | 按下 GPIO0 (BOOT) 键 | `POST /api/trigger` | `LOCAL_TRIGGERED` | **红** `0xF800`（按下立即） | 尚未刷新（仍是上一次的角标） |
| **2** | 服务器写入 `trigger_events` 并 ACK | 返回 `200 {"ack": true}` | `REMOTE_ACKED` | **绿** `0x07E0`（约 0.4 s 后） | 🟢 绿点发光「按键: 远端已确认」 |
| **3** | 再次按下 GPIO0 (BOOT) 键 | `POST /api/cancel` | `IDLE` | **白** `0xFFFF`（按下立即） | 🔴 红点「按键: 已取消」 |
| **4** | 服务端不可达，ACK 超时（5 s） | 无（TCP 连接失败） | `CANCELLED` | **黄** `0xFFE0`（超时后） | 不变（服务端无记录，页面无从刷新） |
| **5** | 无事件 / 初始状态 | — | `IDLE` | **白** `0xFFFF` | ⚪ 灰点「按键: 待机」 |

> **⚠️ 两个容易误判的实机细节（2026-11-02 真机复验结论）**
> 1. **网页永远不会显示橙色「本地触发」**：`/api/trigger` 在**同一次请求**里就写入 `REMOTE_ACKED` 并返回 ACK（`week3_key_feedback/server/app.py:319-333`），前端 500 ms 轮询取到时已经是绿色。因此"红屏→等待确认"这一瞬间的证据只能取 **LCD 实物 + 串口 `LOCAL_TRIGGERED` 行**，不能靠网页。
> 2. **黄色 ≠ 用户取消**：用户主动取消时固件立刻变白（`IDLE`）并 POST `/api/cancel`；`CANCELLED` 状态只出现在 **ACK 超时**（`main.c:688-693`）。此时服务端根本没收到这次事件，`trigger_events` 里**不会**有这条记录，`cancelled_at` 也不会被写。

### 3. 状态定义

| status | 含义 | LCD 全屏颜色（2026-11-02 实物实测） | 备注 |
|--------|------|--------------------------------|------|
| `IDLE` | 无事件 | **白** `0xFFFF` | 上电默认 / 用户取消后 |
| `LOCAL_TRIGGERED` | 按键已按下但未收到服务器确认 | **红** `0xF800` | 只在 HTTP 往返的几百毫秒内可见 |
| `REMOTE_ACKED` | 服务器已确认收到触发 | **绿** `0x07E0` | 常驻，直到再次按键 |
| `CANCELLED` | ACK 超时（5 s 无响应） | **黄** `0xFFE0` | 仅"断网/服务端不可达"；用户主动取消**不会**进入此状态 |

> 网页上的角标颜色是另一套语义（`index.html` CSS）：`IDLE` 灰 `#8b949e`、`LOCAL_TRIGGERED` 橙 `#d2991d` 闪烁、`REMOTE_ACKED` 绿 `#3fb950` 发光、`CANCELLED` 红 `#f85149`。因服务端在同一请求内就 ACK，橙色几乎不可能在网页上被看到。

### 3.1 实机验证记录（2026-11-02 10:01–10:03，COM4）

日志：`evidence/week03/serial_key.log`（PowerShell `Tee-Object` 写出，UTF-16LE）；板子 IP `10.1.41.149`，服务端 `10.1.41.43:5000`。

| 绝对时间 | 开机相对 | 串口/日志证据 | LCD | 说明 |
|---|---|---|---|---|
| 10:01:02 | 0 s | `Week3: button_task(8192) + trigger_http_task(8192) created` | 白 | 烧录后复位，联网成功 |
| 10:02:40 | 98.2 s | `BUTTON: TRIGGER event_id=20261102_100240_8E4C LCD=TRIGGERED` | 白→**红** | 按键 |
| 10:02:40 | 98.6 s | `TRIGGER response: {"ack":true,...}` → `HTTP: REMOTE_ACKED` | 红→**绿** | 服务端 **0.42 s** 内 ACK |
| 10:03:02 | 119.7 s | `BUTTON: CANCEL event_id=...8E4C LCD=IDLE` | 绿→**白** | 再按（服务端已于 10:02:57 停止） |
| 10:03:07 | 124.7 s | `CANCEL: HTTP open failed: ESP_ERR_HTTP_CONNECT (0x7002)` | 白 | 取消请求**未到达**服务端 |
| 10:03:08 | 126.0 s | `BUTTON: TRIGGER event_id=20261102_100308_9977` | 白→**红** | 断网测试按键 |
| 10:03:13 | 131.1 s | `HTTP: NO_ACK` / `NETWORK_TIMEOUT_NO_ACK` | 红→**黄** | 连接失败，约 5 s 后判超时 |

**数据库核对**（`week3_key_feedback/server/sensor_data.db` → `trigger_events`）

| event_id | status | created_at | acknowledged_at | cancelled_at | 判定 |
|---|---|---|---|---|---|
| `20261102_100240_8E4C` | `REMOTE_ACKED` | 10:02:40 | 10:02:40 | `NULL` | ✅ 正确：取消请求因服务端已停未到达，`cancelled_at` 本就不该有值 |
| `20261102_100308_9977` | 无记录 | — | — | — | ✅ 正确：断网事件从未到达服务端，表里只存"服务端看到的事实" |

> **取消路径的取证需要服务端在线**：再跑一次 30 秒即可——按 BOOT（白→红→绿）→ 立刻再按（→白）→ `flask.log` 出现 `Cancel: event_id=... rows_affected=1`，DB 该行变为 `CANCELLED` 且 `cancelled_at` 非空（与 2026-09-30 的历史记录一致）。

**两条待观察项（不影响第 3 周验收）**
- `task_wdt: Task watchdog got triggered` ×2：只发生在 HTTP 连接失败阻塞的那 5 s 内，**未复位**，属告警；
- `E BOD: Brownout detector was triggered` ×4（日志尾部）：USB 供电瞬时跌落。第 14 周测试更久、Wi-Fi 发射更密集，建议改用**带外部供电的 USB Hub 或主板后置 USB 口**，避免中途复位污染补传数据。

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
| 2026-11-02 | 串口日志误导（曾让人误判"多出几次触发"） | `http_upload()` 里复制粘贴了 `ESP_LOGI("Sending trigger to URL: %s", SERVER_TRIGGER_URL)`，实际是**每轮传感器上传**都打印"发送触发" | 改为 `Uploading sensor data to URL: %s`（纯日志，不影响功能；下次烧录生效） |


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

### 6. 实机复验（2026-11-02，COM4 / 10.1.41.149）

> 详细台账（串口原文、DB 前后对比、图片指纹）：`evidence/week07/REAL_DEVICE_20261102.md`

| 环节 | 实测证据 |
|---|---|
| 摄像头初始化 | `Detected OV2640 camera` → `Camera OV2640 initialized: QVGA JPEG PSRAM`（上电 7.8 s） |
| 网页发起拍照 | `POST /api/capture_image` → `Capture pending request created: id=20261102_093207_B693B2` |
| 板端执行 | `Action = capture, taking photo...` → `Captured JPEG: 9434 bytes` |
| 上传回执 | `CAPTURE: HTTP 200`（拍照→上传 **210 ms**）；服务端同步记录 `POST /api/capture_image` 200 from `10.1.41.149` |
| 服务端落盘 | `Image saved from ESP32: capture_20261102_093209.jpg (9434 bytes)`；`Capture: ESP32 image received after 0.4s (attempt 2)` |
| 文件校验 | 9,434 B；JPEG SOI `ffd8` / EOI `ffd9` 完整；SHA256 `FA2DA623…B8790885`；`captured_images` 新增 id=22 |
| 防作弊 | 请求发出前清空 `image-area` 并置 `lastCapturedImageUrl=null`；服务端按 mtime < 2 s 判定为新图，无旧图复用 |

**一段话结论**：2026-11-02 09:32:07 网页发起拍照 → 板端约 1.9 s 后拍到 **9,434 B** JPEG（OV2640 QVGA / PSRAM）→ **210 ms** 内 `POST /api/capture_image` 收到 `CAPTURE: HTTP 200` → 服务端落盘 `capture_20261102_093209.jpg`（`captured_images` id=22）并把新图回显给页面；文件头尾 **SOI `FF D8` / EOI `FF D9`** 完整、SHA256 `FA2DA623…B8790885`，可证明是本次新拍而非复用 `latest.jpg` 缓存。

**本机联调中发现的 P3 已修复（2026-11-02）**：原 `/api/capture_image` 成功落盘后没有把对应 `collection_requests` 置 `COMPLETED`，请求停在 `RECEIVED`，随后被 `_check_timeouts()`（`app.py:111-125`，阈值 5 s）刷成 `TIMEOUT`，状态图与统计口径全错。修复后：ESP32 上传的 JPEG 落盘成功后，服务端在同一事务里把该设备最新一条未完成的 `capture` 请求置 `COMPLETED` 并写 `completed_at`（若固件改为带 `?request_id=` 或 `X-Request-Id`，则精确匹配该条）。重启服务后真机复验：`20261102_095205_387D45` 创建于 09:52:05，09:52:06 完成（日志 `Capture: collection_requests COMPLETED (matched=1)`），库内状态 `COMPLETED`、`completed_at=2026-11-02 09:52:06`，不再被误判超时。

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

### 遗留说明（不影响本次验收）

| 项 | 现象 | 影响 | 处置 |
|---|---|---|---|
| flash size 配置 | `sdkconfig` 中 `CONFIG_ESPTOOLPY_FLASHSIZE="2MB"`，实际模组 8 MB，启动多一条 `W (…) Flash size …` 提示 | 当前 app 1.04 MB、分区余量 29%，远未触顶，功能无影响 | 暂不改；后续可切 `CONFIG_ESPTOOLPY_FLASHSIZE_8MB` 重烧消除告警 |
| 历史请求状态 | P3 修复前产生的拍照请求（如 `20261102_093207_B693B2`）仍为 `RECEIVED`，会被超时检查刷成 `TIMEOUT` | 仅影响历史行展示，修复后的新请求均正常 `COMPLETED` | 保留原始记录作为 P3 现场证据，不回填 |
| 证据留存位置 | 详细台账在 `evidence/week07/REAL_DEVICE_20261102.md`，但 `/evidence/` 被 `.gitignore:69` 忽略 | 远程仓库看不到台账原文 | 关键数据（9,434 B、SOI/EOI、160 ms/210 ms）已浓缩进本文各周「一段话结论」 |


---

## 第9周：视觉事件触发主动询问与用户选择 (Proactive Inquiry)

> **提交日期**: 2026-10-08
> **对应目录**: week9_proactive_inquiry/

### 1. 新增功能

| 功能 | 说明 |
|------|------|
| **uncertain 事件触发** | 推理返回 status=="uncertain" 时，前端主动弹出询问模态框 |
| **📷 重拍** | 清空当前结果，重新触发拍照流程，记录 user_action='retake' |
| **❌ 忽略 + 冷却** | 关闭弹窗，启用 60 秒冷却，期间再次推理若仍 uncertain 不再弹出；用 localStorage 持久化 |
| **冷却状态持久化** | localStorage.proactiveCooldownUntil 保存时间戳，刷新页面不丢失 |
| **运行位置标注** | 面板下方明确标注模型/设备/服务实际运行位置 |
| **冷却倒计时** | 冷却期间显示"已忽略本次询问，冷却中（剩余 XX 秒）" |

---

### 2. API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/record_user_action | 记录用户对 uncertain 推理的响应（retake/ignore），写入 vision_results |

---

### 3. 数据库新增字段

sql
ALTER TABLE vision_results ADD COLUMN user_action TEXT;    -- 'retake' | 'ignore'
ALTER TABLE vision_results ADD COLUMN action_at TEXT;      -- 操作时间 ISO datetime


兼容策略：init_vision_db() 在 CREATE TABLE 后用 try/except ALTER TABLE，列已存在则跳过。

---

### 4. 测试记录（10 步完整流程）

| 步骤 | 操作 | 预期 | 结果 |
|------|------|------|------|
| ① 拍照 | 点击「📷 拍照」 | 图像区域显示图片 | ✅ |
| ② 推理触发 uncertain | 点击「🔍 推理」 | 多次推理中约 30% 概率触发低分 | ✅ |
| ③ 模态框弹出 | uncertain 发生时 | 弹出半透明遮罩 + 橙色边框模态框，文案："⚠️ 画面不可用/无法确定" | ✅ |
| ④ 点击🔄重拍 | 点击「🔄 重拍」 | 模态框关闭 → 图片区域清空 → 重新拍照 → DB 记录 user_action='retake' | ✅ |
| ⑤ 再次触发 uncertain → 点击❌忽略 | 推理→低分→点「❌ 忽略」 | 模态框关闭 → DB 记录 user_action='ignore' → 面板显示"冷却中（剩余 60 秒）" | ✅ |
| ⑥ 冷却期间再次推理 | 冷却中再次点击推理 | 即使返回 uncertain，也**不弹出**询问框，仅更新冷却倒计时 | ✅ |
| ⑦ 冷却结束后推理 | 等待 60 秒后再次推理 → uncertain | 冷却提示消失，询问框**正常弹出** | ✅ |
| ⑧ 刷新页面冷却不丢 | 忽略后立即刷新页面 | localStorage 恢复冷却状态，倒计时继续 | ✅ |
| ⑨ 人工纠正保留 | 推理后点击「✏️ 人工纠正」 | 弹窗输入 → 显示"模型说 XX / 人工纠正为 YY"对比 | ✅ |
| ⑩ 重拍清除冷却 | 在有冷却时手动点击「📷 重新采集」 | 冷却提示消失，冷却状态清除 | ✅ |

---

### 5. 问题归因与修复清单

| # | 现象 | 归因 | 修复 |
|---|------|------|------|
| 1 | 旧数据库没有 user_action 列 | 第8周 CREATE TABLE 不含这两个字段 | init_vision_db() 中 ALTER TABLE try/except 兼容 |
| 2 | 冷却状态刷新后丢失 | 未持久化，仅存于 JS 内存变量 | 添加 localStorage 持久化 proactiveCooldownUntil |
| 3 | 冷却期间不确定是否生效 | 无可见提示 | 在面板中添加 .cooldown-hint 显示倒计时 |
| 4 | 重拍后冷却未清除 | recapture() 函数无冷却重置逻辑 | monkey-patch recapture() 追加 proactiveCooldownUntil=0 |
| 5 | 两次连续 uncertain 可能弹出两个模态框 | showProactiveInquiry 无去重 | 添加已存在检测 |
| 6 | 老师要求标注实际运行位置 | 第8周未标注 | 添加 .location-note 显示模型/设备/服务位置 |
| 7 | 拍照卡死——ESP32 未响应 capture | COM4 被占用且板子跑 lesson10_real 旧固件（无 poll_service） | 杀进程释放 COM4，重新烧录 week7 固件 |
| 8 | 烧录 week7 固件后摄像头仍不工作 | 草率复制依赖 | idf.py fullclean && build && flash |
| 9 | ipconfig 双 IP | 双网卡同子网，路由歧义 | 未阻断通信；Flask 绑定 0.0.0.0:5000 |

---

### 6. 启动命令

powershell
cd "D:\lesson\xiaolin\lesson-main (1)\lesson-main\week9_proactive_inquiry\server"
python app.py


浏览器访问：http://10.1.41.43:5000

---

### 7. 架构图


用户点击推理 → POST /api/infer_image
  ├── status='success' → 正常展示标签/置信度
  └── status='uncertain' → 前端检查冷却
         ├── 冷却中 → 更新倒计时，不弹出
         └── 无冷却 → 弹出询问框
                ├── 🔄 重拍 → POST record_user_action(retake) → recapture()
                └── ❌ 忽略 → POST record_user_action(ignore) → localStorage 存冷却 → 启动倒计时


---

### 8. 关键技术决策

| 决策 | 理由 |
|------|------|
| 30% 低分概率触发 uncertain | 继承第8周模拟推理，保证当堂可见 |
| 60 秒冷却 | 老师要求的"不反复打扰" |
| localStorage 持久化冷却 | 刷新页面不丢冷却状态 |
| monkey-patch recapture() | 不修改第8周原有函数，最小侵入 |
| 界面标注运行位置 | 老师明确要求的"演示中说明模型/设备及服务实际运行位置" |
---

## 第10周：多源状态追踪与归因分析

> **提交日期**: 2026-10-09
> **对应目录**: week10_multi_source_state/

### 1. 项目概述

在第9周主动询问的基础上，新增多源状态追踪面板，实现4个数据源（传感器、网络、摄像头、位置/GPS）的独立状态监控、过期检测、补传标记和 **归因分析**。  
当 ESP32 数据中断时，可一眼定位是"传感器坏了"、"网络断了"还是"摄像头没收到"，杜绝信源黑盒。

---

### 2. 运行方式

```bash
cd week10_multi_source_state/server/
pip install flask matplotlib pillow rembg numpy opencv-python-headless --quiet
python app.py
```

浏览器访问：**http://localhost:5000** → 点击顶部Tab **"📊 多源状态"**

---

### 3. 数据源与过期阈值

| 源名称 | source_name | 视觉图标 | 过期阈值 | 示例正常值 |
|--------|-------------|----------|---------|-----------|
| 加速度传感器 | sensor | 📡 | 5s | ax=-0.72 ay=0.52 az=-1.06（单位 **g**，静止模长≈1.3，含未校准偏置） |
| 网络连接 | network | 🌐 | 30s | WiFi connected |
| 摄像头 | camera | 📷 | 60s | filename=capture_20261008_1553.jpg |
| 位置(GPS) | gps | 📍 | 60s | lat=31.2304 lng=121.4737 |

**位置数据源说明：**  
本项目中无真实 GNSS 硬件，GPS 源标记为 **"回放数据-仅供演示"**。`init_source_states_db()` 阶段会自动注入一组模拟坐标（上海），便于教学演示多源时序。

---

### 4. 测试场景

#### 场景①：有旧位置但本次 no_fix

| 步骤 | 操作 | 预期 |
|------|------|------|
| A | 启动 app.py → 进入 📊多源状态 | 📍位置（GPS）显示 🟢 成功，有 lat/lng，带"回放数据-仅供演示"标注 |
| B | `curl -X POST http://localhost:5000/api/simulate_no_fix` | 📍位置变为 🔵 无有效解（非故障），值显示"无有效解，非故障"（**不是** ❌ 失败：无解≠故障） |
| C | 观察 | 卡片底部的**陈旧数据区**保留旧坐标 lat=31.23 lng=121.47，标注"陈旧" |

#### 场景②：网络在线但位置未更新（独立性验证）

| 步骤 | 操作 | 预期 |
|------|------|------|
| A | 让 ESP32 持续上传感应器数据 | 🌐网络显示 🟢 成功，📡传感器显示 🟢 成功 |
| B | 不调用任何 GPS 更新 | 📍位置逐渐变 🟡 过期（>60s），但 🌐网络和 📡传感器仍然正常 |
| C | 结论 | **各源状态完全独立，网络好不代表GPS好** |

#### 场景③：补传数据（延迟到达）

| 步骤 | 操作 | 预期 |
|------|------|------|
| A | 模拟传感器数据携带 3 秒前的 observation_time | 在 📡传感器卡片上出现 📦 补传标记 |
| B | 观察年龄 | 年龄以 observation_time 计算（如 5.3 秒前），而不是 receive_time |
| C | 标注内容 | "📦 补传（原始观测时间：YYYY-MM-DD HH:MM:SS，延迟 X.X秒）" |

#### 场景④：无证据不补造

| 步骤 | 操作 | 预期 |
|------|------|------|
| A | 初次启动或清空 camera 数据 | 📷摄像头显示 ⚪ 未启动 |
| B | 不通过任何外部手段"自动补"数据 | 不会出现凭空捏造的摄像头文件名或IP反查GPS坐标 |
| C | 来源标注 | 每个源卡片底部都有明确的 source_location |

---

### 5. API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/source_states` | GET | 返回所有源的当前状态、年龄、补传标记 |
| `/api/simulate_no_fix` | POST | 模拟 GNSS no_fix（用于教学演示场景①） |

---

### 6. 归因分析逻辑（价值链）

```
ESP32数据中断
    ↓
观察 📊多源状态 面板：
    ├── 📡传感器 → 失败 ▸ 结论：QMA6100P 硬件/I2C 故障
    ├── 🌐网络   → 正常 ▸ 排除网络故障
    ├── 📷摄像头 → 正常 ▸ 排除视觉链路故障
    └── 📍位置   → 过期 ▸ GNSS 信号弱/无解（非故障）
    ↓
归因：传感器硬件故障（约78.5%），非网络断连
```

---

### 7. 文件清单

```
week10_multi_source_state/
├── server/
│   ├── app.py                ← 新增 init_source_states_db / update_source_state / /api/source_states
│   ├── templates/
│   │   └── index.html        ← 新增 📊多源状态 Tab + 面板 + JS 轮询
│   └── static/               ← 不变
└── esp32_firmware/           ← 完全未动，只读
```

---

### 8. 补充说明

- 补传数据的年龄始终以 **observation_time（原始观测时间）** 计算，符合"补传按原观测时间解释"的教学要求
- GPS 源明确标注"回放数据-仅供演示"，不冒充真实 GNSS 数据
- 每个源的状态卡片都有独立的来源标注（source_location）
- 所有代码修改仅位于 week10 目录，week9 未动，ESP32 固件未修改

---

## 第11周：根据多源证据组织交互上下文

> **提交日期**: 2026-10-10
> **对应目录**: week11_context_engine/

### 1. 项目概述

在第10周多源状态追踪基础上，新增 **上下文解释引擎（Context Engine）**，将4个数据源的原始观测转换为三层结构化输出（原始观测 → 派生状态 → 交互决策），实现：
- 加速度模长判断静止/移动（`is_moving`）
- GPS 可信度评估（`position_trustworthy`）
- 摄像头可用性判断（`camera_usable`）
- 已知事实 / 不确定项 / 追问语句 自动生成

---

### 2. 运行方式

```bash
cd week11_context_engine/server/
pip install flask matplotlib pillow rembg numpy opencv-python-headless --quiet
python app.py
```

浏览器访问：**http://localhost:5000** → 点击顶部Tab **"🧠 交互上下文"**

---

### 3. 三层结构

| 层级 | 说明 | 示例字段 |
|------|------|----------|
| raw_observations | DB 直读各源原始值 | `sensor: {ax,ay,az}`, `gps: {lat,lng}`, `network: WiFi connected` |
| derived_states | 固定规则推演 | `is_moving`, `position_trustworthy`, `camera_usable` |
| interaction | 上下文决策 | `known_facts[]`, `uncertain_items[]`, `question`, `rule_version` |

**推导规则：**
- `is_moving`：设备上报单位为 **g**，先换算 `mag_g = mag if mag<=4.0 else mag/9.80665`；`|mag_g - 1.0| > 0.5` → "可能在移动"，否则"静止"（`derived_states.accel_magnitude` 也输出 g 值）
- `position_trustworthy`：GPS status=success 且 age<60s → true
- `camera_usable`：camera status=success 且 age<60s → true

---

### 4. 当堂验证考点（全部通过）

#### 场景①：陈旧位置 — "无有效解"不包装成"当前位置"

| 层级 | 字段 | 实际值 |
|------|------|--------|
| raw_observations | gps.status | failed |
| interaction.uncertain_items | item=当前位置 | `GPS 无有效解，非故障` |

✅ 正确走 `elif status==failed` 分支，未伪装成"当前位置"。

#### 场景②：摄像头不可用 — "画面不可用"绝无"危险"

| 层级 | 字段 | 实际值 |
|------|------|--------|
| derived_states | camera_usable | false（age>60s） |
| interaction.uncertain_items | item=画面内容 | `画面不可用` |

✅ 全输出中无"危险""紧急"。

#### 场景③：模型推断 vs 观测区分

| fact | source |
|------|--------|
| `当前可能静止` | **规则推断** |
| `网络连接正常` | **网络连接** |

✅ 规则推断与原始观测 source 字段可追溯。

#### 场景④：冲突输入 — 三者独立

| 源 | known_facts | uncertain_items |
|----|-------------|-----------------|
| 🌐 网络 (age=32s) | `网络连接正常` | — |
| 📍 GPS (failed) | — | `当前位置` → GPS 无有效解 |
| 📷 摄像头 (age>60s) | — | `画面内容` → 画面不可用 |

✅ 网络正常≠位置正常，互不干扰。

---

### 5. API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/context` | GET | 返回三层结构化上下文（raw_observations + derived_states + interaction） |
| `/api/source_states` | GET | 继承第10周，多源状态原始数据 |
| `/api/simulate_no_fix` | POST | 继承第10周，模拟 GPS no_fix |

---

### 6. 文件清单

```
week11_context_engine/
├── server/
│   ├── app.py                ← 新增 RULES_VERSION, MOVING_THRESHOLD, /api/context 端点
│   ├── templates/
│   │   └── index.html        ← 新增 🧠交互上下文 Tab + 三块面板 + JS 轮询
│   └── static/               ← 不变
├── README_SUBMIT.md          ← 冲突样例 + 三层对照表
└── esp32_firmware/           ← 完全未动，只读
```

---

### 7. 补充说明

- 摄像头不可用时 uncertain_items 仅写"画面不可用"，绝不出现"危险""紧急"
- 位置过期时 known_facts 写"上次报告位置…"绝不写"当前位置"
- 规则推断必须标注 `source="规则推断"`，与原始观测区分
- 所有已有业务逻辑（多源状态/NLP/视觉推理/主动询问）零改动

---

## 第12周：让用户纠错影响后续提醒

> **提交日期**: 2026-10-10
> **对应目录**: `week12_feedback_preferences/`

### 概述

在第11周「交互上下文引擎」基础上，新增 **用户偏好表 (user_preferences)** 和完整的 **反馈闭环 API**，使系统能够记录用户的操作偏好并在同类场景下自动决策，减少不必要的打断。

---

### 新增/修改文件

| 文件 | 说明 |
|---|---|
| `server/app.py` | 新增 `user_preferences` 建表、4 个偏好 API、偏好写入钩子 |
| `server/templates/index.html` | 偏好面板 UI + 主动询问去重拦截 + 稍后按钮 + 偏好 JS 轮询 |

---

### 偏好的存储模型

**`user_preferences` 表**:

| 列 | 类型 | 含义 |
|---|---|---|
| id | INTEGER PK | 自增主键 |
| preference_key | TEXT UNIQUE | 偏好 Key，如 `event_ignore_123` / `label_correct_45` |
| preference_value | TEXT | 偏好值：`retake` / `ignore` / `snooze` / 人工纠正标签 |
| created_at | TEXT | 创建时间 ISO8601 |
| expires_at | TEXT | 过期时间或 NULL（永久） |
| config_version | INTEGER | 配置版本号，每次写入递增（reset 后+1） |

---

### 新增 API 端点

#### 1. GET `/api/check_preference?key=<key>`

查询某条偏好是否存在、是否过期。

**响应**:
```json
// 命中
{ "preference_exists": true, "preference_value": "ignore" }

// 未命中 / 已过期
{ "preference_exists": false }
```

#### 2. POST `/api/preference`

手动写入一条偏好。

**请求体**:
```json
{ "key": "event_snooze_123", "value": "snooze", "duration": 30 }
```

- `duration`：秒数，`null` 或不传表示永久。
- **幂等**：`INSERT OR REPLACE`。

**响应**: `{ "success": true, "key": "...", "config_version": N }`

#### 3. GET `/api/preferences`

返回所有当前偏好及最大 `config_version`。

**响应**:
```json
{
  "success": true,
  "config_version": 3,
  "preferences": [ ... ]
}
```

#### 4. POST `/api/preferences/reset`

一键恢复默认：**清空偏好表** 并将 `config_version` + 1。

---

### 偏好写入钩子（透明注入）

#### `POST /api/record_user_action`

当用户对 uncertain 推理选择 `retake` / `ignore` 时，**自动**写入：
- Key: `event_retake_<result_id>` / `event_ignore_<result_id>`
- Value: 对应 action
- Duration: 永久

#### `POST /api/correct_label`

当用户人工纠正标签时，**自动**写入：
- Key: `label_correct_<result_id>`
- Value: 纠正后的标签
- Duration: 永久

---

### 前端功能改动

#### 1. 偏好面板 (`⚙️ 用户偏好`)

位于「交互上下文」Tab 页下方，实时显示：
- 所有偏好条目（Key / Value / 过期时间）
- 当前配置版本号
- 一键「🔄 恢复默认」按钮

#### 2. 主动询问去重（BUG 修复）

调用 `showProactiveInquiry()` 时，**先查询** `/api/check_preference`：
- 若 `event_ignore_<result_id>` 已存在 → **跳过询问**，显示 toast 提示
- 若未命中 → 正常弹出询问

#### 3. 主动询问加入「稍后」按钮

询问弹窗新增两个按钮：

| 按钮 | 效果 |
|---|---|
| ⏰ 稍后(30s) | 写入 `event_snooze_<rid>` 偏好，30 秒过期 |
| ⏰ 稍后(5分) | 写入 `event_snooze_<rid>` 偏好，5 分钟过期 |

---

### BUG 修复说明

**问题**：原代码中，用户点击「忽略」后同类事件仍会在下次采集时再次弹出，虽然写入了局部冷却（60s），但未考虑持久化偏好。

**修复**：在 `showProactiveInquiry()` 开头增加 `GET /api/check_preference` 调用，命中偏好时直接跳过弹窗。

---

### 启动方法

```bash
cd server
pip install flask opencv-python-headless pillow openai torch torchvision numpy
python app.py
```

访问 `http://127.0.0.1:5000`。

---

### 每步代码量

| 步骤 | 代码行（增量） |
|---|---|
| server/app.py | +135 行 |
| index.html | +105 行 |
| **合计** | ~240 行 |

---

### 验证清单

- [x] `user_preferences` 表随 `init_user_preferences_db()` 自动创建
- [x] 4 个 API 可手工 curl 调用
- [x] `api_record_user_action` 和 `api_correct_label` 自动写入偏好
- [x] 「忽略」事件后同 result_id 不再弹窗
- [x] 「稍后」按钮在指定秒数/分钟后自动过期
- [x] 「恢复默认」清空所有偏好
- [x] 前端面板每 3 秒刷新显示最新偏好

---

### 测试场景（当堂验证）

#### 场景 1：重放去重

同一 `result_id` 多次触发 `showProactiveInquiry()`：
- 首次弹出询问 → 用户点击「忽略」→ 写入 `event_ignore_151`
- 第二次同 `result_id` 再次触发 → 前端调用 `/api/check_preference?key=event_ignore_151` → 命中偏好 → **跳过弹窗**
- 第三次同 `result_id` → 同样跳过

**结果**: `event_ignore_151` / `event_ignore_153` 被记住，不重复弹窗 ✅

#### 场景 2：忽略不打扰

用户对推理结果点击「忽略」后：
- 后端写入 `event_ignore_<id>` 偏好（永久）
- 后续同 `result_id` 在偏好生效期内 **不再弹窗**

**结果**: 用户忽略后不打扰 ✅

#### 场景 3：稍后 30s / 5min

| 按钮 | 写入偏好 | 过期时间 |
|---|---|---|
| ⏰ 稍后(30s) | `event_snooze_<id> = snooze`，`expires_at` = now + 30s | 30 秒后自动过期 |
| ⏰ 稍后(5分) | `event_snooze_<id> = snooze`，`expires_at` = now + 300s | 5 分钟后自动过期 |

过期后再次触发同 `result_id` 将重新弹窗询问。

#### 场景 4：恢复默认

| 操作 | 版本变化 | 效果 |
|---|---|---|
| 初始 | - | 无偏好 |
| 写入第一条 ignore → | v1 → v2 | 偏好列表中可见 |
| 写入第二条 ignore → | v3 | 偏好列表中可见 |
| 写入 label_correct → | v4 | 偏好列表中可见 |
| 写入第一条 ignore → | v5 | 偏好列表中可见 |
| 写入第三条 ignore → | v6 | 偏好列表中可见 |
| 点击「🔄 恢复默认」→ | v6 → v7 | 偏好清空，显示"已恢复默认" ✅ |
| 再次点击恢复默认 → | v7 → v8 | 确认已空 ✅ |

---

### 前后对照表

| 场景 | 修改前 | 修改后 |
|---|---|---|
| 同一事件重复弹出 | 同一 `result_id` 弹窗 3 次 | 0 次（首次忽略后永久去重） |
| 用户依赖 | 仅有 60s 局部冷却 + localStorage | 持久化偏好 + 过期时间 + 版本控制 |
| 可恢复性 | 无 | 一键「🔄 恢复默认」 |
| 偏好可见性 | 无 | 偏好面板实时显示所有条目 |

---

### 配置版本变更记录

| 版本 | 触发操作 | 说明 |
|---|---|---|
| v1 | 建表初始 | `user_preferences` 表为空 |
| v2 → v4 | 写入 ignore / retake / label_correct | 每次 API 自动 `_get_next_config_version()` |
| v5 → v6 | 继续写入偏好 | 版本递增 |
| v6 → v7 | 点击「🔄 恢复默认」 | 清空所有偏好，版本 +1 ✅ |

---

### 偏好键规则表

| 键模式 | 来源 | 含义 |
|---|---|---|
| `event_ignore_<id>` | `POST /api/record_user_action` action=ignore | 永久忽略该推理结果 |
| `event_retake_<id>` | `POST /api/record_user_action` action=retake | 对该结果请求重拍 |
| `event_snooze_<id>` | 「稍后」按钮 → `POST /api/preference` | 暂缓该结果，带 `expires_at` |
| `label_correct_<id>` | `POST /api/correct_label` | 人工纠正的标签值 |
| `_RESET_` | `POST /api/preferences/reset` | 重置标记，版本号递增 |

---

### 文件清单

```
week12_feedback_preferences/
├── server/
│   ├── app.py                ← 新增 user_preferences 建表 + 4 API + 偏好钩子
│   ├── templates/
│   │   └── index.html        ← 新增偏好面板 + 去重拦截 + 稍后按钮 + JS 轮询
│   └── static/               ← 不变
└── esp32_firmware/           ← 完全未动，只读
```

---

### 补充说明

- 所有已有业务逻辑（多源状态/NLP/视觉推理/主动询问）零改动
- 偏好写入是幂等的（`INSERT OR REPLACE`），重复写入不会产生脏数据
- 过期偏好在前端不展示状态位，但 `check_preference` 会自动过滤已过期的记录
- `config_version` 用于前端增量同步判断，避免不必要的全量刷新

---

## 第13周：边缘推理能力注册与云+本地回退

> **提交日期**: 2026-10-13
> **对应目录**: `week13_14_15_edge_inference/`（涵盖第13、14、15周全功能完整版）

### 1. 功能概述

将推理能力从纯云端扩展到"云端优先 + 近端边缘回退"的双层架构，新增能力注册表、离线检测横幅和本地规则推理引擎。

```
┌──────────────────────────────┐
│   用户请求推理（页面按钮）      │
└────────────┬─────────────────┘
             ▼
    ┌─────────────────┐
    │  /api/infer      │  统一推理入口
    └────────┬────────┘
             │
    ┌────────▼────────┐    ┌──────────────────┐
    │  云端 DeepSeek   │───▶│ source=cloud      │
    │  (优先尝试)       │    │ 云端推理标签       │
    └────────┬────────┘    └──────────────────┘
             │ 失败/未配置
    ┌────────▼────────┐    ┌──────────────────┐
    │  /api/local_infer│───▶│ source=local_near_edge │
    │  本地规则引擎     │    │ 近端边缘验证标签    │
    └─────────────────┘    └──────────────────┘
```

### 2. 新增 API 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/capabilities` | GET | 返回能力注册表 + 运行位置清单 |
| `/api/local_infer` | POST | 本地规则推理（读取 `source_states` 表） |
| `/api/infer` | POST | 云优先 + 本地回退统一入口 |
| `/api/offline_status` | GET | 当前离线状态查询 |

### 3. 测试验证

| 场景 | 预期 | 结果 |
|------|------|------|
| 断开外网后本地推理仍运行 | `source=local_near_edge`，显示「近端边缘验证」 | ✅ |
| 联网增强可用提示 | 云端可用→`source=cloud`；不可用→回退本地 | ✅ |
| 仅电脑推理标注 | 橙色标签「目标设备验收待补」，不冒充 ESP32 | ✅ |
| 能力表正确 | 两表：本地/联网能力表 + 运行位置清单 | ✅ |
| 离线横幅自动切换 | 断网→橙色横幅；联网→自动消失（15s轮询） | ✅ |

### 4. 代码变更

- **server/app.py**: 新增 `check_offline_status()`、capabilities 字典、4 个 API 路由（~130行）
- **templates/index.html**: 新增离线横幅 CSS、🔌 运行位置与能力 Tab、边缘推理按钮、`runEdgeInference()`、`loadCapabilities()`、`checkOfflineStatus()`
- **esp32_firmware/main.c**: 零改动

### 5. 启动方法

```bash
cd server
pip install flask opencv-python-headless pillow openai torch torchvision numpy python-dotenv
python app.py
```

浏览器打开 `http://10.1.41.43:5000`。

---

## 第14周：离线缓存与断网续传 + 看门狗加固

> **对应目录**: `week13_14_15_edge_inference/`（涵盖第13、14、15周全功能完整版）

### 1. 功能概述

实现 ESP32 离线场景下的数据缓存与网络恢复后的自动续传，同时加固看门狗定时器防止 HTTP 长耗时触发复位。

```
┌──────────────────────┐         Wi-Fi 可用时        ┌──────────────────────┐
│   ESP32-S3-EYE       │ ──── 实时上传 (live) ──────▶│   Flask Server       │
│   传感器采集          │                              │   delivery_status     │
│                      │         Wi-Fi 断线时         │   = 'live'           │
│   ┌────────────────┐ │                              │                      │
│   │ 环形缓冲区(90条)│ │                              │   Wi-Fi 恢复后         │
│   │ 缓存+时间戳     │ │ ──── 批量续传 (recovered) ──▶│   delivery_status     │
│   └────────────────┘ │                              │   = 'recovered'       │
└──────────────────────┘                              └──────────────────────┘
```

### 2. ESP32 端实现

| 组件 | 说明 |
|------|------|
| **环形缓冲区** | `CACHE_QUEUE_SIZE=90`，`cache_record_t` 结构体存储 ax/ay/az/device_time；90 条 @1 Hz ≈ 90~100 s 离线窗口（约 8 KB RAM）。**必须大于服务端 `recovered` 判定阈值 30 s**，否则记录会被环形覆盖、补传时 `delay` 全部 < 30 s，被误标为 `live` |
| **缓存互斥锁** | `g_cache_mutex` FreeRTOS 信号量保护并发访问 |
| **自动续传** | `retransmit_cached_records()` → WiFi 恢复后逐条重传缓存数据 |
| **时间戳回退** | `get_valid_timestamp()` → SNTP 未同步时回退到编译时间（`__DATE__`） |
| **看门狗加固** | `esp_task_wdt_reset()` 在 `http_upload()` 和 `capture_and_upload()` 中调用，防止长 HTTP 耗时触发 WDT |

### 3. 服务器端实现

| 功能 | 说明 |
|------|------|
| **delivery_status** | `accelerometer` 表新增列，`'live'` 正常 / `'recovered'` 续传 |
| **original_ts** | 记录数据原始采集时间戳 |
| **retransmit_ts** | 记录续传发生时间 |
| **transmission_status** | `source_states` 表新增列，前端显示延迟徽章 |

### 4. 数据流标记

```
            正常路径: delivery_status='live', transmission_status='live'
离线缓存→恢复上传: delivery_status='recovered', transmission_status='recovered'
```

前端根据 `transmission_status === 'recovered'` 显示 🟡「离线恢复」徽章。

### 5. 验证清单

- [x] 环形缓冲区缓存最多 90 条离线数据（≈90 s，覆盖服务端 30 s 的 `recovered` 判定阈值）
- [x] WiFi 断线时数据写入缓冲区不丢失
- [x] WiFi 恢复后自动批量续传（标记 `recovered`）
- [x] 前端显示「离线恢复」延迟徽章
- [x] `esp_task_wdt_reset()` 防止 HTTP 超时触发看门狗复位

### 5.1 实机验证记录（2026-11-02 10:37–10:39，COM4）

> 证据文件（本地，`/evidence/` 与 `*.log` 已被 `.gitignore` 忽略）：`evidence/week14/serial_week14.log`、`serial_retransmit_excerpt.txt`、`flask_week14.log`、`db_check.txt`、`sensor_history_week14.txt`。

**先说两个挡路的坑**（与续传逻辑无关，但极易被误读成"补传没生效"）

| 现象 | 根因 | 处置 |
|------|------|------|
| `esptool` 报 `PermissionError(13, '拒绝访问')` / `Could not open COM4` | COM4 被上一轮的 `idf.py monitor` 一直持有（该 monitor 的日志 10:05 后就没再写行，进程却在跑） | 结束该 monitor 释放端口；烧录改用 `evidence/week14/flash_usb.ps1`，按 `--before=default_reset → no_reset → usb_reset` 三种策略重试 |
| 串口每 10 s 一条 `E BOD: Brownout detector was triggered`，永远连不上 Wi-Fi | 板子在 Wi-Fi 发射瞬间掉压复位（换后置 USB 口 + 粗线后仍复现），与固件逻辑无关 | `main.c` 在 `esp_wifi_start()` 后加 `esp_wifi_set_max_tx_power(32)`（8 dBm）降低峰值电流；修复后连续 4 分钟 **0 条 BOD**，Wi-Fi 一次连上 |

> 另一条坑：`idf.py monitor` 在 ESP32-S3 **原生 USB（USB-Serial-JTAG）** 上会因 DTR/RTS 触发芯片复位 → `ClearCommError (PermissionError 13)` → monitor 重连 → 再复位，形成死循环。本次改用 `evidence/week14/serial_capture.py`（`open()` 前设 `dtr=False/rts=False`，纯只读，不碰控制线）抓串口，稳定无复位。

**时间线（串口 + `flask.log` + DB 三方对齐）**

| 时间 | 事件 | 证据 |
|------|------|------|
| 10:37:04 | Flask 停机，设备 5 次轮询失败后转入本地缓存 | 串口 `Server unreachable (5 consecutive failures), collecting for local cache (queue=1/90)` |
| 10:37:04–10:38:33 | 断网窗口 **89 s**，逐秒入队，峰值 `queue=23/90`（未触顶，无环形覆盖丢帧） | 串口 23 行 `Cached locally (queue=n/90)`，n=1…23 |
| 10:38:33 | 重启 `python app.py`（服务端在线） | `flask.log` 恢复记录请求 |
| 10:38:36 | 检测到服务端恢复，开始批量补传 | 串口 `RETRANSMIT: sending 23 cached records` |
| 10:38:36–10:38:51 | 23 条逐条补传完毕，队列清零 | 串口 `RETRANSMIT done: 23/23 records sent, 0 remain in queue`；服务端 `Upload: detected RECOVERED delivery (delay=51s)` / `delivery=recovered` |
| 10:38:51 之后 | 回到 1 Hz 实时上传 | 串口持续 `Poll response (22 bytes): {"has_request":false}` |

**DB 核对（表 `accelerometer`，`delay = retransmit_ts - original_ts`）**

| id | original_ts | retransmit_ts | delay | delivery_status | 说明 |
|----|-------------|---------------|-------|-----------------|------|
| 16 | 10:37:04 | 10:38:36 | **92 s** | `recovered` | 断网最早一条 |
| 24 | 10:37:36 | 10:38:43 | 67 s | `recovered` | 中间段 |
| 34 | 10:38:17 | 10:38:48 | **31 s** | `recovered` | 刚好越过 30 s 阈值 |
| 35 | 10:38:21 | 10:38:48 | 27 s | `live` | ≤30 s，按 `app.py:359-363` 仍算 `live` |
| 36–38 | 10:38:25–10:38:33 | 10:38:49/50 | 24 / 20 / 17 s | `live` | 同上 |

**结论**：23 条缓存 = **19 条 `recovered`（delay 31–92 s）+ 4 条 `live`（delay 17–27 s）**，与服务端"`delay > 30 s` 才判 recovered"的规则完全吻合（不是丢数据）；`/api/sensor_history?count=60` 返回同样的 `delivery_status / original_ts / retransmit_ts`，前端数据表可直接标出「📦 补传」。修复发射功率后未再出现 BOD，入队 23 条、出队 23 条，无丢失。

---

### 文件清单

```
week13_14_15_edge_inference/     ← 涵盖第13、14、15周全功能完整版
├── esp32_firmware/
│   ├── main/
│   │   └── main.c              ← 环形缓冲区 + 离线续传 + WDT 加固
│   └── CMakeLists.txt
├── server/
│   ├── app.py                  ← capability/infer + delivery_status + 续传标记
│   ├── templates/
│   │   └── index.html          ← 边缘推理 UI + 运行位置 Tab + 离线横幅
│   ├── static/
│   │   └── captured/
│   └── requirements.txt
└── README_SUBMIT.md
```

---

## 第15周：处理重复、迟到与过期任务
* **幂等防重（防重复上传）**：服务端 `/api/upload` 使用 `BEGIN IMMEDIATE` 事务锁，对同一 `request_id` 的并发上传进行串行化校验，100次并发仅落库1条。
* **过期拦截（防旧指令复活）**：服务端下发任务时带上 `expire_at`。设备端对比本地 SNTP 时间，若判定过期，则不执行采集，直接回传 `EXPIRED` 回执，彻底杜绝过时指令执行。
* **设备端防重放**：设备端 RAM 中记录 `last_executed_request_id`，收到相同 ID 时直接跳过，避免浪费算力和传感器寿命。

---

## 第16周：用任务与运行数据检验体验
* **测试方法**：以 2 名真实同伴开展形成性测试（如实记录，不外推至儿童或老人）。
* **真实问题暴露**：发现并记录了 2 个真实的交互盲区（首次点击等待易引发误触连点、对降级黄条产生报错误解）。
* **改进计划**：针对真实测试反馈，提出了 3 项后续优化建议（如增加 Loading 倒计时、修改黄条文案等），详情见 `week16_usability_test/README.md`。

---

## 第17周：完成改进与个人项目迁移
* **基于证据的修改**：针对第16周同伴测试暴露的“等待焦虑误触”与“误解降级文案”问题，优化了前端交互（增加 3 秒倒计时防抖机制，并修改了降级横幅提示语）。
* **代码与回归**：通过 Node 语法校验与 Flask 接口测试，验证了修改未破坏原有 `request_id` 状态机逻辑。
* **个人项目迁移**：将第14周的“断网环形缓存与双时间戳比对机制”成功迁移至个人项目“边缘 AI 健康监护（心率监测）”场景，确保医疗级历史数据在补传时不会冒充当前实时数据，详情见 `week17_migration_and_fix/README.md`。

---

## 第18周：现场验收与联合复盘
* **真实交付**：完成了可运行原型的最终归档。项目坚守了“不过度包装”的原则，明确列出了未接入真实云端模型（语音、视觉）的遗留问题。
* **验收索引**：详细的能力清单与未完成项说明见 `week18_final_acceptance/README.md`。

---
