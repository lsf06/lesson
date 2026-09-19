# ESP32-S3-EYE IMU+Camera → Flask Server 照片上传系统

## 项目概述

基于 ESP32-S3-EYE 开发板，实现 IMU 传感器数据实时上传 + 远程控制拍照上传 JPEG 照片到 Flask 服务器的完整系统。

## 功能特性

- **IMU 数据流**：QMA6100P 加速度计数据实时上传（2秒间隔）
- **远程拍照**：通过 Web 前端发送 capture 命令，ESP32 拍照并上传 JPEG
- **竞争条件修复**：拍照期间暂停 IMU 上传，避免 req_id 冲突导致"假成功"
- **前端验证**：轮询 `/api/photos/count` 确认照片真正到达服务器

## 项目结构

```
2/
├── qma6100_wifi_upload/        # ESP32 固件 (ESP-IDF v5.4.4)
│   ├── main/
│   │   ├── main.c              # 主程序（IMU+Camera+WiFi）
│   │   ├── CMakeLists.txt
│   │   └── idf_component.yml
│   ├── CMakeLists.txt
│   └── sdkconfig               # ESP-IDF 配置
├── server/                     # Flask 服务器
│   ├── app.py                  # Flask 应用
│   ├── templates/
│   │   └── index.html          # Web 前端
│   ├── static/
│   │   └── echarts.min.js      # ECharts 图表库
│   └── requirements.txt        # Python 依赖
├── test_e2e.py                 # 端到端测试脚本
├── read_serial.py              # 串口读取工具
└── README.md
```

## 环境要求

### 硬件
- ESP32-S3-EYE 开发板（OV2640 摄像头 + QMA6100P IMU）
- USB 数据线

### 软件
- ESP-IDF v5.4.4
- Python 3.10+
- Flask

## 快速开始

### 1. 编译 & 烧录固件

```bash
cd qma6100_wifi_upload
idf.py build
idf.py -p COM5 flash monitor
```

### 2. 启动 Flask 服务器

```bash
cd server
pip install -r requirements.txt
python app.py
```

### 3. 访问 Web 界面

浏览器打开 `http://localhost:5000`，点击"拍照"按钮发送 capture 命令。

### 4. 运行端到端测试

```bash
python test_e2e.py
```

## 关键技术点

- **OV2640 摄像头**：使用 VGA (640×480) 分辨率，DVP 驱动不支持 QVGA
- **JPEG 编码**：OV2640 内置 JPEG 编码器，无需 ESP32-S3 硬件 JPEG（/dev/video10 不可用）
- **V4L2 接口**：通过 `/dev/video2` 访问摄像头，使用 mmap 方式获取帧数据
- **竞争条件**：拍照时使用 `pending_req_id` 标记，期间跳过 IMU 上传防止前端误判
- **SPIRAM**：需启用 PSRAM 支持以满足 VGA 帧缓冲需求