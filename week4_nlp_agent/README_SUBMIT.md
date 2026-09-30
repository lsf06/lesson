# Week 4: 自然语言查询与请求采集 (NLP Agent)

> **项目名称**: group01_esp32s3eye — QMA6100P EgoLink DevBench  
> **提交日期**: 2026-09-30  

---

## 1. 系统架构（双路径设计）

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

**核心特性**：
- 有 API key 时走大模型（DeepSeek function calling），精准理解意图
- 无 API key 时自动降级到本地规则引擎，零外部依赖
- 歧义输入（如"查一下那个东西"）不猜测，反问用户指定设备
- 越界设备（不在白名单）直接拒绝

---

## 2. 前端功能：自然语言对话面板

网页右下角新增 **🔮 自然语言查询** 面板，包含：

- 💬 对话窗口 — 用户输入（蓝色气泡）与系统回复（灰色气泡）
- 📝 输入框 — 支持回车发送
- 🏷 Badge 状态 — 实时显示当前执行的工具：`📡 查询` / `📥 采集` / `🤖 大模型`

---

## 3. 网页测试用例（5 个场景）

### ① 查询最新数据 ✅
**输入**: "查看 group01_esp32s3eye 的最新数据"  
**解析**: `tool_query_latest`, device_id=group01_esp32s3eye  
**返回**:
```
📡 设备 group01_esp32s3eye 最新数据：
　AX=0.12　AY=-0.03　AZ=9.81
　📅 设备时间：2026-09-30 19:00:00
　⏱ 服务器时间：2026-09-30 19:00:01
```
**Badge**: `📡 查询`

---

### ② 重新采集数据 ✅
**输入**: "帮 group01_esp32s3eye 重新采集一次"  
**解析**: `tool_request_collection`, device_id=group01_esp32s3eye  
**返回**:
```
✅ 采集成功！设备 group01_esp32s3eye 已上报：
　AX=0.15　AY=-0.01　AZ=9.78
　📅 设备时间：2026-09-30 19:00:05
　🔖 request_id: 20260930_190005_ABCDEF
```
**Badge**: `📥 采集`

---

### ③ 歧义反问 ✅
**输入**: "查一下那个东西"  
**解析**: ambiguous=True（含代词"那个"，无明确设备）  
**返回**: `🤔 请问您要查的是什么设备的数据？目前支持：group01_esp32s3eye。`  
**Badge**: 不变（未执行工具）

---

### ④ 越界拒绝 ✅
**输入**: "查一下 group99_fake 的最新数据"  
**解析**: rejected=True（group99_fake 不在白名单）  
**返回**: `⛔ 设备 "group99_fake" 不在白名单中。仅支持：group01_esp32s3eye。`  
**Badge**: 不变（未执行工具）

---

### ⑤ 无意义输入 ✅
**输入**: "今天天气不错"  
**解析**: ambiguous=True（无法识别查询/采集意图）  
**返回**: `🤔 抱歉，我没理解您的意图。请问要"查看最新数据"还是"重新采集"？支持：group01_esp32s3eye。`

---

## 4. 单元测试结果（test_nlp.py）

```
测试目标：本地规则引擎 _local_nlp_parse()
环境：openai 未安装 → 自动使用 local rule engine

[PASS] "查看 group01_esp32s3eye 的最新数据" → tool_query_latest
[PASS] "查一下那个东西"                    → ambiguous（反问）
[PASS] "帮 group01_esp32s3eye 重新采集一次" → tool_request_collection
[PASS] "查一下 group99_fake 的数据"         → rejected（越界）
[PASS] "帮我测一下"                         → tool_request_collection
[PASS] "今天天气不错"                       → ambiguous（无意图）
[PASS] "上一条记录是什么"                   → tool_query_latest
[PASS] "测一下"                             → tool_request_collection
[PASS] "查一下那个东西"                     → ambiguous（反问）

ALL TESTS PASSED ✅  (9/9)
```

运行方式：
```batch
cd week4_nlp_agent\tools
python test_parser_unit.py
```

---

## 5. 硬件环境

| 项目 | 说明 |
|------|------|
| **固件** | 复用 Week 3 固件，板子端代码未修改 |
| **硬件** | ESP32-S3-EYE (QMA6100P) |
| **端口** | COM4 |
| **编译烧录** | `cd esp32_firmware && build_flash.bat` |
| **WiFi** | 同 Week 3 配置 |

---

## 6. 文件结构

```
week4_nlp_agent/
├── server/
│   ├── app.py                 # Flask 应用（新增 /api/nlp，含 _local_nlp_parse 和 _llm_nlp_parse）
│   ├── .env                   # DEEPSEEK_API_KEY（可选，已 .gitignore）
│   ├── requirements.txt       # 依赖：flask, openai, python-dotenv, requests
│   ├── templates/
│   │   └── index.html         # Web 前端（新增 NLP 对话面板）
│   └── static/
│       └── echarts.min.js     # ECharts 图表库
├── esp32_firmware/            # 复用 Week 3 固件（未修改）
│   ├── main/
│   │   └── main.c
│   ├── CMakeLists.txt
│   └── build_flash.bat
├── tools/
│   ├── test_nlp.py            # 集成测试（依赖 Flask 运行中）
│   ├── test_parser_unit.py    # 本地解析器单元测试（纯 Python，无需 Flask）
│   └── ...                    # Week 3 原有工具脚本
└── README_SUBMIT.md           # 本文件
```

---

## 7. 启动方式

```batch
:: 1. 安装依赖
cd week4_nlp_agent\server
pip install -r requirements.txt

:: 2. （可选）配置 DeepSeek API Key
::    编辑 server\.env，填入真实的 DEEPSEEK_API_KEY
::    不填则自动使用本地规则引擎

:: 3. 启动 Flask
python app.py

:: 4. 浏览器打开
http://localhost:5000
```

---

## 8. API 接口（新增）

| 方法 | 路径 | 说明 | 请求体 |
|------|------|------|--------|
| `POST` | `/api/nlp` | 自然语言查询 / 采集 | `{"text": "查看最新数据"}` |

### 响应格式

```json
{
  "reply": "📡 设备 group01_esp32s3eye 最新数据：\n　AX=0.12　AY=-0.03　AZ=9.81\n　📅 ...",
  "success": true,
  "tool_used": "tool_query_latest",
  "data": {
    "device_id": "group01_esp32s3eye",
    "ax": 0.12,
    "ay": -0.03,
    "az": 9.81,
    "device_time": "2026-09-30 19:00:00",
    "server_time": "2026-09-30 19:00:01"
  }
}
```

---

## 9. 关键技术决策

| 决策 | 理由 |
|------|------|
| **双路径设计** | 有 API key 时用 DeepSeek function calling 精准解析；无时降级到本地规则引擎，零成本可运行 |
| **歧义必须反问** | 不做猜测，避免"查一下那个"错误匹配到 group01，造成用户困惑 |
| **白名单校验** | 即使 LLM 返回了 device_id，也逐字校验是否在白名单中，防止幻觉 |
| **采集轮询上限 10s** | 与 Week 2 的 `REQUEST_TIMEOUT_S=5` 相比放宽，给硬件更多响应时间 |
| **复用 Week 3 固件** | ESP32 侧不需要修改任何代码，NLP 解析完全在服务器端完成 |