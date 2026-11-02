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

### 1.2 改后（week7 `app.py:871-893`）

```python
if os.path.isfile(latest_path):
    age = time.time() - os.path.getmtime(latest_path)
    if age < 30:                      # 有 30s 内文件：直接返回，不等待任何新图
        ...
        log.warning('Capture: recent cached image (age=%.1fs), NOT live', age)
        return jsonify({
            'success': False,
            'error': f'非本次采集：latest.jpg 是 {age:.1f}s 前上传的缓存图，本次未等待新图',
            'source': 'recent_cache',
            'captured_at': captured_at,
            'age_seconds': round(age, 1),
            'waited_seconds': 0.0,        # 本分支 0 等待
            'cache_file': 'latest.jpg',
            'image': ...
        })
# 只有「30s 内没有任何文件」才建 PENDING 并进入 60×0.5s 轮询（:913），超时返回
# {'success': False, 'source': 'timeout', 'waited_seconds': 30.0}（:930-931）
```

前端 `templates/index.html:690` 起新增 `recent_cache` 分支：叠加红条「⚠️ 非本次采集：这是 <拍摄时间> 的缓存图片（Ns 前）」，徽章降级为橙色「⚠️ 历史缓存」；样式 `:133`。

### 1.3 为什么「0.0s 前的图」也不是本次采集（回答 A 的自相矛盾）

判断逻辑只有两条互斥分支：

| 分支 | 触发条件 | 是否等待 | 返回 |
|---|---|---|---|
| 2a 缓存直返 | `latest.jpg` 存在且 `age < 30s` | **不等待**（`:871-893`） | `success:false / source:recent_cache / waited_seconds:0.0` |
| 2b+2c 请求新图 | 无 `latest.jpg` 或 `age ≥ 30s` | 建 PENDING 后 60×0.5s 轮询（`:913`） | 有新图 → `success:true / source:esp32_camera`；超时 → `404 / source:timeout / waited_seconds:30.0`（`:930-931`） |

所以 `age_seconds` 的含义是「**磁盘上那张 latest.jpg 距现在多久**」，不是「本次等了多久」；
本次等待时长由 `waited_seconds` 单独给出。旧文案把两者揉成一句「等待新图超时，当前仅有 0.0s 前的缓存图」，
而 2a 分支根本没等待 —— 这句描述本身是错的，已删除并用 `waited_seconds` 显式区分。

**上一版 `age_seconds: 0.0` 的来源必须交代**：那是我用 `os.utime` 把 `latest.jpg` 的 mtime 刷成「刚刚」，
人为造出的 0.0s。这个取证手法不规范（改动了被测对象），已作废，改用下面两段可重复用例重取。

### 1.4 实测重取（2026-10-29 12:36，week7，5000 端口）

T1：设备先上传一张 3974B 新图 → 1.5s 后浏览器点「拍照」

```
upload_jpeg=capture_20261001_161230.jpg bytes=3974 sha=6d183d4ff36c590f
UPLOAD       status=200 17ms {"filename":"capture_20261029_123600.jpg","message":"image saved","success":true}
AFTER-UPLOAD n_files=26 sha=6d183d4ff36c590f n_captured=15 n_requests=61
BROWSER      status=200 2ms
  success=False source=recent_cache waited_seconds=0.0 age_seconds=1.5 cache_file=latest.jpg
  captured_at=2026-10-29 12:36:00
  error=非本次采集：latest.jpg 是 1.5s 前上传的缓存图，本次未等待新图
  returned_bytes=3974 decoded_sha=6d183d4ff36c590f same_as_file=True
AFTER-BROWSER n_files=26 sha=6d183d4ff36c590f n_captured=15 n_requests=61
  CHECK sha_unchanged=True file_count_unchanged=True captured_rows_unchanged=True new_requests=0
```

T2：`latest.jpg` 置为 200s 前（构造陈旧缓存）→ 点「拍照」

```
BEFORE age=200s sha=6d183d4ff36c590f n_files=26 n_captured=15 n_requests=61
RESP   status=404 elapsed=30.7s {"error":"no images","source":"timeout","success":false,"waited_seconds":30.0}
AFTER  age=231s sha=6d183d4ff36c590f n_files=26 n_captured=15 n_requests=62
  CHECK sha_unchanged=True mtime_unchanged=True file_count_unchanged=True captured_rows_unchanged=True new_requests=1
  DB newest request: ('20261029_123601_BB01D8', 'PENDING', '2026-10-29 12:36:01', 'capture')
```

- T1 结论：返回图解码后与被上传的 3974B 文件 sha 相同，且本次**没有**新增文件 / `captured_images` 行 / 采集请求 ⇒ 这张图属于上一个请求，不是本次采集。
- T2 结论：等满 30s 超时（`waited_seconds=30.0`），`latest.jpg` 的 sha、mtime、文件数、`captured_images` 行数**全部未变**，只多一条 `PENDING` 请求 ⇒ 「等待超时后 latest.jpg 未被替换」可稳定复现。

### 1.5 同一段代码的 8 份拷贝

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

前端 8 个模板合计 `+171 -2`，后端 8 个文件合计 `+143 -52`（其中 week7 `+17 -6`、week13 `+41 -15`），均无整文件重写（`git diff --shortstat HEAD~1 -- ...` 即可核对）。

### 1.6 没有动的部分

`git diff -- '*.c'` → `diff_chars=0`。固件一行未改，拍照链路本身未被破坏。

---

## 二、Week8 / Week13_14_15：视觉推理是 Mock，却没有一句声明

### 2.1 改前

- `week8_vision_feedback/` **没有 README.md**（整个目录只有 server / firmware / 素材）。
- `week13_14_15_edge_inference/README_SUBMIT.md` 把 `/api/infer_image` 当普通能力列在「新增 API 路由」表里，全文没有 mock 字样；
  而 week8 `server/app.py:957` / week13 `server/app.py:1238` 写死 `ENABLE_MOCK_VISION = True`，
  `_mock_infer()`（week8 `:964` / week13 `:1245`）用 `random.choice()` 造标签，`model_version` 硬编码 `MOCK-V1`（week8 `:982` / week13 `:1263`）。
- `README_SUBMIT.md:180` 称「main.c / esp32_firmware — 零改动」（改前为 `:175`），实际 `week13_14_15_edge_inference/esp32_firmware/main/main.c:407` 有新增的 `device_infer_accel()`（调用点 `:419`、`:1199`）。
- `README_SUBMIT.md:191` 启动路径写成 `...\week13_edge_inference\server`（改前为 `:184`，目录不存在）。

### 2.2 改后

- 新建 `week8_vision_feedback/README.md`（122 行），第 0 节即「证据等级声明」表格：

| 项 | 事实 | 位置（改后 `git grep -n` 实测） |
|---|---|---|
| 推理开关 | `ENABLE_MOCK_VISION = True` | `server/app.py:957` |
| 结果来源 | `random.choice(VISION_LABELS)`，30% 低分演示 uncertain | `:964-983` |
| 版本标注 | `model_version = MOCK-V1` | `:982` |
| 调用点 | `if ENABLE_MOCK_VISION: result = _mock_infer()` | `:1003-1009` |
| 模型权重 | 无（仓库无 .onnx/.tflite/.pt） | — |
| 端侧部署 | 无 | — |

- `README_SUBMIT.md` 顶部加 5 行声明（含「云端 DeepSeek 未配置 Key，云路径实际未跑通」+ 本目录/week8 的精确行号）。
- `:180-182` 改为：main.c **并非零改动**，`device_infer_accel()` 是 if/else 阈值判定、**不含模型推理**；本次修复对 main.c 改动 0 字节。
- `:191` 路径更正为 `week13_14_15_edge_inference\server`。

**B：行号为什么会「对不上」** —— 三个原因，逐条给实测：

1. `954 / 961 / 979` 是 **week8** 的行号（当时 `git grep` 实测），不是 week13 的；
2. 本轮我又在 2a 分支插了 2 行、超时分支插了 1 行，week8 整体 +3 → 现在是 `957 / 964 / 982`；
3. 施工单里的 `week13_14_15/server/app.py:1212 / 1219 / 1237`，在当前 HEAD 上分别是「capture 轮询里的 `age` 计算」「轮询命中后的 `success: True`」「`VISION_LABELS` 第一行」，**都不是 mock 本体** —— 行号随代码演进漂移了。week13 的 mock 本体是 `:1238 / :1245 / :1263`。

当前 HEAD 实测（`git grep -n`，原样粘贴）：

```
week13_14_15_edge_inference/server/app.py:1238:ENABLE_MOCK_VISION = True
week13_14_15_edge_inference/server/app.py:1245:def _mock_infer():
week13_14_15_edge_inference/server/app.py:1263:        "model_version": "MOCK-V1"
week13_14_15_edge_inference/server/app.py:1284:    if ENABLE_MOCK_VISION:
week8_vision_feedback/server/app.py:957:ENABLE_MOCK_VISION = True
week8_vision_feedback/server/app.py:964:def _mock_infer():
week8_vision_feedback/server/app.py:982:        "model_version": "MOCK-V1"
week8_vision_feedback/server/app.py:1003:    if ENABLE_MOCK_VISION:
```

`README_SUBMIT.md` 两处修正的当前行号（`git diff -U0` + 带行首编号）：

```
@@ -8,0 +9,2 @@
+> 本目录代码位置（2026-10-29 `git grep -n` 实测）：`server/app.py:1238` 开关、`:1245` `_mock_infer()`、`:1263` `model_version`、`:1284-1290` 调用点；
+> week8 同源代码位于 `week8_vision_feedback/server/app.py:957 / :964 / :982`（`:1003-1009` 为调用点）。
  180| ### 本次红线修复未修改的文件
  182| - ⚠️ main.c — **第 13 周功能改动里已包含设备端阈值规则** `device_infer_accel()`（`esp32_firmware/main/main.c:407`，调用点 `:419`、`:1199`），属于 if/else 阈值判定、**不含任何模型推理**；2026-10-29 红线修复对 main.c 的改动为 **0 字节**（`git diff -- *.c` 输出 0 字符）
  191| cd "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week13_14_15_edge_inference\server"
```

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
| `app.py:502-503` | `/api/history` SELECT 增加 `id` 与 `original_ts, retransmit_ts, delivery_status, data_origin` |
| `app.py:511` / `:520` | 同上，dict 回吐（`id` / 四个字段） |
| `app.py:1047` / `:1066` | `/api/sensor_history` 同上 |
| `index.html:491` | 表头加「来源」列 |
| `index.html:1052-1054` | 行内渲染 🧪 注入样例 / 📡 真实设备 / 📦 补传 |

### 3.3 状态注入工具（新增）

`week13_14_15_edge_inference/tools/backfill_fixture.py`：走**真实** `POST /api/upload`，把 `original_ts` 设为 45s 前、
`retransmit_ts` 设为当前，让服务端按 `app.py:356-367` 自行判 `recovered`；再 `GET /api/history` 回读断言。
文件头已写明：**这是状态注入，不是实物断网**。

### 3.4 实测闭环（2026-10-29 12:37，week13_14_15，5000 端口）

**① 注入 3 条补传（真实 `POST /api/upload`，`data_origin=simulated`）**

```
[POST] /api/upload status=200 original_ts=1793248609 retransmit_ts=1793248654 -> {"server_time": "2026-10-29 12:37:34", "status": "ok"}
[POST] /api/upload status=200 original_ts=1793248608 retransmit_ts=1793248654 -> {"server_time": "2026-10-29 12:37:34", "status": "ok"}
[POST] /api/upload status=200 original_ts=1793248607 retransmit_ts=1793248654 -> {"server_time": "2026-10-29 12:37:34", "status": "ok"}
=== /api/history 回吐（仅本次注入行）===
original_ts | retransmit_ts | delivery_status | data_origin
 1793248609 |    1793248654 |       recovered | simulated
 1793248608 |    1793248654 |       recovered | simulated
 1793248607 |    1793248654 |       recovered | simulated
PASS: 3 行均为 delivery_status=recovered + data_origin=simulated
注意：这是状态注入结果，前端会显示「🧪 注入样例」标记；实物断网补传仍未验证。
[exit=0]
```

（上一版这里出现 `fixture_exit=1`：原因是我用 cp936 管道捕获子进程 stdout，脚本打印 🧪 时触发 `UnicodeEncodeError` 退出码 1；
加 `PYTHONIOENCODING=utf-8` 后 `exit=0`，断言本身一直是 PASS。已改正重现方式。）

**② `GET /api/history?count=5` 完整有序数组（含 `id`，不截断）**

```
status=200 n=5
[0] id=8  server_time=2026-10-29 12:17:07 original_ts=1793247381 retransmit_ts=1793247427 delivery=recovered origin=simulated
[1] id=9  server_time=2026-10-29 12:17:07 original_ts=1793247380 retransmit_ts=1793247427 delivery=recovered origin=simulated
[2] id=10 server_time=2026-10-29 12:37:01 original_ts=1793248576 retransmit_ts=1793248621 delivery=recovered origin=simulated
[3] id=11 server_time=2026-10-29 12:37:01 original_ts=1793248575 retransmit_ts=1793248621 delivery=recovered origin=simulated
[4] id=12 server_time=2026-10-29 12:37:01 original_ts=1793248574 retransmit_ts=1793248621 delivery=recovered origin=simulated
ASSERT 最后一条 delivery_status == recovered -> True
```

**排序口径（也就是我上一版贴错的地方）**：`app.py:504` 是 `ORDER BY id DESC`，紧接着 `:523 result.reverse() # oldest first`，
所以数组是**最旧 → 最新**，`records[-1]` 才是最新一条。上一版我贴的「recovered 在前、live 在后」两行是按我自己的挑选顺序排的，
不是接口顺序 —— 取证不规范，作废；以上是按 `records[0..4]` 原样打印。

**③ `GET /api/source_states`（徽章真正读的那个接口，`app.py:1424`）**

```
status=200 success=True n_sources=5
  source=camera           status=not_attempted transmission_status=live      is_delayed=False observation_time=None
  source=device_inference status=stale  transmission_status=live      is_delayed=False observation_time=2026-10-21T19:28:32
  source=gps              status=stale  transmission_status=live      is_delayed=False observation_time=2026-10-21T19:26:50.770838
  source=network          status=success transmission_status=recovered is_delayed=True  observation_time=2026-10-29T12:37:01
  source=sensor           status=stale  transmission_status=recovered is_delayed=True  observation_time=2026-10-29T12:36:14
ASSERT sensor.transmission_status == recovered -> True
```

> sensor 同时是 `status=stale`：`stale` 由 `SOURCE_STALE_THRESHOLDS`（按 `observation_time` 算年龄，`app.py:1460-1463`）决定，
> 与补传标记无关；徽章只看 `transmission_status`。两者并存不矛盾，但必须写清楚，否则容易被误读成「又实时又补传」。

**④ 页面徽章断言：拿模板里那段真实 JS + 上面的真实 JSON 求值（不是 `has_字样`）**

```
template line of marker = 1578
extracted lines 1579-1585:
    1579|                 var delayHtml = '';
    1580|                 if (src.transmission_status === 'recovered') {
    1581|                     delayHtml = '<div class="source-card-delay">📦 已接收（补传）'
    1582|                         + ' 原始时间：' + (src.observation_time || '--') + '</div>';
    1583|                 } else if (src.transmission_status === 'live' && src.status === 'success') {
    1584|                     delayHtml = '<div style="color:var(--green);font-size:13px;margin-top:4px;">✅ 已接收（实时）</div>';
    1585|                 }
node exit=0
rendered HTML: <div class="source-card-delay">📦 已接收（补传） 原始时间：2026-10-29T12:36:14</div>
ASSERT 含「📦 已接收（补传）」 -> True
ASSERT 含 source-card-delay 类（CSS 定义在模板 :244） -> True
ASSERT 不再出现「✅ 已接收（实时）」 -> True
```

> 这一步的两条边界必须写明：
> 1. 它是「真实模板代码 + 真实接口 JSON + Node 求值」，**不是浏览器截图**。本机 `playwright/selenium/jsdom` 三者都没有（实测 `missing`），
>    无法做 DOM 断言，也就没有伪造「页面已显示」的截图。
> 2. 注入数据是 `data_origin=simulated`，证明的是「服务端判定 → 落库 → 回吐 → 徽章渲染」整链通；
>    **不证明**设备在真实断网时缓存并补传。

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
3. 实跑结果（`python week17_migration_and_fix/heart_rate_simulator.py`，纯标准库、不联网）：

```
  6 |     72 |    09:00:06 |      09:00:44 |    38.0 | recovered
  7 |     75 |    09:00:07 |      09:00:44 |    37.0 | recovered
  8 |     78 |    09:00:08 |      09:00:44 |    36.0 | recovered
[WARN] QUEUE FULL, dropped oldest record: seq=13 hr=64
[INFO] flush -> 20 条补传记录，丢弃 5 条最旧记录

=== 计数口径（逐项可核对，不是自证）===
[COUNT] 样本总数 seq=33 = 阶段1 5(live) + 阶段2 3(进队列) + 阶段4 灌入 25
[COUNT] recovered=23 = 阶段3 补传 3 + 阶段4 补传 20
[COUNT] 阶段4：灌入 25 = 入队 20 + 丢弃最旧 5
[COUNT] live=5（阶段1 直传，retransmit_ts=0）

ALL ASSERTIONS PASSED (live=5, recovered=23, dropped=5)
```

**C：`flush -> 20` 与 `recovered=23` 为什么不矛盾**

`recovered` 是**全局累加**，`flush -> 20` 只是**阶段4 那一次** flush 的条数：

| 阶段 | 输入 | 结果 |
|---|---|---|
| 1 网络正常 | 5 拍 1Hz 直传 | `live = 5`（`retransmit_ts=0`） |
| 2 断网 | 3 拍进 20 槽环形队列 | 队列 3/20，未发送 |
| 3 网络恢复 | flush 3 拍，delay 36–38s > 30s | `recovered += 3` |
| 4 长时间断网 | 25 拍灌入 20 槽，丢最旧 5 条 | `dropped = 5`；flush 20 条 → `recovered += 20` |

合计：样本 `5 + 3 + 25 = 33`（断言 `seq == 33`）；`recovered = 3 + 20 = 23`；`dropped = 5`（只发生在阶段4）；`live = 5`。

`recovered` 不是自证：每条状态由 `RingCache.flush()` 按**与服务端同一条件**
（`retransmit_ts > 0 and (original_ts <= 0 or delay > 30)`，对齐 `app.py:363`）计算，
断言再独立检查 `retransmit_ts > original_ts`、`delay_s > 30`、`dropped == 5`、`len(recovered2) == QUEUE_SIZE`、`seq == 33`；
而这条规则本体已在 week14 服务端由 `tools/backfill_fixture.py` 实测通过（3.4 ②③）。

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
仓库内**没有 `.env`**，本次无法登录复验，因此不声称「我又跑通了一次」；
鉴权后的 `201 / id=10 / count=4` **全部引用** `week1_vps_upload/README_SUBMIT.md` 0.7 节的原记录（该记录标注为 2026-10-29 早前一轮联调，不是本次审计）。
`week18_final_acceptance/README.md:16` 已按你要求写成：

> 其中 `POST /api/data → 201 (id=10)`、`GET /api/data → count=4` 为**引用** `week1_vps_upload/README_SUBMIT.md` 0.7 节的既有记录，**本次审计未复验**（仓库内无 `.env`，无法登录）；本次只做了**未鉴权只读探活**：`GET /api/vps_history → 401`（26ms，说明服务在线且要求 Bearer）。

### 5.3 改后

- `:16` → 「其中 `POST /api/data → 201 (id=10)`、`GET /api/data → count=4` 为**引用** week1 0.7 节的既有记录，**本次审计未复验**（仓库内无 `.env`）；本次只做**未鉴权只读探活**：`GET /api/vps_history → 401`（26ms，说明服务在线且要求 Bearer）；**Web 控制台仍只跑本机局域网**，无域名/无生产级 TLS/无 gunicorn+nginx+systemd」。
- `:76` → 第1周「数据面已通，Web 未上公网」。
- `:89` → 「**VPS 仅覆盖数据面**」，仍不能宣称 Web 公网可用。
- `:79` / `:103` → 已补打本地 tag `v1.0-final`（当时注明不 push；**2026-11-02 已 push 远端**），此项销账。
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
| Python 语法（8 个后端 + 2 个新脚本） | `python -m py_compile ...` | `py_compile=0` |
| 前端 JS 语法（8 个模板） | `node --check` 提取的 script 块 | `node_check_failures=0` |
| 缓存图不再冒充实时（T1） | 设备上传 3974B → 1.5s 后 `POST /api/capture_image` | `success=false, source=recent_cache, waited_seconds=0.0, age_seconds=1.5`，返回图与上传文件 sha 相同，`new_files=0 / new_captured_rows=0 / new_requests=0` |
| 等待超时后 latest.jpg 未被替换（T2） | `latest.jpg` 置 200s 前 → `POST /api/capture_image` | `404, source=timeout, waited_seconds=30.0, elapsed=30.7s`，sha/mtime/文件数/`captured_images` 行数全未变，仅新增 1 条 `PENDING` |
| 补传闭环（服务端） | `PYTHONIOENCODING=utf-8 python tools/backfill_fixture.py --count 3 --delay 45` | `PASS: 3 行均为 delivery_status=recovered + data_origin=simulated`，`exit=0` |
| `/api/history` 有序数组 | `GET /api/history?count=5` | `records[0..4]` 全为 `recovered/simulated`，`records[-1].delivery_status == recovered`（`:523 reverse()` ⇒ 最旧在前） |
| 徽章数据源 | `GET /api/source_states` | `sensor.transmission_status=recovered, is_delayed=True`；`network` 同为 `recovered` |
| 徽章渲染（模板真代码 + 真 JSON） | 切出 `index.html:1579-1585` 交 Node 求值 | `<div class="source-card-delay">📦 已接收（补传）…</div>`，`node exit=0` |
| 心率仿真计数口径 | `python week17_migration_and_fix/heart_rate_simulator.py` | `[COUNT] seq=33 / recovered=23=3+20 / dropped=5 / live=5` + `ALL ASSERTIONS PASSED (live=5, recovered=23, dropped=5)` |
| 固件零改动 | `git diff -- '*.c'` | `diff_chars=0` |

> 未做：浏览器 DOM 断言 / 截图（本机无 `playwright`/`selenium`/`jsdom`，实测均 missing）；不拿「页面 has_字样」冒充「页面已渲染」。

---

## 八、本次变更文件

**代码（16 个）**

- 8 × `*/server/app.py`：缓存图不再冒充实时；本轮二次修正把 `'error'` 文案改成「非本次采集…本次未等待新图」，并新增 `waited_seconds`（缓存分支 0.0 / 超时分支 30.0）与 `cache_file`
- 8 × `*/server/templates/index.html`：新增 `recent_cache` 红条分支 + `.cache-warning` 样式
- `week13_14_15_edge_inference/server/app.py`：`data_origin` 迁移 + 两接口 4 字段 + 上传来源标记 + `/api/history` 回吐 `id`（便于逐条核对）
- `week13_14_15_edge_inference/server/templates/index.html`：历史表「来源」列 + 三种徽章样式

**新增（4 个）**

- `week8_vision_feedback/README.md`
- `week17_migration_and_fix/heart_rate_simulator.py`（本轮加 `[COUNT]` 计数口径段）
- `week13_14_15_edge_inference/tools/backfill_fixture.py`
- `Audit_Evidence_Raw.md`（A/D/C/自检 的原始控制台输出，未编辑）
- `Audit_Fix_Report.md`（本文件）

**文档修订（4 个）**

- `week13_14_15_edge_inference/README_SUBMIT.md`（证据声明 + 精确行号 + main.c 表述 + 启动路径）
- `week8_vision_feedback/README.md`（T1/T2 两段可重复取证替换原「改 mtime」写法）
- `week17_migration_and_fix/README.md`（全文重写 + 计数口径说明）
- `week18_final_acceptance/README.md`（VPS / tag / 补传标签；`:16` 改为「引用 week1 0.7 记录、本次未复验、仅 401 探活」）

**版本**：本地 tag `v1.0-final`（当时 **未 push**；**2026-11-02 已 push 远端**，指向本次文档收尾的最终提交）。本轮为审计后的补充取证，改动量：`git diff --stat HEAD` = 8 个后端 +44 -19，无前端改动。

---

## 九、补证索引（对应复核意见 A–E）

| 复核项 | 结论 | 本报告位置 | 原始输出 |
|---|---|---|---|
| **A** `age_seconds:0.0` 却说「等待超时」 | 文案本身是错的：`age<30` 分支**不等待**；已改文案并新增 `waited_seconds`（0.0 / 30.0）。上一版 0.0s 是我 `os.utime` 刷 mtime 造出来的，作废 | §1.3、§1.4 | `Audit_Evidence_Raw.md` 第 A 段（T1/T2） |
| **B** 行号对不上 | `954/961/979` 是 **week8** 改前行号，改后为 `957/964/982`；施工单的 week13 `1212/1219/1237` 在当前 HEAD 是 capture 轮询与 `VISION_LABELS`，mock 本体在 `1238/1245/1263` | §2.2 | 同上，`git grep -n` 原样粘贴 |
| **C** `flush -> 20` vs `recovered=23` | 不矛盾：`recovered` 全局累加 = 阶段3 的 3 + 阶段4 的 20；样本 33 = 5 + 3 + 25（20 入队 + 5 丢弃） | §4.3 | 第 C 段（含 `[COUNT]` 四行） |
| **D** 缺 `/api/source_states` 与徽章断言 | 已补：`/api/history?count=5` 完整有序数组（`records[-1]=recovered`）、`/api/source_states` 的 `transmission_status=recovered`、模板 `:1579-1585` 真实 JS 求值出「📦 已接收（补传）」；并声明不是浏览器截图 | §3.4 | 第 D/ D2 段 |
| **E** VPS 表述 | `week18_final_acceptance/README.md:16` 已写明「201/id=10/count=4 引用 week1 0.7 节记录，本次仅 401 探活、未复验鉴权后接口」 | §5.2、§5.3 | 第 V 段 `w18-16` 检查 |

**仍未关闭的**：tag/commit **只在本地，未 push**（按要求保持）。

> **2026-11-02 更新**：上述唯一未关闭项已关闭——`main` 分支与 tag `v1.0-final` 均已 push 到 `origin`；`git rev-parse 'v1.0-final^{}'` 与 `HEAD` 相同，`git status -sb` 显示 `## main`（0 ahead / 0 behind）。

---

## 十、一句话结论

原系统里「缓存图冒充实时拍摄」是真造假，已从代码层根除（8 份拷贝）；
「视觉推理」「心率迁移」是夸大，现已降级为可核验的 Mock / 仿真并写明边界；
「VPS 未部署」是自我贬低的过时表述，已按实测改为「数据面通、Web 未上公网」。
剩下的做不到的部分没有一条被伪造成做得到。

---

## 十一、批1（2026-10-29 13:50–14:35）：课程周次缺口修复（量纲 / no_fix / observed_at / 端口）

> 范围：`week1_vps_upload`、`week10_multi_source_state`、`week11_context_engine`、`week12_feedback_preferences`、`week13_14_15_edge_inference` 五份后端 + 五份 `templates/index.html` + 根 `README.md`。
> 铁律：验证**只用 5001**，5000 全程未起（`netstat -ano | findstr :5000` 无 `LISTENING`，收尾复核同上）。

### 11.1 四条改动与根因

| # | 缺陷（修前） | 根因 | 处置 | 落地位置 |
|---|---|---|---|---|
| 0 | 起第二实例验证必与现场 5000 抢端口 | 端口硬编码 | `_port = int(os.environ.get('PORT','5000'))`，默认不变 | week10 `:1332`、week11 `:1494`、week13 `:2019`（week12/week1 **按约定未改**） |
| 1 | `/api/local_infer` 恒判「可能在移动」 | 设备上报单位是 **g**（静止实测模长 1.31–1.34），代码拿 `9.81` 当基准 | `mag_g = mag if mag <= 4.0 else mag / 9.80665`；判据 `abs(mag_g - 1.0) > 0.5`；`detail` 输出 g | week13 `api_local_infer`、**week1 同源拷贝**（原以为只有 week13，实物发现 week1 也有，一并修） |
| 1b | `/api/context.derived_states.is_moving` 恒判移动 | 同上（另一处拷贝） | 同上换算，`accel_magnitude` 一并输出 g | week1/11/12/13 各 1 处 |
| 2 | GNSS 无解被写成 `failed`（把「没解」污名成「坏了」） | 状态机只有 success/failed | `simulate_no_fix` 写 `status='no_fix'`；**保旧值条件**扩为 `status in ('failed','no_fix')`（兼容库内历史 failed 行）；上下文 `gps.get('status') in ('failed','no_fix')` | 5 份后端 + 5 份前端 `statusText` 加 `no_fix:'🔵 无有效解（非故障）'` + `README.md:715` |
| 3 | `known_facts[].observed_at` 用「生成时刻」冒充「观测时刻」 | 直接 `t_fmt(now)` | `raw[name]` 增 `observation_time`（源的真实 `last_observation_time`）→ `src_time(src)` 解析，**失败返回空串，绝不回退 now**；5 处事实全部改源时间 | week11 先行；随后 week1 `:1863/1895/1915/1921/1932/1941/1956`、week12 `:1426/1458/1478/1484/1495/1504/1519`、week13 `:1566/1598/1618/1624/1635/1644/1659` |

> 改动3 的动机：`observed_at == 生成时刻` 时，「事实」与「何时观测到的」被绑死，等于没有时间证据。week1 是第 18 周现场版，只修 week11 等于现场演示仍是假时间。

### 11.2 实测矩阵（全部在 2026-10-29 本机复跑）

| 检查 | 手段 | 结果 |
|---|---|---|
| A1 端口参数化生效 | `PORT=5001` 起 week13，`GET /` + `POST /api/local_infer` | 日志 `Starting sensor dashboard on http://0.0.0.0:5001`，`local_infer HTTP 200`；无板时返回「画面不可用」（**正确语义**，不是推理结果） |
| A2 量纲分支 | scratch DB + `test_client`（不碰真实库、不监听端口） | `|a|=1.305` → `环境正常`(0.85)；`|a|=1.658` → `可能在移动`(0.5611)；`detail=加速度模长=1.66g（静止基准 1.0g）` |
| B no_fix 语义（live） | week10、week13 各起 5001 → `POST /api/simulate_no_fix` → 前后读 `source_states` | 两份均 `status=no_fix`，`previous_value` 仍保留 `lat 31.2304 / lng 121.4737`（旧坐标没丢） |
| C observed_at（fixture） | 四份 `test_client` + 两条 GPS 分支（新 8s / 过期 400s） | 见 11.3，`ALL PASS`；`observed_at` 分别等于源真实时间 14:32:02/03/04/00（B 场景 GPS 为 14:25:32），**均 ≠ now(14:32:12)** |
| D 静态 | `python -c "ast.parse(...)"` × 5；`git grep -n 't_fmt(now)' -- week12 week13 week1` | `AST OK: 5`；grep **0 命中**（exit=1） |
| E 量纲回归 | 同上 fixture | 四份 `accel_magnitude=1.383`、`is_moving=静止`、`uncertain=["GPS 无有效解，非故障"]` |
| F 端口收尾 | `netstat -ano` | 5001/5000 均无 `LISTENING`；只关了自己起的 PID，`msedge 21400` 未动 |

### 11.3 原始输出（节选，完整见 `evidence_batch1.zip`）

```
--- week1 A 新鲜 GPS(8s) -> 当前位置分支
  OK   当前可能静止 | source= 规则推断 | observed_at= 14:32:02
  OK   网络连接正常 | source= 网络连接 | observed_at= 14:32:03
  OK   当前位置 lat=31.2304 lng=121.4737 | source= 位置GPS | observed_at= 14:32:04
  OK   摄像头可用，最后采集 fixture_still.jpg | source= 摄像头 | observed_at= 14:32:00
  OK   observed_at 全都不等于 now(14:32:12)
--- week1 B 过期 GPS(400s) -> 上次报告位置分支
  OK   上次报告位置是 lat=31.2304 lng=121.4737 | observed_at= 14:25:32
  OK   no_fix 回归 -> ["GPS 无有效解，非故障"] | derived -> {"accel_magnitude": 1.383, "is_moving": "静止", ...}
RESULT week1 PASS
... week12 PASS / week13 PASS / week11 PASS
SUMMARY [('week1', True), ('week12', True), ('week13', True), ('week11', True)]
ALL PASS
```

week13 服务端日志（`evidence/batch1/week13_flask_tail200_batch1_20261029.log`，仅 `-Tail 200`）：

```
[2026-10-29 14:01:28] INFO >>> POST /api/local_infer ?   from 127.0.0.1
[2026-10-29 14:01:28] INFO 127.0.0.1 - - [29/Oct/2026 14:01:28] "POST /api/local_infer HTTP/1.1" 200 -
[2026-10-29 14:06:34] INFO Starting sensor dashboard on http://0.0.0.0:5001
[2026-10-29 14:06:36] INFO >>> POST /api/simulate_no_fix ?   from 127.0.0.1
[2026-10-29 14:06:36] INFO 127.0.0.1 - - [29/Oct/2026 14:06:36] "POST /api/simulate_no_fix HTTP/1.1" 200 -
```

week11 服务端日志（`evidence/batch1/week11_flask_tail200_batch1_20261029.log`）：

```
[2026-10-29 14:07:03] INFO Starting sensor dashboard on http://0.0.0.0:5001
[2026-10-29 14:07:04] INFO >>> GET /api/context ?   from 127.0.0.1
[2026-10-29 14:07:04] INFO 127.0.0.1 - - [29/Oct/2026 14:07:04] "GET /api/context HTTP/1.1" 200 -
```

### 11.4 缺口：week13「近端边缘」只能写到「接口通」

A1 在**无摄像头图**的条件下返回 `画面不可用`，这是正确语义，但**不能**据此写「端侧真实推理完成」。本批对此的口径固定为：

- 可写：`/api/local_infer` 接口通（HTTP 200）、量纲分支经 fixture 验证、无图时明确拒绝出结论；
- 不可写：真实图像推理、模型精度、端侧加速比；
- 待补条件：`week7` 相机出图（需烧录，本机无 ESP 板 / 无 COM 口）→ 拿真实 `latest.jpg` 再跑一次本接口并归档响应原文。

### 11.5 本批未做（写明，不粉饰）

| 项 | 原因 | 归属 |
|---|---|---|
| week12 端口参数化 | 约定本批只动 week10/11/13 | 批2 |
| week1 端口参数化 | 第 18 周现场版，保持 5000 硬编码，避免现场行为变化 | 不改 |
| W7 相机烧录 / 串口日志 | 无 ESP 板、无 COM 口（枚举仅 ACPI/蓝牙） | 需人工插板；`env_setup.ps1` 已备好 `Invoke-IdfPy` |
| DeepSeek key、视觉权重、MAX30102、真人被试 | 外部依赖未到 | 不阻塞批1 |
| `idf.py` 版本 | `ESP-IDF v5.4.4-dirty`（工作区有本地改动） | 仅记录 |

---

## 十二、最终总结（2026-11-02 定稿）：18 周状态分级

> 本节给整份报告收口。前三章都在讲「我改了什么」，这一节只回答一个问题：**18 周里，哪些能力拿得出证据，哪些拿不出，哪些是外部条件补不上。** 分级只看证据，不看代码量，也不看投入时间。

### 12.1 三类口径的判定标准

| 分级 | 判定标准（三条同时满足才算） | 允许对外的表述 | 不允许的表述 |
|---|---|---|---|
| **A　实机验证闭环** | ① 真实板子（ESP32-S3-EYE，COM4）参与；② 有串口日志 / 服务端日志 / DB 原始记录；③ 设备侧与服务器侧时间戳能互相对上 | 「已实测通过」 | —（A 类可以报数） |
| **B　代码修复、缺外部条件** | 代码存在且能跑（语法 / 接口级），但缺 API Key、模型权重、传感器器件或真人被试，端到端证据无法产生 | 「已实现，未验收」 | 「已完成」「已接通」 |
| **C　代码修复、缺实机证据** | 逻辑已用 fixture / `test_client` / 状态注入 / 既有日志自测过，但没有一次真实设备把该周主线完整走完 | 「逻辑验证通过，实机待补」 | 「已实测」「经测试可用」 |

> 一句话记住区别：**B 是「没条件做」，C 是「有条件但没做」**。B 可以归因于环境，C 只能记在留证不足或工期上。

### 12.2 18 周总表

| 周 | 主题 | 分级 | 证据（可核验位置） | 缺口 / 补证条件 |
|:--:|------|:--:|------|------|
| 1 | 周期性传感器上传 | **A** | 2026-11-02 实机：`POST /api/upload` → 200、`accelerometer` id=37、`STATS: ok=1 fail=0`（根 `README.md` §1「实机复验」）；VPS 数据面 39 条 `201`、`GET /api/data → count=42`（`week1_vps_upload/README_SUBMIT.md` 0.7） | 周期上传固件（`week1_periodic_upload/`）本轮未单独烧录，跑的是第 7 周固件的「请求触发上传」；补证：烧 week1 固件跑 60 s 看 `STATS` 计数 |
| 2 | 请求采集 / `request_id` 闭环 | **A** | `POST /api/request_collection` → `Poll: received request_id=20261102_093151_988A69` → **160 ms** 回传 → `collection_requests.COMPLETED`（根 `README.md` §2） | 无；五种状态（PENDING/RECEIVED/COMPLETED/CANCELLED/EXPIRED）在历史库均有真实记录 |
| 3 | 按键触发 / 取消反馈 | **A** | §3.1：三态 LCD（白→红→绿→白）+ ACK 往返 0.18 s；§3.2：`POST /api/cancel` → `rows_affected=1` → DB `CANCELLED` + `cancelled_at=14:04:47/14:04:48`（含 <1 s 触发即取消） | 无 |
| 4 | 自然语言查询（NLP Agent） | **B** | 双路径设计（云优先 + 本地规则）+ 9/9 单元测试（根 `README.md` §4） | `DEEPSEEK_API_KEY` 为空，**云路径 0 次执行**；补证：配 Key 后跑 5 条用例并归档响应原文 |
| 5 | 按键说话 / 语音播报 | **B** | 浏览器 Web Speech API 链路 + 5 场景（根 `README.md` §5） | 板载麦克风驱动未打通、无云端 ASR/TTS；补证：打通 I2S 麦克风 + 真实语音往返 |
| 6 | 任务取消与结果隔离 | **C** | 取消状态机 + 结果隔离 + `test_client` 用例（根 `README.md` §6） | 无「输入结束 → 首次反馈」时延实测；未用真实语音走完一次取消；补证：录屏 + 秒表或时间戳埋点 |
| 7 | 图像采集与防作弊 | **A** | 2026-11-02 09:32 实机：`Captured JPEG: 9434 bytes` → `CAPTURE: HTTP 200`（拍照→上传 **210 ms**）→ `capture_20261102_093209.jpg`，SOI/EOI 完整、SHA256 `FA2DA623…B8790885`、`captured_images` id=22；P3 超时误判已修（根 `README.md` §7.6） | 无 |
| 8 | 视觉推理与人工反馈 | **B** | 面板/低分 uncertain/人工纠正/重新采集 5 项通过，但全程 `MOCK-V1`（根 `README.md` §8.0） | 无权重、无 NPU 部署、教师基线未接入；补证：接入真实 VLM 基线并保留失败样本 |
| 9 | 视觉事件 → 主动询问 | **C** | 10 步完整流程 + 三选项（重拍/忽略/说明）（根 `README.md` §9.4） | **冷却时间未实现**（全文检索无 `cooldown`）；且事实源是第 8 周 mock 视觉 |
| 10 | 多源状态与归因 | **C** | `source_states` 4 行真实源；`observed_at` 与接收时间分离（批1 §11.2 C 项 `ALL PASS`，GPS 新 8 s / 过期 400 s 两分支） | 无 GNSS 硬件（回放数据已在系统内标注）；未接真实设备事件流跑一次完整归因 |
| 11 | 上下文组织（三层结构） | **C** | `raw_observations / derived_states / interaction` 三层 + 4 个当堂考点全 PASS（根 `README.md` §11.4：陈旧位置不包装、画面不可用不写危险、推断与观测可分、冲突源互不污染） | 事实源来自库里既有数据 + fixture，非本次实时设备数据 |
| 12 | 纠错影响后续提醒 | **C** | 偏好模型 + 透明注入钩子 + `config_version` 递增（根 `README.md` §12、§11.2） | `user_preferences` 仅 3–9 行自测数据，无真人纠错样本；补证：至少 1 名真实用户纠错 3 轮并留存版本号 |
| 13 | 边缘推理注册 + 云/本地回退 | **B** | 4 个 API（`/api/capabilities`、`/api/local_infer`、`/api/infer`、`/api/offline_status`）+ 断网横幅 15 s 轮询；无图时返回「画面不可用」而非编造结论（批1 §11.2 A1） | 本地是 `device_infer_accel()` 的 if/else 阈值，**不是模型**；无权重、无端侧加速数据 |
| 14 | 离线缓存与断网续传 | **A** | 2026-11-02 10:37–10:39：`queue` 峰值 **23/90**、`RETRANSMIT: sending 23 cached records` → `23/23 sent, 0 remain`、DB **19 条 `recovered`（delay 31–92 s）+ 4 条 `live`（17–27 s）**、0 丢失；BOD 由 `esp_wifi_set_max_tx_power(32)` 修复（根 `README.md` §5.1） | 无；10-21 另有 19 条真实补传记录（`week18_final_acceptance/evidence/week14_retransmit_records_20261021.csv`） |
| 15 | 重复 / 迟到 / 过期任务 | **C** | 服务端 `Duplicate upload ignored` **229 条**、`Task expired receipt recorded` **3 条**（含 `W15_EXPIRED_TEST`），DB 有对应 `EXPIRED`/`CANCELLED`（`week18_final_acceptance/README.md` §2） | 设备端防重放（`last_executed_request_id`）与 `expire_at` 比对只有开发者自测，无该项实机留证 |
| 16 | 可用性检验 | **B** | 同伴测试 n=2 原始观察与用户原话（`week16_usability_test/README.md`）：误触 1/2、横幅误读 1/2、补传时机理解 0/1 | 无录屏、无埋点、n=2 不具统计意义；补证：≥8 人 + 录屏 + 固定脚本 |
| 17 | 改进落地与个人项目迁移 | **B** | UI 改进真实落地（`index.html:578-611` 3 s 倒计时 + 横幅新文案）；心率迁移为设计 + 仿真，`ALL ASSERTIONS PASSED (live=5, recovered=23, dropped=5)` | 无 MAX30102 实物与驱动，未做真实心率采样；补证：接器件跑 1 Hz 并复现队列满丢最旧 |
| 18 | 现场验收与联合复盘 | **C** | `week18_final_acceptance/README.md`：能力清单 + 未完成项 + CSV 证据索引；tag `v1.0-final` **已推远端** | 归档中 3 条「未验证」已于 11-02 补实测（见 12.4），正文口径需同步；VPS 只做 401 探活，未重新登录复验 |

### 12.3 数量、交付边界与对外口径

**数量**：A = **5 周**（1/2/3/7/14）｜B = **6 周**（4/5/8/13/16/17）｜C = **7 周**（6/9/10/11/12/15/18）。

**可以对外说的三句话**

1. 「板端采集 → HTTP 上传 → SQLite 落库 → 页面回显」这条主链在**真实 ESP32-S3-EYE** 上跑通（第 1/2/7 周，串口 + 服务端 + DB 三源对得上）。
2. 按键触发/取消的全链路在真实硬件上闭环：LCD 三态 + ACK 0.18 s + 服务端 `REMOTE_ACKED`/`CANCELLED` + `cancelled_at`（第 3 周）。
3. 断网 89 s、缓存 23 条零丢失，恢复后 **15 s 内补传完毕**，19 条按 `delay > 30 s` 正确判为 `recovered`（第 14 周）。

**不能说的三句话**

1. ✗「已接入云端大模型 / 视觉模型」——第 4/13 周只有本地规则，第 8/9 周是 `MOCK-V1`，`DEEPSEEK_API_KEY` 全程为空。
2. ✗「已实现端侧 AI 推理」——第 13 周是加速度模长阈值分支，仓库内无任何 `.tflite` / `.espdl`。
3. ✗「可用性达标 / 用户满意」——第 16 周 n=2，只够定位问题，不构成统计结论。

### 12.4 对第六章「补不上的（外部条件）」与 §3.1 遗留缺口的现状更新

> 第六章与根 `README.md` §3.1 的遗留说明写于 2026-10-29 ～ 11-02 上午，当时本机无设备 / 服务端已停。11-02 下午拿到板子后，其中 3 条已经补齐，**原表述必须按此表更新**，其余条目仍然成立。

| 原条目（出处） | 2026-11-02 之后的状态 | 证据 |
|---|---|---|
| 真实设备断网补传（§六，原：「只提供 `recovered` **状态注入**证据，并标注非实物」） | **已补齐实物**：停服务端 89 s，23 条入队、0 丢失、19 条 `recovered` | 根 `README.md` §5.1；`evidence/week14/serial_week14.log`、`flask_week14.log`、`db_check.txt` |
| 真实拍照 / ESP32-CAM（§六，原：「板子不在手边，缓存分支已改为 `recent_cache`」） | **已补齐实物**：09:32 实拍 9,434 B 新图，SHA256 固定，非 `latest.jpg` 复用 | 根 `README.md` §7.6；`evidence/week07/REAL_DEVICE_20261102.md` |
| 第 3 周取消落库（根 `README.md` §3.1 遗留说明，原：「该行只停在 `REMOTE_ACKED`，`cancelled_at` 本就不该有值」） | **已补齐实物**：`CANCELLED` + `cancelled_at`，`rows_affected=1`，含 <1 s 触发即取消 | 根 `README.md` §3.2；`evidence/week3/cancel_evidence_1404.txt` |
| 真实视觉模型、云端语言模型、端侧模型、GNSS、板载麦克风、n=2 录屏（§六） | **仍未补**（外部条件或已过时点，事后无法补拍） | 见 12.2 的 B 类各行 |

### 12.5 剩余待办（按性价比排序，做完即可把 B/C 往 A 推）

| # | 待办 | 需要什么 | 推进哪一周 | 量级 |
|:--:|------|------|:--:|------|
| 1 | 烧 `week1_periodic_upload` 固件跑 60 s，抓 `STATS` 与 `flask.log` 计数 | 板子 + 1 次烧录 | 1（A→更硬） | 10 min |
| 2 | 配 `DEEPSEEK_API_KEY` 跑 5 条 NLP 用例并归档响应原文 | 一个 Key | 4、13 云路径 | 30 min |
| 3 | 补第 9 周冷却时间（`cooldown` 未实现），并用 fixture 断言 | 纯代码 | 9（功能缺口） | 1 h |
| 4 | 设备端防重放 / `expire_at` 比对的实机留证（同 §3.2 取证法） | 板子 + 20 min | 15（C→A） | 30 min |
| 5 | MAX30102 I2C 驱动 + 1 Hz 采样，复现队列满丢最旧 | 心率器件 | 17 | 1 天 |
| 6 | ≥8 人可用性测试 + 录屏 + 固定脚本 | 人 + 半天 | 16 | 半天 |
| 7 | 接入教师 VLM 基线替换 `_mock_infer()` | 权重 / 授权 | 8、9 | 1–2 天 |
| 8 | VPS 落地 gunicorn + nginx + 域名 + TLS | 域名 / 证书 | 1（部署入口） | 1 天 |

### 12.6 一句话结论

**18 周里，5 周（1/2/3/7/14）拿得出「板子 + 串口 + 服务端 + DB」四源对得上的实机证据，可以报「已实测通过」；6 周（4/5/8/13/16/17）缺 Key、缺权重、缺器件、缺真人，只能报「已实现，未验收」；7 周（6/9/10/11/12/15/18）逻辑已修、自测已过，但没有一次真实设备把该周主线完整走完，只能报「逻辑验证通过，实机待补」。** 这份分级不粉饰任何一条：能证明的写死，不能证明的写明为什么不能。

---

*最后更新：2026-11-02（Week3 取消落库与 Week14 断网补传实机取证之后）｜对应 tag：`v1.0-final`*
