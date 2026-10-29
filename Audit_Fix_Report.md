# 证据造假 / 夸大 审计与修复报告

> 审计对象：`d:\lesson\xiaolin\lesson-main (1)\lesson-main`
> 执行日期：2026-10-29
> 判定口径：只看三类证据 —— **代码、接口实测输出、数据库原始字段**。口头描述、设计文档、单张截图不算证据。
> 本报告只写两件事：(1) 已在代码或接口上验证过的；(2) 明确标注「补不上」的。

---

## 摘要

| # | 问题（修前状态） | 定性 | 处置 | 结论 |
|---|---|---|---|---|
| 1 | 30s 内的旧图被当作「本次实时拍摄」，前端打绿色「📷 实时拍摄（ESP32-CAM）」 | **造假** | 后端改为 `success:false / source:recent_cache / captured_at / age_seconds`，前端加红条 + 橙徽章；8 个同源拷贝全部修 | 已修复 + 已实测 |
| 2 | week8 无 README；视觉推理 `MOCK-V1` 未在任何交付文档里声明 | **夸大（未声明）** | 新建 `week8_vision_feedback/README.md` 证据等级表；`README_SUBMIT.md` 顶部加声明 | 已补证 |
| 3 | 补传徽章上游字段缺失：`/api/history`、`/api/sensor_history` 都不返回 `delivery_status` | **链路断（无法举证）** | 两接口补齐 4 个字段；新增 `data_origin` 迁移；前端加「来源」列 | 已修复 + 已实测 |
| 4 | week17 声称「已迁移至心率场景」，目录内无任何实现代码 | **夸大** | README 重写为「设计级 + 未接 MAX30102」；新增可运行仿真脚本并附实跑输出 | 已补证（仿真，非实物） |
| 5 | week18 称「全系统未部署 VPS」「无 git tag」，与 week1 实测 201 自相矛盾 | **过时 / 自相矛盾** | 改为「数据面已通、Web 仍本机」；补打本地 tag | 已修复 |
| 6 | 真实模型推理、GNSS、板载麦克风、第16周 n=2 录屏、真实断网补传 | **外部条件缺失** | 不补，逐条写清边界 | 补不上 |

---

## 一、Week7：缓存图冒充实时拍摄（最严重）

### 1.1 改前（假证据）

`week7_image_capture/server/app.py:871-882`：

```python
if os.path.isfile(latest_path):
    age = time.time() - os.path.getmtime(latest_path)
    if age < 30:
        ...
        log.info(''Capture: returning recent ESP32 image (age=%.1fs)', age)
        return jsonify({
            ''success': True,
            ''image': ...,
            ''source': ''esp32_camera''
        })
```

前端 `templates/index.html:706-707`（改前）：`isEsp32` 为真就打绿色徽章「✅ 摄像头实时拍摄」。

**为什么算造假**：图片是磁盘上最多 30 秒前的旧文件，接口却回报 `source=esp32_camera`，前端据此宣称「实时拍摄」，且不显示拍摄时间 —— 用户无法分辨这是本次采集还是上一轮遗留。

### 1.2 改后

后端 `app.py:871-890`：

```python
mtime = os.path.getmtime(latest_path)
captured_at = time.strftime(''%Y-%m-%d %H:%M:%S'', time.localtime(mtime))
log.warning(''Capture: recent cached image (age=%.1fs), NOT live'', age)
return jsonify({
    ''success': False,
    ''error': ...等待新图超时...,
    ''source': ''recent_cache'',
    ''captured_at'': captured_at,
    ''age_seconds'': round(age, 1),
    ''image'': ...
})
```

前端 `templates/index.html:690` 起新增 `recent_cache` 分支：叠加红条「⚠️ 非本次采集：这是 <拍摄时间> 的缓存图片（Ns 前）」，徽章降级为橙色「⚠️ 历史缓存」；样式 `:133`。

### 1.3 实测输出（2026-10-29 12:08，5000 端口）

```
POST /api/capture_image -> {"age_seconds": 0.0, "captured_at": "2026-10-29 12:08:26",
  "error": "等待新图超时，当前仅有 0.0s 前的缓存图",
  "image": "base64:5279 chars", "source": "recent_cache", "success": false}
GET / len=53724 cache-warning=True recent_cache=True
```

### 1.4 同一段代码的 8 份拷贝

| 周目录 | 后端 app.py | 前端 index.html |
|---|---|---|
| week1_vps_upload | 已修 | 已修 |
| week7_image_capture | 已修 | 已修 |
| week8_vision_feedback | 已修 | 已修 |
| week9_proactive_inquiry | 已修 | 已修 |
| week10_multi_source_state | 已修 | 已修 |
| week11_context_engine | 已修 | 已修 |
| week12_feedback_preferences | 已修 | 已修 |
| week13_14_15_edge_inference | 已修 | 已修 |

前端合计 `+160 -0`，后端合计 8 个文件 `+83 -33`（其中 week7 为 `+13 -5`），均无整文件重写（diff 行数即可核对）。

### 1.5 没有动的部分

`git diff -- '*.c'` → `diff_chars=0`。固件一行未改，拍照链路本身未被破坏。

---

## 二、Week8 / Week13_14_15：视觉推理是 Mock，却没有一句声明

### 2.1 改前

- `week8_vision_feedback/` **没有 README.md**（整个目录只有 server / firmware / 素材）。
- `week13_14_15_edge_inference/README_SUBMIT.md` 把 `/api/infer_image` 当普通能力列在「新增 API 路由」表里，全文没有 mock 字样；
  而 `server/app.py:948` 写死 `ENABLE_MOCK_VISION = True`，`_mock_infer()` 用 `random.choice()` 造标签，`model_version` 硬编码 `MOCK-V1`。
- `README_SUBMIT.md:175` 称「main.c / esp32_firmware — 零改动」，实际 `week13_14_15_edge_inference/esp32_firmware/main/main.c:407` 有新增的 `device_infer_accel()`（调用点 `:419`、`:1199`）。
- `README_SUBMIT.md:184` 启动路径写成 `...\week13_edge_inference\server`（目录不存在）。

### 2.2 改后

- 新建 `week8_vision_feedback/README.md`（122 行），第 0 节即「证据等级声明」表格：

| 项 | 事实 | 位置 |
|---|---|---|
| 推理开关 | `ENABLE_MOCK_VISION = True`（补丁后行号 `:954`） | `server/app.py:954` |
| 结果来源 | `random.choice(VISION_LABELS)`，30% 低分演示 uncertain | `:956-979` |
| 版本标注 | `model_version = MOCK-V1` | `:979` |
| 模型权重 | 无（仓库无 .onnx/.tflite/.pt） | — |
| 端侧部署 | 无 | — |

- `README_SUBMIT.md` 顶部加 4 行声明（含「云端 DeepSeek 未配置 Key，云路径实际未跑通」）。
- `:175` 改为：main.c **并非零改动**，`device_infer_accel()` 是 if/else 阈值判定、**不含模型推理**；本次修复对 main.c 改动 0 字节。
- `:184` 路径更正为 `week13_14_15_edge_inference\server`。

---

## 三、Week14：补传徽章「看得见但举不了证」

### 3.1 根因链（改前）

1. 徽章只读 `GET /api/source_states` 的 `transmission_status`；
2. 该字段只在 `POST /api/upload` 的瞬间由 `update_source_state(...)` 写入（`app.py:445-456`）；
3. 而 `GET /api/history`（`:495-500`）与 `GET /api/sensor_history`（`:1034-1039`）**都不返回 `delivery_status`**。

→ 结果：只要错过上传那一秒，页面上再也看不到「📦 补传」，任何事后复核都无从举证。

### 3.2 改后（字段 + 迁移 + 前端列）

| 位置 | 改动 |
|---|---|
| `app.py:113-116` | 迁移列表加 `('data_origin', TEXT DEFAULT 'device')` |
| `app.py:414-416` | 上传时判定来源：`data_origin in (device, simulated)`，兼容 `simulated:true` |
| `app.py:421` | INSERT 增加 `data_origin` 列（旧库缺列时仍走原 fallback） |
| `app.py:503` | `/api/history` SELECT 增加 `original_ts, retransmit_ts, delivery_status, data_origin` |
| `app.py:520` | 同上，dict 回吐 |
| `app.py:1047` / `:1065` | `/api/sensor_history` 同上 |
| `index.html:491` | 表头加「来源」列 |
| `index.html:1052-1054` | 行内渲染 🧪 注入样例 / 📡 真实设备 / 📦 补传 |

### 3.3 状态注入工具（新增）

`week13_14_15_edge_inference/tools/backfill_fixture.py`：走**真实** `POST /api/upload`，把 `original_ts` 设为 45s 前、
`retransmit_ts` 设为当前，让服务端按 `app.py:356-367` 自行判 `recovered`；再 `GET /api/history` 回读断言。
文件头已写明：**这是状态注入，不是实物断网**。

### 3.4 实测（2026-10-29 12:17）

```
[POST] /api/upload status=200 original_ts=1793247382 retransmit_ts=1793247427 -> {"server_time": "2026-10-29 12:17:07", "status": "ok"}
...（共 3 条）
=== /api/history 回吐（仅本次注入行）===
original_ts | retransmit_ts | delivery_status | data_origin
 1793247382 |    1793247427 |       recovered | simulated
 1793247381 |    1793247427 |       recovered | simulated
 1793247380 |    1793247427 |       recovered | simulated
PASS: 3 行均为 delivery_status=recovered + data_origin=simulated
```

`curl "http://127.0.0.1:5000/api/history?count=5"`（截取 5 条中的 3 条注入行 + 2 条老数据）：

```
{"device_time": "2026-10-29 12:16:22", "original_ts": 1793247382, "retransmit_ts": 1793247427, "delivery_status": "recovered", "data_origin": "simulated"}
{"device_time": "2026-10-21 19:29:20", "original_ts": 0, "retransmit_ts": 0, "delivery_status": "live", "data_origin": "device"}
```

`curl http://127.0.0.1:5000/` → `page_len=99063`，`has_来源=True has_注入样例=True has_cache-warning=True`。

> 边界：这证明的是「接口契约 + 服务端判定 + 落库 + 回吐 + 前端列」整条链通了；
> **不证明**设备在真实断网时缓存并补传。

---

## 四、Week17：声称「已迁移」，实际零实现

### 4.1 改前

`week17_migration_and_fix/README.md:11-14` 用将来时写迁移（「将替换为 MAX30102」），但目录中**没有任何 .py**，
也没有心率相关代码；`heart_rate_simulator.py` 在被审计时根本不存在。等于用一段设计文字冒充「迁移完成」。

### 4.2 改后

1. README 重写（114 行），开头即「本目录不是一个已完成迁移的心率系统」，第 0 节证据表把四件事分别定性：
   UI 改进=已落地代码；迁移=设计+仿真；MAX30102 驱动=不存在；真实断网补传=未验证。
2. 新增 `heart_rate_simulator.py`（纯标准库），复刻：
   - `main.c:92` `CACHE_QUEUE_SIZE=20`、`:377-388` `cache_enqueue()` 丢最旧 + `QUEUE FULL, dropped oldest record`；
   - `app.py:356-367` 的 `delay>30s → recovered` 判定。
3. 实跑结果（`python week17_migration_and_fix/heart_rate_simulator.py`）：

```
  6 |     72 |    09:00:06 |      09:00:44 |    38.0 | recovered
  7 |     75 |    09:00:07 |      09:00:44 |    37.0 | recovered
  8 |     78 |    09:00:08 |      09:00:44 |    36.0 | recovered
[WARN] QUEUE FULL, dropped oldest record: seq=11 hr=62
[INFO] flush -> 20 条补传记录，丢弃 5 条最旧记录
ALL ASSERTIONS PASSED (live=5, recovered=23, dropped=5)
```

> 边界：仿真通过的只是队列容量、丢最旧策略、双时间戳与状态判定；**心率数值是构造的**，与真实脉搏无关。

---

## 五、Week18：把「已做到的」写成「没做到」，把「没做的」写成「已做」

### 5.1 改前

| 行 | 原文 | 问题 |
|---|---|---|
| `:16` | 全系统**未部署到 VPS**，无公网域名、无 TLS | 与 `week1_vps_upload/README_SUBMIT.md` 0.7 节矛盾（该节记录 `POST /api/data` 返回 201、`id=10`） |
| `:76` | 第1周 **未部署 VPS**，只有局域网地址 | 同上 |
| `:89` | **VPS 未部署** … 只能在局域网内联调 | 同上 |
| `:79` / `:103` | 无 git tag、`git tag` 为空 | 修复后已打 tag，需同步 |
| `:101` | 补传 UI 标签未验证 | 已有注入验证手段，应写清「注入过、实物未过」 |

### 5.2 本次取证

```
GET /api/vps_history -> HTTP 401 in 0.026317s
{"error": "缺少或无效的 Authorization: Bearer <token>"}
```

→ VPS `https://123.58.43.162:8443` **在线且要求鉴权**（26ms 响应）。
仓库内**没有 `.env`**，本次无法重新登录复验，因此不声称「我又跑通了一次」；
鉴权后的 201 / `id=10` 只能引用 `week1_vps_upload/README_SUBMIT.md` 0.7 节的原记录。

### 5.3 改后

- `:16` → 「数据面已上 VPS（201/id=10 有记录；今日 401 探活在线）；**Web 控制台仍只跑本机局域网**，无自有域名、无生产级 TLS、无 gunicorn/nginx/systemd」。
- `:76` → 第1周「数据面已通，Web 未上公网」。
- `:89` → 「**VPS 仅覆盖数据面**」，仍不能宣称 Web 公网可用。
- `:79` / `:103` → 已补打本地 tag `v1.0-final`（不 push），此项销账。
- `:101` → 改为「注入验证已过、实物复测仍缺」。

---

## 六、补不上的（外部条件，不粉饰）

| 事项 | 为什么补不上 | 现在的诚实写法 |
|---|---|---|
| 真实视觉模型推理 | 无权重、无 NPU 部署、教师基线未接入 | 全链路标注 `MOCK-V1`，见 week8 README 第 0 节 |
| 真实云端语言模型 | `DEEPSEEK_API_KEY` 为空，一次都没跑 | `README_SUBMIT.md` 顶部声明「云路径未跑通」 |
| 端侧模型推理 | `device_infer_accel()` 只是 if/else 阈值 | 明确写「非模型」，不写「端侧 AI 推理」 |
| GNSS 定位 | 无硬件 | 沿用「回放数据-仅供演示（无真实GNSS硬件）」标注 |
| 板载麦克风 | 音频链路未打通 | 只写浏览器 Web Speech API |
| 第16周 n=2 录屏 / 埋点 | 当时未录，事后无法补拍 | week17 README 写「n=2 只能定位问题，不构成统计显著」 |
| 真实设备断网补传 | 需实物拔网 + 串口日志，本机无设备 | 只提供 `recovered` **状态注入**证据，并标注「非实物」 |
| 真实拍照（ESP32-CAM） | 板子不在手边 | 缓存分支已改为 `recent_cache`，不再冒充实时 |

---

## 七、验证清单（可逐条复跑）

| 检查 | 命令 | 结果 |
|---|---|---|
| Python 语法（8 个后端 + 2 个新脚本） | `python -m py_compile ...` | `exit=0` |
| 前端 JS 语法（8 个模板） | `node --check` 提取的 script 块 | `node_check_failures=0` |
| 缓存分支不再冒充实时 | `POST /api/capture_image` | `success=false, source=recent_cache, captured_at=...` |
| 页面含红条与列 | `curl /` 后检索关键字 | `cache-warning=True`、`注入样例=True`、`来源=True` |
| 补传闭环 | `python tools/backfill_fixture.py --count 3 --delay 45` | `PASS: 3 行均为 delivery_status=recovered + data_origin=simulated` |
| 历史接口字段 | `curl "/api/history?count=5"` | 3 条 `recovered/simulated` + 2 条 `live/device` |
| 心率仿真 | `python week17_migration_and_fix/heart_rate_simulator.py` | `ALL ASSERTIONS PASSED (live=5, recovered=23, dropped=5)` |
| 固件零改动 | `git diff -- '*.c'` | `diff_chars=0` |

---

## 八、本次变更文件

**代码（16 个）**

- 8 × `*/server/app.py`：缓存图不再冒充实时（week7 另含 `captured_at/age_seconds`）
- 8 × `*/server/templates/index.html`：新增 `recent_cache` 红条分支 + `.cache-warning` 样式
- `week13_14_15_edge_inference/server/app.py`：`data_origin` 迁移 + 两接口 4 字段 + 上传来源标记
- `week13_14_15_edge_inference/server/templates/index.html`：历史表「来源」列 + 三种徽章样式

**新增（4 个）**

- `week8_vision_feedback/README.md`
- `week17_migration_and_fix/heart_rate_simulator.py`
- `week13_14_15_edge_inference/tools/backfill_fixture.py`
- `Audit_Fix_Report.md`（本文件）

**文档修订（3 个）**

- `week13_14_15_edge_inference/README_SUBMIT.md`（声明 + main.c 表述 + 启动路径）
- `week17_migration_and_fix/README.md`（全文重写）
- `week18_final_acceptance/README.md`（VPS / tag / 补传标签 7 处）

**版本**：本地 tag `v1.0-final`（**未 push**）。

---

## 九、一句话结论

原系统里「缓存图冒充实时拍摄」是真造假，已从代码层根除（8 份拷贝）；
「视觉推理」「心率迁移」是夸大，现已降级为可核验的 Mock / 仿真并写明边界；
「VPS 未部署」是自我贬低的过时表述，已按实测改为「数据面通、Web 未上公网」。
剩下的做不到的部分没有一条被伪造成做得到。
