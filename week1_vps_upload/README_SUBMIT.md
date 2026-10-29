# Week 1: 数据上云 —— 近端边缘 Flask → 公网 VPS

> 本目录由 `week13_14_15_edge_inference` 复制而来，固化固件侧（零改动），在其基础上新增 VPS 云端转发。  
> 日期：2026-10-29 | 分支：week1_vps_upload | 设备：group01_esp32s3eye @ COM4

> 说明：下面的「一～六」为继承自第 13 周的原始测试报告，本文件在「零」节补充第 1 周新增的数据上云能力。

---

## Week 13: 连接目标端推理与联网服务 — 测试报告

> 项目：group01_esp32s3eye | EgoLink DevBench  
> 日期：2026-10-13  
> 分支：week13_edge_inference

---

## 零、第1周新增：数据上云（近端 Flask → 公网 VPS）

### 0.1 目标与边界

- **固件零改动**：`esp32_firmware/`、`main.c`、COM4 全部未动，`HTTP_TIMEOUT_MS = 3000` 保持原值
- 近端 Flask 在数据**成功落库后**，把同一条数据转发到公网 VPS
- 新增 `☁️ VPS 云端记录` Tab，可直接查看云端已收到的数据

### 0.2 变更文件

| 文件 | 变更 |
|------|------|
| `server/app.py` | +约 180 行：VPS 客户端（登录 / token 缓存 / 401 重登 / 异步转发）+ 2 个新路由 |
| `server/templates/index.html` | 顶部 VPS 连接横幅 + `☁️ VPS 云端记录` Tab（表格 / 10s 轮询 / 手动刷新） |
| `server/.env` | 本地凭据，**已被 .gitignore 忽略，不提交** |
| `server/.env.example` | 新增并提交，仅含占位符，复制为 `.env` 后填真实凭据 |
| `esp32_firmware/**`、`main.c`、COM4 | ❌ 零改动 |

### 0.3 关键设计：为什么转发必须异步

设备端 `HTTP_TIMEOUT_MS = 3000`（WDT 5s），而一次 VPS 请求包含 TLS 握手 + 可能的登录，公网耗时不可控。
若同步转发，任何一次 >3s 的等待都会让设备判定上传失败 —— 等于用固件改动去补一个服务端问题。

因此转发放在 `threading.Thread(daemon=True)` 中执行，`/api/upload` 立即返回，设备端始终在 3s 内拿到 200。
需要课堂演示"阻塞对比"时把 `VPS_ASYNC=0` 即可切同步。

### 0.4 VPS 客户端行为

| 行为 | 说明 |
|------|------|
| 登录 | `POST {VPS_BASE_URL}/api/login`，JSON `{"username","password"}` |
| Token 缓存 | 默认 30 天（若响应含 `expires_in/ttl` 则以它为准），提前 60s 视为过期 |
| 认证 | `Authorization: Bearer <token>` |
| 证书 | VPS 为自签证书 → `verify=False` + 关闭 `InsecureRequestWarning` |
| 401 处理 | 强制重登一次并重试同一请求；仍失败则只记录错误，不抛异常 |
| 失败退避 | 登录失败后 30s 内不再重试（`VPS_LOGIN_BACKOFF`），避免 401 刷成请求风暴 |
| 限速 | 本地 60s 滑动窗口 ≤ 280 条（平台限制 300 条/分钟） |
| 转发时机 | 仅在 `INSERT` + `commit()` 成功后；`duplicate`（幂等丢弃）与 `EXPIRED` 两个提前返回分支**不转发** |
| 日志 | `[VPS] 登录成功 token=abc123...wxyz`（打码）、`[VPS] 上传成功 200 ...`、`[VPS] 上传失败 status=...`、`[VPS] token 已失效(401)，重新登录后重试一次` |

### 0.5 新增 API 路由

| 路由 | 方法 | 说明 | 返回要点 |
|------|------|------|----------|
| `/api/vps_status` | GET | VPS 连接状态（10s 缓存） | `configured / connected / base_url / device_id / channel / sent / failed / last_error / token_masked` |
| `/api/vps_history` | GET | 代理 VPS 的 `GET /api/data?limit=N`，N 限 1~200 | `{success, source:"vps", base_url, count, records, fetched_at}`；失败返回 502 + `error` |

### 0.6 前端

- **顶部横幅**：`☁️ 已连接 VPS: 123.58.43.162:8443`（绿）／`⚠️ VPS 未连接: ...`（红，附原因），15s 刷新
- **新 Tab `☁️ VPS 云端记录`**：列 `# / 时间戳 / 设备 / AX / AY / AZ / 通道`，10s 轮询 + `🔄 刷新`
- 字段名做了兼容映射（`timestamp|time|created_at|server_time|device_time`、`ax|acc_x|x` 等），因为尚未拿到 VPS 真实返回样本

### 0.7 联调结果（2026-10-29 本地实测）

| 检查项 | 结果 |
|--------|------|
| `python -m py_compile app.py` | ✅ 通过 |
| `GET /` | ✅ 200，页面已含横幅 / Tab / JS |
| `GET /api/vps_status` | ✅ 200，`configured=true`、`connected=false`，`last_error="login 401 账号或口令错误"` |
| `POST /api/upload`（模拟设备报文） | ✅ 200 `status=ok`，日志同时出现 `[VPS] 上传失败：VPS 不可达或登录失败 channel=sensor1`（证明异步且不影响设备响应） |
| `GET /api/vps_history` | ✅ 502 + JSON 错误（凭据 401 期间符合预期） |
| **VPS 真实上传** | ⚠️ 阻塞：`POST /api/login` 返回 `401 {"error":"账号或口令错误"}`，待老师确认账号/口令 |

> 一旦拿到正确口令：只需修改 `server/.env` 的 `VPS_USERNAME` / `VPS_PASSWORD` 并重启 Flask，**无需改动任何代码**。
> 届时日志应出现 `[VPS] 登录成功 token=***` 与 `[VPS] 上传成功 200 ...`，`☁️ VPS 云端记录` Tab 即可看到云端数据。

### 0.8 启动

```bash
cd "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week1_vps_upload\server"
copy .env.example .env    # 首次运行，然后填入真实账号 / 口令
python app.py
```

浏览器打开：`http://10.1.41.43:5000`

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
cd "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week1_vps_upload\server"
python app.py
```

浏览器打开：`http://10.1.41.43:5000`

---

## 六、备注

- 云端推理需要配置有效的 `DEEPSEEK_API_KEY` 才能走 cloud 路径
- 若设置 `ENABLE_CLOUD_INFER=False`，直接使用本地规则推理
- 所有推理结果标注真实来源，绝不伪造设备端推理