# Week 13: 连接目标端推理与联网服务 — 测试报告

> 项目：group01_esp32s3eye | EgoLink DevBench  
> 日期：2026-10-13  
> 分支：week13_edge_inference

---

## 一、测试环境

| 组件 | 详情 |
|------|------|
| 设备端 | ESP32-S3-EYE QMA6100P @ COM4 |
| 近端边缘 | Flask @ 10.1.41.43:5000 |
| 云端 | DeepSeek API（未配置 API Key） |
| 浏览器 | Chrome / Edge |

---

## 二、新增 API 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/capabilities` | GET | 返回能力注册表 + 运行位置清单 |
| `/api/local_infer` | POST | 本地规则推理（读 source_states 表） |
| `/api/infer` | POST | 云优先+本地回退统一入口 |
| `/api/offline_status` | GET | 当前离线状态查询 |

---

## 三、测试场景与结果

### 场景 1：断开外网后本地推理仍运行 ✅

**操作：**
1. 设置 `ENABLE_CLOUD_INFER=False`（或断外网）
2. 打开页面 → 📷 图像采集 → 点击 🔌 边缘推理

**预期结果：**
- 推理正常返回结果
- `source=local_near_edge`
- 界面显示 "近端边缘验证" 标签 + "目标设备验收待补"

**实际结果：** ✅ 通过

返回示例：
```json
{
    "success": true,
    "label": "环境正常",
    "score": 0.85,
    "status": "success",
    "source": "local_near_edge",
    "location_note": "近端边缘验证，目标设备验收待补"
}
```

前端显示：
- 🟢 状态行旁有蓝色 `近端边缘验证` 标签
- 🟡 下方有橙色 `目标设备验收待补` 小字
- 顶部横幅 `⚠️ 外网不可用：本地基础反馈仍可用`

---

### 场景 2：联网增强可用提示 ✅

**操作：**
1. 配置 API Key 后恢复外网
2. `ENABLE_CLOUD_INFER=True`
3. 点击 🔌 边缘推理

**预期结果：**
- 若在线模型可用 → `source=cloud`，显示 "云端推理" 标签
- 若不可用 → 回退本地，`source=local_near_edge`，提示回退信息

**实际结果（API Key 未配置）：** ✅ 通过

因为 `.env` 中 `DEEPSEEK_API_KEY` 为空，系统自动将 `OFMLINE_MODE=True`，推理回退到本地 `api_local_infer`。顶部横幅自动显示离线提示。

---

### 场景 3：仅电脑推理标注 ✅

**操作：**
- 点击 🔌 边缘推理

**预期结果：**
- 界面明确标注 "近端边缘验证，目标设备验收待补"
- 不会误以为这是 ESP32 端推理

**实际结果：** ✅ 通过

每次从 `api_local_infer` 返回的结果都带：
- `source: "local_near_edge"`
- `location_note: "近端边缘验证，目标设备验收待补"`
- 前端显示橙色 `目标设备验收待补` 标签
- 绝不冒充 ESP32 端推理

---

### 场景 4：能力表正确 ✅

**操作：**
打开 "🔌 运行位置与能力" Tab

**预期结果：**
显示两表：本地/联网能力表、运行位置清单

**实际结果：** ✅ 通过

#### 表一：本地/联网能力表

| 功能 | 运行位置 | 离线可用 | 当前状态 | 备注 |
|------|----------|----------|----------|------|
| 传感器采集 | 📟 设备端 | ✅ | 可用 | ESP32-S3-EYE QMA6100P @ COM4 |
| 视觉推理 | 🖥️ 近端边缘 | ✅ | 可用 | 近端边缘规则推理，目标设备验收待补 |
| NLP意图解析 | 🖥️ 近端边缘 | ✅ | 可用 | 本地规则引擎 |
| 语音播报 | 🖥️ 近端边缘 | ✅ | 可用 | Web Speech API |
| 云端大模型推理 | ☁️ 云端 | ❌ | 回退 | 需外网，未配置时回退本地 |

#### 表二：运行位置清单

| 层级 | 节点 | 详情 |
|------|------|------|
| 📟 设备端 | ESP32-S3-EYE @ COM4 | 运行中 |
| 🖥️ 近端边缘 | Flask @ 10.1.41.43:5000 | 运行中 |
| ☁️ 云端 | 不可用 | 不可用 |

---

### 场景 5：离线横幅自动切换 ✅

**操作：**
- 断网 → 观察顶部横幅
- 联网 → 观察横幅消失

**实际结果：** ✅ 通过

- 外网不可用时 → 顶部出现橙色横幅 `⚠️ 外网不可用：本地基础反馈仍可用`
- 外网恢复时 → 横幅自动消失（15秒轮询检测）
- 横幅不会遮挡主要功能

---

## 四、代码变更总结

### app.py 新增（约130行，附在 `if __name__` 前）

```
+ import math, requests
+ OFFLINE_MODE / ENABLE_CLOUD_INFER
+ check_offline_status()
+ capabilities 字典
+ /api/capabilities
+ /api/local_infer
+ /api/infer
+ /api/offline_status
```

### index.html 新增

```
+ CSS: .offline-banner, .capabilities-container, .cap-table, .source-tag
+ HTML: 🔌 运行位置与能力 Tab (按钮 + 页面)
+ HTML: 离线横幅 <div>
+ HTML: 🔌 边缘推理按钮
+ JS:  runEdgeInference()
+ JS:  loadCapabilities()
+ JS:  checkOfflineStatus()
+ JS:  runInference() 增强（source 标签展示）
```

### 未修改文件

- ✅ main.c / esp32_firmware — 零改动
- ✅ COM4 操作 — 零改动
- ✅ 多源状态 / NLP / 视觉推理 / 上下文引擎 / 偏好系统 — 零改动

---

## 五、启动命令

```bash
cd "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week13_edge_inference\server"
python app.py
```

浏览器打开：`http://10.1.41.43:5000`

---

## 六、备注

- 云端推理需要配置有效的 `DEEPSEEK_API_KEY` 才能走 cloud 路径
- 若设置 `ENABLE_CLOUD_INFER=False`，直接使用本地规则推理
- 所有推理结果标注真实来源，绝不伪造设备端推理