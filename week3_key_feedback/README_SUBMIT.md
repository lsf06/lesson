# Week 3: GPIO0 按键触发事件反馈系统

> **项目名称**: group01_esp32s3eye — QMA6100P EgoLink DevBench  
> **提交日期**: 2026-09-30  

---

## 1. 系统架构

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

---

## 2. 按键触发流程

| 步骤 | 操作 | HTTP 请求 | 前端状态 | 指示灯 |
|------|------|-----------|----------|--------|
| **1** | 按下 GPIO0 (BOOT) 键 | `POST /api/trigger` | **本地触发** / 等待确认 | 🟠 橙色闪烁 |
| **2** | 服务器收到事件 → 写入 `trigger_events` → ACK | 返回 `200 {"ack": true}` | **远端已确认** | 🟢 绿色发光 |
| **3** | 再次按下 GPIO0 (BOOT) 键 | `POST /api/cancel` | **已取消** | 🔴 红色 |
| **4** | 无事件 / 初始状态 | — | **待机** | ⚪ 灰色 |

### 状态定义（数据库 `trigger_events` 表）

| status | 含义 | 点亮颜色 |
|--------|------|----------|
| `IDLE` | 无事件（API 默认返回） | 灰色 `#8b949e` |
| `LOCAL_TRIGGERED` | 按键已按下但未收到服务器确认 | 橙色 `#d2991d`（闪烁） |
| `REMOTE_ACKED` | 服务器已确认收到触发 | 绿色 `#3fb950`（发光） |
| `CANCELLED` | 用户取消了本次触发 | 红色 `#f85149` |

---

## 3. 文件结构

```
week3_key_feedback/
├── server/
│   ├── app.py              # Flask 应用（含 /api/trigger, /api/cancel, /api/trigger_status）
│   ├── templates/
│   │   └── index.html       # Web 前端（500ms 轮询 trigger_status）
│   ├── static/
│   │   └── echarts.min.js   # ECharts 图表库
│   └── sensor_data.db       # SQLite 数据库
├── esp32_firmware/
│   ├── main/
│   │   └── main.c           # ESP32 固件（GPIO0 按键 → HTTP POST trigger/cancel）
│   ├── CMakeLists.txt
│   └── build_flash.bat      # 编译烧录一键脚本
└── README_SUBMIT.md         # 本文件
```

---

## 4. 编译与烧录（ESP32）

```batch
cd week3_key_feedback\esp32_firmware
build_flash.bat
```

该脚本自动完成：
1. `idf.py fullclean`
2. `idf.py build`
3. `idf.py -p COM4 flash`
4. `idf.py -p COM4 monitor`

---

## 5. 启动 Flask 服务器

```batch
cd week3_key_feedback\server
python app.py
```

服务器地址: `http://0.0.0.0:5000`

---

## 6. API 接口

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

---

## 7. 关键参数

| 参数 | 位置 | 值 |
|------|------|-----|
| 轮询间隔（状态） | `index.html` `setInterval` | 500ms |
| 按键引脚 | `main.c` | GPIO0 |
| HTTP 超时 | `main.c` | 5000ms |
| 服务器端口 | `app.py` | 5000 |
| 前端刷新率 | `index.html` `refresh` | 200ms |
| 波形点数 | `index.html` `MAX_POINTS` | 200 |

---

## 8. Bug 修复记录

| 日期 | 问题 | 根因 | 修复 |
|------|------|------|------|
| 2026-09-30 | 前端按键状态不更新 | `index.html` 第 269 行多余 `}` 导致 JS 语法错误，`pollTriggerStatus()` 及之后所有代码未执行 | 删除多余 `}` |
| 2026-09-30 | HTTP 错误信息不明确 | `main.c` 只打印 `esp_err_to_name` 无十六进制码 | 添加 `(0x%x)` 和完整 URL 日志 |