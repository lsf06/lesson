﻿# Week 8: 视觉推理与人工反馈 (Vision Feedback)

> **项目名称**: group01_esp32s3eye — QMA6100P EgoLink DevBench  
> **提交日期**: 2026-10-01  

---

## 0. 最终验证结果 ✅

| 测试项 | 结果 | 输出 |
|--------|------|------|
| **ESP32 板载 OV2640 摄像头初始化** | ✅ **通过** | Detected OV2640 camera + Camera OV2640 initialized: QVGA JPEG PSRAM |
| **网页「拍照」显示真实图像** | ✅ **通过** | 前端显示实时彩色画面，右上角绿色「📷 实时拍摄 (ESP32-CAM)」标签 |
| **ESP32 按键触发（红→绿）** | ✅ **通过** | 初始红色 → 按键后变绿 |
| **历史记录 & 防作弊** | ✅ **通过** | 清除旧图 + 失败清空，无旧图残留 |
| **poll_service 独立任务轮询** | ✅ **通过** | 每秒 Poll response，看门狗无触发 |
| **服务器 → 板端拍照指令全链路** | ✅ **通过** | 网页点击「拍照」→ 服务器推送 → ESP32 拍照上传 → 网页展示 |
| **推理面板正常显示** | ✅ **通过** | 推理标签、置信度、模型版本、状态正确展示 |
| **低分 uncertain 状态** | ✅ **通过** | 30% 概率触发，显示橙色「⚠️ 不确定 (uncertain)」 |
| **模拟推理标注** | ✅ **通过** | 模型版本 MOCK-V1，橙色警告条「⚠️ 当前为模拟推理（仅演示界面）」 |
| **人工纠正** | ✅ **通过** | 弹窗输入 → 显示「模型说 XX / 人工纠正为 YY」对比 |
| **重新采集** | ✅ **通过** | 清空推理结果 → 重新拍照 → 重新推理 |

---

## 1. 新增功能总览

| 功能 | 后端 | 前端 | 说明 |
|------|------|------|------|
| **模拟视觉推理** | _mock_infer() + ENABLE_MOCK_VISION=True | 推理面板 | 约 30% 低分概率，标注 MOCK-V1 |
| **推理结果展示** | POST /api/infer_image | 标签 / 置信度 / 版本 / 状态 | 橙色警告条标注模拟推理 |
| **人工纠正** | POST /api/correct_label | 弹窗输入纠正标签 | 保存三方对应：image_path / model / human |
| **模型 vs 人工对比** | vision_results 表存储 | 对比面板 | 🤖 模型说 vs 🙋 人工纠正为 |
| **重新采集** | ecapture() | 清空推理结果重新拍照 | 避免旧 ID 被错误使用 |
| **推理历史** | GET /api/vision_history | 历史记录展示 | vision_results 表查询 |

---

## 2. 视觉推理流程

### 2.1 完整交互流程


### 2.1 完整交互流程

`
用户点击「📷 拍照」
       │
       v
采集图片成功 → 显示「📸 图片已采集，点击「推理」进行分析」
       │
       v
用户点击「🔍 推理」
       │
       v
POST /api/infer_image
       │
       ├─ _mock_infer() ← 模拟推理（约 30% 概率低分）
       │   └─ 返回 { label, score, model_version, status }
       │
       ├─ INSERT INTO vision_results (image_path, model_label, ...)
       │   └─ cursor.lastrowid → result_id 返回前端
       │
       v
前端展示推理面板：
   ├─ 推理标签：物体移动 / 光照变化 / ...
   ├─ 置信度：89.8%（或 44.3% 触发 uncertain）
   ├─ 模型版本：MOCK-V1
   ├─ 状态：✅ 成功 或 ⚠️ 不确定
   └─ ⚠️ 当前为模拟推理（仅演示界面）
       │
       v
用户点击「✏️ 人工纠正」
       │
       ├─ 弹窗输入纠正后标签
       └─ POST /api/correct_label { result_id, corrected_label }
            └─ UPDATE vision_results SET human_corrected_label=?
                 └─ 显示对比面板：模型说 XX vs 人工纠正为 YY
`

### 2.2 模拟推理机制

`python
ENABLE_MOCK_VISION = True  # 全局开关

def _mock_infer():
    \"\"\"模拟推理：约 30% 概率返回低分 (< 0.7) 以演示 uncertain 状态。
    标注 model_version: 'MOCK-V1'，严禁冒充真实模型分数。\"\"\"
    candidates = ['环境正常', '人员走动', '物体移动', '光照变化', '异常闯入', '设备异常', '画面模糊']
    label = random.choice(candidates)
    # 30% 低分概率 → uncertain 状态
    if random.random() < 0.3:
        score = random.uniform(0.30, 0.68)
        status = 'uncertain'
    else:
        score = random.uniform(0.70, 0.98)
        status = 'success'
    return {
        'label': label,
        'score': round(score, 4),
        'model_version': 'MOCK-V1',
        'status': status
    }
`

**关键点**：
- 🔴 模型版本固定为 MOCK-V1，前端显示橙色警告条
- 🔴 约 30% 概率 score < 0.7，status = uncertain
- 🔴 前端用橙色 (ar(--orange)) 区分 uncertain 状态
- 🔴 分数写在 mock-score CSS 类中，不与真实模型混淆

### 2.3 人工纠正流程

`
┌─ 推理完成后 ──────────────────────────────────┐
│ lastVisionResultId = data.result_id (数据库主键) │
└────────────────────────────────────────────────┘
       │
       v
用户点击「✏️ 人工纠正」
       │
       v
prompt('✏️ 输入纠正后的标签：')
       │
       ├─ 取消或空 → 不做任何操作
       └─ 输入有效标签 →
            POST /api/correct_label
            { result_id: lastVisionResultId, corrected_label: "凳子" }
            │
            v
            数据库 UPDATE vision_results SET
            human_corrected_label = "凳子",
            corrected_at = "2026-10-01T..."
            WHERE id = ?
            │
            v
            前端显示对比面板：
            🤖 模型说：物体移动（89.8%）
            🙋 人工纠正为：凳子
`

---

## 3. 视觉推理 API

### POST /api/infer_image

**请求**: {}（空请求体）

**成功响应**:
`json
{
  "success": true,
  "label": "光照变化",
  "score": 0.891,
  "model_version": "MOCK-V1",
  "status": "success",
  "image_path": "D:/.../static/captured/latest.jpg",
  "result_id": 3
}
`

**低分响应**:
`json
{
  "success": true,
  "label": "环境正常",
  "score": 0.443,
  "model_version": "MOCK-V1",
  "status": "uncertain",
  "image_path": "D:/.../static/captured/latest.jpg",
  "result_id": 4
}
`

**无图片响应**:
`json
{
  "success": false,
  "error": "no image available for inference"
}
`

### POST /api/correct_label

**请求**:
`json
{
  "result_id": 3,
  "corrected_label": "凳子"
}
`

**成功响应**:
`json
{
  "success": true,
  "message": "label corrected",
  "result_id": 3
}
`

### GET /api/vision_history?limit=20

**响应**:
`json
{
  "success": true,
  "history": [
    {
      "id": 3,
      "image_path": "...",
      "model_label": "物体移动",
      "model_score": 0.898,
      "model_version": "MOCK-V1",
      "status": "success",
      "human_corrected_label": "凳子",
      "corrected_at": "2026-10-01T12:00:00",
      "created_at": "2026-10-01T11:59:00"
    }
  ]
}
`

---

## 4. 数据库设计

### vision_results 表

`sql
CREATE TABLE IF NOT EXISTS vision_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL,
    model_label TEXT NOT NULL,
    model_score REAL NOT NULL,
    model_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    human_corrected_label TEXT,
    corrected_at TEXT,
    created_at TEXT NOT NULL
)
`

**三方对应关系**：
- image_path — 推理的原始图片
- model_label + model_score + model_version — 模型推理结果
- human_corrected_label + corrected_at — 人工纠正结果

---

## 5. 文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| week8_vision_feedback/ | 新建 | 从 week7_image_capture 复制 |
| server/app.py | **大幅修改** | 新增 init_vision_db()、_mock_infer()、/api/infer_image、/api/correct_label、/api/vision_history |
| server/templates/index.html | **大幅修改** | 新增推理面板、橙色警告条、人工纠正按钮、重新采集按钮、对比展示 |
| README_SUBMIT.md | 修改 | 本文件 |

**未变更文件**（保留 week7 源内容）：
- esp32_firmware/main/main.c ❌
- esp32_firmware/CMakeLists.txt ❌
- precaptured_images/ ❌

---

## 6. 项目目录结构

`
D:.
├── week8_vision_feedback/
│   ├── server/
│   │   ├── app.py
│   │   ├── requirements.txt
│   │   ├── static/
│   │   │   └── captured/
│   │   └── templates/
│   │       └── index.html
│   ├── precaptured_images/
│   │   ├── sample_hallway.png
│   │   ├── sample_desk.png
│   │   └── sample_corridor.png
│   ├── esp32_firmware/
│   │   ├── main/main.c
│   │   ├── components/esp32_camera/
│   │   └── CMakeLists.txt
│   └── README_SUBMIT.md
`

---

## 7. 硬件环境

| 项目 | 配置 |
|------|------|
| **开发板** | ESP32-S3-EYE (ESP32-S3R8 + PSRAM 8MB) |
| **摄像头** | 板载 OV2640（通过 FPC 排线连接） |
| **串口** | COM4 (CP2102 USB 转串口) |
| **WiFi** | SSID: 431 / 密码: 88888888 |
| **服务器 IP** | 10.1.41.43:5000 |
| **IDF 版本** | ESP-IDF v5.4.4 |
| **设备 ID** | group01_esp32s3eye |

### 7.1 启动步骤

`atch
:: 1. 启动 Flask 服务器（Windows）
cd week8_vision_feedback\server
pip install -r requirements.txt
python app.py

:: 2. ESP32 烧录固件（沿用 week7 固件，无需修改）
cd week8_vision_feedback\esp32_firmware
call "%%IDF_PATH%%\export.bat"
idf.py -p COM4 flash

:: 3. ESP32 自动运行（不要用阻塞的 monitor）

:: 4. 浏览器打开
http://10.1.41.43:5000

:: 5. 拍照 → 推理 → 人工纠正
`

> ⚠️ **浏览器要求**: 推荐 Chrome / Edge / Safari

---

## 8. 测试场景

### 8.1 正常推理（高分样例）
**操作**: 拍照 → 点击「🔍 推理」
**预期**:
- 显示推理标签（如「物体移动」）
- 置信度 > 70%（如 89.8%）
- 状态：「✅ 成功 (success)」
- 模型版本：「MOCK-V1」
- 橙色警告条：「⚠️ 当前为模拟推理（仅演示界面）」

### 8.2 低分推理（uncertain 样例）
**操作**: 多次点击「🔍 重新推理」
**预期**: 约 30% 概率触发：
- 置信度 < 70%（如 44.3%）
- 标签变橙色
- 状态：「⚠️ 不确定 (uncertain)」

### 8.3 人工纠正
**操作**: 推理完成后 → 点击「✏️ 人工纠正」→ 输入「凳子」
**预期**:
- 弹窗成功弹出（不会提示"请先执行推理"）
- 对比面板显示：
  - 🤖 模型说：物体移动（89.8%）
  - 🙋 人工纠正为：凳子
- 纠正按钮变为「✏️ 已纠正 ✓」

### 8.4 重新采集
**操作**: 推理完成 → 点击「📷 重新采集」
**预期**:
- 推理结果面板清空
- 触发新的拍照流程
- 显示「📸 图片已采集，点击「推理」进行分析」

### 8.5 ESP32-CAM 真实拍照（同 week7）
**操作**: 点击拍照按钮
**预期**:
- ESP32 串口: Poll response + Captured JPEG: xxx bytes
- 前端显示彩色画面, 右上角绿色[实时拍摄 ESP32-CAM]标记

### 8.6 防作弊（同 week7）
**操作**: 拍照成功 → 遮挡摄像头 → 再次拍照
**预期**: 失败时旧图消失, 仅显示错误信息

---

## 9. 排错历程

### 9.1 推理无图片可用
| 问题 | 原因 | 解决 |
|------|------|------|
| 
o image available for inference | pi_infer_image 查找 precaptured_images/latest.jpg，但 ESP32 图片存于 static/captured/latest.jpg | 统一路径为 os.path.join(__file__, 'static', 'captured') |

### 9.2 人工纠正弹窗失败
| 问题 | 原因 | 解决 |
|------|------|------|
| 点击「人工纠正」提示「请先执行推理」 | 后端未返回 esult_id，前端 data.id 为 undefined | 后端加 cursor.lastrowid + esult['result_id']；前端读 data.result_id |

### 9.3 模拟推理标注
| 问题 | 原因 | 解决 |
|------|------|------|
| 需区分模拟与真实推理 | 老师要求当堂可见模拟标记 | model_version: "MOCK-V1" + 橙色警告条 |

---

## 10. 技术决策

| 决策 | 理由 |
|------|------|
| ENABLE_MOCK_VISION = True 全局开关 | 可一键切换真实/模拟推理 |
| MOCK-V1 固定版本号 | 前端据此显示橙色警告条，避免混淆 |
| 30% 低分概率 | 保证当堂演示可见 uncertain 状态 |
| lastrowid 返回前端 | 人工纠正需要数据库主键 |
| 路径统一为 static/captured/latest.jpg | 与 capture 端点存图路径一致 |
| orange 色区分 uncertain | 不与 success 的绿色混淆 |
| ecapture() 清空 lastVisionResultId | 防止旧 ID 被错误用于新图片 |
