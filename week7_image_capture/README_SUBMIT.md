# Week 7: 图像采集与防作弊 (Image Capture)

> **项目名称**: group01_esp32s3eye — QMA6100P EgoLink DevBench  
> **提交日期**: 2026-10-01  

---

## 0. 最终验证结果 ✅

| 测试项 | 结果 | 输出 |
|--------|------|------|
| **ESP32 板载 OV2640 摄像头初始化** | ✅ **通过** | `Detected OV2640 camera` + `Camera OV2640 initialized: QVGA JPEG PSRAM` |
| **网页「拍照」显示真实图像** | ✅ **通过** | 前端显示实时彩色画面，右上角绿色「📷 实时拍摄 (ESP32-CAM)」标签 |
| **ESP32 按键触发（红→绿）** | ✅ **通过** | 初始红色 → 按键后变绿 |
| **历史记录 & 防作弊** | ✅ **通过** | 清除旧图 + 失败清空，无旧图残留 |
| **poll_service 独立任务轮询** | ✅ **通过** | 每秒 Poll response，看门狗无触发 |
| **服务器 → 板端拍照指令全链路** | ✅ **通过** | 网页点击「拍照」→ 服务器推送 → ESP32 拍照上传 → 网页展示 |

---

## 1. 新增功能总览

| 功能 | 后端 | 前端 | 说明 |
|------|------|------|------|
| **ESP32 板载 OV2640 采集** | `/api/capture_image` + `/api/pending_request` | 「拍照」按钮 + 图像展示区 | 驱动真实 OV2640 摄像头拍照并上传 |
| **poll_service 独立任务** | Flask 返回 action | - | 独立 FreeRTOS 任务轮询服务器指令 |
| **预存图降级** | 摄像头不可用时自动选择预存图片 | 橙色「📁 预存图片」标记 | 无摄像头环境不崩溃 |
| **防作弊机制** | 采集前后端清除旧图 | 采集前立即清除旧图 | 老师验证：看不到旧图 |
| **预存图片库** | `precaptured_images/` 目录 (3张) | - | 纯色 PNG，保证降级可用 |

---

## 2. 图像采集流程

### 2.1 真实 ESP32-CAM 采集（主流程）

```
用户点击「📷 拍照」
       │
       v
Flask /api/capture_image
       │
       ├─ 写入 pending_request { has_request: true, action: "capture" }
       │
       v
ESP32 poll_service
       │
       ├─ http_poll_request() 发现 action == "capture"
       ├─ capture_and_upload()
       │   ├─ esp_camera_fb_get()    ← OV2640 硬件拍照
       │   ├─ JPEG 编码 (PSRAM 缓冲)
       │   └─ HTTP POST → server /api/capture_image
       │
       v
Flask 接收图片 → base64 编码
       │
       v
前端显示彩色图片 + 📷 实时拍摄 (ESP32-CAM) 绿色标记
```

### 2.2 降级流程（ESP32 不可达 / OpenCV 无摄像头）

```
用户点击「📷 拍照」
       │
       v
POST /api/capture_image
       │
       ├─ ESP32 不可达 → 尝试 OpenCV 本地摄像头
       ├─ 本地摄像头失败 → 从 precaptured_images/ 随机选择一张
       └─ 返回 JSON { success, image, source: "precaptured" }
       │
       v
前端显示图片 + 📁 预存图片 橙色标记
```

---

## 3. 防作弊机制（核心）

> 老师当堂验证时，在采集失败或「画面不可用」情况下，**绝对不允许显示上一次的旧图**。

### 3.1 前端防作弊逻辑

```javascript
function captureImage() {
    // ⚠️ 第一步：立即清空 image-area 内容
    area.innerHTML = '<div class="empty-hint">⏳ 采集进行中...</div>';
    area.className = 'image-area visible';
    lastCapturedImageUrl = null;

    // 第二步：发起采集请求
    fetch('/api/capture_image', {method:'POST'})
    .then(...)
    .catch(function(e) {
        // 已在第一步清空，此处仅显示错误
        area.innerHTML = '<div class="capture-error">⚠️ ' + e.message + '</div>';
    });
}
```

**关键点**：
- 采集请求**发送前**立即清除旧图
- 网络请求失败时，旧图已不可见
- 后端返回错误时，旧图已不可见
- `lastCapturedImageUrl` 变量也同时置空

### 3.2 后端防崩溃

```python
try:
    import cv2
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if cap.isOpened():
        ret, frame = cap.read()
        ...
except ImportError:
    log.info('OpenCV not installed, fallback to precaptured')
except Exception as e:
    log.warning('Camera error: %s, fallback', e)
```

**关键点**：
- `import cv2` 放在 try 块内，未安装时不崩溃
- 预存图不存在时返回 503，前端显示错误

---

## 4. 文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `week7_image_capture/` | 新建 | 从 week6 复制，新增图像采集功能 |
| `esp32_firmware/main/main.c` | **大幅修改** | 新增 capture_and_upload()、camera_init()、poll_service() 独立任务、I2C 复用配置、WDT 修复 |
| `esp32_firmware/CMakeLists.txt` | 修改 | 链接 camera、esp_jpeg、led_indicator 组件 |
| `server/app.py` | 修改 | 新增 `/api/capture_image`、`/api/pending_request`、ESP32 图片接收、OpenCV 集成、预存降级 |
| `server/templates/index.html` | 修改 | 新增「图像采集」面板、拍照按钮、防作弊逻辑、ESP32-CAM 标记 |
| `server/requirements.txt` | 修改 | 新增 `opencv-python`、`Pillow` |
| `precaptured_images/` | 新建 | 3 张预存图片（sample_hallway, outdoor, desk） |
| `.gitignore` | 修改 | 新增 week7 build 目录 |
| `README_SUBMIT.md` | 修改 | 本文件 |

---

## 5. 文件结构

```
week7_image_capture/
├─ server/
│   ├─ app.py                      # Flask 应用（ESP32 集成 + 图像采集端点）
│   ├─ .env                        # DEEPSEEK_API_KEY（可选）
│   ├─ requirements.txt            # 依赖（含 opencv-python、Pillow）
│   ├─ templates/
│   │   └─ index.html              # 新增图像采集面板 + 防作弊 + ESP32-CAM 标记
│   ├─ static/
│   │   ├─ echarts.min.js
│   │   └─ captured/               # ESP32/OpenCV 拍摄的图片（自动创建）
│   └─ flask.log
├─ precaptured_images/             # 预存图片（摄像头不可用时的降级）
│   ├─ sample_hallway.png
│   ├─ sample_outdoor.png
│   └─ sample_desk.png
├─ esp32_firmware/                 # ESP32-S3-EYE 固件（OV2640 驱动）
│   ├─ main/
│   │   ├─ main.c                  # 主程序：camera_init + capture_and_upload + poll_service
│   │   ├─ CMakeLists.txt          # 组件链接
│   │   ├─ camera_pins.h           # OV2640 引脚定义
│   │   └── i2c_utils.h            # I2C 复用工具
│   ├─ components/                 # 本地组件（esp32-camera）
│   ├─ build_flash.bat
│   └─ sdkconfig                   # 启用 PSRAM、CONFIG_ESP_TASK_WDT
├─ tools/
│   ├─ test_nlp.py
│   └─ ...
└─ README_SUBMIT.md                # 本文件
```

---

## 6. 硬件环境

| 项目 | 配置 |
|------|------|
| **开发板** | ESP32-S3-EYE (ESP32-S3R8 + PSRAM 8MB) |
| **摄像头** | 板载 OV2640（通过 FPC 排线连接） |
| **串口** | COM4 (CP2102 USB 转串口) |
| **WiFi** | SSID: `431` / 密码: `88888888` |
| **服务器 IP** | `10.1.41.43:5000` |
| **IDF 版本** | ESP-IDF v5.4.4 |
| **设备 ID** | `group01_esp32s3eye` |

### 6.1 启动步骤

```batch
:: 1. 启动 Flask 服务器（Windows）
cd week7_image_capture\server
pip install -r requirements.txt
python app.py

:: 2. ESP32 烧录固件
cd week7_image_capture\esp32_firmware
call "%IDF_PATH%\export.bat"
idf.py -p COM4 flash

:: 3. ESP32 自动运行（不要用阻塞的 monitor）
::    日志可通过串口工具或 VSCode 查看

:: 4. 浏览器打开
http://10.1.41.43:5000
```

> ⚠️ **浏览器要求**: 推荐 Chrome / Edge / Safari

---

## 7. API 接口

### POST /api/capture_image

**请求**: `{}`（空请求体）

**成功响应（ESP32-CAM）**:
```json
{
  "success": true,
  "image": "data:image/jpeg;base64,...",
  "source": "camera",
  "filename": "capture_20261001_120000_123456.jpg",
  "esp32_captured": true
}
```

**成功响应（预存降级）**:
```json
{
  "success": true,
  "image": "data:image/png;base64,...",
  "source": "precaptured",
  "filename": "sample_hallway.png"
}
```

**失败响应**:
```json
{
  "success": false,
  "error": "摄像头不可用且无预存图片"
}
```

### GET /api/pending_request?device_id=group01_esp32s3eye

**无请求时**:
```json
{"has_request": false}
```

**有拍照请求时**:
```json
{"has_request": true, "request_id": "...", "action": "capture"}
```

---


---

## 8. 排错历程（关键记录）

### 8.1 OV2640 摄像头驱动

| 问题 | 原因 | 解决 |
|------|------|------|
| Camera not found | 引脚与板型不匹配 | 重写 camera_pins.h |
| GPIO 越界 (GPIO>48) | 引脚号超限 | 修正到合法范围 |
| I2C 地址冲突 | OV2640 与 QMA6100P 共用总线 | CMD_SUSPEND/RESUME 复用 |
| PSRAM 分配失败 | 未启用 PSRAM | sdkconfig 启用 CONFIG_SPIRAM |
| JPEG 编码失败 | 组件未链接 | CMakeLists 添加 REQUIRES esp_jpeg |

### 8.2 poll_service 独立任务

| 问题 | 原因 | 解决 |
|------|------|------|
| while(1) 无延时导致 WDT 复位 | 无 vTaskDelay | 独立任务 + vTaskDelay |
| WDT task not found | 新任务未注册 | esp_task_wdt_add(NULL) |
| WDT 仍 5s 触发 | HTTP 超时 5s = WDT 边界 | HTTP_TIMEOUT_MS=3000 |
| TWDT already init | IDF 已初始化 | 去掉重复 init |

### 8.3 HTTP 通信

| 问题 | 原因 | 解决 |
|------|------|------|
| perform 无法读 body | DNS/路由 | open/read/close 模式 |
| DNS 不解析 | 未配 DNS | 用 IP 直连 |
| send() timeout | 防火墙 | 关闭防火墙 |
| 图片上传损坏 | JPEG 截断 | Content-Type + 完整长度 |

---

## 9. 技术决策

| 决策 | 理由 |
|------|------|
| poll_service 独立 FreeRTOS 任务 | 不阻塞主任务, WDT 安全 |
| I2C CMD_SUSPEND/RESUME 复用 | 避免 OV2640 与 QMA6100P 冲突 |
| PSRAM 作为帧缓冲 | OV2640 JPEG 不耗尽 DRAM |
| Base64 data URI | 简单直接 |
| open/read/close 而非 perform | 稳定读取 response body |
| 前置清除旧图 | 防作弊核心 |
| precaptured_images 纯色 PNG | 无需 PIL |
| 随机选择预存图 | 结果不同便于验证 |

---

## 10. 测试场景

### 10.1 ESP32-CAM 真实拍照
**操作**: 点击拍照按钮
**观察**:
- ESP32 串口: Poll response + Captured JPEG: xxx bytes
- 前端显示彩色画面, 右上角绿色[实时拍摄 ESP32-CAM]标记

### 10.2 按键触发(红->绿)
**操作**: 按下 ESP32-S3-EYE 板载按键 GPIO 0
**观察**: LCD 从红色变为绿色

### 10.3 降级测试(无摄像头)
**前提**: ESP32 不可达或 pip uninstall opencv-python
**操作**: 点击拍照
**观察**: 显示预存图片 + 橙色标记

### 10.4 防作弊测试
**操作**: 拍照成功 -> 遮挡摄像头 -> 再次拍照
**观察**: 失败时旧图消失, 仅显示错误信息
