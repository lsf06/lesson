# ESP32-S3-EYE QMA6100P 加速度传感器仪表盘

> 基于 ESP32-S3-EYE + QMA6100P 三轴加速度计 + Flask Web 服务器的实时传感器数据采集与可视化系统。

---

## 📁 项目结构（按周次）

| 文件夹 | 周次 | 功能 | 采集模式 |
|--------|------|------|----------|
| `week1_periodic_upload/` | 第一周 | 5Hz 周期上报，连续曲线 | ESP32 每 200ms 自动采集并上传 |
| `week2_request_collection/` | 第二周 | 按需采集，带 request_id 闭环，状态流转 | Web 端点击 "REQUEST CAPTURE" 按钮触发单次采集 |

> ⚠️ **编译烧录需 `cd` 到对应周次的 `esp32_firmware` 文件夹下进行。**

---

## 🔧 硬件要求

| 硬件 | 说明 |
|------|------|
| **ESP32-S3-EYE** 开发板 | 板载 QMA6100P 三轴加速度计 |
| USB-C 数据线 | 供电 + 烧录 |
| 电脑 | 运行 Flask 服务器（与 ESP32 同一 Wi-Fi 网络） |

## 📦 软件环境

### 服务器端
- Python 3.8+
- Flask（见各周 `server/requirements.txt`）

### ESP32 端
- ESP-IDF v5.2+（https://docs.espressif.com/projects/esp-idf/）
- 组件依赖（`idf.py build` 自动拉取）：
  - `espressif/qma6100p`
  - `espressif/esp32_s3_eye`

---

## 🚀 部署步骤

### 一、启动服务器

```bash
# 第一周：5Hz 周期上报
cd week1_periodic_upload/server
pip install -r requirements.txt
python app.py

# 第二周：按需采集
cd week2_request_collection/server
pip install -r requirements.txt
python app.py
```

服务启动后访问仪表盘：http://<你的IP>:5000

### 二、配置并烧录 ESP32

1. **修改 Wi-Fi 和服务器地址**

   编辑对应周次 `esp32_firmware/main/main.c`，修改以下宏：

   ```c
   #define WIFI_SSID       "你的WiFi名"
   #define WIFI_PASSWORD   "你的WiFi密码"
   #define SERVER_URL      "http://<服务器IP>:5000/api/upload"
   ```

2. **编译烧录**

   ```bash
   # ⚠️ 必须 cd 到对应周次的 esp32_firmware 目录
   cd week1_periodic_upload/esp32_firmware    # 或 week2_request_collection/esp32_firmware
   idf.py set-target esp32s3
   idf.py build
   idf.py -p <COM口> flash monitor
   ```

---

## 🖥️ 仪表盘功能

| 功能 | 说明 |
|------|------|
| **波形示波器** | ECharts 滚动静默波形，三轴 AX(红)/AY(绿)/AZ(蓝) 分别显示 |
| **数值卡片** | AX/AY/AZ 实时数值（大号字体），变化时闪烁边框动画 |
| **3D 姿态立方体** | 纯 CSS 3D 旋转，Pitch/Roll 角度显示，加速度方向映射空间朝向 |
| **连接状态** | 在线/离线/数据停滞检测，速率 Hz 显示，总记录数统计 |
| **REQUEST CAPTURE** | （仅第二周）点击按钮触发单次传感器采集，带 request_id 和状态流转 |

---

## 📁 目录结构

```
lesson-main/
├── week1_periodic_upload/              # 第一周：5Hz 周期上报
│   ├── server/                         # Flask 后端
│   │   ├── app.py                      # 主程序（SQLite + REST API）
│   │   ├── requirements.txt            # Python 依赖
│   │   ├── static/
│   │   │   └── echarts.min.js          # ECharts 离线库
│   │   └── templates/
│   │       └── index.html              # 仪表盘前端
│   └── esp32_firmware/                 # ESP32 固件源码
│       ├── CMakeLists.txt
│       ├── sdkconfig
│       ├── dependencies.lock
│       └── main/
│           ├── CMakeLists.txt
│           ├── idf_component.yml
│           └── main.c                  # 5Hz 周期采集 + HTTP 上传
│
├── week2_request_collection/           # 第二周：按需采集
│   ├── server/                         # Flask 后端
│   │   ├── app.py                      # 主程序（含 collection_requests 状态流转）
│   │   ├── requirements.txt
│   │   ├── static/
│   │   │   └── echarts.min.js
│   │   └── templates/
│   │       └── index.html              # 仪表盘（含 REQUEST CAPTURE 按钮）
│   ├── esp32_firmware/                 # ESP32 固件源码
│   │   ├── CMakeLists.txt
│   │   ├── sdkconfig
│   │   ├── dependencies.lock
│   │   └── main/
│   │       ├── CMakeLists.txt
│   │       ├── idf_component.yml
│   │       └── main.c                  # 轮询采集 + request_id 闭环
│   └── tools/                          # 辅助开发工具脚本
│       ├── _trigger.py                 # 触发单次采集的测试脚本
│       ├── build_esp32.bat             # 编译脚本
│       ├── flash_esp32.bat             # 烧录脚本
│       ├── start_flask.bat             # 启动 Flask 服务器
│       └── ...（更多工具脚本）
│
├── 2/                                  # 其他项目（不上传）
├── wei/                                # 其他项目（不上传）
├── .gitignore
└── README.md
```

---

## 🛠️ 辅助工具脚本说明

`week2_request_collection/tools/` 目录下提供了一些开发调试用的辅助脚本。

> ⚠️ **重要提醒**：部分脚本（`build_esp32.ps1`、`finalize.py`、`flash_py.py`、`flash_verify.py`、`_trigger.py`、`_tail.py`）中包含硬编码的本地绝对路径（如 `d:\lesson\...` 和 ESP-IDF 工具链路径）。**使用前请修改脚本中的路径为你本机的实际路径。**

---

## 📄 API 接口（第二周）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/latest` | 获取最新一条数据 |
| `GET` | `/api/history?count=100` | 获取最近 N 条历史数据 |
| `GET` | `/api/count` | 获取总记录数 |
| `POST` | `/api/upload` | ESP32 上传数据 |
| `GET` | `/api/pending_request?device_id=...` | ESP32 轮询待处理请求 |
| `POST` | `/api/request_capture` | （Web 端）发起一次采集请求 |
| `GET` | `/api/request_status?request_id=...` | 查询请求状态 |
| `POST` | `/api/complete` | ESP32 完成采集后上报结果 |

### 状态流转（第二周）

```
PENDING → RECEIVED → COMPLETED
                  ↘ TIMEOUT (5s超时)
```

---

## ⚙️ 配置说明

| 参数 | 位置 | 说明 |
|------|------|------|
| Wi-Fi 账号密码 | `main.c` | 改为你的 Wi-Fi |
| 服务器地址 | `main.c` | 改为服务器 IP |
| 设备 ID | `main.c` | 自定义设备标识 |
| 采样间隔（第一周） | `main.c` `UPLOAD_INTERVAL_MS` | 默认 200ms（5Hz） |
| 轮询间隔（第二周） | `main.c` `POLL_INTERVAL_MS` | 默认 1000ms |
| 服务器端口 | `app.py` | 默认 5000 |
| 波形点数 | `index.html` `MAX_POINTS` | 默认 200 |