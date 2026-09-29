# ESP32-S3-EYE QMA6100P 加速度传感器仪表盘

> 基于 ESP32-S3-EYE + QMA6100P 三轴加速度计 + Flask Web 服务器的实时传感器数据采集与可视化系统。

## 📡 项目架构

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

## 🔧 硬件要求

| 硬件 | 说明 |
|------|------|
| **ESP32-S3-EYE** 开发板 | 板载 QMA6100P 三轴加速度计 |
| USB-C 数据线 | 供电 + 烧录 |
| 电脑 | 运行 Flask 服务器（与 ESP32 同一 Wi-Fi 网络） |

## 📦 软件环境

### 服务器端
- Python 3.8+
- Flask（见 `server/requirements.txt`）

### ESP32 端
- ESP-IDF v5.2+（https://docs.espressif.com/projects/esp-idf/）
- 组件依赖（`idf.py build` 自动拉取）：
  - `espressif/qma6100p`
  - `espressif/esp32_s3_eye`

---

## 🚀 部署步骤

### 一、启动服务器

```bash
cd server
pip install -r requirements.txt
python app.py
```

服务启动后：
- 仪表盘：http://<你的IP>:5000
- API 端点：`/api/upload`（POST）、`/api/latest`、`/api/history`、`/api/count`

### 二、配置并烧录 ESP32

1. **修改 Wi-Fi 和服务器地址**

   编辑 `esp32_firmware/main/main.c`，修改以下宏：

   ```c
   #define WIFI_SSID       "你的WiFi名"
   #define WIFI_PASSWORD   "你的WiFi密码"
   #define SERVER_URL      "http://<服务器IP>:5000/api/upload"
   ```

2. **编译烧录**

   ```bash
   cd esp32_firmware
   idf.py set-target esp32s3
   idf.py build
   idf.py -p <COM口> flash monitor
   ```

3. **验证**

   串口输出 `UPLOAD: -0.41, -1.03, 0.32 @ 2026-09-19 12:52:07` 表示正常运行。

---

## 🖥️ 仪表盘功能

| 功能 | 说明 |
|------|------|
| **波形示波器** | 左侧 ECharts 滚动静默波形，三轴 AX(红)/AY(绿)/AZ(蓝) 分别显示 |
| **数值卡片** | AX/AY/AZ 实时数值（大号字体），变化时闪烁边框动画 |
| **3D 姿态立方体** | 纯 CSS 3D 旋转，Pitch/Roll 角度显示，加速度方向映射空间朝向 |
| **连接状态** | 在线/离线/数据停滞检测，速率 Hz 显示，总记录数统计 |
| **离线运行** | 所有静态资源本地化（echarts.min.js），无需互联网连接 |

---

## 📁 目录结构

```
1/
├── server/                        # Flask 后端
│   ├── app.py                     # 主程序（SQLite + REST API）
│   ├── requirements.txt           # Python 依赖
│   ├── static/
│   │   └── echarts.min.js         # ECharts 离线库
│   └── templates/
│       └── index.html             # 仪表盘前端
├── esp32_firmware/                # ESP32 固件源码
│   ├── CMakeLists.txt             # 项目构建文件
│   ├── sdkconfig                  # ESP32-S3 配置
│   ├── dependencies.lock          # 组件版本锁定
│   └── main/
│       ├── CMakeLists.txt
│       ├── idf_component.yml      # 组件依赖声明
│       └── main.c                 # 传感器采集 + HTTP 上传
├── .gitignore
└── README.md
```

## 📄 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/latest` | 获取最新一条数据 |
| `GET` | `/api/history?count=100` | 获取最近 N 条历史数据 |
| `GET` | `/api/count` | 获取总记录数 |
| `POST` | `/api/upload` | ESP32 上传数据 `{"device_id":"...","ax":...,"ay":...,"az":...,"device_time":"..."}` |

---

## ⚙️ 配置说明

| 参数 | 位置 | 说明 |
|------|------|------|
| Wi-Fi 账号密码 | `main.c` 第25-26行 | 改为你的 Wi-Fi |
| 服务器地址 | `main.c` 第27行 | 改为服务器 IP |
| 设备 ID | `main.c` 第28行 | 自定义设备标识 |
| 采样间隔 | `main.c` 第190行 | 默认 1000ms |
| 服务器端口 | `app.py` 第136行 | 默认 5000 |
| 波形点数 | `index.html` `MAX_POINTS` | 默认 200 |
| 刷新频率 | `index.html` `REFRESH_MS` | 默认 200ms |